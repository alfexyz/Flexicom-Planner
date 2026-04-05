# Flexicom Planner

A full-stack S&OP (Sales & Operations Planning) platform for Romanian SMBs. Turns raw invoice exports and stock data into actionable inventory, margin, and demand insights — with a React dashboard and a Python/FastAPI backend.

---

## Features

- **Demand Forecasting** — Rolling weighted averages with seasonality detection across 24 months of invoice history
- **Inventory Alerts** — Days-of-cover per product, reorder-point alerts, stockout risk timeline, dead stock detection
- **Margin Analysis** — Per-product gross margin from purchase vs. selling invoices; supplier cost-trend alerts
- **Customer Intelligence** — Ordering pattern deviation detection, concentration risk, revenue contribution ranking
- **What-If Simulation** — Model impact of supplier price increases on margin and suggested selling-price adjustments
- **Smart Alerts Dashboard** — Prioritized action cards (critical / order now / watch / dead stock / declining)
- **File Upload** — Drop a fresh e-Factura export or stock spreadsheet; the platform re-parses and recalculates automatically

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML / Data | XGBoost, scikit-learn, Pandas, NumPy, rapidfuzz |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS, Recharts |
| Database | SQLite |
| Testing | pytest |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 20+

### 1. Clone the repo

```bash
git clone https://github.com/your-username/Flexicom-Planner.git
cd Flexicom-Planner
```

### 2. Start the backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server (starts on http://localhost:8000)
uvicorn backend.api.main:app --reload
```

The server pre-loads the SQLite database with synthetic demo data (24 months of invoices + stock). On first run it may take a few seconds to warm up the forecasting engines.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Project Structure

```
Flexicom-Planner/
├── backend/
│   ├── api/            # FastAPI routes (products, alerts, customers, overview, forecast, upload)
│   ├── engine/         # Business logic (demand, inventory, margin, forecast)
│   ├── ingestion/      # Parsers (invoice parser, stock parser, SKU normalizer)
│   └── data_generator/ # Synthetic dataset generator
├── frontend/
│   └── src/
│       ├── pages/      # Overview, ProductList, ProductDetail, Alerts
│       ├── components/ # Card, Badge, Spinner, TrendArrow
│       └── api/        # Typed API client
├── data/               # SQLite database + CSV demo files
└── requirements.txt
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/products` | GET | All products with stock status, days-of-cover, trend |
| `/products/{id}` | GET | Full product detail: demand history, margin, seasonality, ROP |
| `/alerts` | GET | All products needing attention today |
| `/alerts/orders` | GET | Consolidated reorder list grouped by supplier |
| `/customers` | GET | Customer ranking with ordering pattern status |
| `/overview` | GET | Dashboard summary: revenue trend, inventory health, top alerts |
| `/forecast` | GET | Demand forecast for all products |
| `/upload/invoices` | POST | Upload e-Factura CSV; triggers re-parse and recalculate |
| `/upload/stock` | POST | Upload stock spreadsheet; triggers re-parse |

---

## Data Sources

The platform is designed around two data asks from the business owner:

1. **e-Factura export** — last 24 months of issued and received invoices (from ANAF SPV or accounting software)
2. **Stock spreadsheet** — current inventory with quantities and supplier info

From these two sources, the engine derives demand rates, margins, reorder points, customer patterns, and supplier cost trends. External sources (BNR exchange rates, ANAF CUI lookup) are integrated silently with no additional asks.

The repository includes a full synthetic dataset (2,000 invoices, 10 suppliers, 12 customers, 30 products) so the demo runs out of the box.

---

## Running Tests

```bash
pytest backend/
```

---

## Design Notes

The SKU normalizer uses `rapidfuzz` fuzzy matching to link product names between the stock spreadsheet and invoice data — handling the common case where "Rulment 6205" in the spreadsheet maps to "RULMENT 6205-2RS SKF" in the invoices. This is where naive approaches break, so it gets dedicated attention in the ingestion layer.

The calculation engine is pure functions with no side effects, making it easy to unit test each feature in isolation.
