"""Dispositions de la fenêtre principale (agencement des panneaux) et préférence persistée.

Les deux dispositions montrent exactement les mêmes panneaux : seule leur place
change. « A » est l'agencement d'origine en trois colonnes (lecteur à gauche,
waveform au centre, séquences à droite) ; « B » met les séquences à gauche, le
lecteur au centre, la source à droite, et pose la waveform sur toute la largeur
en bas.

Le choix est mémorisé comme celui du thème, dans son propre fichier à la racine.
"""

import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from app.config.settings import PROJECT_ROOT

LAYOUT_PREFERENCE_FILE = PROJECT_ROOT / "layout.json"
DEFAULT_LAYOUT = "A"

# Identifiant → libellé du menu Affichage. Le bouton de la barre d'outils n'affiche, lui,
# que « Disposition <identifiant> » : la place y est comptée.
LAYOUTS: Mapping[str, str] = MappingProxyType(
    {
        "A": "A — lecteur à gauche, waveform au centre",
        "B": "B — waveform sur toute la largeur",
    }
)


def get_layout(name: str) -> str:
    """Identifiant de disposition valide : celui demandé, ou celui par défaut s'il est inconnu."""
    return name if name in LAYOUTS else DEFAULT_LAYOUT


def next_layout(name: str) -> str:
    """Disposition suivante dans l'ordre du menu (le bouton de la barre d'outils tourne en rond)."""
    names = list(LAYOUTS)
    return names[(names.index(get_layout(name)) + 1) % len(names)]


def load_layout_preference(store_path: Path | None = None) -> str:
    """Disposition mémorisée, ou celle par défaut si le fichier est absent/illisible/inconnu."""
    path = store_path or LAYOUT_PREFERENCE_FILE
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("layout")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_LAYOUT
    return name if name in LAYOUTS else DEFAULT_LAYOUT


def save_layout_preference(name: str, store_path: Path | None = None) -> None:
    """Mémorise la disposition choisie ; une erreur d'écriture est ignorée (préférence non critique)."""
    path = store_path or LAYOUT_PREFERENCE_FILE
    try:
        path.write_text(json.dumps({"layout": name}), encoding="utf-8")
    except OSError:
        pass
