"""Step 1: clean the raw transactions and write a cleaning log.

Rules (methodology):
  1. trim text fields; parse InvoiceDate, Quantity, Price, Customer ID
  2. drop rows with missing Customer ID
  3. drop cancellation invoices (Invoice starts with "C")
  4. keep Quantity > 0 and Price > 0
  5. detect exact duplicate rows but KEEP them (the source does not prove they are errors)
  6. Revenue = Quantity x Price

Outputs:
  data/fact_transactions_clean.csv   (~80 MB, git-ignored, regenerate with this script)
  outputs/fact_cleaning_log.csv
  outputs/clean_summary.csv
"""
import pandas as pd

from common import CLEAN_CSV, OUTPUTS, RAW_CSV

TEXT_COLS = ["Invoice", "StockCode", "Description", "Country"]


def load_raw(path=RAW_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"Invoice": str, "StockCode": str, "Description": str,
                                    "Country": str})


def clean(raw: pd.DataFrame):
    log = []

    def add(step, before, after, rule):
        log.append({"step": step, "rows_before": before, "rows_after": after,
                    "rows_removed": before - after, "rule": rule})

    df = raw.copy()
    n = len(df)
    add("raw_rows", n, n, "Two workbook sheets concatenated")

    # 1. type coercion and trimming
    for c in TEXT_COLS:
        df[c] = df[c].str.strip()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["Customer ID"] = pd.to_numeric(df["Customer ID"], errors="coerce")
    add("type_coercion", n, len(df), "Parsed dates/numerics; trimmed text")

    before = len(df)
    df = df[df["InvoiceDate"].notna()]
    add("valid_invoice_date", before, len(df), "Removed unparseable InvoiceDate")

    # 2. known customer
    before = len(df)
    df = df[df["Customer ID"].notna()]
    add("known_customer", before, len(df), "Removed rows without Customer ID")

    # 3. cancellations
    before = len(df)
    df = df[~df["Invoice"].str.startswith("C")]
    add("exclude_cancellations", before, len(df), "Removed invoices with Invoice beginning C")

    # 4. positive quantity and price
    before = len(df)
    df = df[(df["Quantity"] > 0) & (df["Price"] > 0)].copy()
    add("positive_sales", before, len(df), "Kept Quantity > 0 and Price > 0")

    # 5. duplicates: detect, do not remove
    dup = int(df.duplicated().sum())
    add("duplicate_handling", len(df), len(df),
        f"Exact duplicates detected={dup}; retained to avoid deleting potentially valid "
        "repeated line items")

    # 6. revenue and helper columns
    df["Customer ID"] = df["Customer ID"].astype("int64")
    df["Revenue"] = df["Quantity"] * df["Price"]
    df["InvoiceMonth"] = df["InvoiceDate"].dt.strftime("%Y-%m")
    df = df.reset_index(drop=True)
    return df, pd.DataFrame(log), dup


def main():
    raw = load_raw()
    df, log, dup = clean(raw)
    df.to_csv(CLEAN_CSV, index=False)
    log.to_csv(OUTPUTS / "fact_cleaning_log.csv", index=False)

    summary = pd.DataFrame([
        ("Raw rows", len(raw)),
        ("Usable transaction rows", len(df)),
        ("Usable customers", df["Customer ID"].nunique()),
        ("Usable invoices", df["Invoice"].nunique()),
        ("Exact duplicates detected and retained", dup),
        ("Historical revenue", df["Revenue"].sum()),
        ("Min InvoiceDate", df["InvoiceDate"].min()),
        ("Max InvoiceDate", df["InvoiceDate"].max()),
        ("RFM snapshot date", df["InvoiceDate"].max().normalize().date()),
    ], columns=["Metric", "Value"])
    summary.to_csv(OUTPUTS / "clean_summary.csv", index=False)
    print(log.to_string(index=False))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
