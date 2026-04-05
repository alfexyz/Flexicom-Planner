"""
Synthetic data generator for Flexicom Planner.

Produces realistic fake data mimicking a Romanian agricultural spare parts dealer:
  - data/invoices.csv   — all issued (sales) and received (purchase) invoices, 48 months
  - data/stock.csv      — current stock snapshot

Run:
    python backend/data_generator/generate.py

Realism features:
  - Customers have specialised product preferences (not random baskets)
  - 1-2 dominant customers drive >40% of revenue (concentration risk)
  - Supplier cost increases are discrete step events, not smooth curves
  - Purchase invoice product names differ from sales names (tests SKU normalizer)
  - Credit notes reference their original invoice number
  - Selling prices lag behind cost increases (margin compression visible)
  - ~5% annual YoY demand growth (growing SMB)
  - 13 price events spanning 4 years (including post-pandemic supply chain shocks)
"""

import csv
import os
import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

import numpy as np

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

OUTPUT_DIR = "data"
END_DATE   = date(2026, 4, 30)
START_DATE = date(2022, 4, 1)

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
# (code, name, base_sell_price, base_buy_price, base_weekly_demand, seasonality, is_declining)
PRODUCTS = [
    ("P001", "Rulment 6205-2RS SKF",              28.50,  14.20, 18, "general",  False),
    ("P002", "Curea trapezoidala B68",             22.00,  10.80, 14, "general",  False),
    ("P003", "Filtru ulei hidraulic JCB",          85.00,  42.00,  8, "planting", False),
    ("P004", "Bujie tractor U650",                 12.50,   5.90, 22, "general",  False),
    ("P005", "Disc frictiune ambreiaj U650",      210.00, 105.00,  4, "planting", False),
    ("P006", "Pompa hidraulica seria 1",           520.00, 260.00,  2, "planting", False),
    ("P007", "Furtun hidraulic 1/2 1m",            38.00,  17.50, 12, "general",  False),
    ("P008", "Garnitura chiulasa U650",             95.00,  47.00,  3, "planting", False),
    ("P009", "Filtru aer motor John Deere",         62.00,  29.00,  9, "harvest",  False),
    ("P010", "Bolt piston 80mm",                   18.00,   8.50, 10, "general",  False),
    ("P011", "Semering ax roata 50x72x10",          9.50,   4.20, 20, "general",  False),
    ("P012", "Lant transmisie 428H-128L",           55.00,  25.00,  6, "general",  False),
    ("P013", "Termostat motor 82C",                32.00,  14.50,  7, "general",  False),
    ("P014", "Alternator 14V 55A reconditionat",  380.00, 185.00,  2, "general",  False),
    ("P015", "Electromotor 12V 2.2kW recond.",    290.00, 140.00,  2, "general",  False),
    ("P016", "Injector motor diesel Perkins",     145.00,  68.00,  4, "harvest",  False),
    ("P017", "Pompa injectie Lucas DPC",           780.00, 385.00,  1, "harvest",  False),
    ("P018", "Arc supapa motor D-110",               6.50,   2.80, 25, "general",  False),
    ("P019", "Bieleta directie tractor",            72.00,  34.00,  5, "planting", False),
    ("P020", "Rulment roata fata 6307",             42.00,  19.50,  8, "general",  False),
    ("P021", "Placuta frana set 4buc",              88.00,  40.00,  6, "general",  False),
    ("P022", "Filtru combustibil universal",        24.00,  10.50, 16, "general",  False),
    ("P023", "Radiator apa tractor 4 cilindri",    320.00, 155.00,  1, "general",  False),
    # Declining — demand fades over the 24 months
    ("P024", "Garnitura capac distributie",        15.00,   6.50,  8, "general",  True),
    ("P025", "Cablu ambreiaj U651",                28.00,  12.00,  6, "general",  True),
    ("P026", "Buton contact pornire",               9.00,   3.80,  5, "general",  True),
]

PRODUCT_MAP = {p[0]: p for p in PRODUCTS}
DECLINING   = {p[0] for p in PRODUCTS if p[6]}

# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
# (cui, name, lead_time_days)
SUPPLIERS = [
    ("RO40000001", "SC Rulmenti SA Barlad",          7),
    ("RO40000002", "SC Hidraulica Industriala SRL",  10),
    ("RO40000003", "SC Auto Parts Distribution SA",   5),
    ("RO40000004", "SC Agro Import SRL",             14),
    ("RO40000005", "SC Pompe si Filtre SRL",          8),
]
SUPPLIER_MAP = {s[0]: s for s in SUPPLIERS}

