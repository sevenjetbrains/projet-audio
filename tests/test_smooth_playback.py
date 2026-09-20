"""Tests de la fluidité de l'aperçu : déplacements regroupés, aperçu allégé (proxy) et bascule sans perte."""

import subprocess
from pathlib import Path

import pytest
from PySide6.QtMultimedia import QMediaPlayer

from app.config.settings import find_ffmpeg_binaries
from app.models.media import MediaInfo
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.preview_proxy import (
    PROXY_HEIGHT,
    build_preview_proxy,
    needs_preview_proxy,
    preview_proxy_path,
)
from app.services.project_service import create_project_for_video
from app.ui.main_window import MainWindow
from app.ui.transport_controls import TransportControls


def _media(resolution) -> MediaInfo:
    return MediaInfo(
        path="v.mp4", duration=10.0, container_format="mp4", video_codec="h264", audio_codec="aac",
        sample_rate=44100, channels=2, resolution=resolution, bitrate=None, size_bytes=1,
    )


# --- décision : quand faut-il un aperçu allégé ? -----------------------------------------------------


@pytest.mark.parametrize(
    ("resolution", "expected"),
    [((1920, 1080), True), ((1280, 720), True), ((854, 480), False), ((640, 360), False), (None, False)],
)
def test_needs_preview_proxy_only_for_heavy_videos(resolution, expected):
    assert needs_preview_proxy(_media(resolution)) is expected


def test_needs_preview_proxy_without_media_info():
    assert needs_preview_proxy(None) is False


# --- création de l'aperçu allégé -----------------------------------------------------------------------


@pytest.fixture
def hd_project(tmp_path_factory, ffmpeg_binaries):
    """Vidéo 1280×720 de 4 s avec très peu d'images clés (comme une vidéo de caméra ou de téléphone)."""
    folder = tmp_path_factory.mktemp("hd")
    video = folder / "hd.mp4"
    subprocess.run(
        [
            ffmpeg_binaries.ffmpeg_path, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=4",
            "-f", "lavfi", "-i", "sine=f=440:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "250", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
        ],
        check=True,
    )
    info = FFprobeService(ffmpeg_binaries.ffprobe_path).probe(str(video))
    return create_project_for_video(info), FFmpegService(ffmpeg_binaries.ffmpeg_path), video


