"""Séances — escalade, course, street workout, skills."""
from datetime import date
import pandas as pd
import plotly.graph_objects as go
from nicegui import ui

from core import storage, sport
from . import theme, widgets


def render():
    profile = storage.load_profile()
    weight = profile["weight_kg"]

    with ui.tabs().classes("w-full") as tabs:
        t_climb  = ui.tab("🧗 Escalade")
        t_run    = ui.tab("🏃 Course")
        t_street = ui.tab("🦾 Street workout")
        t_skill  = ui.tab("🎯 Skills")
    with ui.tab_panels(tabs, value=t_climb).classes("w-full"):
        with ui.tab_panel(t_climb):
            _render_climb(weight)
        with ui.tab_panel(t_run):
            _render_run(weight)
        with ui.tab_panel(t_street):
            _render_street(weight)
        with ui.tab_panel(t_skill):
            _render_skills()


def _session_row(sess, on_delete, weight):
    from core import sport as _sport
    emoji = {"escalade":"🧗","course":"🏃","street_workout":"🦾"}.get(sess["type"],"💪")
    counted = bool(sess.get("counted_in_steps", False))
    kcal = _sport.session_kcal(sess["met"], sess["active_fraction"], weight, sess["duration_min"])
    kcal_txt = "↳ pas" if counted else f"{kcal:.0f} kcal"
    with ui.row().classes("w-full items-center q-mb-xs item-row no-wrap gap-2"):
        ui.label(emoji).classes("text-xl")
        ui.label(str(sess["date"])).classes("text-sm opacity-70")\
          .style("min-width:100px;")
        ui.label(f"{sess['duration_min']:.0f} min").classes("text-sm")\
          .style("min-width:70px;")
        ui.label(kcal_txt).classes(
            "text-sm font-semibold").style(f"color:{theme.WARN}; min-width:80px;")
        ui.label(sess.get("summary") or "—").classes(
            "text-sm flex-1 opacity-90").style("overflow:hidden;")
        ui.button(icon="delete_outline", on_click=on_delete) \
            .props("flat dense round color=negative")