PRODUCT_SUPPLIER = {
    "P001": "RO40000001", "P011": "RO40000001", "P020": "RO40000001",
    "P007": "RO40000002", "P019": "RO40000002", "P023": "RO40000002",
    "P002": "RO40000003", "P004": "RO40000003", "P012": "RO40000003",
    "P013": "RO40000003", "P014": "RO40000003", "P015": "RO40000003",
    "P021": "RO40000003", "P025": "RO40000003", "P026": "RO40000003",
    "P005": "RO40000004", "P006": "RO40000004", "P008": "RO40000004",
    "P010": "RO40000004", "P016": "RO40000004", "P017": "RO40000004",
    "P018": "RO40000004", "P024": "RO40000004",
    "P003": "RO40000005", "P009": "RO40000005", "P022": "RO40000005",
}

# ---------------------------------------------------------------------------
# Supplier product name variations  (fix #3)
# Same physical product — different names on the supplier's invoice.
# This is what makes SKU normalisation hard and interesting.
# ---------------------------------------------------------------------------
SUPPLIER_PRODUCT_NAMES: dict[str, dict[str, str]] = {
    "RO40000001": {                          # Rulmenti SA — uses DIN codes
        "P001": "RULMENT 6205-2RS/C3 DIN625",
        "P011": "SEMERING NBR 50x72x10 DIN3760",
        "P020": "RULMENT RADIAL 6307-2Z SKF",
    },
    "RO40000002": {                          # Hidraulica — uses technical specs
        "P007": "FURTUN HID. SAE100R2 DN12 1.0M",
        "P019": "BIELETA DIRECTIE CAT.2 500MM",
        "P023": "RADIATOR RACIRE 4-CIL. TRACTOR T",
    },
    "RO40000003": {                          # Auto Parts — short codes, no brand
        "P002": "CUREA B-68 LA TRAPEZ",
        "P004": "BUJIE M14x1.25 ECH. U650",
        "P012": "LANT SIMPLU 428H 128 ZALE",
        "P013": "TERMOSTAT 82 GRADE UNIVERSAL",
        "P014": "ALT. RECONDIT. 14V/55A",
        "P015": "ELECTROM. RECONDIT. 12V 2.2KW",
        "P021": "KIT PLACUTE FRANA FATA 4BUC",
        "P025": "CABLU AMBREIAJ L=1200 TRACTORAS",
        "P026": "CONTACT CHEIE PORNIRE 2 POZITII",
    },
    "RO40000004": {                          # Agro Import — Romanian + partial codes
        "P005": "DISC AMBREIAJ COMPLET U-650 MAN",
        "P006": "POMPA HIDRO. ANGRENAJ GP1 80CC",
        "P008": "GARNITURA CHIULASA D-110 6 CIL",
        "P010": "BOLT PISTON D=80MM OTEL 42CrMo",
        "P016": "INJECTOR ASS. PERKINS 3.152",
        "P017": "POMPA INJECTIE LUCAS DPC 4CIL",
        "P018": "ARC SUPAPA MOTOR D110 SET 2BUC",
        "P024": "GARNITURA CAPAC DISTRIBUTIE SET",
    },
    "RO40000005": {                          # Pompe si Filtre — brand + part numbers
        "P003": "FILTRU HIDRAULIC BT8459 / P550228",
        "P009": "FILTRU AER PRIMAR JD AR50041",
        "P022": "FILTRU MOTORINA WF 8046 UNIV.",
    },
}

def supplier_product_name(supplier_cui: str, product_code: str) -> str:
    """Return the supplier's own description for a product, falling back to the canonical name."""
    return SUPPLIER_PRODUCT_NAMES.get(supplier_cui, {}).get(
        product_code, PRODUCT_MAP[product_code][1]
    )

# ---------------------------------------------------------------------------
# Customers and specialisation  (fix #1 + fix #4)
# ---------------------------------------------------------------------------
# Product groups that customers tend to specialise in
PRODUCT_GROUPS = {
    "u650_parts":    ["P004", "P005", "P008", "P024", "P025", "P026"],
    "hydraulics":    ["P003", "P006", "P007", "P019", "P023"],
    "bearings_seals":["P001", "P002", "P011", "P012", "P020", "P021"],
    "engine_misc":   ["P009", "P010", "P013", "P016", "P017", "P018"],
    "consumables":   ["P001", "P004", "P009", "P013", "P022"],
}

