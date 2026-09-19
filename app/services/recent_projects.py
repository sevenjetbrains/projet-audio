"""Liste des projets récemment ouverts/sauvegardés (persistée en JSON dans la racine du projet)."""

import json
from pathlib import Path

from app.config.settings import PROJECT_ROOT

RECENT_PROJECTS_FILE = PROJECT_ROOT / "recent_projects.json"
MAX_RECENT_PROJECTS = 10


def load_recent_projects(store_path: Path | None = None) -> list[str]:
    """Retourne les chemins récents (plus récent d'abord), en ignorant les fichiers disparus."""
    path = store_path or RECENT_PROJECTS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, str) and Path(p).is_file()][:MAX_RECENT_PROJECTS]


def add_recent_project(project_path: str, store_path: Path | None = None) -> None:
    """Place project_path en tête de liste (sans doublon) ; une erreur d'écriture est ignorée."""
    path = store_path or RECENT_PROJECTS_FILE
    normalized = str(Path(project_path).resolve())
    others = [p for p in load_recent_projects(path) if Path(p).resolve() != Path(normalized)]
    updated = [normalized, *others][:MAX_RECENT_PROJECTS]
    try:
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
