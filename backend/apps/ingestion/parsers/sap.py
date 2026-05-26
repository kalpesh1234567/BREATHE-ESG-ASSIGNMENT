"""
SAP MB51 flat-file parser — Fuel Consumption.

Why MB51 flat file?
  SAP clients can run this standard report with zero custom development — just 
  transaction MB51, set filters, and Export → Spreadsheet. IDoc/OData require 
  middleware or BASIS config most enterprise clients don't have pre-wired. 
  ME2M procurement exports use the same parsing logic with different field mappings.

What we handle:
  - Semicolon-delimited exports (standard for German-locale SAP, where comma = decimal)
  - German AND English column headers (dual-map approach)
  - Dates in DD.MM.YYYY format
  - European number format: 1.250,00 → 1250.00
  - Negative quantities = goods issue (consumption) — correct behavior
  - Positive quantities = goods receipt — flagged as suspicious
  - Movement type filtering: 201, 261, 331 = consumption; 101, 122 = receipt
  - SAP unit codes mapped to normalized units

What we deliberately don't handle:
  - IDoc XML format
  - OData JSON responses
  - Multi-level BOMs or batch splits
  - SAP special characters / codepages beyond UTF-8 and latin-1
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Optional

# ── Column name mappings: German → canonical, English → canonical ─────────────
COLUMN_MAP = {
    # German headers (German-locale SAP)
    'materialbel.': 'doc_number',
    'pos.': 'item',
    'buchungsdatum': 'posting_date',
    'bewegungsart': 'movement_type',
    'werk': 'plant',
    'lagerort': 'storage_location',
    'materialnummer': 'material',
    'materialbezeichnung': 'material_description',
    'menge': 'quantity',
    'me': 'unit',
    'basismengeneinheit': 'unit',
    'betrag hw': 'amount',
    'betrag in hw': 'amount',
    'währg': 'currency',
    'währung': 'currency',
    'kostenstelle': 'cost_center',
    'auftrag': 'order',
    # English headers
    'material doc.': 'doc_number',
    'material doc': 'doc_number',
    'posting date': 'posting_date',
    'movement type': 'movement_type',
    'plant': 'plant',
    'storage location': 'storage_location',
    'material': 'material',
    'material description': 'material_description',
    'quantity': 'quantity',
    'unit of entry': 'unit',
    'base unit': 'unit',
    'amount in lc': 'amount',
    'currency': 'currency',
    'cost center': 'cost_center',
    'order': 'order',
}

# SAP unit codes → normalized unit names
UNIT_MAP = {
    'L': 'liters',
    'LTR': 'liters',
    'GAL': 'gallons_us',
    'M3': 'cubic_meters',
    'm3': 'cubic_meters',
    'KG': 'kilograms',
    'T': 'tonnes',
    'TO': 'tonnes',
    'GJ': 'gigajoules',
    'MWH': 'mwh',
    'KWH': 'kwh',
    'KAR': None,   # carton — not a fuel unit, skip
    'ST': None,    # pieces — not a fuel unit, skip
    'EA': None,    # each — skip
}

# Conversion to liters (for liquid fuels) or kg (for solids/gases stored by weight)
# or cubic meters → liters (1 m3 = 1000 L)
UNIT_TO_LITERS = {
    'liters': Decimal('1'),
    'gallons_us': Decimal('3.78541'),
    'cubic_meters': Decimal('1000'),  # 1 m3 liquid = 1000 L
}

UNIT_TO_KG = {
    'kilograms': Decimal('1'),
    'tonnes': Decimal('1000'),
}

# Material code prefixes / keywords → fuel category
MATERIAL_CATEGORY_MAP = {
    'diesel': 'fuel_diesel',
    'kraftstoff': 'fuel_diesel',
    'heizöl': 'fuel_heating_oil',
    'hzoel': 'fuel_heating_oil',
    'erdgas': 'fuel_natural_gas',
    'gas': 'fuel_natural_gas',
    'benzin': 'fuel_petrol',
    'petrol': 'fuel_petrol',
    'lpg': 'fuel_lpg',
    'flüssiggas': 'fuel_lpg',
}

# Movement types that represent consumption (goods issue)
CONSUMPTION_MOVEMENT_TYPES = {'201', '261', '331', '551', '601'}
# Movement types that represent receipts (goods into stock)
RECEIPT_MOVEMENT_TYPES = {'101', '102', '122', '161', '501'}


def parse_german_number(value: str) -> Optional[Decimal]:
    """
    Parse European number format: 1.250,00 → 1250.00
    Also handles plain formats: 500.00, 500,00
    """
    if not value or not value.strip():
        return None
    v = value.strip().replace(' ', '')
    # European: dot = thousands separator, comma = decimal
    if re.match(r'^-?\d{1,3}(\.\d{3})*(,\d+)?$', v):
        v = v.replace('.', '').replace(',', '.')
    else:
        # Plain decimal or already normalized
        v = v.replace(',', '.')
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_sap_date(value: str) -> Optional[date]:
    """Parse SAP date formats: DD.MM.YYYY, MM/DD/YYYY, YYYY-MM-DD"""
    for fmt in ('%d.%m.%Y', '%m/%d/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def detect_delimiter(sample: str) -> str:
    """Detect whether the file uses semicolon or comma as delimiter."""
    semicolons = sample.count(';')
    commas = sample.count(',')
    return ';' if semicolons > commas else ','


def map_headers(raw_headers: list) -> dict:
    """Map raw CSV headers to canonical names using the column map."""
    mapped = {}
    for i, h in enumerate(raw_headers):
        canonical = COLUMN_MAP.get(h.strip().lower())
        if canonical and canonical not in mapped:
            mapped[canonical] = i
    return mapped


def infer_category(material_code: str, description: str) -> str:
    """Infer fuel category from material code or description text."""
    text = f"{material_code} {description}".lower()
    for keyword, category in MATERIAL_CATEGORY_MAP.items():
        if keyword in text:
            return category
    return 'fuel_unknown'


def normalize_quantity(quantity: Decimal, unit_raw: str) -> tuple[Optional[Decimal], str]:
    """
    Convert raw quantity to normalized base unit.
    Liquid fuels → liters
    Solid/gaseous fuels by weight → kilograms
    Natural gas → cubic meters (kept as-is; emission factor is per m3)
    """
    unit_norm = UNIT_MAP.get(unit_raw.strip())
    if unit_norm is None:
        return None, unit_raw

    if unit_norm in UNIT_TO_LITERS:
        return abs(quantity) * UNIT_TO_LITERS[unit_norm], 'liters'
    elif unit_norm in UNIT_TO_KG:
        return abs(quantity) * UNIT_TO_KG[unit_norm], 'kilograms'
    elif unit_norm == 'cubic_meters':
        return abs(quantity), 'cubic_meters'
    else:
        return abs(quantity), unit_norm


def parse_sap_mb51(file_content: bytes) -> tuple[list[dict], list[dict]]:
    """
    Parse a SAP MB51 export file (CSV/TSV).

    Returns:
        (records, errors)
        records: list of normalized dicts ready for ActivityRecord creation
        errors: list of {row_index, row_data, message}
    """
    records = []
    errors = []

    # Decode — try UTF-8 first, fall back to latin-1 (common in SAP exports)
    try:
        text = file_content.decode('utf-8-sig')   # utf-8-sig strips BOM
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    lines = text.splitlines()

    # Skip non-data header rows (SAP often prepends 1-3 report-title rows)
    # Find the actual header row by looking for a row that contains known column keywords
    header_row_index = 0
    for i, line in enumerate(lines[:10]):
        lower = line.lower()
        if any(kw in lower for kw in ['buchungsdatum', 'posting date', 'menge', 'quantity', 'werk', 'plant']):
            header_row_index = i
            break

    data_lines = lines[header_row_index:]
    if not data_lines:
        return [], [{'row_index': 0, 'message': 'No data rows found after header detection'}]

    delimiter = detect_delimiter(data_lines[0])
    reader = csv.reader(io.StringIO('\n'.join(data_lines)), delimiter=delimiter)

    raw_headers = next(reader, None)
    if raw_headers is None:
        return [], [{'row_index': 0, 'message': 'Empty file — no headers found'}]

    col_map = map_headers(raw_headers)

    required = ['posting_date', 'quantity', 'unit']
    missing_required = [r for r in required if r not in col_map]
    if missing_required:
        return [], [{
            'row_index': 0,
            'message': f'Required columns not found: {missing_required}. '
                       f'Got headers: {raw_headers[:10]}'
        }]

    for row_index, row in enumerate(reader, start=1):
        if not any(cell.strip() for cell in row):
            continue   # skip blank rows

        raw_row = dict(zip(raw_headers, row))

        def get(field, default=''):
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return default
            return row[idx].strip()

        # ── Parse date ────────────────────────────────────────────────────
        posting_date = parse_sap_date(get('posting_date'))
        if posting_date is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Cannot parse date: {get("posting_date")}'
            })
            continue

        # ── Parse quantity ────────────────────────────────────────────────
        qty = parse_german_number(get('quantity'))
        if qty is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Cannot parse quantity: {get("quantity")}'
            })
            continue

        unit_raw = get('unit', '').strip()
        if not unit_raw:
            errors.append({'row_index': row_index, 'raw': raw_row, 'message': 'Missing unit'})
            continue

        # ── Movement type ─────────────────────────────────────────────────
        movement_type = get('movement_type', '').strip()
        is_receipt = movement_type in RECEIPT_MOVEMENT_TYPES
        is_consumption = movement_type in CONSUMPTION_MOVEMENT_TYPES or movement_type == ''

        # ── Unit mapping ──────────────────────────────────────────────────
        mapped_unit = UNIT_MAP.get(unit_raw)
        if mapped_unit is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Unrecognized unit: {unit_raw} — skipping (not a fuel unit)'
            })
            continue

        qty_norm, unit_norm = normalize_quantity(qty, unit_raw)
        if qty_norm is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Cannot normalize quantity {qty} {unit_raw}'
            })
            continue

        # ── Category ──────────────────────────────────────────────────────
        material = get('material', '')
        description = get('material_description', '')
        category = infer_category(material, description)

        # ── Suspicious flags ──────────────────────────────────────────────
        suspicion_reasons = []
        if qty > 0 and is_receipt:
            suspicion_reasons.append(f'Goods receipt (movement {movement_type}) — not a consumption record')
        if qty > 0 and not is_receipt and movement_type not in CONSUMPTION_MOVEMENT_TYPES:
            suspicion_reasons.append('Positive quantity on unknown movement type — verify this is consumption')
        if category == 'fuel_unknown':
            suspicion_reasons.append(f'Could not identify fuel type from material {material!r} / {description!r}')

        records.append({
            'source_type': 'sap_fuel',
            'scope': '1',
            'category': category,
            'raw_data': raw_row,
            'period_start': posting_date,
            'period_end': posting_date,
            'facility_code': get('plant', ''),
            'facility_description': f"Plant {get('plant', '')} / Storage {get('storage_location', '')}",
            'quantity_raw': qty,
            'unit_raw': unit_raw,
            'quantity_normalized': qty_norm,
            'unit_normalized': unit_norm,
            'is_suspicious': len(suspicion_reasons) > 0,
            'suspicion_reasons': suspicion_reasons,
            # Extra metadata for display
            '_material': material,
            '_description': description,
            '_movement_type': movement_type,
            '_cost_center': get('cost_center', ''),
            '_doc_number': get('doc_number', ''),
        })

    return records, errors
