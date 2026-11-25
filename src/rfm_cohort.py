"""Step 3: RFM scoring, RFM segments, cohort retention and cohort revenue (pandas).

Key definitions
  Invoice-level table : one row per (customer, invoice) - an invoice is ONE purchase,
                        not each product line.
  Snapshot date       : max cleaned InvoiceDate normalised to the day (2011-12-09).
  RecencyDays         : snapshot - last purchase DAY (dates normalised to midnight).
  Frequency           : distinct invoices per customer.
  Monetary            : sum of revenue per customer.
  Scores              : rank(method="first") then qcut into 5. Customers are sorted by
                        Customer ID first so ties always break the same way.
                        R is reversed so 5 = most recent.

Outputs: outputs/customer_rfm.csv, outputs/fact_cohort_retention.csv,
         outputs/fact_cohort_revenue.csv, outputs/retention_summary.csv
"""
import numpy as np
import pandas as pd

from common import CLEAN_CSV, OUTPUTS


def load_clean(path=CLEAN_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"Invoice": str, "StockCode": str},
                     parse_dates=["InvoiceDate"])
    return df


def invoice_level(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby(["Customer ID", "Invoice"], as_index=False)
              .agg(InvoiceDate=("InvoiceDate", "min"), Revenue=("Revenue", "sum")))


def quintile_score(series: pd.Series, reverse=False) -> pd.Series:
    ranks = series.rank(method="first")          # ties broken by row order (= Customer ID order)
    scores = pd.qcut(ranks, 5, labels=False) + 1  # 1..5
    scores = scores.astype(int)
    return 6 - scores if reverse else scores


# The reference outputs (fact_segment_summary / dim_customer_rfm_clv) were produced with
# F >= 3 for "At-risk loyal". The original clv_project.py says F >= 4. We follow the
# OUTPUTS so every published number reproduces. Set to 4 to use the script's rule
# (moves 471 customers from At-risk loyal to Core customers).
AT_RISK_MIN_F = 3


def rfm_segment(r, f, m):
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"
    if r <= 2 and f >= AT_RISK_MIN_F:
        return "At-risk loyal"
    if r >= 4 and f <= 2:
        return "New / promising"
    if r <= 2 and f <= 2:
        return "Hibernating"
    return "Core customers"


def build_rfm(inv: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    c = (inv.groupby("Customer ID")
            .agg(LastPurchaseDate=("InvoiceDate", "max"),
                 FirstPurchaseDate=("InvoiceDate", "min"),
                 Frequency=("Invoice", "nunique"),
                 Monetary=("Revenue", "sum"))
            .reset_index()
            .sort_values("Customer ID")            # deterministic tie-breaking
            .reset_index(drop=True))
    c["RecencyDays"] = (snapshot - c["LastPurchaseDate"].dt.normalize()).dt.days
    c["CustomerLifetimeDays"] = (snapshot - c["FirstPurchaseDate"].dt.normalize()).dt.days
    c["AverageOrderValue"] = c["Monetary"] / c["Frequency"]
    c["CohortMonth"] = c["FirstPurchaseDate"].dt.strftime("%Y-%m")
    c["LastPurchaseMonth"] = c["LastPurchaseDate"].dt.strftime("%Y-%m")
    c["R_Score"] = quintile_score(c["RecencyDays"], reverse=True)
    c["F_Score"] = quintile_score(c["Frequency"])
    c["M_Score"] = quintile_score(c["Monetary"])
    c["RFM_Score"] = (c["R_Score"].astype(str) + c["F_Score"].astype(str)
                      + c["M_Score"].astype(str)).astype(int)
    c["RFM_Total"] = c["R_Score"] + c["F_Score"] + c["M_Score"]
    c["RFM_Segment"] = [rfm_segment(r, f, m) for r, f, m in
                        zip(c["R_Score"], c["F_Score"], c["M_Score"])]
    return c


def build_cohorts(inv: pd.DataFrame, cust: pd.DataFrame):
    x = inv.merge(cust[["Customer ID", "CohortMonth"]], on="Customer ID")
    pm = x["InvoiceDate"].dt.to_period("M")
    cm = pd.PeriodIndex(x["CohortMonth"], freq="M")
    x["CohortIndex"] = (pm.dt.year - cm.year) * 12 + (pm.dt.month - cm.month) + 1
    sizes = cust.groupby("CohortMonth")["Customer ID"].nunique().rename("CohortSize")
    ret = (x.groupby(["CohortMonth", "CohortIndex"])["Customer ID"].nunique()
             .rename("ActiveCustomers").reset_index()
             .merge(sizes, on="CohortMonth"))
    ret["RetentionRate"] = ret["ActiveCustomers"] / ret["CohortSize"]
    ret = ret[["CohortMonth", "CohortIndex", "CohortSize", "ActiveCustomers", "RetentionRate"]]
    rev = (x.groupby(["CohortMonth", "CohortIndex"])["Revenue"].sum()
             .rename("CohortRevenue").reset_index())
    return ret, rev


def retention_summary(ret: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, idx in [("Average month+1 retention", 2), ("Average month+3 retention", 4),
                       ("Average month+6 retention", 7)]:
        v = ret.loc[ret["CohortIndex"] == idx, "RetentionRate"]
        rows.append((label, v.mean(), len(v)))
    return pd.DataFrame(rows, columns=["Metric", "Value", "CohortsObserved"])


def main():
    df = load_clean()
    snapshot = df["InvoiceDate"].max().normalize()
    inv = invoice_level(df)
    cust = build_rfm(inv, snapshot)
    ret, rev = build_cohorts(inv, cust)
    cust.to_csv(OUTPUTS / "customer_rfm.csv", index=False)
    ret.to_csv(OUTPUTS / "fact_cohort_retention.csv", index=False)
    rev.to_csv(OUTPUTS / "fact_cohort_revenue.csv", index=False)
    rs = retention_summary(ret)
    rs.to_csv(OUTPUTS / "retention_summary.csv", index=False)
    print("Snapshot:", snapshot.date(), "| customers:", len(cust))
    print(cust["RFM_Segment"].value_counts().to_string())
    print(rs.to_string(index=False))


if __name__ == "__main__":
    main()
