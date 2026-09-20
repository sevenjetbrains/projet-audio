"""Tests de l'édition d'une séquence existante : nouvelles bornes et division (service, liste, fenêtre)."""

import wave
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QMessageBox

from app.config.settings import find_ffmpeg_binaries
from app.models.media import MediaInfo
from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.project_service import create_project_for_video
from app.ui.main_window import MainWindow
from app.ui.selection_card import SelectionCard
from app.ui.sequence_list import SequenceListWidget

_RATE = 8000
_DURATION = 10.0


def _wav_seconds(path: str) -> float:
    with wave.open(path, "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


@pytest.fixture
def project(ffmpeg_binaries):
    """Projet dont la source (10 s de tonalité) est déjà extraite, avec 2 séquences : [1, 4] et [6, 9]."""
    t = np.arange(int(_RATE * _DURATION)) / _RATE
    samples = (0.2 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16)
    info = MediaInfo(
        path="demo.mp4", duration=_DURATION, container_format="mp4", video_codec="h264", audio_codec="aac",
        sample_rate=_RATE, channels=1, resolution=(640, 360), bitrate=None, size_bytes=1,
    )
    proj = create_project_for_video(info)
    wav_path = Path(proj.temp_dir) / "source.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_RATE)
        wav_file.writeframes(samples.tobytes())
    proj.original_audio_path = str(wav_path)
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    sequence_service.add_sequence(proj, service, 1.0, 4.0, name="Intro")
    sequence_service.add_sequence(proj, service, 6.0, 9.0, name="Fin")
    return proj, service


# ============================ service : nouvelles bornes ================================================


def test_retime_returns_old_and_new_without_touching_the_project(project):
    proj, service = project
    old_id = proj.sequences[0].id

    old, new = sequence_service.retime_sequence(proj, service, old_id, 0.5, 4.5)

    assert proj.sequences[0] is old  # rien n'est échangé : c'est à l'appelant (annulation) de le faire
    assert (new.source_start, new.source_end) == (0.5, 4.5)
    assert _wav_seconds(new.audio_path) == pytest.approx(4.0, abs=0.05)
    assert new.audio_path != old.audio_path and Path(old.audio_path).exists()  # l'ancien fichier subsiste (annuler)


def test_retime_keeps_identity_name_position_and_settings(project):
    proj, service = project
    proj.sequences[1].audio_settings.gain = 4.0
    old, new = sequence_service.retime_sequence(proj, service, proj.sequences[1].id, 5.5, 9.5)

    assert new.id == old.id and new.name == "Fin" and new.order == old.order == 1
    assert new.audio_settings.gain == 4.0
    assert new.audio_settings is not old.audio_settings  # copie indépendante


def test_retime_reapplies_the_existing_processing(project):
    proj, service = project
    seq = proj.sequences[0]
    seq.audio_settings.gain = 6.0
    from app.services import audio_processor

    audio_processor.process_sequence(proj, seq, service)
    assert seq.processed_audio_path

    _old, new = sequence_service.retime_sequence(proj, service, seq.id, 1.0, 3.0)

    # Sans cela le traitement disparaîtrait en silence à la fusion (l'audio brut serait utilisé à la place).
    assert new.processed_audio_path and Path(new.processed_audio_path).exists()
    assert new.processed_audio_path != seq.processed_audio_path
    assert _wav_seconds(new.processed_audio_path) == pytest.approx(2.0, abs=0.05)


def test_retime_without_processing_leaves_no_processed_file(project):
    proj, service = project

    _old, new = sequence_service.retime_sequence(proj, service, proj.sequences[0].id, 1.5, 3.5)

    assert new.processed_audio_path == ""


@pytest.mark.parametrize(
    ("start", "end", "fragment"),
    [
        (3.0, 3.0, "au moins"),
        (3.0, 3.01, "au moins"),
        (-1.0, 3.0, "négatif"),
        (2.0, 12.0, "dépasse"),
        (1.0, 4.0, "n'ont pas changé"),
    ],
)
def test_retime_rejects_invalid_bounds(project, start, end, fragment):
    proj, service = project

    with pytest.raises(ValueError, match=fragment):
        sequence_service.retime_sequence(proj, service, proj.sequences[0].id, start, end)


def test_retime_unknown_sequence(project):
    proj, service = project

    with pytest.raises(KeyError):
        sequence_service.retime_sequence(proj, service, "inconnue", 1.0, 2.0)


# ============================ service : division ========================================================


def test_split_produces_two_contiguous_parts_named_after_the_original(project):
    proj, service = project

    old, parts = sequence_service.split_sequence(proj, service, proj.sequences[0].id, 2.5)

    assert old.name == "Intro"
    assert [p.name for p in parts] == ["Intro (1)", "Intro (2)"]
    assert [(p.source_start, p.source_end) for p in parts] == [(1.0, 2.5), (2.5, 4.0)]
    assert [_wav_seconds(p.audio_path) for p in parts] == [pytest.approx(1.5, abs=0.05), pytest.approx(1.5, abs=0.05)]
    assert parts[0].id != parts[1].id and old.id not in {p.id for p in parts}


def test_split_parts_inherit_and_reapply_the_processing(project):
    proj, service = project
    seq = proj.sequences[0]
    seq.audio_settings.gain = 3.0

    _old, parts = sequence_service.split_sequence(proj, service, seq.id, 2.0)

    assert all(p.audio_settings.gain == 3.0 for p in parts)
    assert all(p.processed_audio_path and Path(p.processed_audio_path).exists() for p in parts)


@pytest.mark.parametrize("at", [0.5, 1.0, 1.02, 3.98, 4.0, 8.0])
def test_split_outside_or_too_close_to_the_edges_is_rejected(project, at):
    proj, service = project

    with pytest.raises(ValueError, match="à l'intérieur"):
        sequence_service.split_sequence(proj, service, proj.sequences[0].id, at)


def test_replace_sequences_keeps_position_and_reindexes(project):
    proj, service = project
    first = proj.sequences[0]
    _old, parts = sequence_service.split_sequence(proj, service, first.id, 2.5)

    sequence_service.replace_sequences(proj, [first.id], parts)

    assert [s.name for s in proj.sequences] == ["Intro (1)", "Intro (2)", "Fin"]
    assert [s.order for s in proj.sequences] == [0, 1, 2]

    sequence_service.replace_sequences(proj, [p.id for p in parts], [first])

    assert [s.name for s in proj.sequences] == ["Intro", "Fin"]
    assert [s.order for s in proj.sequences] == [0, 1]


def test_replace_sequences_in_the_middle_of_the_list(project):
    proj, service = project
    last = proj.sequences[1]
    _old, parts = sequence_service.split_sequence(proj, service, last.id, 7.5)

    sequence_service.replace_sequences(proj, [last.id], parts)

    assert [s.name for s in proj.sequences] == ["Intro", "Fin (1)", "Fin (2)"]


# ============================ liste des séquences : annulation ===========================================


@pytest.fixture
def widget(qtbot, project):
    proj, service = project
    list_widget = SequenceListWidget(service)
    qtbot.addWidget(list_widget)
    list_widget.set_project(proj)
    return list_widget, proj


def test_retime_is_undoable_and_redoable(widget):
    lst, proj = widget
    original = proj.sequences[0]

    assert lst.retime_sequence(original.id, 0.5, 5.0)
    assert (proj.sequences[0].source_start, proj.sequences[0].source_end) == (0.5, 5.0)
    assert len(proj.sequences) == 2 and proj.sequences[0].id == original.id

    lst.undo_stack.undo()
    assert proj.sequences[0] is original
    assert (original.source_start, original.source_end) == (1.0, 4.0)

    lst.undo_stack.redo()
    assert (proj.sequences[0].source_start, proj.sequences[0].source_end) == (0.5, 5.0)


def test_retime_undo_restores_the_previous_processing(widget):
    lst, proj = widget
    seq = proj.sequences[0]
    seq.audio_settings.gain = 5.0
    from app.services import audio_processor

    audio_processor.process_sequence(proj, seq, lst._ffmpeg_service)
    processed_before = seq.processed_audio_path

    lst.retime_sequence(seq.id, 1.0, 3.0)
    assert proj.sequences[0].processed_audio_path != processed_before

    lst.undo_stack.undo()
    assert proj.sequences[0].processed_audio_path == processed_before and Path(processed_before).exists()


def test_retime_emits_sequences_changed_and_refreshes_the_list(qtbot, widget):
    lst, proj = widget
    seq = proj.sequences[0]

    with qtbot.waitSignal(lst.sequences_changed, timeout=1000):
        lst.retime_sequence(seq.id, 2.0, 3.0)

    assert lst._list_widget.count() == 2  # la ligne est redessinée, pas dupliquée


def test_failed_retime_shows_a_warning_and_changes_nothing(widget, monkeypatch):
    lst, proj = widget
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))

    ok = lst.retime_sequence(proj.sequences[0].id, 1.0, 4.0)  # mêmes bornes

    assert not ok and shown and "n'ont pas changé" in shown[0]
    assert lst.undo_stack.count() == 0


