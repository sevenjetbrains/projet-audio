"""Tests du formatage des dates et délais affichés sur l'écran d'accueil."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.utils.date_utils import format_elapsed, format_folder, format_moment

_NOW = datetime(2026, 9, 21, 10, 30)


@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2026, 9, 21, 9, 12), "aujourd'hui à 09:12"),
        (datetime(2026, 9, 20, 18, 24), "hier à 18:24"),
        (datetime(2026, 9, 17, 9, 51), "17 sept. à 09:51"),
        (datetime(2026, 9, 2, 15, 38), "2 sept. à 15:38"),
        (datetime(2026, 1, 8, 7, 5), "8 janv. à 07:05"),
    ],
)
def test_format_moment_of_the_current_year(moment, expected):
    assert format_moment(moment, now=_NOW) == expected


def test_format_moment_of_another_year_carries_it():
    assert format_moment(datetime(2025, 12, 24, 20, 0), now=_NOW) == "24 déc. 2025 à 20:00"


def test_midnight_yesterday_is_still_yesterday():
    """La bascule se fait sur la date, pas sur un écart de 24 h."""
    assert format_moment(datetime(2026, 9, 20, 23, 59), now=_NOW) == "hier à 23:59"


@pytest.mark.parametrize(
    "delta, expected",
    [
        (timedelta(seconds=5), "à l'instant"),
        (timedelta(seconds=59), "à l'instant"),
        (timedelta(minutes=3), "il y a 3 min"),
        (timedelta(minutes=59), "il y a 59 min"),
        (timedelta(hours=2), "il y a 2 h"),
        (timedelta(days=4), "il y a 4 j"),
    ],
)
def test_format_elapsed(delta, expected):
    assert format_elapsed(_NOW - delta, now=_NOW) == expected


def test_a_moment_in_the_future_does_not_produce_a_negative_delay():
    """Horloge système reculée : mieux vaut « à l'instant » que « il y a -2 min »."""
    assert format_elapsed(_NOW + timedelta(minutes=2), now=_NOW) == "à l'instant"


def test_format_folder_abbreviates_the_home_directory():
    inside_home = Path.home() / "Vidéos" / "conference" / "projet.acsproject"

    assert format_folder(str(inside_home)) == "~/Vidéos/conference/"


def test_format_folder_keeps_paths_outside_the_home_directory():
    result = format_folder("D:/Archives/2026/projet.acsproject")

    assert result.endswith("/Archives/2026/")
    assert not result.startswith("~")
