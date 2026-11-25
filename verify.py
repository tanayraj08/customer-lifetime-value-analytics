"""verify.py - checks every headline number against the generated outputs. Rebuilds nothing.

Two kinds of target:
  * the published numbers (section 1 of the project brief), typed in below, and
  * the reference project's own output tables, stored small in reference/.

Tolerances: cleaning and counts must match EXACTLY; money totals to the cent where they are
deterministic; model outputs (CLV) within 0.5 % relative; retention within 0.01 percentage points.
Usage:  python verify.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT, PBI, REF = ROOT / "outputs", ROOT / "powerbi", ROOT / "reference"
results = []


def check(name, actual, expected, tol=0.0, rel=False):
    if isinstance(expected, bool):
        ok = bool(actual) == expected
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name:<58} rebuilt {('yes' if actual else 'no'):>18}  "
              f"target {('yes' if expected else 'no'):>18}  (exact)")
        return
    try:
        a, e = float(actual), float(expected)
        diff = abs(a - e) / abs(e) if rel else abs(a - e)
        ok = diff <= tol
        tol_s = (f"±{tol:.1%} rel" if rel else ("exact" if tol == 0 else f"±{tol:g}"))
        shown_a, shown_e = f"{a:,.4f}".rstrip("0").rstrip("."), f"{e:,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        ok, tol_s, shown_a, shown_e = str(actual) == str(expected), "exact", str(actual), str(expected)
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:<58} rebuilt {shown_a:>18}  target {shown_e:>18}  ({tol_s})")


def main():
    cs = pd.read_csv(OUT / "clean_summary.csv").set_index("Metric")["Value"]
    log = pd.read_csv(PBI / "fact_cleaning_log.csv").set_index("step")
    mm = pd.read_csv(PBI / "fact_model_metrics.csv").set_index("Metric")["Value"]
    cust = pd.read_csv(PBI / "dim_customer_rfm_clv.csv")
    seg = pd.read_csv(PBI / "fact_segment_summary.csv")

    print("== Cleaning (exact)")
    check("Raw rows", cs["Raw rows"], 1_067_371)
    check("Removed: missing Customer ID", log.loc["known_customer", "rows_removed"], 243_007)
    check("Removed: cancellation invoices (Invoice starts with C)",
          log.loc["exclude_cancellations", "rows_removed"], 18_744)
    check("Removed: Quantity<=0 or Price<=0", log.loc["positive_sales", "rows_removed"], 71)
    check("Usable transaction rows", cs["Usable transaction rows"], 805_549)
    check("Usable customers", cs["Usable customers"], 5_878)
    check("Usable invoices", cs["Usable invoices"], 36_969)
    check("Exact duplicate rows detected (retained)",
          cs["Exact duplicates detected and retained"], 26_124)
    check("Rows after cleaning = rows before duplicates step (dups kept)",
          log.loc["duplicate_handling", "rows_after"], log.loc["duplicate_handling", "rows_before"])
    check("Historical revenue", round(float(cs["Historical revenue"]), 2), 17_743_429.18, 0.005)
    check("First InvoiceDate", str(cs["Min InvoiceDate"])[:16], "2009-12-01 07:45")
    check("Last InvoiceDate", str(cs["Max InvoiceDate"])[:16], "2011-12-09 12:50")
    check("RFM snapshot date", cs["RFM snapshot date"], "2011-12-09")
    ref_log = pd.read_csv(REF / "fact_cleaning_log.csv")
    check("fact_cleaning_log.csv identical to reference",
          pd.read_csv(PBI / "fact_cleaning_log.csv").equals(ref_log), True)

    print("\n== Models (within 0.5 %)")
    check("BG/NBD fitted customers", mm["BG/NBD modeled customers"], 5_878)
    check("Gamma-Gamma fitted customers", mm["Gamma-Gamma modeled customers"], 4_255)
    check("Total predicted 26-week CLV", mm["Predicted 26-week CLV total"], 17_104_456.67, 0.005, rel=True)
    check("Mean predicted CLV (modelled customers)",
          mm["Mean 26-week CLV among modeled customers"], 4_019.85, 0.005, rel=True)
    check("Median predicted CLV (modelled customers)",
          mm["Median 26-week CLV among modeled customers"], 1_511.36, 0.005, rel=True)
    check("Avg retention month+1 (%)", float(mm["Average month+1 retention"]) * 100, 21.17, 0.01)
    check("Avg retention month+3 (%)", float(mm["Average month+3 retention"]) * 100, 21.62, 0.01)
    check("Avg retention month+6 (%)", float(mm["Average month+6 retention"]) * 100, 17.82, 0.01)
    check("Customer-level CLV vs reference: max relative diff <= 0.5%",
          _max_rel_clv(cust) <= 0.005, True)

    print("\n== Segments")
    ch = cust[(cust.RFM_Segment == "Champions") & (cust.CLV_Segment == "High CLV")]
    check("Champions + High CLV customers", len(ch), 785)
    check("Champions + High CLV predicted CLV", ch.PredictedCLV_26w.sum(), 10_896_459.63, 0.005, rel=True)
    check("Champions + High CLV historical revenue", round(ch.Monetary.sum(), 2), 10_854_189.38, 0.005)
    single = seg[seg.CLV_Segment.str.startswith("Single-purchase")].set_index("RFM_Segment")["Customers"]
    check("Single-purchase: Core customers", single.get("Core customers"), 246)
    check("Single-purchase: Hibernating", single.get("Hibernating"), 1_140)
    check("Single-purchase: New / promising", single.get("New / promising"), 237)
    check("Single-purchase total (CLV not modelled)", single.sum(), 1_623)
    check("Single-purchase customers have null CLV",
          cust.loc[cust.CLV_ModelStatus != "Modeled", "PredictedCLV_26w"].isna().all(), True)

    ref = pd.read_csv(REF / "fact_segment_summary.csv")
    check("fact_segment_summary: 22 rows", len(seg), 22)
    j = ref.merge(seg, on=["RFM_Segment", "CLV_Segment"], suffixes=("_ref", ""), how="left")
    for _, r in j.iterrows():
        name = f"  {r.RFM_Segment} | {r.CLV_Segment}"
        ok = (r.Customers == r.Customers_ref
              and abs(r.HistoricalRevenue - r.HistoricalRevenue_ref) < 0.005
              and abs(r.PredictedCLV26w - r.PredictedCLV26w_ref) <= 0.005 * max(r.PredictedCLV26w_ref, 1)
              and r.MedianRecencyDays == r.MedianRecencyDays_ref
              and r.MedianFrequency == r.MedianFrequency_ref)
        check(name + f" ({int(r.Customers_ref)} cust.)", ok, True)
    check("Segment summary row order identical",
          (seg[["RFM_Segment", "CLV_Segment"]].values == ref[["RFM_Segment", "CLV_Segment"]].values).all(), True)

    print("\n== Tables, SQL and Power BI schema")
    check("Combined segment separator is ' | '",
          cust.CustomerSegment.str.contains(r" \| ", regex=True).all(), True)
    check("dim_customer_rfm_clv columns = reference",
          list(cust.columns) == pd.read_csv(REF / "dim_customer_rfm_clv_header.csv").columns.tolist(), True)
    check("fact_cohort_retention identical to reference",
          pd.read_csv(PBI / "fact_cohort_retention.csv").equals(pd.read_csv(REF / "fact_cohort_retention.csv")), True)
    check("dim_date identical to reference",
          pd.read_csv(PBI / "dim_date.csv").equals(pd.read_csv(REF / "dim_date.csv")), True)
    rc = pd.read_csv(REF / "customer_reference_subset.csv").merge(cust, on="Customer ID", suffixes=("_ref", ""))
    for col in ["R_Score", "F_Score", "M_Score", "RFM_Segment", "CLV_Segment"]:
        check(f"Customer {col} identical to reference (5,878 rows)",
              int((rc[col] != rc[col + "_ref"]).sum()), 0)
    sql = pd.read_csv(OUT / "sql_parity_check.csv")
    sql = sql[sql.result != "INFO"]
    check(f"SQL vs pandas parity checks ({len(sql)})", (sql.result == "PASS").all(), True)

    n, p = len(results), sum(results)
    print(f"\n{p} of {n} checks passed")
    sys.exit(0 if p == n else 1)


def _max_rel_clv(cust):
    ref = pd.read_csv(REF / "customer_reference_subset.csv")
    m = ref.merge(cust[["Customer ID", "PredictedCLV_26w"]], on="Customer ID", suffixes=("_ref", ""))
    m = m.dropna(subset=["PredictedCLV_26w_ref"])
    return ((m.PredictedCLV_26w - m.PredictedCLV_26w_ref).abs() / m.PredictedCLV_26w_ref.abs()).max()


if __name__ == "__main__":
    main()
