"""The naive estimator the Kalman filter replaces: OLS slope of weight vs time.

    TDEE = mean(intake) − slope × rho

The 95% CI uses the textbook OLS standard error, which assumes i.i.d. residuals.
Two variants:
  - on raw readings: residuals are autocorrelated (water persists for days) → CI too narrow
  - on an EMA-smoothed series: much worse — each EMA point re-uses past readings,
    so residuals are strongly autocorrelated and the CI is dramatically too narrow
"""
import numpy as np
import pandas as pd
from scipy import stats

from .model import RHO


def ols_tdee(dates, weights, intake_mean: float, ema_halflife_days: float | None = None) -> dict:
    d = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    y = pd.Series(weights, dtype=float).reset_index(drop=True)
    if ema_halflife_days is not None:
        y = y.ewm(halflife=f"{ema_halflife_days} days", times=d).mean()
    x = (d - d.iloc[0]).dt.days.to_numpy(dtype=float)
    n = len(x)
    if n < 3 or x.max() == x.min():
        return {"tdee": np.nan, "tdee_ci95": np.nan, "slope": np.nan}
    b, a = np.polyfit(x, y.to_numpy(), 1)
    resid = y.to_numpy() - (a + b * x)
    s = np.sqrt((resid ** 2).sum() / (n - 2))
    se = s / np.sqrt(((x - x.mean()) ** 2).sum())
    half = stats.t.ppf(0.975, n - 2) * se * RHO
    return {"tdee": intake_mean - b * RHO, "tdee_ci95": half, "slope": b}
