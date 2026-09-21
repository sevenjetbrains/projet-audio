"""Profils de traitement enregistrés par l'utilisateur, à côté des profils prédéfinis.

Stockés en JSON dans la racine du projet, comme la liste des projets récents et le thème.
Un fichier illisible ou un profil écrit par une version ultérieure ne doit jamais empêcher
l'application de démarrer : dans le doute, on ignore l'entrée fautive.
"""

import json
from dataclasses import asdict, fields
from pathlib import Path

from app.config.settings import PROJECT_ROOT
from app.models.audio_settings import AudioSettings

CUSTOM_PROFILES_FILE = PROJECT_ROOT / "custom_profiles.json"


def _known_fields() -> set[str]:
    return {field.name for field in fields(AudioSettings)}


def _read(store_path: Path) -> dict:
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_custom_profiles(store_path: Path | None = None) -> dict[str, AudioSettings]:
    """Profils enregistrés, dans leur ordre d'écriture ; les entrées illisibles sont ignorées."""
    known = _known_fields()
    profiles: dict[str, AudioSettings] = {}
    for name, values in _read(store_path or CUSTOM_PROFILES_FILE).items():
        if not isinstance(values, dict):
            continue
        # Un réglage inconnu (profil d'une version plus récente) est laissé de côté plutôt
        # que de faire échouer le chargement de tout le fichier.
        profiles[name] = AudioSettings(**{k: v for k, v in values.items() if k in known})
    return profiles


def save_custom_profile(name: str, settings: AudioSettings, store_path: Path | None = None) -> None:
    """Enregistre (ou remplace) un profil ; une erreur d'écriture est ignorée, comme pour le thème."""
    path = store_path or CUSTOM_PROFILES_FILE
    profiles = _read(path)
    profiles[name] = asdict(settings)
    try:
        path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def delete_custom_profile(name: str, store_path: Path | None = None) -> None:
    path = store_path or CUSTOM_PROFILES_FILE
    profiles = _read(path)
    if profiles.pop(name, None) is None:
        return
    try:
        path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
