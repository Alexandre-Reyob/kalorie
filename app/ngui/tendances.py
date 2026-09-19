"""Tendances — analytics complets, organisés par question.

Tabs : Trajectoire (poids+réconcilié) · Énergie (bilan net) · Nutrition · Sport.

Convention :
- Bilan net = intake − TDEE
- Couleurs ADAPTÉES à l'objectif courant (profile["goal"]) :
  cut/maintien/recomp → net < 0 (déficit) = ✅ vert · net > 0 (surplus) = 🟠
  bulk → INVERSÉ : net > 0 (surplus, le but) = ✅ vert · net < 0 = 🟠
"""
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

from core import storage, nutrition, energy, sport, weight as weight_mod
from . import theme, widgets


def _style(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, sans-serif", color=theme.TEXT, size=13),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
    )
    return fig


def render():
    with ui.tabs().classes("w-full") as tabs:
        t_traj   = ui.tab("📉 Trajectoire")
        t_net    = ui.tab("⚡ Énergie")
        t_macros = ui.tab("🍽️ Nutrition")
        t_sport  = ui.tab("💪 Sport")
    with ui.tab_panels(tabs, value=t_traj).classes("w-full"):
        with ui.tab_panel(t_traj):
            _render_weight()
        with ui.tab_panel(t_net):
            _render_net()
        with ui.tab_panel(t_macros):
            _render_macros()
        with ui.tab_panel(t_sport):
            _render_sport()


# =========================================================
# BILAN NET (= ex contenu Énergie)
# =========================================================
def _render_net():
    tbl = energy.corrected_energy_table()
    if tbl.empty:
        ui.label("Pas de données.").classes("opacity-60")
        return

    profile = storage.load_profile()
    bulking = energy.is_bulk(profile)
    targets = energy.effective_targets()
    rec = energy.reconciled()
    s_roll = energy.summary(window_days=energy.ROLLING_WINDOW_DAYS)
    avg7 = energy.intake_average(date.today(), days=7)

    ui.html(f'<div style="font-size:0.78rem; color:{theme.MUTED}; margin-bottom:6px;">'
            f'<b style="color:{theme.ACCENT_SOFT};">≈</b> = estimé par le modèle calorique · '
            f'± = IC95 déduit de ta balance</div>')

    with ui.grid(columns=4).classes("w-full gap-3"):
        if avg7:
            widgets.metric_card("Intake 7 jours", f"{avg7['mean']:.0f}",
                                f"loggé · écart-type {avg7['sd']:.0f}")
        widgets.metric_card("Cible", f"{targets['kcal']:.0f}", "kcal/jour")
        if rec.get("ok"):
            widgets.metric_card("TDEE (balance)", f"{rec['tdee']:.0f} ±{rec['ci95']:.0f}", "Kalman · IC95")
        widgets.metric_card("Dépense modèle", f"≈ {s_roll['avg_tdee']:.0f}",
                            f"composants ×k · {s_roll['window_days']}j")

    # --- Intake par jour vs cible : la régularité ---
    widgets.section_title("Intake par jour vs cible", "bar_chart")
    ui.label("Barres = intake loggé · trait = moyenne glissante 7 jours · pointillés = cible. "
             "C'est la moyenne qui fait le rythme, pas un jour isolé.") \
        .classes("opacity-60 text-sm q-mb-sm")
    done = energy.complete_days(tbl)
    dates = done["date"].tolist()
    roll = done.set_index(pd.to_datetime(done["date"]))["intake"].rolling("7D").mean()
    fig_in = go.Figure()
    fig_in.add_bar(x=dates, y=done["intake"], name="Intake",
                   marker=dict(color=theme.ACCENT, opacity=0.55),
                   hovertemplate="%{x}<br>%{y:.0f} kcal<extra></extra>")
    fig_in.add_scatter(x=dates, y=roll.to_numpy(), mode="lines", name="Moyenne 7j",
                       line=dict(color="#ffffff", width=3),
                       hovertemplate="%{x}<br>moy. %{y:.0f}<extra></extra>")
    fig_in.add_hline(y=targets["kcal"], line_dash="dash", line_color=theme.ACCENT_SOFT,
                     annotation_text=f"cible {targets['kcal']:.0f}")
    fig_in.update_layout(height=280, legend=dict(orientation="h", y=1.08, x=0),
                         yaxis=dict(title="kcal"))
    ui.plotly(_style(fig_in)).classes("w-full")

    def _on_target(v):
        return v >= 0 if bulking else v <= 0

    # --- Détail tableau ---
    widgets.section_title("Détail par jour", "table_rows")
    for _, r in tbl[::-1].iterrows():
        net_col = theme.ACCENT if _on_target(r["net"]) else theme.WARN
        label = "déficit" if r["net"] <= 0 else "surplus"
        ui.html(f"""
        <div class="item-row" style="display:flex; gap:14px; align-items:center;
             flex-wrap:wrap; margin-bottom:4px;">
          <b style="min-width:90px;">{r['date']}</b>
          <span style="opacity:0.7; font-size:0.85rem;">in {r['intake']:.0f}</span>
          <span style="opacity:0.7; font-size:0.85rem;">🚶 {r['steps']:.0f}p
                ({r['steps_kcal']:.0f})</span>
          <span style="opacity:0.7; font-size:0.85rem;">💪 {r['sport_kcal']:.0f}</span>
          <span style="opacity:0.7; font-size:0.85rem;">TDEE {r['tdee']:.0f}</span>
          <b style="color:{net_col}; margin-left:auto;">
              {r['net']:+.0f} <span style="font-size:0.75rem;">({label})</span></b>
        </div>
        """)


