# TRADEOFFS.md — Three Things Deliberately Not Built

## 1. Real-time API pulls from source systems

**What was not built:**
Automated, scheduled data pulls from SAP's OData services, utility APIs (Green Button Connect, PG&E API, etc.), or the Concur Platform API.

**What we built instead:**
File upload (drag and drop) for all three sources.

**Why:**
- **Onboarding time:** Concur Platform API requires OAuth client credentials provisioned through SAP's partner program — 2-4 week process. Utility APIs require per-utility OAuth tokens and account linking. SAP OData requires Gateway configuration by a BASIS consultant. For an onboarding prototype, none of these can be ready in 4 days.
- **Client readiness:** Many enterprise clients have "we'll enable API access" on their IT roadmap but haven't done it. File export is the guaranteed path that works for 100% of clients regardless of IT sophistication.
- **Not actually better for accuracy:** API pulls run on a schedule (daily, weekly). File upload triggered by the facilities team at billing time is often *more timely* than a nightly poll.
- **The design supports it:** `IngestionRun.source_type` and the parser dispatch in `service.py` are designed so an API pull handler would slot in identically to the file upload path. No data model changes needed.

**What I'd build next sprint:** Concur API integration first (most ROI, cleanest auth model), then SAP OData for clients who have Gateway configured.

---

## 2. PDF bill parsing

**What was not built:**
Parsing of PDF utility bills or PDF SAP print output.

**What we built instead:**
CSV upload only for utility data.

**Why:**
- **Fragility:** PDF parsing (even with LLM assistance) has a meaningful error rate because every utility designs its bill layout differently. A utility can change their template and break your parser silently.
- **Not the bottleneck:** Virtually every utility portal that can generate a PDF bill can also generate a CSV export of the same data. The CSV path is more reliable, faster to parse, and produces structured data that doesn't need OCR.
- **Auditability:** A CSV upload produces a direct, traceable mapping from column → field. A PDF parse requires OCR → extraction → field mapping — three steps that each introduce error. An auditor asking "where did this 48,250 kWh number come from" gets a cleaner answer from a CSV row than from a PDF extraction.
- **Scope creep:** Building a robust PDF parser is a separate product. Companies like Arcadia and WegoWise do this full-time. Our value is in the normalization, review workflow, and audit trail — not OCR.

**What I'd build if required:** Use AWS Textract or Azure Document Intelligence for PDF extraction, then run the extracted key-value pairs through the same `parse_utility_csv` normalization logic. The parser is already field-mapping, not format-dependent.

---

## 3. Scope 3 supply chain categories (Cat. 1 Purchased Goods, Cat. 7 Employee Commuting)

**What was not built:**
Scope 3 Category 1 (purchased goods and services), Category 7 (employee commuting), Category 5 (waste), and most other Scope 3 categories beyond business travel (Cat. 6).

**What we built instead:**
Scope 3 is limited to Category 6 (business travel: flights, hotels, ground transport via Concur).

**Why:**
- **Data shape is fundamentally different:** Scope 3 Cat. 1 requires either spend-based estimation (multiply procurement spend by an EEIO economic factor) or supplier-specific LCA data. Neither fits the "CSV upload from an existing system" model. It requires either integration with AP/ERP data (different problem) or a separate emissions database (e.g., Ecoinvent, USEEIO).
- **Uncertainty is orders of magnitude higher:** Scope 3 Cat. 1 spend-based factors have uncertainty ranges of ±50-200%. Presenting this alongside Scope 1 fuel consumption (±5%) without clearly distinguishing estimation methodology would mislead analysts and auditors.
- **The assignment is about three specific sources:** The PM described SAP fuel/procurement, utility electricity, and corporate travel. Those are Scope 1, 2, and 3 Cat. 6. Building Cat. 1 would be scope creep beyond the brief.
- **Employee commuting (Cat. 7):** Requires survey data or HR data (employee home postcodes + commuting mode survey). None of the described source systems contain this.

**What I'd build next:** Spend-based Scope 3 Cat. 1 estimation using the US EPA USEEIO v2.0 industry-level emission factors, ingested from the client's procurement export (SAP ME2M by GL account code). This would map GL accounts to NAICS industry codes and apply USEEIO factors — rough but compliant with GHG Protocol guidance for Scope 3 Cat. 1.

---

## Additional Acknowledged Limitations (not counted in the three)

These are real limitations worth flagging to the PM:

- **No CO₂e recalculation after edit:** If an analyst corrects a quantity, `co2e_kg` is not automatically recalculated. The original value persists until the analyst manually updates it. Production fix: trigger recalculation on `quantity_normalized` change.
- **No duplicate upload detection blocking:** SHA-256 hash is stored but currently only warns in `error_detail`, doesn't prevent re-ingestion. Production fix: block upload if hash matches an existing run for the same org.
- **No scope 2 market-based accounting:** Only location-based Scope 2 is supported. Market-based (with RECs/PPAs reducing to zero) requires the client to supply their energy attribute certificates, which is a different input form.
- **Single-region Scope 2 factor:** Defaults to UK grid. Production: auto-select factor based on meter's `service_address` country.
