"""Step 5: model sanity checks.

(a) Fitted BG/NBD and Gamma-Gamma parameters.
(b) Calibration / holdout test: split the date range at its midpoint, fit BG/NBD on the
    first half only, predict repeat purchases for the second half, compare with what
    customers actually did, by calibration-period frequency group.
(c) Gamma-Gamma independence assumption: correlation between purchase frequency and
    average order value among repeat customers.

Outputs: outputs/model_params.csv (from models.py), outputs/calibration_holdout.csv,
         outputs/sanity_checks.csv
"""
import warnings

import numpy as np
import pandas as pd
from lifetimes import BetaGeoFitter
from scipy import stats

from common import OUTPUTS, PENALIZER
from rfm_cohort import invoice_level, load_clean

warnings.filterwarnings("ignore")


def expected_purchases(bgf, t, x, tx, T):
    """BG/NBD conditional expected purchases in the next t weeks (Fader, Hardie & Lee 2005,
    eq. 10) - the SAME formula as lifetimes' conditional_expected_number_of_purchases_up_to_time,
    evaluated without taking log(hyp2f1). lifetimes 0.11.3 returns NaN when a+b+x-1 < 0
    (b < 1 and x = 0) because hyp2f1 is then negative and it takes its log; the product with the
    equally negative (a+b+x-1)/(a-1) factor is still a valid positive number."""
    from scipy.special import hyp2f1
    r, alpha, a, b = (bgf.params_[k] for k in ("r", "alpha", "a", "b"))
    x, tx, T = (np.asarray(v, dtype=float) for v in (x, tx, T))
    hyp = hyp2f1(r + x, b + x, a + b + x - 1, t / (alpha + T + t))
    first = (a + b + x - 1) / (a - 1)
    second = 1 - hyp * ((alpha + T) / (alpha + t + T)) ** (r + x)
    denom = 1 + (x > 0) * (a / (b + x - 1)) * ((alpha + T) / (alpha + tx)) ** (r + x)
    return first * second / denom


def calibration_holdout(inv: pd.DataFrame):
    start, end = inv["InvoiceDate"].min(), inv["InvoiceDate"].max()
    split = (start + (end - start) / 2).normalize()
    end_day = end.normalize()
    inv = inv.assign(Day=inv["InvoiceDate"].dt.normalize())
    cal = inv[inv["Day"] < split]
    hold = inv[inv["Day"] >= split]

    c = (cal.groupby("Customer ID")
            .agg(first=("Day", "min"), last=("Day", "max"), n=("Invoice", "nunique")))
    c["frequency_cal"] = c["n"] - 1
    c["recency_cal"] = (c["last"] - c["first"]).dt.days / 7.0
    c["T_cal"] = (split - c["first"]).dt.days / 7.0
    c["actual_holdout"] = hold.groupby("Customer ID")["Invoice"].nunique()
    c["actual_holdout"] = c["actual_holdout"].fillna(0)
    horizon = (end_day - split).days / 7.0

    bgf = BetaGeoFitter(penalizer_coef=PENALIZER)
    bgf.fit(c["frequency_cal"], c["recency_cal"], c["T_cal"])
    lib = bgf.conditional_expected_number_of_purchases_up_to_time(
        horizon, c["frequency_cal"], c["recency_cal"], c["T_cal"])
    mine = expected_purchases(bgf, horizon, c["frequency_cal"], c["recency_cal"], c["T_cal"])
    ok = np.isfinite(lib)
    assert np.allclose(lib[ok], mine[ok], rtol=1e-9), "formula must equal lifetimes where finite"
    c["predicted_holdout"] = mine
    lib_nan = int((~ok).sum())

    bins = [-1, 0, 1, 2, 4, 9, 10_000]
    labels = ["0", "1", "2", "3-4", "5-9", "10+"]
    c["group"] = pd.cut(c["frequency_cal"], bins=bins, labels=labels)
    tab = (c.groupby("group", observed=True)
             .agg(customers=("n", "size"),
                  avg_actual=("actual_holdout", "mean"),
                  avg_predicted=("predicted_holdout", "mean"),
                  total_actual=("actual_holdout", "sum"),
                  total_predicted=("predicted_holdout", "sum"))
             .reset_index().rename(columns={"group": "calibration_repeat_purchases"}))
    tab["error_pct"] = 100 * (tab["total_predicted"] - tab["total_actual"]) / tab["total_actual"]
    total = pd.DataFrame([{
        "calibration_repeat_purchases": "ALL", "customers": len(c),
        "avg_actual": c["actual_holdout"].mean(), "avg_predicted": c["predicted_holdout"].mean(),
        "total_actual": c["actual_holdout"].sum(), "total_predicted": c["predicted_holdout"].sum(),
        "error_pct": 100 * (c["predicted_holdout"].sum() - c["actual_holdout"].sum())
                     / c["actual_holdout"].sum()}])
    tab = pd.concat([tab, total], ignore_index=True)
    info = {
        "split_date": split.date().isoformat(), "holdout_weeks": round(horizon, 2),
        "cal_params": bgf.params_.to_dict(), "lifetimes_nan": lib_nan,
        "customer_mae": float((c["predicted_holdout"] - c["actual_holdout"]).abs().mean()),
        "customer_corr": float(np.corrcoef(c["predicted_holdout"], c["actual_holdout"])[0, 1]),
    }
    return tab, info


