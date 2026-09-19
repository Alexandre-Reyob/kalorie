"""Adaptateur app → librairie `tdee` : construit la série quotidienne depuis les CSV
et appelle le filtre de Kalman (src/tdee/model.py). Aucune logique de filtre ici."""
from datetime import date, timedelta

import pandas as pd

from tdee import DEFAULT, Params, run as tdee_run
from . import storage, nutrition, weight as weight_mod

RHO = 7700.0
MIN_OBS = 5
MIN_SPAN_DAYS = 7


def _daily_intake() -> pd.DataFrame:
    """[date, intake, est_share] par jour loggé (hors jour en cours, incomplet)."""
    foods, meals = storage.load_foods(), storage.load_meals()
    if meals.empty:
        return pd.DataFrame(columns=["date", "intake", "est_share"])
    m = nutrition.meal_macros(meals, foods).merge(
        foods[["food_id", "source"]], on="food_id", how="left")
    m["low"] = m["source"].apply(storage.food_confidence) == "low"
    m["kcal_low"] = m["kcal"].where(m["low"], 0.0)
    d = m.groupby("date")[["kcal", "kcal_low"]].sum().reset_index()
    d = d[d["date"] < date.today()]
    d["est_share"] = (d["kcal_low"] / d["kcal"]).where(d["kcal"] > 0, 0.0)
    return d.rename(columns={"kcal": "intake"})[["date", "intake", "est_share"]]


def inputs() -> pd.DataFrame:
    u = weight_mod._unified_series(storage.load_weight())
    it = _daily_intake()
    starts = [s for s in (u["date"].min() if not u.empty else None,
                          it["date"].min() if not it.empty else None) if s is not None]
    if not starts:
        return pd.DataFrame(columns=["date", "weight_kg", "intake"])
    start, end = min(starts), date.today()
    days = pd.DataFrame({"date": [start + timedelta(days=i) for i in range((end - start).days + 1)]})
    df = days.merge(u, on="date", how="left").merge(it, on="date", how="left")
    df["from_evening"] = df["from_evening"].eq(True)
    df["noted"] = df["noted"].eq(True)
    df["est_share"] = df["est_share"].fillna(0.0)
    return df


def _prior_tdee(first_weight: float) -> float:
    prof = storage.load_profile()
    bmr = nutrition.bmr_mifflin(first_weight, prof["height_cm"], prof["age"], prof["sex"])
    return nutrition.tdee(bmr, prof["activity_factor"])


def estimate(phase_start: date | None, p: Params = DEFAULT) -> dict:
    """TDEE au matin d'aujourd'hui + IC95. Tourne sur tout l'historique mais regonfle
    l'incertitude à `phase_start` (l'ancienne phase ne sert plus que de prior lâche)."""
    df = inputs()
    obs0 = df["weight_kg"].dropna() if not df.empty else pd.Series(dtype=float)
    if obs0.empty:
        return {"ok": False, "tdee": None}
    breaks = (phase_start,) if phase_start else ()
    full, _ = tdee_run(df, p, _prior_tdee(float(obs0.iloc[0])), breaks)
    hist = full[full["date"] >= phase_start] if phase_start else full
    obs = hist.dropna(subset=["y"])
    span = (obs["date"].max() - obs["date"].min()).days if not obs.empty else 0
    last = hist.iloc[-1]
    recent = hist[hist["date"] >= hist["date"].max() - timedelta(days=14)]["intake"].dropna()
    intake_mean = float(recent.mean()) if not recent.empty else None
    out = {
        "ok": len(obs) >= MIN_OBS and span >= MIN_SPAN_DAYS,
        "tdee": float(last["T"]), "tdee_sd": float(last["T_sd"]),
        "ci95": 1.96 * float(last["T_sd"]),
        "weight": float(last["W"]), "weight_sd": float(last["W_sd"]),
        "water": float(last["H"]),
        "n_obs": int(len(obs)), "n_days": int(len(hist)), "span_days": int(span),
        "intake_mean": intake_mean, "history": hist, "full_history": full,
    }
    if intake_mean is not None:
        out["rate_kg_month"] = (intake_mean - out["tdee"]) / RHO * 30
        out["rate_kg_month_sd"] = out["tdee_sd"] / RHO * 30
    return out
