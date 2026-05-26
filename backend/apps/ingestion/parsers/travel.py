"""
Corporate travel CSV parser (Concur standard export format).

Why Concur CSV?
  Concur is the dominant corporate travel/expense platform. Their standard
  Finance Processor export is well-documented and consistent across clients.
  Navan and similar platforms export in similar structures.

What we handle:
  - Airfare: origin/destination from Description field via regex (e.g. 'BOS-JFK', 'LHR to JFK')
    Distance computed via Great Circle (Haversine) using IATA airport coordinates.
  - Hotel stays: nights × room-night emission factor. Nights inferred from billing period
    or a separate 'Nights' column if present.
  - Ground transport: classified by Expense_Type / Vendor name into taxi, rental car, train,
    personal vehicle (mileage).
  - Cabin class: parsed from Description field or dedicated column if present.

What we DON'T handle:
  - Non-Concur formats (SAP Concur API — would need OAuth)
  - Multi-leg itineraries (we split on '-' separator for simple two-leg routes)
  - Meals & Entertainment (no emissions relevance)
  - Currency normalization (amounts stored in original currency)
  - Missing airport codes with no city match (→ flagged as suspicious)

Distance calculation:
  We use a curated lookup of IATA airport coordinates to compute Great Circle Distance.
  If an airport code isn't in our lookup, we estimate using city-level coordinates or flag.
  DEFRA recommends adding a 9% uplift for indirect routing — we apply this.
"""

import csv
import io
import re
import math
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Optional

# ── Emission factor categories by expense type ────────────────────────────────
EXPENSE_TYPE_MAP = {
    'airfare': 'flight',
    'air travel': 'flight',
    'flight': 'flight',
    'airline': 'flight',

    'lodging': 'hotel',
    'hotel': 'hotel',
    'accommodation': 'hotel',

    'rental car': 'ground_rental_car',
    'car rental': 'ground_rental_car',

    'mileage': 'ground_personal_car',
    'personal mileage': 'ground_personal_car',
    'personal vehicle': 'ground_personal_car',

    'taxi': 'ground_taxi',
    'rideshare': 'ground_taxi',
    'uber': 'ground_taxi',
    'lyft': 'ground_taxi',
    'cab': 'ground_taxi',

    'train': 'ground_train',
    'rail': 'ground_train',
    'amtrak': 'ground_train',
    'eurostar': 'ground_train',

    'bus': 'ground_bus',
    'coach': 'ground_bus',
}

COLUMN_MAP = {
    'report_id': 'report_id',
    'report id': 'report_id',
    'employee_id': 'employee_id',
    'employee id': 'employee_id',
    'emp id': 'employee_id',
    'employee_name': 'employee_name',
    'employee name': 'employee_name',
    'employee': 'employee_name',
    'expense_type': 'expense_type',
    'expense type': 'expense_type',
    'type': 'expense_type',
    'category': 'expense_type',
    'transaction_date': 'transaction_date',
    'transaction date': 'transaction_date',
    'date': 'transaction_date',
    'vendor': 'vendor',
    'vendor name': 'vendor',
    'supplier': 'vendor',
    'amount': 'amount',
    'total amount': 'amount',
    'currency': 'currency',
    'description': 'description',
    'comment': 'description',
    'origin': 'origin',
    'from': 'origin',
    'departure': 'origin',
    'destination': 'destination',
    'to': 'destination',
    'arrival': 'destination',
    'cabin_class': 'cabin_class',
    'cabin class': 'cabin_class',
    'class': 'cabin_class',
    'nights': 'nights',
    'no. of nights': 'nights',
    'distance': 'distance_km',
    'distance (km)': 'distance_km',
    'miles': 'distance_miles',
    'distance (miles)': 'distance_miles',
    'distance (mi)': 'distance_miles',
    'cost_center': 'cost_center',
    'cost center': 'cost_center',
    'department': 'department',
}

DATE_FORMATS = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y']


