"""Step 2 - Load the scraped data into MySQL and model the 176-month panel in SQL.

  sql/01_schema.sql         staging tables, calendar + month dimensions, panel table
  (python)                  bulk-insert data/interim/*.csv into the staging tables
  sql/02_build_monthly.sql  recursive-CTE calendar, day-weighted petrol average,
                            FX monthly average, join + crude -> INR/litre conversion
  sql/03_features.sql       CTE + LAG/AVG window view with lags, differences, rolling means

The finished panel and feature view are exported to data/processed/ for transparency.
"""
import pandas as pd
from sqlalchemy import text

from config import END_MONTH, INTERIM_DIR, MARKET_REGIME_END, MYSQL, PROCESSED_DIR, START_MONTH
from src.db import get_engine, run_sql_file


def create_database() -> None:
    with get_engine(with_database=False).begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{MYSQL['database']}` "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"))


def load_staging(conn) -> dict[str, int]:
    sources = {
        "stg_brent_monthly": ("brent_monthly.csv", ["month_start"]),
        "stg_usdinr_daily": ("usdinr_daily.csv", ["obs_date"]),
        "stg_petrol_delhi": ("petrol_delhi.csv", ["effective_date"]),
    }
    counts = {}
    for table, (csv, date_cols) in sources.items():
        df = pd.read_csv(INTERIM_DIR / csv, parse_dates=date_cols)
        for c in date_cols:
            df[c] = df[c].dt.date
        df = df.astype(object).where(df.notna(), None)          # NaN -> SQL NULL
        df.to_sql(table, conn, if_exists="append", index=False, chunksize=1000, method="multi")
        counts[table] = len(df)
    return counts


def main() -> None:
    create_database()
    with get_engine().begin() as conn:
        run_sql_file(conn, "01_schema.sql")
        counts = load_staging(conn)
        run_sql_file(conn, "02_build_monthly.sql",
                     {"start_month": START_MONTH, "end_month": END_MONTH,
                      "market_regime_end": MARKET_REGIME_END})
        run_sql_file(conn, "03_features.sql")

        for table, n in counts.items():
            print(f"  loaded {table:<20} {n:>6} rows")
        for table in ("dim_calendar", "dim_month", "fuel_monthly"):
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  built  {table:<20} {n:>6} rows")

        panel = pd.read_sql(text("SELECT * FROM fuel_monthly ORDER BY month_start"), conn)
        feats = pd.read_sql(text("SELECT * FROM v_model_features ORDER BY month_start"), conn)
    panel.to_csv(PROCESSED_DIR / "fuel_monthly.csv", index=False)
    feats.to_csv(PROCESSED_DIR / "model_features.csv", index=False)
    print(f"  exported fuel_monthly + v_model_features to {PROCESSED_DIR.name}/")


if __name__ == "__main__":
    main()
