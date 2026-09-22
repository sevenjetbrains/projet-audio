"""Tests des dispositions de la fenêtre principale (préférence, bascule, agencement)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

from app.config import layouts
from app.config.settings import find_ffmpeg_binaries
from app.ui.editor_layouts import CENTER_PANEL_MIN_WIDTH, RIGHT_PANEL_MIN_WIDTH, SIDE_PANEL_MIN_WIDTH
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
    window.apply_layout("B")
    splitter = window._body_scroller.widget()

    assert isinstance(splitter, QSplitter)
    assert splitter.count() == 2
    assert not splitter.childrenCollapsible()


# --- Poignées de redimensionnement (chaque panneau s'ajuste à la souris) ------------------------


@pytest.mark.parametrize("name", list(layouts.LAYOUTS))
def test_layout_columns_form_a_resizable_splitter(window, name):
    row = _column_row(window, name)

    assert isinstance(row, QSplitter)
    assert row.orientation() == Qt.Orientation.Horizontal
    assert row.count() == 3
    assert not row.childrenCollapsible()


@pytest.mark.parametrize("name", list(layouts.LAYOUTS))
def test_side_and_right_panels_have_a_floor_but_no_fixed_ceiling(window, name):
    """Avant : `setFixedWidth` empêchait tout redimensionnement. Un plancher (`setMinimumWidth`)
    garde les panneaux lisibles sans empêcher l'utilisateur de les agrandir."""
    row = _column_row(window, name)

    side, right = row.widget(0), row.widget(2)

    assert side.minimumWidth() == SIDE_PANEL_MIN_WIDTH
    assert right.minimumWidth() == RIGHT_PANEL_MIN_WIDTH
    # Qt renvoie 16777215 (QWIDGETSIZE_MAX) tant qu'aucune largeur maximale n'a été fixée.
    assert side.maximumWidth() > SIDE_PANEL_MIN_WIDTH * 10
    assert right.maximumWidth() > RIGHT_PANEL_MIN_WIDTH * 10


def test_layout_a_center_panel_keeps_its_minimum_width(window):
    row = _column_row(window, "A")

    assert row.widget(1).minimumWidth() == CENTER_PANEL_MIN_WIDTH


def _column_row(window, name: str) -> QSplitter:
    """Splitter horizontal portant les trois colonnes (le corps lui-même en A, son premier
    enfant en B, où le corps sépare verticalement les colonnes du bandeau de la waveform)."""
    window.apply_layout(name)
    body = window._body_scroller.widget()
    return body if name == "A" else body.widget(0)


def _shown_column_row(qtbot, window, name: str) -> QSplitter:
    """Comme `_column_row`, mais avec l'éditeur réellement affiché : la répartition initiale des
    tailles n'a lieu qu'au premier `showEvent`, jamais reçu tant que la page reste sur l'accueil."""
    row = _column_row(window, name)
    window._pages.setCurrentIndex(1)  # bascule vers la page éditeur (l'accueil est affiché par défaut)
    window.resize(1600, 900)
    window.show()
    qtbot.waitExposed(window)
    return row


@pytest.mark.parametrize("name", list(layouts.LAYOUTS))
def test_dragging_a_handle_resizes_the_side_panel(qtbot, window, name):
    """Simule un glissement de poignée (`QSplitter.setSizes`, ce que fait un vrai glissement) et
    vérifie que le panneau prend bien la largeur demandée, au lieu de rester figé."""
    row = _shown_column_row(qtbot, window, name)
    before = row.sizes()
    assert before[0] > SIDE_PANEL_MIN_WIDTH  # la colonne démarre plus large que son plancher

    grown = SIDE_PANEL_MIN_WIDTH + 120
    shrink_center = before[1] - (grown - before[0])
    row.setSizes([grown, max(shrink_center, 1), before[2]])

    assert row.sizes()[0] == grown
    assert row.widget(0).width() == grown

    row.setSizes([SIDE_PANEL_MIN_WIDTH, before[1] + (before[0] - SIDE_PANEL_MIN_WIDTH), before[2]])
    assert row.sizes()[0] == SIDE_PANEL_MIN_WIDTH  # peut aussi être resserrée, jusqu'à son plancher


def test_a_handle_cannot_shrink_a_panel_below_its_floor(qtbot, window):
    """`setChildrenCollapsible(False)` + `setMinimumWidth` : la poignée ne peut pas faire
    disparaître un panneau, ni le réduire sous sa largeur minimale."""
    row = _shown_column_row(qtbot, window, "A")

    row.setSizes([0, 1600, 0])  # tentative de tout donner à la colonne centrale

    assert row.sizes()[0] >= SIDE_PANEL_MIN_WIDTH
    assert row.sizes()[2] >= RIGHT_PANEL_MIN_WIDTH


def test_layout_a_starts_at_the_preferred_column_widths(qtbot, window):
    row = _shown_column_row(qtbot, window, "A")

    assert row.sizes()[0] == window._side_width
    assert row.sizes()[2] == window._right_width


def test_layout_b_columns_start_at_the_preferred_widths(qtbot, window):
    row = _shown_column_row(qtbot, window, "B")

    assert row.sizes()[0] == window._side_width
    assert row.sizes()[2] == window._right_width


@pytest.mark.parametrize("name", list(layouts.LAYOUTS))
def test_no_layout_pushes_its_content_out_of_a_normal_window(window, name):
    """Garde-fou : une colonne trop haute repousserait la waveform sous la ligne de flottaison.

    Constaté sur une fenêtre de 814 px : le bandeau du bas n'était plus atteignable qu'en
    faisant défiler tout l'éditeur. Les colonnes défilent donc pour elles-mêmes.
    """
    window.apply_layout(name)

    assert window._body_scroller.widget().minimumSizeHint().height() <= 620


def test_layout_b_hides_the_player_hint_that_layout_a_shows(window):
    """En B la waveform est juste sous le lecteur : l'aide « l'image suit la waveform » y est
    redondante, et elle coûte deux lignes de hauteur dans une colonne large."""
    hint = window._video_player_panel._hint_label

    window.apply_layout("A")
    assert hint.isVisibleTo(window._video_player_panel)

    window.apply_layout("B")
    assert not hint.isVisibleTo(window._video_player_panel)


def test_the_silence_card_sits_beside_the_selection_card_in_layout_b(window):
    """Ses quatre réglages ne tiennent pas dans une colonne de 360 px : il lui faut la largeur du bandeau."""
    window.apply_layout("B")

    assert _hosting_panel(window._silence_card) == "bottomPanel"


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
