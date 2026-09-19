"""Tests de SequenceListWidget."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui.sequence_list import SequenceListWidget


@pytest.fixture
def widget_with_project(qtbot, ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    widget = SequenceListWidget(ffmpeg_service)
    qtbot.addWidget(widget)
    widget.set_project(project)
    return widget, project


def test_add_sequence_from_selection_populates_list(widget_with_project):
    widget, project = widget_with_project

    widget.add_sequence_from_selection(0.0, 0.4)

    assert widget._list_widget.count() == 1
    assert len(project.sequences) == 1


def test_delete_removes_item_but_keeps_file_for_undo(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)
    sequence = project.sequences[0]

    widget._list_widget.setCurrentRow(0)
    widget._on_delete_clicked()

    assert widget._list_widget.count() == 0
    assert project.sequences == []
    # Le fichier est conservé (pas encore de suppression définitive) pour permettre Ctrl+Z.
    assert Path(sequence.audio_path).exists()


def test_undo_restores_deleted_sequence(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)
    sequence_id = project.sequences[0].id

    widget._list_widget.setCurrentRow(0)
    widget._on_delete_clicked()
    assert project.sequences == []

    widget.undo_stack.undo()

    assert len(project.sequences) == 1
    assert project.sequences[0].id == sequence_id
    assert widget._list_widget.count() == 1


def test_redo_reapplies_delete(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)

    widget._list_widget.setCurrentRow(0)
    widget._on_delete_clicked()
    widget.undo_stack.undo()
    widget.undo_stack.redo()

    assert project.sequences == []
    assert widget._list_widget.count() == 0


def test_undo_add_sequence(widget_with_project):
    widget, project = widget_with_project

    widget.add_sequence_from_selection(0.0, 0.4)
    assert len(project.sequences) == 1

    widget.undo_stack.undo()
    assert project.sequences == []
    assert widget._list_widget.count() == 0

    widget.undo_stack.redo()
    assert len(project.sequences) == 1


def test_duplicate_adds_second_item(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)

    widget._list_widget.setCurrentRow(0)
    widget._on_duplicate_clicked()

    assert widget._list_widget.count() == 2
    assert len(project.sequences) == 2


def test_play_requested_emits_signal(widget_with_project, qtbot):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)
    widget._list_widget.setCurrentRow(0)

    with qtbot.waitSignal(widget.play_requested, timeout=1000) as blocker:
        widget._on_play_clicked()

    name, audio_path = blocker.args
    assert Path(audio_path).exists()


def test_reorder_updates_project_order(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.2)
    widget.add_sequence_from_selection(0.2, 0.4)
    widget.add_sequence_from_selection(0.4, 0.6)

    first_id, second_id, third_id = (seq.id for seq in project.sequences)

    item = widget._list_widget.takeItem(2)
    widget._list_widget.insertItem(0, item)

    widget._on_rows_moved()

    assert [seq.id for seq in project.sequences] == [third_id, first_id, second_id]


def _add_three(widget):
    widget.add_sequence_from_selection(0.0, 0.2)
    widget.add_sequence_from_selection(0.2, 0.4)
    widget.add_sequence_from_selection(0.4, 0.6)


def _select_rows(widget, rows):
    widget._list_widget.clearSelection()
    for row in rows:
        widget._list_widget.item(row).setSelected(True)


def test_selection_changed_emits_selected_sequences_in_order(widget_with_project):
    widget, project = widget_with_project
    _add_three(widget)
    emissions = []
    widget.selection_changed.connect(emissions.append)

    _select_rows(widget, [2, 0])

    assert [seq.id for seq in emissions[-1]] == [project.sequences[0].id, project.sequences[2].id]


def test_delete_multiple_and_undo_restores_original_positions(widget_with_project):
    widget, project = widget_with_project
    _add_three(widget)
    ids = [seq.id for seq in project.sequences]

    _select_rows(widget, [0, 2])
    widget._on_delete_clicked()

    assert [seq.id for seq in project.sequences] == [ids[1]]
    assert widget._list_widget.count() == 1

    widget.undo_stack.undo()
    assert [seq.id for seq in project.sequences] == ids
    assert [seq.order for seq in project.sequences] == [0, 1, 2]

    widget.undo_stack.redo()
    assert [seq.id for seq in project.sequences] == [ids[1]]


def test_duplicate_multiple_creates_copies_and_undo_removes_them(widget_with_project):
    widget, project = widget_with_project
    _add_three(widget)

    _select_rows(widget, [0, 1])
    widget._on_duplicate_clicked()

    assert len(project.sequences) == 5
    assert len({seq.id for seq in project.sequences}) == 5

    widget.undo_stack.undo()
    assert len(project.sequences) == 3


def test_select_sequence_selects_only_that_row(widget_with_project):
    widget, project = widget_with_project
    _add_three(widget)
    _select_rows(widget, [0, 2])
    target = project.sequences[1]

    widget.select_sequence(target.id)

    assert [seq.id for seq in widget.selected_sequences()] == [target.id]
    assert widget.current_sequence().id == target.id


def test_select_unknown_sequence_changes_nothing(widget_with_project):
    widget, project = widget_with_project
    _add_three(widget)
    _select_rows(widget, [0])

    widget.select_sequence("inconnu")

    assert [seq.id for seq in widget.selected_sequences()] == [project.sequences[0].id]
