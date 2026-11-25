"""Run the whole pipeline in order, then verify.

    python run_all.py                       # uses data/online_retail_II.xlsx
    python run_all.py --xlsx path/to/online_retail_II.xlsx
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("Step 1  clean + cleaning log", "src/clean.py"),
    ("Step 3  RFM + cohorts (pandas)", "src/rfm_cohort.py"),
    ("Step 4  BG/NBD + Gamma-Gamma + CLV segments", "src/models.py"),
    ("Step 2  SQL layer + pandas parity check", "src/run_sql.py"),
    ("Step 5  model sanity checks", "src/sanity.py"),
    ("Step 6  charts", "src/charts.py"),
    ("Step 7  Power BI star schema", "src/export_powerbi.py"),
    ("Step 8  dashboard.html", "src/build_dashboard.py"),
    ("Headline facts for README", "src/headline_facts.py"),
    ("Step 9  verify", "verify.py"),
]


def run(label, script, *args):
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}", flush=True)
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / script), *args], check=True, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(ROOT / "data" / "online_retail_II.xlsx"))
    args = ap.parse_args()
    if not (ROOT / "data" / "online_retail_II_raw.csv").exists():
        run("Step 0  read xlsx once -> data/online_retail_II_raw.csv", "src/ingest.py", "--xlsx", args.xlsx)
    for label, script in STEPS:
        run(label, script)


if __name__ == "__main__":
    main()
