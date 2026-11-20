-- =============================================================================
-- 02_build_monthly.sql
-- Builds the 176-month panel from the raw staging tables.
-- Session variables set by the Python runner:
--   @start_month, @end_month   study window
--   @market_regime_end         last month of market-linked (daily revised) pricing
-- =============================================================================

-- ---------------------------------------------------------------- 1. daily calendar
-- A recursive CTE generates every day of the window (about 5,400 rows).
SET SESSION cte_max_recursion_depth = 10000;

INSERT INTO dim_calendar (cal_date, month_start)
WITH RECURSIVE days AS (
    SELECT CAST(@start_month AS DATE) AS cal_date
    UNION ALL
    SELECT cal_date + INTERVAL 1 DAY
    FROM days
    WHERE cal_date < LAST_DAY(@end_month)
)
SELECT cal_date,
       cal_date - INTERVAL (DAY(cal_date) - 1) DAY
FROM days;

-- ---------------------------------------------------------------- 2. monthly index
INSERT INTO dim_month (month_start, month_end, days_in_month, month_index, fiscal_year, pricing_regime)
SELECT month_start,
       LAST_DAY(month_start),
       DAY(LAST_DAY(month_start)),
       ROW_NUMBER() OVER (ORDER BY month_start),
       CASE WHEN MONTH(month_start) >= 4
            THEN CONCAT(YEAR(month_start), '-', RIGHT(YEAR(month_start) + 1, 2))
            ELSE CONCAT(YEAR(month_start) - 1, '-', RIGHT(YEAR(month_start), 2))
       END,
       CASE WHEN month_start <= @market_regime_end THEN 'market_linked' ELSE 'administered' END
FROM (SELECT DISTINCT month_start FROM dim_calendar) AS m;

-- ---------------------------------------------------------------- 3. monthly panel
-- Each source is brought to monthly frequency in its own CTE, then all three are
-- LEFT JOINed onto the month index (so a missing month shows up as NULL instead of
-- silently disappearing) and crude is converted to rupees per litre on the join.
INSERT INTO fuel_monthly (month_start, brent_usd_bbl, usdinr, crude_inr_litre, petrol_rsp,
                          fx_obs_days, petrol_days, petrol_changes)
WITH
-- Petrol prices are "valid from" records (fortnightly revisions before June 2017,
-- daily after). LEAD() turns each record into a validity spell [valid_from, valid_to].
petrol_spells AS (
    SELECT effective_date                                         AS valid_from,
           COALESCE(LEAD(effective_date) OVER w - INTERVAL 1 DAY,
                    effective_date)                               AS valid_to,
           rsp_inr_litre,
           LAG(rsp_inr_litre) OVER w                              AS prev_rsp
    FROM stg_petrol_delhi
    WINDOW w AS (ORDER BY effective_date)
),
-- Expand spells to one row per calendar day: the price actually charged that day.
petrol_daily AS (
    SELECT c.cal_date,
           c.month_start,
           s.rsp_inr_litre,
           (s.valid_from = c.cal_date AND s.rsp_inr_litre <> s.prev_rsp) AS is_change
    FROM dim_calendar AS c
    JOIN petrol_spells AS s
      ON c.cal_date BETWEEN s.valid_from AND s.valid_to
    WHERE s.valid_to >= @start_month
),
-- Day-weighted monthly average: a price in force for 20 days counts 20 times.
petrol_m AS (
    SELECT month_start,
           AVG(rsp_inr_litre) AS petrol_rsp,
           COUNT(*)           AS petrol_days,
           SUM(is_change)     AS petrol_changes
    FROM petrol_daily
    GROUP BY month_start
),
-- FX: simple average over the trading days of the month.
fx_m AS (
    SELECT obs_date - INTERVAL (DAY(obs_date) - 1) DAY AS month_start,
           AVG(inr_per_usd)                            AS usdinr,
           COUNT(*)                                    AS fx_obs_days
    FROM stg_usdinr_daily
    WHERE obs_date BETWEEN @start_month AND LAST_DAY(@end_month)
    GROUP BY month_start
)
SELECT m.month_start,
       b.brent_usd_bbl,
       ROUND(fx.usdinr, 4),
       -- USD/bbl  x  INR/USD  /  158.987 litres per barrel  =  INR per litre of crude
       ROUND(b.brent_usd_bbl * fx.usdinr / 158.987, 4)    AS crude_inr_litre,
       ROUND(p.petrol_rsp, 3),
       fx.fx_obs_days,
       p.petrol_days,
       p.petrol_changes
FROM dim_month AS m
LEFT JOIN stg_brent_monthly AS b  ON b.month_start  = m.month_start
LEFT JOIN fx_m              AS fx ON fx.month_start = m.month_start
LEFT JOIN petrol_m          AS p  ON p.month_start  = m.month_start
ORDER BY m.month_start;
