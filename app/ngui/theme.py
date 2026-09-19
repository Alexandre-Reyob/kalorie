"""Thème global + layout/frame partagé pour toutes les pages."""
from contextlib import contextmanager
from nicegui import ui

from core import energy


# Palette
ACCENT      = "#10b981"
ACCENT_SOFT = "#34d399"
WARN        = "#f59e0b"
DANGER      = "#ef4444"
BG          = "#0b0f1a"
SURFACE     = "#161b2e"
TEXT        = "#e5e7eb"
MUTED       = "#9ca3af"


CSS = f"""
<style>
  /* Reset background */
  body {{
    background: radial-gradient(1200px 800px at 10% -10%, #1a2238 0%, {BG} 60%) !important;
    color: {TEXT};
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, "Segoe UI", Roboto, sans-serif;
  }}

  /* Cards */
  .metric-card {{
    background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 18px 20px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    transition: transform 0.18s ease, box-shadow 0.18s ease;
  }}
  .metric-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
  }}
  .metric-label {{
    font-size: 0.75rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-bottom: 6px;
  }}
  .metric-value {{
    font-size: 1.85rem; font-weight: 700; color: #f3f4f6;
    line-height: 1.05; letter-spacing: -0.02em;
  }}
  .metric-sub {{ font-size: 0.78rem; color: {MUTED}; margin-top: 4px; }}

  /* Progress bars */
  .bar-wrap {{
    height: 8px; margin-top: 14px;
    background: rgba(255,255,255,0.06);
    border-radius: 999px; overflow: hidden;
  }}
  .bar-fill {{ height: 100%; border-radius: 999px;
    transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1); }}
  .bar-ok   {{ background: linear-gradient(90deg, {ACCENT}, {ACCENT_SOFT}); }}
  .bar-warn {{ background: linear-gradient(90deg, {WARN}, #fbbf24); }}
  .bar-over {{ background: linear-gradient(90deg, {DANGER}, #f87171); }}

  /* Sidebar */
  .nav-sidebar {{
    background: rgba(11,15,26,0.7);
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.06);
  }}
  .nav-item {{
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-radius: 10px;
    color: {MUTED}; cursor: pointer; transition: all 0.15s;
    text-decoration: none; font-weight: 500;
  }}
  .nav-item:hover {{ background: rgba(255,255,255,0.04); color: {TEXT}; }}
  .nav-item.active {{
    background: rgba(16,185,129,0.12); color: {ACCENT_SOFT};
    border-left: 3px solid {ACCENT};
  }}

  /* Buttons polish */
  .q-btn--standard {{ border-radius: 10px !important; }}

  /* Tabs polish */
  .q-tab {{ border-radius: 10px 10px 0 0 !important; }}
  .q-tab--active {{ background: rgba(16,185,129,0.10) !important; }}

  /* Smooth transitions */
  .smooth {{ transition: all 0.2s ease; }}

  /* Pill badge */
  .pill {{
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(16,185,129,0.10);
    border: 1px solid rgba(16,185,129,0.25);
    color: {ACCENT_SOFT};
    border-radius: 999px; padding: 4px 12px;
    font-size: 0.8rem; font-weight: 500;
  }}

  /* Header bar */
  .top-bar {{
    background: rgba(11,15,26,0.85);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }}

  /* Meal/Session items */
  .item-row {{
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 10px 14px;
    transition: background 0.15s;
  }}
  .item-row:hover {{ background: rgba(255,255,255,0.045); }}

  /* Scrollbar minimal */
  ::-webkit-scrollbar {{ width: 8px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{
    background: rgba(255,255,255,0.1); border-radius: 999px;
  }}
</style>
"""


PAGES = [
    ("/",           "Aujourd'hui", "today"),
    ("/log",        "Log",         "edit_note"),
    ("/tendances",  "Tendances",   "insights"),
    ("/profil",     "Profil",      "person"),
]


def rate_color(rs: dict) -> str:
    """Vert dans la zone visée · orange si hors zone ET significatif · gris si hors zone mais dans le bruit."""
    if rs["zone"] == "in":
        return ACCENT_SOFT
    return WARN if rs["significant"] else MUTED


def _cap_strip():
    """Bandeau CAP (le "nord") : poids hors eau · rythme ±IC · cible active.
    Rendu à droite de la top-bar, visible sur toutes les pages."""
    try:
        cap = energy.cap_summary()
    except Exception:
        return
    parts = []
    if cap["weight"] is not None:
        parts.append(
            f'<span style="color:{MUTED};">Poids</span> '
            f'<b>{cap["weight"]:.1f} kg</b>')
    rs = cap["rate"]
    if rs["ok"]:
        parts.append(
            f'<span style="color:{MUTED};">Rythme</span> '
            f'<b style="color:{rate_color(rs)};">{rs["rate"]:+.1f}</b>'
            f'<span style="color:{MUTED};"> ±{rs["ci95"]:.1f} kg/mois</span>')
    parts.append(
        f'<span style="color:{MUTED};">Cible</span> '
        f'<b>{cap["target_kcal"]:.0f} kcal</b>')
    ui.html('<div style="display:flex; gap:18px; align-items:center; '
            'font-size:0.82rem; white-space:nowrap;">'
            + '<span>' + '</span><span>'.join(parts) + '</span></div>')


def apply():
    """Applique le thème global (CSS + Quasar)."""
    ui.add_head_html(CSS)
    ui.colors(primary=ACCENT, secondary=WARN,
              accent=ACCENT_SOFT, dark="#0b0f1a")


@contextmanager
def frame(title: str, icon: str = "home"):
    """Layout commun : sidebar + top-bar + main content.

    Applique le thème à chaque page (requis NiceGUI 2.x avec @ui.page).
    """
    apply()

    # Top-bar (titre à gauche · bandeau CAP à droite, visible partout)
    with ui.header(elevated=False).classes("top-bar items-center q-px-md"):
        ui.icon(icon, size="1.5em").classes("text-emerald-400")
        ui.label(title).classes("text-lg font-semibold")
        ui.space()
        _cap_strip()

    # Sidebar (drawer)
    with ui.left_drawer(top_corner=True, bottom_corner=True)\
            .classes("nav-sidebar q-pa-md") as drawer:
        ui.label("MENU").classes("text-xs uppercase tracking-widest opacity-60 q-mb-sm")
        for path, label, ic in PAGES:
            with ui.link(target=path).classes("nav-item smooth no-underline"):
                ui.icon(ic, size="1.1em")
                ui.label(label)

    # Bouton pour ouvrir le drawer sur mobile
    # (NiceGUI le gère auto via header button)

    # Main content
    with ui.column().classes("w-full max-w-6xl mx-auto q-pa-md"):
        yield
