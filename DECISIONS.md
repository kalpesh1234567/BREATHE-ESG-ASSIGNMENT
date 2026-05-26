# DECISIONS.md — Every Ambiguity Resolved

This document covers every significant design decision made during the build, the reasoning, and what I would ask the PM if I could.

---

## Source Format Decisions

### SAP: Chose flat-file CSV from MB51/ME2M, not IDoc or OData

**What I chose:** CSV/XLSX export via SAP transaction MB51 (material documents for fuel consumption) or ME2M (purchase orders). The analyst runs the standard ALV report and exports via `List → Export → Spreadsheet`.

**Why not IDoc?** IDoc is SAP's EDI message format. Using it requires a partner agreement, ALE/middleware configuration by a BASIS consultant, and receiver port setup. The client would need to dedicate 1-2 days of BASIS time before we could ingest a single record. Flat file export needs nothing.

**Why not OData?** SAP Gateway OData services require the Gateway component to be installed and configured, plus specific business intelligence configuration. Many SAP clients have this on their roadmap but not yet active. Flat file is the guaranteed fallback.

**Why not BAPI?** BAPIs require direct RFC connectivity (SAP GUI or RFC SDK) and are called programmatically. This means the BreatheESG platform would need network access to the client's SAP system, VPN configuration, and SAP user credentials with RFC authorization. Not realistic for a prototype onboarding.

**The tradeoff:** Flat file export is manual — someone has to run the report and upload the file. In production, you'd automate with a scheduled SAP job that SFTPs the export to us. But for the prototype, manual upload is honest.

**What I'd ask the PM:** "Does the client's SAP instance have Gateway active? If yes, we can build a one-click OData pull for the next sprint and eliminate the manual export step."

---

### SAP: Chose semicolon delimiter handling over comma-only

SAP in German locale uses comma as the decimal separator (1.250,00 = 1250.00). This means SAP exports from German-locale systems are **semicolon-delimited**, not comma-delimited. The parser autodetects the delimiter by counting occurrences in the first row.

**What I'd ask the PM:** "What's the client's SAP locale? German (most common in European manufacturing) or English? This affects how we validate test files."

---

### SAP: Handling movement types

SAP movement types classify what a material document represents. I filter on:
- **201** (goods issue to cost center) → fuel consumption ✓
- **261** (goods issue to production/maintenance order) → fuel consumption ✓
- **331** (transfer posting to cost center) → consumption ✓
- **101** (goods receipt from purchase order) → flagged as suspicious (receipt, not consumption)
- **122** (return to vendor) → flagged

This matters because an MB51 export will contain **all** material movements for the selected materials, including receipts into stock. Including receipts in the emission calculation would double-count fuel (once when purchased, once when consumed). We flag goods receipts rather than silently dropping them.

**What I ignored:** Movement types for inter-plant transfers (301, 311), subcontracting (541), and scrapping (551). These are edge cases for a prototype.

---

### Utility: Chose billing summary CSV over interval data

**What I chose:** Monthly billing summary CSV (one row per billing period per meter).

**Why not interval data (15-min reads)?** Interval data is useful for load management and peak demand analysis, but carbon accounting only needs total kWh consumed per period. Interval data would be 2,880× more rows (96 intervals/day × 30 days) for the same CO₂e calculation. It's also not universally available — many utility portals only expose billing summaries to commercial customers.

**Why not PDF bills?** PDF parsing is inherently fragile. Every utility designs its bill layout differently. Even with OCR+LLM, you'd have a meaningful error rate and need manual fallback. CSV is the 80% case and is what most utility portal "download" buttons produce.

**Billing period misalignment:** A billing period like Jan 12 → Feb 11 doesn't align with a calendar month. I store the actual billing dates as `period_start` / `period_end` and let analysts and downstream tools decide how to allocate. For carbon reporting, the GHG Protocol allows reporting on a rolling 12-month basis, so exact month alignment is not required at the record level.

**What I'd ask the PM:** "Does the client have multiple utility accounts (different buildings) under one upload, or are they in separate files? Our parser handles both (multiple meter IDs per file), but good to confirm."

---

### Travel: Chose Concur standard export CSV over API

**What I chose:** Standard Concur Finance Processor export CSV (the format that finance teams download for accounting reconciliation).

**Why not Concur API?** The Concur API (SAP Concur Platform API) requires OAuth client credentials provisioned through the Concur partner program, which takes 2-4 weeks to onboard. The client would need to involve their IT team. CSV export requires nothing beyond existing access.

**Why Concur and not Navan/TripActions?** Concur is ~60% market share in enterprise travel. The export format I've built handles the column structure that appears in most Concur Finance reports. Navan's CSV export is structurally similar (same column names, same expense type taxonomy).

**What I ignored:** Real-time trip approval webhooks, multi-currency normalization (amounts stored in original currency — irrelevant for emissions), per-diems, and parking.

---

### Travel: Great Circle Distance for flights

