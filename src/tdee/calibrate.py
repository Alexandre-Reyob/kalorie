"""Maximum-likelihood calibration of the noise parameters on one person's history.

Only the NOISE structure (phi, sigma_h, sigma_v, sigma_t) is fitted: it is personal and
fairly stable, unlike the TDEE level. On ~3 months of data sigma_t tends to collapse to 0
(no drift detectable), in which case keep a small positive value so the filter can
still follow a real lifestyle change.
"""
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .model import DEFAULT, Params, run


def calibrate(inputs: pd.DataFrame, start: Params = DEFAULT, prior_t: float = 2500.0,
              regime_breaks: tuple = ()) -> tuple[Params, float]:
    def unpack(z):
        return replace(start, sigma_t=np.exp(z[0]), phi=1 / (1 + np.exp(-z[1])),
                       sigma_h=np.exp(z[2]), sigma_v=np.exp(z[3]))

    def nll(z):
        _, ll = run(inputs, unpack(z), prior_t, regime_breaks)
        return -ll

    z0 = [np.log(start.sigma_t), np.log(start.phi / (1 - start.phi)),
          np.log(start.sigma_h), np.log(start.sigma_v)]
    res = minimize(nll, z0, method="Nelder-Mead",
                   options={"maxiter": 400, "xatol": 1e-3, "fatol": 1e-3})
    return unpack(res.x), -res.fun
