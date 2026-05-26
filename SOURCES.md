# SOURCES.md — Research Notes Per Data Source

## Source 1: SAP Fuel & Procurement — MB51 Flat File

### What I researched

SAP has four main export mechanisms for material/fuel data:
- **IDoc** (Intermediate Document): SAP's EDI format, XML-based, used for inter-system messaging. Requires ALE middleware configuration and partner agreements.
- **OData services** (via SAP Gateway): REST/JSON API, increasingly common in S/4HANA. Requires Gateway component and specific service activation.
- **BAPIs**: Remote Function Call procedures. Require RFC connectivity and authorization, called programmatically.
- **ALV flat file export**: Any SAP standard list (ALV = ABAP List Viewer) can be exported to spreadsheet via the menu. Zero configuration needed.

I chose **ALV flat file (MB51 transaction)** because:
- Requires no custom development or configuration
- Works on all SAP versions (R/3, ECC, S/4HANA)
- Universally understood by SAP end-users
- No middleware, no API keys, no RFC connectivity

### What a real MB51 export looks like

MB51 shows material documents — the individual records of goods movements in SAP. For fuel tracking:

**Report configuration:** Run MB51 with:
- Material: fuel material codes (e.g., `DIESEL-001`, `HZOEL-001`, `ERDGAS-001`)
- Movement type: 201, 261 (consumption movements)
- Plant: all relevant plants
- Date range: reporting period

**Critical facts learned:**
1. **German-locale SAP** (most common in European manufacturing) uses **semicolon as delimiter** because comma is the decimal separator. 1.250,00 means 1250.00.
2. Column headers vary by SAP configuration — German headers (`Buchungsdatum`, `Menge`, `Werk`) are common; English headers available on English-locale systems.
3. Negative quantities = goods issue (consumption). Positive = goods receipt. Both appear in MB51.
4. Movement type 261 = goods issue to production/maintenance order. 201 = goods issue to cost center. Both represent consumption.
5. SAP exports often include 1-3 non-data header rows at the top (report title, filter summary). Must skip these to find the actual column header row.
6. Material codes are client-defined — `DIESEL-001` is illustrative. In reality, it might be `000000000010023456`. The material *description* (Materialbezeichnung) is what humans can read.

### Why my sample data looks the way it does

- **Two plants** (1000 and 2000): Typical mid-sized manufacturing company with a main site and a secondary facility
- **Three fuel types**: Diesel (forklifts/vehicles/generators), Heizöl EL (heating oil for space heating), Erdgas (natural gas for process heat)
- **500-1200L per transaction**: Realistic for forklift/generator fill-ups — a 500L diesel IBC refill, or a 1200L heating oil delivery
- **One goods receipt record (movement 101)**: Included deliberately to show the parser correctly flags it as suspicious
- **Semicolon delimiter with European decimals**: Matches what a German-locale SAP export actually produces
- **6 weeks of data**: Covers a full Q1 scenario for seasonal heating oil demand

### What would break in a real deployment

1. **Material code mapping**: We infer fuel type from material description text (`"Dieselkraftstoff"`, `"Heizöl"`). A real client might have material `000000000010023456` with description `"KFZ-DIESEL-50"` — we'd need a material master lookup table from SAP.
2. **Custom display variants**: The SAP user who exports may have a custom display variant with renamed/reordered columns. Our dual-language column map handles common variants but not all.
3. **Batch splits and subcontracting**: Materials processed in batches (movement 311/312) would require additional movement type handling.
4. **Non-fuel materials**: MB51 for the same plant will include non-fuel goods (maintenance parts, etc.). The unit-based filtering (skip `ST` = pieces, `EA` = each) handles most cases, but a material code allowlist would be more robust.
5. **Reversals**: SAP movement 102 reverses a 101; movement 262 reverses a 261. Reversals produce negative quantities on goods receipt movements — our suspicious-flagging logic doesn't fully handle all reversal patterns.

---

## Source 2: Utility Electricity — Portal Billing CSV

### What I researched

Utility data access modes for commercial/industrial customers:

1. **Manual portal CSV export**: Every major utility (PG&E, ConEd, National Grid, EDF, etc.) provides a web portal with CSV export of billing history. Universally available.
2. **Green Button**: US standard for utility data download (XML) and API access. Adopted by most US utilities but not universal internationally.
3. **Utility-specific APIs**: Some utilities offer APIs (PG&E's Share My Data, ComEd's Green Button Connect). Requires per-utility OAuth credentials.
4. **PDF bills**: Ubiquitous but fragile to parse.

I chose **manual portal CSV** because it's the guaranteed 100% case.

**Critical facts learned:**
1. **No standard column format**: Each utility has its own export format. PG&E calls it "Energy" while ConEd calls it "KWH". National Grid might call it "Consumption (kWh)". I handle 15+ column name variants.
2. **Billing periods do not align with calendar months**: A commercial customer might have a billing cycle from the 12th to the 11th of the following month. This is normal and by design (utilities stagger billing runs to avoid simultaneous meter reading). For carbon accounting, we store the actual billing dates and do not force calendar month alignment.
3. **Demand charges ≠ consumption**: The bill shows peak demand (kW) — this is used for billing the capacity costs. It is NOT used for emissions calculation. Only the kWh consumption figure is used. A parser that applies an emission factor to kW instead of kWh would be wrong by a large factor.
4. **kWh vs MWh**: Large industrial sites may be billed in MWh. Our parser handles both and normalizes to kWh.
5. **Multiple meters per file**: A facilities team might download one CSV covering all meters at a campus. The parser uses Meter_ID and Account_Number to assign facility codes.

### Why my sample data looks the way it does

- **Two meters at two plants**: MTR-7712834 at Plant 1000 (large, ~50,000 kWh/month) and MTR-9934521 at Plant 2000 (medium, ~33,000 kWh/month)
- **Non-calendar billing periods**: Jan 12-Feb 11, Feb 12-Mar 13, etc. — deliberately offset to demonstrate the billing period misalignment issue
- **Varying monthly consumption**: Summer months (Jun-Jul) are higher due to cooling load — realistic for a manufacturing facility
- **Two tariff codes** (GS-3 large service, GS-2 medium service): Typical commercial/industrial rate schedule classification

### What would break in a real deployment

1. **Locale-specific column names**: International utilities (UK, India, Germany) use completely different column headers. The German equivalent of "kWh" is still "kWh" but billing period might be "Abrechnungszeitraum" rather than "Billing Start/End".
2. **Net metering**: Sites with solar panels may have negative net consumption in some periods. Our parser rejects zero/negative kWh — needs special handling for net metering.
3. **Multiple rate tiers**: Some industrial tariffs split consumption into peak/off-peak kWh with different prices. For emissions, we only care about total kWh. Tiered billing is handled transparently.
4. **Gas utility bills**: Natural gas consumption (CCF, therms, m³) would need a separate parser and Scope 1 classification. We've classified this as a deliberate omission.
5. **Cumulative index readings**: Some smart meter exports show cumulative meter readings, not consumption — you must subtract the previous reading. Our parser expects consumption values, not index values.

---

## Source 3: Corporate Travel (Concur) — Standard CSV Export

### What I researched

Corporate travel data access modes:

1. **Concur Finance Processor export**: Standard CSV download from Concur's administrative reports. Available to any Concur Finance admin. No API credentials needed.
2. **Concur Platform API (v4)**: Full REST API with expense, travel, and report endpoints. Requires OAuth client credentials from SAP's partner program — 2-4 week onboarding.
3. **Navan/TripActions export**: Very similar CSV structure to Concur. Our parser handles both.
4. **Expense Management integrations**: Some companies route Concur data through their ERP (SAP) which then appears in the MB51 export as cost center allocations. Not reliable for emissions — cost allocation doesn't preserve travel details.

I chose **Concur Finance Processor export CSV** for zero-friction prototyping.