# =========================================================
# MACROS (ex dashboard)
# =========================================================
def _render_macros():
    targets = energy.effective_targets()  # dynamique : poids courant + TDEE rolling 14j
    foods = storage.load_foods()
    meals = storage.load_meals()
    m = nutrition.meal_macros(meals, foods)
    daily = nutrition.daily_totals(m)

    if daily.empty:
        ui.label("Pas encore de repas loggés.").classes("opacity-70")
        return

    widgets.section_title("Macros par jour", "pie_chart")
    dates = daily["date"].tolist()
    macros_cfg = [
        ("Protéines (g)", "protein_g", theme.ACCENT,
         targets["protein_g"], targets["protein_g_min"]),
        ("Lipides (g)",   "fat_g",     theme.WARN,
         targets["fat_g"],     targets["fat_g_min"]),
        ("Glucides (g)",  "carbs_g",   "#6366f1",
         targets["carbs_g"],   targets["carbs_g_min"]),
    ]
    for title, col, color, tgt, tgt_min in macros_cfg:
        avg_val = float(daily[col].mean())
        fig_m = go.Figure()
        fig_m.add_bar(x=dates, y=daily[col], name="Réalisé",
                      marker=dict(color=color, opacity=0.75),
                      hovertemplate="%{x}<br>%{y:.0f} g<extra></extra>")
        fig_m.add_scatter(x=[dates[0], dates[-1]], y=[tgt]*2,
                          mode="lines", name=f"Cible {tgt:.0f}g",
                          line=dict(dash="dash", color="#ffffff", width=2.5))
        fig_m.add_scatter(x=[dates[0], dates[-1]], y=[tgt_min]*2,
                          mode="lines", name=f"Min {tgt_min:.0f}g",
                          line=dict(dash="dash", color="#ef4444", width=2.5))
        fig_m.add_scatter(x=[dates[0], dates[-1]], y=[avg_val]*2,
                          mode="lines", name=f"Moy. {avg_val:.0f}g",
                          line=dict(dash="dot", color=color, width=2.5))
        fig_m.update_layout(height=220, showlegend=True,
                            legend=dict(orientation="h", y=1.12, x=0),
                            yaxis=dict(title=title))
        widgets.section_title(title, "show_chart")
        ui.plotly(_style(fig_m)).classes("w-full")


