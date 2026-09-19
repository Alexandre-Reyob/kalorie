"""Poids unifié "équivalent matin", EMA (pour interpoler le BMR) et ETA.

Le poids brut matin/soir est très bruité (±1 à 2.5 kg : eau, sel, glycogène,
contenu digestif). On unifie matin/soir en "équivalent matin" (le soir est
décalé de l'offset moyen observé) puis on lisse par EMA.
Le TDEE déduit de la balance est dans core/kalman.py (qui appelle la librairie tdee) (pas ici).
"""
import pandas as pd


HALFLIFE_DAYS = 5.0      # demi-vie de l'EMA (compromis réactivité / lissage)


def _unified_series(weight_df: pd.DataFrame) -> pd.DataFrame:
    """Une valeur de poids par jour, ramenée en équivalent MATIN.

    - jour avec pesée matin → on prend le matin (référence à jeun)
    - jour avec seulement soir → soir − offset moyen (soir−matin)
    Retourne un df trié [date, weight_kg, from_evening, noted] (noted = la pesée
    retenue a une note de contexte, ex. "après petit-déj").
    """
    if weight_df.empty:
        return pd.DataFrame(columns=["date", "weight_kg", "from_evening", "noted"])
    piv = weight_df.pivot_table(index="date", columns="moment",
                                values="weight_kg", aggfunc="first")
    notes = {}
    if "notes" in weight_df.columns:
        has = weight_df[weight_df["notes"].fillna("").astype(str).str.strip() != ""]
        notes = {(r["date"], r["moment"]) for _, r in has.iterrows()}
    # offset moyen soir−matin sur les jours appariés (sinon 0)
    offset = 0.0
    if "matin" in piv.columns and "soir" in piv.columns:
        paired = piv.dropna(subset=["matin", "soir"])
        if len(paired) >= 3:
            offset = float((paired["soir"] - paired["matin"]).mean())
    rows = []
    for d, r in piv.iterrows():
        if "matin" in piv.columns and pd.notna(r.get("matin")):
            rows.append({"date": d, "weight_kg": float(r["matin"]),
                         "from_evening": False, "noted": (d, "matin") in notes})
        elif "soir" in piv.columns and pd.notna(r.get("soir")):
            rows.append({"date": d, "weight_kg": float(r["soir"]) - offset,
                         "from_evening": True, "noted": (d, "soir") in notes})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def smoothed_series(weight_df: pd.DataFrame,
                    halflife_days: float = HALFLIFE_DAYS) -> pd.DataFrame:
    """Série lissée EMA (équivalent matin). Colonnes : date, weight_kg, ema."""
    u = _unified_series(weight_df)
    if u.empty:
        u["ema"] = []
        return u
    times = pd.to_datetime(u["date"])
    u["ema"] = (u["weight_kg"]
                .ewm(halflife=f"{halflife_days} days", times=times).mean())
    return u


def weight_on_dates(weight_df: pd.DataFrame, dates) -> pd.Series:
    """Poids lissé (EMA) estimé pour chaque date demandée.

    Interpolation linéaire entre les pesées, extrapolation plate aux bords.
    Sert à calculer un BMR qui SUIT le poids dans le temps (sinon on applique
    le poids d'aujourd'hui à des jours où on pesait 3 kg de plus).
    Retourne une Series indexée comme `dates` (NaN si aucune pesée du tout).
    """
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    ema = smoothed_series(weight_df)
    if ema.empty:
        return pd.Series([float("nan")] * len(idx), index=idx)
    s = pd.Series(ema["ema"].to_numpy(dtype=float),
                  index=pd.DatetimeIndex(pd.to_datetime(ema["date"])))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    # union des index → interpolation temporelle → on relit sur les dates voulues
    merged = s.reindex(s.index.union(idx)).interpolate(method="time")
    return merged.ffill().bfill().reindex(idx)


def eta_to_goal(smoothed_now: float, slope_kg_per_week: float,
                goal_kg: float, reliable: bool = True,
                target_rate_kg_per_month: float | None = None) -> dict:
    """Estime le délai jusqu'à l'objectif.

    Deux régimes :
    - pente MESURÉE fiable → on projette dessus (`source='mesuré'`)
    - pente pas fiable (peu de pesées, bruit d'eau) → on projette sur le
      RYTHME VISÉ si fourni (`source='rythme visé'`). Projeter une pente de
      7 jours de pesées donnait des ETA absurdes (ex: "+5.5 kg en 7 semaines"
      extrapolé d'un pic d'eau post-resto).

    Retourne {weeks, reachable, source}.
    """
    if smoothed_now is None:
        return {"weeks": None, "reachable": False, "source": None}
    delta = goal_kg - smoothed_now              # <0 si on veut descendre

    use_measured = reliable and slope_kg_per_week != 0 and delta * slope_kg_per_week > 0
    if use_measured:
        return {"weeks": abs(delta / slope_kg_per_week), "reachable": True,
                "source": "mesuré"}

    if target_rate_kg_per_month:
        target_week = target_rate_kg_per_month / 30.0 * 7
        if delta * target_week > 0:
            return {"weeks": abs(delta / target_week), "reachable": True,
                    "source": "rythme visé"}
    return {"weeks": None, "reachable": False, "source": None}
