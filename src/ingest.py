"""Step 0: read the UCI Online Retail II workbook ONCE and cache it as CSV.

Reading 1,067,371 rows from xlsx takes several minutes; every later step
reads data/online_retail_II_raw.csv instead.

Usage:
    python src/ingest.py --xlsx data/online_retail_II.xlsx
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ["Year 2009-2010", "Year 2010-2011"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(ROOT / "data" / "online_retail_II.xlsx"))
    ap.add_argument("--out", default=str(ROOT / "data" / "online_retail_II_raw.csv"))
    args = ap.parse_args()

    frames = []
    for sheet in SHEETS:
        # Invoice and StockCode mix numbers and text (e.g. "C489449"), so read as text.
        part = pd.read_excel(args.xlsx, sheet_name=sheet,
                             dtype={"Invoice": str, "StockCode": str})
        print(f"{sheet}: {part.shape}")
        frames.append(part)
    raw = pd.concat(frames, ignore_index=True)
    print("Combined raw shape:", raw.shape)
    raw.to_csv(args.out, index=False)
    print("Saved", args.out)


if __name__ == "__main__":
    main()
