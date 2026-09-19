import json
import os
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd

# pandas warne sur concat avec colonnes all-NA — c'est juste forward-compat
warnings.filterwarnings("ignore", category=FutureWarning, message=".*concat.*")

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("TRACKER_DATA", ROOT / "data"))

FOODS = DATA / "foods.csv"
MEALS = DATA / "meals.csv"
WEIGHT = DATA / "weight.csv"
PROFILE = DATA / "profile.json"
TEMPLATES = DATA / "templates.json"
SESSIONS = DATA / "sessions.csv"
EXOS = DATA / "exos.csv"
SKILLS = DATA / "skills.csv"
STEPS = DATA / "steps.csv"
CHECKINS = DATA / "checkins.csv"
MEASURES = DATA / "measures.csv"

FOOD_COLS = ["food_id", "name", "brand", "kcal_100g", "protein_100g",
             "fat_100g", "carbs_100g", "source", "unit_name", "unit_g",
             "default_qty_g"]

# --- Confiance d'un aliment selon sa source ---
# Sert à savoir où sont les marges d'erreur (resto/voyage = estimé à ±20-30%).
_HIGH_CONF = {"label", "seed", "ciqual", "usda", "web", "eatthismuch", "supp"}


def food_confidence(source) -> str:
    """'high' (label/base officielle), 'low' (estimation), 'med' (autre)."""
    s = str(source or "").lower()
    if any(tag in s for tag in ("estim", "generic", "estimé")):
        return "low"
    if any(s.startswith(h) or h in s for h in _HIGH_CONF):
        return "high"
    return "med"


# --- Résolution de date de log (garde-fou nuit tardive) ---
def resolve_log_date(now: datetime | None = None) -> tuple[date, bool]:
    """Date à utiliser pour un log + faut-il confirmer.

    Entre minuit et ~3h, `date.today()` est déjà le lendemain alors que pour
    l'utilisateur c'est encore "la veille" (soirée qui continue). On renvoie alors la
    veille avec needs_confirm=True. Sinon aujourd'hui, needs_confirm=False.
    """
    now = now or datetime.now()
    if now.hour < 3:
        return (now.date() - timedelta(days=1), True)
    return (now.date(), False)


# --- Profile ---
def load_profile() -> dict:
    return json.loads(PROFILE.read_text())


def save_profile(p: dict) -> None:
    PROFILE.write_text(json.dumps(p, indent=2, ensure_ascii=False))


# --- Foods ---
def load_foods() -> pd.DataFrame:
    df = pd.read_csv(FOODS)
    # migration: ajoute colonnes manquantes
    for col in FOOD_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[FOOD_COLS]


def save_foods(df: pd.DataFrame) -> None:
    df[FOOD_COLS].to_csv(FOODS, index=False)


def add_food(name: str, kcal_100g: float, protein_100g: float,
             fat_100g: float, carbs_100g: float,
             brand: str = "", source: str = "manual",
             unit_name: str = "", unit_g: float | None = None,
             default_qty_g: float | None = None) -> str:
    df = load_foods()
    food_id = name.strip().lower().replace(" ", "_")
    if brand:
        food_id = f"{food_id}__{brand.strip().lower().replace(' ', '_')}"
    if food_id in df["food_id"].astype(str).values:
        # met à jour les unités si elles étaient absentes
        idx = df.index[df["food_id"].astype(str) == food_id][0]
        if unit_name and not df.at[idx, "unit_name"] or pd.isna(df.at[idx, "unit_name"]):
            df.at[idx, "unit_name"] = unit_name
            df.at[idx, "unit_g"] = unit_g
            save_foods(df)
        return food_id
    row = {
        "food_id": food_id, "name": name, "brand": brand,
        "kcal_100g": kcal_100g, "protein_100g": protein_100g,
        "fat_100g": fat_100g, "carbs_100g": carbs_100g, "source": source,
        "unit_name": unit_name or "", "unit_g": unit_g,
        "default_qty_g": default_qty_g,
    }
    new_row = pd.DataFrame([row])
    df = new_row if df.empty else pd.concat([df, new_row], ignore_index=True)
    save_foods(df)
    return food_id


def set_default_qty(food_id: str, qty_g: float) -> None:
    """Fixe la portion par défaut d'un aliment (évite de redemander à chaque log)."""
    df = load_foods()
    mask = df["food_id"].astype(str) == food_id
    if mask.any():
        df.loc[mask, "default_qty_g"] = qty_g
        save_foods(df)


