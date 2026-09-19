"""Synthetic users with a KNOWN true TDEE — the only way to check whether a 95% CI covers 95%.

The generator follows the same structure as the model (tissue + water + scale noise) but
adds things the filter does not know about: water spikes (travel, salty meals), missing
days, and a TDEE step change if requested.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import RHO


@dataclass(frozen=True)
class SimConfig:
    days: int = 84
    tdee_range: tuple = (2200.0, 3000.0)
    w0_range: tuple = (60.0, 85.0)
    sigma_t: float = 5.0
    phi: float = 0.77
    sigma_h: float = 0.75
    sigma_v: float = 0.21
    surplus_mean: float = 150.0   # true mean intake − TDEE (kcal/day)
    intake_sd: float = 450.0      # day-to-day spread of true intake
    log_noise: float = 0.05       # logged = true × (1 + N(0, log_noise))
    p_weigh: float = 0.8          # share of days with a morning reading
    p_log: float = 0.9            # share of days with logged intake
    spike_prob: float = 0.02      # chance per day of a water spike
    spike_kg: float = 1.5
    step_day: int | None = None   # optional TDEE regime change
    step_kcal: float = 0.0
    start: str = "2026-01-01"


def simulate_user(cfg: SimConfig = SimConfig(), rng: np.random.Generator | None = None
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (inputs, truth). inputs: date, weight_kg, intake (NaN when missing).
    truth: date, W, T, H, intake_true."""
    rng = rng or np.random.default_rng()
    n = cfg.days
    T = np.empty(n)
    W = np.empty(n)
    H = np.empty(n)
    T[0] = rng.uniform(*cfg.tdee_range)
    W[0] = rng.uniform(*cfg.w0_range)
    H[0] = rng.normal(0, cfg.sigma_h)
    intake_true = np.empty(n)
    q_h = cfg.sigma_h * np.sqrt(1 - cfg.phi ** 2)
    for t in range(n):
        intake_true[t] = max(800.0, rng.normal(T[t] + cfg.surplus_mean, cfg.intake_sd))
        if t == n - 1:
            break
        T[t + 1] = T[t] + rng.normal(0, cfg.sigma_t)
        if cfg.step_day is not None and t + 1 == cfg.step_day:
            T[t + 1] += cfg.step_kcal
        W[t + 1] = W[t] + (intake_true[t] - T[t]) / RHO
        spike = cfg.spike_kg if rng.random() < cfg.spike_prob else 0.0
        H[t + 1] = cfg.phi * H[t] + rng.normal(0, q_h) + spike

    dates = pd.date_range(cfg.start, periods=n, freq="D").date
    y = W + H + rng.normal(0, cfg.sigma_v, n)
    y[rng.random(n) > cfg.p_weigh] = np.nan
    y[0] = W[0] + H[0] + rng.normal(0, cfg.sigma_v)  # filter needs a first reading
    logged = intake_true * (1 + rng.normal(0, cfg.log_noise, n))
    logged[rng.random(n) > cfg.p_log] = np.nan
    inputs = pd.DataFrame({"date": dates, "weight_kg": y, "intake": logged})
    truth = pd.DataFrame({"date": dates, "W": W, "T": T, "H": H, "intake_true": intake_true})
    return inputs, truth
