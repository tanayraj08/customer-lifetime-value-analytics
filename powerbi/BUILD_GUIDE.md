# Power BI build guide (4 pages)

There is **no .pbix file in this repo**. A .pbix can only be created in Power BI Desktop
(Windows). This folder gives you everything needed to build it in about an hour: the
star-schema tables, a theme (`clv_theme.json`), DAX (`DAX_measures.md`) and this guide.

## 1. Load the data

1. Run the pipeline first (`python run_all.py`) so `data/fact_transactions_clean.csv` exists
   (it is ~80 MB and not committed to GitHub).
2. Power BI Desktop → Get data → Text/CSV, load:
   - `data/fact_transactions_clean.csv`
   - `powerbi/dim_customer_rfm_clv.csv`, `dim_date.csv`, `fact_cohort_retention.csv`,
     `fact_cohort_revenue.csv`, `fact_segment_summary.csv`, `fact_model_metrics.csv`,
     `fact_cleaning_log.csv`, `monthly_revenue.csv`
3. In Power Query, check the types:
   - `fact_transactions_clean`: `InvoiceDate` = Date/Time, `Customer ID` = Whole number,
     `Invoice` and `StockCode` = **Text** (some invoices/stock codes contain letters),
     `Revenue`, `Price` = Decimal.
   - Add a column `InvoiceDay = Date.From([InvoiceDate])` (type Date) for the date relationship.
   - `dim_customer_rfm_clv`: `PredictedCLV_26w`, `ExpectedAverageValue` = Decimal (blanks stay
     null for single-purchase customers), `CohortMonth` = Text.
   - `dim_date[Date]` = Date.
4. View → Themes → Browse for themes → `powerbi/clv_theme.json`.

## 2. Model (star schema)

| From (many) | To (one) | Cardinality | Filter direction |
|---|---|---|---|
| `fact_transactions_clean[Customer ID]` | `dim_customer_rfm_clv[Customer ID]` | many-to-one | single |
| `fact_transactions_clean[InvoiceDay]` | `dim_date[Date]` | many-to-one | single |

`fact_cohort_retention`, `fact_cohort_revenue`, `fact_segment_summary`, `fact_model_metrics`
and `fact_cleaning_log` are pre-aggregated and stay unrelated (they drive their own visuals).
Mark `dim_date` as the date table. Add the measures from `DAX_measures.md`.

Sort-by columns: `dim_date[MonthName]` sorted by `Month`; create a small ordering column for
`RFM_Segment` (Champions=1, At-risk loyal=2, New / promising=3, Core customers=4,
Hibernating=5) and for `CLV_Segment` (High=1 … Low=4, Single-purchase=5).

## 3. Pages

### Page 1 - Overview
- KPI cards: Total Revenue (17.74M), Customers (5,878), Orders (36,969), AOV (479.95),
  Predicted CLV 26w (17.10M), Retention Month+1 (21.17%).
- Line chart: `dim_date[YearMonth]` × Total Revenue. Add a text box: "Dec 2011 has only
  9 days of data".
- Slicers: `dim_date[Year]` and `fact_transactions_clean[Country]`.
- Small table: `fact_cleaning_log` (step, rows_removed, rule) - shows data quality work.

### Page 2 - Segments
- Bar chart: `RFM_Segment` × Customer Count; second bar chart: `RFM_Segment` × Revenue Share
  of Total (two separate charts - never a dual axis).
- Matrix: rows `RFM_Segment`, columns `CLV_Segment`, values Customer Count and
  Predicted CLV 26w (heat-colour the cells with conditional formatting).
- Scatter: `dim_customer_rfm_clv` Frequency (x) vs Monetary (y), detail = `Customer ID`,
  legend = `RFM_Segment`, log scales.
- Slicer: `CustomerSegment`.

### Page 3 - Cohort retention
- Matrix: rows `fact_cohort_retention[CohortMonth]`, columns `CohortIndex`, value
  `Retention Rate`, format %, conditional formatting background (white → dark blue).
  Filter CohortIndex ≥ 2 (month 0 is always 100%).
- Cards: Retention Month+1 / +3 / +6.
- Line chart: `CohortIndex` × `Avg Cohort Retention` (the average retention curve).
- Note on page: "The 2009-12 cohort includes every customer already active before the data
  starts, so its retention is higher than a true new-customer cohort."

### Page 4 - CLV and retention strategy
- Cards: Champions High CLV Count (785), Champions High CLV Predicted CLV (10.90M),
  Modeled Customers (4,255), Median Predicted CLV 26w (1,511).
- Bar chart: `fact_segment_summary` `RFM_Segment | CLV_Segment` × `PredictedCLV26w`
  (highlight Champions | High CLV).
- Table "who to call first": `dim_customer_rfm_clv` filtered to RFM_Segment = At-risk loyal
  and CLV_Segment in (High CLV, Mid-high CLV), columns Customer ID, RecencyDays, Frequency,
  Monetary, ProbabilityAlive, PredictedCLV_26w, sorted by PredictedCLV_26w desc.
- Text box with the action plan:
  - Champions | High CLV (785): protect - VIP service, early access, no blanket discounts.
  - At-risk loyal with high/mid-high CLV (80): win-back outreach first.
  - New / promising | High CLV (33): second-purchase nurture.
  - Single-purchase customers (1,623): CLV not modelled; target with a second-order offer.
- Footnote: "Predicted CLV is a statistical forecast for repeat customers (BG/NBD + Gamma-Gamma,
  lifetimes customer_lifetime_value with time=26, freq=W, discount_rate=0.01). It is not booked
  revenue. A holdout test showed the model ranks customers well but over-predicts purchase
  volume (see README)."

## 4. Check your numbers
With no filters, the cards must show the values above. They are also in
`fact_model_metrics.csv`. If they differ, check data types (Invoice as Text) and that
`Predicted CLV 26w` is a SUM over `dim_customer_rfm_clv`, not over transactions.
