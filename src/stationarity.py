"""Step 4 - Unit-root testing with ADF and KPSS.

The two tests have opposite null hypotheses, so using both avoids reading a weak test as
evidence:
    ADF   H0: unit root (non-stationary)      -> want to REJECT for a stationary series
    KPSS  H0: stationary                      -> want to NOT reject for a stationary series

Levels are tested with constant + trend ("ct"), so a series that is merely trend-stationary
is not mistaken for I(1). First differences are tested with a constant ("c").
A series is called I(1) when its level looks non-stationary on BOTH tests and its first
difference looks stationary on BOTH tests (5% level).
"""
import json
import warnings

import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import adfuller, kpss

from config import FIG_DIR, REPORTS_DIR
from src import plot_style as ps
from src.models import load_features

SERIES = {
    "brent_usd_bbl": "Brent crude (USD/bbl)",
    "usdinr": "USD/INR (INR per USD)",
    "petrol_rsp": "Delhi petrol (INR/litre)",
    "crude_inr_litre": "Crude cost (INR/litre, derived)",
}
ALPHA = 0.05


def run_tests(x: pd.Series, regression: str) -> dict:
    adf_stat, adf_p, adf_lags, *_ = adfuller(x, regression=regression, autolag="AIC",
                                             result_object=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InterpolationWarning)   # KPSS p is tabulated in [0.01, 0.10]
        kpss_stat, kpss_p, kpss_lags, _ = kpss(x, regression=regression, nlags="auto",
                                               result_object=False)
    return {"adf_stat": adf_stat, "adf_p": adf_p, "adf_lags": adf_lags,
            "kpss_stat": kpss_stat, "kpss_p": kpss_p}


def fmt_kpss(p: float) -> str:
    return "<= 0.01" if p <= 0.01 else (">= 0.10" if p >= 0.10 else f"{p:.3f}")


def main() -> pd.DataFrame:
    df = load_features()
    rows = []
    for col, label in SERIES.items():
        lvl = run_tests(df[col], "ct")
        dif = run_tests(df[col].diff().dropna(), "c")
        level_nonstationary = lvl["adf_p"] > ALPHA and lvl["kpss_p"] < ALPHA
        diff_stationary = dif["adf_p"] < ALPHA and dif["kpss_p"] > ALPHA
        verdict = "I(1)" if level_nonstationary and diff_stationary else "inconclusive"
        rows.append({
            "series": label,
            "ADF level (p)": f"{lvl['adf_stat']:.2f} ({lvl['adf_p']:.3f})",
            "KPSS level (p)": f"{lvl['kpss_stat']:.2f} ({fmt_kpss(lvl['kpss_p'])})",
            "ADF diff (p)": f"{dif['adf_stat']:.2f} ({dif['adf_p']:.4f})",
            "KPSS diff (p)": f"{dif['kpss_stat']:.2f} ({fmt_kpss(dif['kpss_p'])})",
            "order": verdict,
        })
    table = pd.DataFrame(rows)
    table.to_csv(REPORTS_DIR / "stationarity_tests.csv", index=False)
    (REPORTS_DIR / "stationarity_tests.md").write_text(
        "# Unit-root tests (176 months, 5% level)\n\n"
        "Levels: constant + trend. Differences: constant. "
        "ADF H0 = unit root; KPSS H0 = stationary.\n\n" + table.to_markdown(index=False) + "\n",
        encoding="utf-8")
    (REPORTS_DIR / "results_stationarity.json").write_text(
        json.dumps({r["series"]: r["order"] for r in rows}, indent=2), encoding="utf-8")
    print(table.to_string(index=False))

    plot_overview(df)
    return table


def plot_overview(df: pd.DataFrame) -> None:
    ps.apply_style()
    fig, axes = plt.subplots(4, 1, figsize=(10, 10.5), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1.6, 1]})
    a, b, c, d = axes

    a.plot(df.index, df["brent_usd_bbl"], color=ps.BLUE)
    a.set_title("Brent crude, USD per barrel")
    b.plot(df.index, df["usdinr"], color=ps.BLUE)
    b.set_title("USD/INR, rupees per dollar")

    c.plot(df.index, df["petrol_rsp"], color=ps.BLUE, label="Delhi petrol pump price")
    c.plot(df.index, df["crude_inr_litre"], color=ps.ORANGE, label="Crude cost per litre (Brent x USD/INR / 158.987)")
    c.plot(df.index, df["petrol_ma12"], color=ps.BLUE, lw=1, alpha=0.45, label="Petrol, 12-month rolling mean (SQL)")
    c.set_title("Same unit, INR per litre: pump price vs the crude inside it")
    c.legend(loc="upper left", ncols=1, bbox_to_anchor=(0, 0.93))
    for col, color in (("petrol_rsp", ps.BLUE), ("crude_inr_litre", ps.ORANGE)):
        c.annotate(f"{df[col].iloc[-1]:.1f}", (df.index[-1], df[col].iloc[-1]), xytext=(4, 0),
                   textcoords="offset points", va="center", color=ps.INK_2, fontsize=9)

    wedge = df["petrol_rsp"] - df["crude_inr_litre"]
    d.plot(df.index, wedge, color=ps.AQUA)
    d.set_title("Non-crude wedge = pump price - crude cost (taxes, refining & retail margins)")

    for ax in axes:
        ps.mark_regimes(ax, label=ax is a)
        ax.set_ylabel("")
    ps.year_axis(d)
    fig.suptitle("176 months, Mar-2012 to Oct-2026", x=0.01, ha="left", color=ps.INK_2, fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_overview.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
