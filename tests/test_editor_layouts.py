"""Tests des dispositions de la fenêtre principale (préférence, bascule, agencement)."""

import pytest
from PySide6.QtWidgets import QWidget

from app.config import layouts
from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow
from app.ui.selected_sequence_card import SelectedSequenceCard

# Tous les panneaux partagés : chaque disposition doit les poser quelque part, sinon ils se
# retrouveraient sans parent, c'est-à-dire en fenêtres flottantes.
_SHARED_PANELS = (
    "_video_player_panel",
    "_video_panel",
    "_transport_controls",
    "_waveform_overview",
    "_waveform_widget",
    "_selection_card",
    "_silence_card",
    "_sequence_list",
    "_save_state_title",
    "_save_state_hint",
    "_zoom_label",
    "_position_label",
    "_duration_label",
    "_merge_preview_button",
    "_crossfade_spin",
)


@pytest.fixture
def window(qtbot, monkeypatch):
    """Fenêtre principale dont les préférences ne touchent pas le dépôt."""
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.save_layout_preference", lambda name: None)
    monkeypatch.setattr("app.ui.main_window.load_layout_preference", lambda: layouts.DEFAULT_LAYOUT)
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    return window


def _ancestors(widget: QWidget):
    node = widget.parent()
    while node is not None:
        yield node
        node = node.parent()


def _hosting_panel(widget: QWidget) -> str:
    """Nom du panneau (objectName) qui accueille le widget, en remontant ses parents."""
    for node in _ancestors(widget):
        if node.objectName() in {"sidePanel", "centerPanel", "rightPanel", "bottomPanel"}:
            return node.objectName()
    return ""


# --- Préférence ---------------------------------------------------------------------------------


def test_layout_preference_roundtrip(tmp_path):
    store = tmp_path / "layout.json"
    assert layouts.load_layout_preference(store) == layouts.DEFAULT_LAYOUT

    layouts.save_layout_preference("B", store)

    assert layouts.load_layout_preference(store) == "B"


@pytest.mark.parametrize("content", ["pas du json", '{"layout": "Z"}', "[1, 2]"])
def test_invalid_layout_preference_falls_back_to_default(tmp_path, content):
    store = tmp_path / "layout.json"
    store.write_text(content, encoding="utf-8")

    assert layouts.load_layout_preference(store) == layouts.DEFAULT_LAYOUT


def test_next_layout_cycles_through_every_layout():
    seen = []
    name = layouts.DEFAULT_LAYOUT
    for _ in range(len(layouts.LAYOUTS)):
        seen.append(name)
        name = layouts.next_layout(name)

    assert sorted(seen) == sorted(layouts.LAYOUTS)
    assert name == layouts.DEFAULT_LAYOUT  # la roue est bouclée


def test_unknown_layout_falls_back_to_default():
    assert layouts.get_layout("Z") == layouts.DEFAULT_LAYOUT
    assert layouts.get_layout("B") == "B"


def test_the_remembered_layout_is_applied_at_startup(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.load_layout_preference", lambda: "B")
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    assert window._layout_name == "B"
    assert window._layout_actions["B"].isChecked()


def test_switching_layout_is_remembered(window, monkeypatch):
    saved = []
    monkeypatch.setattr("app.ui.main_window.save_layout_preference", saved.append)

    window.apply_layout("B")

    assert saved == ["B"]


# --- Agencement ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(layouts.LAYOUTS))
def test_every_layout_hosts_every_shared_panel(window, name):
    window.apply_layout(name)
    body = window._body_scroller.widget()

    for attribute in _SHARED_PANELS:
        widget = getattr(window, attribute)
        assert body in list(_ancestors(widget)), f"{attribute} n'est posé nulle part en disposition {name}"


def test_switching_back_and_forth_keeps_the_same_panels(window):
    panels = {attribute: getattr(window, attribute) for attribute in _SHARED_PANELS}

    window.apply_layout("B")
    window.apply_layout("A")

    for attribute, widget in panels.items():
        assert getattr(window, attribute) is widget
        assert widget.parent() is not None


def test_layout_a_keeps_the_waveform_in_the_middle_column(window):
    window.apply_layout("A")

    assert _hosting_panel(window._waveform_widget) == "centerPanel"
    assert _hosting_panel(window._sequence_list) == "rightPanel"
    assert _hosting_panel(window._video_player_panel) == "sidePanel"


def test_layout_b_puts_the_waveform_under_the_columns(window):
    window.apply_layout("B")

    assert _hosting_panel(window._waveform_widget) == "bottomPanel"
    assert _hosting_panel(window._selection_card) == "bottomPanel"
    assert _hosting_panel(window._sequence_list) == "sidePanel"
    assert _hosting_panel(window._video_player_panel) == "centerPanel"
    assert _hosting_panel(window._video_panel) == "rightPanel"


def test_layout_b_lets_the_waveform_band_be_resized(window):
    """L'aperçu vidéo occupe toute la largeur centrale : sans poignée il écraserait la waveform."""
    from PySide6.QtWidgets import QSplitter

    window.apply_layout("B")
    splitter = window._body_scroller.widget()

    assert isinstance(splitter, QSplitter)
    assert splitter.count() == 2
    assert not splitter.childrenCollapsible()


def test_the_selected_sequence_card_belongs_to_layout_b_only(window):
    window.apply_layout("B")
    assert isinstance(window._selected_sequence_card, SelectedSequenceCard)

    window.apply_layout("A")
    assert window._selected_sequence_card is None


# --- Commandes ----------------------------------------------------------------------------------


def test_the_toolbar_action_names_the_current_layout(window):
    assert window._layout_action.text() == f"Disposition {layouts.DEFAULT_LAYOUT}"

    window._toggle_layout()

    assert window._layout_name != layouts.DEFAULT_LAYOUT
    assert window._layout_action.text() == f"Disposition {window._layout_name}"


def test_the_view_menu_switches_layout(window):
    window._layout_actions["B"].trigger()

    assert window._layout_name == "B"
    assert window._layout_actions["B"].isChecked()
    assert not window._layout_actions["A"].isChecked()
