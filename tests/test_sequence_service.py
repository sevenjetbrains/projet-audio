"""Tests de app.services.sequence_service."""

from pathlib import Path

import pytest

from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video


@pytest.fixture
def project_with_audio(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    return project, ffmpeg_service


def test_add_sequence_creates_wav_file(project_with_audio):
    project, ffmpeg_service = project_with_audio

    sequence = sequence_service.add_sequence(project, ffmpeg_service, 0.1, 0.6)

    assert sequence in project.sequences
    assert Path(sequence.audio_path).exists()
    assert sequence.order == 0
    assert sequence.duration == pytest.approx(0.5)


def test_add_sequence_rejects_invalid_range(project_with_audio):
    project, ffmpeg_service = project_with_audio
    with pytest.raises(ValueError):
        sequence_service.add_sequence(project, ffmpeg_service, 0.5, 0.5)


def test_remove_sequence_deletes_file_and_reindexes(project_with_audio):
    project, ffmpeg_service = project_with_audio
    seq1 = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.2)
    seq2 = sequence_service.add_sequence(project, ffmpeg_service, 0.2, 0.4)

    sequence_service.remove_sequence(project, seq1.id)

    assert project.sequences == [seq2]
    assert seq2.order == 0
    assert not Path(seq1.audio_path).exists()


def test_duplicate_sequence_copies_file(project_with_audio):
    project, ffmpeg_service = project_with_audio
    original = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.3)

    duplicate = sequence_service.duplicate_sequence(project, original.id)

    assert duplicate.id != original.id
    assert duplicate.audio_path != original.audio_path
    assert Path(duplicate.audio_path).exists()
    assert "(copie)" in duplicate.name


def test_rename_sequence(project_with_audio):
    project, ffmpeg_service = project_with_audio
    seq = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.2)

    sequence_service.rename_sequence(project, seq.id, "Introduction")

    assert seq.name == "Introduction"


def test_reorder_sequences(project_with_audio):
    project, ffmpeg_service = project_with_audio
    seq1 = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.2)
    seq2 = sequence_service.add_sequence(project, ffmpeg_service, 0.2, 0.4)
    seq3 = sequence_service.add_sequence(project, ffmpeg_service, 0.4, 0.6)

    sequence_service.reorder_sequences(project, [seq3.id, seq1.id, seq2.id])

    assert [seq.id for seq in project.sequences] == [seq3.id, seq1.id, seq2.id]
    assert [seq.order for seq in project.sequences] == [0, 1, 2]


def test_reorder_sequences_rejects_mismatched_ids(project_with_audio):
    project, ffmpeg_service = project_with_audio
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.2)

    with pytest.raises(ValueError):
        sequence_service.reorder_sequences(project, ["not-a-real-id"])
