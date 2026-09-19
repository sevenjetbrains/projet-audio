"""Tests de l'affichage des séquences existantes sur la forme d'onde."""

import numpy as np
import pytest
from PySide6.QtGui import QColor

from app.config.settings import find_ffmpeg_binaries
from app.models.project import Project
from app.models.sequence import Sequence
from app.ui.main_window import MainWindow
from app.ui.waveform_widget import WaveformWidget


@pytest.fixture
def waveform(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 140)
    widget._duration = 10.0
    widget._view_start, widget._view_end = 0.0, 10.0
    widget._peaks = np.zeros((400, 2))  # forme d'onde plate : seuls fond, zones et tête de lecture se voient
    return widget


def _pixel(widget, x: int, y: int) -> QColor:
    """Couleur au point (x, y) en pixels logiques du widget, quel que soit le ratio d'échelle de l'écran."""
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio))


def test_regions_are_painted_only_where_sequences_are(waveform):
    empty_inside = _pixel(waveform, 100, 100)
    waveform.set_sequence_regions([(2.0, 4.0, "Intro")])  # x = 80..160 sur 400 px

    assert _pixel(waveform, 120, 100) != empty_inside   # dans la zone
    assert _pixel(waveform, 30, 100) == empty_inside    # avant la zone
    assert _pixel(waveform, 250, 100) == empty_inside   # après la zone


def test_adjacent_regions_get_different_colors(waveform):
    waveform.set_sequence_regions([(0.0, 2.0, "A"), (2.0, 4.0, "B")])

    assert _pixel(waveform, 40, 100) != _pixel(waveform, 120, 100)


def test_regions_follow_zoom_and_skip_offscreen_ones(waveform):
    waveform._view_start, waveform._view_end = 5.0, 10.0  # 80 px par seconde
    background = _pixel(waveform, 10, 100)
    waveform.set_sequence_regions([(0.0, 2.0, "Hors champ"), (6.0, 7.0, "Visible")])

    assert _pixel(waveform, 40, 100) == background       # x = 40 ↔ 5,5 s : entre les deux zones
    assert _pixel(waveform, 120, 100) != background      # x = 120 ↔ 6,5 s : dans « Visible »


def test_regions_survive_theme_change_and_partial_overlap(waveform):
    from app.config.themes import get_theme

    waveform.set_sequence_regions([(9.0, 15.0, "Déborde")])  # dépasse la fin de l'audio
    waveform.set_theme(get_theme("Clair"))

    waveform.grab()  # ne doit pas planter
    assert _pixel(waveform, 380, 100) != QColor("#ffffff")


def test_clearing_regions_restores_plain_background(waveform):
    plain = _pixel(waveform, 120, 100)
    waveform.set_sequence_regions([(2.0, 4.0, "X")])
    waveform.set_sequence_regions([])

    assert _pixel(waveform, 120, 100) == plain


def test_main_window_pushes_sequences_to_waveform(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    project = Project(name="demo")
    project.sequences = [
        Sequence(id="b", name="Deuxième", source_start=5.0, source_end=7.0, order=1),
        Sequence(id="a", name="Première", source_start=1.0, source_end=3.0, order=0),
    ]
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))

    window._on_sequences_changed()

    # Triées par ordre d'affichage, avec les bornes dans l'audio source.
    assert window._waveform_widget._regions == [(1.0, 3.0, "Première"), (5.0, 7.0, "Deuxième")]

    project.sequences.clear()
    window._on_sequences_changed()
    assert window._waveform_widget._regions == []
