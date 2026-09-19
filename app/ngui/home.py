"""Accueil — résumé d'un jour (date picker, défaut aujourd'hui).

Convention :
- Bilan net = intake − TDEE
- Couleurs ADAPTÉES à l'objectif courant (profile["goal"]) :
  cut/maintien/recomp → net < 0 (déficit) = ✅ vert · net > 0 (surplus) = 🟠
  bulk → INVERSÉ : net > 0 (surplus, le but) = ✅ vert · net < 0 = 🟠
"""
import math
from datetime import date, timedelta
import pandas as pd
from nicegui import ui

from core import storage, nutrition, energy, sport, weight as weight_mod
from . import theme, widgets


def _kcal_ring(kcal: float, target: float, bulking: bool = False) -> str:
    """Anneau SVG kcal.

    Sèche/maintien : vert tant qu'on est SOUS la cible (déficit), orange sinon.
    Bulk : inversé — vert à partir de la cible atteinte (il faut le surplus
    pour progresser), orange tant qu'on est EN DESSOUS.
    """
    r, sw = 52, 11
    circ = 2 * math.pi * r
    pct = kcal / target if target else 0
    off = circ * (1 - min(max(pct, 0), 1))
    on_track = kcal >= target if bulking else kcal <= target
    color = theme.ACCENT if on_track else theme.WARN
    reste = target - kcal
    if bulking:
        reste_txt = (f"<span style='color:{theme.WARN};'>reste {reste:.0f} kcal à manger</span>"
                     if reste > 0 else f"+{-reste:.0f} au-dessus ✅")
    else:
        reste_txt = (f"reste {reste:.0f} kcal" if reste >= 0
                     else f"<span style='color:{theme.WARN};'>+{-reste:.0f} au-dessus</span>")
    return f"""
    <div style="display:flex; flex-direction:column; align-items:center;">
      <svg width="128" height="128" viewBox="0 0 128 128">
        <circle cx="64" cy="64" r="{r}" fill="none"
                stroke="rgba(255,255,255,0.08)" stroke-width="{sw}"/>
        <circle cx="64" cy="64" r="{r}" fill="none" stroke="{color}"
                stroke-width="{sw}" stroke-linecap="round"
                stroke-dasharray="{circ:.0f}" stroke-dashoffset="{off:.0f}"
                transform="rotate(-90 64 64)"/>
        <text x="64" y="60" text-anchor="middle" fill="#f3f4f6"
              font-size="24" font-weight="700">{kcal:.0f}</text>
        <text x="64" y="80" text-anchor="middle" fill="{theme.MUTED}"
              font-size="12">/ {target:.0f} kcal</text>
      </svg>
      <div style="font-size:0.76rem; color:{theme.MUTED}; margin-top:4px;">{reste_txt}</div>
    </div>"""


def _macro_bar(label: str, val: float, tgt: float, tgt_min: float, color: str) -> str:
    """Barre macro compacte : rouge sous le plancher, ambre sous la cible, couleur pleine sinon."""
    pct = min(max(val / tgt, 0), 1) * 100 if tgt else 0
    if val < tgt_min:
        bar = theme.DANGER
    elif val < tgt:
        bar = theme.WARN
    else:
        bar = color
    return f"""
    <div>
      <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
        <span>{label}</span>
        <span style="color:{theme.MUTED};">{val:.0f} / {tgt:.0f} g</span>
      </div>
      <div style="height:7px; background:rgba(255,255,255,0.06); border-radius:99px;">
        <div style="width:{pct:.0f}%; height:100%; background:{bar}; border-radius:99px;"></div>
      </div>
    </div>"""


