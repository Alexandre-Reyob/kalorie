"""Log — repas (avec récents/favoris/edit), aliments, poids."""
from datetime import date
import pandas as pd
from nicegui import ui

from core import storage, openfoodfacts as off
from . import widgets
from . import sessions_page  # On réutilise le contenu Séances


MEALS = ["petit-déj", "déjeuner", "snack", "dîner"]


def render():
    with ui.tabs().classes("w-full") as tabs:
        t_meal   = ui.tab("🍽️ Repas")
        t_food   = ui.tab("➕ Aliment")
        t_sport  = ui.tab("🦾 Sport")
        t_weight = ui.tab("⚖️ Poids")
        t_steps  = ui.tab("🚶 Pas")
    with ui.tab_panels(tabs, value=t_meal).classes("w-full"):
        with ui.tab_panel(t_meal):
            _render_meals()
        with ui.tab_panel(t_food):
            _render_food_add()
        with ui.tab_panel(t_sport):
            sessions_page.render()
        with ui.tab_panel(t_weight):
            _render_weight()
        with ui.tab_panel(t_steps):
            _render_steps()


# =========================================================
# TAB MEALS
# =========================================================
def _render_meals():
    state = {
        "date": date.today(),
        "meal": "déjeuner",
        "food_id": None,
        "qty_unit": 100.0,
        "unit": "g",
    }

    foods = storage.load_foods()
    if foods.empty:
        ui.label("Base d'aliments vide. → onglet ➕ Aliment.").classes("opacity-70")
        return

    # --- Header date + repas ---
    with ui.row().classes("w-full gap-3 items-center"):
        date_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        meal_in = ui.select(MEALS, value="déjeuner", label="Repas") \
            .props("dense outlined").classes("flex-1")

    date_in.on_value_change(lambda e: (state.update(date=date.fromisoformat(e.value)),
                                        day_meals_panel.refresh()))
    meal_in.on_value_change(lambda e: state.update(meal=e.value))

    ui.separator().classes("q-my-md")

    # --- Quick-add form ---
    widgets.section_title("Ajouter un aliment", "add_circle")

    options = {}
    for _, r in foods.iterrows():
        label = f"{r['name']} ({r['brand']})" \
            if r.get("brand") and pd.notna(r["brand"]) and r["brand"] else r["name"]
        options[r["food_id"]] = label
    state["food_id"] = list(options.keys())[0]

    with ui.row().classes("w-full gap-3 items-end"):
        food_sel = ui.select(options, value=state["food_id"], with_input=True,
                              label="Aliment") \
            .props("dense outlined").classes("flex-1")
        unit_sel = ui.select(["g"], value="g", label="Unité") \
            .props("dense outlined").style("width: 130px;")
        qty_in = ui.number(label="Qté", value=100.0, min=0.1, step=1.0,
                            format="%.1f") \
            .props("dense outlined").style("width: 110px;")
        add_btn = ui.button("Ajouter", icon="add") \
            .props("rounded color=primary").classes("smooth")

    def refresh_units():
        row = foods[foods["food_id"] == state["food_id"]].iloc[0]
        opts = ["g"]
        if pd.notna(row.get("unit_g")) and row.get("unit_g"):
            opts.append(row["unit_name"])
        unit_sel.options = opts
        unit_sel.update()
        unit_sel.value = "g"
        state["unit"] = "g"
        qty_in.value = 100.0
        state["qty_unit"] = 100.0

    food_sel.on_value_change(lambda e: (state.update(food_id=e.value), refresh_units()))
    unit_sel.on_value_change(lambda e: (state.update(unit=e.value),
                                         qty_in.set_value(1.0 if e.value != "g" else 100.0)))
    qty_in.on_value_change(lambda e: state.update(qty_unit=e.value or 0))
    refresh_units()

    def on_add():
        row = foods[foods["food_id"] == state["food_id"]].iloc[0]
        mult = float(row["unit_g"]) if state["unit"] != "g" else 1.0
        qty_g = float(state["qty_unit"]) * mult
        storage.log_meal(state["date"], state["meal"], state["food_id"], qty_g)
        ui.notify(f"+ {options[state['food_id']]} · {qty_g:.0f}g",
                  color="positive", position="top")
        day_meals_panel.refresh()
        recents_panel.refresh()

    add_btn.on_click(on_add)

    ui.separator().classes("q-my-md")

    # --- Refreshable panels ---
    @ui.refreshable
    def recents_panel():
        ui.html('<div class="text-base font-semibold q-mb-sm">🕐 Récents</div>')
        rs = storage.recent_meals(n=10)
        if not rs:
            ui.label("Aucun repas loggé.").classes("opacity-60 text-sm")
            return
        for r in rs:
            info = foods[foods["food_id"] == r["food_id"]]
            if info.empty:
                continue
            nm = info.iloc[0]["name"]
            fid = r["food_id"]
            qty = float(r["qty_g"])

            def handler(fid_=fid, qty_=qty, nm_=nm):
                storage.log_meal(state["date"], state["meal"], fid_, qty_)
                ui.notify(f"+ {nm_}", color="positive", position="top")
                day_meals_panel.refresh()

            ui.button(f"➕ {nm} · {qty:.0f}g", on_click=handler) \
                .props("flat align=left no-caps").classes(
                "w-full text-left q-mb-xs item-row smooth")

    @ui.refreshable
    def favoris_panel():
        ui.html('<div class="text-base font-semibold q-mb-sm">⭐ Favoris</div>')
        templates = storage.load_templates()
        if not templates:
            ui.label("Aucun favori.").classes("opacity-60 text-sm")
            return
        for t in templates:
            items = t["items"]
            name = t["name"]
            with ui.row().classes("w-full items-center q-mb-xs no-wrap gap-2"):
                def apply_t(items_=items, name_=name):
                    for it in items_:
                        storage.log_meal(state["date"], state["meal"],
                                         it["food_id"], it["qty_g"])
                    ui.notify(f"Favori « {name_} » appliqué",
                              color="positive", position="top")
                    day_meals_panel.refresh()
                    recents_panel.refresh()

                def delete_t(name_=name):
                    storage.delete_template(name_)
                    ui.notify("Favori supprimé", color="warning", position="top")
                    favoris_panel.refresh()

                ui.button(f"📋 {name} ({len(items)} items)", on_click=apply_t) \
                    .props("flat align=left no-caps").classes(
                    "text-left flex-1 item-row smooth")
                ui.button(icon="delete_outline", on_click=delete_t) \
                    .props("flat dense round color=negative")

    @ui.refreshable
    def day_meals_panel():
        ui.html(f'<div class="text-base font-semibold q-mb-sm q-mt-md">'
                f'🍽️ Repas du {state["date"].isoformat()}</div>')
        meals_df = pd.read_csv(storage.MEALS)
        if meals_df.empty:
            ui.label("Rien loggé.").classes("opacity-60 text-sm")
            return
        meals_df["__abs_idx"] = meals_df.index
        day = meals_df[meals_df["date"] == str(state["date"])]
        if day.empty:
            ui.label("Rien loggé pour cette date.").classes("opacity-60 text-sm")
            return
        day = day.merge(foods[["food_id", "name"]], on="food_id", how="left")
        for _, row in day.iterrows():
            idx = int(row["__abs_idx"])
            nm = row["name"] or row["food_id"]
            with ui.row().classes("w-full items-center q-mb-xs no-wrap item-row gap-2"):
                ui.label(row["meal"]).classes("text-xs font-bold opacity-80")\
                  .style("min-width:80px;")
                ui.label(nm).classes("flex-1 text-sm").style("overflow:hidden;")
                q_in = ui.number(value=float(row["qty_g"]), min=1, step=10, suffix="g") \
                    .props("dense outlined").style("max-width:110px;")

                def save_h(idx_=idx, q_in_=q_in):
                    storage.update_meal_qty(idx_, float(q_in_.value))
                    ui.notify("Modifié", color="positive", position="top")
                    day_meals_panel.refresh()
                    recents_panel.refresh()

                def del_h(idx_=idx):
                    storage.delete_meal_row(idx_)
                    ui.notify("Supprimé", color="warning", position="top")
                    day_meals_panel.refresh()
                    recents_panel.refresh()

                ui.button(icon="save", on_click=save_h) \
                    .props("flat dense round color=primary")
                ui.button(icon="delete_outline", on_click=del_h) \
                    .props("flat dense round color=negative")

    # --- Render panels ---
    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.element("div"):
            recents_panel()
        with ui.element("div"):
            favoris_panel()

    ui.separator().classes("q-my-md")
    day_meals_panel()

    # --- Save as favorite ---
    with ui.expansion("⭐ Sauvegarder les repas du jour comme favori") \
            .classes("w-full q-mt-md"):
        name_in = ui.input(label="Nom du favori",
                            placeholder="ex: Petit-déj type") \
            .props("dense outlined").classes("w-full")

        def save_template():
            if not name_in.value:
                ui.notify("Choisis un nom", color="warning")
                return
            df = pd.read_csv(storage.MEALS)
            today_df = df[df["date"] == str(state["date"])]
            items = [{"food_id": r["food_id"], "qty_g": float(r["qty_g"])}
                     for _, r in today_df.iterrows()]
            if not items:
                ui.notify("Pas de repas à enregistrer", color="warning")
                return
            storage.add_template(name_in.value, items)
            ui.notify(f"Favori « {name_in.value} » enregistré.",
                      color="positive", position="top")
            name_in.value = ""
            favoris_panel.refresh()

        ui.button("💾 Sauvegarder", on_click=save_template, icon="save") \
            .props("color=primary").classes("q-mt-sm")


