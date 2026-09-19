"""TDEE par composants (modèle empirique réel) + cibles effectives.

TDEE_jour =  BMR
           + NEAT_BASE (non-locomoteur : postures, gestes, tâches)
           + TEF (~10% de l'intake du jour)
           + kcal_pas (depuis le tel)
           + sport (sessions loggées : street, escalade, course…)
           + extra (bonus manuel, ex: D+ rando — généralement 0)

Note : la course est aussi dans les pas, mais le tel la sous-compte
(MET marche), donc l'ajouter compense. Le D+ n'est pas capté par les pas
→ bonus caché (on reste conservateur).
"""
from datetime import date, timedelta
import pandas as pd
from . import storage, nutrition, sport, kalman, weight as weight_mod


def is_bulk(profile: dict | None = None) -> bool:
    """True si l'objectif courant est une prise de masse (surplus visé)."""
    profile = profile or storage.load_profile()
    return profile.get("goal") == "bulk"


CHECKIN_EVERY_DAYS = 7
CHECKIN_MAX_STEP = 150  # kcal max de variation de cible par point (le TDEE bouge avec le bruit)


def _tdee_estimate(profile: dict, bmr: float) -> float | None:
    """TDEE Kalman borné (garde-fou physiologique), sinon composants, sinon None (théorique)."""
    rec = reconciled()
    if rec["ok"]:
        return min(max(rec["tdee"], bmr * 1.2), bmr * 1.9)
    s = summary(window_days=ROLLING_WINDOW_DAYS)
    return s["avg_tdee"] if s["days"] >= MIN_DAYS_FOR_EMPIRICAL else None


def effective_targets() -> dict:
    """Cibles utilisées PARTOUT dans l'app.

    - kcal : FIGÉE au dernier point hebdo validé (storage.load_checkins) — elle ne
      bouge plus à chaque pesée. Sans point hebdo : TDEE + rythme visé, en direct.
    - TDEE affiché : estimation courante (Kalman > composants > théorique)
    - Macros : recalculées sur le poids courant, glucides = le reste
    """
    profile = storage.load_profile()
    weight = storage.current_weight()
    bmr = nutrition.bmr_mifflin(weight, profile["height_cm"], profile["age"], profile["sex"])
    ck = storage.load_checkins()
    kcal = float(ck["target_kcal"].iloc[-1]) if not ck.empty else None
    out = nutrition.effective_targets(profile, weight, _tdee_estimate(profile, bmr), kcal)
    out["checkin_date"] = ck["date"].iloc[-1] if not ck.empty else None
    return out


def checkin_proposal() -> dict:
    """Point hebdo : nouvelle cible = TDEE (Kalman) + rythme visé, variation plafonnée.

    `due` = aucun point encore, ou le dernier date d'au moins CHECKIN_EVERY_DAYS jours.
    """
    profile = storage.load_profile()
    rec = reconciled()
    ck = storage.load_checkins()
    last = ck["date"].iloc[-1] if not ck.empty else None
    due = last is None or (date.today() - last).days >= CHECKIN_EVERY_DAYS
    if not rec["ok"]:
        return {"ok": False, "due": due}
    rate_target = profile.get("target_rate_kg_per_month", 0.0)
    raw = nutrition.target_from_rate(rec["tdee"], rate_target)
    before = float(ck["target_kcal"].iloc[-1]) if not ck.empty else None
    proposed = raw if before is None else before + max(-CHECKIN_MAX_STEP, min(CHECKIN_MAX_STEP, raw - before))
    avg7 = intake_average(date.today(), days=7)
    rs = rate_status(rec, profile)
    return {"ok": True, "due": due, "last": last, "tdee": rec["tdee"], "tdee_ci95": rec["ci95"],
            "rate": rs.get("rate"), "rate_ci95": rs.get("ci95"),
            "intake_7d": avg7["mean"] if avg7 else None,
            "target_before": before, "target_raw": raw, "target_proposed": round(proposed),
            "capped": before is not None and abs(raw - before) > CHECKIN_MAX_STEP}


