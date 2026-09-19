import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tdee import DEFAULT, SimConfig, ols_tdee, run, simulate_user  # noqa: E402


def _coverage(n_users: int, day: int) -> tuple[float, float]:
    rng = np.random.default_rng(123)
    k_hits, ema_hits = 0, 0
    for _ in range(n_users):
        inp, tr = simulate_user(SimConfig(days=day + 1), rng)
        h, _ = run(inp, DEFAULT, tr["T"].iloc[0] + rng.normal(0, 300))
        T = tr["T"].iloc[day]
        k_hits += abs(h["T"].iloc[day] - T) <= 1.96 * h["T_sd"].iloc[day]
        obs = inp.dropna(subset=["weight_kg"])
        r = ols_tdee(obs["date"], obs["weight_kg"], inp["intake"].iloc[:day].mean(), ema_halflife_days=5)
        ema_hits += abs(r["tdee"] - T) <= r["tdee_ci95"]
    return k_hits / n_users, ema_hits / n_users


def test_kalman_ci_is_calibrated_and_ema_ols_is_not():
    k, ema = _coverage(n_users=150, day=42)
    assert k > 0.85
    assert ema < 0.6


def test_recovers_constant_tdee_without_noise():
    days = 120
    dates = pd.date_range("2026-01-01", periods=days).date
    tdee, intake, w0 = 2500.0, 2800.0, 70.0
    weight = w0 + (intake - tdee) / 7700 * np.arange(days)
    inp = pd.DataFrame({"date": dates, "weight_kg": weight, "intake": intake})
    h, _ = run(inp, DEFAULT, prior_t=2000.0)
    assert abs(h["T"].iloc[-1] - tdee) < 60


def test_smoother_uses_future_data():
    inp, _ = simulate_user(SimConfig(days=60), np.random.default_rng(0))
    h, _ = run(inp, DEFAULT, prior_t=2600.0)
    assert (h["W_s_sd"] <= h["W_sd"] + 1e-9).all()
    assert h["W_s_sd"].iloc[0] < h["W_sd"].iloc[0]


def test_missing_days_are_handled():
    inp, _ = simulate_user(SimConfig(days=40, p_weigh=0.3, p_log=0.5), np.random.default_rng(1))
    h, ll = run(inp, DEFAULT, prior_t=2600.0)
    assert len(h) == 40 and np.isfinite(ll) and h["T"].notna().all()