def horizon_check():
    """(d) What the CLV `time` argument means. lifetimes' customer_lifetime_value() treats `time`
    as MONTHS (it steps 4.345 weeks per month when freq="W") and discount_rate as per month.
    The project's metric uses time=26, i.e. ~113 weeks. This compares it with time=6 (~26 weeks)
    and with the historical spend rate of the same customers."""
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    c = pd.read_csv(OUTPUTS / "customer_model.csv")
    rep = c[c["frequency"] > 0]
    bgf = BetaGeoFitter(penalizer_coef=PENALIZER).fit(c["frequency"], c["recency"], c["T"])
    ggf = GammaGammaFitter(penalizer_coef=PENALIZER).fit(rep["frequency"], rep["AverageOrderValue"])
    v6 = ggf.customer_lifetime_value(bgf, rep["frequency"], rep["recency"], rep["T"],
                                     rep["AverageOrderValue"], time=6, freq="W", discount_rate=0.01)
    v6 = pd.Series(v6.values, index=rep.index)
    q25, q50, q75 = v6.quantile([0.25, 0.5, 0.75])
    b = (v6 >= q25).astype(int) + (v6 >= q50).astype(int) + (v6 >= q75).astype(int)
    seg6 = b.map(dict(enumerate(["Low CLV", "Mid-low CLV", "Mid-high CLV", "High CLV"])))
    champ6 = (rep["RFM_Segment"] == "Champions") & (seg6 == "High CLV")
    weeks_hist = (pd.Timestamp("2011-12-09") - pd.Timestamp("2009-12-01")).days / 7
    rows = [
        ("Project metric PredictedCLV_26w: time=26, freq='W' (lifetimes horizon = 26 x 4.345 weeks)",
         rep["PredictedCLV_26w"].sum()),
        ("Same model, time=6 (~26.1 weeks) total CLV", v6.sum()),
        ("Same model, time=6: mean / median CLV", f"{v6.mean():.2f} / {v6.median():.2f}"),
        ("Same model, time=6: Champions | High CLV customers", int(champ6.sum())),
        ("Same model, time=6: Champions | High CLV predicted CLV", v6[champ6].sum()),
        ("Same model, time=6: customers whose CLV quartile changes", int((seg6 != rep["CLV_Segment"]).sum())),
        ("Spearman rank corr between time=26 and time=6 CLV",
         round(stats.spearmanr(v6, rep["PredictedCLV_26w"]).correlation, 5)),
        ("Repeat customers' historical revenue per 26 weeks (2009-12-01..2011-12-09)",
         rep["Monetary"].sum() / weeks_hist * 26),
    ]
    out = pd.DataFrame(rows, columns=["Check", "Value"])
    out.to_csv(OUTPUTS / "clv_horizon_check.csv", index=False)
    print("\n(d) CLV horizon check")
    print(out.to_string(index=False))


def main():
    horizon_check()
    inv = invoice_level(load_clean())
    params = pd.read_csv(OUTPUTS / "model_params.csv")
    print("(a) Fitted parameters (full data)")
    print(params.to_string(index=False))

    tab, info = calibration_holdout(inv)
    tab.round(3).to_csv(OUTPUTS / "calibration_holdout.csv", index=False)
    print(f"\n(b) Calibration/holdout: fit before {info['split_date']}, predict next "
          f"{info['holdout_weeks']} weeks")
    print(tab.round(2).to_string(index=False))
    print("calibration-fit params:", {k: round(v, 4) for k, v in info["cal_params"].items()},
          f"| lifetimes returned NaN for {info['lifetimes_nan']} zero-repeat customers "
          "(evaluated with the same formula without log)")
    print(f"customer-level MAE {info['customer_mae']:.2f} purchases; "
          f"correlation(predicted, actual) {info['customer_corr']:.3f}")

    cm = pd.read_csv(OUTPUTS / "customer_model.csv")
    rep = cm[cm["frequency"] > 0]
    pear = rep["frequency"].corr(rep["AverageOrderValue"])
    spear = stats.spearmanr(rep["frequency"], rep["AverageOrderValue"]).correlation
    print(f"\n(c) Repeat customers: n={len(rep)}; corr(frequency, AOV) Pearson {pear:.3f}, "
          f"Spearman {spear:.3f}")

    rows = [(f"BG/NBD {k}", v) for k, v in zip(params.Parameter[params.Model == "BG/NBD"],
                                                params.Value[params.Model == "BG/NBD"])]
    rows += [(f"Gamma-Gamma {k}", v) for k, v in
             zip(params.Parameter[params.Model == "Gamma-Gamma"],
                 params.Value[params.Model == "Gamma-Gamma"])]
    rows += [("Calibration split date", info["split_date"]),
             ("Holdout weeks", info["holdout_weeks"]),
             *[(f"Calibration-fit BG/NBD {k}", round(v, 6)) for k, v in info["cal_params"].items()],
             ("Calibration customers where lifetimes returned NaN (recomputed)", info["lifetimes_nan"]),
             ("Holdout total actual repeat purchases", tab.iloc[-1]["total_actual"]),
             ("Holdout total predicted repeat purchases", round(tab.iloc[-1]["total_predicted"], 1)),
             ("Holdout aggregate error pct", round(tab.iloc[-1]["error_pct"], 2)),
             ("Holdout customer-level MAE", round(info["customer_mae"], 3)),
             ("Holdout corr(predicted, actual)", round(info["customer_corr"], 3)),
             ("Repeat customers for independence check", len(rep)),
             ("Pearson corr(frequency, AOV)", round(pear, 3)),
             ("Spearman corr(frequency, AOV)", round(spear, 3))]
    pd.DataFrame(rows, columns=["Check", "Value"]).to_csv(OUTPUTS / "sanity_checks.csv", index=False)


if __name__ == "__main__":
    main()
