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


def test_delete_removes_item_and_file(widget_with_project):
    widget, project = widget_with_project
    widget.add_sequence_from_selection(0.0, 0.4)
    sequence = project.sequences[0]

    widget._list_widget.setCurrentRow(0)
    widget._on_delete_clicked()

    assert widget._list_widget.count() == 0
    assert project.sequences == []
    assert not Path(sequence.audio_path).exists()


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