# (cui, name, industry_caen, active, order_gap_days, volume_mult, primary_group, secondary_group)
# volume_mult drives customer concentration: 2 dominant clients at 3.5x, 2 large at 1.5x, rest small
CUSTOMERS = [
    # ---- dominant (creates concentration risk) ----
    ("RO12345678", "SC Agro Muntenia SRL",        "0111", True,  3,  8.0, "u650_parts",    "hydraulics"),
    ("RO78901234", "SC Holding Cereale SRL",       "0111", True,  5,  2.0, "engine_misc",   "bearings_seals"),
    # ---- medium ----
    ("RO34567890", "SC Tehnica Agricola SA",       "4669", True,  8,  1.5, "bearings_seals","hydraulics"),
    ("RO45678901", "SC Agroservice Dobrogea SRL",  "4669", True,  9,  1.5, "hydraulics",    "engine_misc"),
    # ---- regular ----
    ("RO23456789", "SC Ferma Verde SRL",           "0111", True, 11,  1.0, "u650_parts",    "consumables"),
    ("RO56789012", "SC Utilaje Campiei SRL",       "4669", True, 12,  1.0, "bearings_seals","consumables"),
    ("RO67890123", "SC Agrotrans Olt SRL",         "4941", True, 13,  1.0, "engine_misc",   "u650_parts"),
    ("RO89012345", "SC Piese Tractor Nord SRL",    "4669", True, 10,  1.0, "u650_parts",    "bearings_seals"),
    ("RO90123456", "SC Bazele Agriculturii SRL",   "0111", True, 14,  0.8, "consumables",   "engine_misc"),
    ("RO01234567", "SC Mecanica Campului SRL",     "3311", True, 15,  0.8, "hydraulics",    "bearings_seals"),
    ("RO11223344", "SC Agro Suceava SRL",          "0111", True, 14,  0.8, "engine_misc",   "consumables"),
    # ---- churned (last order ~late Nov 2025) ----
    ("RO22334455", "SC Utilaje Iasi SRL",          "4669", False,10,  1.0, "bearings_seals","hydraulics"),
    ("RO33445566", "SC Agro Moldova SRL",          "0111", False,12,  0.9, "u650_parts",    "consumables"),
]

def customer_product_weights(primary: str, secondary: str) -> dict[str, float]:
    """
    Returns a weight per product code.
    Products in primary group: weight 6
    Products in secondary group: weight 2
    All others: weight 0.3  (occasional cross-sells)
    """
    weights: dict[str, float] = {}
    for p in PRODUCTS:
        code = p[0]
        if code in PRODUCT_GROUPS[primary]:
            weights[code] = 6.0
        elif code in PRODUCT_GROUPS[secondary]:
            weights[code] = 2.0
        else:
            weights[code] = 0.3
    return weights

# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------
SEASONALITY_PROFILES = {
    #            Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
    "general":  [0.70, 0.75, 1.10, 1.05, 1.00, 0.95, 0.90, 0.95, 1.00, 1.05, 0.90, 0.65],
    "planting": [0.40, 0.55, 1.90, 1.80, 1.20, 0.80, 0.70, 0.75, 0.80, 0.85, 0.65, 0.40],
    "harvest":  [0.60, 0.65, 0.80, 0.85, 0.90, 1.00, 1.20, 1.85, 1.75, 1.10, 0.75, 0.55],
}

def seasonal_mult(profile: str, month: int) -> float:
    return SEASONALITY_PROFILES[profile][month - 1]

def yoy_growth_mult(d: date) -> float:
    """~5% annual YoY demand growth, compounded from START_DATE."""
    years_elapsed = (d - START_DATE).days / 365.25
    return 1.0 + 0.05 * years_elapsed

def decline_mult(product_code: str, d: date) -> float:
    if product_code not in DECLINING:
        return 1.0
    total = (END_DATE - START_DATE).days
    elapsed = (d - START_DATE).days
    return max(0.10, 1.0 - 0.90 * (elapsed / total))

