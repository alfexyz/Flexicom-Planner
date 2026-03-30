# Flexicom-Planner
FLEXICOM Planner - a easy to use tool that gives you a ton of insight into the company's operations

# S&OP Platform — Redesigned Build Plan

Optimized for maximum insight from minimum data sources. The guiding principle: every additional source costs social capital (you're asking a busy person to do something). Every additional column from the same source is nearly free.

---

## Part 1: The Data You Need

### Source A — e-Factura Export (one ask: "export your invoices from the last 2 years")

This single source, pulled from either the ANAF SPV portal or exported as CSV from their accounting software, gives you:

| Column | What It Unlocks |
|---|---|
| Invoice date | Demand trends, seasonality detection, weekly/monthly patterns |
| Invoice type (normal vs. credit note) | Net demand (gross sales minus returns) — without this, forecasts are inflated |
| Product name / code | Per-product analysis, SKU grouping, product master seed |
| Quantity | Demand rate per product, volume rankings |
| Unit price (selling) | Revenue analysis, price change detection, discount patterns |
| Total value per line | Revenue trends, product revenue ranking |
| Customer CUI (B2B) | Customer segmentation, concentration risk, ordering pattern analysis |
| Customer name | Human-readable customer identification |
| Supplier CUI (on purchase invoices received) | Supplier identification, cost tracking |
| Unit price on purchase invoices | Purchase cost per product — margin calculation without needing a separate price list |

**Why this source is gold:** e-Factura is bilateral. You don't just get your sales — you get your purchase invoices too. This means you get both selling price AND buying price for every product, which unlocks margin analysis from a single source.

**The ask to the business owner:** "Can you export your e-Factura data from the last 24 months? Both issued and received invoices." One export. One conversation. Ten columns of insight.


### Source B — Stock Spreadsheet (one ask: "send me your current stock list")

This is the manual spreadsheet or accounting software export they already maintain for their top products:

| Column | What It Unlocks |
|---|---|
| Product name / code | Links to e-Factura data for matching |
| Current quantity in stock | Days of cover, reorder alerts, stockout risk |
| Supplier name | Groups products by supplier for consolidated ordering |
| Supplier lead time (days, estimated) | Reorder point calculation, delivery risk |
| Minimum order quantity (if known) | Realistic order recommendations |
| Purchase price (if not available from e-Factura) | Fallback for margin calculation |

**The ask to the business owner:** "Send me whatever stock list you currently maintain — Excel, screenshot of your software, anything." One file. You clean it.


### Source C — No Ask Required (free public APIs you integrate yourself)

| Data | Source | Access |
|---|---|---|
| Customer company details (industry, size, location) | ANAF public CUI lookup API | Free, no auth needed, enrich from CUI in e-Factura |
| Daily exchange rates (EUR/RON, USD/RON) | BNR XML feed | Free, no auth, daily update |
| Agricultural calendar / crop cycles | MADR public data | Static dataset, built once |
| EU subsidy payment schedule | APIA public announcements | Manual tracking, updated a few times per year |

These require zero involvement from the business owner. You integrate them silently, and they show up as context in your analysis ("demand spike coincides with APIA subsidy payments in March").

---

**Total asks to the business owner: 2**
1. Export e-Factura (issued + received) — last 24 months
2. Send current stock list

Everything else you get yourself.

---

## Part 2: The Features You Can Build

### Tier 1 — From e-Factura Alone (no stock data needed)

**1.1 Demand Rate per Product**
Calculate rolling average daily/weekly demand for each product using invoice quantities over time. Use a weighted moving average (more recent months count more) rather than a simple average, so the model adapts to trends. Display as "X units/week" with a trend arrow (rising, flat, falling). This is the foundation number that feeds almost every other feature.

**1.2 Seasonality Detection**
With 24 months of data, compare the same month across two years to detect repeating patterns. Flag products where a specific month consistently shows 2x+ the average demand. Overlay this with the agricultural calendar (Source C) to validate — if tractor parts spike every March and March is planting season, that's a confirmed seasonal pattern, not noise. Present as a heatmap: products on the Y axis, months on the X axis, color intensity = demand relative to average.

**1.3 Product Ranking (Volume and Revenue)**
Rank all products by units sold and by total revenue. These are often different lists — a cheap gasket sells thousands of units but a hydraulic pump generates more revenue per sale. Display both rankings side by side. Highlight products that rank high on volume but low on revenue (high handling cost, low value) and products that rank high on revenue but low on volume (high value, worth protecting stock).

**1.4 Product Margin Ranking**
Using selling price from issued invoices and purchase cost from received invoices, calculate gross margin per product. Rank products by margin percentage and by total margin contribution (margin % × volume). Flag products with declining margins over time (supplier raised prices but selling price didn't follow). This tells the owner which products actually make money vs. which ones just move.

**1.5 Revenue Trend Analysis**
Aggregate total revenue monthly. Fit a simple trend line. Break it down: is revenue growth coming from selling more units, from price increases, or from new customers? Show decomposition: volume effect vs. price effect vs. customer mix effect. Monthly granularity (not weekly — weekly is too noisy for B2B).

**1.6 Customer Concentration Risk**
Calculate what percentage of total revenue comes from the top 1, 3, 5, and 10 customers. If one customer represents 30%+ of revenue, that's a risk flag. Display as a simple bar chart + a warning if concentration is dangerously high. Enrich each customer with their CAEN industry code from the free ANAF API (Source C) to show if the business is also concentrated in a single industry.

**1.7 Customer Ordering Patterns**
For each B2B customer, calculate: average order frequency (days between orders), average order size, and last order date. Flag customers whose last order was significantly later than their usual frequency ("Customer X usually orders every 45 days but hasn't ordered in 78 days"). This is a softer, more honest version of "churn detection" — you're not claiming they churned, you're saying their pattern has deviated.

**1.8 Price Sensitivity Detection**
Track unit price changes over time per product. When a price increased, did the quantity sold in the following period drop? Correlate price changes with demand changes to flag products where customers are price-sensitive (demand drops when price rises) vs. price-inelastic (demand stays flat regardless). This helps the owner decide where they can raise prices and where they can't.

**1.9 Slow-Moving Product Alert**
Compare each product's sales rate in the last 90 days vs. the previous 90 days. Flag products where the rate has dropped by more than 40%. Differentiate between "seasonal dip" (expected, matches historical pattern) and "genuine decline" (no seasonal explanation). This prevents the owner from reordering products that are dying.

**1.10 Cost Trend per Product**
Track purchase cost over time from received e-Factura invoices. Alert when a supplier has raised prices by more than a threshold (e.g., 10% in 6 months). Cross-reference with BNR exchange rates (Source C) — if the supplier prices in EUR and the RON weakened, that explains the cost increase. If the RON was stable and costs still rose, that's the supplier raising margins.


### Tier 2 — From e-Factura + Stock Spreadsheet Combined

**2.1 Days of Cover per Product**
Current stock ÷ average daily demand = days until stockout at current sales rate. The single most actionable number in inventory management. Color-code: green (60+ days), amber (15-60 days), red (under 15 days). Adjust dynamically if an upcoming month is historically high-demand.

**2.2 Reorder Point Alert**
ROP = (average daily demand × supplier lead time) + safety stock. Safety stock = Z × σ_demand × √lead_time, where Z is based on a service level the owner chooses (95% default = Z of 1.65). When current stock drops below ROP, fire an alert: "Order [product] now — at current demand, you'll run out in [X] days and your supplier needs [Y] days to deliver."

**2.3 Suggested Order Quantity**
Don't just say "order now" — say how much. Use Economic Order Quantity as a starting point, adjusted for the supplier's minimum order quantity and any volume discount thresholds. Present as: "Order [N] units of [product] from [supplier]. This covers [X] days of demand at current rate including safety buffer. Estimated cost: [amount] RON."

**2.4 Stockout Risk Timeline**
For every product, project when it will run out based on current stock and demand rate. Display as a timeline: "Product A runs out April 12, Product B runs out April 18, Product C is safe until June." Overlay with supplier lead times to show which products will run out BEFORE a new order could arrive — those are the critical emergencies.

**2.5 Dead Stock Detection**
Cross-reference stock on hand with sales history. Products sitting in stock with zero or near-zero sales in the last 6 months are dead stock. Calculate the capital tied up: quantity × purchase cost. Present as: "You have 12,400 RON worth of products that haven't sold in 6 months. Here's the list, ranked by capital trapped."

**2.6 Supplier Ordering Summary**
Group all reorder recommendations by supplier. Instead of 15 individual product alerts, generate one consolidated order per supplier: "For Supplier X, order: 50 units of A, 30 units of B, 20 units of C. Total estimated cost: 8,200 RON. This shipment covers all their products for the next 45 days." This is what the owner actually wants — not product-level alerts but a supplier-level shopping list.

**2.7 Working Capital in Inventory**
Total value of all stock on hand at purchase cost. Break down by: healthy stock (selling well), slow stock (selling but declining), and dead stock (not selling). Show the owner how much cash is trapped in inventory that isn't earning anything. Trend this monthly to show whether inventory efficiency is improving or worsening.

**2.8 Margin-Weighted Reorder Priority**
Not all stockouts are equal. Running out of a high-margin product costs more than running out of a low-margin one. Multiply stockout risk by gross margin to create a priority score. The owner should reorder the high-margin, high-risk products first. This combines Tier 1 margin analysis with Tier 2 stock data.

---

## Part 3: What to Build Before You Have Real Data

The goal: when the business owner hands you an e-Factura export and a stock spreadsheet, you plug them in, and the platform works immediately. No rebuilding. No "give me two weeks." Here's what you build, in order.

### Build 1: Synthetic Data Generator
**Time estimate: 1-2 days**

A Python script that produces fake but realistic data mimicking what you'd get from a real business:

- 20-30 products (agricultural spare parts with realistic names like "Rulment 6205-2RS", "Curea trapezoidala B68", "Filtru ulei hidraulic")
- 10-15 B2B customers with real-looking CUIs
- 24 months of daily invoice data with:
  - Seasonal variation (planting season spike in March-April, harvest spike in August-September)
  - Random noise (demand isn't perfectly smooth)
  - Occasional credit notes (returns, ~3-5% of invoices)
  - Gradual price changes (supplier costs rising ~5-8% per year)
  - 2-3 products that are clearly declining (slow movers entering dead stock)
  - 1-2 customers who stopped ordering 4 months ago (pattern deviation)
- A matching set of "received" invoices (purchase invoices from 5 suppliers) with purchase costs
- A stock spreadsheet with current quantities, supplier names, and estimated lead times

This is NOT busy work. This generator IS your test suite. Every time you change your calculation engine, you rerun it against this data and verify the outputs look sensible.

### Build 2: Data Ingestion & Normalization Layer
**Time estimate: 2-3 days**

A Python module that takes raw input and produces clean, standardized tables:

- **e-Factura parser:** Reads the XML or CSV export. Handles encoding issues (Romanian diacritics). Separates issued vs. received invoices. Extracts all 10 columns from Source A. Handles edge cases: partial deliveries, multi-line invoices, credit notes linked to original invoices.
- **Stock spreadsheet parser:** Reads Excel/CSV with flexible column matching (the owner's spreadsheet won't have your exact column names — use fuzzy matching or LLM-assisted column mapping to figure out which column is "quantity" vs. "price" vs. "product name").
- **SKU normalization:** Uses an LLM call to match messy product names between the stock spreadsheet and the invoice data. "Rulment 6205" in the spreadsheet needs to match "RULMENT 6205-2RS SKF" in the invoices. This is where most naive approaches break — invest effort here.
- **Output:** Two clean database tables — a transaction table (all invoices, normalized) and an inventory table (current stock, linked to the same product IDs).

### Build 3: Calculation Engine
**Time estimate: 3-4 days**

A Python module with pure functions (no UI, no API, just math). Each function takes the clean tables as input and returns a result:

- `compute_demand_rate(product_id, window_days)` → average daily demand, standard deviation, trend direction
- `detect_seasonality(product_id)` → monthly indices (e.g., March = 1.8x average, November = 0.4x average)
- `compute_days_of_cover(product_id, current_stock)` → days until stockout, adjusted for upcoming seasonal period
- `compute_reorder_point(product_id, lead_time, service_level)` → ROP, safety stock, suggested order quantity
- `rank_products(metric)` → sorted list by volume, revenue, margin, or margin-weighted risk
- `detect_customer_pattern_deviation(customer_id)` → expected order date, days overdue, confidence level
- `compute_margin(product_id)` → gross margin %, margin trend, cost trend with exchange rate overlay
- `detect_slow_movers(threshold_pct)` → products with demand drop exceeding threshold
- `compute_dead_stock(months_threshold)` → products with zero/near-zero sales, capital trapped
- `generate_supplier_order(supplier_id)` → consolidated order list, total cost, coverage days
- `compute_working_capital_breakdown()` → total inventory value split by healthy/slow/dead

Write unit tests for each function using your synthetic data. Every function should have at least 3 test cases: a normal product, a seasonal product, and an edge case (new product with only 2 months of history, product with zero sales, etc.).

### Build 4: REST API
**Time estimate: 1-2 days**

FastAPI wrapper around the calculation engine. Endpoints:

- `GET /products` → all products with current status (stock level, days of cover, color code, trend)
- `GET /products/{id}` → full detail for one product (demand history, margin, seasonality, ROP)
- `GET /alerts` → all products that need attention today (below ROP, dead stock, declining demand)
- `GET /alerts/orders` → consolidated order recommendations grouped by supplier
- `GET /customers` → customer ranking with ordering pattern status
- `GET /customers/{id}` → single customer detail (order history, revenue contribution, pattern analysis)
- `GET /overview` → dashboard summary (total revenue trend, inventory health score, top 5 alerts, cash in stock)
- `POST /upload/invoices` → upload new e-Factura export, triggers re-parsing and recalculation
- `POST /upload/stock` → upload new stock spreadsheet, triggers re-parsing

The upload endpoints are critical — they're what turns a demo into a real product. The owner drops in a fresh export, the dashboard updates. No developer needed.

### Build 5: React Dashboard
**Time estimate: 4-5 days**

Four screens, clean and functional. Use Recharts for charts, Tailwind for styling, keep it simple.

**Screen 1 — Overview Dashboard**
A single page the owner opens every morning. Shows:
- Total revenue this month vs. last month vs. same month last year (three numbers, big font)
- Inventory health: a donut chart showing percentage of stock that's healthy / needs reorder / dead
- Working capital in inventory (total RON trapped in stock)
- Alert count badge: "7 products need attention"
- Top 3 most urgent alerts as cards (clickable, leads to product detail)

**Screen 2 — Product List**
Table of all products. Each row shows: product name, current stock, days of cover (color-coded), demand trend arrow, gross margin %, and a status badge (OK / Order Soon / Critical / Dead). Sortable by any column. Clicking a row opens the product detail.

**Screen 3 — Product Detail**
For a single product, shows:
- Sales history chart (24 months, with seasonal overlay if detected)
- Current stock vs. reorder point (visual gauge)
- Margin chart over time (selling price line vs. purchase cost line)
- Key numbers: daily demand rate, days of cover, ROP, safety stock, suggested order quantity
- Supplier info: name, lead time, last order date, last delivery date
- If below ROP: a prominent "Generate Order" action that adds it to the supplier order queue

**Screen 4 — Smart Alerts**
A prioritized list of everything that needs action, categorized:
- 🔴 **Critical:** Products that will stock out before a supplier order could arrive
- 🟠 **Order Now:** Products below their reorder point
- 🟡 **Watch:** Products approaching reorder point within 2 weeks
- 💀 **Dead Stock:** Products with zero sales and capital trapped
- 📉 **Declining:** Products with significant demand drops (not seasonal)
- 👤 **Customer Deviation:** B2B customers whose ordering pattern has broken

Each alert is a card with the key context and a recommended action. Not just "Product X is low" but "Product X has 12 units left, selling 3/week, supplier needs 14 days. You'll run out April 8. Order 45 units (6-week cover + safety stock) for ~2,100 RON."

---

## The Bridge Between Demo and Production

When you sit down with the business owner, here's exactly what happens:

1. They export their e-Factura data (10-minute task in their accounting software or ANAF portal)
2. They send you whatever stock list they have (email an Excel file — 2 minutes)
3. You run the data through your ingestion layer (automated, takes seconds)
4. The SKU normalizer matches products between the two sources (LLM-assisted, you review edge cases in 10 minutes)
5. The calculation engine runs (seconds)
6. The dashboard populates with their real numbers

**Total time from "here's my data" to "here's your dashboard": under 30 minutes.**

That's the demo. Not slides. Not mockups. Their actual data, their actual products, their actual problems, on screen, in half an hour.

Everything you built with synthetic data works identically with real data because the interface between the data and the engine is the same two normalized tables. The synthetic data generator was just a stand-in for the real parser output. Swap the input, keep everything else.
