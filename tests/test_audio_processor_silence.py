"""Tests d'intégration : suppression des silences via audio_processor.process_sequence."""

import wave
from pathlib import Path

import numpy as np
import pytest

from app.models.audio_settings import AudioSettings
from app.models.media import MediaInfo
from app.models.project import Project
from app.services import sequence_service
from app.services.audio_processor import process_sequence
from app.services.ffmpeg_service import FFmpegService


@pytest.fixture
def project_with_silence_sequence(ffmpeg_binaries, tmp_path):
    """Séquence de 2s : 1s de silence puis 1s de tonalité."""
    framerate = 8000
    silence = np.zeros(framerate, dtype=np.int16)
    t = np.linspace(0, 1, framerate, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    samples = np.concatenate([silence, tone])

    source_wav = tmp_path / "source.wav"
    with wave.open(str(source_wav), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(framerate)
        wav_file.writeframes(samples.tobytes())

    project = Project(
        name="test",
        source_video=MediaInfo(
            path="x.mp4", duration=2.0, container_format="wav", video_codec=None,
            audio_codec="pcm_s16le", sample_rate=framerate, channels=1, resolution=None,
            bitrate=None, size_bytes=1,
        ),
        temp_dir=str(tmp_path),
        original_audio_path=str(source_wav),
    )

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    sequence = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 2.0)
    return project, sequence, ffmpeg_service


def test_process_sequence_removes_leading_silence(project_with_silence_sequence):
    project, sequence, ffmpeg_service = project_with_silence_sequence
    sequence.audio_settings = AudioSettings(
        silence_removal=True, silence_threshold_db=-35.0, silence_min_duration=0.3, silence_keep_padding=0.0
    )

    result = process_sequence(project, sequence, ffmpeg_service)

    assert result is not None
    with wave.open(result, "rb") as w:
        duration = w.getnframes() / w.getframerate()
    # Le silence (~1s) doit avoir été retiré, ne reste que la tonalité (~1s)
    assert duration == pytest.approx(1.0, abs=0.1)
    # Le fichier brut original n'est jamais modifié
    assert Path(sequence.audio_path).exists()


def test_process_sequence_silence_removal_plus_gain(project_with_silence_sequence):
    project, sequence, ffmpeg_service = project_with_silence_sequence
    sequence.audio_settings = AudioSettings(silence_removal=True, silence_min_duration=0.3, gain=3.0)

    result = process_sequence(project, sequence, ffmpeg_service)

    assert result is not None
    assert Path(result).exists()
    assert sequence.processed_audio_path == result
