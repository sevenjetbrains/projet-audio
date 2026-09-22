"""Les deux agencements de l'éditeur, construits à partir des mêmes widgets.

La fenêtre principale possède ses panneaux une fois pour toutes ; ce module ne fait
que les poser dans un arbre de conteneurs. Changer de disposition revient donc à
rebâtir ce seul arbre : les widgets partagés sont reparentés (leur état, leurs
signaux et la lecture en cours sont conservés) et l'ancien corps, désormais vide,
est jeté.

Contrainte à respecter en ajoutant une disposition : **chaque widget partagé doit
être posé quelque part**. Un widget laissé de côté se retrouverait sans parent,
c'est-à-dire en fenêtre flottante. Le test `test_editor_layouts` monte la garde.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config.layouts import get_layout
from app.ui.design import card_layout, icon_button, label, section_header
from app.ui.selected_sequence_card import SelectedSequenceCard

_WAVEFORM_HINT = "clic = lecture · glisser = sélection"
# Hauteur plancher de la waveform : la disposition B lui donne toute la largeur, autant qu'elle
# y gagne aussi en hauteur, sinon le bandeau du bas se réduit à une ligne de vagues.
_WAVEFORM_MIN_HEIGHT = {"A": 110, "B": 110}


@dataclass(frozen=True)
class EditorWidgets:
    """Les panneaux partagés par les dispositions, tels que la fenêtre les possède."""

    video_player_panel: QWidget
    video_panel: QWidget
    transport_controls: QWidget
    waveform_overview: QWidget
    waveform: QWidget
    selection_card: QWidget
    silence_card: QWidget
    sequence_list: QWidget
    save_state_title: QLabel
    save_state_hint: QLabel
    zoom_label: QWidget
    position_label: QLabel
    duration_label: QLabel
    merge_preview_button: QWidget
    crossfade_spin: QWidget
    processing_action: QAction
    side_width: int
    right_width: int


def build_body(name: str, widgets: EditorWidgets) -> QWidget:
    """Corps de l'éditeur (tout sauf la barre d'outils) dans la disposition demandée."""
    name = get_layout(name)
    widgets.waveform.setMinimumHeight(_WAVEFORM_MIN_HEIGHT[name])
    # En B la waveform est juste sous le lecteur : l'aide « l'image suit la waveform » y est
    # à la fois redondante et coûteuse (deux lignes de hauteur dans une colonne large).
    widgets.video_player_panel.set_hint_visible(name == "A")
    builder: Callable[[EditorWidgets], QWidget] = _BUILDERS[name]
    return builder(widgets)


# --- Briques communes aux deux dispositions ---------------------------------------------------


def _panel(object_name: str, margins: tuple[int, int, int, int], spacing: int) -> tuple[QWidget, QVBoxLayout]:
    panel = QWidget()
    panel.setObjectName(object_name)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return panel, layout


def _save_state_card(widgets: EditorWidgets) -> QWidget:
    card, layout = card_layout("soft", spacing=3, margin=12)
    layout.addWidget(widgets.save_state_title)
    layout.addWidget(widgets.save_state_hint)
    return card


def _transport_card(widgets: EditorWidgets) -> QWidget:
    card, layout = card_layout(spacing=0, margin=0)
    layout.addWidget(widgets.transport_controls)
    return card


def _fusion_row(widgets: EditorWidgets) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(label("Aperçu du montage complet", "hintLabel"))
    row.addStretch(1)
    row.addWidget(widgets.crossfade_spin)
    row.addWidget(widgets.merge_preview_button)
    return row


def _fusion_column(widgets: EditorWidgets) -> QVBoxLayout:
    """Même contenu que `_fusion_row`, empilé : la colonne de droite est trop étroite pour une ligne."""
    column = QVBoxLayout()
    column.setSpacing(6)
    column.addWidget(label("Aperçu du montage complet", "hintLabel"))
    column.addWidget(widgets.crossfade_spin)
    column.addWidget(widgets.merge_preview_button)
    return column


def _waveform_header(widgets: EditorWidgets) -> QHBoxLayout:
    zoom_out_button = icon_button("zoom_out", size=30, flat=True)
    zoom_out_button.clicked.connect(widgets.waveform.zoom_out)
    zoom_out_button.setToolTip("Dézoomer (molette sur la waveform)")
    zoom_in_button = icon_button("zoom_in", size=30, flat=True)
    zoom_in_button.clicked.connect(widgets.waveform.zoom_in)
    zoom_in_button.setToolTip("Zoomer (molette sur la waveform)")

    header = QHBoxLayout()
    header.setSpacing(8)
    header.addWidget(zoom_out_button)
    header.addWidget(widgets.zoom_label)
    header.addWidget(zoom_in_button)
    header.addSpacing(10)
    # Une aide décorative ne doit pas imposer sa largeur à tout le panneau :
    # sur un écran étroit, c'est elle qui cède en premier.
    hint = label(_WAVEFORM_HINT, "hintLabel")
    hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    header.addWidget(hint)
    header.addStretch(1)
    header.addWidget(widgets.position_label)
    header.addWidget(widgets.duration_label)
    return header


def _processing_button(widgets: EditorWidgets) -> QPushButton:
    """Raccourci vers la fenêtre de traitement : il déclenche l'action du menu, sans la doubler."""
    button = QPushButton("Traitement audio…")
    button.setToolTip("Ouvrir la fenêtre de traitement sur la sélection")
    button.clicked.connect(widgets.processing_action.trigger)
    return button