def validate_checkin(target_kcal: float | None = None) -> None:
    """Fige la cible (proposée, ou une valeur choisie à la main)."""
    p = checkin_proposal()
    storage.log_checkin({
        "date": date.today().isoformat(), "tdee": round(p["tdee"]), "tdee_ci95": round(p["tdee_ci95"]),
        "rate": round(p["rate"], 2) if p["rate"] is not None else None,
        "rate_ci95": round(p["rate_ci95"], 2) if p["rate_ci95"] is not None else None,
        "intake_7d": round(p["intake_7d"]) if p["intake_7d"] else None,
        "target_before": p["target_before"], "target_proposed": p["target_proposed"],
        "target_kcal": round(target_kcal if target_kcal is not None else p["target_proposed"]),
    })


NEAT_BASE = 150        # kcal/j non-locomoteur
TEF_RATE = 0.10        # part de l'intake
KCAL_PER_STEP = 0.031  # kcal/pas, ordre de grandeur d'un compteur de téléphone
DEFAULT_STEPS = 6000   # défaut si pas de données ce jour-là
DEFAULT_STEPS_KCAL = DEFAULT_STEPS * KCAL_PER_STEP  # ~186 kcal

# Rolling window pour s'adapter aux changements de mode de vie
ROLLING_WINDOW_DAYS = 14
MIN_DAYS_FOR_EMPIRICAL = 7  # en dessous on reste sur théorique
# Fenêtre de moyenne de F et A pour calibrer k
RECONCILE_WINDOW_DAYS = 21

# --- Calibration k de la partie ACTIVITÉ du TDEE composants ---
# On scale UNIQUEMENT la partie estimée A (NEAT+pas+sport), pas F (BMR+TEF).
#   TDEE_corrigé = F + k·A
# k auto = (réconcilié − moy F)/moy A si dans une plage saine, sinon k FIXE.
# Prior 1.0 (neutre) quand le TDEE balance n'est pas encore disponible.
FIXED_K = 1.0
K_SANE = (0.60, 1.40)


def reconcile_k(window_days: int = RECONCILE_WINDOW_DAYS) -> dict:
    """Facteur k de correction de l'activité. {k, source, auto_k}."""
    tbl = complete_days(build_energy_table())
    rec = reconciled()
    if tbl.empty or not rec["ok"]:
        return {"k": FIXED_K, "source": "fixed", "auto_k": None}
    last = tbl["date"].max()
    win = tbl[tbl["date"] >= last - timedelta(days=window_days)]
    mean_f = float((win["bmr"] + win["tef"]).mean())
    mean_a = float((win["neat"] + win["steps_kcal"] + win["sport_kcal"]).mean())
    if mean_a <= 0:
        return {"k": FIXED_K, "source": "fixed", "auto_k": None}
    auto = (rec["tdee"] - mean_f) / mean_a
    if K_SANE[0] <= auto <= K_SANE[1]:
        return {"k": auto, "source": "auto", "auto_k": auto}
    return {"k": FIXED_K, "source": "fixed", "auto_k": auto}


def corrected_energy_table() -> pd.DataFrame:
    """build_energy_table + colonnes corrigées par k (TDEE/net/cumul)."""
    tbl = build_energy_table()
    if tbl.empty:
        return tbl
    k = reconcile_k()["k"]
    tbl = tbl.copy()
    a = tbl["neat"] + tbl["steps_kcal"] + tbl["sport_kcal"]
    tbl["tdee"] = tbl["bmr"] + tbl["tef"] + k * a
    tbl["net"] = tbl["intake"] - tbl["tdee"]
    tbl["cumul_net"] = tbl["net"].cumsum()
    return tbl


def reconciled() -> dict:
    """TDEE réconcilié sur la balance, par filtre de Kalman (core/kalman.py).

    {ok, tdee, tdee_sd, ci95, weight, water, rate_kg_month(_sd), n_obs, span_days,
     history, window_days (= jours de phase couverts)}.
    """
    rec = kalman.estimate(phase_start_date())
    rec["window_days"] = rec.get("n_days", 0)
    return rec


def daily_tdee(bmr: float, intake: float, steps_kcal: float,
               sport_kcal: float, extra_kcal: float = 0) -> float:
    return bmr + NEAT_BASE + TEF_RATE * intake + steps_kcal + sport_kcal + extra_kcal


