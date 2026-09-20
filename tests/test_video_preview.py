"""Tests de l'aperçu vidéo : widget, sortie du lecteur et lecture de la vidéo source."""

import pytest

from app.config.settings import find_ffmpeg_binaries
from app.models.media import MediaInfo
from app.models.project import Project
from app.ui.main_window import MainWindow
from app.ui.transport_controls import TransportControls
from app.ui.video_preview import VideoPreview


def _media_info(path: str = "C:/x/demo.mp4") -> MediaInfo:
    return MediaInfo(
        path=path, duration=10.0, container_format="mp4", video_codec="h264",
        audio_codec="aac", sample_rate=44100, channels=2, resolution=(1920, 1080),
        bitrate=None, size_bytes=1,
    )


def _project(video_path: str = "C:/x/demo.mp4") -> Project:
    return Project(
        name="demo",
        source_video=_media_info(video_path),
        temp_dir="C:/x/temp",
        original_audio_path="C:/x/temp/source.wav",
    )


def _window(qtbot, monkeypatch, project: Project | None = None) -> MainWindow:
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    if project is not None:
        monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))
    return window


def test_preview_starts_on_placeholder(qtbot):
    preview = VideoPreview()
    qtbot.addWidget(preview)

    assert not preview.is_active

    preview.set_active(True)
    assert preview.is_active


def test_transport_controls_expose_video_output(qtbot):
    controls = TransportControls()
    qtbot.addWidget(controls)
    preview = VideoPreview()
    qtbot.addWidget(preview)

    controls.set_video_output(preview.video_widget)

    assert controls._player.videoOutput() is preview.video_widget


def test_main_window_plugs_preview_into_player(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)

    assert window._transport_controls._player.videoOutput() is window._video_preview.video_widget


def test_source_playback_uses_the_video_file(qtbot, monkeypatch):
    project = _project()
    window = _window(qtbot, monkeypatch, project)
    loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", loaded.append)

    window._on_audio_ready(project.original_audio_path, 10.0)

    assert loaded == ["C:/x/demo.mp4"]
    assert window._video_preview.is_active


def test_playback_error_falls_back_to_extracted_audio(qtbot, monkeypatch):
    project = _project()
    window = _window(qtbot, monkeypatch, project)
    loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", loaded.append)

    window._on_playback_error("codec non supporté")

    assert loaded == ["C:/x/temp/source.wav"]
    assert window._video_playback_failed
    assert not window._video_preview.is_active


def test_playback_error_ignored_while_playing_a_sequence(qtbot, monkeypatch):
    project = _project()
    window = _window(qtbot, monkeypatch, project)
    window._playback_offset = 4.0  # une séquence est en cours de lecture
    loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", loaded.append)

    window._on_playback_error("fichier introuvable")

    assert loaded == []
    assert not window._video_playback_failed


def test_seek_after_sequence_reloads_the_video(qtbot, monkeypatch):
    project = _project()
    window = _window(qtbot, monkeypatch, project)
    window._playback_offset = 4.0
    loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", loaded.append)
    seeked = []
    monkeypatch.setattr(window._transport_controls, "set_position_seconds", seeked.append)

    window._on_waveform_seek_requested(2.5)

    assert loaded == ["C:/x/demo.mp4"]
    assert seeked == [2.5]
    assert window._playback_offset == 0.0


def test_source_playback_falls_back_when_project_has_no_video(qtbot, monkeypatch):
    project = Project(name="demo", temp_dir="C:/x/temp", original_audio_path="C:/x/temp/source.wav")
    window = _window(qtbot, monkeypatch, project)

    assert window._source_playback_path() == "C:/x/temp/source.wav"


@pytest.mark.parametrize("failed,expected", [(False, "C:/x/demo.mp4"), (True, "C:/x/temp/source.wav")])
def test_source_playback_path_depends_on_video_failure(qtbot, monkeypatch, failed, expected):
    window = _window(qtbot, monkeypatch, _project())
    window._video_playback_failed = failed

    assert window._source_playback_path() == expected
