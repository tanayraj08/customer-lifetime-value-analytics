"""Shared paths and constants used by every step of the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"            # large / raw files (git-ignored)
OUTPUTS = ROOT / "outputs"      # small CSVs and metrics (committed)
POWERBI = ROOT / "powerbi"      # Power BI star-schema tables (committed, except transactions)
DOCS = ROOT / "docs"            # chart PNGs and dashboard preview
SQL_DIR = ROOT / "sql"

RAW_CSV = DATA / "online_retail_II_raw.csv"
CLEAN_CSV = DATA / "fact_transactions_clean.csv"   # ~80 MB, git-ignored
SQLITE_DB = DATA / "retail.db"                      # git-ignored

# Modelling assumptions (documented in methodology)
PENALIZER = 0.001
CLV_TIME = 26  # lifetimes `time` argument (lifetimes counts it in months; see models.py)
DISCOUNT_RATE = 0.01  # passed to lifetimes, which applies it per MONTH-length period

SEPARATOR = " | "  # combined-segment separator used in the reference outputs
SINGLE_PURCHASE_LABEL = "Single-purchase / CLV not modeled"  # exact text in reference outputs
CLV_LABELS = ["Low CLV", "Mid-low CLV", "Mid-high CLV", "High CLV"]
RFM_ORDER = ["Champions", "At-risk loyal", "New / promising", "Core customers", "Hibernating"]

for _d in (DATA, OUTPUTS, POWERBI, DOCS):
    _d.mkdir(exist_ok=True)
