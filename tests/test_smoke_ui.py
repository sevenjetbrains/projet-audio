"""Smoke test : la fenêtre principale s'instancie sans planter."""

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow


def test_main_window_instantiates(qtbot, monkeypatch):
    # Évite toute dépendance à l'état réel de temp/ (autosaves d'une session
    # précédente) : sinon MainWindow.__init__ planifie une QMessageBox.question
    # modale (récupération autosave) qui bloquerait ce test.
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    assert window.windowTitle() == "AudioCut Studio"
    assert window.centralWidget() is not None


def test_recent_projects_menu_lists_and_opens(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    project_file = tmp_path / "demo.acsproject"
    project_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.ui.main_window.load_recent_projects", lambda: [str(project_file)])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    opened = []
    monkeypatch.setattr(window, "_start_project_load", lambda path, remember=True: opened.append(path))

    window._populate_recent_menu()
    actions = window._recent_menu.actions()
    assert [a.text() for a in actions] == ["demo.acsproject"]

    actions[0].trigger()
    assert opened == [str(project_file)]


def test_recent_projects_menu_empty(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.load_recent_projects", lambda: [])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    window._populate_recent_menu()
    assert [(a.text(), a.isEnabled()) for a in window._recent_menu.actions()] == [("(aucun)", False)]


def _window_with_duration(qtbot, monkeypatch, duration=10.0):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    for spin in (window._selection_start_spin, window._selection_end_spin):
        spin.setRange(0.0, duration)
    return window


def test_mark_in_out_shortcuts_set_selection_from_playhead(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 2.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))

    window._mark_selection_start()
    position["value"] = 6.5
    window._mark_selection_end()

    assert window._selection_start_spin.value() == 2.0
    assert window._selection_end_spin.value() == 6.5


def test_mark_in_after_out_pushes_end_forward(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 3.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))
    window._mark_selection_end()

    position["value"] = 8.0
    window._mark_selection_start()

    assert window._selection_start_spin.value() == 8.0
    assert window._selection_end_spin.value() == 8.0


def test_mark_out_before_in_pulls_start_back(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 5.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))
    window._mark_selection_start()

    position["value"] = 1.0
    window._mark_selection_end()

    assert window._selection_start_spin.value() == 1.0
    assert window._selection_end_spin.value() == 1.0


def test_enter_shortcut_creates_sequence_from_selection(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence, QShortcut

    window = _window_with_duration(qtbot, monkeypatch)
    calls = []
    monkeypatch.setattr(window._sequence_list, "add_sequence_from_selection", lambda s, e: calls.append((s, e)))
    window._selection_start_spin.setValue(1.0)
    window._selection_end_spin.setValue(4.0)

    enter_shortcuts = [
        sc for sc in window.findChildren(QShortcut)
        if sc.key() in (QKeySequence(Qt.Key.Key_Return), QKeySequence(Qt.Key.Key_Enter))
    ]
    assert len(enter_shortcuts) == 2

    window._on_create_sequence_clicked()
    assert calls == [(1.0, 4.0)]


def test_status_bar_summary_tracks_sequences_and_crossfade(qtbot, monkeypatch):
    from app.models.project import Project
    from app.models.sequence import Sequence

    window = _window_with_duration(qtbot, monkeypatch)
    assert window._project_summary_label.text() == "Aucun projet"

    project = Project(name="demo")
    project.sequences = [
        Sequence(id="a", name="A", source_start=0.0, source_end=4.0, order=0),
        Sequence(id="b", name="B", source_start=10.0, source_end=16.0, order=1),
    ]
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))

    window._update_project_summary()
    assert window._project_summary_label.text() == "2 séquences — durée fusionnée : 00:00:10.000"

    window._crossfade_spin.setValue(1.0)
    assert window._project_summary_label.text() == "2 séquences — durée fusionnée : 00:00:09.000"

    project.sequences.pop()
    window._on_sequences_changed()
    assert window._project_summary_label.text() == "1 séquence — durée fusionnée : 00:00:04.000"


def test_sequence_play_request_loads_and_plays(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    played = []
    monkeypatch.setattr(window._transport_controls, "load_and_play", played.append)

    window._sequence_list.play_requested.emit("Séquence 1", "C:/x/seq.wav", 12.5)

    assert played == ["C:/x/seq.wav"]
    assert window._playback_offset == 12.5


def test_playback_position_offset_by_playing_sequence_start(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    positions = []
    monkeypatch.setattr(window._waveform_widget, "set_playhead", positions.append)

    window._sequence_list.play_requested.emit("Séquence 1", "C:/x/seq.wav", 12.5)
    window._transport_controls.position_changed.emit(1.5)

    assert positions == [14.0]


def test_playback_offset_reset_when_full_source_loaded(qtbot, monkeypatch):
    from app.models.project import Project

    window = _window_with_duration(qtbot, monkeypatch)
    window._playback_offset = 12.5
    project = Project(name="demo")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))

    window._on_audio_ready("C:/x/source.wav", 10.0)

    assert window._playback_offset == 0.0


def test_merge_preview_suppresses_playhead_offset(qtbot, monkeypatch):
    from app.models.project import Project

    window = _window_with_duration(qtbot, monkeypatch)
    project = Project(name="demo", original_audio_path="C:/x/source.wav")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))
    monkeypatch.setattr("app.ui.main_window.merge_sequences", lambda *a, **k: "C:/x/final.wav")
    monkeypatch.setattr(window._transport_controls, "load_and_play", lambda *_: None)

    window._on_merge_preview_clicked()

    assert window._playback_offset is None

    positions = []
    monkeypatch.setattr(window._waveform_widget, "set_playhead", positions.append)
    window._transport_controls.position_changed.emit(3.0)
    assert positions == []


def test_waveform_seek_reloads_source_after_sequence_playback(qtbot, monkeypatch):
    from app.models.project import Project

    window = _window_with_duration(qtbot, monkeypatch)
    project = Project(name="demo", original_audio_path="C:/x/source.wav")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))
    window._playback_offset = 12.5  # une séquence était en cours de lecture

    sources_loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", sources_loaded.append)
    seeked = []
    monkeypatch.setattr(window._transport_controls, "set_position_seconds", seeked.append)

    window._on_waveform_seek_requested(4.0)

    assert sources_loaded == ["C:/x/source.wav"]
    assert seeked == [4.0]
    assert window._playback_offset == 0.0


def test_waveform_seek_does_not_reload_when_already_on_source(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    window._playback_offset = 0.0

    sources_loaded = []
    monkeypatch.setattr(window._transport_controls, "set_source", sources_loaded.append)
    seeked = []
    monkeypatch.setattr(window._transport_controls, "set_position_seconds", seeked.append)

    window._on_waveform_seek_requested(4.0)

    assert sources_loaded == []
    assert seeked == [4.0]


def test_double_click_on_waveform_region_plays_the_sequence(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    played = []
    monkeypatch.setattr(window._sequence_list, "play_sequence", played.append)

    window._waveform_widget.region_double_clicked.emit("seq-1")

    assert played == ["seq-1"]
