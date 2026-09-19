"""Thèmes de l'application (feuille de style + couleurs des widgets dessinés à la main) et préférence persistée."""

import json
from dataclasses import dataclass
from pathlib import Path

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


THEMES: dict[str, Theme] = {
    "Sombre": Theme("Sombre", "dark_theme.qss", "#252526", "#999999", "#4fc3f7", "#ff5252"),
    "Clair": Theme("Clair", "light_theme.qss", "#ffffff", "#666666", "#0277bd", "#d32f2f"),
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def load_stylesheet(theme: Theme) -> str:
    """Contenu QSS du thème (chaîne vide si le fichier est absent : l'application reste utilisable)."""
    path = STYLES_DIR / theme.stylesheet_file
    return path.read_text(encoding="utf-8") if path.exists() else ""


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
