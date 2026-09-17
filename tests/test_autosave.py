"""Tests d'autosave / récupération après fermeture inattendue (§33)."""

import shutil
from pathlib import Path

import pytest

from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import (
    AUTOSAVE_FILENAME,
    autosave_project,
    create_project_for_video,
    find_recoverable_autosaves,
)


@pytest.fixture
def project_with_sequence(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.4)

    yield project

    # create_project_for_video écrit dans le vrai TEMP_DIR de l'appli (pas un tmp_path
    # isolé) : on nettoie pour ne pas laisser un autosave "orphelin" déclencher la
    # boîte de dialogue de récupération dans une session ultérieure (manuelle ou test).
    shutil.rmtree(project.temp_dir, ignore_errors=True)


def test_autosave_writes_file_in_project_temp_dir(project_with_sequence):
    out_path = autosave_project(project_with_sequence)

    assert Path(out_path).name == AUTOSAVE_FILENAME
    assert Path(out_path).parent == Path(project_with_sequence.temp_dir)
    assert Path(out_path).exists()


def test_find_recoverable_autosaves_includes_saved_project(project_with_sequence):
    autosave_project(project_with_sequence)

    found = find_recoverable_autosaves()

    assert any(Path(project_with_sequence.temp_dir) / AUTOSAVE_FILENAME == Path(p) for p in found)
