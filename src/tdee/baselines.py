"""The naive estimator the Kalman filter replaces: OLS slope of weight vs time.

    TDEE = mean(intake) − slope × rho

Standard errors:
  - textbook OLS (i.i.d. residuals): too narrow, water residuals are autocorrelated
  - on an EMA-smoothed series: much worse — each EMA point re-uses past readings
  - Newey-West (HAC, Bartlett kernel): the standard fix for autocorrelated residuals,
    but badly biased downward on short, persistent series (tens of readings)
"""
import numpy as np
import pandas as pd
from scipy import stats

from .model import RHO


def newey_west_lags(n: int) -> int:
    """Newey & West (1994) rule of thumb: floor(4 (n/100)^(2/9)), at least 1."""
    return max(1, int(4 * (n / 100) ** (2 / 9)))


def ols_tdee(dates, weights, intake_mean: float, ema_halflife_days: float | None = None,
             hac_lags: int | None = None) -> dict:
    """`hac_lags`: None = textbook SE ; int = Newey-West SE with that many lags
    (lags counted in readings, not calendar days)."""
    d = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    y = pd.Series(weights, dtype=float).reset_index(drop=True)
    if ema_halflife_days is not None:
        y = y.ewm(halflife=f"{ema_halflife_days} days", times=d).mean()
    x = (d - d.iloc[0]).dt.days.to_numpy(dtype=float)
    n = len(x)
    if n < 3 or x.max() == x.min():
        return {"tdee": np.nan, "tdee_ci95": np.nan, "slope": np.nan}
    X = np.column_stack([np.ones(n), x])
    beta = np.linalg.lstsq(X, y.to_numpy(), rcond=None)[0]
    resid = y.to_numpy() - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    if hac_lags is None:
        s2 = (resid ** 2).sum() / (n - 2)
        var_b = s2 * XtX_inv[1, 1]
    else:
        u = X * resid[:, None]
        S = u.T @ u
        for lag in range(1, hac_lags + 1):
            G = u[lag:].T @ u[:-lag]
            S += (1 - lag / (hac_lags + 1)) * (G + G.T)
        var_b = (XtX_inv @ S @ XtX_inv)[1, 1]
    half = stats.t.ppf(0.975, n - 2) * np.sqrt(var_b) * RHO
    return {"tdee": intake_mean - beta[1] * RHO, "tdee_ci95": half, "slope": beta[1]}
