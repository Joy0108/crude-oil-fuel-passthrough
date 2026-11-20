"""Model building blocks shared by the cointegration and forecasting steps.

All inputs come from the MySQL view v_model_features, so the lags and differences
used here are exactly the ones built with LAG() windows in sql/03_features.sql.
"""
import itertools
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import coint

from src.db import read_table

Y, X = "petrol_rsp", "crude_inr_litre"
HAC = {"cov_type": "HAC", "cov_kwds": {"maxlags": 3}}   # autocorrelation-robust standard errors


def load_features() -> pd.DataFrame:
    df = read_table("SELECT * FROM v_model_features ORDER BY month_start")
    df["month_start"] = pd.to_datetime(df["month_start"])
    df = df.set_index("month_start").asfreq("MS")
    numeric = df.columns.difference(["pricing_regime"])
    df[numeric] = df[numeric].astype(float)          # MySQL DECIMAL -> float
    return df


# ----------------------------------------------------------------------------- cointegration
def engle_granger(df: pd.DataFrame, x_cols=(X,), trend: str = "c") -> dict:
    """Engle-Granger residual test with MacKinnon critical values (not plain ADF values,
    which would be too lenient because the residual comes from an estimated regression)."""
    tau, p, crit = coint(df[Y], df[list(x_cols)], trend=trend, autolag="aic")
    return {"tau": tau, "p_value": p, "crit_5pct": crit[1]}


def long_run_fit(df: pd.DataFrame):
    """Step 1 of Engle-Granger: static levels regression petrol = a + b * crude_inr_litre."""
    return sm.OLS(df[Y], sm.add_constant(df[[X]])).fit()


def equilibrium_error(df: pd.DataFrame, long_run) -> pd.Series:
    return df[Y] - long_run.predict(sm.add_constant(df[[X]]))


# ----------------------------------------------------------------------------- ECM
def ecm_columns(p: int, q: int) -> list[str]:
    return (["ect_lag1"] + [f"d_petrol_lag{i}" for i in range(1, p + 1)]
            + [f"d_crude_lag{j}" for j in range(1, q + 1)])


def fit_ecm(df: pd.DataFrame, train_end, max_lag: int = 3) -> dict:
    """Step 2 of Engle-Granger: an error-correction model in first differences

        d_petrol_t = c + alpha * u_{t-1} + sum_i phi_i d_petrol_{t-i} + sum_j theta_j d_crude_{t-j} + e_t

    Only lagged terms enter, so every forecast uses information available a month earlier.
    The long-run equation and the lag orders (p, q) are chosen on the training months only."""
    d = df.copy()
    long_run = long_run_fit(d.loc[:train_end])
    d["ect_lag1"] = equilibrium_error(d, long_run).shift(1)

    common = d.loc[:train_end].dropna(subset=ecm_columns(max_lag, max_lag) + ["d_petrol"])

    def bic(pq):
        return sm.OLS(common["d_petrol"], sm.add_constant(common[ecm_columns(*pq)])).fit().bic

    lags = min(itertools.product(range(1, max_lag + 1), repeat=2), key=bic)
    cols = ecm_columns(*lags)
    est = d.loc[:train_end].dropna(subset=cols + ["d_petrol"])
    model = sm.OLS(est["d_petrol"], sm.add_constant(est[cols])).fit(**HAC)
    return {"long_run": long_run, "model": model, "lags": lags, "cols": cols, "data": d}


def forecast_ecm(fit: dict, test_index) -> pd.Series:
    """One-step-ahead level forecasts: last observed price + predicted change."""
    d = fit["data"].loc[test_index]
    d_hat = fit["model"].predict(sm.add_constant(d[fit["cols"]], has_constant="add"))
    return d["petrol_lag1"] + d_hat


# ----------------------------------------------------------------------------- SARIMA
def fit_sarima(train_y: pd.Series, max_pq: int = 2):
    """Univariate benchmark. d = 1 because ADF/KPSS show petrol is I(1). No seasonal
    differencing (D = 0): seasonality, if any, is left to the seasonal AR/MA terms, which
    also keeps AIC comparable across the grid (AIC is not comparable across differencing orders)."""
    best = None
    for p, q, P, Q in itertools.product(range(max_pq + 1), range(max_pq + 1), range(2), range(2)):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = SARIMAX(train_y, order=(p, 1, q), seasonal_order=(P, 0, Q, 12)).fit(disp=False)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if best is None or res.aic < best.aic:
            best = res
    return best


def forecast_sarima(res, y: pd.Series, test_index) -> pd.Series:
    """Re-filter the series with parameters frozen at the end of training, then take the
    one-step-ahead predictions (each uses actual data up to the previous month)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        applied = res.apply(y.loc[:test_index[-1]])
    return applied.get_prediction(start=test_index[0], end=test_index[-1], dynamic=False).predicted_mean


# ----------------------------------------------------------------------------- evaluation
def rmse(err) -> float:
    return float(np.sqrt(np.mean(np.square(err))))


def diebold_mariano(e_model, e_bench) -> tuple[float, float]:
    """DM test on squared errors (h = 1) with the Harvey-Leybourne-Newbold small-sample fix.
    Negative statistic = model more accurate than benchmark."""
    d = np.square(np.asarray(e_model)) - np.square(np.asarray(e_bench))
    n = len(d)
    dm = d.mean() / np.sqrt(d.var(ddof=1) / n) * np.sqrt((n - 1) / n)
    return float(dm), float(2 * stats.t.sf(abs(dm), df=n - 1))


# ----------------------------------------------------------------------------- pass-through
def passthrough(df: pd.DataFrame, lags: int = 2) -> dict:
    """Cumulative short-run pass-through: rupees of pump-price change per rupee change in
    crude cost per litre, summed over the same month and `lags` following months."""
    cols = ["d_crude"] + [f"d_crude_lag{k}" for k in range(1, lags + 1)]
    d = df.dropna(subset=cols + ["d_petrol"])
    m = sm.OLS(d["d_petrol"], sm.add_constant(d[cols])).fit(**HAC)
    t = m.t_test(" + ".join(cols) + " = 0")
    return {"months": f"{d.index[0]:%Y-%m} to {d.index[-1]:%Y-%m}", "n": int(m.nobs),
            "cum_passthrough": float(np.squeeze(t.effect)), "se": float(np.squeeze(t.sd)),
            "p_value": float(np.squeeze(t.pvalue)), "r2": float(m.rsquared)}