# ---------------------------------------------------------------------------
# Price events  (fix #2 + fix #6)
# Supplier raises prices on a specific date — all products from that supplier jump.
# Selling prices follow 1-3 months later, partially (margin compression window).
# ---------------------------------------------------------------------------
# (supplier_cui, effective_date, pct_increase)
SUPPLIER_COST_EVENTS: list[tuple[str, date, float]] = [
    # 2022 — post-pandemic supply chain shocks + energy crisis
    ("RO40000004", date(2022, 7,  1), 0.09),   # Agro Import +9% (energy/transport)
    ("RO40000002", date(2022, 9,  1), 0.08),   # Hidraulica +8% (steel prices)
    ("RO40000003", date(2022, 11, 1), 0.07),   # Auto Parts +7% (chip shortage echo)
    # 2023 — inflation wave
    ("RO40000001", date(2023, 2,  1), 0.06),   # Rulmenti +6%
    ("RO40000005", date(2023, 5,  1), 0.05),   # Pompe si Filtre +5%
    ("RO40000004", date(2023, 9,  1), 0.07),   # Agro Import +7% (weak RON vs EUR)
    # 2024 — stabilization with selective increases
    ("RO40000003", date(2024, 8,  1), 0.06),   # Auto Parts +6%
    ("RO40000004", date(2024, 10, 1), 0.08),   # Agro Import +8% (weak RON)
    # 2025 — continued pressure
    ("RO40000001", date(2025, 2,  1), 0.11),   # Rulmenti +11%
    ("RO40000005", date(2025, 4,  1), 0.07),   # Pompe si Filtre +7%
    ("RO40000002", date(2025, 6,  1), 0.09),   # Hidraulica +9%
    ("RO40000001", date(2025, 11, 1), 0.07),   # Rulmenti second round +7%
    # 2026
    ("RO40000004", date(2026, 1,  1), 0.05),   # Agro Import +5%
]

# Selling price events lag behind cost events by 1-3 months, partial pass-through (~65%)
SELL_PRICE_EVENTS: list[tuple[str, date, float]] = []
for supplier_cui, cost_date, pct in SUPPLIER_COST_EVENTS:
    lag_months = random.randint(1, 3)
    lag_date = date(
        cost_date.year + (cost_date.month + lag_months - 1) // 12,
        (cost_date.month + lag_months - 1) % 12 + 1,
        1,
    )
    for pcode, scui in PRODUCT_SUPPLIER.items():
        if scui == supplier_cui:
            SELL_PRICE_EVENTS.append((pcode, lag_date, pct * 0.65))

def _apply_events(events: list[tuple], key: str, d: date, base: float) -> float:
    """Apply cumulative price events for a given key (product or supplier) up to date d."""
    result = base
    for ev_key, ev_date, ev_pct in events:
        if ev_key == key and d >= ev_date:
            result *= (1.0 + ev_pct)
    return result

def buy_price(product_code: str, d: date) -> float:
    base = PRODUCT_MAP[product_code][3]
    supplier_cui = PRODUCT_SUPPLIER.get(product_code, "RO40000003")
    price = _apply_events(
        [(s, dt, p) for s, dt, p in SUPPLIER_COST_EVENTS],
        supplier_cui, d, base,
    )
    # Small per-invoice noise
    return round(price * random.uniform(0.98, 1.02), 2)

def sell_price(product_code: str, d: date) -> float:
    base = PRODUCT_MAP[product_code][2]
    price = _apply_events(SELL_PRICE_EVENTS, product_code, d, base)
    # Small per-invoice noise (less than buy side)
    return round(price * random.uniform(0.97, 1.03), 2)

# ---------------------------------------------------------------------------
# Invoice number counters
# ---------------------------------------------------------------------------
_issued_seq   = 1000
_received_seq = 5000

def next_issued() -> str:
    global _issued_seq
    _issued_seq += 1
    return f"FC{_issued_seq}"

def next_received() -> str:
    global _received_seq
    _received_seq += 1
    return f"RF{_received_seq}"

# ---------------------------------------------------------------------------
# Sales event generation
# ---------------------------------------------------------------------------

