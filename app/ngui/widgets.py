"""Composants réutilisables — cartes métriques, badges, etc."""
from nicegui import ui


def metric_card(label: str, value: str, sub: str = "", pct: float | None = None,
                 pct_min: float | None = None, value_color: str | None = None):
    """Carte métrique avec barre de progression optionnelle.

    pct      : ratio current/cible_ideale (1.0 = pile)
    pct_min  : ratio current/plancher_min (1.0 = juste au plancher)
               si fourni, la barre est rouge en dessous du plancher,
               jaune entre plancher et cible, vert au-dessus
    value_color : couleur CSS optionnelle pour surligner la valeur (ex: vert/orange
                  selon si on est dans le rythme visé).
    """
    with ui.element("div").classes("metric-card w-full"):
        ui.html(f'<div class="metric-label">{label}</div>')
        style = f' style="color:{value_color};"' if value_color else ''
        ui.html(f'<div class="metric-value"{style}>{value}</div>')
        if sub:
            ui.html(f'<div class="metric-sub">{sub}</div>')
        if pct is not None:
            if pct_min is not None:
                # 3-zone color logic
                if pct_min < 1.0:
                    cls = "bar-over"   # rouge: sous le plancher
                elif pct < 1.0:
                    cls = "bar-warn"   # jaune: au-dessus du plancher mais sous la cible
                else:
                    cls = "bar-ok"     # vert: à la cible ou au-dessus
            else:
                cls = "bar-over" if pct > 1.1 else ("bar-warn" if pct < 0.6 else "bar-ok")
            width = min(max(pct, 0), 1.3) * 100 / 1.3
            ui.html(f'<div class="bar-wrap"><div class="bar-fill {cls}" '
                    f'style="width: {width:.0f}%"></div></div>')


def info_pill(text: str, color: str = "#10b981"):
    ui.html(f'<span class="pill">{text}</span>')


def section_title(text: str, icon: str | None = None):
    with ui.row().classes("items-center gap-2 q-mt-lg q-mb-sm"):
        if icon:
            ui.icon(icon, size="1.2em").classes("text-emerald-400")
        ui.label(text).classes("text-lg font-semibold")


_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
         "septembre", "octobre", "novembre", "décembre"]


def fr_date(d) -> str:
    return f"{_JOURS[d.weekday()].capitalize()} {d.day} {_MOIS[d.month - 1]} {d.year}"
