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
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME, SUPPORTED_VIDEO_FORMATS
from app.config.settings import FFmpegBinaries
from app.config.themes import THEMES, get_theme, load_stylesheet, load_theme_preference, save_theme_preference
from app.services.export_service import ExportError, merge_sequences
from app.services.project_service import (
    PROJECT_FILE_EXTENSION,
    autosave_project,
    find_recoverable_autosaves,
    load_project,
    save_project,
)
from app.services.recent_projects import add_recent_project, load_recent_projects
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
from app.ui.video_panel import VideoPanel
from app.ui.video_player_panel import VideoPlayerPanel
from app.ui.video_preview import VideoPreview
from app.ui.waveform_overview import WaveformOverview
from app.ui.waveform_widget import WaveformWidget
from app.utils.time_utils import format_timecode, format_timecode_fr
from app.workers.ffmpeg_worker import FFmpegTaskWorker

_SIDE_PANEL_WIDTH = 410
_RIGHT_PANEL_WIDTH = 360
_AUTOSAVE_INTERVAL_MS = 2 * 60 * 1000
_SAVE_STATE_REFRESH_MS = 30 * 1000
_WAVEFORM_HINT = "clic = lecture · glisser = sélection"


class MainWindow(QMainWindow):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setAcceptDrops(True)

        self._video_panel = VideoPanel(ffmpeg_binaries)
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

        self._playback_offset: float | None = 0.0
        self._preview_proxy_path = ""
        self._proxy_worker = None
        # La source est lue depuis le fichier vidéo (image + son synchronisés) ; si Qt ne sait pas
        # le décoder, on bascule une seule fois sur le WAV extrait par FFmpeg.
        self._video_playback_failed = False
        self._dirty = False

        self._build_actions()
        self.setCentralWidget(self._build_central_widget())
        self._build_menus()
        self._build_status_bar()
        self._wire_signals()
        self._register_shortcuts()

        self._update_project_summary()
        self._update_window_title()
        self._update_save_state()

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
        self._status_hint_label = label("Prêt", "hintLabel")
        self.statusBar().addPermanentWidget(self._project_summary_label, 1)
        self.statusBar().addPermanentWidget(self._status_hint_label)

    def _register_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_I), self, activated=self._mark_selection_start)
        QShortcut(QKeySequence(Qt.Key.Key_O), self, activated=self._mark_selection_end)
        QShortcut(QKeySequence("Shift+Space"), self, activated=self._listen_to_selection)
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
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
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
        autosaves = find_recoverable_autosaves()
        if not autosaves:
            return

        answer = QMessageBox.question(
            self,
            "AudioCut Studio",
            "Un projet non sauvegardé a été trouvé (fermeture inattendue).\n"
            "Voulez-vous le récupérer ?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_project_load(autosaves[0], remember=False)

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
        self._waveform_widget.seek_requested.connect(self._on_waveform_seek_requested)
        self._waveform_widget.selection_changed.connect(self._on_selection_changed)
        self._waveform_widget.region_clicked.connect(self._sequence_list.select_sequence)
        self._waveform_widget.region_double_clicked.connect(self._sequence_list.play_sequence)
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

    def _update_window_title(self) -> None:
        project = self._video_panel.project
        if project is None:
            self.setWindowTitle(APP_NAME)
            self._set_project_name_label("")
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
        self._waveform_widget.load(wav_path, duration)
        self._waveform_overview.load(wav_path, duration)
        self._video_playback_failed = False
        self._preview_proxy_path = ""
        self._load_source_playback()
        self._playback_offset = 0.0
        self._sequence_list.set_project(self._video_panel.project)
        self._audio_processing_panel.set_project(self._video_panel.project)
        self._update_waveform_regions()
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

    def _on_create_sequence_clicked(self) -> None:
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "AudioCut Studio", "Sélectionnez une plage valide avant de créer une séquence.")
            return
        self._sequence_list.add_sequence_from_selection(start, end)

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
            self._project_summary_label.setText("Aucun projet")
            return
        count = len(project.sequences)
        total = sum(seq.duration for seq in project.sequences)
        if count > 1:
            total -= project.crossfade_duration * (count - 1)
        total = max(total, 0.0)
        plural = "s" if count > 1 else ""
        self._project_summary_label.setText(f"{count} séquence{plural} — durée fusionnée : {format_timecode(total)}")

    def _on_sequence_play_requested(self, name: str, audio_path: str, source_start: float) -> None:
        self._playback_offset = source_start
        self._transport_controls.set_now_playing(name)
        self._video_player_panel.set_now_playing(name)
        self._transport_controls.load_and_play(audio_path)

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

    def _on_auto_split_done(self, sequences: list, progress: QProgressDialog) -> None:
        progress.close()
        if not sequences:
            return
        self._sequence_list.add_sequences(sequences)
        self.statusBar().showMessage(f"{len(sequences)} séquences créées automatiquement.", 5000)

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
