"""Tests de sauvegarde/chargement de projet (.acsproject)."""

import json
from pathlib import Path

import pytest

from app.models.audio_settings import AudioSettings
from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import ProjectLoadError, create_project_for_video, load_project, save_project


@pytest.fixture
def project_with_sequences(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    seq1 = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.4, name="Intro")
    seq2 = sequence_service.add_sequence(project, ffmpeg_service, 0.4, 0.9, name="Fin")
    seq1.audio_settings = AudioSettings(gain=2.0, fade_in=0.1)

    return project, ffmpeg_service, ffprobe_service


def test_save_project_writes_json(project_with_sequences, tmp_path):
    project, _ffmpeg_service, _ffprobe_service = project_with_sequences
    out_path = tmp_path / "mon_projet.acsproject"

    save_project(project, str(out_path))

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["project_name"] == project.name
    assert data["source_video"] == project.source_video.path
    assert len(data["sequences"]) == 2
    assert data["sequences"][0]["name"] == "Intro"
    assert data["sequences"][0]["audio_settings"]["gain"] == 2.0


def test_load_project_regenerates_audio(project_with_sequences, tmp_path):
    project, ffmpeg_service, ffprobe_service = project_with_sequences
    out_path = tmp_path / "mon_projet.acsproject"
    save_project(project, str(out_path))

    loaded = load_project(str(out_path), ffprobe_service, ffmpeg_service)

    assert len(loaded.sequences) == 2
    assert [s.name for s in loaded.sequences] == ["Intro", "Fin"]
    assert Path(loaded.original_audio_path).exists()
    for seq in loaded.sequences:
        assert Path(seq.audio_path).exists()

    intro = next(s for s in loaded.sequences if s.name == "Intro")
    assert intro.audio_settings.gain == 2.0
    assert intro.audio_settings.fade_in == 0.1
    assert intro.processed_audio_path
    assert Path(intro.processed_audio_path).exists()


def test_load_project_missing_video_raises(tmp_path, ffmpeg_binaries):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    project_file = tmp_path / "broken.acsproject"
    project_file.write_text(
        json.dumps({"project_name": "x", "source_video": "does_not_exist.mp4", "sequences": []}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectLoadError, match="introuvable"):
        load_project(str(project_file), ffprobe_service, ffmpeg_service)


def test_load_project_corrupted_file_raises(tmp_path, ffmpeg_binaries):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    project_file = tmp_path / "corrupted.acsproject"
    project_file.write_text("not valid json{{{", encoding="utf-8")

    with pytest.raises(ProjectLoadError):
        load_project(str(project_file), ffprobe_service, ffmpeg_service)
