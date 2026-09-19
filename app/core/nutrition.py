"""BMR, TDEE, macros et agrégation des repas."""
import pandas as pd


def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex.upper() == "M" else -161)


def tdee(bmr: float, activity_factor: float) -> float:
    return bmr * activity_factor


def target_from_rate(tdee_val: float, rate_kg_per_month: float) -> float:
    """Cible = TDEE + surplus du rythme visé (0.5 kg/mois → +128 kcal/j)."""
    return tdee_val + rate_kg_per_month * 7700 / 30


def effective_targets(profile: dict, current_weight: float,
                       tdee_empirical: float | None = None,
                       kcal: float | None = None) -> dict:
    """Cibles basées sur le poids COURANT.

    - TDEE : empirique si fourni, sinon théorique (poids courant × activity_factor)
    - Cible kcal : `kcal` si fournie (cible figée au dernier point hebdo),
      sinon TDEE + rythme visé
    - Macros : g/kg × poids courant, planchers idem ; glucides = le reste
    """
    bmr = bmr_mifflin(current_weight, profile["height_cm"],
                      profile["age"], profile["sex"])
    if tdee_empirical is not None:
        td = tdee_empirical
        source = "empirical"
    else:
        td = tdee(bmr, profile["activity_factor"])
        source = "theoretical"
    if kcal is None:
        kcal = target_from_rate(td, profile.get("target_rate_kg_per_month", 0.0))
    w = current_weight
    p_max = profile["protein_g_per_kg"] * w
    p_min = profile.get("protein_g_per_kg_min", 1.6) * w
    f_max = profile["fat_g_per_kg"] * w
    f_min = profile.get("fat_g_per_kg_min", 0.8) * w
    c_target = max(0, (kcal - 4 * p_max - 9 * f_max) / 4)
    c_min = 1.5 * w
    return {
        "weight_kg": w, "bmr": bmr, "tdee": td, "tdee_source": source,
        "kcal": kcal,
        "protein_g": p_max, "protein_g_min": p_min,
        "fat_g": f_max, "fat_g_min": f_min,
        "carbs_g": c_target, "carbs_g_min": c_min,
    }


def meal_macros(meals: pd.DataFrame, foods: pd.DataFrame) -> pd.DataFrame:
    """Joint meals + foods, calcule kcal/macros par ligne."""
    if meals.empty:
        return pd.DataFrame(columns=["date", "meal", "food_id", "qty_g",
                                     "kcal", "protein_g", "fat_g", "carbs_g"])
    m = meals.merge(foods, on="food_id", how="left")
    factor = m["qty_g"] / 100.0
    m["kcal"] = m["kcal_100g"] * factor
    m["protein_g"] = m["protein_100g"] * factor
    m["fat_g"] = m["fat_100g"] * factor
    m["carbs_g"] = m["carbs_100g"] * factor
    return m[["date", "meal", "food_id", "name", "qty_g",
              "kcal", "protein_g", "fat_g", "carbs_g"]]


def daily_totals(meal_df: pd.DataFrame) -> pd.DataFrame:
    if meal_df.empty:
        return pd.DataFrame(columns=["date", "kcal", "protein_g", "fat_g", "carbs_g"])
    return (meal_df.groupby("date")[["kcal", "protein_g", "fat_g", "carbs_g"]]
            .sum().reset_index())