def test_split_is_a_single_undoable_step(widget):
    lst, proj = widget
    original = proj.sequences[0]

    assert lst.split_sequence_at(original.id, 2.5)
    assert [s.name for s in proj.sequences] == ["Intro (1)", "Intro (2)", "Fin"]
    assert lst.undo_stack.count() == 1

    lst.undo_stack.undo()
    assert proj.sequences[0] is original and len(proj.sequences) == 2

    lst.undo_stack.redo()
    assert len(proj.sequences) == 3 and [s.order for s in proj.sequences] == [0, 1, 2]


def test_failed_split_shows_a_warning(widget, monkeypatch):
    lst, proj = widget
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))

    ok = lst.split_sequence_at(proj.sequences[0].id, 8.0)

    assert not ok and shown and lst.undo_stack.count() == 0


def test_bounds_and_split_buttons_request_the_current_sequence(widget):
    lst, proj = widget
    bounds, splits = [], []
    lst.edit_bounds_requested.connect(bounds.append)
    lst.split_requested.connect(splits.append)
    lst._list_widget.setCurrentRow(1)

    lst._bounds_button.click()
    lst._split_button.click()

    assert bounds == [proj.sequences[1].id] and splits == [proj.sequences[1].id]


def test_bounds_and_split_buttons_do_nothing_without_a_current_sequence(widget):
    lst, _proj = widget
    lst.set_project(lst._project.__class__(name="vide"))
    bounds, splits = [], []
    lst.edit_bounds_requested.connect(bounds.append)
    lst.split_requested.connect(splits.append)

    lst._bounds_button.click()
    lst._split_button.click()

    assert bounds == [] and splits == []