def default_qty(food_id: str) -> float | None:
    """Portion par défaut d'un aliment : default_qty_g > unit_g > None."""
    df = load_foods()
    row = df[df["food_id"].astype(str) == food_id]
    if row.empty:
        return None
    dq = row["default_qty_g"].iloc[0]
    if pd.notna(dq):
        return float(dq)
    ug = row["unit_g"].iloc[0]
    return float(ug) if pd.notna(ug) else None


# --- Meals ---
def load_meals() -> pd.DataFrame:
    df = pd.read_csv(MEALS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def log_meal(date, meal: str, food_id: str, qty_g: float) -> None:
    df = pd.read_csv(MEALS)
    row = pd.DataFrame([{"date": str(date), "meal": meal,
                         "food_id": food_id, "qty_g": qty_g}])
    df_out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    df_out.to_csv(MEALS, index=False)


def delete_meal_row(row_index: int) -> None:
    df = pd.read_csv(MEALS)
    if 0 <= row_index < len(df):
        df = df.drop(df.index[row_index]).reset_index(drop=True)
        df.to_csv(MEALS, index=False)


def update_meal_qty(row_index: int, new_qty: float) -> None:
    df = pd.read_csv(MEALS)
    if 0 <= row_index < len(df):
        df.at[df.index[row_index], "qty_g"] = new_qty
        df.to_csv(MEALS, index=False)


def recent_meals(n: int = 10) -> list[dict]:
    """Renvoie les N derniers couples (food_id, qty_g) uniques, plus récent en premier."""
    df = pd.read_csv(MEALS)
    if df.empty:
        return []
    df = df.iloc[::-1]  # inverse l'ordre
    seen, out = set(), []
    for _, r in df.iterrows():
        key = (r["food_id"], float(r["qty_g"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"food_id": r["food_id"], "qty_g": float(r["qty_g"])})
        if len(out) >= n:
            break
    return out


# --- Weight ---
def load_weight() -> pd.DataFrame:
    df = pd.read_csv(WEIGHT)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        if "moment" not in df.columns:
            df["moment"] = "matin"
        df = df.sort_values(["date", "moment"])
    return df


def current_weight() -> float:
    """Poids "courant" : dernière mesure (matin > soir si même jour),
    fallback profil si pas de pesée."""
    df = load_weight()
    if df.empty:
        return float(load_profile()["weight_kg"])
    last_date = df["date"].max()
    last_day = df[df["date"] == last_date]
    matin = last_day[last_day["moment"] == "matin"]
    if not matin.empty:
        return float(matin["weight_kg"].iloc[0])
    return float(last_day["weight_kg"].iloc[-1])


def log_weight(date, weight_kg: float, moment: str = "matin") -> None:
    """moment : 'matin' (à jeun) ou 'soir' (pré-dîner)."""
    df = pd.read_csv(WEIGHT)
    if "moment" not in df.columns and not df.empty:
        df["moment"] = "matin"
    if not df.empty:
        # supprime entrée existante pour (date, moment)
        df = df[~((df["date"] == str(date)) & (df.get("moment", "matin") == moment))]
    row = pd.DataFrame([{"date": str(date), "weight_kg": weight_kg, "moment": moment}])
    pd.concat([df, row], ignore_index=True).to_csv(WEIGHT, index=False)


# --- Templates (repas favoris) ---
def load_templates() -> list[dict]:
    if not TEMPLATES.exists():
        return []
    return json.loads(TEMPLATES.read_text())


def save_templates(t: list[dict]) -> None:
    TEMPLATES.write_text(json.dumps(t, indent=2, ensure_ascii=False))


def add_template(name: str, items: list[dict]) -> None:
    """items = liste de {food_id, qty_g}"""
    t = [x for x in load_templates() if x["name"] != name]
    t.append({"name": name, "items": items})
    save_templates(t)


def delete_template(name: str) -> None:
    save_templates([x for x in load_templates() if x["name"] != name])


# --- Sessions sport ---
def load_sessions() -> pd.DataFrame:
    df = pd.read_csv(SESSIONS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def log_session(date, sport_type: str, duration_min: float,
                met: float, active_fraction: float = 1.0,
                distance_km: float = None,
                summary: str = "", notes: str = "",
                weight_kg: float = None,
                counted_in_steps: bool = False) -> None:
    from core import sport as _sport
    if weight_kg is None:
        weight_kg = current_weight()
    kcal = _sport.session_kcal(met, active_fraction, weight_kg, duration_min)
    df = pd.read_csv(SESSIONS)
    row = pd.DataFrame([{
        "date": str(date), "type": sport_type,
        "duration_min": duration_min,
        "kcal_burned": kcal,
        "met": met, "active_fraction": active_fraction,
        "distance_km": distance_km,
        "counted_in_steps": counted_in_steps,
        "summary": summary, "notes": notes,
    }])
    out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    out.to_csv(SESSIONS, index=False)


def delete_session_row(row_index: int) -> None:
    df = pd.read_csv(SESSIONS)
    if 0 <= row_index < len(df):
        df = df.drop(df.index[row_index]).reset_index(drop=True)
        df.to_csv(SESSIONS, index=False)


# --- Exos street workout ---
def load_exos() -> pd.DataFrame:
    df = pd.read_csv(EXOS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def log_exo(date, exo: str, set_num: int, reps: int,
            weight_kg: float = 0, duration_sec: float = 0, notes: str = "") -> None:
    df = pd.read_csv(EXOS)
    row = pd.DataFrame([{
        "date": str(date), "exo": exo, "set_num": set_num, "reps": reps,
        "weight_kg": weight_kg, "duration_sec": duration_sec, "notes": notes,
    }])
    out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    out.to_csv(EXOS, index=False)


def delete_exo_row(row_index: int) -> None:
    df = pd.read_csv(EXOS)
    if 0 <= row_index < len(df):
        df = df.drop(df.index[row_index]).reset_index(drop=True)
        df.to_csv(EXOS, index=False)


# --- Skills ---
def load_skills() -> pd.DataFrame:
    df = pd.read_csv(SKILLS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def log_skill(date, skill: str, value: float, unit: str = "reps", notes: str = "") -> None:
    df = pd.read_csv(SKILLS)
    row = pd.DataFrame([{
        "date": str(date), "skill": skill, "value": value,
        "unit": unit, "notes": notes,
    }])
    out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    out.to_csv(SKILLS, index=False)


# --- Steps (pas quotidiens, depuis le tel) ---
def load_steps() -> pd.DataFrame:
    if not STEPS.exists():
        return pd.DataFrame(columns=["date", "steps", "steps_kcal", "extra_kcal"])
    df = pd.read_csv(STEPS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def log_steps(date, steps: int, steps_kcal: float, extra_kcal: float = 0) -> None:
    """extra_kcal = bonus manuel (dénivelé rando, etc.) non capté par les pas plats."""
    df = pd.read_csv(STEPS) if STEPS.exists() else \
        pd.DataFrame(columns=["date", "steps", "steps_kcal", "extra_kcal"])
    if not df.empty:
        df = df[df["date"] != str(date)]
    row = pd.DataFrame([{"date": str(date), "steps": steps,
                         "steps_kcal": steps_kcal, "extra_kcal": extra_kcal}])
    out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    out.to_csv(STEPS, index=False)


# --- Points hebdo (cible figée entre deux points, façon check-in MacroFactor) ---
CHECKIN_COLS = ["date", "tdee", "tdee_ci95", "rate", "rate_ci95", "intake_7d",
                "target_before", "target_proposed", "target_kcal"]


def load_checkins() -> pd.DataFrame:
    if not CHECKINS.exists():
        return pd.DataFrame(columns=CHECKIN_COLS)
    df = pd.read_csv(CHECKINS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date")


def log_checkin(row: dict) -> None:
    df = load_checkins()
    out = pd.concat([df, pd.DataFrame([{c: row.get(c) for c in CHECKIN_COLS}])], ignore_index=True)
    out.to_csv(CHECKINS, index=False)


# --- Mensurations (tour de taille) ---
def load_measures() -> pd.DataFrame:
    if not MEASURES.exists():
        return pd.DataFrame(columns=["date", "waist_cm", "notes"])
    df = pd.read_csv(MEASURES)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date")


def log_measure(date, waist_cm: float, notes: str = "") -> None:
    df = load_measures()
    row = pd.DataFrame([{"date": str(date), "waist_cm": waist_cm, "notes": notes}])
    out = pd.concat([df, row], ignore_index=True) if not df.empty else row
    out.to_csv(MEASURES, index=False)
