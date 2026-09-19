"""State-space model of energy balance, estimated with a Kalman filter + RTS smoother.

Daily state (morning, before eating):  x = [W, T, H]
  W  tissue mass (kg) — only moves with the energy balance
  T  total daily energy expenditure, TDEE (kcal/day) — slow random walk
  H  water / gut content (kg) — AR(1), mean-reverting

Transition   W' = W + (I − T)/rho + e_W      T' = T + e_T      H' = phi·H + e_H
Observation  y  = W + H + v                   (morning-equivalent scale reading)

I is the LOGGED intake, so T is expressed "in logging units": a systematic logging
bias is absorbed into T, which is what you want when the output is a calorie target
that will be compared to logged intake.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

RHO = 7700.0  # kcal per kg of body mass change


@dataclass(frozen=True)
class Params:
    sigma_t: float = 5.0            # TDEE drift per day (kcal)
    phi: float = 0.77               # day-to-day persistence of water (half-life ~2.6 d)
    sigma_h: float = 0.75           # stationary sd of water (kg)
    sigma_v: float = 0.21           # pure scale noise (kg)
    sigma_v_evening: float = 0.35   # extra noise for an evening reading converted to morning
    noted_factor: float = 2.0       # reading flagged as non-standard → noise × 2
    intake_err: float = 0.05        # logging error sd = intake × (err + err_est × estimated share)
    intake_err_est: float = 0.20
    missing_intake_sd: float = 700.0  # unlogged day: assume I ≈ T ± 700 kcal
    prior_t_sd: float = 350.0
    prior_w_sd: float = 1.0
    robust_z: float = 2.5           # innovations beyond z·sd are down-weighted (travel water spikes)
    regime_bump_sd: float = 250.0   # extra TDEE uncertainty injected at a known regime change


DEFAULT = Params()


def run(inputs: pd.DataFrame, p: Params = DEFAULT, prior_t: float = 2500.0,
        regime_breaks: tuple = ()) -> tuple[pd.DataFrame, float]:
    """Filter + smooth a daily series.

    `inputs`: one row per calendar day with columns
        date, weight_kg (NaN if no reading), intake (NaN if not logged),
        and optionally from_evening, noted (bool), est_share (0-1).
    Returns (history, log-likelihood). History columns: filtered W/T/H with sds
    (causal: uses data up to that day) and smoothed W_s/T_s/H_s (uses all data).
    """
    df = inputs.reset_index(drop=True)
    for col, default in (("from_evening", False), ("noted", False), ("est_share", 0.0)):
        if col not in df:
            df[col] = default
    first = df["weight_kg"].dropna()
    if first.empty:
        return pd.DataFrame(), float("nan")

    x = np.array([float(first.iloc[0]), prior_t, 0.0])
    P = np.diag([p.prior_w_sd ** 2, p.prior_t_sd ** 2, p.sigma_h ** 2])
    Hm = np.array([1.0, 0.0, 1.0])
    q_h = p.sigma_h ** 2 * (1 - p.phi ** 2)
    loglik, rows = 0.0, []
    xs_prior, Ps_prior, xs_post, Ps_post, Fs = [], [], [], [], []

    for i, r in enumerate(df.itertuples(index=False)):
        if r.date in regime_breaks:
            P[1, 1] += p.regime_bump_sd ** 2
        xs_prior.append(x.copy())
        Ps_prior.append(P.copy())
        if pd.notna(r.weight_kg):
            sd = np.hypot(p.sigma_v, p.sigma_v_evening) if r.from_evening else p.sigma_v
            if r.noted:
                sd *= p.noted_factor
            S = Hm @ P @ Hm + sd ** 2
            e = r.weight_kg - Hm @ x
            if abs(e) > p.robust_z * np.sqrt(S):
                S = (e / p.robust_z) ** 2
            K = P @ Hm / S
            x = x + K * e
            P = P - np.outer(K, Hm @ P)
            loglik += -0.5 * (np.log(2 * np.pi * S) + e ** 2 / S)
        rows.append({"date": r.date, "y": r.weight_kg, "intake": r.intake,
                     "W": x[0], "W_sd": np.sqrt(P[0, 0]), "T": x[1],
                     "T_sd": np.sqrt(P[1, 1]), "H": x[2]})
        xs_post.append(x.copy())
        Ps_post.append(P.copy())
        if i == len(df) - 1:
            break
        if pd.notna(r.intake):
            F = np.array([[1.0, -1 / RHO, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, p.phi]])
            u = np.array([r.intake / RHO, 0.0, 0.0])
            sd_i = r.intake * (p.intake_err + p.intake_err_est * r.est_share)
        else:
            F = np.diag([1.0, 1.0, p.phi])
            u = np.zeros(3)
            sd_i = p.missing_intake_sd
        Fs.append(F)
        x = F @ x + u
        P = F @ P @ F.T + np.diag([(sd_i / RHO) ** 2, p.sigma_t ** 2, q_h])

    # Rauch-Tung-Striebel backward pass
    n = len(xs_post)
    xs_s, Ps_s = [None] * n, [None] * n
    xs_s[-1], Ps_s[-1] = xs_post[-1], Ps_post[-1]
    for t in range(n - 2, -1, -1):
        C = Ps_post[t] @ Fs[t].T @ np.linalg.inv(Ps_prior[t + 1])
        xs_s[t] = xs_post[t] + C @ (xs_s[t + 1] - xs_prior[t + 1])
        Ps_s[t] = Ps_post[t] + C @ (Ps_s[t + 1] - Ps_prior[t + 1]) @ C.T
    out = pd.DataFrame(rows)
    out["W_s"] = [v[0] for v in xs_s]
    out["W_s_sd"] = [np.sqrt(v[0, 0]) for v in Ps_s]
    out["T_s"] = [v[1] for v in xs_s]
    out["T_s_sd"] = [np.sqrt(v[1, 1]) for v in Ps_s]
    out["H_s"] = [v[2] for v in xs_s]
    return out, loglik


def summarize(history: pd.DataFrame, since=None, intake_window: int = 14) -> dict:
    """Current TDEE with 95% CI, and the weight-change rate implied by recent intake."""
    h = history if since is None else history[history["date"] >= since]
    last = h.iloc[-1]
    recent = h["intake"].tail(intake_window).dropna()
    out = {"tdee": float(last["T"]), "tdee_ci95": 1.96 * float(last["T_sd"]),
           "tissue_weight": float(last["W"]), "water": float(last["H"]),
           "n_readings": int(h["y"].notna().sum())}
    if not recent.empty:
        out["intake_mean"] = float(recent.mean())
        out["rate_kg_month"] = (out["intake_mean"] - out["tdee"]) / RHO * 30
        out["rate_kg_month_ci95"] = out["tdee_ci95"] / RHO * 30
    return out
