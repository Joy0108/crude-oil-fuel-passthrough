"""Step 5 - Engle-Granger cointegration, the error-correction model and pass-through.

1. Engle-Granger test: is there a stable long-run (levels) link between the pump price and
   the rupee cost of crude? Run on the full window and on the training window.
2. ECM: Engle-Granger two-step model on the training window (Mar-2012..Oct-2024). The
   error-correction coefficient alpha says how fast deviations from the long-run line close.
3. Short-run pass-through on changes (the I(0) scale), split by pricing regime, plus a
   36-month rolling estimate to show WHEN the link changed.
4. Rockets and feathers: do crude increases pass through faster than decreases?
"""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS

from config import FIG_DIR, HOLDOUT_MONTHS, REPORTS_DIR
from src import plot_style as ps
from src.models import (HAC, X, Y, engle_granger, equilibrium_error, fit_ecm, load_features,
                        long_run_fit, passthrough)


def eg_table(df: pd.DataFrame, train_end) -> pd.DataFrame:
    rows = []
    for sample, d in (("full, 176 months", df), (f"training, {len(df.loc[:train_end])} months", df.loc[:train_end])):
        for spec, cols, trend in (("petrol ~ crude INR/litre", (X,), "c"),
                                  ("petrol ~ crude INR/litre + trend", (X,), "ct"),
                                  ("petrol ~ Brent + USD/INR", ("brent_usd_bbl", "usdinr"), "c")):
            r = engle_granger(d, cols, trend)
            rows.append({"sample": sample, "long-run equation": spec, "EG tau": round(r["tau"], 2),
                         "5% critical": round(r["crit_5pct"], 2), "p-value": round(r["p_value"], 3),
                         "cointegrated at 5%?": "yes" if r["p_value"] < 0.05 else "no"})
    return pd.DataFrame(rows)


def asymmetry_test(df: pd.DataFrame) -> dict:
    """d_petrol on crude rises and falls separately (same month + 1 lag), market-linked months."""
    cols = ["d_crude_up", "d_crude_up_lag1", "d_crude_down", "d_crude_down_lag1"]
    d = df[df["pricing_regime"] == "market_linked"].dropna(subset=cols + ["d_petrol"])
    m = sm.OLS(d["d_petrol"], sm.add_constant(d[cols])).fit(**HAC)
    up = m.t_test("d_crude_up + d_crude_up_lag1 = 0")
    down = m.t_test("d_crude_down + d_crude_down_lag1 = 0")
    wald = m.t_test("d_crude_up + d_crude_up_lag1 - d_crude_down - d_crude_down_lag1 = 0")
    return {"passthrough_of_increases": float(np.squeeze(up.effect)),
            "passthrough_of_decreases": float(np.squeeze(down.effect)),
            "difference_p_value": float(np.squeeze(wald.pvalue)), "n": int(m.nobs)}


def main() -> dict:
    df = load_features()
    train_end = df.index[-HOLDOUT_MONTHS - 1]

    # ---- 1. Engle-Granger
    eg = eg_table(df, train_end)
    full_lr = long_run_fit(df)
    u = equilibrium_error(df, full_lr)

    # ---- 2. ECM on the training window
    ecm = fit_ecm(df, train_end)
    m = ecm["model"]
    coef = pd.DataFrame({"coef": m.params, "HAC s.e.": m.bse, "p-value": m.pvalues}).round(4)
    alpha, alpha_p = m.params["ect_lag1"], m.pvalues["ect_lag1"]
    half_life = (np.log(0.5) / np.log(1 + alpha)) if (alpha < 0 and alpha_p < 0.05) else None

    # ---- 3. pass-through by regime + rolling
    regimes = {
        "whole window": df,
        "market-linked (Mar-2012..Apr-2022)": df[df["pricing_regime"] == "market_linked"],
        "administered (May-2022..Oct-2026)": df[df["pricing_regime"] == "administered"],
    }
    pt = pd.DataFrame({k: passthrough(v) for k, v in regimes.items()}).T
    rolling = rolling_passthrough(df)

    # ---- 4. asymmetry
    asym = asymmetry_test(df)

    results = {
        "engle_granger": eg.to_dict("records"),
        "long_run_full": {"intercept": float(full_lr.params["const"]), "beta": float(full_lr.params[X]),
                          "r2": float(full_lr.rsquared)},
        "ecm_train": {"train_end": f"{train_end:%Y-%m}", "lags_p_q": ecm["lags"],
                      "long_run_beta": float(ecm["long_run"].params[X]),
                      "alpha": float(alpha), "alpha_p": float(alpha_p), "half_life_months": half_life,
                      "r2": float(m.rsquared), "n": int(m.nobs)},
        "passthrough_by_regime": pt.reset_index(names="sample").to_dict("records"),
        "asymmetry_market_linked": asym,
    }
    (REPORTS_DIR / "results_cointegration_ecm.json").write_text(json.dumps(results, indent=2, default=str))
    write_report(eg, full_lr, coef, ecm, half_life, pt, asym)
    plot_equilibrium_error(u, eg)
    plot_rolling(rolling, pt)

    print(eg.to_string(index=False))
    print(f"\nECM (train to {train_end:%Y-%m}), lags p,q = {ecm['lags']}: alpha = {alpha:.4f} (p = {alpha_p:.3f})")
    print(pt.round(3).to_string())
    print("asymmetry:", {k: round(v, 3) if isinstance(v, float) else v for k, v in asym.items()})
    return results


