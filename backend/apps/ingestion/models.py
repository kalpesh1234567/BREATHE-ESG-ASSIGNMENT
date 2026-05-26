"""
Ingestion models — the core of BreatheESG's data layer.

Design decisions:
- IngestionRun: one row per file upload; anchor for source-of-truth tracking
- EmissionFactor: versioned lookup; value is SNAPSHOTTED onto ActivityRecord at ingestion
  time so historical calculations are always reproducible even if the factor table is updated
- ActivityRecord: central fact table. raw_data preserves the original CSV row verbatim so
  analysts can always drill back to the source byte. co2e_kg is computed but NOT trusted for
  audit until status='locked'.
- AuditLog: append-only; records every state transition with before/after JSON snapshots
"""
import uuid
from django.db import models
from apps.core.models import Organization, User


class EmissionFactor(models.Model):
    """
    Versioned emission factor lookup.
    Values sourced from DEFRA 2024, US EPA eGRID2023, IEA, CEA India.
    """
    UNIT_PER_LITER = 'per_liter'
    UNIT_PER_KG = 'per_kg'
    UNIT_PER_M3 = 'per_m3'
    UNIT_PER_KWH = 'per_kwh'
    UNIT_PER_PKM = 'per_pkm'          # passenger-kilometre (travel)
    UNIT_PER_ROOM_NIGHT = 'per_room_night'
    UNIT_PER_KM = 'per_km'            # vehicle distance

    UNIT_CHOICES = [
        (UNIT_PER_LITER, 'per Liter'),
        (UNIT_PER_KG, 'per Kilogram'),
        (UNIT_PER_M3, 'per Cubic Meter'),
        (UNIT_PER_KWH, 'per kWh'),
        (UNIT_PER_PKM, 'per Passenger-km'),
        (UNIT_PER_ROOM_NIGHT, 'per Room-Night'),
        (UNIT_PER_KM, 'per km'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Category key — must match what parsers produce
    # e.g. 'fuel_diesel', 'fuel_natural_gas', 'electricity_uk', 'flight_economy_longhaul'
    category = models.CharField(max_length=100, db_index=True)
    value = models.DecimalField(max_digits=12, decimal_places=6)   # kgCO2e per unit
    unit = models.CharField(max_length=30, choices=UNIT_CHOICES)
    source = models.CharField(max_length=200)   # e.g. 'DEFRA 2024', 'EPA eGRID2023'
    region = models.CharField(max_length=100, blank=True)  # e.g. 'UK', 'US', 'IN', 'Global'
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)     # null = currently active
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-valid_from']
        indexes = [models.Index(fields=['category', 'valid_to'])]

    def __str__(self):
        return f"{self.category} — {self.value} kgCO2e/{self.unit} ({self.source})"


class IngestionRun(models.Model):
    """
    One row per file upload / ingestion attempt.
    This is the source-of-truth anchor: every ActivityRecord traces back to one run.
    file_hash (SHA-256) allows detection of duplicate uploads.
    """
    SOURCE_SAP_FUEL = 'sap_fuel'
    SOURCE_SAP_PROCUREMENT = 'sap_procurement'
    SOURCE_UTILITY = 'utility_electricity'
    SOURCE_TRAVEL = 'travel'

    SOURCE_CHOICES = [
        (SOURCE_SAP_FUEL, 'SAP — Fuel Consumption (MB51)'),
        (SOURCE_SAP_PROCUREMENT, 'SAP — Procurement (ME2M)'),
        (SOURCE_UTILITY, 'Utility — Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel (Concur/Navan)'),
    ]

    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ingestion_runs')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ingestion_runs')
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    filename = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64, blank=True)   # SHA-256 hex
    row_count = models.IntegerField(default=0)
    parsed_count = models.IntegerField(default=0)   # rows successfully parsed
    error_count = models.IntegerField(default=0)    # rows that failed parsing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROCESSING)
    error_detail = models.JSONField(default=list, blank=True)  # list of {row, message}
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.source_type} / {self.filename} ({self.status})"


