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
    assert window._waveform_widget._regions == [(1.0, 3.0, "Première", "a"), (5.0, 7.0, "Deuxième", "b")]

    project.sequences.clear()
    window._on_sequences_changed()
    assert window._waveform_widget._regions == []


# --- clic sur une zone -----------------------------------------------------------------------------


def _click(widget, x: float):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(int(x), 60))


def test_click_on_region_emits_its_sequence_id_and_seek(qtbot, waveform):
    waveform.set_sequence_regions([(1.0, 3.0, "A", "id-a"), (5.0, 7.0, "B", "id-b")])
    ids, seeks = [], []
    waveform.region_clicked.connect(ids.append)
    waveform.seek_requested.connect(seeks.append)

    _click(waveform, 240)  # 6 s

    assert ids == ["id-b"]
    assert seeks == [pytest.approx(6.0, abs=0.05)]


def test_click_outside_regions_only_seeks(qtbot, waveform):
    waveform.set_sequence_regions([(1.0, 3.0, "A", "id-a")])
    ids, seeks = [], []
    waveform.region_clicked.connect(ids.append)
    waveform.seek_requested.connect(seeks.append)

    _click(waveform, 300)  # 7,5 s

    assert ids == []
    assert len(seeks) == 1


def test_click_on_overlapping_regions_picks_the_topmost(waveform):
    waveform.set_sequence_regions([(1.0, 5.0, "Dessous", "low"), (2.0, 4.0, "Dessus", "top")])

    assert waveform.region_at(3.0).sequence_id == "top"
    assert waveform.region_at(4.5).sequence_id == "low"
    assert waveform.region_at(9.0) is None


def test_drag_selection_does_not_pick_a_region(qtbot, waveform):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    waveform.set_sequence_regions([(0.0, 10.0, "Tout", "all")])
    ids = []
    waveform.region_clicked.connect(ids.append)

    QTest.mousePress(waveform, Qt.MouseButton.LeftButton, pos=QPoint(80, 60))
    QTest.mouseMove(waveform, QPoint(200, 60))
    QTest.mouseRelease(waveform, Qt.MouseButton.LeftButton, pos=QPoint(200, 60))

    assert ids == []
    assert waveform._selection is not None


def test_regions_without_id_are_not_clickable(waveform):
    waveform.set_sequence_regions([(0.0, 10.0, "Sans id")])
    ids = []
    waveform.region_clicked.connect(ids.append)

    _click(waveform, 100)

    assert ids == []


def test_clicking_a_region_selects_the_sequence_in_the_list(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    selected = []
    monkeypatch.setattr(window._sequence_list, "select_sequence", selected.append)

    window._waveform_widget.region_clicked.emit("abc")

    assert selected == ["abc"]