def rolling_passthrough(df: pd.DataFrame, window: int = 36) -> pd.DataFrame:
    d = df.dropna(subset=["d_petrol", "d_crude", "d_crude_lag1"])
    res = RollingOLS(d["d_petrol"], sm.add_constant(d[["d_crude", "d_crude_lag1"]]), window=window).fit()
    total = res.params["d_crude"] + res.params["d_crude_lag1"]
    cov = res.cov_params()                                   # (n, k, k) stacked covariance matrices
    w = np.array([0.0, 1.0, 1.0])
    se = np.sqrt(np.einsum("i,nij,j->n", w, cov.values.reshape(len(d), 3, 3), w))
    return pd.DataFrame({"passthrough": total.values, "se": se}, index=d.index).dropna()


def write_report(eg, full_lr, coef, ecm, half_life, pt, asym) -> None:
    lr = ecm["long_run"]
    alpha, alpha_p = ecm["model"].params["ect_lag1"], ecm["model"].pvalues["ect_lag1"]
    pt_fmt = pt.copy()
    for c in ("cum_passthrough", "se", "r2"):
        pt_fmt[c] = pt_fmt[c].astype(float).round(3)
    pt_fmt["p_value"] = pt_fmt["p_value"].astype(float).map(lambda p: f"{p:.4f}")
    text = f"""# Cointegration, ECM and pass-through

## Engle-Granger cointegration test
MacKinnon critical values. H0: no cointegration (the levels residual has a unit root).

{eg.to_markdown(index=False)}

Static long-run fit on all 176 months: petrol = {full_lr.params['const']:.2f} + {full_lr.params[X]:.3f} x crude_INR_per_litre (R^2 = {full_lr.rsquared:.2f}).
Because the residual is not stationary, this line is **not** a reliable long-run equilibrium.

## Error-correction model (Engle-Granger two-step, training window)
Long-run step on the training window: petrol = {lr.params['const']:.2f} + {lr.params[X]:.3f} x crude_INR_per_litre.
Lag orders chosen by BIC: p = {ecm['lags'][0]} lags of d_petrol, q = {ecm['lags'][1]} lags of d_crude. HAC standard errors.

{coef.to_markdown()}

Error-correction coefficient alpha = {alpha:.4f} (p = {alpha_p:.3f}).
{"Half-life of a deviation: %.1f months." % half_life if half_life else "Alpha is not significantly negative, so there is no measurable pull back to the long-run line (consistent with the Engle-Granger result)."}

## Short-run pass-through on changes, by pricing regime
Rupees of pump-price change per 1 rupee change in crude cost per litre, summed over months t, t-1, t-2.

{pt_fmt.to_markdown()}

## Rockets and feathers (market-linked months)
Pass-through of crude increases = {asym['passthrough_of_increases']:.3f}, of decreases = {asym['passthrough_of_decreases']:.3f}
(test of equality: p = {asym['difference_p_value']:.3f}, n = {asym['n']}).
"""
    (REPORTS_DIR / "cointegration_ecm.md").write_text(text, encoding="utf-8")


def plot_equilibrium_error(u: pd.Series, eg: pd.DataFrame) -> None:
    ps.apply_style()
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.axhline(0, color=ps.AXIS, lw=0.9)
    ax.plot(u.index, u, color=ps.BLUE)
    ps.mark_regimes(ax)
    ps.year_axis(ax)
    p = eg.loc[0, "p-value"]
    ax.set_title(f"Equilibrium error from the levels regression wanders instead of mean-reverting "
                 f"(Engle-Granger p = {p:.2f})")
    ax.set_ylabel("INR per litre")
    fig.savefig(FIG_DIR / "fig2_equilibrium_error.png")
    plt.close(fig)


def plot_rolling(r: pd.DataFrame, pt: pd.DataFrame) -> None:
    ps.apply_style()
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.fill_between(r.index, r["passthrough"] - 1.96 * r["se"], r["passthrough"] + 1.96 * r["se"],
                    color=ps.BLUE, alpha=0.12, lw=0)
    ax.axhline(0, color=ps.AXIS, lw=0.9)
    ax.plot(r.index, r["passthrough"], color=ps.BLUE)
    ps.mark_regimes(ax)
    ps.year_axis(ax)
    last = r.iloc[-1]
    ax.annotate(f"{last['passthrough']:.2f}", (r.index[-1], last["passthrough"]), xytext=(4, 0),
                textcoords="offset points", va="center", color=ps.INK_2, fontsize=9)
    ax.set_title("Rolling 36-month pass-through: INR change at the pump per INR change in crude cost "
                 "(same + next month, 95% band)")
    fig.savefig(FIG_DIR / "fig3_rolling_passthrough.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
