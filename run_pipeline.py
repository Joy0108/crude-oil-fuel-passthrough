"""Run the whole study end to end.

    python run_pipeline.py            scrape fresh data, then everything else
    python run_pipeline.py --offline  reuse the raw files already in data/raw/
"""
import argparse
import time

from src import build_database, cointegration_ecm, forecast_eval, quality_checks, scrape, stationarity


def main(offline: bool) -> None:
    steps = [
        ("1  Scrape EIA / Federal Reserve / PPAC", lambda: scrape.main(offline=offline)),
        ("2  Load MySQL + model the monthly panel in SQL", build_database.main),
        ("3  SQL data-quality gate", quality_checks.main),
        ("4  Unit-root tests (ADF + KPSS)", stationarity.main),
        ("5  Engle-Granger cointegration, ECM, pass-through", cointegration_ecm.main),
        ("6  Hold-out forecasts: ECM vs SARIMA", forecast_eval.main),
    ]
    start = time.time()
    for title, step in steps:
        print(f"\n=== Step {title} " + "=" * max(0, 60 - len(title)))
        step()
    print(f"\nDone in {time.time() - start:.0f}s. Reports in reports/, figures in reports/figures/.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip downloading, parse data/raw/")
    main(ap.parse_args().offline)
