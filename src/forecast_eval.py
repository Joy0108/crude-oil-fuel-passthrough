"""Step 6 - One-step-ahead forecast comparison: ECM vs SARIMA (and a no-change benchmark).

Protocol (identical for every model):
  * all parameters and lag orders are chosen on the training months only;
  * parameters are then frozen and each hold-out month t is forecast using data up to t-1;
  * accuracy = RMSE / MAE of the pump-price forecast in INR per litre; Diebold-Mariano
    test for whether the ECM-vs-SARIMA difference is statistically meaningful.

Hold-out windows:
  * PRIMARY - the last 24 months of the study (Nov-2024..Oct-2026), as planned.
  * ROBUSTNESS - the last 24 months of market-linked pricing (May-2020..Apr-2022). Added
    after the primary result, to check whether the ECM does better when prices still
    followed crude. Reported as a secondary check, not as the headline.
"""
import json

import matplotlib.pyplot as plt
import pandas as pd

from config import FIG_DIR, HOLDOUT_MONTHS, MARKET_REGIME_END, REPORTS_DIR
from src import plot_style as ps
from src.models import (Y, diebold_mariano, fit_ecm, fit_sarima, forecast_ecm, forecast_sarima,
                        load_features, rmse)


def evaluate_window(df: pd.DataFrame, test_end, name: str) -> tuple[dict, pd.DataFrame]:
    test_end = pd.Timestamp(test_end)
    end_pos = df.index.get_loc(test_end)
    test_index = df.index[end_pos - HOLDOUT_MONTHS + 1: end_pos + 1]
    train_end = df.index[end_pos - HOLDOUT_MONTHS]

    sarima = fit_sarima(df.loc[:train_end, Y])
    ecm = fit_ecm(df, train_end)

    actual = df.loc[test_index, Y]
    preds = pd.DataFrame({
        "actual": actual,
        "no_change": df.loc[test_index, "petrol_lag1"],
        "sarima": forecast_sarima(sarima, df[Y], test_index),
        "ecm": forecast_ecm(ecm, test_index),
    })
    err = {m: preds["actual"] - preds[m] for m in ("no_change", "sarima", "ecm")}
    dm, dm_p = diebold_mariano(err["ecm"], err["sarima"])
    r = {m: rmse(e) for m, e in err.items()}
    summary = {
        "window": name,
        "train": f"{df.index[0]:%Y-%m} to {train_end:%Y-%m}",
        "test": f"{test_index[0]:%Y-%m} to {test_index[-1]:%Y-%m}",
        "sarima_order": f"{sarima.model.order}x{sarima.model.seasonal_order}",
        "ecm_lags_p_q": ecm["lags"],
        "rmse_no_change": r["no_change"], "rmse_sarima": r["sarima"], "rmse_ecm": r["ecm"],
        "mae_sarima": float(err["sarima"].abs().mean()), "mae_ecm": float(err["ecm"].abs().mean()),
        "ecm_vs_sarima_rmse_pct": 100 * (r["ecm"] / r["sarima"] - 1),
        "dm_stat": dm, "dm_p_value": dm_p,
        "months_with_price_change": int((df.loc[test_index, "d_petrol"].abs() > 0.01).sum()),
    }
    return summary, preds


def main() -> list[dict]:
    df = load_features()
    windows = [("primary: last 24 months", df.index[-1]),
               ("robustness: last 24 market-linked months", MARKET_REGIME_END)]
    summaries, all_preds = [], {}
    for name, end in windows:
        s, p = evaluate_window(df, end, name)
        summaries.append(s)
        all_preds[name] = p
        p.assign(window=name).to_csv(
            REPORTS_DIR / f"forecasts_{'primary' if name.startswith('primary') else 'robustness'}.csv")

    table = pd.DataFrame(summaries)
    show = table[["window", "test", "sarima_order", "ecm_lags_p_q", "rmse_no_change", "rmse_sarima",
                  "rmse_ecm", "ecm_vs_sarima_rmse_pct", "dm_p_value", "months_with_price_change"]].copy()
    show.columns = ["hold-out window", "test months", "SARIMA order", "ECM lags (p,q)", "RMSE no-change",
                    "RMSE SARIMA", "RMSE ECM", "ECM vs SARIMA (%)", "DM p-value", "months price moved"]
    show = show.round(3)
    (REPORTS_DIR / "forecast_comparison.md").write_text(
        "# One-step-ahead forecast comparison (INR per litre)\n\n"
        "Parameters frozen at the end of training; each month forecast from data up to the month before.\n"
        "Negative 'ECM vs SARIMA' = ECM more accurate. DM = Diebold-Mariano test on squared errors.\n\n"
        + show.to_markdown(index=False) + "\n", encoding="utf-8")
    show.to_csv(REPORTS_DIR / "forecast_comparison.csv", index=False)
    (REPORTS_DIR / "results_forecast.json").write_text(json.dumps(summaries, indent=2, default=str))

    plot_forecasts(all_preds, summaries)
    print(show.to_string(index=False))
    return summaries


def plot_forecasts(all_preds: dict, summaries: list[dict]) -> None:
    ps.apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, (name, p), s in zip(axes, all_preds.items(), summaries):
        ax.plot(p.index, p["actual"], color=ps.INK_2, lw=2.4, label="Actual pump price")
        ax.plot(p.index, p["sarima"], color=ps.BLUE, marker="o", ms=4, label=f"SARIMA (RMSE {s['rmse_sarima']:.2f})")
        ax.plot(p.index, p["ecm"], color=ps.ORANGE, marker="o", ms=4, label=f"ECM (RMSE {s['rmse_ecm']:.2f})")
        ax.set_title(name.split(":")[0].capitalize() + f" hold-out, {s['test'].replace(' to ', ' - ')}")
        ax.set_ylabel("INR per litre")
        ax.legend(loc="upper left")
        ax.tick_params(axis="x", labelrotation=0)
        ax.xaxis.set_major_locator(plt.matplotlib.dates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b %Y"))
    fig.suptitle("One-step-ahead forecasts of the Delhi petrol price", x=0.01, ha="left",
                 fontsize=11.5, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_holdout_forecasts.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
