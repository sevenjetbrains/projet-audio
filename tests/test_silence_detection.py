"""Tests de app.audio.silence_detection.compute_keep_ranges (géométrie pure)."""

from app.audio.silence_detection import compute_keep_ranges


def test_no_silences_keeps_everything():
    assert compute_keep_ranges([], total_duration=10.0) == [(0.0, 10.0)]


def test_single_silence_in_middle():
    keep = compute_keep_ranges([(4.0, 6.0)], total_duration=10.0)
    assert keep == [(0.0, 4.0), (6.0, 10.0)]


def test_keep_padding_shrinks_silence():
    keep = compute_keep_ranges([(4.0, 6.0)], total_duration=10.0, keep_padding=0.5)
    assert keep == [(0.0, 4.5), (5.5, 10.0)]


def test_silence_at_start_and_end():
    keep = compute_keep_ranges([(0.0, 1.0), (9.0, 10.0)], total_duration=10.0)
    assert keep == [(1.0, 9.0)]


def test_padding_larger_than_silence_removes_it():
    keep = compute_keep_ranges([(4.0, 4.2)], total_duration=10.0, keep_padding=0.5)
    assert keep == [(0.0, 10.0)]


def test_entirely_silent_returns_empty():
    keep = compute_keep_ranges([(0.0, 10.0)], total_duration=10.0)
    assert keep == []