# --- Disposition A : lecteur à gauche, waveform au centre, séquences à droite -------------------


def _build_layout_a(widgets: EditorWidgets) -> QWidget:
    body = QWidget()
    layout = QHBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(_a_side_panel(widgets))
    layout.addWidget(_a_center_panel(widgets), 1)
    layout.addWidget(_a_right_panel(widgets))
    return body


def _a_side_panel(widgets: EditorWidgets) -> QWidget:
    panel, layout = _panel("sidePanel", (16, 14, 16, 14), 14)
    panel.setFixedWidth(widgets.side_width)
    layout.addWidget(widgets.video_player_panel)
    layout.addWidget(section_header("Source"))
    layout.addWidget(widgets.video_panel)
    layout.addStretch(1)
    layout.addWidget(_save_state_card(widgets))
    return panel


def _a_center_panel(widgets: EditorWidgets) -> QWidget:
    panel, layout = _panel("centerPanel", (16, 10, 16, 10), 9)
    layout.addLayout(_waveform_header(widgets))
    layout.addWidget(widgets.waveform_overview)
    layout.addWidget(widgets.waveform, 1)
    layout.addWidget(widgets.selection_card)
    layout.addWidget(widgets.silence_card)
    layout.addLayout(_fusion_row(widgets))
    layout.addWidget(_transport_card(widgets))
    return panel


def _a_right_panel(widgets: EditorWidgets) -> QWidget:
    panel, layout = _panel("rightPanel", (0, 0, 0, 0), 0)
    panel.setFixedWidth(widgets.right_width)
    layout.addWidget(widgets.sequence_list)
    return panel


# --- Disposition B : séquences à gauche, lecteur au centre, waveform pleine largeur -------------


def _build_layout_b(widgets: EditorWidgets) -> QWidget:
    columns = QWidget()
    columns_layout = QHBoxLayout(columns)
    columns_layout.setContentsMargins(0, 0, 0, 0)
    columns_layout.setSpacing(0)
    columns_layout.addWidget(_b_sequences_panel(widgets))
    columns_layout.addWidget(_b_player_panel(widgets), 1)
    columns_layout.addWidget(_b_source_panel(widgets))

    # L'aperçu vidéo occupe toute la largeur centrale : sans poignée, il imposerait sa hauteur
    # (jusqu'à 420 px) au bandeau de la waveform. La séparation se règle donc à la souris.
    body = _EditorSplitter()
    body.addWidget(columns)
    body.addWidget(_b_waveform_dock(widgets))
    # Les colonnes gardent leur hauteur naturelle, la place en plus va à la waveform : c'est
    # elle qu'on est venu chercher dans cette disposition.
    body.setStretchFactor(0, 0)
    body.setStretchFactor(1, 1)
    return body


