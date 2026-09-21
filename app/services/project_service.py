"""Création et gestion du cycle de vie d'un Project, sauvegarde/chargement (.acsproject)."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config.settings import TEMP_DIR
from app.models.audio_settings import AudioSettings
from app.models.marker import Marker
from app.models.media import MediaInfo
from app.models.project import Project
from app.services import sequence_service
from app.services.audio_processor import process_sequence
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService, ProbeError

PROJECT_FILE_EXTENSION = ".acsproject"
AUTOSAVE_FILENAME = "autosave.acsproject"


class ProjectLoadError(RuntimeError):
    """Erreur utilisateur claire lors du chargement d'un projet."""


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


def save_project(project: Project, out_path: str) -> None:
    """Sérialise le projet en JSON (.acsproject) : références + paramètres, pas l'audio."""
    if project.source_video is None:
        raise ValueError("project.source_video must be set before saving")

    data = {
        "project_name": project.name,
        "source_video": project.source_video.path,
        "crossfade_duration": project.crossfade_duration,
        "markers": [
            {"id": marker.id, "position": marker.position, "label": marker.label}
            for marker in sorted(project.markers, key=lambda m: m.position)
        ],
        "sequences": [
            {
                "id": seq.id,
                "name": seq.name,
                "start": seq.source_start,
                "end": seq.source_end,
                "order": seq.order,
                "audio_settings": asdict(seq.audio_settings),
            }
            for seq in sorted(project.sequences, key=lambda s: s.order)
        ],
    }
    Path(out_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def autosave_project(project: Project) -> str:
    """Sauvegarde automatique (§33) dans le dossier temp du projet, pour récupération après crash."""
    out_path = str(Path(project.temp_dir) / AUTOSAVE_FILENAME)
    save_project(project, out_path)
    return out_path


@dataclass(frozen=True)
class AutosaveInfo:
    """Une sauvegarde automatique récupérable, telle que l'écran d'accueil la présente."""

    path: str
    project_name: str
    saved_at: datetime


def describe_autosave(path: str) -> AutosaveInfo:
    """Nom du projet et date de la sauvegarde ; un fichier illisible garde le nom du dossier."""
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        name = data.get("project_name") or file.parent.name
    except (OSError, ValueError):
        name = file.parent.name
    try:
        saved_at = datetime.fromtimestamp(file.stat().st_mtime)
    except OSError:
        saved_at = datetime.now()
    return AutosaveInfo(str(file), name, saved_at)


def find_recoverable_autosaves() -> list[str]:
    """Liste les autosaves de sessions précédentes, les plus récentes en premier."""
    if not TEMP_DIR.exists():
        return []
    candidates = list(TEMP_DIR.glob(f"project_*/{AUTOSAVE_FILENAME}"))
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in candidates]


def load_project(path: str, ffprobe_service: FFprobeService, ffmpeg_service: FFmpegService) -> Project:
    """Recharge un projet .acsproject : régénère l'audio depuis la vidéo source (§16 : non
    obligatoire de conserver les fichiers intermédiaires, ils sont recréés)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectLoadError("Impossible de lire ce fichier de projet.") from exc

    video_path = data.get("source_video")
    if not video_path or not Path(video_path).exists():
        raise ProjectLoadError(f"Le fichier vidéo source est introuvable : {video_path}")

    try:
        media_info = ffprobe_service.probe(video_path)
    except ProbeError as exc:
        raise ProjectLoadError(str(exc)) from exc

    project = create_project_for_video(media_info)
    project.name = data.get("project_name", project.name)
    project.crossfade_duration = data.get("crossfade_duration", 0.0)

    # Les projets antérieurs aux repères n'ont pas de clé « markers » : liste vide.
    project.markers = [
        Marker(id=m.get("id") or uuid4().hex[:8], position=m["position"], label=m.get("label", ""))
        for m in sorted(data.get("markers", []), key=lambda m: m["position"])
    ]

    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(video_path, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    for seq_data in sorted(data.get("sequences", []), key=lambda s: s["order"]):
        sequence = sequence_service.add_sequence(
            project, ffmpeg_service, seq_data["start"], seq_data["end"], name=seq_data["name"]
        )
        settings_data = seq_data.get("audio_settings", {})
        sequence.audio_settings = AudioSettings(**settings_data)
        process_sequence(project, sequence, ffmpeg_service)

    return project
