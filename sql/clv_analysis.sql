-- =====================================================================
-- clv_analysis.sql  -  SQL layer for the Online Retail II CLV project
-- Engine: SQLite (Python standard-library sqlite3), SQLite >= 3.25 for
--         window functions.
-- Tables (created by src/run_sql.py):
--   transactions(invoice, stock_code, description, quantity, invoice_date,
--                price, customer_id, country, revenue)   -- cleaned rows
--   customer_clv(customer_id, predicted_clv_26w, clv_segment)  -- model output
-- Each query starts with a "-- name: <query_name>" line; run_sql.py splits
-- the file on those markers and writes outputs/sql/<query_name>.csv.
-- =====================================================================


-- name: setup_views
-- One row per (customer, invoice): an invoice is ONE purchase, not each product line.
DROP VIEW IF EXISTS v_invoices;
CREATE VIEW v_invoices AS
SELECT customer_id,
       invoice,
       MIN(invoice_date) AS invoice_date,
       SUM(revenue)      AS revenue
FROM transactions
GROUP BY customer_id, invoice;

-- One row per customer with raw R, F, M inputs.
DROP VIEW IF EXISTS v_customer_base;
CREATE VIEW v_customer_base AS
WITH snapshot AS (
    SELECT DATE(MAX(invoice_date)) AS snapshot_date FROM transactions
)
SELECT i.customer_id,
       MIN(i.invoice_date)                                   AS first_purchase,
       MAX(i.invoice_date)                                   AS last_purchase,
       COUNT(DISTINCT i.invoice)                             AS frequency,
       SUM(i.revenue)                                        AS monetary,
       CAST(JULIANDAY(s.snapshot_date)
            - JULIANDAY(DATE(MAX(i.invoice_date))) AS INTEGER) AS recency_days
FROM v_invoices i
CROSS JOIN snapshot s
GROUP BY i.customer_id;


-- name: customer_rfm
-- Quintile scores that reproduce pandas  rank(method="first") + qcut(q=5)  EXACTLY.
--   * ROW_NUMBER() ordered by (value, customer_id) = pandas rank(method="first") on a
--     table sorted by Customer ID (ties broken by Customer ID).
--   * pandas qcut on ranks 1..n puts bin edges at 1 + k*(n-1)/5 (k = 1..4), bins are
--     right-closed. NTILE(5) instead makes bins of 1176,1176,1176,1175,1175 customers,
--     which differs from qcut's 1176,1175,1176,1175,1176 - so we compute the edges.
--     ntile_* columns are kept only to show that difference (see run_sql.py output).
WITH ranked AS (
    SELECT b.*,
           COUNT(*)     OVER ()                                        AS n,
           ROW_NUMBER() OVER (ORDER BY recency_days, customer_id)      AS rn_r,
           ROW_NUMBER() OVER (ORDER BY frequency,    customer_id)      AS rn_f,
           ROW_NUMBER() OVER (ORDER BY ROUND(monetary, 6), customer_id) AS rn_m,
           NTILE(5)     OVER (ORDER BY recency_days, customer_id)      AS ntile_r_raw,
           NTILE(5)     OVER (ORDER BY frequency,    customer_id)      AS ntile_f,
           NTILE(5)     OVER (ORDER BY ROUND(monetary, 6), customer_id) AS ntile_m
    FROM v_customer_base b
),
bucketed AS (
    SELECT *,
           CASE WHEN rn_r <= 1 + 1*(n-1)/5.0 THEN 1 WHEN rn_r <= 1 + 2*(n-1)/5.0 THEN 2
                WHEN rn_r <= 1 + 3*(n-1)/5.0 THEN 3 WHEN rn_r <= 1 + 4*(n-1)/5.0 THEN 4
                ELSE 5 END AS r_bucket,
           CASE WHEN rn_f <= 1 + 1*(n-1)/5.0 THEN 1 WHEN rn_f <= 1 + 2*(n-1)/5.0 THEN 2
                WHEN rn_f <= 1 + 3*(n-1)/5.0 THEN 3 WHEN rn_f <= 1 + 4*(n-1)/5.0 THEN 4
                ELSE 5 END AS f_score,
           CASE WHEN rn_m <= 1 + 1*(n-1)/5.0 THEN 1 WHEN rn_m <= 1 + 2*(n-1)/5.0 THEN 2
                WHEN rn_m <= 1 + 3*(n-1)/5.0 THEN 3 WHEN rn_m <= 1 + 4*(n-1)/5.0 THEN 4
                ELSE 5 END AS m_score
    FROM ranked
)
SELECT customer_id,
       recency_days,
       frequency,
       ROUND(monetary, 2)           AS monetary,
       6 - r_bucket                 AS r_score,      -- reversed: 5 = most recent
       f_score,
       m_score,
       6 - ntile_r_raw              AS ntile_r,
       ntile_f,
       ntile_m
FROM bucketed
ORDER BY customer_id;


-- name: rfm_segments
-- Segment rules, applied in this order (first match wins).
-- NOTE: "At-risk loyal" uses F >= 3 to match the reference outputs (clv_project.py says F >= 4).
WITH scores AS (
    SELECT * FROM rfm_scores          -- table materialised by run_sql.py from customer_rfm
)
SELECT customer_id, r_score, f_score, m_score,
       CASE
           WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
           WHEN r_score <= 2 AND f_score >= 3                  THEN 'At-risk loyal'
           WHEN r_score >= 4 AND f_score <= 2                  THEN 'New / promising'
           WHEN r_score <= 2 AND f_score <= 2                  THEN 'Hibernating'
           ELSE 'Core customers'
       END AS rfm_segment
