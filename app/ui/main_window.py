"""Fenêtre principale d'AudioCut Studio.

Disposition en trois colonnes : lecteur vidéo et source à gauche, waveform et
outils de découpage au centre, liste des séquences à droite.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME, SUPPORTED_VIDEO_FORMATS
from app.config.settings import FFmpegBinaries
from app.config.themes import THEMES, get_theme, load_stylesheet, load_theme_preference, save_theme_preference
from app.services import marker_service
from app.services.export_service import ExportError, merge_sequences
from app.services.project_service import (
    PROJECT_FILE_EXTENSION,
    autosave_project,
    describe_autosave,
    find_recoverable_autosaves,
    load_project,
    save_project,
)
from app.services.recent_projects import add_recent_project, describe_recent_projects, load_recent_projects
from app.services.preview_proxy import build_preview_proxy, needs_preview_proxy
from app.services.sequence_service import create_sequences_from_ranges, detect_speech_ranges
from app.ui.app_toolbar import AppToolBar
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.auto_split_dialog import AutoSplitDialog
from app.ui.design import card_layout, flat_button, icon_button, label, section_header
from app.ui.export_dialog import ExportDialog
from app.ui.icons import set_icon_palette
from app.ui.processing_dialog import ProcessingDialog
from app.ui.selection_card import SelectionCard
from app.ui.sequence_list import SequenceListWidget
from app.ui.shortcuts import set_button_shortcut, shortcuts_help_html
from app.ui.silence_split_card import SilenceSplitCard
from app.ui.split_preview_dialog import SplitPreviewDialog
from app.ui.transport_controls import TransportControls
from app.ui.undo_commands import CallbackCommand
from app.ui.video_panel import VideoPanel
from app.ui.video_player_panel import VideoPlayerPanel
from app.ui.video_preview import VideoPreview
from app.ui.waveform_overview import WaveformOverview
from app.ui.waveform_widget import WaveformWidget
from app.ui.welcome_view import WelcomeView
from app.utils.time_utils import format_timecode, format_timecode_fr
from app.workers.ffmpeg_worker import FFmpegTaskWorker

_SIDE_PANEL_WIDTH = 410
_RIGHT_PANEL_WIDTH = 360
_AUTOSAVE_INTERVAL_MS = 2 * 60 * 1000
_SAVE_STATE_REFRESH_MS = 30 * 1000
_WAVEFORM_HINT = "clic = lecture · glisser = sélection"
_EMPTY_SUMMARY = "0 séquence · aucune durée estimée"
# Menus sans objet tant qu'aucun projet n'est ouvert (grisés sur l'écran d'accueil).
_PROJECT_MENUS = ("Édition", "Séquences", "Traitement")
# Saisie d'un repère à la tête de lecture : quelques pixels à l'écran, jamais moins d'un quart de seconde.
_MARKER_PICK_PIXELS = 6
_MARKER_PICK_SECONDS = 0.25


class MainWindow(QMainWindow):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setAcceptDrops(True)

        self._video_panel = VideoPanel(ffmpeg_binaries)
        self._welcome_view = WelcomeView()
        self._video_preview = VideoPreview()
        self._waveform_widget = WaveformWidget()
        self._waveform_overview = WaveformOverview()
        self._transport_controls = TransportControls()
        self._transport_controls.set_video_output(self._video_preview.video_widget)
        self._video_player_panel = VideoPlayerPanel(self._transport_controls, self._video_preview)
        self._video_panel.set_import_guard(self._confirm_discard_changes)
        self._sequence_list = SequenceListWidget(self._video_panel.ffmpeg_service)
        self._audio_processing_panel = AudioProcessingPanel(self._video_panel.ffmpeg_service)
        self._audio_processing_panel.set_undo_stack(self._sequence_list.undo_stack)
        self._processing_dialog = ProcessingDialog(self._audio_processing_panel, self)

        self._selection_card = SelectionCard()
        self._selection_start_spin = self._selection_card.start_spin
        self._selection_end_spin = self._selection_card.end_spin
        self._create_sequence_button = self._selection_card.create_button
        self._silence_card = SilenceSplitCard()

        self._merge_preview_button = flat_button("Fusionner et prévisualiser")
        self._merge_preview_button.clicked.connect(self._on_merge_preview_clicked)
        set_button_shortcut(self._merge_preview_button, "Ctrl+M", "Fusionner et prévisualiser")

        self._crossfade_spin = QDoubleSpinBox()
        self._crossfade_spin.setRange(0.0, 5.0)
        self._crossfade_spin.setSingleStep(0.1)
        self._crossfade_spin.setSuffix(" s")
        self._crossfade_spin.setPrefix("Crossfade : ")
        self._crossfade_spin.setToolTip("Fondu enchaîné appliqué entre deux séquences à la fusion")
        self._crossfade_spin.valueChanged.connect(self._on_crossfade_changed)

        self._zoom_label = flat_button("× 1,0")
        self._zoom_label.setToolTip("Réafficher tout le fichier")
        self._zoom_label.clicked.connect(self._waveform_widget.reset_zoom)
        self._position_label = label(format_timecode_fr(0.0), "timecodeLabel")
        self._duration_label = label(f"/ {format_timecode_fr(0.0)}", "timecodeTotalLabel")

        self._last_autosave: datetime | None = None
        self._save_state_title = label("Projet à jour", "titleLabel")
        self._save_state_hint = label("Aucune modification en attente.", "hintLabel")

        self._source_duration = 0.0
        self._playback_offset: float | None = 0.0
        self._editing_sequence_id: str | None = None
        self._playing_sequence_id: str | None = None  # séquence chargée dans le lecteur (comparaison A/B)
        self._preview_proxy_path = ""
        self._proxy_worker = None
        # La source est lue depuis le fichier vidéo (image + son synchronisés) ; si Qt ne sait pas
        # le décoder, on bascule une seule fois sur le WAV extrait par FFmpeg.
        self._video_playback_failed = False
        self._dirty = False
        self._pending_autosave = None

        self._build_actions()
        self.setCentralWidget(self._build_central_widget())
        self._build_menus()
        self._build_status_bar()
        self._wire_signals()
        self._register_shortcuts()

        self._update_project_summary()
        self._update_window_title()
        self._update_save_state()
        self._update_project_menus()
        self._show_welcome()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(_AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._on_autosave_tick)
        self._autosave_timer.start()

        self._save_state_timer = QTimer(self)
        self._save_state_timer.setInterval(_SAVE_STATE_REFRESH_MS)
        self._save_state_timer.timeout.connect(self._update_save_state)
        self._save_state_timer.start()

        QTimer.singleShot(0, self._check_for_recoverable_autosave)

    # --- Actions ------------------------------------------------------------

    def _build_actions(self) -> None:
        """Toutes les commandes de l'application, partagées entre menus et barre d'outils."""
        self._import_action = self._action("Importer une vidéo…", "Ctrl+O", self._video_panel.trigger_import, "Importer")
        self._save_action = self._action("Enregistrer le projet…", "Ctrl+S", self._on_save_project_clicked, "Enregistrer")
        self._open_action = self._action("Ouvrir un projet…", "Ctrl+Shift+O", self._on_open_project_clicked)
        self._export_action = self._action("Exporter…", "Ctrl+E", self._on_export_clicked, "Fusionner && exporter")
        self._export_action.setProperty("accent", "true")

        self._undo_action = self._sequence_list.undo_stack.createUndoAction(self, "Annuler")
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._undo_action.setProperty("toolbar_icon", "undo")
        self._redo_action = self._sequence_list.undo_stack.createRedoAction(self, "Refaire")
        self._redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self._redo_action.setProperty("toolbar_icon", "redo")

        # Sans raccourci : les boutons de la fenêtre portent déjà ceux de leurs commandes.
        self._auto_split_action = self._action(
            "Découper automatiquement selon les silences…", None, self._on_auto_split_clicked, "Découpage auto"
        )
        self._markers_to_sequences_action = self._action(
            "Créer les séquences depuis les repères…", None, self._on_create_sequences_from_markers
        )
        self._merge_action = self._action("Fusionner et prévisualiser", None, self._on_merge_preview_clicked)
        self._processing_action = self._action(
            "Appliquer un traitement…", None, self._open_processing_dialog, "Traitement"
        )
        self._theme_toggle_action = self._action("Changer de thème", None, self._toggle_theme)
        self._theme_toggle_action.setProperty("toolbar_icon", "moon")
        self._shortcuts_action = self._action("Raccourcis clavier", "F1", self._show_shortcuts_help, "F1 Aide")

    def _action(self, text: str, shortcut: str | None, slot, toolbar_label: str | None = None) -> QAction:
        """Crée une QAction ; `toolbar_label` est le libellé court utilisé par la barre d'outils."""
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        if toolbar_label:
            action.setProperty("toolbar_label", toolbar_label)
        return action

    # --- Construction de l'interface ---------------------------------------

    def _build_central_widget(self) -> QWidget:
        """Deux pages : l'accueil tant qu'aucun projet n'est ouvert, puis l'éditeur."""
        self._pages = QStackedWidget()
        self._pages.addWidget(self._welcome_view)
        self._pages.addWidget(self._build_editor())
        return self._pages

    def _build_editor(self) -> QWidget:
        toolbar = AppToolBar(
            groups=(
                (self._import_action, self._save_action),
                (self._undo_action, self._redo_action),
                (self._auto_split_action, self._processing_action, self._export_action),
            ),
            trailing=(self._theme_toggle_action, self._shortcuts_action),
        )

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_side_panel())
        body.addWidget(self._build_center_panel(), 1)
        body.addWidget(self._build_right_panel())

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addLayout(body, 1)
        return central

    def _build_side_panel(self) -> QWidget:
        save_state_card, save_state_layout = card_layout("soft", spacing=3, margin=12)
        save_state_layout.addWidget(self._save_state_title)
        save_state_layout.addWidget(self._save_state_hint)

        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(_SIDE_PANEL_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(self._video_player_panel)
        layout.addWidget(section_header("Source"))
        layout.addWidget(self._video_panel)
        layout.addStretch(1)
        layout.addWidget(save_state_card)
        return panel

    def _build_waveform_header(self) -> QHBoxLayout:
        zoom_out_button = icon_button("zoom_out", size=30, flat=True)
        zoom_out_button.clicked.connect(self._waveform_widget.zoom_out)
        zoom_out_button.setToolTip("Dézoomer (molette sur la waveform)")
        zoom_in_button = icon_button("zoom_in", size=30, flat=True)
        zoom_in_button.clicked.connect(self._waveform_widget.zoom_in)
        zoom_in_button.setToolTip("Zoomer (molette sur la waveform)")

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(zoom_out_button)
        header.addWidget(self._zoom_label)
        header.addWidget(zoom_in_button)
        header.addSpacing(10)
        header.addWidget(label(_WAVEFORM_HINT, "hintLabel"))
        header.addStretch(1)
        header.addWidget(self._position_label)
        header.addWidget(self._duration_label)
        return header

    def _build_center_panel(self) -> QWidget:
        fusion_row = QHBoxLayout()
        fusion_row.setSpacing(8)
        fusion_row.addWidget(label("Aperçu du montage complet", "hintLabel"))
        fusion_row.addStretch(1)
        fusion_row.addWidget(self._crossfade_spin)
        fusion_row.addWidget(self._merge_preview_button)

        transport_card, transport_layout = card_layout(spacing=0, margin=0)
        transport_layout.addWidget(self._transport_controls)

        panel = QWidget()
        panel.setObjectName("centerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        layout.addLayout(self._build_waveform_header())
        layout.addWidget(self._waveform_overview)
        layout.addWidget(self._waveform_widget, 1)
        layout.addWidget(self._selection_card)
        layout.addWidget(self._silence_card)
        layout.addLayout(fusion_row)
        layout.addWidget(transport_card)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel.setFixedWidth(_RIGHT_PANEL_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._sequence_list)
        return panel

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Fichier")
        file_menu.addAction(self._import_action)
        file_menu.addSeparator()
        file_menu.addAction(self._open_action)
        self._recent_menu = file_menu.addMenu("Projets récents")
        self._recent_menu.aboutToShow.connect(self._populate_recent_menu)
        file_menu.addAction(self._save_action)
        file_menu.addSeparator()
        file_menu.addAction(self._export_action)

        edit_menu = menu_bar.addMenu("Édition")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)

        sequences_menu = menu_bar.addMenu("Séquences")
        sequences_menu.addAction(self._auto_split_action)
        sequences_menu.addAction(self._markers_to_sequences_action)
        sequences_menu.addAction(self._merge_action)

        processing_menu = menu_bar.addMenu("Traitement")
        processing_menu.addAction(self._processing_action)

        self._build_theme_menu()
        self._build_help_menu()
        self._build_title_bar_widgets()

    def _build_title_bar_widgets(self) -> None:
        """Nom de l'application à gauche des menus, nom du projet à droite (comme la maquette)."""
        # Références conservées : la barre de menus reparente ces widgets sans que PySide le sache, et un
        # QLabel local serait détruit à la sortie de la fonction (le titre n'apparaîtrait alors jamais).
        self._app_title_label = label(APP_NAME, "appTitle")
        self._app_title_label.setContentsMargins(12, 0, 10, 0)
        self._project_name_label = label("", "projectName")
        self._project_name_label.setContentsMargins(0, 0, 12, 0)
        self.menuBar().setCornerWidget(self._app_title_label, Qt.Corner.TopLeftCorner)
        self.menuBar().setCornerWidget(self._project_name_label, Qt.Corner.TopRightCorner)

    def _build_help_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Aide")
        help_menu.addAction(self._shortcuts_action)

    def _build_theme_menu(self) -> None:
        view_menu = self.menuBar().addMenu("Affichage")
        theme_menu = view_menu.addMenu("Thème")
        group = QActionGroup(self)
        group.setExclusive(True)
        current = get_theme(load_theme_preference()).name
        self._theme_actions: dict[str, QAction] = {}
        for name in THEMES:
            action = theme_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(lambda _checked=False, n=name: self.apply_theme(n))
            group.addAction(action)
            self._theme_actions[name] = action
        self._apply_theme_to_painted_widgets(get_theme(current))

    def _build_status_bar(self) -> None:
        self._project_summary_label = QLabel()
        version = self._video_panel.ffmpeg_service.version()
        self._status_hint_label = label(
            f"FFmpeg détecté · version {version}" if version else "FFmpeg détecté", "hintLabel"
        )
        self.statusBar().addPermanentWidget(self._project_summary_label, 1)
        self.statusBar().addPermanentWidget(self._status_hint_label)

    def _register_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_I), self, activated=self._mark_selection_start)
        QShortcut(QKeySequence(Qt.Key.Key_O), self, activated=self._mark_selection_end)
        QShortcut(QKeySequence("Shift+Space"), self, activated=self._listen_to_selection)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, activated=self._add_marker_at_playhead)
        QShortcut(QKeySequence("Shift+M"), self, activated=self._remove_marker_at_playhead)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self._go_to_previous_marker)
        QShortcut(QKeySequence("Alt+Down"), self, activated=self._go_to_next_marker)
        QShortcut(QKeySequence("Alt+S"), self, activated=self._select_between_markers)
        QShortcut(QKeySequence(Qt.Key.Key_L), self, activated=self._selection_card.loop_button.toggle)
        for key in (Qt.Key.Key_F, Qt.Key.Key_F11):
            QShortcut(QKeySequence(key), self, activated=self._video_player_panel.toggle_fullscreen)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._on_create_sequence_clicked)

    # --- Thème --------------------------------------------------------------

    def apply_theme(self, name: str) -> None:
        """Applique le thème à toute l'application et le mémorise pour le prochain lancement."""
        theme = get_theme(name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(load_stylesheet(theme))
        self._apply_theme_to_painted_widgets(theme)
        save_theme_preference(theme.name)

    def _apply_theme_to_painted_widgets(self, theme) -> None:
        """Répercute le thème sur les widgets dessinés au QPainter, hors feuille de style."""
        set_icon_palette(theme.palette)
        self._waveform_widget.set_theme(theme)
        self._waveform_overview.set_theme(theme)
        self._sequence_list.set_theme(theme)

    def _toggle_theme(self) -> None:
        """Bascule entre les deux thèmes depuis la barre d'outils."""
        names = list(THEMES)
        current = get_theme(load_theme_preference()).name
        target = names[(names.index(current) + 1) % len(names)]
        self.apply_theme(target)
        action = self._theme_actions.get(target)
        if action is not None:
            action.setChecked(True)

    def _show_shortcuts_help(self) -> None:
        QMessageBox.information(self, "Raccourcis clavier", shortcuts_help_html())

    # --- Glisser-déposer -----------------------------------------------------

    @staticmethod
    def _dropped_path(mime_data) -> tuple[str, str] | None:
        """Premier fichier déposé exploitable : ("video", chemin) ou ("project", chemin)."""
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            suffix = Path(path).suffix.lower()
            if suffix in SUPPORTED_VIDEO_FORMATS:
                return "video", path
            if suffix == PROJECT_FILE_EXTENSION:
                return "project", path
        return None

    def dragEnterEvent(self, event) -> None:
        if self._dropped_path(event.mimeData()) is not None:
            self._welcome_view.set_drop_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._welcome_view.set_drop_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._welcome_view.set_drop_active(False)
        dropped = self._dropped_path(event.mimeData())
        if dropped is None:
            event.ignore()
            return
        event.acceptProposedAction()
        kind, path = dropped
        if kind == "video":
            self._video_panel.import_video(path)
        else:
            self._start_project_load(path)

    # --- Sauvegarde automatique ---------------------------------------------

    def _check_for_recoverable_autosave(self) -> None:
        """Propose la récupération dans un bandeau de l'accueil, jamais dans une boîte modale.

        Une boîte modale au lancement bloque l'application avant qu'on ait rien vu ; le
        bandeau laisse importer une vidéo ou ouvrir un autre projet sans y répondre."""
        autosaves = find_recoverable_autosaves()
        if not autosaves:
            return
        self._pending_autosave = describe_autosave(autosaves[0])
        self._welcome_view.show_autosave_offer(
            self._pending_autosave.project_name, self._pending_autosave.saved_at
        )

    def _recover_autosave(self) -> None:
        if self._pending_autosave is None:
            return
        path = self._pending_autosave.path
        self._dismiss_autosave()
        self._start_project_load(path, remember=False)

    def _dismiss_autosave(self) -> None:
        self._pending_autosave = None
        self._welcome_view.hide_autosave_offer()

    def _on_autosave_tick(self) -> None:
        project = self._video_panel.project
        if project is not None:
            autosave_project(project)
            self._last_autosave = datetime.now()
            self._update_save_state()

    def _update_save_state(self) -> None:
        """Carte d'état de la colonne gauche : modifications en attente et dernière sauvegarde auto."""
        if self._video_panel.project is None:
            self._save_state_title.setText("Aucun projet")
            self._save_state_hint.setText("Importez une vidéo pour commencer.")
            return

        self._save_state_title.setText(
            "Modifications non enregistrées" if self._dirty else "Projet enregistré"
        )
        self._save_state_hint.setText(self._autosave_text())

    def _autosave_text(self) -> str:
        if self._last_autosave is None:
            return "Sauvegarde automatique toutes les 2 min."
        minutes = int((datetime.now() - self._last_autosave).total_seconds() // 60)
        if minutes < 1:
            return "Sauvegarde automatique à l'instant"
        return f"Sauvegarde automatique il y a {minutes} min"

    # --- Câblage des signaux -------------------------------------------------

    def _wire_signals(self) -> None:
        self._video_panel.audio_ready.connect(self._on_audio_ready)
        self._video_panel.extraction_started.connect(self._welcome_view.start_import_progress)
        self._video_panel.extraction_progress.connect(self._welcome_view.set_import_progress)
        self._video_panel.extraction_finished.connect(self._welcome_view.hide_import_progress)

        self._welcome_view.import_requested.connect(self._video_panel.trigger_import)
        self._welcome_view.open_project_requested.connect(self._on_open_project_clicked)
        self._welcome_view.recent_project_chosen.connect(self._start_project_load)
        self._welcome_view.autosave_recovery_requested.connect(self._recover_autosave)
        self._welcome_view.autosave_dismissed.connect(self._dismiss_autosave)
        self._welcome_view.import_cancel_requested.connect(self._video_panel.cancel_extraction)
        self._waveform_widget.seek_requested.connect(self._on_waveform_seek_requested)
        self._waveform_widget.selection_changed.connect(self._on_selection_changed)
        self._waveform_widget.region_clicked.connect(self._sequence_list.select_sequence)
        self._waveform_widget.region_double_clicked.connect(self._sequence_list.play_sequence)
        self._waveform_widget.marker_moved.connect(self._on_marker_moved)
        self._waveform_widget.marker_double_clicked.connect(self._rename_marker)
        self._waveform_widget.view_changed.connect(self._on_view_changed)
        self._waveform_overview.view_requested.connect(self._waveform_widget.set_view_range)

        self._transport_controls.position_changed.connect(self._on_playback_position_changed)
        self._transport_controls.playback_error.connect(self._on_playback_error)
        self._video_player_panel.snapshot_saved.connect(self._on_snapshot_saved)

        self._selection_start_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._selection_end_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._selection_card.mark_start_requested.connect(self._mark_selection_start)
        self._selection_card.mark_end_requested.connect(self._mark_selection_end)
        self._selection_card.create_requested.connect(self._on_create_sequence_clicked)
        self._selection_card.listen_requested.connect(self._listen_to_selection)
        self._selection_card.edit_cancelled.connect(self._stop_bounds_edit)
        self._sequence_list.edit_bounds_requested.connect(self._start_bounds_edit)
        self._sequence_list.split_requested.connect(self._split_sequence_at_playhead)
        self._sequence_list.original_toggled.connect(self._on_original_toggled)
        self._selection_card.loop_toggled.connect(self._transport_controls.set_loop)
        self._silence_card.split_requested.connect(self._run_auto_split)

        self._sequence_list.play_requested.connect(self._on_sequence_play_requested)
        self._sequence_list.sequence_selected.connect(self._on_sequence_selected)
        self._sequence_list.sequences_changed.connect(self._on_sequences_changed)
        self._sequence_list.selection_changed.connect(self._audio_processing_panel.set_selected_sequences)
        self._sequence_list.processing_requested.connect(self._open_processing_dialog)
        self._audio_processing_panel.processed.connect(self._sequence_list.refresh)
        self._audio_processing_panel.processed.connect(self._mark_dirty)

    # --- État du projet ------------------------------------------------------

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_window_title()
        self._update_save_state()

    def _mark_dirty(self) -> None:
        self._set_dirty(True)

    def _show_welcome(self) -> None:
        """Revient à l'accueil et y rafraîchit la liste des projets récents."""
        self._welcome_view.set_recent_projects(describe_recent_projects())
        self._pages.setCurrentWidget(self._welcome_view)

    def _update_project_menus(self) -> None:
        """Grise les menus qui n'ont aucun sens sans projet (comme sur la maquette d'accueil)."""
        opened = self._video_panel.project is not None
        for action in self.menuBar().actions():
            if action.text() in _PROJECT_MENUS:
                action.setEnabled(opened)

    def _update_window_title(self) -> None:
        project = self._video_panel.project
        if project is None:
            self.setWindowTitle(APP_NAME)
            self._set_project_name_label("Aucun projet ouvert")
            return
        suffix = " *" if self._dirty else ""
        self.setWindowTitle(f"{project.name}{suffix} — {APP_NAME}")
        self._set_project_name_label(f"{project.name}{suffix}")

    def _set_project_name_label(self, text: str) -> None:
        """Nom du projet à droite de la barre de menus ; la barre ne redimensionne pas seule ses coins."""
        self._project_name_label.setText(text)
        self._project_name_label.adjustSize()
        # Re-poser le widget force la barre de menus à recalculer la place réservée au coin.
        self.menuBar().setCornerWidget(self._project_name_label, Qt.Corner.TopRightCorner)
        self._project_name_label.show()

    def _confirm_discard_changes(self) -> bool:
        """Propose d'enregistrer les modifications en cours ; False si l'utilisateur annule."""
        if not self._dirty:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "AudioCut Studio",
            "Le projet contient des modifications non sauvegardées.\nVoulez-vous les enregistrer ?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self._save_project()
        return answer == buttons.Discard

    def closeEvent(self, event) -> None:
        if self._confirm_discard_changes():
            super().closeEvent(event)
        else:
            event.ignore()

    # --- Chargement de la source ---------------------------------------------

    def _on_audio_ready(self, wav_path: str, duration: float) -> None:
        self._pages.setCurrentIndex(1)
        self._welcome_view.hide_autosave_offer()
        self._update_project_menus()
        self._waveform_widget.load(wav_path, duration)
        self._waveform_overview.load(wav_path, duration)
        self._video_playback_failed = False
        self._stop_bounds_edit()
        self._preview_proxy_path = ""
        self._load_source_playback()
        self._playback_offset = 0.0
        self._sequence_list.set_project(self._video_panel.project)
        self._audio_processing_panel.set_project(self._video_panel.project)
        self._source_duration = duration
        self._update_waveform_regions()
        self._update_waveform_markers()
        self._crossfade_spin.blockSignals(True)
        self._crossfade_spin.setValue(self._video_panel.project.crossfade_duration)
        self._crossfade_spin.blockSignals(False)
        self._update_project_summary()
        self._set_dirty(False)

        project = self._video_panel.project
        self._video_player_panel.set_media_info(project.source_video if project else None)
        self._video_player_panel.set_duration(duration)
        self._video_player_panel.set_now_playing("source")
        self._video_preview.set_snapshot_dir(project.temp_dir if project else "")
        self._transport_controls.set_now_playing("Source complète")
        self._duration_label.setText(f"/ {format_timecode_fr(duration)}")
        self._selection_card.set_range(duration)
        self._selection_start_spin.setValue(0.0)
        self._selection_end_spin.setValue(0.0)
        self._status_hint_label.setText("Prêt · extraction terminée")
        self._start_preview_proxy()

    def _source_playback_path(self) -> str:
        """Média à lire pour la source : la vidéo (image + son), ou le WAV extrait en repli."""
        project = self._video_panel.project
        if project is None:
            return ""
        video = project.source_video
        if video is not None and video.path and not self._video_playback_failed:
            return self._preview_proxy_path or video.path
        return project.original_audio_path

    def _load_source_playback(self) -> None:
        self._playing_sequence_id = None
        path = self._source_playback_path()
        if not path:
            return
        self._transport_controls.set_source(path)
        self._video_preview.set_active(not self._video_playback_failed)
        self._video_player_panel.set_synchronised(not self._video_playback_failed)

    # --- Aperçu fluide (copie allégée de la vidéo) -----------------------------------

    def _start_preview_proxy(self) -> None:
        """Prépare en arrière-plan la copie d'aperçu si la vidéo est assez lourde pour saccader."""
        project = self._video_panel.project
        if project is None or not needs_preview_proxy(project.source_video):
            return
        service = self._video_panel.ffmpeg_service
        self._status_hint_label.setText("Préparation de l'aperçu fluide… 0 %")
        worker = FFmpegTaskWorker(lambda report: build_preview_proxy(project, service, report), with_progress=True)
        worker.progress.connect(
            lambda percent: self._status_hint_label.setText(f"Préparation de l'aperçu fluide… {percent} %")
        )
        worker.succeeded.connect(lambda path: self._on_preview_proxy_ready(project, path))
        worker.failed.connect(self._on_preview_proxy_failed)
        self._proxy_worker = worker
        worker.start()

    def _on_preview_proxy_ready(self, project, path: str) -> None:
        """Bascule la lecture de la source sur la copie légère, sans perdre la position ni l'état lecture."""
        if project is not self._video_panel.project or self._video_playback_failed:
            return  # un autre projet a été ouvert entre-temps
        self._preview_proxy_path = path
        self._status_hint_label.setText("Aperçu fluide prêt")
        if self._playback_offset == 0.0:
            self._transport_controls.replace_source_keep_position(path)

    def _on_preview_proxy_failed(self, _message: str) -> None:
        """Sans copie d'aperçu on garde la vidéo d'origine : plus lente à parcourir, mais fonctionnelle."""
        self._status_hint_label.setText("Prêt · aperçu fluide indisponible")

    def _on_playback_error(self, message: str) -> None:
        """Vidéo illisible par Qt : on rebascule sur l'audio extrait, qui lui est toujours lisible."""
        if self._video_playback_failed or self._playback_offset != 0.0:
            return
        project = self._video_panel.project
        if project is None or not project.original_audio_path:
            return
        self._video_playback_failed = True
        self._load_source_playback()
        self.statusBar().showMessage(
            "Aperçu vidéo indisponible pour ce format : lecture de l'audio extrait uniquement.", 8000
        )

    # --- Waveform, zoom et sélection -----------------------------------------

    def _on_view_changed(self, start: float, end: float) -> None:
        self._waveform_overview.set_view_range(start, end)
        self._zoom_label.setText(f"× {self._waveform_widget.zoom_factor:.1f}".replace(".", ","))

    def _on_selection_changed(self, start: float, end: float) -> None:
        self._selection_start_spin.blockSignals(True)
        self._selection_end_spin.blockSignals(True)
        self._selection_start_spin.setValue(start)
        self._selection_end_spin.setValue(end)
        self._selection_start_spin.blockSignals(False)
        self._selection_end_spin.blockSignals(False)
        self._selection_card.refresh_duration()
        # Borne tirée sur la waveform pendant une écoute en boucle : la boucle suit sans s'interrompre.
        self._transport_controls.update_range(start, end)

    def _mark_selection_start(self) -> None:
        """Raccourci I : place le début de la sélection à la position de lecture."""
        position = min(self._transport_controls.position_seconds, self._selection_start_spin.maximum())
        if self._selection_end_spin.value() < position:
            self._selection_end_spin.setValue(position)
        self._selection_start_spin.setValue(position)

    def _mark_selection_end(self) -> None:
        """Raccourci O : place la fin de la sélection à la position de lecture."""
        position = min(self._transport_controls.position_seconds, self._selection_end_spin.maximum())
        if self._selection_start_spin.value() > position:
            self._selection_start_spin.setValue(position)
        self._selection_end_spin.setValue(position)

    def _on_selection_spin_changed(self) -> None:
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        self._waveform_widget.set_selection(start, end)
        # Réglage fin pendant l'écoute : la boucle prend les nouvelles bornes sans s'interrompre.
        self._transport_controls.update_range(start, end)

    def _on_create_sequence_clicked(self) -> None:
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "AudioCut Studio", "Sélectionnez une plage valide avant de créer une séquence.")
            return
        if self._editing_sequence_id is not None:
            self._apply_bounds_edit(start, end)
            return
        self._sequence_list.add_sequence_from_selection(start, end)

    # --- Ajustement des bornes et division d'une séquence existante ------------------------------------

    def _start_bounds_edit(self, sequence_id: str) -> None:
        """Charge les bornes d'une séquence dans la sélection : on les règle avec les poignées, puis on valide."""
        sequence = self._sequence_list.get_sequence(sequence_id)
        if sequence is None:
            return
        self._editing_sequence_id = sequence_id
        self._selection_card.set_editing(sequence.name)
        self._selection_start_spin.setValue(sequence.source_start)
        self._selection_end_spin.setValue(sequence.source_end)
        self._waveform_widget.ensure_range_visible(sequence.source_start, sequence.source_end)
        self._ensure_source_playback()
        self._transport_controls.set_position_seconds(sequence.source_start)
        self.statusBar().showMessage(
            f"Ajustez les bornes de « {sequence.name} » (poignées, champs ou I / O), puis validez avec Entrée.", 8000
        )

    def _apply_bounds_edit(self, start: float, end: float) -> None:
        sequence_id = self._editing_sequence_id
        if sequence_id is None:
            return
        if self._sequence_list.retime_sequence(sequence_id, start, end):
            self._stop_bounds_edit()
            self.statusBar().showMessage("Bornes de la séquence mises à jour.", 5000)

    def _stop_bounds_edit(self) -> None:
        self._editing_sequence_id = None
        self._selection_card.set_editing(None)

    def _split_sequence_at_playhead(self, sequence_id: str) -> None:
        """Divise la séquence à la position de lecture (sur la timeline de la source)."""
        at = self._waveform_widget.playhead
        if self._sequence_list.split_sequence_at(sequence_id, at):
            self.statusBar().showMessage(f"Séquence divisée à {format_timecode_fr(at)}.", 5000)

    def _ensure_source_playback(self) -> None:
        """Reprend la lecture de la source si une séquence ou le résultat fusionné était chargé."""
        if self._playback_offset != 0.0 and self._source_playback_path():
            self._load_source_playback()
            self._playback_offset = 0.0
            self._video_player_panel.set_now_playing("source")
            self._transport_controls.set_now_playing("Source complète")

    def _on_waveform_seek_requested(self, seconds: float) -> None:
        """Un clic sur la waveform (piste source) doit reprendre la lecture de la source,
        même si une séquence ou le résultat fusionné était en cours de lecture."""
        self._ensure_source_playback()
        self._transport_controls.set_position_seconds(seconds)

    def _listen_to_selection(self) -> None:
        """Écoute uniquement la plage sélectionnée (image et son de la source), puis s'arrête à la fin."""
        project = self._video_panel.project
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        if project is None or end <= start:
            self.statusBar().showMessage("Sélectionnez une plage sur la waveform avant de l'écouter.", 4000)
            return
        self._ensure_source_playback()
        self._transport_controls.play_range(start, end)

    # --- Repères -------------------------------------------------------------

    def _update_waveform_markers(self) -> None:
        project = self._video_panel.project
        markers = project.markers if project is not None else []
        self._waveform_widget.set_markers([(m.position, m.label, m.id) for m in markers])

    def _marker_pick_tolerance(self) -> float:
        """Écart toléré entre la tête de lecture et un repère pour le considérer « sous » elle.

        Exprimé en pixels à l'écran : dézoomé, une seconde tient dans un pixel, et une
        tolérance fixe empêcherait de reprendre un repère qu'on voit pourtant sous la tête."""
        start, end = self._waveform_widget.view_range
        width = max(self._waveform_widget.width(), 1)
        return max(_MARKER_PICK_SECONDS, (end - start) / width * _MARKER_PICK_PIXELS)

    def _push_marker_command(self, description: str, redo_fn, undo_fn) -> None:
        """Pousse une modification des repères sur la pile d'undo partagée, rendu et état inclus."""

        def with_refresh(action):
            def run() -> None:
                action()
                self._update_waveform_markers()
                self._update_project_summary()
                self._mark_dirty()

            return run

        self._sequence_list.undo_stack.push(
            CallbackCommand(description, with_refresh(redo_fn), with_refresh(undo_fn))
        )

    def _require_project(self, message: str):
        """Projet courant, ou None après avoir expliqué en barre d'état pourquoi l'action n'a rien fait."""
        project = self._video_panel.project
        if project is None:
            self.statusBar().showMessage(message, 4000)
            return None
        return project

    def _add_marker_at_playhead(self) -> None:
        """Raccourci M : pose un repère nommé à la position de lecture."""
        project = self._require_project("Importez une vidéo avant de poser un repère.")
        if project is None:
            return
        position = min(max(self._waveform_widget.playhead, 0.0), self._source_duration)
        existing = marker_service.marker_near(project, position, self._marker_pick_tolerance())
        if existing is not None:
            self.statusBar().showMessage(f"« {existing.label} » est déjà posé ici.", 4000)
            return
        marker = marker_service.create_marker(project, position)
        self._push_marker_command(
            f"Poser le repère {marker.label}",
            lambda: marker_service.insert_marker(project, marker),
            lambda: marker_service.remove_marker(project, marker.id),
        )
        self.statusBar().showMessage(
            f"{marker.label} posé à {format_timecode_fr(marker.position)} · Maj+M pour le retirer", 4000
        )

    def _remove_marker_at_playhead(self) -> None:
        """Raccourci Maj+M : retire le repère situé sous la tête de lecture."""
        project = self._require_project("Aucun projet : aucun repère à retirer.")
        if project is None:
            return
        marker = marker_service.marker_near(project, self._waveform_widget.playhead, self._marker_pick_tolerance())
        if marker is None:
            self.statusBar().showMessage("Aucun repère sous la tête de lecture.", 4000)
            return
        self._push_marker_command(
            f"Retirer le repère {marker.label}",
            lambda: marker_service.remove_marker(project, marker.id),
            lambda: marker_service.insert_marker(project, marker),
        )
        self.statusBar().showMessage(f"{marker.label} retiré · Ctrl+Z pour le remettre", 4000)

    def _go_to_previous_marker(self) -> None:
        """Raccourci Alt+Haut : se cale sur le repère précédent."""
        self._go_to_marker(marker_service.previous_marker)

    def _go_to_next_marker(self) -> None:
        """Raccourci Alt+Bas : se cale sur le repère suivant."""
        self._go_to_marker(marker_service.next_marker)

    def _go_to_marker(self, pick) -> None:
        project = self._require_project("Importez une vidéo avant de naviguer entre les repères.")
        if project is None:
            return
        if not project.markers:
            self.statusBar().showMessage("Aucun repère posé (M pour en poser un).", 4000)
            return
        marker = pick(project, self._waveform_widget.playhead)
        if marker is None:
            self.statusBar().showMessage("Aucun repère de ce côté de la tête de lecture.", 4000)
            return
        self._on_waveform_seek_requested(marker.position)
        self._waveform_widget.set_playhead(marker.position)
        self._waveform_widget.ensure_range_visible(marker.position, marker.position)
        self.statusBar().showMessage(f"{marker.label} — {format_timecode_fr(marker.position)}", 4000)

    def _select_between_markers(self) -> None:
        """Raccourci Alt+S : sélectionne l'intervalle délimité par les repères qui encadrent la lecture."""
        project = self._require_project("Importez une vidéo avant de sélectionner entre deux repères.")
        if project is None:
            return
        span = marker_service.surrounding_range(project, self._waveform_widget.playhead, self._source_duration)
        if span is None:
            self.statusBar().showMessage("Aucun intervalle entre repères à cet endroit.", 4000)
            return
        start, end = span
        self._selection_start_spin.blockSignals(True)
        self._selection_end_spin.blockSignals(True)
        self._selection_start_spin.setValue(start)
        self._selection_end_spin.setValue(end)
        self._selection_start_spin.blockSignals(False)
        self._selection_end_spin.blockSignals(False)
        self._on_selection_spin_changed()
        self._selection_card.refresh_duration()
        self.statusBar().showMessage(
            f"Sélection entre repères : {format_timecode_fr(start)} → {format_timecode_fr(end)} · Entrée pour créer la séquence",
            5000,
        )

    def _find_marker(self, marker_id: str):
        """Repère du projet courant, ou None : un signal peut arriver après sa suppression (undo)."""
        project = self._video_panel.project
        if project is None:
            return None
        return next((marker for marker in project.markers if marker.id == marker_id), None)

    def _on_marker_moved(self, marker_id: str, position: float) -> None:
        """Repère tiré à la souris : le déplacement est enregistré en une seule étape annulable."""
        project = self._video_panel.project
        marker = self._find_marker(marker_id)
        if marker is None:
            return
        old_position = marker.position
        new_position = min(max(position, 0.0), self._source_duration)
        if abs(new_position - old_position) < 1e-6:
            self._update_waveform_markers()  # rien n'a bougé : on remet l'affichage sur le modèle
            return
        self._push_marker_command(
            f"Déplacer le repère {marker.label}",
            lambda: marker_service.move_marker(project, marker_id, new_position),
            lambda: marker_service.move_marker(project, marker_id, old_position),
        )
        self.statusBar().showMessage(
            f"{marker.label} déplacé à {format_timecode_fr(new_position)} · Ctrl+Z pour revenir", 4000
        )

    def _rename_marker(self, marker_id: str) -> None:
        """Double-clic sur un repère : lui donner un nom parlant (« Question du public »…)."""
        project = self._video_panel.project
        marker = self._find_marker(marker_id)
        if marker is None:
            return
        new_label, accepted = QInputDialog.getText(self, "Renommer le repère", "Nom du repère :", text=marker.label)
        new_label = new_label.strip()
        if not accepted or not new_label or new_label == marker.label:
            return
        old_label = marker.label
        self._push_marker_command(
            f"Renommer le repère {old_label}",
            lambda: marker_service.rename_marker(project, marker_id, new_label),
            lambda: marker_service.rename_marker(project, marker_id, old_label),
        )

    def _on_create_sequences_from_markers(self) -> None:
        """Transforme en séquences les tranches délimitées par les repères, après validation.

        Le même aperçu que le découpage automatique sert à décocher les tranches dont on ne
        veut pas : poser un repère au début et à la fin de chaque passage intéressant laisse
        alors les tranches inutiles de côté en deux clics."""
        project = self._require_project("Importez une vidéo avant de découper aux repères.")
        if project is None:
            return
        if not project.markers:
            QMessageBox.information(
                self, "AudioCut Studio", "Posez au moins un repère (touche M) pour découper l'audio à cet endroit."
            )
            return
        slices = marker_service.intervals(project, self._source_duration)
        if not slices:
            QMessageBox.information(self, "AudioCut Studio", "Les repères ne délimitent aucune tranche exploitable.")
            return

        preview = SplitPreviewDialog(slices, self, title="Tranches délimitées par les repères")
        if preview.exec() != SplitPreviewDialog.DialogCode.Accepted:
            return
        chosen = preview.selected_ranges()
        if not chosen:
            return

        service = self._video_panel.ffmpeg_service
        ranges = [(entry[0], entry[1]) for entry in chosen]
        names = [entry[2] if len(entry) > 2 else "" for entry in chosen]
        progress = QProgressDialog("Découpage des séquences…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        self._split_worker = FFmpegTaskWorker(
            lambda: create_sequences_from_ranges(project, service, ranges, names)
        )
        self._split_worker.succeeded.connect(
            lambda sequences: self._on_auto_split_done(sequences, progress, origin="depuis les repères")
        )
        self._split_worker.failed.connect(lambda message: self._on_auto_split_failed(message, progress))
        self._split_worker.start()

    # --- Séquences -----------------------------------------------------------

    def _on_crossfade_changed(self, value: float) -> None:
        project = self._video_panel.project
        if project is not None:
            project.crossfade_duration = value
            self._mark_dirty()
        self._update_project_summary()

    def _update_project_summary(self) -> None:
        """Barre d'état : nombre de séquences et durée totale estimée du résultat fusionné."""
        project = self._video_panel.project
        if project is None:
            self._project_summary_label.setText(_EMPTY_SUMMARY)
            return
        count = len(project.sequences)
        total = sum(seq.duration for seq in project.sequences)
        if count > 1:
            total -= project.crossfade_duration * (count - 1)
        total = max(total, 0.0)
        plural = "s" if count > 1 else ""
        summary = f"{count} séquence{plural} — durée fusionnée : {format_timecode(total)}"
        if project.markers:
            marker_plural = "s" if len(project.markers) > 1 else ""
            summary += f" · {len(project.markers)} repère{marker_plural}"
        self._project_summary_label.setText(summary)

    def _on_sequence_play_requested(self, name: str, audio_path: str, source_start: float) -> None:
        self._playback_offset = source_start
        sequence = self._sequence_list.current_sequence()
        self._playing_sequence_id = sequence.id if sequence is not None and sequence.source_start == source_start else None
        label = self._sequence_playback_label(sequence) if self._playing_sequence_id else name
        self._transport_controls.set_now_playing(label)
        self._video_player_panel.set_now_playing(label)
        self._transport_controls.load_and_play(audio_path)

    def _sequence_playback_label(self, sequence) -> str:
        """Nom affiché pendant la lecture ; précise « original » quand on écoute l'audio sans traitement."""
        if self._sequence_list.plays_original and sequence.processed_audio_path:
            return f"{sequence.name} · original"
        return sequence.name

    def _on_original_toggled(self, _checked: bool) -> None:
        """Bascule A/B en cours d'écoute : même séquence, autre version, à la même position (sans coupure)."""
        sequence_id = self._playing_sequence_id
        sequence = self._sequence_list.get_sequence(sequence_id) if sequence_id else None
        if sequence is None or self._playback_offset != sequence.source_start:
            return  # aucune séquence en cours de lecture : le réglage servira à la prochaine lecture
        self._transport_controls.replace_source_keep_position(self._sequence_list.playback_path(sequence))
        label = self._sequence_playback_label(sequence)
        self._transport_controls.set_now_playing(label)
        self._video_player_panel.set_now_playing(label)

    def _on_playback_position_changed(self, seconds: float) -> None:
        if self._playback_offset is not None:
            absolute = self._playback_offset + seconds
            self._waveform_widget.set_playhead(absolute)
            self._position_label.setText(format_timecode_fr(absolute))

    def _on_sequence_selected(self, sequence_id: str) -> None:
        self._audio_processing_panel.set_sequence(self._sequence_list.get_sequence(sequence_id))
        self._waveform_widget.set_active_sequence(sequence_id)

    def _update_waveform_regions(self) -> None:
        project = self._video_panel.project
        sequences = sorted(project.sequences, key=lambda seq: seq.order) if project is not None else []
        self._waveform_widget.set_sequence_regions(
            [(seq.source_start, seq.source_end, seq.name, seq.id) for seq in sequences]
        )

    def _on_sequences_changed(self) -> None:
        if self._editing_sequence_id is not None and self._sequence_list.get_sequence(self._editing_sequence_id) is None:
            self._stop_bounds_edit()  # la séquence en cours d'ajustement a été supprimée
        self._update_waveform_regions()
        self._update_project_summary()
        self._mark_dirty()
        self._audio_processing_panel.set_sequence(self._sequence_list.current_sequence())

    def _open_processing_dialog(self) -> None:
        """Ouvre la fenêtre de traitement audio sur la sélection courante."""
        self._audio_processing_panel.set_sequence(self._sequence_list.current_sequence())
        self._audio_processing_panel.set_selected_sequences(self._sequence_list.selected_sequences())
        self._processing_dialog.show_and_raise()

    def _on_snapshot_saved(self, path: str) -> None:
        self.statusBar().showMessage(f"Image enregistrée : {path}", 5000)

    # --- Découpage automatique -----------------------------------------------

    def _on_auto_split_clicked(self) -> None:
        """Entrée par le menu : les réglages passent par le dialogue dédié."""
        dialog = AutoSplitDialog(self)
        if dialog.exec() != AutoSplitDialog.DialogCode.Accepted:
            return
        self._run_auto_split(dialog.params())

    def _run_auto_split(self, params) -> None:
        """Étape 1 : détection des passages en tâche de fond ; l'utilisateur les valide ensuite."""
        project = self._video_panel.project
        if project is None or not project.original_audio_path:
            QMessageBox.warning(self, "AudioCut Studio", "Importez une vidéo avant de découper automatiquement.")
            return

        progress = QProgressDialog("Détection des silences…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()

        service = self._video_panel.ffmpeg_service
        self._split_worker = FFmpegTaskWorker(lambda: detect_speech_ranges(project, service, params))
        self._split_worker.succeeded.connect(lambda ranges: self._on_split_ranges_detected(ranges, progress))
        self._split_worker.failed.connect(lambda message: self._on_auto_split_failed(message, progress))
        self._split_worker.start()

    def _on_split_ranges_detected(self, ranges: list, progress: QProgressDialog) -> None:
        """Étape 2 : aperçu et choix des passages, puis découpage des seuls passages retenus."""
        progress.close()
        self._silence_card.set_detected_count(len(ranges))
        if not ranges:
            QMessageBox.information(self, "AudioCut Studio", "Aucun passage détecté avec ces réglages.")
            return

        preview = SplitPreviewDialog(ranges, self)
        if preview.exec() != SplitPreviewDialog.DialogCode.Accepted:
            return
        chosen = preview.selected_ranges()
        if not chosen:
            return

        project = self._video_panel.project
        service = self._video_panel.ffmpeg_service
        cutting = QProgressDialog("Découpage des séquences…", None, 0, 0, self)
        cutting.setWindowModality(Qt.WindowModality.WindowModal)
        cutting.setCancelButton(None)
        cutting.show()
        self._split_worker = FFmpegTaskWorker(lambda: create_sequences_from_ranges(project, service, chosen))
        self._split_worker.succeeded.connect(lambda sequences: self._on_auto_split_done(sequences, cutting))
        self._split_worker.failed.connect(lambda message: self._on_auto_split_failed(message, cutting))
        self._split_worker.start()

    def _on_auto_split_done(self, sequences: list, progress: QProgressDialog, origin: str = "automatiquement") -> None:
        progress.close()
        if not sequences:
            return
        self._sequence_list.add_sequences(sequences)
        self.statusBar().showMessage(f"{len(sequences)} séquences créées {origin}.", 5000)

    def _on_auto_split_failed(self, message: str, progress: QProgressDialog) -> None:
        progress.close()
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    # --- Fusion et export ----------------------------------------------------

    def _on_merge_preview_clicked(self) -> None:
        project = self._video_panel.project
        if project is None:
            return
        try:
            final_wav = merge_sequences(project, self._video_panel.ffmpeg_service)
        except ExportError as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return
        # Le résultat fusionné n'a pas de correspondance simple avec la timeline source
        # (ordre différent, crossfades) : on n'y déplace pas la tête de lecture.
        self._playback_offset = None
        self._playing_sequence_id = None
        self._transport_controls.set_now_playing("Montage fusionné")
        self._video_player_panel.set_now_playing("montage")
        self._transport_controls.load_and_play(final_wav)

    def _on_export_clicked(self) -> None:
        project = self._video_panel.project
        if project is None or not project.sequences:
            QMessageBox.warning(self, "AudioCut Studio", "Créez au moins une séquence avant d'exporter.")
            return
        dialog = ExportDialog(project, self._video_panel.ffmpeg_service, self)
        dialog.exec()

    # --- Projets --------------------------------------------------------------

    def _populate_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = load_recent_projects()
        if not recent:
            self._recent_menu.addAction("(aucun)").setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self._start_project_load(p))

    def _on_save_project_clicked(self) -> None:
        self._save_project()

    def _save_project(self) -> bool:
        """Sauvegarde le projet (dialogue de fichier). Retourne True si le fichier a été écrit."""
        project = self._video_panel.project
        if project is None:
            QMessageBox.warning(self, "AudioCut Studio", "Importez une vidéo avant de sauvegarder un projet.")
            return False

        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder le projet", "", f"Projet AudioCut Studio (*{PROJECT_FILE_EXTENSION})"
        )
        if not path:
            return False
        if not path.endswith(PROJECT_FILE_EXTENSION):
            path += PROJECT_FILE_EXTENSION

        save_project(project, path)
        add_recent_project(path)
        self._set_dirty(False)
        self.statusBar().showMessage(f"Projet sauvegardé : {path}", 5000)
        return True

    def _on_open_project_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet", "", f"Projet AudioCut Studio (*{PROJECT_FILE_EXTENSION})"
        )
        if path:
            self._start_project_load(path)

    def _start_project_load(self, path: str, remember: bool = True) -> None:
        if remember and not self._confirm_discard_changes():
            return
        progress = QProgressDialog("Chargement du projet…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()

        self._load_worker = FFmpegTaskWorker(
            lambda: load_project(path, self._video_panel.ffprobe_service, self._video_panel.ffmpeg_service)
        )
        self._load_worker.succeeded.connect(
            lambda project: self._on_project_loaded(project, progress, path if remember else None)
        )
        self._load_worker.failed.connect(lambda message: self._on_project_load_failed(message, progress))
        self._load_worker.start()

    def _on_project_loaded(self, project, progress: QProgressDialog, path: str | None) -> None:
        progress.close()
        self._video_panel.set_loaded_project(project)
        # Projet récupéré d'une sauvegarde automatique (path None) : pas encore enregistré.
        self._set_dirty(path is None)
        if path is not None:
            add_recent_project(path)

    def _on_project_load_failed(self, message: str, progress: QProgressDialog) -> None:
        progress.close()
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)
