# MODEL.md — BreatheESG Data Model

## Overview

The data model is built around four core design principles:

1. **Multi-tenancy by default** — Every row of emissions data belongs to exactly one `Organization`. Query filtering at the ORM layer prevents cross-tenant data access.
2. **Immutable source preservation** — Raw CSV rows are stored verbatim in a `JSONField` so the source of any number can always be traced.
3. **Emission factor snapshotting** — The factor value used to compute CO₂e is written onto each `ActivityRecord` at ingestion time. If DEFRA updates its factors next year, historical records remain exactly reproducible.
4. **Append-only audit trail** — Every state change (ingested → flagged → approved → locked) writes a new `AuditLog` row. Nothing is deleted or updated in that table.

---

## Entity Relationship

```
Organization
    │
    ├── User (role: analyst | admin)
    │
    ├── IngestionRun  (one per file upload)
    │       │
    │       └── ActivityRecord  (one per parsed row)
    │               │
    │               ├── EmissionFactor (FK, value snapshotted)
    │               │
    │               └── AuditLog  (append-only, N per record)
    │
    └── EmissionFactor  (global lookup table)
```

---

## Tables

### `Organization`
Multi-tenant root. Every other table FK's back to this.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR(255) | Display name |
| slug | SlugField unique | Used in URLs |
| created_at | TIMESTAMP | |

**Why UUID PKs?** URL-safe and prevents enumeration attacks across tenants.

---

### `User`
Extends Django's `AbstractUser`. Two roles with different capabilities.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization | FK → Organization | NULL allowed for Django superusers |
| role | ENUM(analyst, admin) | analyst: review/approve; admin: can also lock |

**Why not separate permission tables?** With only two roles and a small team, the overhead of fine-grained RBAC isn't justified. If this scales to 50+ analysts with varied scopes, we'd migrate to Django's built-in `Permission` model.

---

### `EmissionFactor`
Global lookup table with versioning. A record is "currently active" when `valid_to IS NULL`.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| category | VARCHAR(100) | e.g. `fuel_diesel`, `flight_economy_longhaul` |
| value | DECIMAL(12,6) | kgCO₂e per unit |
| unit | ENUM | `per_liter`, `per_kwh`, `per_pkm`, `per_room_night`, `per_km`, `per_m3`, `per_kg` |
| source | VARCHAR(200) | e.g. `DEFRA 2024`, `EPA eGRID2023` |
| region | VARCHAR(100) | e.g. `UK`, `US`, `Global` |
| valid_from | DATE | |
| valid_to | DATE nullable | NULL = currently active |
| notes | TEXT | Methodology notes |

**Why snapshot onto ActivityRecord?** If you update the factor table (new DEFRA release), all unapproved records recalculate but locked historical records must remain unchanged for audit. Snapshotting the value solves this cleanly without soft-versioning the factor table.

---

### `IngestionRun`
One row per upload event. The source-of-truth anchor for all records produced by that upload.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization | FK → Organization | |
| uploaded_by | FK → User | |
| source_type | ENUM | `sap_fuel`, `sap_procurement`, `utility_electricity`, `travel` |
| filename | VARCHAR(500) | Original filename preserved |
| file_hash | CHAR(64) | SHA-256 of file bytes — detects re-uploads |
| row_count | INT | Total rows in file |
| parsed_count | INT | Successfully parsed |
| error_count | INT | Failed rows |
| status | ENUM | `processing` → `complete` or `failed` |
| error_detail | JSONField | `[{row_index, message, raw}]` |
| uploaded_at | TIMESTAMP | |
| completed_at | TIMESTAMP nullable | |

**Why SHA-256?** We can detect and warn on duplicate uploads before creating duplicate `ActivityRecord` rows. In production, you'd block re-uploads or let the user confirm.

---

### `ActivityRecord` — Central Fact Table