def _sum_sport_kcal(sp: pd.DataFrame) -> float:
    """Somme kcal sport, en excluant les sessions déjà comptées dans les pas
    (ex: course avec tel porté)."""
    if sp.empty:
        return 0.0
    if "counted_in_steps" in sp.columns:
        sp = sp[~sp["counted_in_steps"].fillna(False).astype(bool)]
    return float(sp["kcal_burned"].sum()) if not sp.empty else 0.0


def phase_start_date(profile: dict | None = None) -> date | None:
    """Date de début de la phase courante (ex: retour France + lancement bulk).

    Sert de PLANCHER pour tout ce qui est cumulé/calibré sur une période
    (cumul net, TDEE réconcilié, moyennes glissantes) : sans ça, une fenêtre
    ou un cumul depuis "le début du suivi" mélange l'ancienne phase avec la
    courante. `bulk_start_date` du profil fait office d'ancrage."""
    profile = profile or storage.load_profile()
    raw = profile.get("bulk_start_date")
    return date.fromisoformat(raw) if raw else None


def build_energy_table() -> pd.DataFrame:
    """Table jour par jour : intake, composants TDEE, déficit, cumul.

    Le BMR SUIT le poids dans le temps (interpolé depuis les pesées lissées) —
    sinon on appliquerait le poids d'aujourd'hui à des jours d'il y a 3 mois.
    Bornée à `phase_start_date()` : tout ce qui est cumulé/calibré ici (cumul
    net, TDEE réconcilié, moyennes glissantes) démarre à la phase courante,
    jamais avant — sinon on remélange avec l'ancienne phase.
    """
    profile = storage.load_profile()

    foods = storage.load_foods()
    meals = storage.load_meals()
    sessions = storage.load_sessions()
    steps = storage.load_steps()

    m = nutrition.meal_macros(meals, foods)
    daily = nutrition.daily_totals(m)
    if daily.empty:
        return pd.DataFrame()

    daily = daily.sort_values("date")
    anchor = phase_start_date(profile)
    if anchor is not None:
        daily = daily[daily["date"] >= anchor]
    if daily.empty:
        return pd.DataFrame()
    # poids estimé pour chaque jour → BMR qui évolue avec le poids réel
    w_series = weight_mod.weight_on_dates(storage.load_weight(), daily["date"])
    fallback_w = storage.current_weight()

    rows = []
    cum = 0.0
    for _, r in daily.iterrows():
        d = r["date"]
        intake = r["kcal"]
        w_day = w_series.get(pd.Timestamp(d), float("nan"))
        if pd.isna(w_day):
            w_day = fallback_w
        bmr = nutrition.bmr_mifflin(float(w_day), profile["height_cm"],
                                    profile["age"], profile["sex"])
        # steps (défaut 6000 pas si pas de données ce jour-là)
        s = steps[steps["date"] == d] if not steps.empty else pd.DataFrame()
        if not s.empty:
            steps_kcal = float(s["steps_kcal"].sum())
            extra_kcal = float(s["extra_kcal"].sum())
            n_steps = int(s["steps"].sum())
            steps_default = False
        else:
            steps_kcal = DEFAULT_STEPS_KCAL
            extra_kcal = 0.0
            n_steps = DEFAULT_STEPS
            steps_default = True
        # sport (kcal figée — exclut les sessions déjà comptées dans les pas)
        sp = sessions[sessions["date"] == d] if not sessions.empty else pd.DataFrame()
        sport_kcal = _sum_sport_kcal(sp)
        # tdee
        tef = TEF_RATE * intake
        tdee = daily_tdee(bmr, intake, steps_kcal, sport_kcal, extra_kcal)
        # CONVENTION UNIVERSELLE : net = intake − tdee
        #   net < 0 = déficit = on perd du gras ✅ (objectif cut)
        #   net > 0 = surplus = on prend du gras 🟠
        net = intake - tdee
        cum += net
        rows.append({
            "date": d, "intake": intake, "bmr": bmr, "tef": tef,
            "neat": NEAT_BASE, "steps": n_steps, "steps_kcal": steps_kcal,
            "steps_default": steps_default,
            "sport_kcal": sport_kcal, "tdee": tdee,
            "net": net, "cumul_net": cum,
        })
    return pd.DataFrame(rows)


RATE_ZONE = (-0.2, 0.3)  # zone acceptable autour du rythme visé (0.5 → 0.3-0.8 kg/mois)


