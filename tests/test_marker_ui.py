"""Tests de l'interface des repères : rendu sur la waveform, raccourcis, undo et navigation."""

import numpy as np
import pytest
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from app.config.settings import find_ffmpeg_binaries
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import marker_service
from app.ui.main_window import MainWindow
from app.ui.waveform_widget import WaveformWidget


@pytest.fixture
def waveform(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 140)
    widget._duration = 10.0
    widget._view_start, widget._view_end = 0.0, 10.0
    widget._peaks = np.zeros((400, 2))  # forme d'onde plate : seuls le fond et les repères se voient
    return widget


def _pixel(widget, x: int, y: int) -> QColor:
    """Couleur au point (x, y) en pixels logiques du widget, quel que soit le ratio d'échelle de l'écran."""
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio))


# --- Rendu sur la forme d'onde ---------------------------------------------


def test_marker_is_painted_as_a_vertical_line_at_its_position(waveform):
    background = _pixel(waveform, 200, 40)

    waveform.set_markers([(5.0, "Chapitre")])  # x = 200 sur 400 px

    assert _pixel(waveform, 200, 40) != background
    assert _pixel(waveform, 260, 40) == background


def test_clearing_markers_restores_plain_background(waveform):
    plain = _pixel(waveform, 200, 40)
    waveform.set_markers([(5.0, "Chapitre")])
    waveform.set_markers([])

    assert _pixel(waveform, 200, 40) == plain


def test_markers_follow_zoom_and_offscreen_ones_are_skipped(waveform):
    waveform._view_start, waveform._view_end = 5.0, 10.0  # 80 px par seconde
    background = _pixel(waveform, 40, 40)

    waveform.set_markers([(1.0, "Hors champ"), (6.0, "Visible")])

    assert _pixel(waveform, 40, 40) == background   # x = 40 ↔ 5,5 s : aucun repère
    assert _pixel(waveform, 80, 40) != background   # x = 80 ↔ 6,0 s : le repère « Visible »


def test_marker_flag_stays_inside_the_widget_near_the_right_edge(waveform):
    """Le fanion d'un repère en toute fin d'audio est rabattu vers l'intérieur, pas tronqué."""
    waveform.set_markers([(9.98, "Fin de la conférence")])

    height = waveform._wave_height
    assert _pixel(waveform, 340, height - 10) != _pixel(waveform, 40, height - 10)


def test_marker_at_picks_the_closest_one_within_reach(waveform):
    waveform.set_markers([(2.5, "A", "id-a"), (7.5, "B", "id-b")])  # x = 100 et 300

    assert waveform.marker_at(102).marker_id == "id-a"
    assert waveform.marker_at(299).marker_id == "id-b"
    assert waveform.marker_at(200) is None


def test_markers_render_in_both_themes(waveform):
    from app.config.themes import get_theme

    waveform.set_markers([(5.0, "Chapitre")])
    waveform.set_theme(get_theme("Clair"))

    assert _pixel(waveform, 200, 40) != QColor("#ffffff")


# --- Fenêtre principale ------------------------------------------------------


@pytest.fixture
def window_with_project(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    project = Project(name="demo")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))

    window._source_duration = 10.0
    window._waveform_widget._duration = 10.0
    window._waveform_widget._view_start, window._waveform_widget._view_end = 0.0, 10.0
    window._waveform_widget.resize(400, 140)
    window._selection_card.set_range(10.0)
    return window, project


def _place_playhead(window, seconds: float) -> None:
    window._waveform_widget.set_playhead(seconds)


def test_adding_a_marker_at_the_playhead_shows_it_on_the_waveform(window_with_project):
    window, project = window_with_project
    _place_playhead(window, 4.0)

    window._add_marker_at_playhead()

    assert [(m.position, m.label) for m in project.markers] == [(4.0, "Repère 1")]
    assert window._waveform_widget._markers == [(4.0, "Repère 1", project.markers[0].id)]