class ActivityRecord(models.Model):
    """
    Central fact table. One row = one normalized activity event.

    Key design choices:
    - raw_data (JSONField): the original CSV row exactly as parsed, before any transformation.
      Analysts can always see where a number came from.
    - emission_factor_value: snapshotted at ingestion time. If DEFRA updates its factors next
      year, this record's historical CO2e remains reproducible.
    - status progresses: pending → (flagged | approved | rejected) → locked
      'locked' rows are immutable — no edits after analyst approval for audit.
    - is_edited + original_values: if an analyst corrects a value (e.g. wrong unit),
      both the new value and the original are preserved.
    """
    # ── Scope ────────────────────────────────────────────────────────────────
    SCOPE_1 = '1'
    SCOPE_2 = '2'
    SCOPE_3 = '3'
    SCOPE_CHOICES = [(SCOPE_1, 'Scope 1'), (SCOPE_2, 'Scope 2'), (SCOPE_3, 'Scope 3')]

    # ── Source types (mirrors IngestionRun) ──────────────────────────────────
    SOURCE_SAP_FUEL = 'sap_fuel'
    SOURCE_SAP_PROCUREMENT = 'sap_procurement'
    SOURCE_UTILITY = 'utility_electricity'
    SOURCE_TRAVEL = 'travel'
    SOURCE_CHOICES = [
        (SOURCE_SAP_FUEL, 'SAP Fuel (MB51)'),
        (SOURCE_SAP_PROCUREMENT, 'SAP Procurement (ME2M)'),
        (SOURCE_UTILITY, 'Utility Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    # ── Review status ────────────────────────────────────────────────────────
    STATUS_PENDING = 'pending'
    STATUS_FLAGGED = 'flagged'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_LOCKED = 'locked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_FLAGGED, 'Flagged — Needs Attention'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_LOCKED, 'Locked for Audit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='activity_records')
    ingestion_run = models.ForeignKey(IngestionRun, on_delete=models.CASCADE, related_name='records')

    # ── Classification ───────────────────────────────────────────────────────
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    # Fine-grained category — e.g. 'fuel_diesel', 'fuel_natural_gas', 'electricity_grid',
    # 'flight_economy_longhaul', 'hotel_stay', 'ground_taxi'
    category = models.CharField(max_length=100, db_index=True)

    # ── Raw preservation ─────────────────────────────────────────────────────
    # The original CSV row, stored verbatim. Never modified after ingestion.
    raw_data = models.JSONField()

    # ── Period ───────────────────────────────────────────────────────────────
    period_start = models.DateField()
    period_end = models.DateField()

    # ── Location / facility ──────────────────────────────────────────────────
    # SAP: plant code; Utility: meter ID; Travel: employee ID / cost center
    facility_code = models.CharField(max_length=200, blank=True)
    facility_description = models.CharField(max_length=500, blank=True)

    # ── Quantity — raw ───────────────────────────────────────────────────────
    quantity_raw = models.DecimalField(max_digits=18, decimal_places=4)
    unit_raw = models.CharField(max_length=50)    # exactly as it appeared in the source

    # ── Quantity — normalized ────────────────────────────────────────────────
    # All quantities converted to a canonical base unit before applying emission factors:
    # fuels → liters (or kg for solids), electricity → kWh, travel → passenger-km
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4)
    unit_normalized = models.CharField(max_length=50)

    # ── Emissions ────────────────────────────────────────────────────────────
    emission_factor = models.ForeignKey(
        EmissionFactor,
        on_delete=models.PROTECT,     # never delete a factor that was used
        null=True,
        related_name='activity_records',
    )
    # Snapshotted at ingestion time — immutable even if EmissionFactor row changes
    emission_factor_value = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    emission_factor_unit = models.CharField(max_length=30, blank=True)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True)

    # ── Flags ────────────────────────────────────────────────────────────────
    # Auto-flagged during ingestion for: negative quantity, missing EF, unit not recognized,
    # period > 1 year, reversal posting (SAP movement 102/122)
    is_suspicious = models.BooleanField(default=False)
    suspicion_reasons = models.JSONField(default=list)  # list of strings

    # ── Review workflow ──────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    flag_reason = models.TextField(blank=True)     # analyst's note when flagging/rejecting
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # ── Edit tracking ────────────────────────────────────────────────────────
    is_edited = models.BooleanField(default=False)
    original_values = models.JSONField(null=True, blank=True)  # snapshot of fields before edit
    edited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='edited_records'
    )
    edited_at = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'scope']),
            models.Index(fields=['organization', 'period_start', 'period_end']),
            models.Index(fields=['ingestion_run']),
        ]

    def __str__(self):
        return f"{self.category} | {self.period_start} | {self.co2e_kg} kgCO2e"

    @property
    def is_locked(self):
        return self.status == self.STATUS_LOCKED


class AuditLog(models.Model):
    """
    Append-only audit trail. Every state transition on an ActivityRecord is logged here.
    Rows are NEVER deleted or updated — only appended.
    """
    ACTION_INGESTED = 'ingested'
    ACTION_FLAGGED = 'flagged'
    ACTION_EDITED = 'edited'
    ACTION_APPROVED = 'approved'
    ACTION_REJECTED = 'rejected'
    ACTION_LOCKED = 'locked'
    ACTION_UNFLAGGED = 'unflagged'

    ACTION_CHOICES = [
        (ACTION_INGESTED, 'Ingested'),
        (ACTION_FLAGGED, 'Flagged'),
        (ACTION_EDITED, 'Edited'),
        (ACTION_APPROVED, 'Approved'),
        (ACTION_REJECTED, 'Rejected'),
        (ACTION_LOCKED, 'Locked for Audit'),
        (ACTION_UNFLAGGED, 'Unflagged'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    before_state = models.JSONField(null=True, blank=True)   # relevant fields before action
    after_state = models.JSONField(null=True, blank=True)    # relevant fields after action
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
        # No updates/deletes allowed — enforced at application layer

    def __str__(self):
        return f"{self.action} on {self.record_id} by {self.actor} at {self.timestamp}"
