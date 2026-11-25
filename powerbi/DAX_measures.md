# DAX measures

Create a blank table called `_Measures` (Home → Enter data → load an empty table) and add
these measures to it. Table and column names match the CSVs in this folder.
Every measure was written for the model described in `BUILD_GUIDE.md`.

## Core sales measures (on `fact_transactions_clean`)

```DAX
Total Revenue =
SUM ( fact_transactions_clean[Revenue] )

Customers =
DISTINCTCOUNT ( fact_transactions_clean[Customer ID] )

Orders =
DISTINCTCOUNT ( fact_transactions_clean[Invoice] )

AOV =
DIVIDE ( [Total Revenue], [Orders] )

Revenue per Customer =
DIVIDE ( [Total Revenue], [Customers] )
```

Expected totals with no filters: Total Revenue 17,743,429.18 · Customers 5,878 ·
Orders 36,969 · AOV ≈ 479.95 (17,743,429.18 ÷ 36,969).

## Customer / CLV measures (on `dim_customer_rfm_clv`)

```DAX
Customer Count =
COUNTROWS ( dim_customer_rfm_clv )

Historical Revenue (customers) =
SUM ( dim_customer_rfm_clv[Monetary] )

Predicted CLV 26w =
SUM ( dim_customer_rfm_clv[PredictedCLV_26w] )
-- 26-week model forecast for repeat customers only; single-purchase customers are blank.

Avg Predicted CLV 26w =
AVERAGE ( dim_customer_rfm_clv[PredictedCLV_26w] )   -- ignores blanks: 4,019.85

Median Predicted CLV 26w =
MEDIAN ( dim_customer_rfm_clv[PredictedCLV_26w] )    -- 1,511.36

Modeled Customers =
CALCULATE ( [Customer Count], dim_customer_rfm_clv[CLV_ModelStatus] = "Modeled" )   -- 4,255

Champions Count =
CALCULATE ( [Customer Count], dim_customer_rfm_clv[RFM_Segment] = "Champions" )     -- 1,292

Champions High CLV Count =
CALCULATE (
    [Customer Count],
    dim_customer_rfm_clv[RFM_Segment] = "Champions",
    dim_customer_rfm_clv[CLV_Segment] = "High CLV"
)                                                                                   -- 785

Champions High CLV Predicted CLV =
CALCULATE (
    [Predicted CLV 26w],
    dim_customer_rfm_clv[RFM_Segment] = "Champions",
    dim_customer_rfm_clv[CLV_Segment] = "High CLV"
)                                                                                   -- 10,896,459.63

Avg Probability Alive =
AVERAGE ( dim_customer_rfm_clv[ProbabilityAlive] )
```

## Share measures

```DAX
Revenue Share of Total =
DIVIDE (
    [Historical Revenue (customers)],
    CALCULATE ( [Historical Revenue (customers)], ALL ( dim_customer_rfm_clv ) )
)
-- Put RFM_Segment (or CustomerSegment) on rows; format as %.

Predicted CLV Share of Total =
DIVIDE (
    [Predicted CLV 26w],
    CALCULATE ( [Predicted CLV 26w], ALL ( dim_customer_rfm_clv ) )
)

Customer Share of Total =
DIVIDE ( [Customer Count], CALCULATE ( [Customer Count], ALL ( dim_customer_rfm_clv ) ) )
```

## Retention measures (on `fact_cohort_retention`)

```DAX
Retention Rate =
DIVIDE (
    SUM ( fact_cohort_retention[ActiveCustomers] ),
    SUM ( fact_cohort_retention[CohortSize] )
)
-- In a matrix with CohortMonth on rows and CohortIndex on columns, each cell is that
-- cohort's retention for that month.

Avg Cohort Retention =
AVERAGEX ( fact_cohort_retention, fact_cohort_retention[RetentionRate] )
-- Simple mean across cohorts (the method used in this project).

Retention Month+1 =
CALCULATE ( [Avg Cohort Retention], fact_cohort_retention[CohortIndex] = 2 )   -- 21.17%

Retention Month+3 =
CALCULATE ( [Avg Cohort Retention], fact_cohort_retention[CohortIndex] = 4 )   -- 21.62%

Retention Month+6 =
CALCULATE ( [Avg Cohort Retention], fact_cohort_retention[CohortIndex] = 7 )   -- 17.82%
```

Note: `Retention Rate` (sum of active / sum of cohort size) is size-weighted, so on a
total row it will NOT equal `Avg Cohort Retention` (an unweighted mean of cohort rates). The
published 21.17 / 21.62 / 17.82 % figures are the unweighted means.

## Time intelligence (needs the `dim_date` relationship)

```DAX
Revenue MoM % =
VAR Curr = [Total Revenue]
VAR Prev = CALCULATE ( [Total Revenue], DATEADD ( dim_date[Date], -1, MONTH ) )
RETURN DIVIDE ( Curr - Prev, Prev )

Revenue Running Total =
CALCULATE (
    [Total Revenue],
    FILTER ( ALL ( dim_date[Date] ), dim_date[Date] <= MAX ( dim_date[Date] ) )
)
```

Mark `dim_date` as a date table (Table tools → Mark as date table → `Date`).
