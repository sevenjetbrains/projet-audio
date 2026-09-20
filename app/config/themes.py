"""Thèmes de l'application (feuille de style + couleurs des widgets dessinés à la main) et préférence persistée.

Les deux thèmes partagent un unique gabarit QSS (`base.qss`) : seule la palette
change, ce qui évite d'entretenir deux feuilles de style en parallèle.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from types import MappingProxyType
from typing import Mapping

from app.config.palette import DARK_PALETTE, LIGHT_PALETTE
from app.config.settings import PROJECT_ROOT

STYLES_DIR = PROJECT_ROOT / "resources" / "styles"
THEME_PREFERENCE_FILE = PROJECT_ROOT / "theme.json"
DEFAULT_THEME = "Sombre"


@dataclass(frozen=True)
class Theme:
    name: str
    stylesheet_file: str
    waveform_background: str
    waveform_text: str
    waveform_color: str
    playhead_color: str
    palette: Mapping[str, str] = field(default_factory=dict)

    def color(self, token: str) -> str:
        """Couleur d'un jeton de la palette (voir app/config/palette.py)."""
        return self.palette[token]


def _theme(name: str, palette: dict[str, str]) -> Theme:
    """Thème dérivé d'une palette : les couleurs de la waveform en sont extraites."""
    return Theme(
        name=name,
        stylesheet_file="base.qss",
        waveform_background=palette["wave_bg"],
        waveform_text=palette["wave_text"],
        waveform_color=palette["wave_bar"],
        playhead_color=palette["playhead"],
        palette=MappingProxyType(palette),
    )


THEMES: dict[str, Theme] = {
    "Sombre": _theme("Sombre", DARK_PALETTE),
    "Clair": _theme("Clair", LIGHT_PALETTE),
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def load_stylesheet(theme: Theme) -> str:
    """QSS du thème : gabarit `base.qss` dont chaque `$jeton` reçoit la couleur de la palette.

    Chaîne vide si le fichier est absent : l'application reste utilisable, avec le style Qt par défaut.
    """
    path = STYLES_DIR / theme.stylesheet_file
    if not path.exists():
        return ""
    return Template(path.read_text(encoding="utf-8")).safe_substitute(theme.palette)


def load_theme_preference(store_path: Path | None = None) -> str:
    """Nom du thème mémorisé, ou le thème par défaut si absent/illisible/inconnu."""
    path = store_path or THEME_PREFERENCE_FILE
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


def save_theme_preference(name: str, store_path: Path | None = None) -> None:
    """Mémorise le thème choisi ; une erreur d'écriture est ignorée (préférence non critique)."""
    path = store_path or THEME_PREFERENCE_FILE
    try:
        path.write_text(json.dumps({"theme": name}), encoding="utf-8")
    except OSError:
        pass
