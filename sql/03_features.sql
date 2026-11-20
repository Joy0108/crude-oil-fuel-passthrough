-- =============================================================================
-- 03_features.sql
-- Feature view used by the models: lags, first differences and rolling means,
-- all computed with CTEs and window functions (LAG / AVG OVER).
--
-- Every regressor is a *lagged* value, i.e. something already known at the end
-- of the previous month. That keeps the hold-out forecasts honest one-step-ahead
-- forecasts with no peeking at the month being predicted.
-- =============================================================================

CREATE OR REPLACE VIEW v_model_features AS
WITH
base AS (
    SELECT f.month_start,
           m.month_index,
           m.pricing_regime,
           f.petrol_changes,
           f.petrol_rsp,
           f.crude_inr_litre,
           f.brent_usd_bbl,
           f.usdinr
    FROM fuel_monthly AS f
    JOIN dim_month    AS m USING (month_start)
),
-- First differences: the stationary (I(0)) transforms of the I(1) series.
diffs AS (
    SELECT b.*,
           LAG(petrol_rsp)      OVER w                    AS petrol_lag1,
           LAG(crude_inr_litre) OVER w                    AS crude_lag1,
           petrol_rsp      - LAG(petrol_rsp)      OVER w  AS d_petrol,
           crude_inr_litre - LAG(crude_inr_litre) OVER w  AS d_crude,
           brent_usd_bbl   - LAG(brent_usd_bbl)   OVER w  AS d_brent,
           usdinr          - LAG(usdinr)          OVER w  AS d_usdinr
    FROM base AS b
    WINDOW w AS (ORDER BY month_start)
)
SELECT d.*,
       -- short-run dynamics: lagged differences
       LAG(d_petrol, 1) OVER w                                  AS d_petrol_lag1,
       LAG(d_petrol, 2) OVER w                                  AS d_petrol_lag2,
       LAG(d_petrol, 3) OVER w                                  AS d_petrol_lag3,
       LAG(d_crude, 1)  OVER w                                  AS d_crude_lag1,
       LAG(d_crude, 2)  OVER w                                  AS d_crude_lag2,
       LAG(d_crude, 3)  OVER w                                  AS d_crude_lag3,
       -- crude increases and decreases split apart (rockets-and-feathers test)
       GREATEST(d_crude, 0)                                     AS d_crude_up,
       LEAST(d_crude, 0)                                        AS d_crude_down,
       GREATEST(LAG(d_crude, 1) OVER w, 0)                      AS d_crude_up_lag1,
       LEAST(LAG(d_crude, 1) OVER w, 0)                         AS d_crude_down_lag1,
       -- rolling means, emitted only once the window is full
       CASE WHEN month_index >= 3
            THEN AVG(crude_inr_litre) OVER (w ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
       END                                                      AS crude_ma3,
       CASE WHEN month_index >= 12
            THEN AVG(crude_inr_litre) OVER (w ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
       END                                                      AS crude_ma12,
       CASE WHEN month_index >= 12
            THEN AVG(petrol_rsp) OVER (w ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
       END                                                      AS petrol_ma12
FROM diffs AS d
WINDOW w AS (ORDER BY month_start);
