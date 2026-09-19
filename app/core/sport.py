"""Calculs sport — MET, kcal brûlées, PR, allure."""
import pandas as pd

# MET actif par discipline. Source: Compendium of Physical Activities 2024.
# Pour les activités intermittentes (escalade), active_fraction × MET_ACTIF + (1-fraction) × MET_REPOS
MET_ACTIF = {
    "escalade":       8.8,   # indoor bouldering (Compendium 2024)
    "course":         9.5,   # course modérée ~10-11 km/h
    "street_workout": 7.0,   # calisthenics vigorous
    "corde_a_sauter": 11.0,
}
MET_REPOS = 2.0  # assis/debout au repos entre les blocs

# Fraction active par défaut (temps réel d'effort / durée totale)
ACTIVE_FRACTION_DEFAULT = {
    "escalade":       0.5,   # ~50% actif en bouldering (bloc joué intensément)
    "course":         1.0,
    "street_workout": 1.0,
    "corde_a_sauter": 1.0,
}

# Compat legacy
MET = {k: MET_ACTIF[k] * ACTIVE_FRACTION_DEFAULT[k] + MET_REPOS * (1 - ACTIVE_FRACTION_DEFAULT[k])
       for k in MET_ACTIF}

# Liste d'exos suggérée pour autocomplete (l'utilisateur peut taper n'importe quoi)
EXOS_SUGGESTED = [
    # --- Tirage ---
    "Pull-up", "Chin-up", "Wide pull-up", "Archer pull-up",
    "Muscle-up", "Muscle-up négatif", "L-sit pull-up",
    # --- Poussée vertic ---
    "Pike push-up", "Handstand hold", "Wall HSPU", "Free HSPU", "HSPU négatif",
    # --- Poussée horiz ---
    "Push-up", "Diamond push-up", "Archer push-up", "Pseudo-planche push-up",
    "Ring dip", "Dip", "Bench dip",
    # --- Jambes ---
    "Squat", "Pistol squat", "Bulgarian split squat", "Jump squat",
    # --- Core / statique ---
    "L-sit", "Tuck planche", "Straddle planche", "Front lever tuck",
    "Front lever advanced", "Back lever", "Plank", "Hollow body hold",
    # --- Cardio / accessoires ---
    "Corde à sauter", "Burpees", "Mountain climbers",
]


def session_kcal(met_actif: float, active_fraction: float,
                 weight_kg: float, duration_min: float) -> float:
    """kcal dynamique : (MET_actif × fraction + MET_repos × (1-fraction)) × poids × heures."""
    effective_met = met_actif * active_fraction + MET_REPOS * (1 - active_fraction)
    return effective_met * weight_kg * (duration_min / 60.0)


def kcal_burned(activity: str, weight_kg: float, duration_min: float) -> float:
    """Legacy — utiliser session_kcal() pour les nouveaux logs."""
    met = MET_ACTIF.get(activity, 7.0)
    frac = ACTIVE_FRACTION_DEFAULT.get(activity, 1.0)
    return session_kcal(met, frac, weight_kg, duration_min)


def pace_str(distance_km: float, duration_min: float) -> str:
    """Allure au format 'min:ss / km'."""
    if not distance_km or distance_km <= 0:
        return "-"
    pace_min = duration_min / distance_km
    m = int(pace_min)
    s = int(round((pace_min - m) * 60))
    return f"{m}:{s:02d} / km"


def exo_pr(exos_df: pd.DataFrame, exo: str) -> dict:
    """PR pour un exo donné.
    - max_weight: poids max (avec reps>=1)
    - max_reps_bw: max reps au poids du corps (weight_kg = 0 ou NaN)
    - max_reps_at_max_weight: meilleur reps au poids max
    """
    if exos_df.empty:
        return {"max_weight": None, "max_reps_bw": None, "max_reps_at_max_weight": None}
    sub = exos_df[exos_df["exo"] == exo].copy()
    if sub.empty:
        return {"max_weight": None, "max_reps_bw": None, "max_reps_at_max_weight": None}
    sub["weight_kg"] = pd.to_numeric(sub["weight_kg"], errors="coerce").fillna(0)
    sub["reps"] = pd.to_numeric(sub["reps"], errors="coerce").fillna(0)
    bw = sub[sub["weight_kg"] == 0]
    return {
        "max_weight": float(sub["weight_kg"].max()) if not sub.empty else None,
        "max_reps_bw": int(bw["reps"].max()) if not bw.empty else None,
        "max_reps_at_max_weight": int(sub.loc[sub["weight_kg"].idxmax(), "reps"])
                                  if not sub.empty else None,
    }


