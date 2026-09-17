"""Tests de TransportControls (skip si aucun backend audio n'est disponible)."""

import pytest

from PySide6.QtMultimedia import QMediaPlayer


@pytest.fixture
def transport_controls(qtbot):
    from app.ui.transport_controls import TransportControls

    try:
        widget = TransportControls()
    except Exception as exc:  # backend audio indisponible dans cet environnement
        pytest.skip(f"Backend audio indisponible : {exc}")

    qtbot.addWidget(widget)
    return widget


def test_play_button_disabled_before_source(transport_controls):
    assert not transport_controls._play_button.isEnabled()


def test_set_source_enables_playback(transport_controls, synthetic_wav_file, qtbot):
    transport_controls.set_source(synthetic_wav_file)
    assert transport_controls._play_button.isEnabled()


def test_toggle_play_pause_updates_state(transport_controls, synthetic_wav_file, qtbot):
    transport_controls.set_source(synthetic_wav_file)

    qtbot.waitUntil(
        lambda: transport_controls._player.mediaStatus()
        in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia),
        timeout=5000,
    )

    transport_controls._toggle_play_pause()
    qtbot.waitUntil(
        lambda: transport_controls._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
        timeout=3000,
    )
    assert "Pause" in transport_controls._play_button.text()

    transport_controls._toggle_play_pause()
    qtbot.waitUntil(
        lambda: transport_controls._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState,
        timeout=3000,
    )
