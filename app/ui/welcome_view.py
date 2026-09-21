"""Écran d'accueil : ce que la fenêtre montre tant qu'aucun projet n'est ouvert.

Il reprend les deux entrées de l'application (importer une vidéo, ouvrir un projet), la
zone de dépôt, les projets récents, et sert aussi de support aux deux évènements qui ne
peuvent survenir que là : la proposition de récupérer une sauvegarde automatique et la
progression de l'extraction audio (avec son annulation).
"""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import SUPPORTED_VIDEO_FORMATS
from app.services.recent_projects import RecentProject
from app.ui.design import badge, card_layout, kbd, label, labelled_icon_button, section_label
from app.ui.icons import set_label_icon
from app.utils.date_utils import format_elapsed, format_folder, format_moment

# Même largeur que le panneau gauche de l'éditeur ; le pied de page (« Raccourcis : … ») y tient
# tout juste, une colonne plus étroite le tronquerait. Sur un écran étroit, la colonne cède
# quand même : mieux vaut un pied de page serré qu'une colonne moitié hors de l'écran.
_SIDE_WIDTH = 410
_SIDE_MIN_WIDTH = 260
_TITLE = "Découpez et nettoyez l'audio d'une vidéo"
_INTRO = (
    "Importez une vidéo : AudioCut Studio en extrait la piste audio, vous la découpez en séquences, "
    "vous les nettoyez, puis vous exportez. Le fichier vidéo d'origine n'est jamais modifié."
)
_EXTRACTION_HINT = (
    "Lecture des métadonnées, puis extraction de la piste audio complète. "
    "Vous pouvez annuler à tout moment."
)
_SHORTCUTS = (("Ctrl+O", "importer"), ("Ctrl+S", "enregistrer"), ("F1", "aide"))


def _sequence_count_text(count: int) -> str:
    return f"{count} séquence{'s' if count > 1 else ''}"


