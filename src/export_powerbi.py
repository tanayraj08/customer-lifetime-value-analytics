"""Step 7: export the Power BI star schema with the reference column names.

powerbi/ (committed)                      data/ (git-ignored, ~80 MB)
  dim_customer_rfm_clv.csv                  fact_transactions_clean.csv  <- written by clean.py
  dim_date.csv
  fact_cohort_retention.csv
  fact_cohort_revenue.csv
  fact_segment_summary.csv
  fact_model_metrics.csv
  fact_cleaning_log.csv
  monthly_revenue.csv (helper for the dashboard, from SQL)
"""
import shutil

import pandas as pd

from common import CLEAN_CSV, OUTPUTS, POWERBI

CUSTOMER_COLS = [
    "Customer ID", "LastPurchaseDate", "FirstPurchaseDate", "Frequency", "Monetary",
    "RecencyDays", "CustomerLifetimeDays", "AverageOrderValue", "CohortMonth",
    "LastPurchaseMonth", "R_Score", "F_Score", "M_Score", "RFM_Score", "RFM_Total",
    "frequency", "recency", "T", "PredictedPurchases_26w", "ProbabilityAlive",
    "ExpectedAverageValue", "PredictedCLV_26w", "CLV_ModelStatus", "CLV_Segment",
    "RFM_Segment", "CustomerSegment"]


def dim_date(start, end) -> pd.DataFrame:
    d = pd.DataFrame({"Date": pd.date_range(start.normalize(), end.normalize(), freq="D")})
    d["DateKey"] = d["Date"].dt.strftime("%Y%m%d").astype(int)
    d["Year"] = d["Date"].dt.year
    d["Month"] = d["Date"].dt.month
    d["MonthName"] = d["Date"].dt.month_name()
    d["YearMonth"] = d["Date"].dt.strftime("%Y-%m")
    d["Quarter"] = "Q" + d["Date"].dt.quarter.astype(str)
    d["Date"] = d["Date"].dt.strftime("%Y-%m-%d")
    return d


def main():
    cust = pd.read_csv(OUTPUTS / "customer_model.csv")[CUSTOMER_COLS]
    cust.to_csv(POWERBI / "dim_customer_rfm_clv.csv", index=False)

    cs = pd.read_csv(OUTPUTS / "clean_summary.csv").set_index("Metric")["Value"]
    dim_date(pd.Timestamp(cs["Min InvoiceDate"]), pd.Timestamp(cs["Max InvoiceDate"])) \
        .to_csv(POWERBI / "dim_date.csv", index=False)

    for name in ["fact_cohort_retention", "fact_cohort_revenue", "fact_segment_summary",
                 "fact_model_metrics", "fact_cleaning_log"]:
        shutil.copy(OUTPUTS / f"{name}.csv", POWERBI / f"{name}.csv")
    shutil.copy(OUTPUTS / "sql" / "monthly_revenue.csv", POWERBI / "monthly_revenue.csv")

    print("Power BI tables written to", POWERBI)
    print("Transaction fact table (git-ignored):", CLEAN_CSV)


if __name__ == "__main__":
    main()
