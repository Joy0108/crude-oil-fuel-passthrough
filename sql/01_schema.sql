-- =============================================================================
-- 01_schema.sql
-- Raw data is stored at its native frequency (monthly / daily / per revision).
-- The monthly model table is derived from it in 02_build_monthly.sql, so the
-- aggregation logic lives in SQL and can be audited.
-- =============================================================================

DROP VIEW  IF EXISTS v_model_features;
DROP TABLE IF EXISTS fuel_monthly;
DROP TABLE IF EXISTS dim_month;
DROP TABLE IF EXISTS dim_calendar;
DROP TABLE IF EXISTS stg_petrol_delhi;
DROP TABLE IF EXISTS stg_usdinr_daily;
DROP TABLE IF EXISTS stg_brent_monthly;

-- ---------------------------------------------------------------- staging (raw)
CREATE TABLE stg_brent_monthly (
    month_start    DATE          NOT NULL PRIMARY KEY,      -- first day of the month
    brent_usd_bbl  DECIMAL(8,2)  NOT NULL,                  -- monthly average spot, USD per barrel
    CONSTRAINT chk_brent_month_start CHECK (DAY(month_start) = 1),
    CONSTRAINT chk_brent_positive    CHECK (brent_usd_bbl > 0)
) COMMENT = 'U.S. EIA - Europe Brent Spot Price FOB, monthly average';

CREATE TABLE stg_usdinr_daily (
    obs_date     DATE           NOT NULL PRIMARY KEY,
    inr_per_usd  DECIMAL(10,4)  NOT NULL,
    CONSTRAINT chk_fx_positive CHECK (inr_per_usd > 0)
) COMMENT = 'Federal Reserve H.10 - noon buying rate, rupees per US dollar';

CREATE TABLE stg_petrol_delhi (
    effective_date  DATE          NOT NULL PRIMARY KEY,     -- price applies from this day onwards
    rsp_inr_litre   DECIMAL(8,2)  NOT NULL,                 -- retail selling price at IOCL Delhi
    source          ENUM('PPAC_REVISION', 'PPAC_DAILY') NOT NULL,
    remark          VARCHAR(120)  NULL,
    CONSTRAINT chk_petrol_positive CHECK (rsp_inr_litre > 0)
) COMMENT = 'PPAC - retail selling price of petrol at Delhi (revisions to 2017, daily after)';

-- ---------------------------------------------------------------- dimensions
CREATE TABLE dim_calendar (
    cal_date     DATE NOT NULL PRIMARY KEY,
    month_start  DATE NOT NULL,
    KEY idx_calendar_month (month_start)
) COMMENT = 'One row per day of the study window';

CREATE TABLE dim_month (
    month_start    DATE      NOT NULL PRIMARY KEY,
    month_end      DATE      NOT NULL,
    days_in_month  TINYINT   NOT NULL,
    month_index    SMALLINT  NOT NULL UNIQUE,               -- 1..176, drives gap checks and the split
    fiscal_year    CHAR(7)   NOT NULL,                      -- Indian FY, e.g. '2024-25'
    pricing_regime ENUM('market_linked', 'administered') NOT NULL
) COMMENT = 'The monthly index the whole study is built on';

-- ---------------------------------------------------------------- modelled monthly panel
CREATE TABLE fuel_monthly (
    month_start      DATE           NOT NULL PRIMARY KEY,
    brent_usd_bbl    DECIMAL(8,2)   NULL,                   -- USD per barrel
    usdinr           DECIMAL(10,4)  NULL,                   -- monthly average, INR per USD
    crude_inr_litre  DECIMAL(10,4)  NULL,                   -- crude cost converted to INR per litre
    petrol_rsp       DECIMAL(8,3)   NULL,                   -- day-weighted average pump price, INR/litre
    fx_obs_days      TINYINT        NULL,                   -- trading days behind the FX average
    petrol_days      TINYINT        NULL,                   -- days with a known pump price
    petrol_changes   TINYINT        NULL,                   -- number of pump-price changes in the month
    CONSTRAINT fk_fuel_month FOREIGN KEY (month_start) REFERENCES dim_month (month_start)
) COMMENT = 'Analysis-ready monthly panel; NULLs are kept on purpose so gaps stay visible';