@ui.refreshable
def _checkin_banner():
    """Point hebdo : propose la nouvelle cible, figée jusqu'au prochain point une fois validée."""
    p = energy.checkin_proposal()
    if not (p["ok"] and p["due"]):
        return
    before = (f"actuelle {p['target_before']:.0f} → " if p["target_before"] is not None
              else "première cible figée : ")
    cap = " (variation plafonnée à ±150)" if p["capped"] else ""
    intake = f" · intake 7j {p['intake_7d']:.0f}" if p["intake_7d"] else ""

    def _ok():
        energy.validate_checkin()
        ui.notify("Cible figée jusqu'au prochain point", color="positive", position="top")
        ui.navigate.reload()

    with ui.card().classes("w-full q-mb-md").style(
            "background:rgba(99,102,241,0.08); border:1px solid rgba(99,102,241,0.3); border-radius:14px;"):
        ui.html(f'<div style="font-size:12px; letter-spacing:0.09em; color:{theme.MUTED};">POINT HEBDO</div>'
                f'<div style="margin-top:4px;">TDEE <b>{p["tdee"]:.0f} ±{p["tdee_ci95"]:.0f}</b> · '
                f'rythme <b>{p["rate"]:+.1f} ±{p["rate_ci95"]:.1f} kg/mois</b>{intake}</div>'
                f'<div style="margin-top:4px;">Cible : {before}<b style="color:{theme.ACCENT_SOFT};">'
                f'{p["target_proposed"]:.0f} kcal</b>{cap}</div>')
        ui.button("Valider la cible", on_click=_ok, icon="check").props("color=primary unelevated dense")


