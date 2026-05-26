"""
Ingestion orchestration — ties parsers to models and emission factor lookup.
"""
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from apps.ingestion.models import IngestionRun, ActivityRecord, EmissionFactor, AuditLog
from apps.ingestion.parsers.sap import parse_sap_mb51
from apps.ingestion.parsers.utility import parse_utility_csv
from apps.ingestion.parsers.travel import parse_travel_csv


# Emission factor category → EF category key (matches EmissionFactor.category)
CATEGORY_EF_MAP = {
    # Scope 1 — Fuel
    'fuel_diesel': 'fuel_diesel',
    'fuel_heating_oil': 'fuel_heating_oil',
    'fuel_natural_gas': 'fuel_natural_gas',
    'fuel_petrol': 'fuel_petrol',
    'fuel_lpg': 'fuel_lpg',
    'fuel_unknown': None,  # can't compute emissions without knowing fuel type

    # Scope 2 — Electricity
    'electricity_grid': 'electricity_uk',   # default region; configurable

    # Scope 3 — Travel
    'flight_economy_domestic': 'flight_economy_domestic',
    'flight_economy_shorthaul': 'flight_economy_shorthaul',
    'flight_economy_longhaul': 'flight_economy_longhaul',
    'flight_economy_unknown_haul': 'flight_economy_shorthaul',  # conservative default
    'flight_business_domestic': 'flight_business_shorthaul',
    'flight_business_shorthaul': 'flight_business_shorthaul',
    'flight_business_longhaul': 'flight_business_longhaul',
    'flight_business_unknown_haul': 'flight_business_longhaul',
    'flight_premium_economy_longhaul': 'flight_premium_economy_longhaul',
    'flight_first_longhaul': 'flight_first_longhaul',
    'hotel_stay': 'hotel_stay',
    'ground_rental_car': 'ground_rental_car',
    'ground_personal_car': 'ground_personal_car',
    'ground_taxi': 'ground_taxi',
    'ground_train': 'ground_train',
    'ground_bus': 'ground_bus',
}


def get_emission_factor(category: str) -> tuple:
    """
    Look up the current active emission factor for a category.
    Returns (EmissionFactor instance or None, value or None, unit or None)
    """
    ef_key = CATEGORY_EF_MAP.get(category)
    if ef_key is None:
        return None, None, None

    ef = EmissionFactor.objects.filter(
        category=ef_key,
        valid_to__isnull=True,   # currently active
    ).order_by('-valid_from').first()

    if ef is None:
        return None, None, None

    return ef, ef.value, ef.unit


def compute_co2e(quantity_normalized: Decimal, ef_value: Decimal) -> Decimal:
    """quantity × emission factor = kgCO2e"""
    if quantity_normalized is None or ef_value is None:
        return None
    return (quantity_normalized * ef_value).quantize(Decimal('0.0001'))


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ingest_file(
    run: IngestionRun,
    file_content: bytes,
    user,
) -> None:
    """
    Parse the file, normalize records, compute emissions, and persist to DB.
    Updates the IngestionRun status on completion or failure.
    """
    run.file_hash = sha256_hash(file_content)
    run.status = IngestionRun.STATUS_PROCESSING
    run.save(update_fields=['file_hash', 'status'])

    try:
        if run.source_type in (IngestionRun.SOURCE_SAP_FUEL, IngestionRun.SOURCE_SAP_PROCUREMENT):
            parsed_records, errors = parse_sap_mb51(file_content)
        elif run.source_type == IngestionRun.SOURCE_UTILITY:
            parsed_records, errors = parse_utility_csv(file_content)
        elif run.source_type == IngestionRun.SOURCE_TRAVEL:
            parsed_records, errors = parse_travel_csv(file_content)
        else:
            raise ValueError(f'Unknown source type: {run.source_type}')

        # Persist parsed records
        created_count = 0
        for rec_data in parsed_records:
            category = rec_data['category']
            ef, ef_value, ef_unit = get_emission_factor(category)

            # Flag if no emission factor found
            suspicion_reasons = rec_data.get('suspicion_reasons', [])
            if ef is None and rec_data.get('quantity_normalized', Decimal('0')) > 0:
                suspicion_reasons.append(
                    f'No emission factor found for category {category!r} — CO₂e not computed'
                )
                rec_data['is_suspicious'] = True

            quantity_norm = rec_data.get('quantity_normalized')
            co2e = compute_co2e(quantity_norm, ef_value) if ef else None

            # Extract private _keys not meant for model fields
            extra_keys = [k for k in rec_data if k.startswith('_')]
            for k in extra_keys:
                rec_data.pop(k)

            record = ActivityRecord.objects.create(
                organization=run.organization,
                ingestion_run=run,
                source_type=rec_data['source_type'],
                scope=rec_data['scope'],
                category=category,
                raw_data=rec_data['raw_data'],
                period_start=rec_data['period_start'],
                period_end=rec_data['period_end'],
                facility_code=rec_data.get('facility_code', ''),
                facility_description=rec_data.get('facility_description', ''),
                quantity_raw=rec_data['quantity_raw'],
                unit_raw=rec_data['unit_raw'],
                quantity_normalized=rec_data['quantity_normalized'],
                unit_normalized=rec_data['unit_normalized'],
                emission_factor=ef,
                emission_factor_value=ef_value,
                emission_factor_unit=ef_unit or '',
                co2e_kg=co2e,
                is_suspicious=rec_data.get('is_suspicious', False),
                suspicion_reasons=suspicion_reasons,
                status=ActivityRecord.STATUS_PENDING,
            )

            # Write initial audit log entry
            AuditLog.objects.create(
                record=record,
                actor=user,
                action=AuditLog.ACTION_INGESTED,
                after_state={
                    'status': record.status,
                    'co2e_kg': str(co2e) if co2e else None,
                    'category': category,
                },
            )

            if record.is_suspicious:
                AuditLog.objects.create(
                    record=record,
                    actor=user,
                    action=AuditLog.ACTION_FLAGGED,
                    after_state={'suspicion_reasons': suspicion_reasons},
                    note='Auto-flagged during ingestion',
                )

            created_count += 1

        run.parsed_count = created_count
        run.error_count = len(errors)
        run.error_detail = errors
        run.row_count = created_count + len(errors)
        run.status = IngestionRun.STATUS_COMPLETE
        run.completed_at = datetime.now(timezone.utc)
        run.save()

    except Exception as exc:
        run.status = IngestionRun.STATUS_FAILED
        run.error_detail = [{'message': str(exc)}]
        run.completed_at = datetime.now(timezone.utc)
        run.save()
        raise