# ============================ carte de sélection : mode édition ==========================================


@pytest.fixture
def card(qtbot):
    widget_ = SelectionCard()
    qtbot.addWidget(widget_)
    return widget_


def test_card_editing_mode_changes_the_action_button_and_shows_cancel(card):
    assert card.create_button.text() == "Créer la séquence" and not card.is_editing

    card.set_editing("Intro")

    assert card.is_editing
    assert card.create_button.text() == "Mettre à jour « Intro »"
    assert not card.cancel_edit_button.isHidden()
    assert "Intro" in card._editing_label.text()


def test_card_leaving_editing_mode_restores_creation(card):
    card.set_editing("Intro")

    card.set_editing(None)

    assert not card.is_editing
    assert card.create_button.text() == "Créer la séquence"
    assert card.cancel_edit_button.isHidden() and card._editing_label.isHidden()


def test_card_cancel_button_emits_signal(qtbot, card):
    card.set_editing("Intro")

    with qtbot.waitSignal(card.edit_cancelled, timeout=1000):
        card.cancel_edit_button.click()


# ============================ fenêtre principale ===========================================================


@pytest.fixture
def window(qtbot, monkeypatch, project):
    proj, service = project
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    monkeypatch.setattr(type(win._video_panel), "project", property(lambda self: proj))
    win._sequence_list._ffmpeg_service = service
    win._sequence_list.set_project(proj)
    win._selection_card.set_range(_DURATION)
    win._waveform_widget._duration = _DURATION
    win._waveform_widget._view_start, win._waveform_widget._view_end = 0.0, _DURATION
    monkeypatch.setattr(win._transport_controls, "set_position_seconds", lambda s: None)
    return win, proj


def test_starting_an_edit_loads_the_bounds_into_the_selection(window):
    win, proj = window

    win._start_bounds_edit(proj.sequences[1].id)

    assert win._editing_sequence_id == proj.sequences[1].id
    assert (win._selection_start_spin.value(), win._selection_end_spin.value()) == (6.0, 9.0)
    assert win._selection_card.is_editing
    assert win._selection_card.create_button.text() == "Mettre à jour « Fin »"


