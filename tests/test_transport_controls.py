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
    # Le bouton est devenu une icône (maquette) : on vérifie l'état de lecture, pas le libellé.
    assert transport_controls.is_playing

    transport_controls._toggle_play_pause()
    qtbot.waitUntil(
        lambda: transport_controls._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState,
        timeout=3000,
    )


def _wait_loaded(qtbot, transport_controls):
    qtbot.waitUntil(
        lambda: transport_controls._player.mediaStatus()
        in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia),
        timeout=5000,
    )


def test_extra_controls_disabled_before_source_and_enabled_after(transport_controls, synthetic_wav_file):
    buttons = (transport_controls._stop_button, transport_controls._back_button, transport_controls._forward_button)
    assert not any(b.isEnabled() for b in buttons)

    transport_controls.set_source(synthetic_wav_file)

    assert all(b.isEnabled() for b in buttons)


def test_skip_is_clamped_to_media_bounds(transport_controls, synthetic_wav_file, qtbot):
    transport_controls.set_source(synthetic_wav_file)
    _wait_loaded(qtbot, transport_controls)
    duration = transport_controls._player.duration()

    transport_controls.skip(-5.0)
    qtbot.waitUntil(lambda: transport_controls._player.position() == 0, timeout=2000)

    transport_controls.skip(10_000.0)
    qtbot.waitUntil(lambda: transport_controls._player.position() == duration, timeout=2000)


def test_volume_slider_controls_audio_output(transport_controls):
    transport_controls._volume_slider.setValue(40)
    assert transport_controls._audio_output.volume() == pytest.approx(0.4, abs=0.01)

    transport_controls.set_volume_percent(250)
    assert transport_controls._audio_output.volume() == pytest.approx(1.0)


def test_load_and_play_starts_playback(transport_controls, synthetic_wav_file, qtbot):
    transport_controls.load_and_play(synthetic_wav_file)

    qtbot.waitUntil(
        lambda: transport_controls._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
        timeout=5000,
    )
    assert transport_controls.is_playing


def test_play_without_source_is_ignored(transport_controls):
    transport_controls.play()

    assert transport_controls._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