**Critical facts learned:**
1. **Distances are NOT provided**: Concur stores flight expenses as dollar amounts with vendor name and description. The origin/destination are typically embedded in the description field (e.g., "BOS-JFK roundtrip client meeting") or a separate trip field if configured. Distance must be computed externally.
2. **Airport codes are buried in free text**: Concur does not have a structured "origin airport" field in the standard export. The description field is free text. We use regex to extract `[A-Z]{3}-[A-Z]{3}` patterns.
3. **Cabin class is often in description text**: Premium cabin purchases may say "business class" in the description. Economy is the default assumption.
4. **Currency is not normalized**: International employees book in local currency. Amounts are irrelevant for emissions (we only need distance and cabin class), so this is fine.
5. **Meals & Entertainment lines are included**: We silently skip these — no emissions relevance.
6. **Mileage reimbursements**: Some companies have Concur configured for personal vehicle mileage (entered as miles × IRS rate). We can reverse-engineer the distance from the reimbursement amount.
7. **DEFRA Radiative Forcing**: DEFRA 2024 flight emission factors already include a 1.7× RF uplift. This is the recommended approach for Scope 3 Cat. 6. Not all standards use RF — ICAO method does not. We use RF because DEFRA is the industry standard for Scope 3 reporting.

### Why my sample data looks the way it does

- **Mix of domestic and international flights**: BOS-JFK (domestic short), ORD-FRA (transatlantic business), LHR-SIN (long-haul economy)
- **Hotel stays matching flight destinations**: Realistic — business travel always combines flights + accommodation
- **Ground transport**: Uber from airport, personal vehicle mileage to airport — realistic Concur entries
- **One record with no airport codes** (Alex Wong's flight): Deliberately included to demonstrate the suspicious-flagging system. Description is "Flight to client site - no route recorded" — common when employees don't fill in expense details
- **Business class long-haul** (James Chen's ORD-FRA): Business class has a much higher EF (0.43 vs 0.12 kgCO₂e/pkm). This is deliberately included to show that cabin class matters significantly.
- **Tokyo trip** (James Chen's ORD-NRT): Longest route in the dataset — 10,800+ km each way, business class. Will produce the highest single-record CO₂e to illustrate the dashboard correctly.

### Emission Factor Sourcing

All emission factors are from **DEFRA 2024** (UK Department for Energy Security and Net Zero):
- Fuel combustion: tank-to-wheel (combustion only), not well-to-wheel
- Electricity: UK National Grid location-based (0.207 kgCO₂e/kWh)
- Flights: include 1.7× Radiative Forcing uplift (DEFRA standard for Scope 3 Cat. 6)
- Hotels: global average (21.4 kgCO₂e/room-night) — wide confidence interval
- Ground transport: UK averages for rental car, taxi, personal vehicle

**Why DEFRA over EPA or IPCC?**
DEFRA is updated annually and is the most comprehensive freely available emission factor database for multi-source, multi-scope corporate carbon accounting. It's the de facto standard in the UK but is used globally because it covers categories that the US EPA does not (e.g., hotel stays, cab rides, specific fuel types). For US-specific electricity, EPA eGRID2023 would be more accurate — a production implementation would select by geography.

### What would break in a real deployment

1. **Non-English descriptions**: If a German employee books in their local Concur instance, the description might be in German ("Flug Frankfurt-New York"). IATA code extraction still works if codes are present.
2. **Multi-leg itineraries**: A trip with a connection (BOS → ORD → LHR) might appear as one expense line. We'd extract BOS-LHR (direct GCD), underestimating actual distance. Production: split on multiple airport code patterns.
3. **Concur report structure changes**: Our column mapping assumes the standard Finance Processor report. Custom Concur configurations may rename columns or add/remove fields.
4. **Missing IATA codes for small airports**: Our airport coordinate table has ~80 major airports. A flight to a regional airport (e.g., `BHX` Birmingham, `PIE` Clearwater) might not be found — record is flagged.
5. **Hotel emission factors**: The global average of 21.4 kgCO₂e/room-night has enormous uncertainty (budget motel ≈ 10, luxury hotel ≈ 50). Property-level data requires the HCMI (Hotel Carbon Measurement Initiative) database or direct API calls to Thrust Carbon / myclimate.
