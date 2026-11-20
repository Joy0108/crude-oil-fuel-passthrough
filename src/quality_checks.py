"""Step 3 - Run the SQL data-quality checks and stop the pipeline if any FAIL check breaks."""
import sys

import pandas as pd

from config import N_MONTHS, REPORTS_DIR
from src.db import get_engine, run_sql_file


def main() -> pd.DataFrame:
    with get_engine().connect() as conn:
        results = run_sql_file(conn, "04_quality_checks.sql", {"n_months": N_MONTHS})
    for df in results:                       # every check returns the same 4 columns, in order
        df.columns = ["check_name", "severity", "violations", "detail"]
    checks = pd.concat(results, ignore_index=True)
    checks["violations"] = checks["violations"].astype(int)
    checks["status"] = checks.apply(
        lambda r: "PASS" if r.violations == 0 else r.severity, axis=1)
    checks = checks[["check_name", "status", "violations", "detail"]]

    checks.to_csv(REPORTS_DIR / "data_quality_checks.csv", index=False)
    (REPORTS_DIR / "data_quality_checks.md").write_text(
        "# Data quality checks (sql/04_quality_checks.sql)\n\n"
        + checks.to_markdown(index=False) + "\n", encoding="utf-8")

    for r in checks.itertuples():
        print(f"  [{r.status:<4}] {r.check_name:<40} {r.detail[:90]}")
    if (checks["status"] == "FAIL").any():
        sys.exit("Data quality gate failed - fix the data before modelling.")
    return checks


if __name__ == "__main__":
    main()