class RecentProjectCard(QFrame):
    """Vignette cliquable d'un projet récent : nom, contenu, date et dossier."""

    clicked = Signal(str)

    def __init__(self, info: RecentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = info.path
        self.setProperty("card", "recent")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # sans quoi le `:hover` de la feuille de style dort
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(info.path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        layout.addWidget(label(info.file_name, "recentName"))
        layout.addWidget(label(f"{_sequence_count_text(info.sequence_count)} · {format_moment(info.modified_at)}"))
        layout.addWidget(label(format_folder(info.path), "pathLabel"))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._path)
        super().mouseReleaseEvent(event)


class WelcomeView(QWidget):
    import_requested = Signal()
    open_project_requested = Signal()
    recent_project_chosen = Signal(str)
    autosave_recovery_requested = Signal()
    autosave_dismissed = Signal()
    import_cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("welcomePanel")

        self._drop_zone = self._build_drop_zone()
        self._autosave_card = self._build_autosave_card()
        self._recent_cards: list[RecentProjectCard] = []
        self._recent_container = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_container)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(10)
        self._recent_empty = label("Aucun projet ouvert récemment.", "hintLabel")
        self._recent_empty.setWordWrap(True)
        self._recent_layout.addWidget(self._recent_empty)
        self._progress_card = self._build_progress_card()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_hero(), 1)
        layout.addWidget(self._build_side())

    # --- Colonne principale ---------------------------------------------------

    def _build_hero(self) -> QWidget:
        title = label(_TITLE, "heroTitle")
        title.setWordWrap(True)
        intro = label(_INTRO, "heroText")
        intro.setWordWrap(True)
        intro.setMaximumWidth(940)
        # Un paragraphe replié peut se resserrer autant qu'il faut : c'est la zone de dépôt,
        # pas le texte, qui fixe la largeur utile de la colonne.
        intro.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 36, 32, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addSpacing(8)
        layout.addWidget(self._drop_zone, 1)
        layout.addWidget(self._autosave_card)
        return panel

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setObjectName("dropZone")
        zone.setProperty("hover", "false")

        icon_tile = QLabel()
        icon_tile.setFixedSize(72, 72)
        icon_tile.setObjectName("dropIcon")
        icon_tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_label_icon(icon_tile, "upload", size=30)

        subtitle = QHBoxLayout()
        subtitle.setSpacing(6)
        subtitle.addStretch(1)
        subtitle.addWidget(label("ou un fichier projet", "hintLabel"))
        subtitle.addWidget(kbd(".acsproject"))
        subtitle.addStretch(1)

        self._import_button = labelled_icon_button("Importer une vidéo…", "folder", accent=True)
        self._import_button.clicked.connect(self.import_requested.emit)
        self._open_button = QPushButton("Ouvrir un projet…")
        self._open_button.clicked.connect(self.open_project_requested.emit)
        for button in (self._import_button, self._open_button):
            button.setMinimumHeight(38)
            # Largeur confortable, mais qui cède sur un écran étroit plutôt que de pousser
            # la colonne des projets récents hors de la fenêtre.
            button.setMinimumWidth(140)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)
        buttons.addWidget(self._import_button)
        buttons.addWidget(self._open_button)
        buttons.addStretch(1)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addStretch(1)
        for extension in SUPPORTED_VIDEO_FORMATS:
            chips.addWidget(badge(extension.lstrip(".").upper().replace("WEBM", "WebM")))
        chips.addStretch(1)

        layout = QVBoxLayout(zone)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(12)
        layout.addStretch(1)
        layout.addWidget(icon_tile, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        layout.addWidget(label("Glissez une vidéo ici", "dropTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(subtitle)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addSpacing(6)
        layout.addLayout(chips)
        layout.addStretch(1)
        return zone

    def _build_autosave_card(self) -> QFrame:
        card, layout = card_layout("warning", spacing=0, margin=14)
        layout.setDirection(QVBoxLayout.Direction.LeftToRight)

        icon = QLabel()
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        set_label_icon(icon, "alert", size=22)

        self._autosave_title = label("Une sauvegarde automatique a été trouvée", "warningTitle")
        self._autosave_detail = label("", "hintLabel")
        self._autosave_detail.setWordWrap(True)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(self._autosave_title)
        texts.addWidget(self._autosave_detail)

        recover = QPushButton("Récupérer")
        recover.setProperty("warning", "true")
        recover.clicked.connect(self.autosave_recovery_requested.emit)
        ignore = QPushButton("Ignorer")
        ignore.clicked.connect(self.autosave_dismissed.emit)

        layout.addWidget(icon)
        layout.addSpacing(6)
        layout.addLayout(texts, 1)
        layout.addSpacing(12)
        layout.addWidget(recover)
        layout.addWidget(ignore)
        card.hide()
        return card

    # --- Colonne des projets récents ------------------------------------------

    def _build_progress_card(self) -> QFrame:
        card, layout = card_layout(spacing=8, margin=14)

        self._progress_percent = label("0 %", "accentValue")
        header = QHBoxLayout()
        header.addWidget(label("Analyse en cours", "warningTitle"))
        header.addStretch(1)
        header.addWidget(self._progress_percent)

        self._progress_name = label("", "hintLabel")
        self._progress_name.setWordWrap(True)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)

        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.import_cancel_requested.emit)
        cancel_row = QHBoxLayout()
        cancel_row.addWidget(cancel)
        cancel_row.addStretch(1)

        hint = label(_EXTRACTION_HINT, "hintLabel")
        hint.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self._progress_name)
        layout.addWidget(self._progress_bar)
        layout.addWidget(hint)
        layout.addLayout(cancel_row)
        card.hide()
        return card

    def _build_shortcuts_footer(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(label("Raccourcis :", "footerHint"))
        for index, (key, description) in enumerate(_SHORTCUTS):
            if index:
                layout.addWidget(label("·", "footerHint"))
            layout.addWidget(kbd(key))
            last = index == len(_SHORTCUTS) - 1
            layout.addWidget(label(description + ("." if last else ""), "footerHint"))
        layout.addStretch(1)
        return row

    def _build_side(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("welcomeSide")
        # Largeur de départ au minimum : c'est `resizeEvent` qui l'élargit dès que la page
        # est affichée. Poser 410 ici en ferait le minimum de toute la page d'accueil.
        panel.setFixedWidth(_SIDE_MIN_WIDTH)
        self._side_panel = panel
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(section_label("Projets récents"))
        layout.addWidget(self._recent_container)
        layout.addWidget(self._progress_card)
        layout.addStretch(1)
        layout.addWidget(self._build_shortcuts_footer())
        return panel

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # La colonne suit la largeur réelle de la page, jamais une estimation de l'écran :
        # c'est la seule mesure fiable quand l'affichage est à une échelle autre que 100 %.
        # Plafonnée au tiers, sinon il ne reste plus assez de place à la zone de dépôt.
        self._side_panel.setFixedWidth(min(_SIDE_WIDTH, max(_SIDE_MIN_WIDTH, self.width() // 3)))

    # --- API ------------------------------------------------------------------

    def set_recent_projects(self, projects: list[RecentProject]) -> None:
        for card in self._recent_cards:
            # setParent(None) détache tout de suite : deleteLater seul laisserait les anciennes
            # vignettes dans l'arbre (et à l'écran) jusqu'au prochain tour de boucle Qt.
            card.setParent(None)
            card.deleteLater()
        self._recent_cards = []

        for info in projects:
            card = RecentProjectCard(info)
            card.clicked.connect(self.recent_project_chosen.emit)
            self._recent_layout.addWidget(card)
            self._recent_cards.append(card)
        self._recent_empty.setVisible(not projects)

    def show_autosave_offer(self, project_name: str, saved_at: datetime) -> None:
        """Bandeau « une sauvegarde automatique a été trouvée », à la place d'une boîte modale."""
        self._autosave_detail.setText(
            f"« {project_name} » — enregistrée {format_elapsed(saved_at)}, après une fermeture inattendue."
        )
        self._autosave_card.show()

    def hide_autosave_offer(self) -> None:
        self._autosave_card.hide()

    def start_import_progress(self, file_name: str) -> None:
        self._progress_name.setText(file_name)
        self.set_import_progress(0)
        self._progress_card.show()

    def set_import_progress(self, percent: int) -> None:
        self._progress_bar.setValue(percent)
        self._progress_percent.setText(f"{percent} %")

    def hide_import_progress(self) -> None:
        self._progress_card.hide()

    @property
    def import_in_progress(self) -> bool:
        # isVisibleTo : l'état propre de la carte, que l'écran d'accueil soit affiché ou non.
        return self._progress_card.isVisibleTo(self)

    def set_drop_active(self, active: bool) -> None:
        """Met la zone de dépôt en évidence pendant qu'un fichier survole la fenêtre."""
        self._drop_zone.setProperty("hover", "true" if active else "false")
        self._drop_zone.style().unpolish(self._drop_zone)
        self._drop_zone.style().polish(self._drop_zone)