def generate_sales() -> list[dict]:
    rows: list[dict] = []

    for cui, cname, _, active, gap_days, vol_mult, primary_grp, secondary_grp in CUSTOMERS:
        cutoff = END_DATE if active else date(2025, 11, 28)

        product_weights_map = customer_product_weights(primary_grp, secondary_grp)
        all_codes  = list(product_weights_map.keys())
        all_weights = [product_weights_map[c] for c in all_codes]

        current_date = START_DATE + timedelta(days=random.randint(0, gap_days))

        while current_date <= cutoff:
            if current_date.weekday() >= 5:        # skip weekends
                current_date += timedelta(days=1)
                continue

            invoice_number = next_issued()

            # Number of lines: weighted toward fewer for small customers
            n_lines = random.choices([1, 2, 3, 4, 5], weights=[15, 30, 30, 15, 10])[0]

            # Sample products using customer specialisation weights
            chosen = random.choices(all_codes, weights=all_weights, k=n_lines)
            chosen = list(dict.fromkeys(chosen))   # deduplicate, preserve order

            for pcode in chosen:
                _, pname, _, _, base_weekly, season_profile, _ = PRODUCT_MAP[pcode]

                s_mult = seasonal_mult(season_profile, current_date.month)
                d_mult = decline_mult(pcode, current_date)
                g_mult = yoy_growth_mult(current_date)
                orders_per_week = 7.0 / gap_days
                expected_units  = (base_weekly / orders_per_week) * s_mult * d_mult * vol_mult * g_mult
                qty = max(1, int(np.random.poisson(max(0.5, expected_units))))

                sp = sell_price(pcode, current_date)
                rows.append({
                    "invoice_number":  invoice_number,
                    "invoice_date":    current_date.isoformat(),
                    "invoice_type":    "factura",
                    "direction":       "issued",
                    "product_code":    pcode,
                    "product_name":    pname,
                    "quantity":        qty,
                    "unit_price":      sp,
                    "total_value":     round(qty * sp, 2),
                    "partner_cui":     cui,
                    "partner_name":    cname,
                    "linked_invoice":  "",
                })

            # ~4% chance: credit note for one line of this order  (fix #5)
            if random.random() < 0.04 and chosen:
                return_code   = random.choice(chosen)
                return_name   = PRODUCT_MAP[return_code][1]
                return_qty    = random.randint(1, 2)
                sp            = sell_price(return_code, current_date)
                storno_date   = current_date + timedelta(days=random.randint(1, 5))
                rows.append({
                    "invoice_number":  next_issued(),
                    "invoice_date":    storno_date.isoformat(),
                    "invoice_type":    "storno",
                    "direction":       "issued",
                    "product_code":    return_code,
                    "product_name":    return_name,
                    "quantity":        -return_qty,
                    "unit_price":      sp,
                    "total_value":     round(-return_qty * sp, 2),
                    "partner_cui":     cui,
                    "partner_name":    cname,
                    "linked_invoice":  invoice_number,  # reference to original
                })

            jitter = max(1, int(np.random.normal(gap_days, gap_days * 0.25)))
            current_date += timedelta(days=jitter)

    return rows

# ---------------------------------------------------------------------------
# Purchase event generation
# ---------------------------------------------------------------------------

def generate_purchases(sales_rows: list[dict]) -> list[dict]:
    # Aggregate sales per product per week
    weekly_sales: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for row in sales_rows:
        if row["invoice_type"] == "storno":
            continue
        d = date.fromisoformat(row["invoice_date"])
        week_start = d - timedelta(days=d.weekday())
        weekly_sales[row["product_code"]][week_start] += row["quantity"]

    rows: list[dict] = []

    for pcode, week_data in weekly_sales.items():
        supplier_cui = PRODUCT_SUPPLIER.get(pcode, "RO40000003")
        supplier     = SUPPLIER_MAP[supplier_cui]
        sup_pname    = supplier_product_name(supplier_cui, pcode)

        accumulated  = 0
        week_count   = 0
        order_every  = 3   # weeks

        for week_start in sorted(week_data.keys()):
            accumulated += week_data[week_start]
            week_count  += 1

            if week_count >= order_every:
                purchase_date = week_start - timedelta(days=random.randint(2, 8))
                if purchase_date < START_DATE:
                    purchase_date = START_DATE

                qty = int(accumulated * random.uniform(1.1, 1.4))
                bp  = buy_price(pcode, purchase_date)

                rows.append({
                    "invoice_number":  next_received(),
                    "invoice_date":    purchase_date.isoformat(),
                    "invoice_type":    "factura",
                    "direction":       "received",
                    "product_code":    pcode,
                    "product_name":    sup_pname,    # supplier's own product name
                    "quantity":        qty,
                    "unit_price":      bp,
                    "total_value":     round(qty * bp, 2),
                    "partner_cui":     supplier_cui,
                    "partner_name":    supplier[1],
                    "linked_invoice":  "",
                })

                accumulated = 0
                week_count  = 0

    return rows