def _keyframe_times(ffprobe: str, path: str) -> list[float]:
    out = subprocess.run(
        [ffprobe, "-loglevel", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return [float(line.strip(",")) for line in out.split() if line.strip(",")]


def test_proxy_is_reduced_and_has_frequent_keyframes(hd_project, ffmpeg_binaries):
    project, service, video = hd_project
    assert len(_keyframe_times(ffmpeg_binaries.ffprobe_path, str(video))) <= 2  # source : une image clé toutes les 10 s

    proxy = build_preview_proxy(project, service)

    info = FFprobeService(ffmpeg_binaries.ffprobe_path).probe(proxy)
    assert info.resolution[1] == PROXY_HEIGHT
    assert info.duration == pytest.approx(4.0, abs=0.3)
    keys = _keyframe_times(ffmpeg_binaries.ffprobe_path, proxy)
    # 25 images/s, une clé toutes les 6 images : jamais plus de 0,25 s à redécoder pour afficher une image.
    assert max(b - a for a, b in zip(keys, keys[1:])) <= 0.3


def test_proxy_keeps_the_audio(hd_project, ffmpeg_binaries):
    project, service, _video = hd_project

    proxy = build_preview_proxy(project, service)

    assert FFprobeService(ffmpeg_binaries.ffprobe_path).probe(proxy).audio_codec == "aac"


def test_proxy_reports_progress_and_is_reused(hd_project):
    project, service, _video = hd_project
    values: list[float] = []

    first = build_preview_proxy(project, service, values.append)
    assert values and values == sorted(values) and values[-1] == pytest.approx(1.0)
    modified = Path(first).stat().st_mtime_ns

    second = build_preview_proxy(project, service)  # déjà prêt : pas de nouvel encodage

    assert second == first
    assert Path(second).stat().st_mtime_ns == modified


def test_proxy_leaves_no_partial_file_and_never_touches_the_source(hd_project):
    project, service, video = hd_project
    original = video.read_bytes()

    proxy = build_preview_proxy(project, service)

    assert not Path(proxy + ".part.mp4").exists()
    assert preview_proxy_path(project) == Path(proxy)
    assert video.read_bytes() == original


def test_failed_encoding_leaves_no_proxy_behind(hd_project, tmp_path):
    project, service, _video = hd_project
    project.source_video.path = str(tmp_path / "absente.mp4")

    with pytest.raises(Exception):
        build_preview_proxy(project, service)

    assert not preview_proxy_path(project).exists()
    assert not Path(str(preview_proxy_path(project)) + ".part.mp4").exists()


def test_proxy_requires_a_source_video(ffmpeg_binaries):
    project = create_project_for_video(_media((1920, 1080)))
    project.source_video = None

    with pytest.raises(ValueError):
        build_preview_proxy(project, FFmpegService(ffmpeg_binaries.ffmpeg_path))


# --- déplacements regroupés -----------------------------------------------------------------------------


@pytest.fixture
def transport(qtbot):
    try:
        widget = TransportControls()
    except Exception as exc:  # backend audio indisponible dans cet environnement
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def recorded_seeks(transport, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(transport._player, "setPosition", calls.append)
    return calls


def test_first_throttled_seek_is_immediate(transport, recorded_seeks):
    transport.seek_throttled(3.0)

    assert recorded_seeks == [3000]


def test_rapid_throttled_seeks_are_merged_and_the_last_one_wins(qtbot, transport, recorded_seeks):
    for seconds in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
        transport.seek_throttled(seconds)

    assert recorded_seeks == [1000]  # un seul déplacement immédiat, les autres attendent
    qtbot.waitUntil(lambda: len(recorded_seeks) == 2, timeout=1000)
    assert recorded_seeks == [1000, 7000]  # et seul le dernier emplacement demandé est appliqué


def test_throttled_seek_is_accepted_again_after_the_pause(qtbot, transport, recorded_seeks):
    transport.seek_throttled(1.0)
    qtbot.wait(120)

    transport.seek_throttled(2.0)

    assert recorded_seeks == [1000, 2000]


def test_exact_seek_cancels_pending_throttled_one(qtbot, transport, recorded_seeks):
    transport.seek_throttled(1.0)
    transport.seek_throttled(2.0)  # en attente

    transport.set_position_seconds(9.0)
    qtbot.wait(150)

    assert recorded_seeks == [1000, 9000]  # le 2 s en attente ne doit pas écraser la position exacte


def test_slider_drag_seeks_live_then_lands_exactly(qtbot, monkeypatch):
    from app.ui.video_player_panel import VideoPlayerPanel
    from app.ui.video_preview import VideoPreview

    try:
        transport = TransportControls()
    except Exception as exc:
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(transport)
    panel = VideoPlayerPanel(transport, VideoPreview())
    qtbot.addWidget(panel)
    panel.set_duration(60.0)
    throttled, exact = [], []
    monkeypatch.setattr(transport, "seek_throttled", throttled.append)
    monkeypatch.setattr(transport, "set_position_seconds", exact.append)

    panel._on_scrub_started()
    panel._position_slider.setValue(10_000)
    panel._position_slider.setValue(25_000)
    assert throttled == [10.0, 25.0]  # l'image suit pendant le glissement
    assert exact == []

    panel._on_scrub_finished()
    assert exact == [25.0]  # position exacte au relâchement


def test_click_on_slider_groove_seeks_exactly(qtbot, monkeypatch):
    from app.ui.video_player_panel import VideoPlayerPanel
    from app.ui.video_preview import VideoPreview

    try:
        transport = TransportControls()
    except Exception as exc:
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(transport)
    panel = VideoPlayerPanel(transport, VideoPreview())
    qtbot.addWidget(panel)
    panel.set_duration(60.0)
    exact = []
    monkeypatch.setattr(transport, "set_position_seconds", exact.append)

    panel._position_slider.setValue(40_000)  # pas de glissement : simple saut

    assert exact == [40.0]


# --- bascule vers l'aperçu allégé ------------------------------------------------------------------------


@pytest.fixture
def other_wav_file(synthetic_wav_file, tmp_path):
    """Second fichier distinct (comme la copie allégée) : recharger l'URL déjà chargée ne ferait rien."""
    copy = tmp_path / "copie.wav"
    copy.write_bytes(Path(synthetic_wav_file).read_bytes())
    return str(copy)


def test_replace_source_keeps_position_and_pause_state(qtbot, transport, synthetic_wav_file, other_wav_file):
    transport.set_source(synthetic_wav_file)
    qtbot.waitUntil(
        lambda: transport._player.mediaStatus()
        in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia),
        timeout=5000,
    )
    transport.set_position_seconds(1.0)
    qtbot.waitUntil(lambda: transport._player.position() >= 900, timeout=3000)

    transport.replace_source_keep_position(other_wav_file)

    qtbot.waitUntil(lambda: 900 <= transport._player.position() <= 1500, timeout=5000)
    assert not transport.is_playing  # était en pause : le reste


def test_replace_source_resumes_playback_when_it_was_playing(qtbot, transport, synthetic_wav_file, other_wav_file):
    transport.load_and_play(synthetic_wav_file)
    qtbot.waitUntil(lambda: transport.is_playing, timeout=5000)

    transport.replace_source_keep_position(other_wav_file)

    qtbot.waitUntil(lambda: transport.is_playing, timeout=5000)


# --- intégration dans la fenêtre --------------------------------------------------------------------------


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    return win


def _with_project(window, monkeypatch, resolution):
    from app.models.project import Project

    project = Project(name="demo", source_video=_media(resolution), temp_dir="C:/tmp/x", original_audio_path="C:/tmp/x/a.wav")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))
    return project


