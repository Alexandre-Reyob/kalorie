"""Point d'entrée NiceGUI — tracker nutrition/poids avec TDEE par filtre de Kalman.

Structure (4 pages) :
- Aujourd'hui : tableau de bord du jour (CAP + cible + repas)
- Log        : repas / aliment / sport / poids / pas
- Tendances  : trajectoire / énergie / nutrition / sport
- Profil     : config

Lancement :  python app/main.py   (génère des données de démo au premier lancement)
            → http://localhost:8080
Vraies données : TRACKER_DATA=/chemin/vers/dossier python app/main.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nicegui import ui

from core import storage
from ngui import theme, home, log, tendances, profil

if not storage.PROFILE.exists():
    import make_demo_data
    make_demo_data.main()


@ui.page("/")
def page_home():
    with theme.frame("Aujourd'hui", "today"):
        home.render()

@ui.page("/log")
def page_log():
    with theme.frame("Log", "edit_note"):
        log.render()

@ui.page("/tendances")
def page_tendances():
    with theme.frame("Tendances", "insights"):
        tendances.render()

@ui.page("/profil")
def page_profil():
    with theme.frame("Profil", "person"):
        profil.render()


if __name__ in {"__main__", "__mp_main__"}:
    import os
    ui.run(
        title="Kalorie",
        favicon="🥗",
        dark=True,
        port=int(os.environ.get("TRACKER_PORT", 8080)),

        reload=True,
        storage_secret="kalorie-local",
    )
