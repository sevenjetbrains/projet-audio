"""Création et gestion du cycle de vie d'un Project (dossier de travail temporaire)."""

from pathlib import Path
from uuid import uuid4

from app.config.settings import TEMP_DIR
from app.models.media import MediaInfo
from app.models.project import Project


def create_project_for_video(video_info: MediaInfo) -> Project:
    """Crée un dossier temp/project_<id>/ dédié et un Project associé à cette vidéo."""
    project_id = uuid4().hex[:8]
    temp_dir = TEMP_DIR / f"project_{project_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    return Project(
        name=Path(video_info.path).stem,
        source_video=video_info,
        temp_dir=str(temp_dir),
    )
