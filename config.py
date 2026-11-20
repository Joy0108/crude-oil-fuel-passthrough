"""Project-wide settings: paths, study window and database connection."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"            # untouched responses from each website
INTERIM_DIR = ROOT / "data" / "interim"    # parsed, tidy CSVs (input to MySQL)
PROCESSED_DIR = ROOT / "data" / "processed"  # monthly panel exported back from MySQL
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
FIG_DIR = REPORTS_DIR / "figures"

# Study window: the latest 176 complete months for which all three sources overlap.
# Petrol was decontrolled in June 2010, so the whole window is market-linked pricing.
START_MONTH = "2012-03-01"
END_MONTH = "2026-10-01"
N_MONTHS = 176
HOLDOUT_MONTHS = 24          # last 24 months are never seen during model fitting

# Pricing regimes, read off the scraped PPAC daily series: the last market-linked daily
# revision was on 6-Apr-2022. Afterwards the Delhi price moved only on policy dates
# (22-May-2022, 15-Mar-2024, 30-Oct-2024, May-2026), i.e. it became administered.
MARKET_REGIME_END = "2022-04-01"

LITRES_PER_BARREL = 158.987  # 1 US oil barrel = 42 US gallons = 158.987 litres

# MySQL connection (override with environment variables)
MYSQL = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "fuel_analyst"),
    "password": os.getenv("MYSQL_PASSWORD", "fuel_pass"),
    "database": os.getenv("MYSQL_DB", "fuel_passthrough"),
}

for _d in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
