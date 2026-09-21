"""Liste des projets récemment ouverts/sauvegardés (persistée en JSON dans la racine du projet)."""

import json
from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class RecentProject:
    """Un projet récent tel que l'écran d'accueil l'affiche : fichier, contenu, date."""

    path: str
    file_name: str
    sequence_count: int
    modified_at: datetime


def describe_recent_project(project_path: str) -> RecentProject:
    """Lit le `.acsproject` pour en compter les séquences ; un fichier illisible en donne zéro."""
    file = Path(project_path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        sequences = data.get("sequences", []) if isinstance(data, dict) else []
        count = len(sequences) if isinstance(sequences, list) else 0
    except (OSError, ValueError):
        count = 0
    try:
        modified_at = datetime.fromtimestamp(file.stat().st_mtime)
    except OSError:
        modified_at = datetime.now()
    return RecentProject(str(file), file.name, count, modified_at)


def describe_recent_projects(store_path: Path | None = None) -> list[RecentProject]:
    """Projets récents décrits un à un, le plus récemment ouvert en tête."""
    return [describe_recent_project(path) for path in load_recent_projects(store_path)]
