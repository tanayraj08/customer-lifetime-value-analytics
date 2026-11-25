"""Step 4: BG/NBD + Gamma-Gamma -> 26-week predicted CLV, CLV quartiles, combined segments.

BG/NBD  (Fader, Hardie & Lee 2005) - a probabilistic model of WHEN customers buy and
        WHEN they silently stop ("die"). Inputs per customer:
          frequency = repeat purchases = invoices - 1
          recency   = weeks between first and last purchase day
          T         = weeks between first purchase day and the snapshot date
        Weeks are whole days / 7, with timestamps normalised to the day (as in the
        reference outputs), so recency <= T always holds and all 5,878 customers are fitted.
Gamma-Gamma - a probabilistic model of HOW MUCH a customer spends per order, fitted on
        repeat customers (frequency > 0) using their average order value.
CLV     - lifetimes' customer_lifetime_value(bgf, ..., time=26, freq="W", discount_rate=0.01):
        expected purchases from BG/NBD x expected order value from Gamma-Gamma, summed period by
        period and discounted. This is the project's "PredictedCLV_26w" metric, reproduced exactly.
        NOTE on units: lifetimes documents `time` in MONTHS and `discount_rate` as monthly; with
        freq="W" it steps 4.345 weeks per period, so time=26 spans ~113 weeks. The same model with
        time=6 (~26 weeks) is reported in outputs/clv_horizon_check.csv (src/sanity.py).

These are statistical models whose parameters are estimated by maximum likelihood; they are
not machine-learning models in the train/predict-with-features sense.

Outputs: outputs/customer_model.csv (customer table with model columns),
         outputs/model_params.csv, outputs/fact_segment_summary.csv,
         outputs/fact_model_metrics.csv
"""
import warnings

import numpy as np
import pandas as pd
from lifetimes import BetaGeoFitter, GammaGammaFitter

from common import (CLV_TIME, CLV_LABELS, OUTPUTS, PENALIZER, SEPARATOR,
                    SINGLE_PURCHASE_LABEL, DISCOUNT_RATE)

warnings.filterwarnings("ignore")


