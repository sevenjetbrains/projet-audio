"""Tests : l'aperçu vidéo garde sa taille après un passage en plein écran (avant : il doublait de hauteur)."""

import subprocess

import pytest
from PySide6.QtCore import QSize
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.models.media import MediaInfo
from app.ui.transport_controls import TransportControls
from app.ui.video_player_panel import VideoPlayerPanel
from app.ui.video_preview import (
    _DEFAULT_ASPECT,
    _MAX_HEIGHT,
    _MIN_HEIGHT,
    _MIN_WIDTH,
    VideoPreview,
    _AspectStackedLayout,
)

_LOADED = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)


# ============================ la règle de dimensionnement ===================================================


def _layout(aspect):
    return _AspectStackedLayout(lambda: aspect)


@pytest.mark.parametrize(
    ("aspect", "width", "expected"),
    [
        (16 / 9, 320, 180),
        (16 / 9, 640, 360),
        (4 / 3, 320, 240),
        (1.0, 320, 320),
        (9 / 16, 320, _MAX_HEIGHT),  # vidéo verticale : plafonnée, sinon le panneau deviendrait démesuré
        (16 / 9, 200, _MIN_HEIGHT),  # jamais en dessous du minimum
    ],
)
def test_height_follows_width_and_video_format(aspect, width, expected):
    assert _layout(aspect).heightForWidth(width) == expected


def test_layout_announces_a_width_dependent_height():
    layout = _layout(16 / 9)

    assert layout.hasHeightForWidth()
    assert layout.sizeHint() == QSize(_MIN_WIDTH, 180)
    assert layout.minimumSize() == QSize(_MIN_WIDTH, _MIN_HEIGHT)


def test_size_hint_follows_the_format_not_the_natural_video_size():
    assert _layout(4 / 3).sizeHint() == QSize(_MIN_WIDTH, 240)


# ============================ VideoPreview ================================================================