One row = one normalized activity event. This is the most important model in the system.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization | FK → Organization | Multi-tenant isolation |
| ingestion_run | FK → IngestionRun | Source-of-truth: which upload produced this |
| source_type | ENUM | Mirrors IngestionRun |
| scope | ENUM(1,2,3) | GHG Protocol scope |
| category | VARCHAR(100) | e.g. `fuel_diesel`, `electricity_grid`, `flight_economy_longhaul` |
| **raw_data** | **JSONField** | **Original CSV row, verbatim. Never modified.** |
| period_start | DATE | Actual activity period (not ingestion date) |
| period_end | DATE | May span multiple calendar months (utility bills) |
| facility_code | VARCHAR(200) | SAP plant code / utility meter ID / employee ID |
| facility_description | VARCHAR(500) | Human-readable location |
| quantity_raw | DECIMAL(18,4) | As it appeared in source |
| unit_raw | VARCHAR(50) | As it appeared in source (e.g. `L`, `m3`, `kWh`) |
| quantity_normalized | DECIMAL(18,4) | In canonical base unit |
| unit_normalized | VARCHAR(50) | `liters`, `kwh`, `passenger_km`, `room_nights`, `km` |
| emission_factor | FK → EmissionFactor | |
| **emission_factor_value** | **DECIMAL(12,6)** | **Snapshotted at ingestion** |
| emission_factor_unit | VARCHAR(30) | Snapshotted |
| **co2e_kg** | **DECIMAL(18,4)** | **Computed. Not trusted for audit until status=locked** |
| is_suspicious | BOOLEAN | Auto-set during parsing |
| suspicion_reasons | JSONField | List of strings explaining why flagged |
| status | ENUM | `pending` → `flagged`/`approved`/`rejected` → `locked` |
| flag_reason | TEXT | Analyst's note |
| reviewed_by | FK → User | |
| reviewed_at | TIMESTAMP | |
| is_edited | BOOLEAN | Set when analyst corrects a value |
| original_values | JSONField | Snapshot of fields before first edit |
| edited_by | FK → User | |
| edited_at | TIMESTAMP | |
| created_at / updated_at | TIMESTAMPS | |

**Status lifecycle:**
```
pending → approved → locked   (normal flow)
pending → flagged  → approved → locked
pending → rejected            (dead end — must re-ingest to correct)
```

**Locking semantics:** `locked` records are immutable at the application layer. No PATCH request is accepted. Only admins can trigger locking. Locked = ready for external auditor access.

**Why store `raw_data` as JSON?** Every source has different fields. A union table approach (with nullable columns for SAP-specific fields, utility-specific fields, etc.) would be a schema maintenance nightmare. JSON lets us preserve the exact original row without schema changes per new source type.

**Why not recompute CO₂e on the fly?** Audit stability. If an emission factor changes, locked records must use the factor that was active when they were ingested. By storing `emission_factor_value`, we can always reproduce the exact historical calculation.

---

### `AuditLog`
Append-only. Never modified after creation.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| record | FK → ActivityRecord | |
| actor | FK → User | NULL if system action |
| action | ENUM | `ingested`, `flagged`, `edited`, `approved`, `rejected`, `locked`, `unflagged` |
| before_state | JSONField | Relevant field snapshot before action |
| after_state | JSONField | Relevant field snapshot after action |
| note | TEXT | Free text from analyst |
| timestamp | TIMESTAMP | auto_now_add |

**Why not use Django signals?** Explicit audit log writes in the service layer are more predictable, easier to test, and give us control over what goes in `before_state`/`after_state`. Signal-based auditing can miss updates that bypass the model's `save()` method.

---

## Scope Classification

| Scope | Definition | Sources in this app |
|---|---|---|
| 1 | Direct emissions from owned/controlled sources | SAP MB51 fuel consumption |
| 2 | Purchased electricity, steam, heat | Utility billing CSV |
| 3 Cat. 6 | Business travel | Concur corporate travel export |

Scope 3 categories not implemented: upstream supply chain (Cat. 1), employee commuting (Cat. 7), waste (Cat. 5). See TRADEOFFS.md.

---

## Unit Normalization

All quantities are converted to canonical base units before applying emission factors:

| Source unit | Canonical | Conversion |
|---|---|---|
| L (liters) | liters | ×1 |
| GAL (US gallons) | liters | ×3.78541 |
| m3 (cubic meters, liquid) | liters | ×1000 |
| m3 (natural gas) | cubic_meters | ×1 (EF is per m³) |
| KG | kilograms | ×1 |
| TO/T (tonnes) | kilograms | ×1000 |
| kWh | kwh | ×1 |
| MWh | kwh | ×1000 |
| passenger-km | passenger_km | ×1 |
| miles | km | ×1.60934 |
| room-nights | room_nights | ×1 |

Raw values are always preserved in `quantity_raw` + `unit_raw`.

---

## Indexes

Composite indexes on:
- `(organization, status)` — powers the review queue filter
- `(organization, scope)` — powers the dashboard scope breakdown
- `(organization, period_start, period_end)` — powers date-range queries
- `(ingestion_run)` — powers the "view all records from this upload" query
- `(category, valid_to)` on EmissionFactor — powers factor lookup

---

## Multi-Tenancy Enforcement

Tenant isolation is enforced at two levels:
1. **ORM level:** All querysets in API views filter by `request.user.organization`. No raw SQL that could cross tenant boundaries.
2. **URL level:** Resource IDs are UUIDs — not guessable. Record ownership is always re-verified on access: `ActivityRecord.objects.get(id=pk, organization=user.organization)`.

In production, we'd add a `organization` discriminator check as database-level Row Level Security (PostgreSQL RLS) for defense in depth.
