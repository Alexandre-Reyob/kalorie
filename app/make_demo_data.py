"""Génère un jeu de données de démo : 70 jours d'un utilisateur synthétique en prise de masse.

Poids et apports viennent du simulateur de la librairie (vérité connue) ; les apports sont
traduits en repas à partir d'aliments génériques. Écrit dans TRACKER_DATA (défaut app/data).
"""
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from core import sport, storage  # noqa: E402
from tdee import SimConfig, simulate_user  # noqa: E402

DAYS = 70
DAY_TEMPLATE = {
    "petit_déj": [("flocons_avoine", 60), ("skyr_nature", 200), ("banane", 120)],
    "déjeuner": [("poulet_(escalope_crue)", 180), ("riz_blanc_cuit", 250), ("brocoli", 150), ("huile_d'olive", 10)],
    "collation": [("pain_complet", 60), ("pomme", 150)],
    "dîner": [("œuf_entier", 150), ("pâtes_cuites", 250), ("huile_d'olive", 10)],
}


def main(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    end = date.today()
    start = end - timedelta(days=DAYS - 1)
    cfg = SimConfig(days=DAYS, tdee_range=(2550, 2750), w0_range=(70, 73), surplus_mean=150,
                    start=start.isoformat())
    inputs, _ = simulate_user(cfg, rng)

    storage.DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(__file__).parent / "seed" / "foods.csv", storage.FOODS)
    foods = storage.load_foods().set_index("food_id")
    template_kcal = sum(foods.loc[f, "kcal_100g"] * q / 100 for items in DAY_TEMPLATE.values() for f, q in items)

    meals = []
    for r in inputs.itertuples(index=False):
        if pd.isna(r.intake):
            continue
        k = r.intake / template_kcal
        slots = ["petit_déj"] if r.date == end else DAY_TEMPLATE  # jour en cours : partiel
        for meal in slots:
            for food, q in DAY_TEMPLATE[meal]:
                meals.append({"date": r.date, "meal": meal, "food_id": food, "qty_g": round(q * k / 5) * 5})
    pd.DataFrame(meals).to_csv(storage.MEALS, index=False)

    w = inputs.dropna(subset=["weight_kg"])
    pd.DataFrame({"date": w["date"], "weight_kg": w["weight_kg"].round(2), "moment": "matin",
                  "notes": ""}).to_csv(storage.WEIGHT, index=False)

    days = [start + timedelta(days=i) for i in range(DAYS)]
    steps = np.clip(rng.normal(9000, 2500, DAYS), 3000, 18000).astype(int)
    pd.DataFrame({"date": days, "steps": steps, "steps_kcal": (steps * 0.031).round(),
                  "extra_kcal": 0}).to_csv(storage.STEPS, index=False)

    sessions, exos = [], []
    for i, d in enumerate(days):
        wd = d.weekday()
        if wd in (0, 3):
            sessions.append(("escalade", 90, sport.MET_ACTIF["escalade"], sport.ACTIVE_FRACTION_DEFAULT["escalade"], d))
        elif wd in (1, 5):
            sessions.append(("street_workout", 45, sport.MET_ACTIF["street_workout"], 1.0, d))
            lest = 2.5 * (i // 14)
            for exo, reps in (("Pull-up", 8), ("Dip", 10)):
                for s in (1, 2, 3):
                    exos.append({"date": d, "exo": exo, "set_num": s, "reps": reps - (s - 1),
                                 "weight_kg": lest, "duration_sec": 0, "notes": ""})
    pd.DataFrame([{"date": d, "type": t, "duration_min": m,
                   "kcal_burned": sport.session_kcal(met, fr, 72.0, m), "met": met, "active_fraction": fr,
                   "distance_km": None, "counted_in_steps": False, "summary": "", "notes": ""}
                  for t, m, met, fr, d in sessions]).to_csv(storage.SESSIONS, index=False)
    pd.DataFrame(exos).to_csv(storage.EXOS, index=False)
    pd.DataFrame(columns=["date", "skill", "value", "unit", "notes"]).to_csv(storage.SKILLS, index=False)
    pd.DataFrame({"date": days[::7], "waist_cm": (80 + 0.1 * np.arange(len(days[::7]))
                                                  + rng.normal(0, 0.3, len(days[::7]))).round(1),
                  "notes": ""}).to_csv(storage.MEASURES, index=False)
    storage.TEMPLATES.write_text("[]")
    storage.PROFILE.write_text(json.dumps({
        "name": "Démo", "sex": "M", "age": 28, "height_cm": 180, "weight_kg": 71.5,
        "goal_weight_kg": 76.0, "activity_factor": 1.5, "goal": "bulk",
        "protein_g_per_kg": 2.0, "protein_g_per_kg_min": 1.6,
        "fat_g_per_kg": 0.9, "fat_g_per_kg_min": 0.7,
        "bulk_start_date": start.isoformat(), "target_rate_kg_per_month": 0.5,
    }, indent=2, ensure_ascii=False))
    print(f"Données de démo écrites dans {storage.DATA}")


if __name__ == "__main__":
    main()