@pytest.fixture
def preview(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    widget = VideoPreview(host)
    widget.host = host
    widget.set_active(True)
    return widget


def test_default_format_is_16_9(preview):
    assert preview.aspect_ratio == pytest.approx(_DEFAULT_ASPECT)
    assert preview.sizeHint() == QSize(_MIN_WIDTH, 180)


def test_set_aspect_ratio_changes_the_size_the_preview_asks_for(preview):
    preview.set_aspect_ratio(640, 480)

    assert preview.aspect_ratio == pytest.approx(4 / 3)
    assert preview.sizeHint().height() == 240  # le reste de la fenêtre est prévenu (updateGeometry)


@pytest.mark.parametrize("size", [(0, 0), (640, 0), (0, 360), (-5, 10)])
def test_unknown_or_invalid_format_falls_back_to_16_9(preview, size):
    preview.set_aspect_ratio(640, 480)

    preview.set_aspect_ratio(*size)

    assert preview.aspect_ratio == pytest.approx(_DEFAULT_ASPECT)


def test_video_widget_never_imposes_its_natural_size(preview):
    policy = preview.video_widget.sizePolicy()

    assert policy.horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert policy.verticalPolicy() == QSizePolicy.Policy.Ignored


def test_placeholder_and_video_states_ask_for_the_same_size(preview):
    preview.set_active(True)
    with_video = preview.sizeHint()

    preview.set_active(False)

    assert preview.sizeHint() == with_video  # pas de saut de taille quand la vidéo apparaît ou disparaît


# ============================ aller-retour plein écran ====================================================


def _column(qtbot, preview):
    """Aperçu placé dans une colonne comme dans la fenêtre : autre contenu au-dessus et un ressort en dessous."""
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    layout.addWidget(QLabel("LECTEUR VIDÉO"))
    layout.addWidget(preview, 1)
    layout.addWidget(QLabel("SOURCE"))
    layout.addStretch(1)
    host.resize(340, 800)
    host.show()
    qtbot.waitExposed(host)
    return host


def _geometry(host, preview):
    return (host.size(), preview.size(), preview.video_widget.size())


def test_fullscreen_round_trip_restores_the_exact_layout(qtbot, preview):
    preview.set_aspect_ratio(640, 360)
    host = _column(qtbot, preview)
    qtbot.wait(100)
    before = _geometry(host, preview)

    for _ in range(3):
        preview.toggle_fullscreen()
        assert preview.is_fullscreen
        preview.toggle_fullscreen()
        qtbot.wait(120)
        assert _geometry(host, preview) == before  # avant : l'aperçu doublait de hauteur au premier retour


def test_round_trip_layout_is_identical_at_different_window_widths(qtbot, preview):
    preview.set_aspect_ratio(640, 360)
    host = _column(qtbot, preview)
    for width in (340, 520, 900):
        host.resize(width, 800)
        qtbot.wait(80)
        before = _geometry(host, preview)

        preview.toggle_fullscreen()
        preview.toggle_fullscreen()
        qtbot.wait(120)

        assert _geometry(host, preview) == before, f"largeur {width}"


def test_preview_follows_the_width_it_is_given(qtbot, preview):
    preview.set_aspect_ratio(640, 360)
    host = _column(qtbot, preview)
    host.resize(700, 800)
    qtbot.wait(100)

    assert preview.height() == round(preview.width() / (16 / 9))  # 16:9 respecté à toute largeur


def test_portrait_video_does_not_grow_past_the_cap(qtbot, preview):
    preview.set_aspect_ratio(360, 640)
    host = _column(qtbot, preview)
    host.resize(500, 900)
    qtbot.wait(100)

    assert preview.height() <= _MAX_HEIGHT


# ============================ avec une vraie vidéo (le cas signalé) ===================================


@pytest.fixture(scope="module")
def video_640x360(tmp_path_factory, ffmpeg_binaries):
    """Vidéo dont la taille naturelle (640×360) est celle qui faisait doubler l'aperçu au retour du plein écran."""
    path = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_binaries.ffmpeg_path, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=2",
            "-f", "lavfi", "-i", "sine=f=440:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return str(path)


def test_real_video_keeps_its_size_across_fullscreen(qtbot, video_640x360):
    try:
        transport = TransportControls()
    except Exception as exc:  # backend multimédia indisponible dans cet environnement
        pytest.skip(f"Backend indisponible : {exc}")
    qtbot.addWidget(transport)
    preview = VideoPreview()
    panel = VideoPlayerPanel(transport, preview)
    host = QWidget()
    qtbot.addWidget(host)  # seul conteneur enregistré : le panneau et l'aperçu en sont des enfants, détruits avec lui
    layout = QVBoxLayout(host)
    layout.addWidget(panel)
    layout.addStretch(1)
    panel.set_media_info(
        MediaInfo(
            path=video_640x360, duration=2.0, container_format="mp4", video_codec="h264", audio_codec="aac",
            sample_rate=44100, channels=2, resolution=(640, 360), bitrate=None, size_bytes=1,
        )
    )
    transport.set_video_output(preview.video_widget)
    preview.set_active(True)
    transport.set_source(video_640x360)
    host.resize(340, 800)
    host.show()
    qtbot.waitExposed(host)
    qtbot.waitUntil(lambda: transport._player.mediaStatus() in _LOADED, timeout=8000)
    qtbot.wait(300)
    before = (panel.size(), preview.size(), preview.video_widget.size())

    for _ in range(2):
        panel.toggle_fullscreen()
        qtbot.wait(300)
        assert preview.is_fullscreen
        panel.toggle_fullscreen()
        qtbot.wait(300)
        assert (panel.size(), preview.size(), preview.video_widget.size()) == before


# ============================ panneau du lecteur ==========================================================


@pytest.fixture
def panel(qtbot):
    try:
        transport = TransportControls()
    except Exception as exc:
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(transport)
    preview = VideoPreview()
    widget = VideoPlayerPanel(transport, preview)
    qtbot.addWidget(widget)  # l'aperçu appartient au panneau : le fermer séparément échouerait
    return widget, preview


def _info(resolution):
    return MediaInfo(
        path="v.mp4", duration=1.0, container_format="mp4", video_codec="h264", audio_codec="aac",
        sample_rate=44100, channels=2, resolution=resolution, bitrate=None, size_bytes=1,
    )


def test_media_info_sets_the_preview_format(panel):
    widget, preview = panel

    widget.set_media_info(_info((1280, 960)))

    assert preview.aspect_ratio == pytest.approx(4 / 3)


def test_missing_media_info_resets_the_format(panel):
    widget, preview = panel
    widget.set_media_info(_info((1280, 960)))

    widget.set_media_info(None)
    assert preview.aspect_ratio == pytest.approx(_DEFAULT_ASPECT)

    widget.set_media_info(_info((1280, 960)))
    widget.set_media_info(_info(None))
    assert preview.aspect_ratio == pytest.approx(_DEFAULT_ASPECT)
