"""Tests des icônes vectorielles (rendu, recoloration par thème, boutons, actions, widgets détruits)."""

import pytest
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import QLabel, QPushButton

from app.config.palette import DARK_PALETTE, LIGHT_PALETTE
from app.ui import icons
from app.ui.design import icon_button
from app.ui.icons import ICON_NAMES, render_icon, set_action_icon, set_button_icon, set_icon_palette, set_label_icon


@pytest.fixture(autouse=True)
def _restore_palette(qapp):
    # `qapp` : les QPixmap exigent une application Qt, même pour les tests qui ne créent aucun widget.
    yield
    set_icon_palette(DARK_PALETTE)


def _painted_pixels(pixmap) -> list[QColor]:
    image = pixmap.toImage()
    return [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    ]


def _solid_color(pixmap) -> QColor:
    """Couleur au cœur du dessin (pixel le plus opaque) : les bords adoucis ont une teinte approximative."""
    return max(_painted_pixels(pixmap), key=lambda c: c.alpha())


def _alpha_channel(pixmap):
    import numpy as np

    image = pixmap.toImage()
    return np.array([[image.pixelColor(x, y).alpha() for x in range(image.width())] for y in range(image.height())])


@pytest.mark.parametrize("name", sorted(ICON_NAMES))
def test_every_icon_draws_something_in_the_requested_color(name):
    pixels = _painted_pixels(render_icon(name, "#ff0000"))

    assert len(pixels) > 20, f"icône « {name} » vide"
    # Toute la matière dessinée est de la couleur demandée (seul l'alpha varie, à cause de l'anticrénelage).
    assert all(p.red() == 255 and p.green() == 0 and p.blue() == 0 for p in pixels)


def test_icons_are_rendered_at_double_resolution():
    pixmap = render_icon("play", "#ffffff")

    assert pixmap.devicePixelRatio() == 2
    assert pixmap.width() == 2 * icons.ICON_SIZE


def test_unknown_icon_is_rejected():
    with pytest.raises(KeyError):
        render_icon("inexistante", "#ffffff")


def test_redo_is_the_mirror_of_undo():
    import numpy as np

    undo = _alpha_channel(render_icon("undo", "#ffffff"))
    redo = _alpha_channel(render_icon("redo", "#ffffff"))

    assert undo.sum() > 0
    # Symétrie exacte au bruit de calcul flottant près (écart de quelques niveaux d'alpha sur 255).
    assert np.abs(redo.astype(int) - undo[:, ::-1].astype(int)).max() <= 4


def test_set_button_icon_replaces_text_and_registers(qtbot):
    button = QPushButton("▶")
    qtbot.addWidget(button)

    set_button_icon(button, "play")

    assert button.text() == ""
    assert not button.icon().isNull()


def test_icon_button_uses_vector_icon_for_known_names_and_text_otherwise(qtbot):
    known = icon_button("stop")
    other = icon_button("?")
    qtbot.addWidget(known)
    qtbot.addWidget(other)

    assert not known.icon().isNull() and known.text() == ""
    assert other.icon().isNull() and other.text() == "?"


def test_disabled_state_uses_a_fainter_color(qtbot):
    button = QPushButton()
    qtbot.addWidget(button)
    set_button_icon(button, "stop")

    assert _solid_color(button.icon().pixmap(20, 20, QIcon.Mode.Normal)).rgb() == QColor(DARK_PALETTE["text"]).rgb()
    assert _solid_color(button.icon().pixmap(20, 20, QIcon.Mode.Disabled)).rgb() == QColor(DARK_PALETTE["text_faint"]).rgb()


def test_accent_buttons_get_a_white_icon(qtbot):
    button = QPushButton()
    button.setProperty("accent", "true")
    qtbot.addWidget(button)

    set_button_icon(button, "play")

    color = _solid_color(button.icon().pixmap(20, 20, QIcon.Mode.Normal))
    assert color.rgb() == QColor(DARK_PALETTE["text_on_accent"]).rgb()


def test_theme_change_recolors_registered_widgets(qtbot):
    button, label, action = QPushButton(), QLabel(), QAction("x")
    qtbot.addWidget(button)
    qtbot.addWidget(label)
    set_button_icon(button, "play")
    set_label_icon(label, "volume")
    set_action_icon(action, "undo")

    set_icon_palette(LIGHT_PALETTE)

    assert _solid_color(button.icon().pixmap(20, 20)).rgb() == QColor(LIGHT_PALETTE["text"]).rgb()
    assert _solid_color(label.pixmap()).rgb() == QColor(LIGHT_PALETTE["text_muted"]).rgb()
    assert _solid_color(action.icon().pixmap(20, 20)).rgb() == QColor(LIGHT_PALETTE["text"]).rgb()


def test_theme_change_ignores_destroyed_widgets(qtbot):
    from shiboken6 import delete

    doomed = QPushButton()
    set_button_icon(doomed, "play")
    delete(doomed)  # objet Qt détruit, wrapper Python encore vivant dans le registre

    set_icon_palette(LIGHT_PALETTE)  # ne doit pas lever « Internal C++ object already deleted »

    assert doomed not in icons._registered


def test_play_pause_toggle_swaps_the_icon(qtbot):
    button = QPushButton()
    qtbot.addWidget(button)
    set_button_icon(button, "play")
    play_image = button.icon().pixmap(20, 20).toImage()

    set_button_icon(button, "pause")

    assert button.icon().pixmap(20, 20).toImage() != play_image