# =========================================================
# TAB ALIMENT
# =========================================================
def _render_food_add():
    state = {"results": []}

    widgets.section_title("Recherche OpenFoodFacts", "search")

    q_in = ui.input(label="Nom ou code-barres",
                    placeholder="ex: skyr, 3017620422003…") \
        .props("dense outlined").classes("w-full")

    @ui.refreshable
    def results_panel():
        for i, p in enumerate(state["results"]):
            with ui.expansion(
                f"{p['name']} · {p['brand']} · {p['kcal_100g']:.0f} kcal/100g") \
                    .classes("w-full"):
                ui.label(f"P {p['protein_100g']:.1f}g · L {p['fat_100g']:.1f}g "
                         f"· G {p['carbs_100g']:.1f}g").classes("opacity-80")

                def add_p(p_=p):
                    fid = storage.add_food(
                        p_["name"], p_["kcal_100g"], p_["protein_100g"],
                        p_["fat_100g"], p_["carbs_100g"],
                        p_["brand"], source="openfoodfacts")
                    ui.notify(f"Ajouté ({fid})", color="positive", position="top")

                ui.button("➕ Ajouter à ma base", on_click=add_p) \
                    .props("color=primary").classes("q-mt-sm")

    def search_off():
        if not q_in.value:
            return
        ui.notify("OpenFoodFacts…", color="info")
        try:
            if q_in.value.isdigit():
                p = off.by_barcode(q_in.value)
                results = [p] if p else []
            else:
                results = off.search(q_in.value, page_size=10)
        except Exception as e:
            ui.notify(f"OFF indisponible: {e}", color="negative")
            results = []
        state["results"] = results
        results_panel.refresh()

    ui.button("🔍 Chercher", on_click=search_off) \
        .props("color=primary").classes("q-mt-sm")
    results_panel()

    ui.separator().classes("q-my-lg")
    widgets.section_title("Ajout manuel", "edit")

    name_in  = ui.input(label="Nom").props("dense outlined").classes("w-full")
    brand_in = ui.input(label="Marque (optionnel)") \
        .props("dense outlined").classes("w-full")
    with ui.row().classes("w-full gap-3"):
        kcal_in = ui.number(label="kcal/100g", value=100, min=0) \
            .props("dense outlined").classes("flex-1")
        prot_in = ui.number(label="P/100g", value=10, min=0) \
            .props("dense outlined").classes("flex-1")
        fat_in  = ui.number(label="L/100g", value=5, min=0) \
            .props("dense outlined").classes("flex-1")
        carb_in = ui.number(label="G/100g", value=10, min=0) \
            .props("dense outlined").classes("flex-1")
    with ui.row().classes("w-full gap-3"):
        unit_n_in = ui.input(label="Unité (optionnel)",
                              placeholder="ex: œuf, c. à soupe") \
            .props("dense outlined").classes("flex-1")
        unit_g_in = ui.number(label="g par unité", value=0, min=0) \
            .props("dense outlined").classes("flex-1")

    def add_manual():
        if not name_in.value:
            ui.notify("Donne un nom", color="warning")
            return
        fid = storage.add_food(name_in.value, kcal_in.value, prot_in.value,
                                fat_in.value, carb_in.value,
                                brand_in.value or "", source="manual",
                                unit_name=unit_n_in.value or "",
                                unit_g=unit_g_in.value if unit_g_in.value > 0 else None)
        ui.notify(f"Ajouté ({fid})", color="positive", position="top")
        name_in.value = ""
        brand_in.value = ""

    ui.button("Ajouter", icon="add", on_click=add_manual) \
        .props("color=primary").classes("q-mt-sm")