def test_validating_the_edit_retimes_the_sequence_instead_of_creating_one(window):
    win, proj = window
    win._start_bounds_edit(proj.sequences[0].id)
    win._selection_start_spin.setValue(0.5)
    win._selection_end_spin.setValue(4.5)

    win._on_create_sequence_clicked()

    assert len(proj.sequences) == 2  # pas de nouvelle séquence
    assert (proj.sequences[0].source_start, proj.sequences[0].source_end) == (0.5, 4.5)
    assert win._editing_sequence_id is None and not win._selection_card.is_editing


def test_a_failed_edit_keeps_the_editing_mode_open(window, monkeypatch):
    win, proj = window
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win._start_bounds_edit(proj.sequences[0].id)
    # Bornes inchangées : refusé, l'utilisateur peut corriger sans tout recommencer.
    win._on_create_sequence_clicked()

    assert win._editing_sequence_id == proj.sequences[0].id and win._selection_card.is_editing


def test_cancelling_the_edit_leaves_the_sequence_untouched(window):
    win, proj = window
    before = (proj.sequences[0].source_start, proj.sequences[0].source_end)
    win._start_bounds_edit(proj.sequences[0].id)
    win._selection_start_spin.setValue(2.0)

    win._selection_card.cancel_edit_button.click()

    assert win._editing_sequence_id is None and not win._selection_card.is_editing
    assert (proj.sequences[0].source_start, proj.sequences[0].source_end) == before


def test_editing_ends_when_the_sequence_is_deleted(window):
    win, proj = window
    win._start_bounds_edit(proj.sequences[0].id)

    win._sequence_list._list_widget.setCurrentRow(0)
    win._sequence_list._list_widget.item(0).setSelected(True)
    win._sequence_list._delete_button.click()

    assert win._editing_sequence_id is None and not win._selection_card.is_editing


def test_new_source_ends_the_edit_mode(window):
    win, proj = window
    win._start_bounds_edit(proj.sequences[0].id)

    win._stop_bounds_edit()

    assert not win._selection_card.is_editing


def test_edit_brings_an_offscreen_sequence_into_view(window):
    win, proj = window
    win._waveform_widget.set_view_range(0.0, 3.0)  # zoom : la séquence [6, 9] est hors de la vue

    win._start_bounds_edit(proj.sequences[1].id)

    assert win._waveform_widget._view_start <= 6.0 and win._waveform_widget._view_end >= 9.0


def test_ensure_range_visible_does_nothing_when_already_visible(window):
    win, _proj = window
    win._waveform_widget.set_view_range(0.0, 10.0)

    win._waveform_widget.ensure_range_visible(2.0, 5.0)

    assert (win._waveform_widget._view_start, win._waveform_widget._view_end) == (0.0, 10.0)


def test_split_uses_the_playhead_position(window, monkeypatch):
    win, proj = window
    win._waveform_widget.set_playhead(2.5)
    calls = []
    monkeypatch.setattr(win._sequence_list, "split_sequence_at", lambda sid, at: calls.append((sid, at)) or True)

    win._split_sequence_at_playhead(proj.sequences[0].id)

    assert calls == [(proj.sequences[0].id, 2.5)]
    assert "divisée" in win.statusBar().currentMessage()


def test_split_end_to_end_through_the_window(window):
    win, proj = window
    win._waveform_widget.set_playhead(2.0)

    win._split_sequence_at_playhead(proj.sequences[0].id)

    assert [s.name for s in proj.sequences] == ["Intro (1)", "Intro (2)", "Fin"]
    win._sequence_list.undo_stack.undo()
    assert [s.name for s in proj.sequences] == ["Intro", "Fin"]


def test_new_shortcuts_are_documented_and_bound(window):
    win, _proj = window
    from PySide6.QtWidgets import QAbstractButton

    from app.ui.shortcuts import SHORTCUTS_HELP

    documented = {key for entries in SHORTCUTS_HELP.values() for key, _ in entries}
    bound = {b.shortcut().toString() for b in win.findChildren(QAbstractButton) if not b.shortcut().isEmpty()}

    assert {"F3", "S"} <= documented and {"F3", "S"} <= bound


def test_card_hides_the_short_hint_while_editing_to_avoid_a_squashed_layout(card):
    assert not card._hint_label.isHidden()

    card.set_editing("Intro")
    assert card._hint_label.isHidden()

    card.set_editing(None)
    assert not card._hint_label.isHidden()