def best_sets(exos_df: pd.DataFrame) -> pd.DataFrame:
    """Meilleure série par (date, exo) : lest le plus lourd, puis le plus de reps.
    (Pas d'e1RM : les séries à 30-50 reps de callisthénie sortent du domaine d'Epley.)"""
    if exos_df.empty:
        return pd.DataFrame(columns=["date", "exo", "reps", "weight_kg"])
    df = exos_df.copy()
    df["reps"] = pd.to_numeric(df["reps"], errors="coerce").fillna(0).astype(int)
    df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce").fillna(0.0)
    df = df[df["reps"] > 0].sort_values(["date", "exo", "weight_kg", "reps"])
    return df.groupby(["date", "exo"]).tail(1)[["date", "exo", "reps", "weight_kg"]] \
             .sort_values(["exo", "date"]).reset_index(drop=True)


def strength_summary(exos_df: pd.DataFrame, today, recent_days: int = 21) -> dict:
    """Dernière meilleure série par exo travaillé récemment, comparée au record d'avant.
    {last_date, exos: [{exo, reps, weight_kg, date, vs}]} ; vs = "lest +2.5 kg", "+3 reps", "=" ou None."""
    bs = best_sets(exos_df)
    if bs.empty:
        return {"last_date": None, "exos": []}
    out = []
    for exo, g in bs[bs["date"] >= today - pd.Timedelta(days=recent_days)].groupby("exo"):
        last = g.iloc[-1]
        prev = bs[(bs["exo"] == exo) & (bs["date"] < last["date"])]
        vs = None
        if not prev.empty:
            rec = prev.sort_values(["weight_kg", "reps"]).iloc[-1]
            if last["weight_kg"] != rec["weight_kg"]:
                vs = f"lest {last['weight_kg'] - rec['weight_kg']:+.1f} kg"
            else:
                vs = f"{int(last['reps'] - rec['reps']):+d} reps" if last["reps"] != rec["reps"] else "="
        out.append({"exo": exo, "reps": int(last["reps"]), "weight_kg": float(last["weight_kg"]),
                    "date": last["date"], "vs": vs})
    return {"last_date": bs["date"].max(), "exos": sorted(out, key=lambda r: r["exo"])}


def weekly_volume(sessions_df: pd.DataFrame, weight_kg: float = 69.0) -> pd.DataFrame:
    """Volume hebdo: minutes + kcal par discipline.

    kcal = kcal_burned figée si dispo, sinon recalcul depuis le MET.
    Les sessions counted_in_steps (course tel porté) comptent 0 kcal
    (mais gardent leur durée pour le volume).
    """
    if sessions_df.empty:
        return pd.DataFrame()
    df = sessions_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if "kcal_burned" in df.columns:
        df["kcal"] = df["kcal_burned"].fillna(
            df.apply(lambda r: session_kcal(r["met"], r["active_fraction"],
                                            weight_kg, r["duration_min"]), axis=1))
    else:
        df["kcal"] = df.apply(
            lambda r: session_kcal(r["met"], r["active_fraction"], weight_kg, r["duration_min"]),
            axis=1)
    if "counted_in_steps" in df.columns:
        df.loc[df["counted_in_steps"].fillna(False).astype(bool), "kcal"] = 0.0
    agg = (df.groupby(["week", "type"])
             .agg(duration_min=("duration_min", "sum"),
                  kcal=("kcal", "sum"),
                  count=("type", "size"))
             .reset_index())
    return agg