class _EditorSplitter(QSplitter):
    """Séparation verticale colonnes / waveform, répartie à la première ouverture.

    `setSizes()` à la construction ne sert à rien : le splitter n'a pas encore sa hauteur et Qt
    ramène les valeurs à la taille par défaut. La répartition se fait donc au premier affichage,
    quand la hauteur réelle est connue : les colonnes prennent ce qu'elles demandent, la waveform
    prend le reste (sans descendre sous son minimum).
    """

    def __init__(self) -> None:
        super().__init__(Qt.Orientation.Vertical)
        self.setObjectName("editorSplitter")
        self.setChildrenCollapsible(False)
        self._balanced = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._balanced or self.count() != 2:
            return
        self._balanced = True
        total = self.height() - self.handleWidth()
        columns = self.widget(0).sizeHint().height()
        dock = max(total - columns, self.widget(1).minimumSizeHint().height())
        self.setSizes([max(total - dock, self.widget(0).minimumSizeHint().height()), dock])


def _b_sequences_panel(widgets: EditorWidgets) -> QWidget:
    panel, layout = _panel("sidePanel", (0, 0, 0, 0), 0)
    panel.setFixedWidth(widgets.side_width)
    layout.addWidget(widgets.sequence_list)
    return panel


def _b_player_panel(widgets: EditorWidgets) -> QWidget:
    """Colonne du lecteur. Elle défile pour elle-même, comme la colonne de droite : sur une
    fenêtre basse, c'est elle qui se resserre, et jamais le bandeau de la waveform qui disparaît."""
    panel, layout = _panel("centerPanel", (16, 10, 16, 10), 9)
    layout.addWidget(widgets.video_player_panel, 1)
    layout.addWidget(_transport_card(widgets))
    return _scrollable_column(panel)


def _b_source_panel(widgets: EditorWidgets) -> QWidget:
    """Colonne « inspecteur » : la source, la séquence sélectionnée, le traitement et la fusion.

    Elle défile pour elle-même : sans cela, sa hauteur s'imposerait au corps de l'éditeur et
    repousserait le bandeau de la waveform hors de l'écran sur une fenêtre un peu basse.
    """
    panel, layout = _panel("rightPanel", (16, 14, 16, 14), 12)
    layout.addWidget(section_header("Source"))
    layout.addWidget(widgets.video_panel)
    layout.addWidget(section_header("Séquence sélectionnée"))
    layout.addWidget(SelectedSequenceCard())
    layout.addWidget(_processing_button(widgets))
    layout.addLayout(_fusion_column(widgets))
    layout.addStretch(1)
    layout.addWidget(_save_state_card(widgets))
    return _scrollable_column(panel, widgets.right_width)


def _scrollable_column(panel: QWidget, width: int | None = None) -> QScrollArea:
    """Colonne qui défile verticalement, sans cadre ni défilement horizontal.

    Sans cela, la plus haute des trois colonnes imposerait sa hauteur au corps de l'éditeur et
    repousserait le bandeau de la waveform hors de l'écran sur une fenêtre un peu basse.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    if width is not None:
        area.setFixedWidth(width)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(panel)
    return area


def _b_waveform_dock(widgets: EditorWidgets) -> QWidget:
    panel, layout = _panel("bottomPanel", (16, 10, 16, 12), 9)
    layout.addLayout(_waveform_header(widgets))
    layout.addWidget(widgets.waveform_overview)
    layout.addWidget(widgets.waveform, 1)
    # Les deux cartes côte à côte : le découpage par silences a besoin de largeur pour ses quatre
    # réglages, et la pleine largeur du bandeau la lui donne sans coûter une ligne de hauteur.
    tools = QHBoxLayout()
    tools.setSpacing(12)
    tools.addWidget(widgets.selection_card, 3)
    tools.addWidget(widgets.silence_card, 2)
    layout.addLayout(tools)
    return panel


_BUILDERS: dict[str, Callable[[EditorWidgets], QWidget]] = {
    "A": _build_layout_a,
    "B": _build_layout_b,
}