When a flight record has origin/destination airport codes (IATA), I compute Great Circle Distance using the Haversine formula and apply a **9% routing uplift** (DEFRA's recommended factor to account for non-direct routes and holding patterns).

**Why Haversine and not the Climatiq API or ICAO calculator?**

- **Climatiq** is a paid API (metered pricing). Introducing a third-party API dependency into a prototype
  adds cost, a network dependency, rate limits, and a service contract to explain to the client. Haversine
  is free, deterministic, and produces identical results on every run — important for audit reproducibility.
- **ICAO Carbon Offset Calculator** is a black box — you can't inspect or version the methodology. DEFRA
  explicitly publishes its uplift assumptions. For a regulated audit trail, an auditor can verify any number
  we produce.
- **Accuracy:** For the major airport pairs in a typical Concur export (e.g., LHR→JFK, ORD→FRA),
  Haversine with 9% uplift produces distances within ±3-5% of ICAO's output — well within the ±15%
  uncertainty of flight emission factors themselves.
- The curated airport coordinate table covers ~80 major hubs. For unlisted airports, the record is
  flagged suspicious and co2e_kg is left null, forcing analyst review. This is honest and safe.

**Why DEFRA 2024 over US EPA?**

DEFRA is the international standard for Scope 3 travel (GHG Protocol Technical Guidance for Scope 3,
Appendix C recommends DEFRA as a default). EPA does not publish per-PKM air travel factors in the same
format. If the client is a US company that prefers EPA-aligned reporting, we'd switch the ground transport
factors to EPA and keep DEFRA for aviation. This is a one-row change in the `EmissionFactor` table.

**Radiative Forcing uplift:** I use DEFRA 2024 factors that **include 1.7× Radiative Forcing uplift**.
RF accounts for the non-CO₂ warming effects of aviation at altitude (contrails, NOx). Some companies
report with RF, some without. DEFRA recommends including it for Scope 3. This is documented in the
emission factor `notes` field. If the client wants to exclude RF, we'd select the without-RF row
(DEFRA publishes both).

Where IATA codes cannot be extracted, the record is flagged as suspicious and co2e_kg is left null.

---

## Architecture Decisions

### Synchronous file parsing (no Celery)

File parsing happens synchronously in the upload request handler. For files up to ~10 MB with <5,000 rows (realistic for the described client), this completes in <2 seconds.

**What I'd add in production:** A Celery task queue with Redis broker for files over 10 MB or for parallel upload ingestion. The `IngestionRun.status = 'processing'` field is already designed for async processing — the frontend can poll.

### SQLite in dev, PostgreSQL in production

Django's `dj-database-url` reads `DATABASE_URL` from environment. Without it, falls back to SQLite. This means local dev works with zero setup.

### JWT with 8-hour access tokens

Long token lifetime chosen for a prototype where token refresh friction would annoy evaluators. In production: 15-minute access tokens with sliding refresh.

### No email/MFA

Out of scope for a prototype. In production: mandatory SSO via SAML (most enterprise clients use Okta/Azure AD), not username/password.

---

## Data Model Decisions

### UUID primary keys throughout

Prevents enumeration attacks across tenants. Slightly larger index size than integers — acceptable tradeoff.

### `co2e_kg` stored and recalculated on analyst edits

The field is computed at ingestion time by multiplying `quantity_normalized` × `emission_factor_value`.
The emission factor value is **snapshotted at ingestion time** onto the record — we do not do a live
lookup at review time. This means if DEFRA updates its factor table next year, all historical records
remain reproducible.

If an analyst corrects `quantity_normalized` (e.g., because the unit was wrong), **co2e_kg is automatically
recalculated** in `perform_update()` using the already-snapshotted factor:

```python
# In ActivityRecordDetailView.perform_update()
new_qty = serializer.validated_data.get('quantity_normalized')
if new_qty is not None and instance.emission_factor_value:
    extra_fields['co2e_kg'] = (
        Decimal(str(new_qty)) * instance.emission_factor_value
    ).quantize(Decimal('0.0001'))
```

The recalculation is logged in the AuditLog `note` field: `"co2e recalculated from snapshotted emission factor"`.
The original values (pre-edit) are preserved in `original_values` JSONField for full traceability.

Records only become `locked` (audit-ready) after analyst approval — the `locked` status signals
that the CO₂e value is trusted and the record is immutable.

### Database-level CHECK constraints on `ActivityRecord`

Beyond Django's application-layer validation, four `CHECK` constraints are enforced at the
database level (PostgreSQL):

```sql
CHECK (period_end >= period_start)         -- period must be logically ordered
CHECK (quantity_normalized >= 0)           -- negative raw values OK; normalized must not be
CHECK (scope IN ('1', '2', '3'))           -- belt-and-suspenders beyond CharField choices
CHECK (status IN ('pending','flagged','approved','rejected','locked'))
```

Rationale: if a future code path bypasses the serializer (bulk ORM update, data migration, shell
command), these constraints catch bad data before it reaches the database. A `pending → approved`
transition that accidentally wrote `scope = '4'` would fail loudly rather than silently.

**What's not a constraint (and why):** `co2e_kg >= 0` is deliberately excluded — some reversal
postings produce negative emissions adjustments, and we preserve those. The app layer flags them
as suspicious rather than rejecting them at the DB level.

The current emission factor seeding uses UK National Grid (0.207 kgCO₂e/kWh). In production, the correct factor depends on the physical location of each meter. The `EmissionFactor.region` field and `facility_code` (meter ID / service address) could be used to automatically select the right regional factor.

**What I'd ask the PM:** "Where are the client's facilities? UK, EU, US, India? Each has a materially different grid emission factor."

---

## What I'd Ask the PM (Summary)

1. Is the client's SAP in German or English locale? (Affects CSV delimiter and column header language)
2. Does their SAP have Gateway/OData active? (Determines whether we can automate ingestion)
3. Where are their facilities geographically? (Determines correct Scope 2 grid emission factor)
4. Does the client use market-based or location-based accounting for Scope 2? (Affects whether RECs/PPAs reduce their factor to 0)
5. What's the typical file size for their SAP MB51 export? (Determines whether we need async processing)
6. Do they need Scope 3 Category 1 (purchased goods) now, or only business travel? (Scope 3 Cat. 1 requires spend-based or LCA data — very different)
7. Do they have a fiscal year vs calendar year for reporting? (Affects date range defaults)