# --- ESCALADE ---
def _render_climb(weight):
    widgets.section_title("Nouvelle séance d'escalade", "terrain")

    with ui.row().classes("w-full gap-3"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        dur_in = ui.number(label="Durée (min)", value=75, min=5, max=300, step=5) \
            .props("dense outlined").classes("flex-1")
        intense_in = ui.select(["modérée", "intense (projet)"], value="modérée",
                                label="Intensité") \
            .props("dense outlined").classes("flex-1")
    summary_in = ui.input(label="Résumé voies/blocs",
                           placeholder="ex: 4×6a flash, 2×6b à vue") \
        .props("dense outlined").classes("w-full")
    notes_in = ui.textarea(label="Notes",
                            placeholder="Sensations, partenaires…") \
        .props("dense outlined").classes("w-full")

    def save():
        frac = 0.5 if "intense" not in intense_in.value else 0.6
        met = sport.MET_ACTIF["escalade"]
        kcal = sport.session_kcal(met, frac, weight, dur_in.value)
        storage.log_session(date.fromisoformat(d_in.value), "escalade",
                            dur_in.value, met, frac, None,
                            summary_in.value or "", notes_in.value or "")
        ui.notify(f"Séance loggée · {kcal:.0f} kcal",
                  color="positive", position="top")
        summary_in.value = ""
        notes_in.value = ""
        history_panel.refresh()

    ui.button("💾 Enregistrer", on_click=save, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")
    widgets.section_title("Historique", "history")

    @ui.refreshable
    def history_panel():
        sess = storage.load_sessions()
        if sess.empty:
            ui.label("Aucune séance.").classes("opacity-60 text-sm")
            return
        sess = sess[sess["type"] == "escalade"]
        if sess.empty:
            ui.label("Aucune séance.").classes("opacity-60 text-sm")
            return
        for idx, row in (sess.sort_values("date", ascending=False)
                          .head(20).reset_index().iterrows()):
            def del_h(idx_=row["index"]):
                storage.delete_session_row(int(idx_))
                history_panel.refresh()
            _session_row(row, del_h, weight)

    history_panel()


# --- COURSE ---
def _render_run(weight):
    widgets.section_title("Nouvelle course", "directions_run")

    with ui.row().classes("w-full gap-3"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        km_in = ui.number(label="Distance (km)", value=5.0, min=0.5,
                           max=50.0, step=0.5) \
            .props("dense outlined").classes("flex-1")
        dur_in = ui.number(label="Temps (min)", value=27.0, min=5.0,
                            max=300.0, step=0.5) \
            .props("dense outlined").classes("flex-1")
    with ui.row().classes("w-full gap-3"):
        intense_in = ui.select(["modérée", "intense (tempo/fractionné)"],
                                value="modérée", label="Intensité") \
            .props("dense outlined").classes("flex-1")
        notes_in = ui.input(label="Notes",
                             placeholder="Parcours, FC moy…") \
            .props("dense outlined").classes("flex-1")
    phone_in = ui.switch("Tel porté pendant la course (déjà compté dans les pas)",
                         value=True)

    def save():
        met = sport.MET_ACTIF["course"]
        counted = bool(phone_in.value)
        kcal = sport.session_kcal(met, 1.0, weight, dur_in.value)
        summary = f"{km_in.value:.1f}km en {dur_in.value:.0f}min · " \
                  f"{sport.pace_str(km_in.value, dur_in.value)}"
        note = notes_in.value or ""
        if counted:
            note = (note + " · tel porté → déjà dans les pas").strip(" ·")
        storage.log_session(date.fromisoformat(d_in.value), "course",
                            dur_in.value, met, 1.0, km_in.value,
                            summary, note, counted_in_steps=counted)
        msg = "comptée dans les pas" if counted else f"{kcal:.0f} kcal"
        ui.notify(f"Course loggée · {msg} · {sport.pace_str(km_in.value, dur_in.value)}",
                  color="positive", position="top")
        notes_in.value = ""
        history_panel.refresh()

    ui.button("💾 Enregistrer", on_click=save, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")
    widgets.section_title("Historique", "history")

    @ui.refreshable
    def history_panel():
        sess = storage.load_sessions()
        if sess.empty:
            ui.label("Aucune course.").classes("opacity-60 text-sm")
            return
        sess = sess[sess["type"] == "course"]
        if sess.empty:
            ui.label("Aucune course.").classes("opacity-60 text-sm")
            return
        for _, row in (sess.sort_values("date", ascending=False)
                        .head(20).reset_index().iterrows()):
            def del_h(idx_=row["index"]):
                storage.delete_session_row(int(idx_))
                history_panel.refresh()
            _session_row(row, del_h, weight)

    history_panel()


# --- STREET WORKOUT ---
def _render_street(weight):
    widgets.section_title("Nouvelle séance street workout", "fitness_center")

    state = {"date": date.today()}

    with ui.row().classes("w-full gap-3"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        dur_in = ui.number(label="Durée totale (min)", value=55,
                            min=10, max=240, step=5) \
            .props("dense outlined").classes("flex-1")

    d_in.on_value_change(lambda e: (state.update(date=date.fromisoformat(e.value)),
                                     today_sets.refresh()))

    def save_session():
        d = date.fromisoformat(d_in.value)
        met = sport.MET_ACTIF["street_workout"]
        kcal = sport.session_kcal(met, 1.0, weight, dur_in.value)
        exos_day = storage.load_exos()
        exos_day = exos_day[exos_day["date"] == d] if not exos_day.empty else exos_day
        if not exos_day.empty:
            top = exos_day.groupby("exo").agg(
                sets=("set_num", "count"), reps=("reps", "sum"))
            summary = " · ".join(
                f"{exo} {row['sets']}×~{row['reps']/row['sets']:.0f}"
                for exo, row in top.iterrows())
        else:
            summary = ""
        storage.log_session(d, "street_workout", dur_in.value, met, 1.0, None, summary, "")
        ui.notify(f"Séance loggée · {kcal:.0f} kcal",
                  color="positive", position="top")
        history_panel.refresh()

    ui.button("💾 Enregistrer la séance (header)", on_click=save_session, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")
    widgets.section_title("Ajouter un set d'exo", "add_circle")

    exos_df = storage.load_exos()
    known_exos = sorted(set(sport.EXOS_SUGGESTED) |
                         set(exos_df["exo"].dropna().unique() if not exos_df.empty else []))

    with ui.row().classes("w-full gap-3 items-end"):
        exo_sel = ui.select(known_exos, value=known_exos[0], with_input=True,
                              label="Exo") \
            .props("dense outlined").classes("flex-1")
        reps_in = ui.number(label="Reps", value=8, min=1, max=200, step=1) \
            .props("dense outlined").style("width:100px;")
        lest_in = ui.number(label="Lest (kg)", value=0.0, min=-50, max=100, step=2.5,
                              format="%.1f") \
            .props("dense outlined").style("width:120px;")
        hold_in = ui.number(label="Hold (s)", value=0, min=0, max=600, step=5) \
            .props("dense outlined").style("width:100px;")
    custom_in = ui.input(label="Ou exo custom (override)",
                          placeholder="Nouveau nom d'exo…") \
        .props("dense outlined").classes("w-full")

    def add_set():
        exo = custom_in.value.strip() if custom_in.value else exo_sel.value
        d = date.fromisoformat(d_in.value)
        ex_df = storage.load_exos()
        ex_day = ex_df[(ex_df["date"] == d) & (ex_df["exo"] == exo)] \
            if not ex_df.empty else pd.DataFrame()
        set_num = len(ex_day) + 1
        storage.log_exo(d, exo, set_num, reps_in.value, lest_in.value, hold_in.value)
        ui.notify(f"{exo} · set #{set_num} · {reps_in.value} reps",
                  color="positive", position="top")
        today_sets.refresh()
        pr_panel.refresh()

    ui.button("➕ Ajouter le set", on_click=add_set, icon="add") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")

    @ui.refreshable
    def today_sets():
        ui.html(f'<div class="text-base font-semibold q-mb-sm">'
                f'Sets du {state["date"].isoformat()}</div>')
        df = storage.load_exos()
        if df.empty:
            ui.label("Aucun set.").classes("opacity-60 text-sm")
            return
        df["__abs_idx"] = df.index
        day = df[df["date"] == state["date"]]
        if day.empty:
            ui.label("Aucun set pour cette date.").classes("opacity-60 text-sm")
            return
        day = day.sort_values(["exo", "set_num"])
        for _, row in day.iterrows():
            with ui.row().classes("w-full items-center q-mb-xs item-row no-wrap gap-2"):
                ui.label(f"{row['exo']}").classes("text-sm font-semibold flex-1")
                ui.label(f"set {int(row['set_num'])}").classes("text-xs opacity-60")\
                  .style("min-width:50px;")
                ui.label(f"{int(row['reps'])} reps").classes("text-sm")\
                  .style("min-width:75px;")
                lest = float(row["weight_kg"]) if pd.notna(row["weight_kg"]) else 0
                ui.label(f"{lest:+.1f} kg" if lest else "BW").classes("text-sm opacity-80")\
                  .style("min-width:65px;")
                hold = int(row["duration_sec"]) if pd.notna(row["duration_sec"]) else 0
                if hold:
                    ui.label(f"{hold}s").classes("text-sm opacity-70")

                def del_h(idx_=int(row["__abs_idx"])):
                    storage.delete_exo_row(idx_)
                    today_sets.refresh()
                    pr_panel.refresh()

                ui.button(icon="delete_outline", on_click=del_h) \
                    .props("flat dense round color=negative")

    today_sets()

    ui.separator().classes("q-my-md")
    widgets.section_title("🏆 Records (PR)", "emoji_events")

    @ui.refreshable
    def pr_panel():
        df = storage.load_exos()
        if df.empty:
            ui.label("Pas encore de records.").classes("opacity-60 text-sm")
            return
        for exo in sorted(df["exo"].unique()):
            pr = sport.exo_pr(df, exo)
            parts = []
            if pr["max_weight"] and pr["max_weight"] > 0:
                parts.append(f"max lest {pr['max_weight']:+.1f} kg "
                              f"× {pr['max_reps_at_max_weight']} reps")
            if pr["max_reps_bw"]:
                parts.append(f"max BW {pr['max_reps_bw']} reps")
            if not parts:
                continue
            with ui.row().classes("w-full items-center q-mb-xs item-row gap-2"):
                ui.label(exo).classes("font-semibold flex-1")
                ui.label(" · ".join(parts)).classes("text-sm opacity-80")

    pr_panel()

    ui.separator().classes("q-my-md")
    widgets.section_title("Historique séances", "history")

    @ui.refreshable
    def history_panel():
        sess = storage.load_sessions()
        if sess.empty:
            ui.label("Aucune séance.").classes("opacity-60 text-sm")
            return
        sess = sess[sess["type"] == "street_workout"]
        if sess.empty:
            ui.label("Aucune séance street.").classes("opacity-60 text-sm")
            return
        for _, row in (sess.sort_values("date", ascending=False)
                        .head(20).reset_index().iterrows()):
            def del_h(idx_=row["index"]):
                storage.delete_session_row(int(idx_))
                history_panel.refresh()
            _session_row(row, del_h, weight)

    history_panel()


# --- SKILLS ---
def _render_skills():
    SKILL_OPTS = [
        "Muscle-up (max reps)", "Muscle-up négatif (max reps)",
        "Handstand push-up (max reps)", "HSPU négatif (max reps)",
        "Front lever (hold sec)", "Back lever (hold sec)",
        "Planche (hold sec)", "L-sit (hold sec)",
        "Pull-up (max reps)", "Pistol squat (max reps/jambe)",
        "Custom…",
    ]

    widgets.section_title("Test mensuel d'un skill", "flag")

    with ui.row().classes("w-full gap-3"):
        d_in = ui.input(value=date.today().isoformat(), label="Date") \
            .props("dense outlined type=date").classes("flex-1")
        skill_sel = ui.select(SKILL_OPTS, value=SKILL_OPTS[0], label="Skill") \
            .props("dense outlined").classes("flex-1")
    custom_in = ui.input(label="Nom custom (si Custom…)",
                          placeholder="ex: One-arm pull-up négatif") \
        .props("dense outlined").classes("w-full")
    with ui.row().classes("w-full gap-3"):
        unit_sel = ui.select(["reps", "sec"], value="reps", label="Unité") \
            .props("dense outlined").classes("flex-1")
        val_in = ui.number(label="Valeur", value=1.0, min=0, max=600) \
            .props("dense outlined").classes("flex-1")
        notes_in = ui.input(label="Notes",
                             placeholder="Forme/ressenti…") \
            .props("dense outlined").classes("flex-1")

    def save():
        sk = custom_in.value.strip() if skill_sel.value == "Custom…" \
            else skill_sel.value.split(" (")[0]
        storage.log_skill(date.fromisoformat(d_in.value), sk, val_in.value,
                          unit_sel.value, notes_in.value or "")
        ui.notify(f"{sk} = {val_in.value} {unit_sel.value}",
                  color="positive", position="top")
        notes_in.value = ""
        charts_panel.refresh()

    ui.button("💾 Enregistrer", on_click=save, icon="save") \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("q-my-md")

    @ui.refreshable
    def charts_panel():
        widgets.section_title("Courbes de progression", "show_chart")
        skills = storage.load_skills()
        if skills.empty:
            ui.label("Aucun skill loggé.").classes("opacity-60 text-sm")
            return
        for sk in sorted(skills["skill"].unique()):
            sub = skills[skills["skill"] == sk].sort_values("date")
            unit = sub.iloc[0]["unit"]
            fig = go.Figure()
            fig.add_scatter(x=sub["date"], y=sub["value"], mode="lines+markers",
                            line=dict(color=theme.ACCENT, width=3),
                            marker=dict(size=10, color=theme.ACCENT))
            fig.update_layout(
                title=f"{sk} ({unit})",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=250, margin=dict(l=10, r=10, t=40, b=10),
            )
            ui.plotly(fig).classes("w-full")

    charts_panel()