# =========================================================
# TAB POIDS
# =========================================================
def _render_weight():
    profile = storage.load_profile()
    widgets.section_title("Pesée du jour", "monitor_weight")

    with ui.row().classes("w-full gap-3"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        moment_in = ui.select(["matin", "soir"], value="matin", label="Moment") \
            .props("dense outlined").classes("flex-1")
        w_in = ui.number(label="Poids (kg)",
                          value=float(profile["weight_kg"]),
                          min=30, max=200, step=0.1, format="%.1f") \
            .props("dense outlined").classes("flex-1")

    def save():
        d = date.fromisoformat(d_in.value)
        w = float(w_in.value)
        storage.log_weight(d, w, moment_in.value)
        prof = storage.load_profile()
        prof["weight_kg"] = w
        storage.save_profile(prof)
        ui.notify(f"Poids {w} kg ({moment_in.value}) enregistré",
                  color="positive", position="top")
        history_panel.refresh()

    ui.button("💾 Enregistrer", on_click=save, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    widgets.section_title("Tour de taille (1×/semaine)", "straighten")
    ui.label("Au nombril, le matin à jeun, ventre relâché, mètre à plat sans serrer.") \
        .classes("opacity-60 text-sm q-mb-sm")
    with ui.row().classes("w-full gap-3"):
        wd_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        waist_in = ui.number(label="Tour de taille (cm)", min=50, max=150, step=0.5,
                             format="%.1f").props("dense outlined").classes("flex-1")

    def save_waist():
        if not waist_in.value:
            ui.notify("Entre une valeur", color="warning", position="top")
            return
        storage.log_measure(date.fromisoformat(wd_in.value), float(waist_in.value))
        ui.notify(f"Tour de taille {waist_in.value} cm enregistré", color="positive", position="top")

    ui.button("Enregistrer", on_click=save_waist, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")
    widgets.section_title("Historique récent")

    @ui.refreshable
    def history_panel():
        weight_df = storage.load_weight()
        if weight_df.empty:
            ui.label("Aucune pesée enregistrée.").classes("opacity-60 text-sm")
            return
        weight_df = weight_df.sort_values("date", ascending=False).head(10)
        for _, r in weight_df.iterrows():
            moment = r.get("moment", "matin")
            color = "text-emerald-400" if moment == "matin" else "text-amber-400"
            with ui.row().classes("w-full items-center q-mb-xs item-row no-wrap gap-2"):
                ui.label(str(r["date"])).classes("opacity-70 text-sm")\
                  .style("min-width:120px;")
                ui.label(moment).classes(f"text-xs {color}")\
                  .style("min-width:50px;")
                ui.label(f"{r['weight_kg']:.1f} kg").classes(
                    "text-base font-semibold")

    history_panel()


# =========================================================
# TAB PAS
# =========================================================
def _render_steps():
    widgets.section_title("Pas du jour (depuis le tel)", "directions_walk")
    ui.label("Si rien n'est saisi pour un jour → défaut 6000 pas (~186 kcal).") \
        .classes("opacity-60 text-sm")

    with ui.row().classes("w-full gap-3 q-mt-md"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        steps_in = ui.number(label="Pas (tel)", value=0, min=0, step=100) \
            .props("dense outlined").classes("flex-1")
        kcal_in = ui.number(label="kcal (tel)", value=0, min=0, step=10) \
            .props("dense outlined").classes("flex-1")

    def save():
        storage.log_steps(date.fromisoformat(d_in.value),
                          int(steps_in.value), float(kcal_in.value))
        ui.notify(f"{int(steps_in.value)} pas · {kcal_in.value:.0f} kcal",
                  color="positive", position="top")
        history.refresh()

    ui.button("💾 Enregistrer", on_click=save, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")
    widgets.section_title("Historique", "history")

    @ui.refreshable
    def history():
        df = storage.load_steps()
        if df.empty:
            ui.label("Aucune donnée.").classes("opacity-60 text-sm")
            return
        for _, r in df.sort_values("date", ascending=False).head(20).iterrows():
            with ui.row().classes("w-full items-center q-mb-xs item-row no-wrap gap-3"):
                ui.label(str(r["date"])).classes("opacity-70 text-sm")\
                  .style("min-width:120px;")
                ui.label(f"🚶 {int(r['steps'])} pas").classes("text-sm")\
                  .style("min-width:130px;")
                ui.label(f"{r['steps_kcal']:.0f} kcal").classes(
                    "text-sm font-semibold")

    history()