def render():
    state = {"date": date.today()}
    _checkin_banner()

    profile = storage.load_profile()
    targets = energy.effective_targets()  # poids courant + TDEE rolling 14j
    foods = storage.load_foods()

    # --- Navigation date ---
    with ui.row().classes("w-full items-center gap-2 q-mb-md"):
        ui.button(icon="chevron_left",
                  on_click=lambda: (state.update(date=state["date"]-timedelta(days=1)),
                                     date_in.set_value(state["date"].isoformat()),
                                     content.refresh())) \
            .props("flat round")
        date_in = ui.input(value=date.today().isoformat()) \
            .props("dense outlined type=date").classes("flex-1")
        date_in.on_value_change(lambda e: (state.update(date=date.fromisoformat(e.value)),
                                            content.refresh()))
        ui.button(icon="chevron_right",
                  on_click=lambda: (state.update(date=state["date"]+timedelta(days=1)),
                                     date_in.set_value(state["date"].isoformat()),
                                     content.refresh())) \
            .props("flat round")
        ui.button("📅 Aujourd'hui",
                  on_click=lambda: (state.update(date=date.today()),
                                     date_in.set_value(date.today().isoformat()),
                                     content.refresh())) \
            .props("color=primary outline rounded")

    @ui.refreshable
    def content():
        d = state["date"]
        ui.label(widgets.fr_date(d)).classes("text-xl font-bold q-mb-sm")

        meals = storage.load_meals()
        sessions = storage.load_sessions()
        exos = storage.load_exos()

        day_meals = meals[meals["date"] == d] if not meals.empty else meals
        day_sessions = sessions[sessions["date"] == d] if not sessions.empty else sessions
        day_exos = exos[exos["date"] == d] if not exos.empty else exos

        m = nutrition.meal_macros(day_meals, foods)
        kcal = float(m["kcal"].sum()) if not m.empty else 0
        prot = float(m["protein_g"].sum()) if not m.empty else 0
        lip  = float(m["fat_g"].sum()) if not m.empty else 0
        glu  = float(m["carbs_g"].sum()) if not m.empty else 0

        # ============ CAP — OÙ J'EN SUIS (une seule source : le Kalman) ============
        rec = energy.reconciled()
        rs = energy.rate_status(rec, profile)
        goal = profile.get("goal_weight_kg")
        bulking = energy.is_bulk(profile)

        def _big(txt, color=None, unit=""):
            col = f" color:{color};" if color else ""
            return (f'<div style="font-size:1.5rem; font-weight:700;{col}">{txt}'
                    f'<span style="font-size:0.8rem; color:{theme.MUTED};">{unit}</span></div>')

        def _sub(txt, color=None):
            return (f'<div style="font-size:0.72rem; color:{color or theme.MUTED}; '
                    f'margin-top:3px;">{txt}</div>')

        if rec.get("ok"):
            last_y = rec["history"]["y"].dropna()
            raw = f" · pesée {last_y.iloc[-1]:.2f}" if not last_y.empty else ""
            c_poids = _big(f"{rec['weight']:.1f}", unit=" kg") + _sub(f"hors eau · Kalman{raw}")
        else:
            c_poids = _big("—") + _sub("pas assez de pesées")

        if rs["ok"]:
            verdict = {"in": "dans la zone visée", "above": "au-dessus de la zone",
                       "below": "en dessous de la zone"}[rs["zone"]]
            if rs["zone"] != "in" and not rs["significant"]:
                verdict += " (pas significatif)"
            c_rate = (_big(f"{rs['rate']:+.1f}", theme.rate_color(rs), f" ±{rs['ci95']:.1f} kg/mois")
                      + _sub(f"visé {rs['target']:.1f} · {verdict}"))
        else:
            c_rate = _big("—") + _sub("pas assez de pesées")

        if goal and rec.get("ok"):
            rate_wk = rs["rate"] * 7 / 30 if rs["ok"] else 0.0
            eta = weight_mod.eta_to_goal(
                rec["weight"], rate_wk, goal, reliable=rs["ok"] and rs["ci95"] <= 0.3,
                target_rate_kg_per_month=profile.get("target_rate_kg_per_month"))
            c_goal = (_big(f"{eta['weeks']:.0f}", unit=" sem") + _sub(f"{eta['source']} · vers {goal:.0f} kg")
                      if eta["reachable"] else _big(f"{goal:.0f} kg") + _sub("pas au bon rythme", theme.WARN))
        else:
            c_goal = _big("—") + _sub("objectif")

        if rec.get("ok"):
            c_tdee = _big(f"{rec['tdee']:.0f}", theme.ACCENT_SOFT, f" ±{rec['ci95']:.0f}") + _sub("balance · Kalman · IC95")
        else:
            c_tdee = _big(f"≈ {targets['tdee']:.0f}", theme.ACCENT_SOFT) + _sub("estimé · modèle (pas assez de pesées)")

        meas = storage.load_measures()
        if meas.empty:
            c_waist = _big("—") + _sub("à mesurer 1×/semaine (Log → Poids)", theme.WARN)
        else:
            lw = meas.iloc[-1]
            age = (date.today() - lw["date"]).days
            old = meas[meas["date"] <= lw["date"] - timedelta(days=21)]
            delta = f" · {lw['waist_cm'] - old['waist_cm'].iloc[-1]:+.1f} cm / 3 sem" if not old.empty else ""
            c_waist = (_big(f"{lw['waist_cm']:.1f}", unit=" cm")
                       + _sub(f"il y a {age} j{delta}" + (" · à refaire" if age >= 8 else ""),
                              theme.WARN if age >= 8 else None))

        def _card(label, inner, accent=False):
            bg = ("rgba(16,185,129,0.06)" if accent else "rgba(255,255,255,0.03)")
            bd = ("rgba(16,185,129,0.25)" if accent else "rgba(255,255,255,0.08)")
            return (f'<div style="background:{bg}; border:1px solid {bd}; border-radius:14px; padding:13px 15px;">'
                    f'<div style="font-size:10px; letter-spacing:0.07em; color:{theme.MUTED}; '
                    f'text-transform:uppercase; margin-bottom:5px;">{label}</div>{inner}</div>')

        ui.html(f'<div style="display:flex; align-items:center; gap:10px; font-size:12px; '
                f'letter-spacing:0.09em; color:{theme.MUTED}; margin:6px 0 10px;">CAP — OÙ J\'EN SUIS'
                f'<span style="letter-spacing:0; text-transform:none; font-size:11px;">'
                f'(± = IC95 · <b style="color:{theme.ACCENT_SOFT};">≈</b> = modèle calorique)</span></div>'
                f'<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px;">'
                + _card("Poids", c_poids) + _card("Rythme", c_rate)
                + _card(f"Objectif {goal:.0f} kg" if goal else "Objectif", c_goal)
                + _card("Tour de taille", c_waist)
                + _card("TDEE (balance)", c_tdee, accent=True) + '</div>').classes("w-full")

        # ============ FORCE — le levier n°1 (surcharge progressive) ============
        ss = sport.strength_summary(storage.load_exos(), date.today())
        ui.html(f'<div style="font-size:12px; letter-spacing:0.09em; color:{theme.MUTED}; '
                f'margin:18px 0 10px;">FORCE — SURCHARGE PROGRESSIVE</div>')
        if not ss["exos"]:
            since = f"depuis le {ss['last_date']}" if ss["last_date"] else "encore"
            ui.html(f'<div style="background:rgba(245,158,11,0.07); border:1px solid rgba(245,158,11,0.25); '
                    f'border-radius:14px; padding:12px 15px; font-size:0.88rem;">Aucune série loggée {since}. '
                    f'Sans suivi des charges, impossible de savoir si le surplus part en muscle. '
                    f'Logge tes séries (exo, reps, lest) après chaque séance : Log → Sport → Street.</div>').classes("w-full")
        else:
            chips = "".join(
                f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); '
                f'border-radius:12px; padding:9px 12px;"><div style="font-size:0.82rem; font-weight:600;">{e["exo"]}</div>'
                f'<div style="font-size:0.95rem;">{e["reps"]} × {"+%.1f kg" % e["weight_kg"] if e["weight_kg"] else "PDC"}</div>'
                f'<div style="font-size:0.72rem; color:{theme.MUTED};">{e["date"]}'
                + (f' · <span style="color:{theme.ACCENT_SOFT if e["vs"].startswith(("lest +", "+")) else theme.MUTED};">'
                   f'{e["vs"]} vs record</span>' if e["vs"] else "") + '</div></div>'
                for e in ss["exos"])
            ui.html(f'<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); '
                    f'gap:8px;">{chips}</div>').classes("w-full")

        # ============ BILAN DU JOUR ============
        # Jour en cours : pas de dépenses/bilan net (journée incomplète + pas par défaut
        # → un "déficit de 1800" le matin, faux et anxiogène). Seulement ce qui reste à manger.
        is_today = d >= date.today()
        avg7 = energy.intake_average(d, days=7)
        macros_html = (_macro_bar("Protéines", prot, targets["protein_g"],
                                  targets["protein_g_min"], theme.ACCENT)
                       + _macro_bar("Lipides", lip, targets["fat_g"],
                                    targets["fat_g_min"], theme.WARN)
                       + _macro_bar("Glucides", glu, targets["carbs_g"],
                                    targets["carbs_g_min"], "#6366f1"))
        avg_html = ""
        if avg7 is not None:
            dev = avg7["mean"] - targets["kcal"]
            avg_col = theme.ACCENT_SOFT if abs(dev) <= 150 else theme.WARN
            avg_html = (f'<span style="font-size:12px;"><span style="color:{theme.MUTED};">'
                        f'Moyenne {avg7["n"]} derniers jours</span> '
                        f'<b style="color:{avg_col};">{avg7["mean"]:.0f}</b> '
                        f'<span style="color:{theme.MUTED};">({dev:+.0f} vs cible · '
                        f'écart-type {avg7["sd"]:.0f})</span></span>')
        if is_today:
            energy_html = (f'<div style="display:flex; gap:22px; margin-top:4px; padding-top:11px; '
                           f'border-top:1px solid rgba(255,255,255,0.06); flex-wrap:wrap;">{avg_html}</div>')
        else:
            en = energy.day_energy(d)
            net = en["net"]
            on_target_net = net >= 0 if bulking else net <= 0
            net_color = theme.ACCENT_SOFT if on_target_net else theme.WARN
            steps_note = " <span style='color:#f59e0b;'>(défaut 6000)</span>" if en["steps_default"] else ""
            est_share = energy.estimated_share(d)
            est_note = (f" · <span style='color:#f59e0b;'>~{est_share*100:.0f}% estimé</span>"
                        if est_share >= 0.25 else "")
            energy_html = (
                f'<div style="display:flex; gap:22px; margin-top:4px; padding-top:11px; '
                f'border-top:1px solid rgba(255,255,255,0.06); flex-wrap:wrap;">'
                f'<span style="font-size:12px;"><span style="color:{theme.MUTED};">Rentrées</span> <b>{en["intake"]:.0f}</b></span>'
                f'<span style="font-size:12px;"><span style="color:{theme.MUTED};">Dépenses</span> <b>≈{en["tdee"]:.0f}</b></span>'
                f'<span style="font-size:12px;"><span style="color:{theme.MUTED};">Bilan net</span> '
                f'<b style="color:{net_color};">≈{net:+.0f}</b></span></div>'
                f'<div style="color:{theme.MUTED}; font-size:0.76rem;">'
                f'BMR {en["bmr"]:.0f} · NEAT {en["neat"]:.0f} · TEF {en["tef"]:.0f} · '
                f'🚶 {en["steps"]:.0f}p ({en["steps_kcal"]:.0f}){steps_note} · '
                f'💪 {en["sport_kcal"]:.0f} · activité ×{en["k"]:.2f}{est_note}</div>')

        ui.html(f'<div style="display:flex; align-items:center; gap:7px; font-size:12px; '
                f'letter-spacing:0.09em; color:{theme.MUTED}; margin:18px 0 10px;">BILAN DU JOUR</div>'
                f'<div style="display:grid; grid-template-columns:minmax(170px,190px) 1fr; gap:14px;">'
                f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); '
                f'border-radius:14px; padding:16px; display:flex; align-items:center; justify-content:center;">'
                + _kcal_ring(kcal, targets["kcal"], bulking) + '</div>'
                f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); '
                f'border-radius:14px; padding:16px; display:flex; flex-direction:column; gap:11px; justify-content:center;">'
                + macros_html + energy_html + '</div></div>').classes("w-full")

        # --- Repas détaillés ---
        widgets.section_title("Repas", "restaurant")
        if m.empty:
            ui.label("Aucun repas loggé.").classes("opacity-60")
        else:
            ORDER = ["petit_déj", "petit-déj", "déjeuner", "collation", "snack", "apéritif", "dîner"]
            for meal in sorted(m["meal"].unique(),
                                key=lambda x: ORDER.index(x) if x in ORDER else 99):
                sub = m[m["meal"] == meal]
                s_kcal = sub["kcal"].sum()
                s_p = sub["protein_g"].sum()
                s_l = sub["fat_g"].sum()
                s_g = sub["carbs_g"].sum()
                share = s_kcal / kcal * 100 if kcal else 0
                with ui.expansion(
                    f"{meal.upper()} — {s_kcal:.0f} kcal · "
                    f"P{s_p:.0f} L{s_l:.0f} G{s_g:.0f} · {share:.0f}%",
                    value=True).classes("w-full"):
                    for _, row in sub.iterrows():
                        with ui.row().classes("w-full items-center item-row q-mb-xs no-wrap gap-2"):
                            ui.label(row["name"]).classes("flex-1 text-sm")
                            ui.label(f"{row['qty_g']:.0f}g").classes("text-sm opacity-70")\
                              .style("min-width:60px;")
                            ui.label(f"{row['kcal']:.0f} kcal").classes(
                                "text-sm font-semibold").style(
                                f"color:{theme.ACCENT_SOFT}; min-width:80px;")
                            ui.label(f"P{row['protein_g']:.1f} L{row['fat_g']:.1f} G{row['carbs_g']:.1f}").classes(
                                "text-xs opacity-60").style("min-width:130px;")

        # --- Séances ---
        widgets.section_title("Séances", "fitness_center")
        if day_sessions.empty:
            ui.label("Aucune séance.").classes("opacity-60")
        else:
            emoji = {"escalade": "🧗", "course": "🏃", "street_workout": "🦾"}
            for _, s in day_sessions.iterrows():
                counted = bool(s.get("counted_in_steps", False))
                kcal_txt = ("déjà dans les pas" if counted
                            else f"{sport.session_kcal(s['met'], s['active_fraction'], targets['weight_kg'], s['duration_min']):.0f} kcal")
                with ui.expansion(
                    f"{emoji.get(s['type'],'💪')} {s['type']} — "
                    f"{s['duration_min']:.0f}min · {kcal_txt}",
                    value=True).classes("w-full"):
                    if s.get("summary"):
                        ui.markdown(f"**Résumé** : {s['summary']}")
                    if s["type"] == "street_workout" and not day_exos.empty:
                        ui.markdown("**Sets** :")
                        for _, ex in day_exos.iterrows():
                            lest = float(ex["weight_kg"]) if pd.notna(ex["weight_kg"]) else 0
                            hold = int(ex["duration_sec"]) if pd.notna(ex["duration_sec"]) else 0
                            with ui.row().classes("w-full items-center q-mb-xs gap-2"):
                                ui.label(f"{ex['exo']}").classes("flex-1 text-sm font-semibold")
                                ui.label(f"set {int(ex['set_num'])}").classes("text-xs opacity-60")\
                                  .style("min-width:50px;")
                                ui.label(f"{int(ex['reps'])} reps").classes("text-sm")
                                ui.label(f"{lest:+.1f} kg" if lest else "BW").classes(
                                    "text-sm opacity-80")
                                if hold:
                                    ui.label(f"{hold}s").classes("text-sm opacity-70")

    content()
