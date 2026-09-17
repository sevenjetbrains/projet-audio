"""Tests du formatage de timecode."""

import pytest

from app.utils.time_utils import format_timecode


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00:00.000"),
        (65.25, "00:01:05.250"),
        (3661.5, "01:01:01.500"),
    ],
)
def test_format_timecode(seconds, expected):
    assert format_timecode(seconds) == expected


def test_format_timecode_rejects_negative():
    with pytest.raises(ValueError):
        format_timecode(-1)