# ---------------------------------------------------------------------------
# Stock snapshot
# ---------------------------------------------------------------------------

def generate_stock(sales_rows: list[dict], purchase_rows: list[dict]) -> list[dict]:
    net: dict[str, int] = defaultdict(int)
    for row in purchase_rows:
        net[row["product_code"]] += row["quantity"]
    for row in sales_rows:
        if row["direction"] == "issued":
            net[row["product_code"]] -= row["quantity"]

    rows = []
    for p in PRODUCTS:
        pcode, pname, _, _, _, _, declining = p
        supplier_cui = PRODUCT_SUPPLIER.get(pcode, "RO40000003")
        supplier     = SUPPLIER_MAP[supplier_cui]

        stock = max(0, net.get(pcode, 0))
        stock = int(stock * random.uniform(0.85, 1.15))   # realistic noise

        if declining:
            stock = max(0, int(stock * 0.25))             # owner hasn't reordered

        # Intentionally bloated dead stock (high-value, slow-moving)
        if pcode in ("P017", "P023"):
            stock = int(stock * 2.8)

        bp = buy_price(pcode, END_DATE)
        rows.append({
            "product_code":      pcode,
            "product_name":      pname,
            "quantity_in_stock": stock,
            "supplier_cui":      supplier_cui,
            "supplier_name":     supplier[1],
            "lead_time_days":    supplier[2],
            "min_order_qty":     random.choice([1, 5, 10]),
            "purchase_price":    bp,
        })
    return rows

# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

INVOICE_FIELDS = [
    "invoice_number", "invoice_date", "invoice_type", "direction",
    "product_code", "product_name", "quantity", "unit_price", "total_value",
    "partner_cui", "partner_name", "linked_invoice",
]

STOCK_FIELDS = [
    "product_code", "product_name", "quantity_in_stock",
    "supplier_cui", "supplier_name", "lead_time_days",
    "min_order_qty", "purchase_price",
]


def write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows):,} rows  →  {path}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Generating synthetic data …\n")

    print("  Building sales invoices …")
    sales = generate_sales()

    print("  Building purchase invoices …")
    purchases = generate_purchases(sales)

    all_invoices = sorted(sales + purchases, key=lambda r: r["invoice_date"])
    write_csv(os.path.join(OUTPUT_DIR, "invoices.csv"), all_invoices, INVOICE_FIELDS)

    print("  Building stock snapshot …")
    stock = generate_stock(sales, purchases)
    write_csv(os.path.join(OUTPUT_DIR, "stock.csv"), stock, STOCK_FIELDS)

    # ---- sanity summary ----
    import pandas as pd
    df   = pd.DataFrame(sales)
    sold = df[df.invoice_type == "factura"]

    print("\nRevenue by customer (top 5):")
    by_customer = (
        sold.groupby("partner_name")["total_value"]
        .sum()
        .sort_values(ascending=False)
    )
    total_rev = by_customer.sum()
    for name, rev in by_customer.head(5).items():
        print(f"    {name:<40s}  {rev:>10,.0f} RON  ({100*rev/total_rev:.1f}%)")
    print(f"    {'... rest ...':<40s}  {by_customer.iloc[5:].sum():>10,.0f} RON  ({100*by_customer.iloc[5:].sum()/total_rev:.1f}%)")

    top1_share = by_customer.iloc[0] / total_rev
    print(f"\n  Top-1 customer share: {100*top1_share:.1f}%  {'⚠ concentration risk' if top1_share > 0.30 else ''}")

    stornos = df[df.invoice_type == "storno"]
    print(f"\n  Sales lines   : {len(sold):,}")
    print(f"  Credit notes  : {len(stornos):,}  ({100*len(stornos)/len(sold):.1f}%)")
    print(f"  Purchase lines: {len(purchases):,}")
    print(f"  Date range    : {START_DATE} → {END_DATE}")

    print("\n  Supplier name variation sample (same product, different invoice names):")
    sample_product = "P001"
    sold_name = PRODUCT_MAP[sample_product][1]
    sup_name  = supplier_product_name(PRODUCT_SUPPLIER[sample_product], sample_product)
    print(f"    Sales invoice : {sold_name}")
    print(f"    Supplier inv. : {sup_name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