# =========================================================
# POIDS
# =========================================================
def _render_weight():
    weight_df = storage.load_weight()
    if weight_df.empty:
        ui.label("Aucune pesée enregistrée — va dans Log → Poids.") \
            .classes("opacity-60 q-mt-md")
        return

    profile = storage.load_profile()
    goal = profile.get("goal_weight_kg")
    rec = energy.reconciled()
    rs = energy.rate_status(rec, profile)

    # --- Cartes : tout vient du même filtre de Kalman ---
    if rec.get("ok"):
        with ui.grid(columns=4).classes("w-full gap-3"):
            widgets.metric_card("Poids hors eau", f"{rec['weight']:.2f} kg",
                                f"Kalman · eau estimée {rec['water']:+.2f} kg")
            if rs["ok"]:
                widgets.metric_card("Rythme", f"{rs['rate']:+.2f} ±{rs['ci95']:.2f}",
                                    f"kg/mois (IC95) · visé {rs['target']:.1f}",
                                    value_color=theme.rate_color(rs))
            if goal:
                eta = weight_mod.eta_to_goal(
                    rec["weight"], rs["rate"] * 7 / 30 if rs["ok"] else 0.0, goal,
                    reliable=rs["ok"] and rs["ci95"] <= 0.3,
                    target_rate_kg_per_month=profile.get("target_rate_kg_per_month"))
                sub = f"{eta['weeks']:.0f} sem · {eta['source']}" if eta["reachable"] else "pas au bon rythme"
                widgets.metric_card("Objectif", f"{goal:.0f} kg", sub)
            widgets.metric_card("TDEE (balance)", f"{rec['tdee']:.0f} ±{rec['ci95']:.0f}",
                                f"Kalman · IC95 · {rec['n_obs']} pesées")

    # --- Courbe : pesées brutes + poids hors eau (lissage Kalman) ---
    widgets.section_title("Évolution du poids", "monitor_weight")
    ui.label("Points = pesées brutes · Ligne = poids hors eau (Kalman lissé) · bande = IC95") \
        .classes("opacity-60 text-sm q-mb-sm")
    fig = go.Figure()
    full = rec.get("full_history")
    if full is not None and not full.empty:
        fig.add_scatter(x=full["date"], y=full["W_s"] + 1.96 * full["W_s_sd"], mode="lines",
                        line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=full["date"], y=full["W_s"] - 1.96 * full["W_s_sd"], mode="lines",
                        line=dict(width=0), fill="tonexty", fillcolor="rgba(255,255,255,0.08)",
                        showlegend=False, hoverinfo="skip")
    for moment, color in [("matin", theme.ACCENT), ("soir", theme.WARN)]:
        sub = weight_df[weight_df["moment"] == moment]
        if not sub.empty:
            fig.add_scatter(x=sub["date"], y=sub["weight_kg"],
                            mode="markers",
                            name=f"Pesée {moment}",
                            marker=dict(size=8, color=color, opacity=0.55,
                                         line=dict(color=theme.BG, width=1)),
                            hovertemplate="%{x}<br>%{y:.1f} kg<extra></extra>")
    if full is not None and not full.empty:
        fig.add_scatter(x=full["date"], y=full["W_s"], mode="lines",
                        name="Poids hors eau",
                        line=dict(color="#ffffff", width=3),
                        hovertemplate="%{x}<br>%{y:.2f} kg<extra></extra>")
    if goal:
        fig.add_hline(y=goal, line_dash="dash", line_color=theme.ACCENT,
                      annotation_text=f"Objectif {goal:.0f} kg")
    fig.update_yaxes(range=[weight_df["weight_kg"].min()-1.5,
                             weight_df["weight_kg"].max()+1.5],
                     title="Poids (kg)")
    fig.update_layout(legend=dict(orientation="h", y=1.08))
    ui.plotly(_style(fig)).classes("w-full")

    # --- Trajectoire visée vs réelle depuis le début de la phase ---
    bt = energy.bulk_trajectory(rec, profile)
    if bt["ok"]:
        widgets.section_title("Objectif vs réel — depuis le début de la phase", "rule")
        ui.label(f"Départ = poids hors eau lissé au {bt['dates'][0]} ({bt['start_weight']:.2f} kg) · "
                 f"pointillés = +{profile.get('target_rate_kg_per_month'):.1f} kg/mois · "
                 f"écart aujourd'hui {bt['gap_kg']:+.2f} kg (repère, pas une dette à rattraper)") \
            .classes("opacity-60 text-sm q-mb-sm")
        up = [a + 1.96 * s_ for a, s_ in zip(bt["actual"], bt["actual_sd"])]
        lo = [a - 1.96 * s_ for a, s_ in zip(bt["actual"], bt["actual_sd"])]
        fig_bp = go.Figure()
        fig_bp.add_scatter(x=bt["dates"], y=up, mode="lines", line=dict(width=0),
                           showlegend=False, hoverinfo="skip")
        fig_bp.add_scatter(x=bt["dates"], y=lo, mode="lines", line=dict(width=0),
                           fill="tonexty", fillcolor="rgba(52,211,153,0.12)",
                           name="IC95", hoverinfo="skip")
        fig_bp.add_scatter(x=bt["dates"], y=bt["expected"], mode="lines",
                           name="Attendu (rythme visé)",
                           line=dict(color=theme.MUTED, width=2, dash="dash"))
        fig_bp.add_scatter(x=bt["dates"], y=bt["actual"], mode="lines",
                           name="Réel (hors eau)",
                           line=dict(color=theme.ACCENT_SOFT, width=3))
        fig_bp.update_layout(height=260, yaxis=dict(title="Poids (kg)"),
                             legend=dict(orientation="h", y=1.1, x=0))
        ui.plotly(_style(fig_bp)).classes("w-full")

    meas = storage.load_measures()
    widgets.section_title("Tour de taille", "straighten")
    if meas.empty:
        ui.label("Pas encore de mesure — 1×/semaine dans Log → Poids. Poids qui monte + taille "
                 "stable = muscle ; les deux qui montent vite = trop de gras.") \
            .classes("opacity-60 text-sm")
    else:
        fig_w = go.Figure()
        fig_w.add_scatter(x=meas["date"], y=meas["waist_cm"], mode="lines+markers",
                          name="Tour de taille", line=dict(color=theme.WARN, width=3))
        fig_w.update_layout(height=220, yaxis=dict(title="cm"))
        ui.plotly(_style(fig_w)).classes("w-full")

    # --- TDEE : réconcilié (Kalman sur la balance) vs composants BRUT ---
    raw_tbl = energy.complete_days(energy.build_energy_table())
    comp_avg = float(raw_tbl.tail(energy.ROLLING_WINDOW_DAYS)["tdee"].mean()) \
        if not raw_tbl.empty else 0.0
    if rec["ok"]:
        widgets.section_title("TDEE : balance vs modèle", "balance")
        diff = comp_avg - rec["tdee"]
        significant = abs(diff) > rec["ci95"]
        rate, rate_ci = rec.get("rate_kg_month"), 1.96 * rec.get("rate_kg_month_sd", 0)
        rate_txt = (f"À ton intake des 14 derniers jours ({rec['intake_mean']:.0f} kcal) : "
                    f"<b>{rate:+.2f} ± {rate_ci:.2f} kg/mois</b> (IC95)." if rate is not None else "")
        ui.html(f"""
        <div style="background:rgba(99,102,241,0.06); border:1px solid rgba(99,102,241,0.2);
                    border-radius:12px; padding:14px 18px;">
          <div style="display:flex; gap:28px; flex-wrap:wrap;">
            <div><div style="color:{theme.MUTED}; font-size:0.72rem; text-transform:uppercase;">
                 Réconcilié (balance)</div>
                 <div style="font-size:1.4rem; font-weight:700;">{rec['tdee']:.0f}
                 <span style="font-size:0.9rem; color:{theme.MUTED};">±{rec['ci95']:.0f}</span></div></div>
            <div><div style="color:{theme.MUTED}; font-size:0.72rem; text-transform:uppercase;">
                 Composants (modèle brut)</div>
                 <div style="font-size:1.4rem; font-weight:700; opacity:0.7;">{comp_avg:.0f}</div></div>
            <div><div style="color:{theme.MUTED}; font-size:0.72rem; text-transform:uppercase;">
                 Écart</div>
                 <div style="font-size:1.4rem; font-weight:700; color:{theme.WARN if significant else theme.ACCENT};">
                 {diff:+.0f}</div></div>
          </div>
          <div style="margin-top:8px; color:{theme.MUTED}; font-size:0.8rem;">
            {rate_txt}<br>
            Filtre de Kalman : TDEE caché + eau autocorrélée + bruit de pesée, recalé chaque
            matin. L'écart avec le modèle n'est significatif que s'il dépasse l'IC
            ({'oui' if significant else 'non'} ici).
          </div>
        </div>
        """)
        hist = rec["history"]
        fig_t = go.Figure()
        fig_t.add_scatter(x=hist["date"], y=hist["T"] + 1.96 * hist["T_sd"], mode="lines",
                          line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig_t.add_scatter(x=hist["date"], y=hist["T"] - 1.96 * hist["T_sd"], mode="lines",
                          line=dict(width=0), fill="tonexty", fillcolor="rgba(99,102,241,0.18)",
                          name="IC95", hoverinfo="skip")
        fig_t.add_scatter(x=hist["date"], y=hist["T"], mode="lines", name="TDEE (Kalman)",
                          line=dict(color=theme.ACCENT_SOFT, width=3),
                          hovertemplate="%{x}<br>%{y:.0f} kcal<extra></extra>")
        fig_t.add_hline(y=comp_avg, line_dash="dot", line_color=theme.MUTED,
                        annotation_text=f"modèle composants {comp_avg:.0f}")
        fig_t.update_layout(height=260, yaxis=dict(title="kcal/j"),
                            legend=dict(orientation="h", y=1.1, x=0))
        ui.plotly(_style(fig_t)).classes("w-full")


# =========================================================
# VOLUME SPORT
# =========================================================
def _render_sport():
    sessions = storage.load_sessions()
    steps_df = storage.load_steps()

    # --- Progression force : première vs dernière meilleure série par exo ---
    bs = sport.best_sets(storage.load_exos())
    widgets.section_title("Progression force", "trending_up")
    if bs.empty:
        ui.label("Aucune série loggée.").classes("opacity-60")
    else:
        ui.label("Meilleure série = lest le plus lourd, puis le plus de reps.") \
            .classes("opacity-60 text-sm q-mb-sm")
        for exo, g in bs.groupby("exo"):
            first, last = g.iloc[0], g.iloc[-1]
            rec = g.sort_values(["weight_kg", "reps"]).iloc[-1]
            fmt = lambda r: f"{int(r['reps'])} × {'+%.1f kg' % r['weight_kg'] if r['weight_kg'] else 'PDC'}"
            ui.html(f'<div class="item-row" style="display:flex; gap:16px; flex-wrap:wrap; font-size:0.88rem; '
                    f'margin-bottom:4px;"><b style="min-width:190px;">{exo}</b>'
                    f'<span style="color:{theme.MUTED};">début {fmt(first)} ({first["date"]})</span>'
                    f'<span style="color:{theme.MUTED};">dernier {fmt(last)} ({last["date"]})</span>'
                    f'<b style="margin-left:auto; color:{theme.ACCENT_SOFT};">record {fmt(rec)}</b></div>')

    widgets.section_title("Volume sport hebdo", "fitness_center")

    if not sessions.empty:
        vol = sport.weekly_volume(sessions, weight_kg=storage.current_weight())
        if not vol.empty:
            with ui.grid(columns=2).classes("w-full gap-4"):
                fig_dur = px.bar(vol, x="week", y="duration_min", color="type",
                                  labels={"duration_min":"Minutes","week":"Semaine"},
                                  color_discrete_map={"escalade":theme.ACCENT,
                                                       "course":"#6366f1",
                                                       "street_workout":theme.WARN})
                fig_dur.update_layout(title="Minutes / semaine")
                ui.plotly(_style(fig_dur)).classes("w-full")

                fig_k = px.bar(vol, x="week", y="kcal", color="type",
                                labels={"kcal":"kcal","week":"Semaine"},
                                color_discrete_map={"escalade":theme.ACCENT,
                                                     "course":"#6366f1",
                                                     "street_workout":theme.WARN})
                fig_k.update_layout(title="kcal / semaine")
                ui.plotly(_style(fig_k)).classes("w-full")
    else:
        ui.label("Aucune séance loggée.").classes("opacity-60 q-mt-sm")

    # --- Pas hebdo ---
    if not steps_df.empty:
        widgets.section_title("Pas par semaine", "directions_walk")
        s = steps_df.copy()
        s["date"] = pd.to_datetime(s["date"])
        s["week"] = s["date"].dt.to_period("W").apply(lambda r: r.start_time.date())
        weekly_steps = s.groupby("week").agg(
            steps=("steps", "sum"),
            kcal=("steps_kcal", "sum")).reset_index()
        avg_steps = int(weekly_steps["steps"].mean())

        with ui.grid(columns=2).classes("w-full gap-4"):
            fig_s = go.Figure()
            fig_s.add_bar(x=weekly_steps["week"], y=weekly_steps["steps"],
                          marker=dict(color="#6366f1"),
                          hovertemplate="%{x}<br>%{y:,.0f} pas<extra></extra>")
            fig_s.add_scatter(x=[weekly_steps["week"].iloc[0], weekly_steps["week"].iloc[-1]],
                              y=[avg_steps]*2, mode="lines", name=f"Moy. {avg_steps:,}",
                              line=dict(dash="dot", color="#ffffff", width=2))
            fig_s.update_layout(title="Pas / semaine", showlegend=True,
                                legend=dict(orientation="h", y=1.12, x=0))
            ui.plotly(_style(fig_s)).classes("w-full")

            fig_sk = go.Figure()
            fig_sk.add_bar(x=weekly_steps["week"], y=weekly_steps["kcal"],
                           marker=dict(color=theme.ACCENT),
                           hovertemplate="%{x}<br>%{y:.0f} kcal<extra></extra>")
            fig_sk.update_layout(title="kcal marche / semaine")
            ui.plotly(_style(fig_sk)).classes("w-full")
