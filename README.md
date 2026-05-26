# BreatheESG — Emissions Data Ingestion & Review Platform

A Django REST + React prototype built for the BreatheESG internship assignment.  
Ingests Scope 1 (SAP fuel), Scope 2 (utility electricity), and Scope 3 (corporate travel) data,  
normalizes it to kgCO₂e, and surfaces an analyst review + approval workflow.

---

## Quick Start (Local Dev)

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend

```bash
cd backend

# Create and activate virtualenv
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements-local.txt

# Run migrations
python manage.py makemigrations core ingestion review
python manage.py migrate

# Seed demo data (org, users, emission factors, 48 sample records)
python manage.py seed_data

# Start dev server
python manage.py runserver
```

Backend runs at **http://localhost:8000**

**Demo credentials:**
| Username | Password | Role |
|---|---|---|
| `admin` | `breatheesg2024` | Admin (can lock records) |
| `analyst` | `breatheesg2024` | Analyst (review & approve) |

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure API URL (copy and edit)
cp .env.example .env

# Start dev server
npm run dev
```

Frontend runs at **http://localhost:5173**

---

## Architecture

```
┌────────────────────────────────────────────┐
│  React 18 + Vite Frontend                  │
│  - Login (JWT)                             │
│  - Dashboard (scope breakdown, charts)     │
│  - Ingestion (drag-drop upload, run log)   │
│  - Review (filterable table, bulk approve) │
│  - Audit log                               │
└───────────────┬────────────────────────────┘
                │ REST API / JWT
┌───────────────▼────────────────────────────┐
│  Django 5 + DRF Backend                    │
│  /api/auth/      JWT login & refresh       │
│  /api/ingestion/ upload & run history      │
│  /api/activities/ records + review actions │
│  /api/audit/     append-only audit trail   │
│  /api/stats/     dashboard aggregations    │
└───────────────┬────────────────────────────┘
                │
┌───────────────▼────────────────────────────┐
│  SQLite (local) / PostgreSQL (production)  │
│  Organizations, Users, IngestionRuns,      │
│  ActivityRecords, EmissionFactors,         │
│  AuditLogs                                 │
└────────────────────────────────────────────┘
```

---

## Data Sources Handled

### Scope 1 — SAP MB51 Fuel Export (CSV)
- Semicolon-delimited (German locale SAP)
- German **and** English column headers (dual-map)
- European number format: `1.250,00` → `1250.00`
- Dates: `DD.MM.YYYY`
- Movement type filtering: 201/261/331 = consumption; 101/122 = receipt (flagged)
- Material → fuel category inference (diesel, Heizoil, Erdgas, Benzin, LPG)
- Units: L, GAL, m3, KG, TO — all normalized

### Scope 2 — Utility Electricity Portal CSV
- Handles many column name variants (PG&E, National Grid, Con Edison patterns)
- kWh and MWh inputs (MWh → kWh automatically)
- Billing periods that don't align with calendar months — stored as-is
- Demand (kW) stored but not used for emissions (billing artifact)
- Suspicious if billing period > 35 days or < 25 days

### Scope 3 — Concur Corporate Travel Export (CSV)
- **Flights**: IATA airport code extraction via regex → Great Circle distance (Haversine)  
  DEFRA 9% routing uplift applied. Classified into domestic/shorthaul/longhaul.
- **Hotels**: nights × room-night emission factor
- **Ground**: rental car, personal vehicle (mileage→km), taxi, train, bus
- Cabin class parsing (economy/business/premium economy/first)
- Records with no route information are auto-flagged for analyst review

---

## Emission Factors

All factors from **DEFRA 2024** (UK) and **EPA eGRID2023** (US), snapshotted at ingestion time.

| Category | Factor | Unit | Source |
|---|---|---|---|
| Diesel | 2.68 | kgCO₂e/L | DEFRA 2024 |
| Heating Oil | 2.54 | kgCO₂e/L | DEFRA 2024 |
| Natural Gas | 2.04 | kgCO₂e/m³ | DEFRA 2024 |
| UK Electricity | 0.207 | kgCO₂e/kWh | DEFRA/DESNZ 2024 |
| Economy flight (short) | 0.126 | kgCO₂e/pkm | DEFRA 2024 + 1.7× RF |
| Business flight (long) | 0.430 | kgCO₂e/pkm | DEFRA 2024 + 1.7× RF |
| Hotel stay | 21.4 | kgCO₂e/room-night | DEFRA 2024 |

---

## Review Workflow

```
ingested → pending → flagged (auto or analyst)
                   → approved → locked (admin only, audit-ready)
                   → rejected
```

- **Auto-flag triggers**: negative receipt postings, missing emission factor, no flight route
- **Bulk approve**: select multiple records → approve all at once  
- **Locked** records are immutable — edit protection enforced at API level
- Every state transition logged to `AuditLog` with before/after JSON snapshots

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login/` | JWT login |
| POST | `/api/auth/refresh/` | Refresh token |
| GET | `/api/me/` | Current user info |
| GET | `/api/stats/` | Dashboard aggregations |
| POST | `/api/ingestion/upload/` | Upload CSV file |
| GET | `/api/ingestion/runs/` | List ingestion runs |
| GET | `/api/activities/` | List records (filterable) |
| GET | `/api/activities/{id}/` | Record detail + audit trail |
| PATCH | `/api/activities/{id}/` | Edit record (analyst) |
| POST | `/api/activities/{id}/approve/` | Approve |
| POST | `/api/activities/{id}/reject/` | Reject with reason |
| POST | `/api/activities/{id}/lock/` | Lock for audit (admin) |
| POST | `/api/activities/bulk-approve/` | Bulk approve |
| GET | `/api/audit/` | Full audit log |

---

## Deployment

### Backend → Render

1. Push `backend/` to GitHub
2. Create Render Web Service — `render.yaml` is pre-configured
3. Environment variables are auto-set (SECRET_KEY generated, DATABASE_URL from Postgres add-on)
4. Build command runs: `pip install`, `collectstatic`, `migrate`, `seed_data`

### Frontend → Vercel

1. Push `frontend/` to GitHub
2. Import in Vercel — Vite detected automatically
3. Set environment variable: `VITE_API_URL=https://your-render-service.onrender.com`
4. `vercel.json` handles SPA routing (`/* → /index.html`)

---

## Design Decisions & Documentation

See the `/docs` directory:
- **`MODEL.md`** — Data model with full design rationale
- **`DECISIONS.md`** — Every design ambiguity resolved  
- **`TRADEOFFS.md`** — Deliberate omissions with reasoning
- **`SOURCES.md`** — Per-source research notes and realistic data rationale

---

## Deliberate Scope Limitations (see TRADEOFFS.md)

1. **No real-time API pulls** — CSV upload is the realistic 80% case; SAP OData/IDoc requires middleware most clients don't have
2. **No PDF parsing** — Fragile and error-prone; utility CSVs are universally available
3. **No Scope 3 supply chain** — Category 1 (purchased goods) requires supplier-specific data not available in standard export formats
