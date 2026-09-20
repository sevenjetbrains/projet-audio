"""Tests de « écouter la sélection » (lecture d'une plage avec arrêt automatique) et de la touche plein écran."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow
from app.ui.selection_card import SelectionCard
from app.ui.transport_controls import TransportControls
from app.ui.video_preview import VideoPreview

_LOADED = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)


@pytest.fixture
def transport(qtbot):
    try:
        widget = TransportControls()
    except Exception as exc:  # backend audio indisponible dans cet environnement
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def loaded(qtbot, transport, synthetic_wav_file):
    """Transport prêt, avec un son de 2 s chargé."""
    transport.set_source(synthetic_wav_file)
    qtbot.waitUntil(lambda: transport._player.mediaStatus() in _LOADED, timeout=5000)
    return transport


# --- lecture d'une plage ----------------------------------------------------------------------------------


def test_play_range_plays_then_pauses_at_the_end_of_the_range(qtbot, loaded):
    finished = []
    loaded.range_finished.connect(lambda: finished.append(True))

    loaded.play_range(0.3, 0.8)
    qtbot.waitUntil(lambda: loaded.is_playing, timeout=3000)
    qtbot.waitUntil(lambda: bool(finished), timeout=4000)

    assert not loaded.is_playing
    assert loaded._player.position() == pytest.approx(800, abs=120)  # arrêté à la fin de la plage, pas des 2 s du média
    assert not loaded.is_playing_range


def test_play_range_starts_at_the_beginning_of_the_range(qtbot, loaded):
    positions = []
    loaded.position_changed.connect(positions.append)

    loaded.play_range(1.0, 1.4)
    qtbot.waitUntil(lambda: len(positions) > 0 and max(positions) >= 1.0, timeout=3000)

    assert min(p for p in positions if p > 0.05) >= 0.9  # aucune lecture avant le début de la plage


def test_play_range_ignores_an_empty_or_reversed_range(loaded):
    loaded.play_range(1.0, 1.0)
    loaded.play_range(1.5, 0.5)

    assert not loaded.is_playing
    assert not loaded.is_playing_range


def test_play_range_needs_a_loaded_source(transport):
    transport.play_range(0.0, 1.0)

    assert not transport.is_playing_range


def test_stale_position_beyond_the_end_does_not_stop_the_range_immediately(loaded, monkeypatch):
    """Le lecteur peut rapporter l'ancienne position (après la fin) avant d'avoir appliqué le déplacement au début."""
    finished, calls = [], []
    loaded.range_finished.connect(lambda: finished.append(True))
    monkeypatch.setattr(loaded._player, "pause", lambda: calls.append("pause"))
    monkeypatch.setattr(loaded._player, "setPosition", lambda ms: calls.append(("seek", ms)))
    loaded._range_end_ms, loaded._range_armed = 600, False  # état juste après play_range, avant toute position reçue

    loaded._check_range_end(1500)  # position périmée (ancien emplacement) : ne doit rien arrêter

    assert finished == [] and calls == []
    assert loaded.is_playing_range

    loaded._check_range_end(300)  # première vraie position, dans la plage : arme l'arrêt
    assert finished == [] and calls == []

    loaded._check_range_end(650)  # la fin est dépassée

    assert finished == [True]
    assert calls == ["pause", ("seek", 600)]  # pause, puis retour exact sur la borne de fin
    assert not loaded.is_playing_range


@pytest.mark.parametrize(
    "action",
    [
        lambda t: t.set_position_seconds(1.0),
        lambda t: t.seek_throttled(1.0),
        lambda t: t.skip(1.0),
        lambda t: t.stop(),
    ],
    ids=["clic", "glissement", "saut", "stop"],
)
def test_user_actions_cancel_the_automatic_stop(loaded, action):
    loaded.play_range(0.2, 0.6)
    assert loaded.is_playing_range

    action(loaded)

    assert not loaded.is_playing_range  # l'utilisateur reprend la main : la lecture ne doit plus s'arrêter seule


def test_changing_source_cancels_the_range(loaded, synthetic_wav_file):
    loaded.play_range(0.2, 0.6)

    loaded.set_source(synthetic_wav_file)

    assert not loaded.is_playing_range


def test_pause_and_resume_keeps_the_range(loaded):
    loaded.play_range(0.2, 0.6)

    loaded.toggle_play_pause()  # pause
    loaded.toggle_play_pause()  # reprise

    assert loaded.is_playing_range  # reprendre après une pause conserve la fin de la plage


# --- carte de sélection ----------------------------------------------------------------------------------


@pytest.fixture
def card(qtbot):
    widget = SelectionCard()
    qtbot.addWidget(widget)
    widget.set_range(60.0)
    return widget


def test_listen_button_is_disabled_until_a_range_is_chosen(card):
    assert not card.listen_button.isEnabled()

    card.start_spin.setValue(2.0)
    card.end_spin.setValue(5.0)

    assert card.listen_button.isEnabled()

    card.end_spin.setValue(2.0)
    assert not card.listen_button.isEnabled()


def test_listen_button_emits_request_and_mentions_its_shortcut(qtbot, card):
    card.start_spin.setValue(1.0)
    card.end_spin.setValue(4.0)

    with qtbot.waitSignal(card.listen_requested, timeout=1000):
        card.listen_button.click()

    assert "Maj+Espace" in card.listen_button.toolTip()


# --- fenêtre principale ----------------------------------------------------------------------------------


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    return win


def _project(window, monkeypatch):
    from app.models.media import MediaInfo
    from app.models.project import Project

    info = MediaInfo(
        path="v.mp4", duration=30.0, container_format="mp4", video_codec="h264", audio_codec="aac",
        sample_rate=44100, channels=2, resolution=(640, 360), bitrate=None, size_bytes=1,
    )
    project = Project(name="demo", source_video=info, temp_dir="C:/tmp/x", original_audio_path="C:/tmp/x/a.wav")
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: project))
    return project


def test_listening_without_a_selection_only_shows_a_hint(window, monkeypatch):
    _project(window, monkeypatch)
    played = []
    monkeypatch.setattr(window._transport_controls, "play_range", lambda *a: played.append(a))

    window._listen_to_selection()

    assert played == []
    assert "Sélectionnez une plage" in window.statusBar().currentMessage()


def test_listening_without_a_project_does_nothing(window, monkeypatch):
    played = []
    monkeypatch.setattr(window._transport_controls, "play_range", lambda *a: played.append(a))
    window._selection_card.set_range(30.0)
    window._selection_start_spin.setValue(1.0)
    window._selection_end_spin.setValue(3.0)

    window._listen_to_selection()

    assert played == []


def test_listening_plays_exactly_the_selected_range(window, monkeypatch):
    _project(window, monkeypatch)
    played = []
    monkeypatch.setattr(window._transport_controls, "play_range", lambda s, e: played.append((s, e)))
    window._selection_card.set_range(30.0)
    window._selection_start_spin.setValue(4.5)
    window._selection_end_spin.setValue(9.25)

    window._listen_to_selection()

    assert played == [(4.5, 9.25)]


def test_listening_switches_back_to_the_source_when_a_sequence_was_loaded(window, monkeypatch):
    _project(window, monkeypatch)
    monkeypatch.setattr(window._transport_controls, "play_range", lambda s, e: None)
    calls = []
    monkeypatch.setattr(window, "_load_source_playback", lambda: calls.append("source"))
    window._playback_offset = 12.0  # une séquence était chargée
    window._selection_card.set_range(30.0)
    window._selection_start_spin.setValue(1.0)
    window._selection_end_spin.setValue(2.0)

    window._listen_to_selection()

    assert calls == ["source"]
    assert window._playback_offset == 0.0


def test_shift_space_shortcut_is_bound_to_the_listen_action(window, monkeypatch):
    shortcut = next(s for s in window.findChildren(QShortcut) if s.key().toString() == "Shift+Space")
    calls = []
    monkeypatch.setattr(window._transport_controls, "play_range", lambda s, e: calls.append((s, e)))
    _project(window, monkeypatch)
    window._selection_card.set_range(30.0)
    window._selection_start_spin.setValue(2.0)
    window._selection_end_spin.setValue(4.0)

    shortcut.activated.emit()

    assert calls == [(2.0, 4.0)]  # le raccourci déclenche bien « écouter la sélection »


def test_shift_space_is_documented_in_the_help(window):
    from app.ui.shortcuts import SHORTCUTS_HELP

    documented = {key for entries in SHORTCUTS_HELP.values() for key, _ in entries}

    assert {"Shift+Space", "F", "F11"} <= documented


# --- touche plein écran ----------------------------------------------------------------------------------


def test_f_and_f11_are_bound_to_fullscreen(window):
    keys = {s.key().toString() for s in window.findChildren(QShortcut)}

    assert {"F", "F11"} <= keys


@pytest.mark.parametrize("key", [Qt.Key.Key_F, Qt.Key.Key_F11, Qt.Key.Key_Escape])
def test_keys_leave_fullscreen(qtbot, key):
    host = QWidget()
    qtbot.addWidget(host)
    preview = VideoPreview(host)
    preview.host = host
    preview.set_active(True)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)
    preview.toggle_fullscreen()
    assert preview.is_fullscreen

    QTest.keyClick(preview._fullscreen_window, key)

    assert not preview.is_fullscreen