def rate_status(rec: dict | None = None, profile: dict | None = None) -> dict:
    """Rythme de prise/perte (Kalman, à l'intake des 14 derniers jours) vs rythme visé.

    SEULE source de "est-ce que je suis dans le rythme" : bandeau, accueil, Tendances.
    zone : 'in' (dans la zone visée), 'above' / 'below' ; significant = l'IC95 exclut la zone.
    """
    profile = profile or storage.load_profile()
    rec = rec if rec is not None else reconciled()
    target = profile.get("target_rate_kg_per_month")
    rate = rec.get("rate_kg_month") if rec.get("ok") else None
    if rate is None or target is None:
        return {"ok": False, "target": target}
    ci = 1.96 * rec["rate_kg_month_sd"]
    lo_z, hi_z = target + RATE_ZONE[0], target + RATE_ZONE[1]
    zone = "in" if lo_z <= rate <= hi_z else ("above" if rate > hi_z else "below")
    significant = (rate - ci > hi_z) if zone == "above" else (rate + ci < lo_z) if zone == "below" else False
    return {"ok": True, "rate": rate, "ci95": ci, "target": target,
            "zone_lo": lo_z, "zone_hi": hi_z, "zone": zone, "significant": significant,
            "direction_known": rate - ci > 0 or rate + ci < 0}


def bulk_trajectory(rec: dict | None = None, profile: dict | None = None) -> dict:
    """Poids hors eau (lissage Kalman) depuis le début de phase vs ligne du rythme visé.
    Départ = poids lissé au 1er jour de phase (plus de pesée brute choisie à la main)."""
    profile = profile or storage.load_profile()
    rec = rec if rec is not None else reconciled()
    target = profile.get("target_rate_kg_per_month")
    if not rec.get("ok") or target is None:
        return {"ok": False}
    h = rec["history"]
    days = pd.Series([(d - h["date"].iloc[0]).days for d in h["date"]], index=h.index)
    expected = h["W_s"].iloc[0] + target / 30.0 * days
    return {"ok": True, "dates": h["date"].tolist(), "actual": h["W_s"].tolist(),
            "actual_sd": h["W_s_sd"].tolist(), "expected": expected.tolist(),
            "gap_kg": float(h["W_s"].iloc[-1] - expected.iloc[-1]),
            "start_weight": float(h["W_s"].iloc[0])}


def cap_summary() -> dict:
    """Bandeau CAP (visible partout) : poids hors eau · rythme ±IC · cible active."""
    rec = reconciled()
    rs = rate_status(rec)
    tg = effective_targets()
    return {
        "weight": rec.get("weight"),
        "rate": rs,
        "target_kcal": tg["kcal"],
        "bulking": is_bulk(),
    }


def intake_average(end: date, days: int = 7) -> dict | None:
    """Moyenne/écart-type de l'intake loggé sur les `days` jours complets AVANT `end`.
    C'est la régularité qui compte, pas un jour isolé."""
    m = nutrition.daily_totals(nutrition.meal_macros(storage.load_meals(), storage.load_foods()))
    if m.empty:
        return None
    win = m[(m["date"] < min(end, date.today())) & (m["date"] >= end - timedelta(days=days))]
    if win.empty:
        return None
    return {"mean": float(win["kcal"].mean()), "sd": float(win["kcal"].std(ddof=1)) if len(win) > 1 else 0.0,
            "n": int(len(win))}


def estimated_share(d) -> float:
    """Part (0-1) des kcal du jour venant d'aliments à faible confiance (estim).

    Sert à savoir quand un total est fragile (journée resto/voyage) vs solide
    (maison, aliments label/base officielle)."""
    foods = storage.load_foods()
    meals = storage.load_meals()
    day = meals[meals["date"] == d] if not meals.empty else meals
    if day.empty:
        return 0.0
    m = day.merge(foods[["food_id", "source", "kcal_100g"]],
                  on="food_id", how="left")
    m["kcal"] = m["kcal_100g"].fillna(0) * m["qty_g"] / 100
    tot = float(m["kcal"].sum())
    if tot <= 0:
        return 0.0
    low = float(m[m["source"].apply(storage.food_confidence) == "low"]["kcal"].sum())
    return low / tot


