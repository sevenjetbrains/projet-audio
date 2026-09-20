"""Copie allégée de la vidéo source pour un aperçu fluide.

Une vidéo HD classique n'a qu'une image clé toutes les 5 à 10 secondes : pour afficher une image quelconque
(surtout en revenant en arrière), le lecteur doit redécoder depuis la dernière image clé, ce qui prend
100 à 500 ms et empile les déplacements. La copie d'aperçu est réduite et porte une image clé toutes les
quelques images : n'importe quelle position s'affiche en quelques millisecondes. Elle ne sert qu'à
l'affichage et à l'écoute ; le fichier source, lui, n'est jamais touché ni utilisé pour l'export.
"""

from pathlib import Path

from app.models.media import MediaInfo
from app.models.project import Project
from app.services.ffmpeg_service import FFmpegService
from app.utils.progress import ProgressCallback

PROXY_HEIGHT = 360
# En dessous de cette hauteur, la vidéo d'origine est déjà assez légère pour se déplacer sans effort.
PROXY_MIN_SOURCE_HEIGHT = 480
PROXY_FILENAME = "preview.mp4"


def needs_preview_proxy(media_info: MediaInfo | None) -> bool:
    """Vrai pour une vidéo assez grande pour que les déplacements dans l'aperçu deviennent saccadés."""
    if media_info is None or not media_info.resolution:
        return False
    return media_info.resolution[1] > PROXY_MIN_SOURCE_HEIGHT


def preview_proxy_path(project: Project) -> Path:
    return Path(project.temp_dir) / PROXY_FILENAME


def build_preview_proxy(
    project: Project, ffmpeg_service: FFmpegService, on_progress: ProgressCallback | None = None
) -> str:
    """Crée (ou réutilise) la copie d'aperçu du projet et retourne son chemin."""
    if project.source_video is None:
        raise ValueError("Aucune vidéo source à préparer.")
    target = preview_proxy_path(project)
    if target.is_file() and target.stat().st_size > 0:
        if on_progress:
            on_progress(1.0)
        return str(target)
    ffmpeg_service.create_preview_proxy(
        project.source_video.path, str(target), project.source_video.duration, PROXY_HEIGHT, on_progress
    )
    return str(target)
