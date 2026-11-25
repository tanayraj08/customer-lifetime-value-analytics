"""Step 6: charts (matplotlib) -> docs/*.png"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

from common import DOCS, OUTPUTS, RFM_ORDER

BLUE = "#2a78d6"
GREY = "#b9b8b2"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e7e6e2", "#fcfcfb"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.titleweight": "bold", "axes.titlesize": 13,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
})
money = FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if abs(v) >= 1e6 else f"{v/1e3:.0f}K")


def monthly_revenue():
    m = pd.read_csv(OUTPUTS / "sql" / "monthly_revenue.csv")
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(m["year_month"], m["revenue"], color=BLUE, lw=2, marker="o", ms=4)
    ax.yaxis.set_major_formatter(money)
    ax.set_title("Monthly revenue (cleaned transactions)", loc="left")
    ax.set_ylabel("Revenue (dataset currency)")
    ax.tick_params(axis="x", rotation=60)
    ax.grid(axis="x", visible=False)
    last = m.iloc[-1]
    ax.annotate("Dec 2011 covers only\n1-9 Dec (data ends)", (len(m) - 1, last["revenue"]),
                xytext=(-110, 10), textcoords="offset points", color=INK2, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    peak = m.loc[m["revenue"].idxmax()]
    ax.annotate(f"Peak {peak['year_month']}: {peak['revenue']/1e6:.2f}M",
                (m.index[m['revenue'].idxmax()], peak["revenue"]), xytext=(-150, -5),
                textcoords="offset points", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(DOCS / "monthly_revenue.png", dpi=150)
    plt.close(fig)


def cohort_heatmap(max_index=13):
    r = pd.read_csv(OUTPUTS / "fact_cohort_retention.csv")
    p = r[(r["CohortIndex"] >= 2) & (r["CohortIndex"] <= max_index)].pivot(index="CohortMonth", columns="CohortIndex",
                                                values="RetentionRate")
    sizes = r.groupby("CohortMonth")["CohortSize"].first()
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    fig, ax = plt.subplots(figsize=(12, 9))
    # month +0 is always 100% by definition, so it is left out
    im = ax.imshow(p.values, cmap=cmap, vmin=0, vmax=0.45, aspect="auto")
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            v = p.values[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7.5,
                    color="white" if v > 0.28 else INK)
    ax.set_xticks(range(p.shape[1]), [f"+{c-1}" for c in p.columns])
    ax.set_yticks(range(p.shape[0]), [f"{c}  (n={sizes[c]})" for c in p.index])
    ax.grid(False)
    ax.set_xlabel("Months after first purchase")
    ax.set_title("Cohort retention: share of each first-purchase cohort active N months later\n(2009-12 includes customers active before the data starts)",
                 loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, format=FuncFormatter(lambda v, _: f"{v:.0%}"))
    cb.outline.set_visible(False)
    fig.tight_layout()
    fig.savefig(DOCS / "cohort_retention_heatmap.png", dpi=150)
    plt.close(fig)


def segment_clv():
    s = pd.read_csv(OUTPUTS / "fact_segment_summary.csv")
    s = s[s["PredictedCLV26w"] > 0].copy()
    s["label"] = s["RFM_Segment"] + " | " + s["CLV_Segment"]
    s = s.sort_values("PredictedCLV26w")
    fig, ax = plt.subplots(figsize=(11, 8))
    colors = [BLUE if l == "Champions | High CLV" else GREY for l in s["label"]]
    ax.barh(s["label"], s["PredictedCLV26w"], color=colors, height=0.7)
    for y, (v, n) in enumerate(zip(s["PredictedCLV26w"], s["Customers"])):
        ax.text(v, y, f"  {v/1e6:.2f}M  ({n} cust.)", va="center", fontsize=8.5, color=INK2)
    ax.xaxis.set_major_formatter(money)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, s["PredictedCLV26w"].max() * 1.25)
    ax.set_xlabel("Predicted 26-week CLV (model forecast, dataset currency)")
    ax.set_title("Predicted 26-week CLV by segment (repeat customers only)", loc="left")
    fig.tight_layout()
    fig.savefig(DOCS / "segment_predicted_clv.png", dpi=150)
    plt.close(fig)


def rfm_distribution():
    c = pd.read_csv(OUTPUTS / "customer_model.csv")
    g = c.groupby("RFM_Segment").agg(customers=("Customer ID", "size"),
                                     revenue=("Monetary", "sum")).reindex(RFM_ORDER)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, col, title, fmt in [
        (axes[0], "customers", "Customers by RFM segment", lambda v: f"{v:,.0f}"),
        (axes[1], "revenue", "Historical revenue by RFM segment", lambda v: f"{v/1e6:.1f}M")]:
        ax.bar(g.index, g[col], color=BLUE, width=0.6)
        for x, v in enumerate(g[col]):
            ax.text(x, v, fmt(v), ha="center", va="bottom", fontsize=9, color=INK2)
        ax.set_title(title, loc="left")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="x", visible=False)
    axes[1].yaxis.set_major_formatter(money)
    fig.tight_layout()
    fig.savefig(DOCS / "rfm_distribution.png", dpi=150)
    plt.close(fig)


def clv_distribution():
    c = pd.read_csv(OUTPUTS / "customer_model.csv")
    v = c["PredictedCLV_26w"].dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    bins = np.logspace(np.log10(max(v.min(), 1)), np.log10(v.max()), 50)
    ax.hist(v, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=0.8)
    ax.set_xscale("log")
    for q, lab, ha in [(v.median(), "median", "right"), (v.mean(), "mean", "left")]:
        ax.axvline(q, color=INK2, lw=1, ls="--")
        ax.text(q, ax.get_ylim()[1] * 0.95, f" {lab} {q:,.0f} " , color=INK2, fontsize=9, ha=ha)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlabel("Predicted 26-week CLV (log scale)")
    ax.set_ylabel("Customers")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Distribution of predicted 26-week CLV ({len(v):,} repeat customers)", loc="left")
    fig.tight_layout()
    fig.savefig(DOCS / "clv_distribution.png", dpi=150)
    plt.close(fig)


def main():
    monthly_revenue()
    cohort_heatmap()
    segment_clv()
    rfm_distribution()
    clv_distribution()
    print("Charts written to", DOCS)


if __name__ == "__main__":
    main()