def test_light_video_never_builds_a_proxy(window, monkeypatch):
    _with_project(window, monkeypatch, (640, 360))
    started = []
    monkeypatch.setattr("app.ui.main_window.FFmpegTaskWorker", lambda *a, **k: started.append(True))

    window._start_preview_proxy()

    assert started == []


def test_heavy_video_starts_proxy_and_shows_progress(window, monkeypatch):
    _with_project(window, monkeypatch, (1920, 1080))
    created = []

    class FakeWorker:
        def __init__(self, task, with_progress=False):
            self.progress = _Signal()
            self.succeeded = _Signal()
            self.failed = _Signal()
            created.append(self)

        def start(self):
            pass

    monkeypatch.setattr("app.ui.main_window.FFmpegTaskWorker", FakeWorker)

    window._start_preview_proxy()
    created[0].progress.emit(42)

    assert "42 %" in window._status_hint_label.text()


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


def test_proxy_ready_switches_source_playback_and_keeps_position(window, monkeypatch):
    project = _with_project(window, monkeypatch, (1920, 1080))
    replaced = []
    monkeypatch.setattr(window._transport_controls, "replace_source_keep_position", replaced.append)
    window._playback_offset = 0.0

    window._on_preview_proxy_ready(project, "C:/tmp/x/preview.mp4")

    assert replaced == ["C:/tmp/x/preview.mp4"]
    assert window._source_playback_path() == "C:/tmp/x/preview.mp4"
    assert window._status_hint_label.text() == "Aperçu fluide prêt"


def test_proxy_ready_does_not_interrupt_a_sequence_being_played(window, monkeypatch):
    project = _with_project(window, monkeypatch, (1920, 1080))
    replaced = []
    monkeypatch.setattr(window._transport_controls, "replace_source_keep_position", replaced.append)
    window._playback_offset = 12.5  # une séquence est en cours de lecture

    window._on_preview_proxy_ready(project, "C:/tmp/x/preview.mp4")

    assert replaced == []
    # La prochaine lecture de la source, elle, utilisera bien la copie légère.
    assert window._source_playback_path() == "C:/tmp/x/preview.mp4"


def test_proxy_ready_for_a_closed_project_is_ignored(window, monkeypatch):
    project = _with_project(window, monkeypatch, (1920, 1080))
    replaced = []
    monkeypatch.setattr(window._transport_controls, "replace_source_keep_position", replaced.append)
    other = _media((1920, 1080))
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: other))

    window._on_preview_proxy_ready(project, "C:/tmp/x/preview.mp4")

    assert replaced == []
    assert window._preview_proxy_path == ""


def test_proxy_failure_keeps_original_video(window, monkeypatch):
    project = _with_project(window, monkeypatch, (1920, 1080))

    window._on_preview_proxy_failed("boom")

    assert window._source_playback_path() == project.source_video.path
    assert "indisponible" in window._status_hint_label.text()
