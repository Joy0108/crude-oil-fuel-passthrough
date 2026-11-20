-- =============================================================================
-- 04_quality_checks.sql
-- Each statement returns ONE row: check_name | severity | violations | detail.
-- A check passes when violations = 0. FAIL-severity checks stop the pipeline;
-- WARN checks are reported for review only.
-- Session variable set by the Python runner: @n_months
-- =============================================================================

-- 1. The panel has exactly the expected number of months.
SELECT 'panel_has_176_months'                         AS check_name,
       'FAIL'                                         AS severity,
       ABS(COUNT(*) - @n_months)                      AS violations,
       CONCAT(COUNT(*), ' rows, expected ', @n_months) AS detail
FROM fuel_monthly;

-- 2. Gaps in the monthly index: consecutive complete months must be exactly
--    one month apart (LAG over the ordered index).
WITH ordered AS (
    SELECT month_start,
           LAG(month_start) OVER (ORDER BY month_start) AS prev_month
    FROM fuel_monthly
    WHERE brent_usd_bbl IS NOT NULL AND usdinr IS NOT NULL AND petrol_rsp IS NOT NULL
)
SELECT 'no_gaps_in_monthly_index',
       'FAIL',
       COUNT(*),
       COALESCE(GROUP_CONCAT(CONCAT(prev_month, ' -> ', month_start) SEPARATOR ', '),
                'every step between consecutive months is exactly 1 month')
FROM ordered
WHERE prev_month IS NOT NULL
  AND TIMESTAMPDIFF(MONTH, prev_month, month_start) <> 1;

-- 3. Gaps-and-islands: complete months must form ONE unbroken run.
--    (month number - row number) is constant inside a run and jumps at a gap.
WITH complete AS (
    SELECT month_start,
           TIMESTAMPDIFF(MONTH, '2000-01-01', month_start)
             - ROW_NUMBER() OVER (ORDER BY month_start) AS island_id
    FROM fuel_monthly
    WHERE brent_usd_bbl IS NOT NULL AND usdinr IS NOT NULL AND petrol_rsp IS NOT NULL
),
islands AS (
    SELECT island_id, MIN(month_start) AS run_start, MAX(month_start) AS run_end, COUNT(*) AS n
    FROM complete
    GROUP BY island_id
)
SELECT 'complete_months_form_one_run',
       'FAIL',
       ABS(COUNT(*) - 1),
       GROUP_CONCAT(CONCAT(run_start, ' to ', run_end, ' (', n, ' months)') SEPARATOR ', ')
FROM islands;

-- 4. Source-level gaps: anti-join the month index against the Brent staging table.
SELECT 'brent_source_has_every_month',
       'FAIL',
       COUNT(*),
       COALESCE(GROUP_CONCAT(m.month_start SEPARATOR ', '), 'no month missing')
FROM dim_month AS m
LEFT JOIN stg_brent_monthly AS b USING (month_start)
WHERE b.month_start IS NULL;

-- 5. No NULLs left in the modelled panel.
SELECT 'no_nulls_in_panel',
       'FAIL',
       SUM(brent_usd_bbl IS NULL) + SUM(usdinr IS NULL)
         + SUM(crude_inr_litre IS NULL) + SUM(petrol_rsp IS NULL),
       CONCAT('brent=', SUM(brent_usd_bbl IS NULL), ' fx=', SUM(usdinr IS NULL),
              ' crude_inr=', SUM(crude_inr_litre IS NULL), ' petrol=', SUM(petrol_rsp IS NULL))
FROM fuel_monthly;

-- 6. A pump price is known for every single day (so the day-weighted mean is complete).
SELECT 'petrol_price_known_every_day',
       'FAIL',
       COUNT(*),
       COALESCE(GROUP_CONCAT(f.month_start SEPARATOR ', '), 'all months fully covered')
FROM fuel_monthly AS f
JOIN dim_month    AS m USING (month_start)
WHERE f.petrol_days IS NULL OR f.petrol_days <> m.days_in_month;

-- 7. The daily PPAC feed (since 16-Jun-2017) skips no day.
WITH d AS (
    SELECT effective_date,
           LAG(effective_date) OVER (ORDER BY effective_date) AS prev_date
    FROM stg_petrol_delhi
    WHERE source = 'PPAC_DAILY'
)
SELECT 'daily_petrol_feed_has_no_missing_days',
       'FAIL',
       COUNT(*),
       COALESCE(GROUP_CONCAT(CONCAT(prev_date, ' -> ', effective_date) SEPARATOR ', '),
                'consecutive days only')
FROM d
WHERE prev_date IS NOT NULL AND DATEDIFF(effective_date, prev_date) <> 1;

-- 8. The INR/litre conversion is internally consistent.
SELECT 'crude_conversion_consistent',
       'FAIL',
       SUM(ABS(crude_inr_litre - brent_usd_bbl * usdinr / 158.987) > 0.001),
       CONCAT('max abs deviation = ',
              ROUND(MAX(ABS(crude_inr_litre - brent_usd_bbl * usdinr / 158.987)), 6))
FROM fuel_monthly;

-- 9. Every FX monthly average rests on enough trading days.
SELECT 'fx_month_has_15_plus_trading_days',
       'WARN',
       SUM(fx_obs_days < 15),
       CONCAT('min trading days in a month = ', MIN(fx_obs_days))
FROM fuel_monthly;

-- 10. Large month-on-month moves, for human review (they can be real shocks).
WITH moves AS (
    SELECT month_start,
           100 * (brent_usd_bbl / LAG(brent_usd_bbl) OVER w - 1) AS brent_pct,
           100 * (petrol_rsp    / LAG(petrol_rsp)    OVER w - 1) AS petrol_pct
    FROM fuel_monthly
    WINDOW w AS (ORDER BY month_start)
)
SELECT 'large_moves_brent_30pct_or_petrol_7pct',
       'WARN',
       COUNT(*),
       COALESCE(GROUP_CONCAT(CONCAT(DATE_FORMAT(month_start, '%Y-%m'),
                                    ' (brent ', ROUND(brent_pct, 1), '%, petrol ',
                                    ROUND(petrol_pct, 1), '%)') SEPARATOR ', '),
                'none')
FROM moves
WHERE ABS(brent_pct) > 30 OR ABS(petrol_pct) > 7;
