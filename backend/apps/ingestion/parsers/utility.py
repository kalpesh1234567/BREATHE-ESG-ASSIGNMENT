"""
Utility electricity portal CSV parser.

Why CSV upload?
  Facilities teams universally know how to export CSVs from utility portals
  (PG&E, National Grid, Con Edison, etc.). PDF parsing is brittle and error-prone.
  Utility APIs exist but require per-utility OAuth integration — not realistic for
  a prototype serving multiple utilities. CSV is the 80% case.

What we handle:
  - Monthly billing summary CSVs (not interval/smart-meter data)
  - Billing periods that don't align with calendar months (e.g. Jan 18 → Feb 17)
    Stored as-is; carbon calculations use the actual billing period, not calendar month.
  - kWh and MWh (normalized to kWh)
  - Multiple meters per account
  - Demand charges (kW) — stored separately, NOT used for emission calculation
    (demand kW is a billing artifact, not energy consumption)
  - Multiple header format variants (utilities don't standardize)

What we don't handle:
  - Interval / 15-min / 30-min data (different use case — load shifting, not carbon accounting)
  - Gas utility bills (therms/CCF) — would need separate source type
  - PDF bills (out of scope by design — see TRADEOFFS.md)
  - Green Button XML format (not yet implemented)
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Optional

# ── Column header mappings ────────────────────────────────────────────────────
# Map various utility-portal column names to canonical names.
# Utilities don't standardize column names, so we map many variants.
COLUMN_MAP = {
    'account_number': 'account_number',
    'account number': 'account_number',
    'account no': 'account_number',
    'account no.': 'account_number',
    'account': 'account_number',

    'meter_id': 'meter_id',
    'meter id': 'meter_id',
    'meter number': 'meter_id',
    'meter no': 'meter_id',
    'meter': 'meter_id',

    'service_address': 'service_address',
    'service address': 'service_address',
    'address': 'service_address',
    'location': 'service_address',

    'billing_start': 'billing_start',
    'billing start': 'billing_start',
    'start date': 'billing_start',
    'from date': 'billing_start',
    'period start': 'billing_start',
    'read date from': 'billing_start',

    'billing_end': 'billing_end',
    'billing end': 'billing_end',
    'end date': 'billing_end',
    'to date': 'billing_end',
    'period end': 'billing_end',
    'read date to': 'billing_end',

    'kwh_consumption': 'kwh',
    'usage (kwh)': 'kwh',
    'usage(kwh)': 'kwh',
    'kwh used': 'kwh',
    'total kwh': 'kwh',
    'energy (kwh)': 'kwh',
    'consumption (kwh)': 'kwh',
    'kwh': 'kwh',

    'mwh_consumption': 'mwh',
    'usage (mwh)': 'mwh',
    'mwh used': 'mwh',
    'mwh': 'mwh',

    'peak_demand_kw': 'peak_demand_kw',
    'demand (kw)': 'peak_demand_kw',
    'peak demand': 'peak_demand_kw',
    'demand kw': 'peak_demand_kw',

    'rate_schedule': 'rate_schedule',
    'rate schedule': 'rate_schedule',
    'tariff': 'rate_schedule',
    'tariff code': 'rate_schedule',

    'total_bill': 'total_bill',
    'total bill': 'total_bill',
    'total amount': 'total_bill',
    'amount': 'total_bill',
}

DATE_FORMATS = [
    '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y',
    '%m-%d-%Y', '%Y/%m/%d', '%d.%m.%Y',
]


def parse_date(value: str) -> Optional[date]:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def parse_decimal(value: str) -> Optional[Decimal]:
    if not value or not value.strip():
        return None
    # Strip currency symbols, commas used as thousand separators
    cleaned = re.sub(r'[^\d.\-]', '', value.strip())
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def map_headers(raw_headers: list) -> dict:
    mapped = {}
    for i, h in enumerate(raw_headers):
        canonical = COLUMN_MAP.get(h.strip().lower())
        if canonical and canonical not in mapped:
            mapped[canonical] = i
    return mapped


def parse_utility_csv(file_content: bytes) -> tuple[list[dict], list[dict]]:
    """
    Parse a utility portal billing summary CSV.

    Returns:
        (records, errors)
        records: normalized dicts for ActivityRecord creation
        errors: list of {row_index, row_data, message}
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

    # Find header row (first row that contains recognizable utility column keywords)
    header_row_index = 0
    for i, line in enumerate(lines[:5]):
        lower = line.lower()
        if any(kw in lower for kw in ['kwh', 'meter', 'billing', 'account', 'usage']):
            header_row_index = i
            break

    reader = csv.reader(io.StringIO('\n'.join(lines[header_row_index:])))
    raw_headers = next(reader, None)
    if raw_headers is None:
        return [], [{'row_index': 0, 'message': 'No header row found'}]

    col_map = map_headers(raw_headers)

    # We need at least one energy column and billing dates
    if 'kwh' not in col_map and 'mwh' not in col_map:
        return [], [{
            'row_index': 0,
            'message': f'No energy consumption column found. Expected kWh or MWh column. '
                       f'Got: {raw_headers}'
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

        # ── Energy consumption ────────────────────────────────────────────
        kwh_val = None
        if 'kwh' in col_map:
            kwh_val = parse_decimal(get('kwh'))
        if kwh_val is None and 'mwh' in col_map:
            mwh = parse_decimal(get('mwh'))
            if mwh is not None:
                kwh_val = mwh * Decimal('1000')

        if kwh_val is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': 'Cannot parse energy consumption value'
            })
            continue

        if kwh_val <= 0:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Zero or negative kWh value ({kwh_val}) — skipping'
            })
            continue

        # ── Dates ─────────────────────────────────────────────────────────
        start_str = get('billing_start')
        end_str = get('billing_end')

        period_start = parse_date(start_str) if start_str else None
        period_end = parse_date(end_str) if end_str else None

        if period_start is None or period_end is None:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Cannot parse billing dates: start={start_str!r}, end={end_str!r}'
            })
            continue

        if period_end < period_start:
            errors.append({
                'row_index': row_index,
                'raw': raw_row,
                'message': f'Billing end {period_end} is before start {period_start}'
            })
            continue

        # ── Suspicious flags ──────────────────────────────────────────────
        suspicion_reasons = []
        billing_days = (period_end - period_start).days
        if billing_days > 35:
            suspicion_reasons.append(
                f'Billing period is {billing_days} days — unusually long (expected 28–32 for monthly)'
            )
        if billing_days < 25:
            suspicion_reasons.append(
                f'Billing period is only {billing_days} days — may be a partial period'
            )
        if kwh_val > 500_000:
            suspicion_reasons.append(
                f'Very high consumption: {kwh_val} kWh — verify this is correct'
            )

        # ── Facility identification ────────────────────────────────────────
        meter_id = get('meter_id', '')
        account_number = get('account_number', '')
        service_address = get('service_address', '')
        facility_code = meter_id or account_number
        facility_description = service_address or account_number

        records.append({
            'source_type': 'utility_electricity',
            'scope': '2',
            'category': 'electricity_grid',
            'raw_data': raw_row,
            'period_start': period_start,
            'period_end': period_end,
            'facility_code': facility_code,
            'facility_description': facility_description,
            'quantity_raw': kwh_val,
            'unit_raw': 'kWh',
            'quantity_normalized': kwh_val,
            'unit_normalized': 'kwh',
            'is_suspicious': len(suspicion_reasons) > 0,
            'suspicion_reasons': suspicion_reasons,
            # Extra display metadata
            '_account_number': account_number,
            '_meter_id': meter_id,
            '_rate_schedule': get('rate_schedule', ''),
            '_peak_demand_kw': get('peak_demand_kw', ''),
            '_total_bill': get('total_bill', ''),
        })

    return records, errors