def bgnbd_inputs(cust: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    first = pd.to_datetime(cust["FirstPurchaseDate"]).dt.normalize()
    last = pd.to_datetime(cust["LastPurchaseDate"]).dt.normalize()
    out = cust.copy()
    out["frequency"] = out["Frequency"] - 1
    out["recency"] = (last - first).dt.days / 7.0
    out["T"] = (snapshot - first).dt.days / 7.0
    # One customer (12713) first bought ON the snapshot day, giving T = 0. The reference
    # outputs floor T at 0.01 weeks so the BG/NBD likelihood is defined for them.
    out["T"] = out["T"].clip(lower=0.01)
    return out


def fit_bgnbd(c: pd.DataFrame) -> BetaGeoFitter:
    assert (c["T"] >= c["recency"]).all(), "recency must not exceed T"
    bgf = BetaGeoFitter(penalizer_coef=PENALIZER)
    bgf.fit(c["frequency"], c["recency"], c["T"])
    return bgf


def fit_gamma_gamma(rep: pd.DataFrame) -> GammaGammaFitter:
    ggf = GammaGammaFitter(penalizer_coef=PENALIZER)
    ggf.fit(rep["frequency"], rep["AverageOrderValue"])
    return ggf


def run_models(cust: pd.DataFrame, snapshot: pd.Timestamp):
    c = bgnbd_inputs(cust, snapshot)
    bgf = fit_bgnbd(c)
    # t is in the same unit as recency/T (weeks), so this one IS a true 26-week purchase forecast.
    c["PredictedPurchases_26w"] = bgf.conditional_expected_number_of_purchases_up_to_time(
        26, c["frequency"], c["recency"], c["T"])
    c["ProbabilityAlive"] = bgf.conditional_probability_alive(c["frequency"], c["recency"], c["T"])

    mask = (c["frequency"] > 0) & (c["AverageOrderValue"] > 0)
    rep = c[mask]
    ggf = fit_gamma_gamma(rep)
    c["ExpectedAverageValue"] = np.nan
    c.loc[mask, "ExpectedAverageValue"] = ggf.conditional_expected_average_profit(
        rep["frequency"], rep["AverageOrderValue"]).values
    c["PredictedCLV_26w"] = np.nan
    c.loc[mask, "PredictedCLV_26w"] = ggf.customer_lifetime_value(
        bgf, rep["frequency"], rep["recency"], rep["T"], rep["AverageOrderValue"],
        time=CLV_TIME, freq="W", discount_rate=DISCOUNT_RATE).values
    c["CLV_ModelStatus"] = np.where(mask, "Modeled", "Not modeled - one purchase")

    # CLV quartiles among modelled customers. A customer moves up a bucket when their CLV is
    # >= the 25th / 50th / 75th percentile (np.quantile, linear interpolation). This is what
    # the reference outputs used. clv_project.py's qcut(rank) uses right-closed bins instead,
    # which differs for exactly one customer (14522, the exact median) - see README.
    # Predicted CLV has no ties among the 4,255 modelled customers, so no tie-break is needed.
    c["CLV_Segment"] = SINGLE_PURCHASE_LABEL
    clv = c.loc[mask, "PredictedCLV_26w"]
    q25, q50, q75 = clv.quantile([0.25, 0.50, 0.75])
    bucket = (clv >= q25).astype(int) + (clv >= q50).astype(int) + (clv >= q75).astype(int)
    c.loc[mask, "CLV_Segment"] = bucket.map(dict(enumerate(CLV_LABELS))).values
    c["CustomerSegment"] = c["RFM_Segment"] + SEPARATOR + c["CLV_Segment"]
    return c, bgf, ggf


def segment_summary(c: pd.DataFrame) -> pd.DataFrame:
    s = (c.groupby(["RFM_Segment", "CLV_Segment"])
          .agg(Customers=("Customer ID", "nunique"),
               HistoricalRevenue=("Monetary", "sum"),
               PredictedCLV26w=("PredictedCLV_26w", "sum"),
               MedianPredictedCLV26w=("PredictedCLV_26w", "median"),
               MedianRecencyDays=("RecencyDays", "median"),
               MedianFrequency=("Frequency", "median"))
          .reset_index()
          .sort_values("PredictedCLV26w", ascending=False, kind="stable")
          .reset_index(drop=True))
    return s


def model_metrics(clean_summary: pd.DataFrame, c: pd.DataFrame, retention: pd.DataFrame):
    cs = dict(zip(clean_summary["Metric"], clean_summary["Value"]))
    log = pd.read_csv(OUTPUTS / "fact_cleaning_log.csv").set_index("step")["rows_removed"]
    clv = c["PredictedCLV_26w"].dropna()
    rt = dict(zip(retention["Metric"], retention["Value"]))
    rows = [
        ("Raw rows", int(cs["Raw rows"]), "All rows across both workbook sheets before cleaning"),
        ("Usable transaction rows", int(cs["Usable transaction rows"]),
         "Known customer, non-cancellation, positive quantity and positive price"),
        ("Rows removed for missing Customer ID", int(log["known_customer"]),
         "Customer ID is required for customer-level analytics"),
        ("Rows removed for cancellation invoices", int(log["exclude_cancellations"]),
         "Invoice starts with C"),
        ("Rows removed for non-positive quantity/price", int(log["positive_sales"]),
         "Quantity > 0 and Price > 0"),
        ("Exact duplicates detected and retained", int(cs["Exact duplicates detected and retained"]),
         "Retained; no deduplication assumption imposed"),
        ("Usable customers", int(cs["Usable customers"]),
         "Distinct Customer ID in cleaned transaction table"),
        ("Usable invoices", int(cs["Usable invoices"]),
         "Distinct completed invoice ID in cleaned transaction table"),
        ("Historical revenue", float(cs["Historical revenue"]),
         "Sum of Quantity x Price after cleaning"),
        ("RFM snapshot date", cs["RFM snapshot date"], "Max cleaned InvoiceDate normalized to day"),
        ("BG/NBD modeled customers", int(c["PredictedPurchases_26w"].notna().sum()),
         "All usable customers"),
        ("Gamma-Gamma modeled customers", int(len(clv)),
         "Frequency > 0 and positive average order value"),
        ("CLV horizon weeks", CLV_TIME, "Modeling assumption"),
        ("CLV discount rate per week", DISCOUNT_RATE,
         "Modeling assumption passed to lifetimes"),
        ("Predicted 26-week CLV total", clv.sum(),
         "Sum of customer-level CLV where Gamma-Gamma conditions hold"),
        ("Mean 26-week CLV among modeled customers", clv.mean(),
         "Mean over non-null customer-level CLV"),
        ("Median 26-week CLV among modeled customers", clv.median(),
         "Median over non-null customer-level CLV"),
        ("Average month+1 retention", rt["Average month+1 retention"],
         "Mean across cohorts with a month+1 observation"),
        ("Average month+3 retention", rt["Average month+3 retention"],
         "Mean across cohorts with a month+3 observation"),
        ("Average month+6 retention", rt["Average month+6 retention"],
         "Mean across cohorts with a month+6 observation"),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value", "Methodology"])


def main():
    cust = pd.read_csv(OUTPUTS / "customer_rfm.csv")
    clean_summary = pd.read_csv(OUTPUTS / "clean_summary.csv")
    snapshot = pd.Timestamp(clean_summary.set_index("Metric").loc["RFM snapshot date", "Value"])
    c, bgf, ggf = run_models(cust, snapshot)

    params = pd.concat([
        pd.DataFrame({"Model": "BG/NBD", "Parameter": bgf.params_.index, "Value": bgf.params_.values}),
        pd.DataFrame({"Model": "Gamma-Gamma", "Parameter": ggf.params_.index, "Value": ggf.params_.values}),
    ])
    params.to_csv(OUTPUTS / "model_params.csv", index=False)
    c.to_csv(OUTPUTS / "customer_model.csv", index=False)
    seg = segment_summary(c)
    seg.to_csv(OUTPUTS / "fact_segment_summary.csv", index=False)
    mm = model_metrics(clean_summary, c, pd.read_csv(OUTPUTS / "retention_summary.csv"))
    mm.to_csv(OUTPUTS / "fact_model_metrics.csv", index=False)

    champ = c[(c.RFM_Segment == "Champions") & (c.CLV_Segment == "High CLV")]
    print(params.to_string(index=False))
    print(mm[["Metric", "Value"]].to_string(index=False))
    print(f"Champions + High CLV: {len(champ)} customers, predicted CLV "
          f"{champ.PredictedCLV_26w.sum():,.2f}, historical revenue {champ.Monetary.sum():,.2f}")


if __name__ == "__main__":
    main()
