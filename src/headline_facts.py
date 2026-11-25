"""Derived headline figures quoted in README / notes, written to outputs/headline_facts.csv so every
number in the write-up points to a generated file."""
import pandas as pd

from common import OUTPUTS, POWERBI


def main():
    c = pd.read_csv(POWERBI / "dim_customer_rfm_clv.csv")
    mm = pd.read_csv(POWERBI / "fact_model_metrics.csv").set_index("Metric")["Value"].astype(str)
    mr = pd.read_csv(OUTPUTS / "sql" / "monthly_revenue.csv")
    top = pd.read_csv(OUTPUTS / "sql" / "top10_customers.csv")
    hold = pd.read_csv(OUTPUTS / "calibration_holdout.csv").set_index("calibration_repeat_purchases")
    san = pd.read_csv(OUTPUTS / "sanity_checks.csv").set_index("Check")["Value"]

    total_rev = c.Monetary.sum()
    total_clv = c.PredictedCLV_26w.sum()
    ch = c[(c.RFM_Segment == "Champions") & (c.CLV_Segment == "High CLV")]
    champs = c[c.RFM_Segment == "Champions"]
    risk = c[(c.RFM_Segment == "At-risk loyal") & c.CLV_Segment.isin(["High CLV", "Mid-high CLV"])]
    peak = mr.loc[mr.revenue.idxmax()]
    rows = [
        ("Champions | High CLV share of customers (%)", 100 * len(ch) / len(c)),
        ("Champions | High CLV share of historical revenue (%)", 100 * ch.Monetary.sum() / total_rev),
        ("Champions | High CLV share of predicted CLV (%)", 100 * ch.PredictedCLV_26w.sum() / total_clv),
        ("Champions | High CLV median ProbabilityAlive", ch.ProbabilityAlive.median()),
        ("Champions | High CLV median invoices", ch.Frequency.median()),
        ("Champions | High CLV median RecencyDays", ch.RecencyDays.median()),
        ("All Champions customers", len(champs)),
        ("All Champions share of historical revenue (%)", 100 * champs.Monetary.sum() / total_rev),
        ("At-risk loyal with High/Mid-high CLV: customers", len(risk)),
        ("At-risk loyal with High/Mid-high CLV: predicted CLV", risk.PredictedCLV_26w.sum()),
        ("At-risk loyal with High/Mid-high CLV: median ProbabilityAlive", risk.ProbabilityAlive.median()),
        ("Single-purchase customers share of customers (%)",
         100 * (c.CLV_ModelStatus != "Modeled").mean()),
        ("Single-purchase customers historical revenue", c.loc[c.CLV_ModelStatus != "Modeled", "Monetary"].sum()),
        ("Peak revenue month", peak.year_month),
        ("Peak month revenue", peak.revenue),
        ("Top customer by revenue: Customer ID", int(top.iloc[0].customer_id)),
        ("Top customer revenue", top.iloc[0].revenue),
        ("Top 10 customers share of revenue (%)", top.share_of_revenue_pct.sum()),
        ("Predicted CLV total / historical revenue (%)", 100 * total_clv / total_rev),
        ("Holdout predicted / actual repeat purchases (ALL)",
         f"{hold.loc['ALL', 'total_predicted']:.0f} / {hold.loc['ALL', 'total_actual']:.0f}"),
        ("Holdout aggregate over-prediction (%)", hold.loc["ALL", "error_pct"]),
        ("Holdout over-prediction for 10+ group (%)", hold.loc["10+", "error_pct"]),
        ("Holdout over-prediction for 0 group (%)", hold.loc["0", "error_pct"]),
        ("Holdout corr(predicted, actual)", san["Holdout corr(predicted, actual)"]),
        ("Pearson corr(frequency, AOV)", san["Pearson corr(frequency, AOV)"]),
        ("Spearman corr(frequency, AOV)", san["Spearman corr(frequency, AOV)"]),
    ]
    out = pd.DataFrame(rows, columns=["Fact", "Value"])
    out.to_csv(OUTPUTS / "headline_facts.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
