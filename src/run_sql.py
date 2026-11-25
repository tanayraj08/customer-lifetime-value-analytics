"""Step 2: SQL layer.

1. Loads the cleaned transactions into SQLite with the standard-library sqlite3 + csv modules.
2. Runs every named query in sql/clv_analysis.sql and writes outputs/sql/<name>.csv.
3. Checks that SQL results equal the pandas results (RFM scores, segments, cohort retention,
   segment counts) and writes outputs/sql_parity_check.csv.

Run after src/clean.py, src/rfm_cohort.py and src/models.py.
"""
import csv
import re
import sqlite3

import pandas as pd

from common import CLEAN_CSV, OUTPUTS, SQL_DIR, SQLITE_DB

SQL_OUT = OUTPUTS / "sql"
SQL_OUT.mkdir(exist_ok=True)
# Query results that later queries read from, so they are saved as tables.
MATERIALISE = {"customer_rfm": "rfm_scores", "rfm_segments": "rfm_segments",
               "cohort_retention": "cohort_retention"}


def load_db(con: sqlite3.Connection):
    con.executescript("""
        DROP TABLE IF EXISTS transactions;
        CREATE TABLE transactions (
            invoice TEXT, stock_code TEXT, description TEXT, quantity INTEGER,
            invoice_date TEXT, price REAL, customer_id INTEGER, country TEXT, revenue REAL);
    """)
    with open(CLEAN_CSV, newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        con.executemany(
            "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?)",
            ((r["Invoice"], r["StockCode"], r["Description"], int(r["Quantity"]),
              r["InvoiceDate"], float(r["Price"]), int(r["Customer ID"]), r["Country"],
              float(r["Revenue"])) for r in rows))
    con.execute("CREATE INDEX idx_tx_cust ON transactions(customer_id, invoice)")

    # CLV model output (from Python) so SQL can build the combined segment summary
    con.execute("DROP TABLE IF EXISTS customer_clv")
    con.execute("CREATE TABLE customer_clv (customer_id INTEGER PRIMARY KEY, "
                "predicted_clv_26w REAL, clv_segment TEXT)")
    with open(OUTPUTS / "customer_model.csv", newline="", encoding="utf-8") as f:
        con.executemany("INSERT INTO customer_clv VALUES (?,?,?)",
                        ((int(r["Customer ID"]),
                          float(r["PredictedCLV_26w"]) if r["PredictedCLV_26w"] else None,
                          r["CLV_Segment"]) for r in csv.DictReader(f)))
    con.commit()


def split_queries(text: str):
    parts = re.split(r"^-- name:\s*(\S+)\s*$", text, flags=re.M)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def run_all(con):
    results = {}
    for name, body in split_queries((SQL_DIR / "clv_analysis.sql").read_text()):
        if name == "setup_views":
            con.executescript(body)
            continue
        df = pd.read_sql_query(body, con)
        df.to_csv(SQL_OUT / f"{name}.csv", index=False)
        results[name] = df
        if name in MATERIALISE:
            df.to_sql(MATERIALISE[name], con, if_exists="replace", index=False)
        print(f"{name:26s} {len(df):>6} rows")
    return results


def parity(results):
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    py = pd.read_csv(OUTPUTS / "customer_model.csv").drop(columns=["frequency", "recency", "T"])
    sq = results["customer_rfm"].merge(results["rfm_segments"][["customer_id", "rfm_segment"]],
                                       on="customer_id")
    m = py.merge(sq, left_on="Customer ID", right_on="customer_id")
    add("customer count", len(m) == len(py) == len(sq), f"pandas {len(py)}, sql {len(sq)}")
    for p, s in [("RecencyDays", "recency_days"), ("Frequency", "frequency"),
                 ("R_Score", "r_score"), ("F_Score", "f_score"), ("M_Score", "m_score")]:
        diff = int((m[p] != m[s]).sum())
        add(f"{p} equal", diff == 0, f"{diff} customers differ")
    mon = (m["Monetary"].round(2) - m["monetary"]).abs().max()
    add("Monetary equal (2dp)", mon < 0.006, f"max abs diff {mon:.4f}")
    diff = int((m["RFM_Segment"] != m["rfm_segment"]).sum())
    add("RFM_Segment equal", diff == 0, f"{diff} customers differ")
    for p, s in [("R_Score", "ntile_r"), ("F_Score", "ntile_f"), ("M_Score", "ntile_m")]:
        diff = int((m[p] != m[s]).sum())
        checks.append({"check": f"(info) plain NTILE(5) vs pandas {p}", "result": "INFO",
                       "detail": f"{diff} customers would differ if NTILE(5) were used"})

    seg_py = py["RFM_Segment"].value_counts().sort_index()
    seg_sq = results["rfm_segment_summary"].set_index("rfm_segment")["customers"].sort_index()
    add("segment counts equal", seg_py.equals(seg_sq.rename("count").rename_axis("RFM_Segment")),
        "; ".join(f"{k}={v}" for k, v in seg_sq.items()))

    cr_py = pd.read_csv(OUTPUTS / "fact_cohort_retention.csv")
    cr_sq = results["cohort_retention"]
    j = cr_py.merge(cr_sq, left_on=["CohortMonth", "CohortIndex"],
                    right_on=["cohort_month", "cohort_index"], how="outer", indicator=True)
    both = (j["_merge"] == "both").all()
    md = (j["RetentionRate"] - j["retention_rate"]).abs().max()
    add("cohort retention equal", both and md < 1e-12 and
        (j["ActiveCustomers"] == j["active_customers"]).all(),
        f"{len(cr_sq)} cohort-month rows, max retention diff {md:.2e}")

    ar = results["avg_retention"]
    rs = pd.read_csv(OUTPUTS / "retention_summary.csv")["Value"].values
    md = abs(ar["avg_retention_rate"].values - rs).max()
    add("avg retention m+1/m+3/m+6 equal", md < 1e-12,
        ", ".join(f"m+{a}: {b:.4%}" for a, b in zip(ar.months_after_first, ar.avg_retention_rate)))

    fs = pd.read_csv(OUTPUTS / "fact_segment_summary.csv")
    cs = results["combined_segment_summary"]
    j = fs.merge(cs, left_on=["RFM_Segment", "CLV_Segment"],
                 right_on=["rfm_segment", "clv_segment"])
    ok = len(j) == len(fs) == len(cs) and (j["Customers"] == j["customers"]).all() and \
        (j["PredictedCLV26w"].round(2) - j["predicted_clv_26w"]).abs().max() < 0.01
    add("combined segment summary equal", ok, f"{len(cs)} segment rows")
    return pd.DataFrame(checks)


def main():
    if SQLITE_DB.exists():
        SQLITE_DB.unlink()
    con = sqlite3.connect(SQLITE_DB)
    load_db(con)
    print("Loaded", con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
          "rows into", SQLITE_DB.name)
    results = run_all(con)
    report = parity(results)
    report.to_csv(OUTPUTS / "sql_parity_check.csv", index=False)
    print(report.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