def day_energy(d) -> dict:
    """Énergie pour une date précise (dépenses / rentrées / net).

    net = rentrées − dépenses  (négatif = déficit = perte de gras)
    """
    profile = storage.load_profile()
    bmr = nutrition.bmr_mifflin(storage.current_weight(), profile["height_cm"],
                                profile["age"], profile["sex"])
    foods = storage.load_foods()
    meals = storage.load_meals()
    sessions = storage.load_sessions()
    steps = storage.load_steps()

    day_meals = meals[meals["date"] == d] if not meals.empty else meals
    mm = nutrition.meal_macros(day_meals, foods)
    intake = float(mm["kcal"].sum()) if not mm.empty else 0.0

    s = steps[steps["date"] == d] if not steps.empty else pd.DataFrame()
    if not s.empty:
        steps_kcal = float(s["steps_kcal"].sum())
        extra_kcal = float(s["extra_kcal"].sum())
        n_steps = int(s["steps"].sum())
        steps_default = False
    else:
        steps_kcal = DEFAULT_STEPS_KCAL
        extra_kcal = 0.0
        n_steps = DEFAULT_STEPS
        steps_default = True

    sp = sessions[sessions["date"] == d] if not sessions.empty else pd.DataFrame()
    sport_kcal = _sum_sport_kcal(sp)

    # TDEE = F (BMR+TEF, fiable) + k·A (NEAT+pas+sport, surestimé → corrigé)
    tef = TEF_RATE * intake
    f = bmr + tef
    a = NEAT_BASE + steps_kcal + sport_kcal + extra_kcal
    k = reconcile_k()["k"]
    tdee_raw = f + a
    tdee = f + k * a
    return {
        "intake": intake, "tdee": tdee, "net": intake - tdee,
        "tdee_raw": tdee_raw, "k": k,
        "bmr": bmr, "neat": NEAT_BASE, "tef": tef,
        "steps": n_steps, "steps_kcal": steps_kcal, "steps_default": steps_default,
        "sport_kcal": sport_kcal,
    }


def complete_days(tbl: pd.DataFrame) -> pd.DataFrame:
    """Exclut le jour EN COURS (repas pas encore tous loggés).

    Sinon toute moyenne glissante est tirée vers le bas le matin (intake partiel
    → TEF partiel → TDEE sous-estimé → cible sous-estimée), au moment précis où
    on consulte sa cible.
    """
    if tbl.empty:
        return tbl
    return tbl[tbl["date"] < date.today()]


def rolling_window(tbl: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Fenêtre CALENDAIRE des N derniers jours complets.

    Volontairement pas un `tail(N)` : avec les trous de logging (vacances), les
    N dernières LIGNES peuvent remonter à 1 mois et mélanger deux phases
    (ex : des jours d'une phase de perte mélangés à une prise de masse).
    """
    done = complete_days(tbl)
    if done.empty:
        return done
    last = done["date"].max()
    return done[done["date"] >= last - timedelta(days=window_days - 1)]


def summary(window_days: int | None = None) -> dict:
    """Résumé énergétique. Convention universelle : − = déficit · + = surplus.

    - cumul_net / fat_kg : sur TOUT l'historique (depuis le début du suivi)
    - avg_* : si window_days passé, moyennes sur les N derniers jours
              CALENDAIRES complets (sinon sur tout l'historique complet)
    TDEE/net/cumul corrigés par k (cohérent avec l'accueil et le tab Énergie).
    """
    tbl = corrected_energy_table()
    if tbl.empty:
        return {"days": 0, "window_days": 0, "span_days": 0, "cumul_net": 0,
                "fat_kg": 0, "avg_tdee": 0, "avg_intake": 0, "avg_net": 0}
    cum = float(tbl["cumul_net"].iloc[-1])
    win = rolling_window(tbl, window_days) if window_days else complete_days(tbl)
    if win.empty:
        win = tbl
    span = int((win["date"].max() - win["date"].min()).days) + 1
    return {
        "days": len(tbl),
        "window_days": len(win),
        "span_days": span,
        "cumul_net": cum,
        "fat_kg": cum / 7700,
        "avg_tdee": float(win["tdee"].mean()),
        "avg_intake": float(win["intake"].mean()),
        "avg_net": float(win["net"].mean()),
    }
