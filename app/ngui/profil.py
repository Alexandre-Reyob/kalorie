"""Profil — réglages + cible active + historique des points hebdo.

L'analyse (TDEE, rythme, trajectoire) vit dans Tendances ; ici on ne règle que les objectifs.
"""
from nicegui import ui

from core import storage, energy
from . import theme, widgets


def render():
    @ui.refreshable
    def content():
        profile = storage.load_profile()
        targets = energy.effective_targets()
        ck = storage.load_checkins()

        # =====================================================
        # CIBLE ACTIVE
        # =====================================================
        widgets.section_title("Cible active", "flag")
        origin = (f"figée au point du {targets['checkin_date']}" if targets["checkin_date"]
                  else "en direct (aucun point hebdo validé)")
        with ui.grid(columns=4).classes("w-full gap-3"):
            widgets.metric_card("Cible kcal", f"{targets['kcal']:.0f}", origin)
            widgets.metric_card("TDEE estimé", f"{targets['tdee']:.0f}",
                                "Kalman" if targets["tdee_source"] == "empirical" else "théorique")
            widgets.metric_card("Rythme visé", f"{profile.get('target_rate_kg_per_month', 0):+.1f}",
                                "kg/mois")
            widgets.metric_card("Macros P/L/G",
                                f"{targets['protein_g']:.0f}/{targets['fat_g']:.0f}/{targets['carbs_g']:.0f}",
                                f"g/jour · sur {targets['weight_kg']:.1f} kg")

        if not ck.empty:
            widgets.section_title("Points hebdo", "event_repeat")
            for _, r in ck[::-1].iterrows():
                ui.html(f'<div class="item-row" style="display:flex; gap:16px; flex-wrap:wrap; '
                        f'font-size:0.88rem; margin-bottom:4px;">'
                        f'<b style="min-width:90px;">{r["date"]}</b>'
                        f'<span style="color:{theme.MUTED};">TDEE {r["tdee"]:.0f} ±{r["tdee_ci95"]:.0f}</span>'
                        f'<span style="color:{theme.MUTED};">rythme {r["rate"]:+.1f} ±{r["rate_ci95"]:.1f}</span>'
                        f'<span style="color:{theme.MUTED};">intake 7j {r["intake_7d"]:.0f}</span>'
                        f'<b style="margin-left:auto; color:{theme.ACCENT_SOFT};">{r["target_kcal"]:.0f} kcal</b>'
                        f'</div>')

        ui.separator().classes("q-my-md")

        # =====================================================
        # PROFIL & OBJECTIFS
        # =====================================================
        widgets.section_title("Profil & objectifs", "person")

        with ui.row().classes("w-full gap-3"):
            age_in = ui.number(label="Âge", value=int(profile["age"]), min=10, max=100) \
                .props("dense outlined").classes("flex-1")
            sex_in = ui.select(["M", "F"], value=profile["sex"], label="Sexe") \
                .props("dense outlined").classes("flex-1")
            height_in = ui.number(label="Taille (cm)", value=float(profile["height_cm"]),
                                  min=100, max=230) \
                .props("dense outlined").classes("flex-1")
        with ui.row().classes("w-full gap-3"):
            goal_in = ui.select(["cut", "maintien", "recomp", "bulk"], value=profile["goal"],
                                label="Objectif") \
                .props("dense outlined").classes("flex-1")
            rate_in = ui.number(label="Rythme visé (kg/mois) — négatif = perte",
                                value=float(profile.get("target_rate_kg_per_month", 0.0)),
                                min=-2.0, max=2.0, step=0.1, format="%.1f") \
                .props("dense outlined").classes("flex-1")
            goal_weight_in = ui.number(label="Objectif poids (kg)",
                                       value=float(profile.get("goal_weight_kg") or 70),
                                       min=30, max=200, step=0.5, format="%.1f") \
                .props("dense outlined").classes("flex-1")

        with ui.row().classes("w-full gap-3"):
            pkg_in = ui.number(label="Protéines cible g/kg", value=float(profile["protein_g_per_kg"]),
                               min=0.5, max=4.0, step=0.1, format="%.1f") \
                .props("dense outlined").classes("flex-1")
            pmin_in = ui.number(label="Protéines plancher g/kg",
                                value=float(profile.get("protein_g_per_kg_min", 1.7)),
                                min=0.5, max=4.0, step=0.1, format="%.1f") \
                .props("dense outlined").classes("flex-1")
            fkg_in = ui.number(label="Lipides cible g/kg", value=float(profile["fat_g_per_kg"]),
                               min=0.4, max=2.0, step=0.05, format="%.2f") \
                .props("dense outlined").classes("flex-1")
            fmin_in = ui.number(label="Lipides plancher g/kg",
                                value=float(profile.get("fat_g_per_kg_min", 0.8)),
                                min=0.4, max=2.0, step=0.05, format="%.2f") \
                .props("dense outlined").classes("flex-1")

        def save():
            # On PART du profil existant (merge) pour ne jamais perdre un champ
            # géré ailleurs (bulk_start_date, etc.) qui n'a pas son propre input ici.
            updated = dict(profile)
            updated.update({
                "sex": sex_in.value,
                "age": int(age_in.value),
                "height_cm": float(height_in.value),
                "goal_weight_kg": float(goal_weight_in.value),
                "goal": goal_in.value,
                "target_rate_kg_per_month": float(rate_in.value),
                "protein_g_per_kg": float(pkg_in.value),
                "protein_g_per_kg_min": float(pmin_in.value),
                "fat_g_per_kg": float(fkg_in.value),
                "fat_g_per_kg_min": float(fmin_in.value),
            })
            storage.save_profile(updated)
            ui.notify("Profil mis à jour — la cible changera au prochain point hebdo",
                      color="positive", position="top")
            content.refresh()

        ui.button("Enregistrer", on_click=save, icon="save") \
            .props("color=primary").classes("q-mt-sm")

    content()