FROM scores
ORDER BY customer_id;


-- name: cohort_retention
-- Cohort = month of first purchase. CohortIndex 1 = the first month.
WITH first_month AS (
    SELECT customer_id, STRFTIME('%Y-%m', MIN(invoice_date)) AS cohort_month
    FROM v_invoices
    GROUP BY customer_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM first_month
    GROUP BY cohort_month
),
activity AS (
    SELECT f.cohort_month,
           (CAST(STRFTIME('%Y', i.invoice_date) AS INTEGER)
              - CAST(SUBSTR(f.cohort_month, 1, 4) AS INTEGER)) * 12
         + (CAST(STRFTIME('%m', i.invoice_date) AS INTEGER)
              - CAST(SUBSTR(f.cohort_month, 6, 2) AS INTEGER)) + 1 AS cohort_index,
           i.customer_id
    FROM v_invoices i
    JOIN first_month f ON f.customer_id = i.customer_id
)
SELECT a.cohort_month,
       a.cohort_index,
       s.cohort_size,
       COUNT(DISTINCT a.customer_id)                         AS active_customers,
       COUNT(DISTINCT a.customer_id) * 1.0 / s.cohort_size   AS retention_rate
FROM activity a
JOIN cohort_size s ON s.cohort_month = a.cohort_month
GROUP BY a.cohort_month, a.cohort_index, s.cohort_size
ORDER BY a.cohort_month, a.cohort_index;


-- name: avg_retention
-- Average retention across cohorts at month+1 / +3 / +6 (CohortIndex 2 / 4 / 7).
SELECT cohort_index - 1          AS months_after_first,
       COUNT(*)                  AS cohorts_observed,
       AVG(retention_rate)       AS avg_retention_rate
FROM cohort_retention
WHERE cohort_index IN (2, 4, 7)
GROUP BY cohort_index
ORDER BY cohort_index;


-- name: monthly_revenue
-- Monthly revenue, running total and month-over-month change with LAG.
WITH monthly AS (
    SELECT STRFTIME('%Y-%m', invoice_date) AS year_month,
           SUM(revenue)                    AS revenue,
           COUNT(DISTINCT invoice)         AS orders,
           COUNT(DISTINCT customer_id)     AS customers
    FROM transactions
    GROUP BY year_month
)
SELECT year_month,
       ROUND(revenue, 2)                                                   AS revenue,
       orders,
       customers,
       ROUND(SUM(revenue) OVER (ORDER BY year_month
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2)
                                                                           AS running_revenue,
       ROUND(revenue - LAG(revenue) OVER (ORDER BY year_month), 2)         AS mom_change,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY year_month))
             / LAG(revenue) OVER (ORDER BY year_month), 2)                 AS mom_change_pct
FROM monthly
ORDER BY year_month;


-- name: top10_customers
-- Top 10 customers by historical revenue, ranked with RANK().
WITH cust AS (
    SELECT customer_id,
           SUM(revenue)            AS revenue,
           COUNT(DISTINCT invoice) AS orders
    FROM transactions
    GROUP BY customer_id
),
ranked AS (
    SELECT customer_id, revenue, orders,
           RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
           revenue * 100.0 / SUM(revenue) OVER () AS share_of_revenue_pct
    FROM cust
)
SELECT customer_id, ROUND(revenue, 2) AS revenue, orders, revenue_rank,
       ROUND(share_of_revenue_pct, 2) AS share_of_revenue_pct
FROM ranked
WHERE revenue_rank <= 10
ORDER BY revenue_rank;


-- name: rfm_segment_summary
-- Customers, revenue and share of revenue per RFM segment.
WITH seg AS (
    SELECT s.rfm_segment, b.customer_id, b.monetary
    FROM rfm_segments s
    JOIN v_customer_base b ON b.customer_id = s.customer_id
)
SELECT rfm_segment,
       COUNT(*)                                             AS customers,
       ROUND(SUM(monetary), 2)                              AS revenue,
       ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS share_of_revenue_pct,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)   AS share_of_customers_pct
FROM seg
GROUP BY rfm_segment
ORDER BY revenue DESC;


-- name: combined_segment_summary
-- RFM segment x CLV segment (CLV from the Python model, loaded as customer_clv).
SELECT s.rfm_segment,
       c.clv_segment,
       COUNT(*)                                 AS customers,
       ROUND(SUM(b.monetary), 2)                AS historical_revenue,
       ROUND(COALESCE(SUM(c.predicted_clv_26w), 0), 2) AS predicted_clv_26w,
       ROUND(100.0 * SUM(b.monetary) / SUM(SUM(b.monetary)) OVER (), 2) AS share_of_revenue_pct
FROM rfm_segments s
JOIN v_customer_base b ON b.customer_id = s.customer_id
JOIN customer_clv   c ON c.customer_id = s.customer_id
GROUP BY s.rfm_segment, c.clv_segment
ORDER BY predicted_clv_26w DESC;