def test_adding_a_marker_marks_the_project_dirty_and_is_undoable(window_with_project):
    window, project = window_with_project
    window._set_dirty(False)
    _place_playhead(window, 4.0)

    window._add_marker_at_playhead()
    assert window._dirty

    window._sequence_list.undo_stack.undo()

    assert project.markers == []
    assert window._waveform_widget._markers == []

    window._sequence_list.undo_stack.redo()
    assert len(project.markers) == 1


def test_a_second_marker_at_the_same_spot_is_refused(window_with_project):
    window, project = window_with_project
    _place_playhead(window, 4.0)
    window._add_marker_at_playhead()

    _place_playhead(window, 4.05)
    window._add_marker_at_playhead()

    assert len(project.markers) == 1


def test_removing_the_marker_under_the_playhead_and_undoing_it(window_with_project):
    window, project = window_with_project
    _place_playhead(window, 4.0)
    window._add_marker_at_playhead()

    window._remove_marker_at_playhead()
    assert project.markers == []

    window._sequence_list.undo_stack.undo()

    assert [m.position for m in project.markers] == [4.0]
    assert window._waveform_widget._markers[0][0] == 4.0


def test_removing_does_nothing_when_no_marker_is_under_the_playhead(window_with_project):
    window, project = window_with_project
    _place_playhead(window, 4.0)
    window._add_marker_at_playhead()

    _place_playhead(window, 9.0)
    window._remove_marker_at_playhead()

    assert len(project.markers) == 1


def test_navigation_moves_the_playhead_from_marker_to_marker(window_with_project):
    window, project = window_with_project
    for position in (2.0, 6.0):
        _place_playhead(window, position)
        window._add_marker_at_playhead()

    _place_playhead(window, 0.0)
    window._go_to_next_marker()
    assert window._waveform_widget.playhead == pytest.approx(2.0)

    window._go_to_next_marker()
    assert window._waveform_widget.playhead == pytest.approx(6.0)

    window._go_to_next_marker()  # plus rien après : la tête ne bouge pas
    assert window._waveform_widget.playhead == pytest.approx(6.0)

    window._go_to_previous_marker()
    assert window._waveform_widget.playhead == pytest.approx(2.0)


def test_navigation_without_markers_leaves_the_playhead_alone(window_with_project):
    window, _project = window_with_project
    _place_playhead(window, 3.0)

    window._go_to_next_marker()

    assert window._waveform_widget.playhead == pytest.approx(3.0)


def test_select_between_markers_fills_the_selection_bounds(window_with_project):
    window, project = window_with_project
    for position in (2.0, 6.0):
        _place_playhead(window, position)
        window._add_marker_at_playhead()

    _place_playhead(window, 4.0)
    window._select_between_markers()

    assert window._selection_start_spin.value() == pytest.approx(2.0)
    assert window._selection_end_spin.value() == pytest.approx(6.0)
    assert window._waveform_widget._selection == (pytest.approx(2.0), pytest.approx(6.0))


def test_select_between_markers_uses_the_file_edges(window_with_project):
    window, _project = window_with_project
    _place_playhead(window, 6.0)
    window._add_marker_at_playhead()

    _place_playhead(window, 1.0)
    window._select_between_markers()

    assert window._selection_start_spin.value() == pytest.approx(0.0)
    assert window._selection_end_spin.value() == pytest.approx(6.0)


def test_status_summary_mentions_the_markers(window_with_project):
    window, project = window_with_project
    project.sequences = [Sequence(id="a", name="Intro", source_start=0.0, source_end=1.0, order=0)]

    window._update_project_summary()
    assert "repère" not in window._project_summary_label.text()

    marker_service.insert_marker(project, marker_service.create_marker(project, 3.0))
    window._update_project_summary()

    assert "1 repère" in window._project_summary_label.text()


def test_marker_shortcuts_are_registered(window_with_project):
    window, _project = window_with_project
    keys = {s.key().toString() for s in window.findChildren(QShortcut)}

    for expected in ("M", "Shift+M", "Alt+Up", "Alt+Down", "Alt+S"):
        assert QKeySequence(expected).toString() in keys


def test_marker_actions_are_harmless_without_a_project(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    window._add_marker_at_playhead()
    window._remove_marker_at_playhead()
    window._go_to_next_marker()
    window._select_between_markers()

    assert window._waveform_widget._markers == []
