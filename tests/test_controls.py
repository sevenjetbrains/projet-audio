"""Tests des contrôles de la maquette : interrupteur, boutons segmentés, curseur, carte de profil."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from app.config.themes import get_theme
from app.ui.controls import ProfileCard, SegmentedControl, SliderRow, ToggleSwitch


def _pixel(widget, x: int, y: int) -> QColor:
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio))


# --- Interrupteur ------------------------------------------------------------


def test_toggle_reports_and_changes_its_state(qtbot):
    toggle = ToggleSwitch()
    qtbot.addWidget(toggle)
    states = []
    toggle.toggled.connect(states.append)

    QTest.mouseClick(toggle, Qt.MouseButton.LeftButton)

    assert toggle.isChecked() and states == [True]


def test_toggle_moves_its_knob_and_changes_colour_when_checked(qtbot):
    toggle = ToggleSwitch()
    qtbot.addWidget(toggle)
    toggle.set_theme(get_theme("Sombre"))
    off_track = _pixel(toggle, 26, 4)
    off_left = _pixel(toggle, 10, 14)

    toggle.setChecked(True)

    assert _pixel(toggle, 26, 4) != off_track          # la piste passe en accent
    assert _pixel(toggle, 10, 14) != off_left          # le bouton a quitté la gauche
    assert _pixel(toggle, 42, 14) != _pixel(toggle, 26, 4)  # il est à droite


def test_toggle_follows_the_theme(qtbot):
    toggle = ToggleSwitch()
    qtbot.addWidget(toggle)
    toggle.setChecked(True)

    toggle.set_theme(get_theme("Sombre"))
    dark = _pixel(toggle, 26, 14)
    toggle.set_theme(get_theme("Clair"))

    assert _pixel(toggle, 26, 14) != dark


# --- Boutons segmentés --------------------------------------------------------


@pytest.fixture
def segments(qtbot):
    control = SegmentedControl(("Aucune", "Faible", "Moyenne", "Forte"))
    qtbot.addWidget(control)
    return control


def test_segmented_control_starts_on_its_first_option(segments):
    assert segments.value() == "Aucune"


def test_segmented_control_is_exclusive_and_announces_the_choice(segments):
    chosen = []
    segments.changed.connect(chosen.append)

    segments._group.button(2).click()

    assert segments.value() == "Moyenne"
    assert chosen == ["Moyenne"]
    assert [b.isChecked() for b in segments._group.buttons()] == [False, False, True, False]


def test_setting_the_value_does_not_re_emit(segments):
    chosen = []
    segments.changed.connect(chosen.append)

    segments.set_value("Forte")

    assert segments.value() == "Forte"
    assert chosen == []


def test_an_unknown_option_is_ignored(segments):
    segments.set_value("Extrême")

    assert segments.value() == "Aucune"


# --- Ligne de curseur ----------------------------------------------------------


def test_slider_row_exposes_a_decimal_value_through_an_integer_slider(qtbot):
    row = SliderRow("Gain", -12.0, 12.0, "dB", signed=True)
    qtbot.addWidget(row)

    row.set_value(-3.5)

    assert row.value() == pytest.approx(-3.5)
    assert row.slider.value() == -35


def test_slider_row_writes_the_value_the_french_way(qtbot):
    row = SliderRow("Basses", -12.0, 12.0, "dB", signed=True)
    qtbot.addWidget(row)

    row.set_value(-3.0)
    assert row._value_label.text() == "-3,0 dB"

    row.set_value(2.0)
    assert row._value_label.text() == "+2,0 dB"


def test_an_unsigned_row_has_no_plus_sign_and_can_drop_the_decimals(qtbot):
    row = SliderRow("Cible", -30.0, -5.0, "LUFS", scale=1, decimals=0)
    qtbot.addWidget(row)

    row.set_value(-16.0)

    assert row._value_label.text() == "-16 LUFS"


def test_setting_the_value_programmatically_does_not_emit(qtbot):
    row = SliderRow("Gain", -12.0, 12.0, "dB")
    qtbot.addWidget(row)
    seen = []
    row.value_changed.connect(seen.append)

    row.set_value(4.0)
    assert seen == []

    row.slider.setValue(60)
    assert seen == [pytest.approx(6.0)]


# --- Carte de profil ------------------------------------------------------------


def test_profile_card_shows_a_check_only_when_selected(qtbot):
    card = ProfileCard("Podcast")
    qtbot.addWidget(card)

    assert card.property("profile") == "false"
    assert not card._check_label.isVisibleTo(card)

    card.set_selected(True)

    assert card.property("profile") == "true"
    assert card._check_label.isVisibleTo(card)


def test_clicking_a_profile_card_announces_its_name(qtbot):
    card = ProfileCard("Podcast")
    qtbot.addWidget(card)
    card.resize(200, 50)
    chosen = []
    card.clicked.connect(chosen.append)

    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))

    assert chosen == ["Podcast"]