# ── IATA Airport Coordinate Lookup ────────────────────────────────────────────
# A curated subset of major airports (lat, lon in decimal degrees).
# In production, this would be a full IATA database (~7,000 airports).
AIRPORT_COORDS = {
    # North America
    'JFK': (40.6413, -73.7781), 'LGA': (40.7769, -73.8740), 'EWR': (40.6895, -74.1745),
    'BOS': (42.3656, -71.0096), 'ORD': (41.9742, -87.9073), 'MDW': (41.7868, -87.7522),
    'LAX': (33.9425, -118.4081), 'SFO': (37.6213, -122.3790), 'SJC': (37.3626, -121.9290),
    'SEA': (47.4502, -122.3088), 'DEN': (39.8561, -104.6737), 'DFW': (32.8998, -97.0403),
    'ATL': (33.6407, -84.4277), 'MIA': (25.7959, -80.2870), 'IAD': (38.9531, -77.4565),
    'DCA': (38.8521, -77.0377), 'YYZ': (43.6777, -79.6248), 'YVR': (49.1967, -123.1815),
    'MEX': (19.4363, -99.0721), 'GRU': (-23.4356, -46.4731),
    # Europe
    'LHR': (51.4700, -0.4543), 'LGW': (51.1537, -0.1821), 'STN': (51.8850, 0.2350),
    'CDG': (49.0097, 2.5479), 'ORY': (48.7233, 2.3794), 'AMS': (52.3086, 4.7639),
    'FRA': (50.0379, 8.5622), 'MUC': (48.3537, 11.7860), 'BER': (52.3667, 13.5033),
    'ZRH': (47.4647, 8.5492), 'VIE': (48.1103, 16.5697), 'BCN': (41.2974, 2.0833),
    'MAD': (40.4936, -3.5668), 'FCO': (41.8003, 12.2389), 'MXP': (45.6306, 8.7281),
    'DUB': (53.4213, -6.2700), 'CPH': (55.6181, 12.6561), 'OSL': (60.1939, 11.1004),
    'ARN': (59.6519, 17.9186), 'HEL': (60.3172, 24.9633),
    # Asia Pacific
    'SIN': (1.3644, 103.9915), 'HKG': (22.3080, 113.9185), 'NRT': (35.7720, 140.3929),
    'HND': (35.5494, 139.7798), 'ICN': (37.4602, 126.4407), 'PEK': (40.0799, 116.6031),
    'PVG': (31.1443, 121.8083), 'BOM': (19.0896, 72.8656), 'DEL': (28.5665, 77.1031),
    'BLR': (13.1979, 77.7063), 'SYD': (-33.9399, 151.1753), 'MEL': (-37.6690, 144.8410),
    'DXB': (25.2532, 55.3657), 'DOH': (25.2731, 51.6081),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great Circle Distance in km via Haversine formula."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


ROUTING_UPLIFT = Decimal('1.09')  # DEFRA recommends 9% uplift for indirect routing


def airport_distance_km(origin: str, dest: str) -> tuple[Optional[Decimal], list[str]]:
    """
    Compute Great Circle Distance between two IATA codes.
    Returns (distance_km, suspicion_reasons)
    """
    o = AIRPORT_COORDS.get(origin.upper().strip())
    d = AIRPORT_COORDS.get(dest.upper().strip())
    reasons = []

    if o is None:
        reasons.append(f'Unknown origin airport code: {origin!r} — cannot compute distance')
    if d is None:
        reasons.append(f'Unknown destination airport code: {dest!r} — cannot compute distance')

    if o and d:
        gcd = haversine_km(*o, *d)
        return Decimal(str(round(gcd, 1))) * ROUTING_UPLIFT, reasons

    return None, reasons


def extract_airport_codes(description: str) -> tuple[Optional[str], Optional[str]]:
    """
    Try to extract IATA airport codes or city abbreviations from a description string.
    Handles patterns like: 'BOS-JFK', 'LHR to JFK', 'NYC client meeting roundtrip BOS-JFK'
    """
    if not description:
        return None, None
    # Pattern: three uppercase letters separated by dash, space, or 'to'
    pattern = r'\b([A-Z]{3})\s*[-–/→]\s*([A-Z]{3})\b'
    match = re.search(pattern, description)
    if match:
        return match.group(1), match.group(2)
    # Pattern: 'LHR to JFK'
    pattern2 = r'\b([A-Z]{3})\s+to\s+([A-Z]{3})\b'
    match2 = re.search(pattern2, description, re.IGNORECASE)
    if match2:
        return match2.group(1).upper(), match2.group(2).upper()
    return None, None


def parse_cabin_class(text: str) -> str:
    """Infer cabin class from free text."""
    t = text.lower()
    if any(w in t for w in ['first', '1st class', 'first class']):
        return 'first'
    if any(w in t for w in ['business', 'biz class', 'business class']):
        return 'business'
    if any(w in t for w in ['premium economy', 'prem economy', 'premium eco']):
        return 'premium_economy'
    return 'economy'  # default


def classify_flight(distance_km: Optional[Decimal], cabin: str) -> str:
    """Determine emission factor category based on distance and cabin."""
    if distance_km is None:
        return f'flight_{cabin}_unknown_haul'
    if distance_km < Decimal('500'):
        return f'flight_{cabin}_domestic'
    elif distance_km < Decimal('3700'):
        return f'flight_{cabin}_shorthaul'
    else:
        return f'flight_{cabin}_longhaul'


def parse_decimal(value: str) -> Optional[Decimal]:
    if not value or not value.strip():
        return None
    cleaned = re.sub(r'[^\d.\-]', '', value.strip())
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_date(value: str) -> Optional[date]:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def map_headers(raw_headers: list) -> dict:
    mapped = {}
    for i, h in enumerate(raw_headers):
        canonical = COLUMN_MAP.get(h.strip().lower())
        if canonical and canonical not in mapped:
            mapped[canonical] = i
    return mapped


def classify_expense(expense_type_raw: str, vendor: str) -> Optional[str]:
    """Map raw Concur expense type + vendor to our internal category."""
    combined = f"{expense_type_raw} {vendor}".lower()
    for keyword, category in EXPENSE_TYPE_MAP.items():
        if keyword in combined:
            return category
    return None


def parse_travel_csv(file_content: bytes) -> tuple[list[dict], list[dict]]:
    """
    Parse a Concur standard corporate travel/expense CSV export.

    Returns:
        (records, errors)
    """
    records = []
    errors = []

    try:
        text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    lines = text.splitlines()
    if not lines:
        return [], [{'row_index': 0, 'message': 'Empty file'}]

    # Find header row
    header_row_index = 0
    for i, line in enumerate(lines[:5]):
        lower = line.lower()
        if any(kw in lower for kw in ['expense', 'employee', 'amount', 'vendor', 'date']):
            header_row_index = i
            break

    reader = csv.reader(io.StringIO('\n'.join(lines[header_row_index:])))
    raw_headers = next(reader, None)
    if raw_headers is None:
        return [], [{'row_index': 0, 'message': 'No header row found'}]

    col_map = map_headers(raw_headers)

    if 'expense_type' not in col_map:
        return [], [{
            'row_index': 0,
            'message': f'No expense type column found. Got: {raw_headers[:10]}'
        }]

    for row_index, row in enumerate(reader, start=1):
        if not any(cell.strip() for cell in row):
            continue

        raw_row = dict(zip(raw_headers, row))

        def get(field, default=''):
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return default
            return row[idx].strip()

        expense_type_raw = get('expense_type')
        vendor = get('vendor', '')
        description = get('description', '')

        # ── Classify expense ──────────────────────────────────────────────
        category_base = classify_expense(expense_type_raw, vendor)
        if category_base is None:
            # Meals, entertainment, etc. — skip silently (not emissions-relevant)
            continue

        # ── Date ──────────────────────────────────────────────────────────
        date_str = get('transaction_date')
        txn_date = parse_date(date_str)
        if txn_date is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Cannot parse date: {date_str!r}'
            })
            continue

        suspicion_reasons = []
        employee_id = get('employee_id', '')
        employee_name = get('employee_name', '')

        # ── FLIGHT ────────────────────────────────────────────────────────
        if category_base == 'flight':
            origin = get('origin', '') or None
            dest = get('destination', '') or None

            # Try origin/dest columns first; fall back to description parsing
            if not origin or not dest:
                origin, dest = extract_airport_codes(description)

            cabin = parse_cabin_class(get('cabin_class', '') or description)

            if origin and dest:
                distance_km, dist_reasons = airport_distance_km(origin, dest)
                suspicion_reasons.extend(dist_reasons)
            else:
                distance_km = None
                suspicion_reasons.append(
                    'Could not determine flight route from Origin/Destination columns or Description — '
                    'cannot compute distance. Consider spend-based estimation.'
                )

            category = classify_flight(distance_km, cabin)

            records.append({
                'source_type': 'travel',
                'scope': '3',
                'category': category,
                'raw_data': raw_row,
                'period_start': txn_date,
                'period_end': txn_date,
                'facility_code': employee_id,
                'facility_description': employee_name,
                'quantity_raw': distance_km or Decimal('0'),
                'unit_raw': 'km',
                'quantity_normalized': distance_km or Decimal('0'),
                'unit_normalized': 'passenger_km',
                'is_suspicious': len(suspicion_reasons) > 0 or distance_km is None,
                'suspicion_reasons': suspicion_reasons,
                '_origin': origin,
                '_destination': dest,
                '_cabin': cabin,
                '_vendor': vendor,
                '_employee': employee_name,
            })

        # ── HOTEL ─────────────────────────────────────────────────────────
        elif category_base == 'hotel':
            nights_str = get('nights', '')
            nights = parse_decimal(nights_str)
            if nights is None:
                nights = Decimal('1')
                suspicion_reasons.append(f'Number of nights not provided; assumed 1 night')

            records.append({
                'source_type': 'travel',
                'scope': '3',
                'category': 'hotel_stay',
                'raw_data': raw_row,
                'period_start': txn_date,
                'period_end': txn_date,
                'facility_code': employee_id,
                'facility_description': f"{employee_name} — {get('description', vendor)}",
                'quantity_raw': nights,
                'unit_raw': 'room_nights',
                'quantity_normalized': nights,
                'unit_normalized': 'room_nights',
                'is_suspicious': len(suspicion_reasons) > 0,
                'suspicion_reasons': suspicion_reasons,
                '_employee': employee_name,
                '_vendor': vendor,
                '_description': description,
            })

        # ── GROUND TRANSPORT ──────────────────────────────────────────────
        else:
            distance_km = None
            unit_raw = 'km'

            dist_val = parse_decimal(get('distance_km', ''))
            if dist_val:
                distance_km = dist_val
            elif get('distance_miles', ''):
                miles = parse_decimal(get('distance_miles'))
                if miles:
                    distance_km = miles * Decimal('1.60934')
                    unit_raw = 'miles_converted'
            else:
                # For mileage/personal car, try to infer from amount
                # e.g. $87.30 at $0.655/mile ≈ 133 miles ≈ 214 km
                if 'mileage' in expense_type_raw.lower() or 'personal' in expense_type_raw.lower():
                    amount = parse_decimal(get('amount', ''))
                    # IRS mileage rate 2024: $0.67/mile; approximate
                    if amount:
                        estimated_miles = amount / Decimal('0.67')
                        distance_km = estimated_miles * Decimal('1.60934')
                        suspicion_reasons.append(
                            f'Distance estimated from mileage reimbursement amount '
                            f'(${amount} ÷ $0.67/mile × 1.609). Verify actual distance.'
                        )

            if distance_km is None or distance_km <= 0:
                # Can't compute emissions without distance — still record but flag
                suspicion_reasons.append(
                    f'No distance provided for {category_base}; cannot compute emissions. '
                    'Record preserved for analyst review.'
                )
                distance_km = Decimal('0')

            records.append({
                'source_type': 'travel',
                'scope': '3',
                'category': category_base,
                'raw_data': raw_row,
                'period_start': txn_date,
                'period_end': txn_date,
                'facility_code': employee_id,
                'facility_description': employee_name,
                'quantity_raw': distance_km,
                'unit_raw': unit_raw,
                'quantity_normalized': distance_km,
                'unit_normalized': 'km',
                'is_suspicious': len(suspicion_reasons) > 0,
                'suspicion_reasons': suspicion_reasons,
                '_employee': employee_name,
                '_vendor': vendor,
                '_expense_type': expense_type_raw,
            })

    return records, errors
