"""Tests de la comparaison A/B : écouter l'audio original ou traité d'une séquence, y compris pendant la lecture."""

import pytest
from PySide6.QtGui import QKeySequence

from app.config.settings import find_ffmpeg_binaries
from app.models.media import MediaInfo
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import sequence_service
from app.ui.main_window import MainWindow
from app.ui.sequence_list import SequenceListWidget


def _sequence(seq_id, name, start, end, processed=""):
    return Sequence(
        id=seq_id, name=name, source_start=start, source_end=end, order=-1,
        audio_path=f"C:/tmp/raw_{seq_id}.wav", processed_audio_path=processed,
    )


@pytest.fixture
def project():
    info = MediaInfo(
        path="v.mp4", duration=60.0, container_format="mp4", video_codec="h264", audio_codec="aac",
        sample_rate=44100, channels=2, resolution=(640, 360), bitrate=None, size_bytes=1,
    )
    proj = Project(name="demo", source_video=info, temp_dir="C:/tmp", original_audio_path="C:/tmp/a.wav")
    sequence_service.insert_sequence(proj, _sequence("a", "Intro", 0.0, 5.0, processed="C:/tmp/proc_a.wav"))
    sequence_service.insert_sequence(proj, _sequence("b", "Corps", 10.0, 20.0))  # jamais traitée
    return proj


# ============================ liste des séquences ==========================================================


@pytest.fixture
def lst(qtbot, project, ffmpeg_binaries):
    from app.services.ffmpeg_service import FFmpegService

    widget = SequenceListWidget(FFmpegService(ffmpeg_binaries.ffmpeg_path))
    qtbot.addWidget(widget)
    widget.set_project(project)
    return widget


def test_playback_defaults_to_the_processed_version(lst, project):
    assert not lst.plays_original
    assert lst.playback_path(project.sequences[0]) == "C:/tmp/proc_a.wav"


def test_original_button_switches_to_the_raw_audio(lst, project):
    lst._original_button.setChecked(True)

    assert lst.plays_original
    assert lst.playback_path(project.sequences[0]) == "C:/tmp/raw_a.wav"

    lst._original_button.setChecked(False)
    assert lst.playback_path(project.sequences[0]) == "C:/tmp/proc_a.wav"


def test_untreated_sequence_plays_the_same_file_either_way(lst, project):
    untreated = project.sequences[1]

    assert lst.playback_path(untreated) == "C:/tmp/raw_b.wav"
    lst._original_button.setChecked(True)
    assert lst.playback_path(untreated) == "C:/tmp/raw_b.wav"


def test_play_button_and_double_click_use_the_selected_version(lst, project):
    played = []
    lst.play_requested.connect(lambda name, path, start: played.append((name, path)))
    lst._list_widget.setCurrentRow(0)

    lst._play_button.click()
    lst._original_button.setChecked(True)
    lst._play_button.click()
    lst.play_sequence(project.sequences[0].id)

    assert played == [("Intro", "C:/tmp/proc_a.wav"), ("Intro", "C:/tmp/raw_a.wav"), ("Intro", "C:/tmp/raw_a.wav")]


def test_toggle_emits_its_state_and_the_button_documents_the_shortcut(qtbot, lst):
    states = []
    lst.original_toggled.connect(states.append)

    lst._original_button.click()
    lst._original_button.click()

    assert states == [True, False]
    assert lst._original_button.isCheckable()
    assert lst._original_button.shortcut() == QKeySequence("Ctrl+B")
    assert "Ctrl+B" in lst._original_button.toolTip()  # le raccourci est rappelé dans l'infobulle


# ============================ fenêtre principale ===========================================================


@pytest.fixture
def window(qtbot, monkeypatch, project, ffmpeg_binaries):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    monkeypatch.setattr(type(win._video_panel), "project", property(lambda self: project))
    win._sequence_list.set_project(project)
    calls = {"loaded": [], "replaced": []}
    monkeypatch.setattr(win._transport_controls, "load_and_play", calls["loaded"].append)
    monkeypatch.setattr(win._transport_controls, "replace_source_keep_position", calls["replaced"].append)
    win.calls = calls
    return win


def _play(window, row):
    window._sequence_list._list_widget.setCurrentRow(row)
    window._sequence_list._play_button.click()


def test_toggling_while_a_sequence_plays_swaps_the_version_in_place(window):
    _play(window, 0)
    assert window.calls["loaded"] == ["C:/tmp/proc_a.wav"]

    window._sequence_list._original_button.setChecked(True)
    assert window.calls["replaced"] == ["C:/tmp/raw_a.wav"]  # même séquence, version originale, position conservée

    window._sequence_list._original_button.setChecked(False)
    assert window.calls["replaced"] == ["C:/tmp/raw_a.wav", "C:/tmp/proc_a.wav"]
    assert window.calls["loaded"] == ["C:/tmp/proc_a.wav"]  # pas de nouveau chargement depuis le début


def test_now_playing_label_mentions_the_original_only_when_it_differs(window):
    _play(window, 0)
    assert window._transport_controls._now_playing_label.text() == "Intro"

    window._sequence_list._original_button.setChecked(True)
    assert window._transport_controls._now_playing_label.text() == "Intro · original"
    assert window._video_player_panel._sequence_badge.text() == "Intro · original"

    window._sequence_list._original_button.setChecked(False)
    assert window._transport_controls._now_playing_label.text() == "Intro"


def test_untreated_sequence_is_never_labelled_original(window):
    window._sequence_list._original_button.setChecked(True)

    _play(window, 1)

    assert window._transport_controls._now_playing_label.text() == "Corps"  # rien à comparer : pas d'étiquette trompeuse


def test_original_mode_set_before_playing_applies_to_the_next_play(window):
    window._sequence_list._original_button.setChecked(True)
    assert window.calls["replaced"] == []  # rien ne joue : simple réglage

    _play(window, 0)

    assert window.calls["loaded"] == ["C:/tmp/raw_a.wav"]
    assert window._transport_controls._now_playing_label.text() == "Intro · original"


def test_toggling_while_the_source_plays_does_not_touch_the_player(window):
    window._load_source_playback = lambda: None
    window._playback_offset = 0.0
    window._playing_sequence_id = None  # lecture de la source complète

    window._sequence_list._original_button.setChecked(True)

    assert window.calls["replaced"] == []


def test_toggling_after_the_merge_preview_does_not_swap_anything(window, monkeypatch):
    _play(window, 0)
    window._playback_offset = None  # aperçu du montage fusionné chargé
    window._playing_sequence_id = None

    window._sequence_list._original_button.setChecked(True)

    assert window.calls["replaced"] == []


def test_switching_to_the_source_forgets_the_playing_sequence(window, monkeypatch):
    _play(window, 0)
    assert window._playing_sequence_id == "a"
    monkeypatch.setattr(window, "_source_playback_path", lambda: "C:/tmp/source.wav")
    monkeypatch.setattr(window._transport_controls, "set_source", lambda p: None)

    window._load_source_playback()

    assert window._playing_sequence_id is None


def test_a_deleted_playing_sequence_is_ignored_on_toggle(window, project):
    _play(window, 0)
    sequence_service.remove_sequence_from_list(project, "a")

    window._sequence_list._original_button.setChecked(True)  # ne doit pas planter ni recharger

    assert window.calls["replaced"] == []


def test_ab_shortcut_is_documented(window):
    from app.ui.shortcuts import SHORTCUTS_HELP

    assert "Ctrl+B" in {key for entries in SHORTCUTS_HELP.values() for key, _ in entries}
