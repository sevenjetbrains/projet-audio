"""Fenêtre « Fusion et export » : comment les séquences sont assemblées, puis où et sous quelle forme.

Disposition conforme à la maquette : la fusion et le format à gauche/droite, un aperçu du
résultat fusionné, ce qui sera écrit, la destination, puis la progression de l'export — qui
peut être interrompue, le projet restant intact.
"""

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.audio.waveform import compute_peaks
from app.config.themes import Theme, get_theme, load_theme_preference
from app.models.project import Project
from app.services.export_service import export_project, export_sequences_separately, merge_sequences
from app.services.ffmpeg_service import FFmpegService, wav_duration
from app.ui.controls import SegmentedControl, SliderRow
from app.ui.screen_fit import ScreenFittedDialog
from app.ui.design import accent_button, card_layout, icon_button, label
from app.ui.icons import set_button_icon
from app.ui.preview_strip import MergedWaveStrip
from app.utils.time_utils import format_clock, format_timecode
from app.workers.ffmpeg_worker import ExportWorker, FFmpegTaskWorker

_FORMATS = ("WAV", "MP3", "FLAC", "M4A", "OGG", "Opus")
_QUALITY_OPTIONS = {
    "WAV": [("16 bits", "16"), ("24 bits", "24")],
    "MP3": [("128 kbit/s", "128"), ("192 kbit/s", "192"), ("256 kbit/s", "256"), ("320 kbit/s", "320")],
    "FLAC": [("16 bits", "16"), ("24 bits", "24")],
    "M4A": [("128 kbit/s", "128"), ("192 kbit/s", "192"), ("256 kbit/s", "256"), ("320 kbit/s", "320")],
    "OGG": [("Standard (q3)", "3"), ("Bonne (q5)", "5"), ("Haute (q7)", "7")],
    "Opus": [("64 kbit/s", "64"), ("96 kbit/s", "96"), ("128 kbit/s", "128"), ("192 kbit/s", "192")],
}
# Les formats sans débit réglable exposent une résolution : le libellé du champ suit.
_BIT_DEPTH_FORMATS = ("WAV", "FLAC")
_SAMPLE_RATES = [("Comme la source", 0), ("44 100 Hz", 44100), ("48 000 Hz", 48000), ("96 000 Hz", 96000)]
_DEFAULT_SAMPLE_RATE_INDEX = 2
_PREVIEW_PEAKS = 200
_MINIMUM_SIZE = (1080, 620)
_PREFERRED_SIZE = (1220, 900)
_FOOTER_NOTE = "Raccourci : Ctrl+E. La vidéo source reste intacte."
_JUNCTION_NOTE = "Les jonctions entre séquences sont marquées en clair."
_CANCEL_NOTE = "L'export peut être interrompu sans perdre le projet."


def _separator() -> QFrame:
    line = QFrame()
    line.setObjectName("cardSeparator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def _card_header(title: str, trailing: QWidget | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(label(title, "cardTitle"))
    row.addStretch(1)
    if trailing is not None:
        row.addWidget(trailing)
    return row


class ExportDialog(ScreenFittedDialog):
    PREFERRED_SIZE = _PREFERRED_SIZE
    MINIMUM_SIZE = _MINIMUM_SIZE

    def __init__(self, project: Project, ffmpeg_service: FFmpegService, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fusion et export — AudioCut Studio")

        self._project = project
        self._ffmpeg_service = ffmpeg_service
        self._worker: ExportWorker | None = None
        self._preview_worker: FFmpegTaskWorker | None = None
        self._preview_path = ""
        self._exported_folder = ""
        self._auto_path = ""
        self._elapsed = QElapsedTimer()

        self._build_widgets()
        self._build_layout()
        self.set_theme(get_theme(load_theme_preference()))
        self._on_format_changed(self._format_segments.value())
        self._on_merge_mode_changed()
        self._refresh_header()

    # --- Construction -----------------------------------------------------------

    def _build_widgets(self) -> None:
        self._subtitle_label = label("", "dialogSubtitle")
        self._close_button = QPushButton()
        self._close_button.setFixedSize(44, 44)
        self._close_button.setProperty("flat", "true")
        self._close_button.setToolTip("Fermer")
        set_button_icon(self._close_button, "close", size=18)
        self._close_button.clicked.connect(self.close)

        # Fusion des séquences
        self._simple_merge_radio = QRadioButton("Fusion simple (bout à bout)")
        self._crossfade_radio = QRadioButton("Fondu enchaîné entre séquences")
        self._crossfade_slider = SliderRow("Durée", 0.0, 2000.0, "ms", scale=1, decimals=0)
        self._crossfade_slider.set_value(self._project.crossfade_duration * 1000)
        self._crossfade_radio.setChecked(self._project.crossfade_duration > 0)
        self._simple_merge_radio.setChecked(self._project.crossfade_duration <= 0)
        self._merge_hint = label("", "settingHint")
        self._merge_hint.setWordWrap(True)
        for radio in (self._simple_merge_radio, self._crossfade_radio):
            radio.toggled.connect(self._on_merge_mode_changed)
        self._crossfade_slider.value_changed.connect(self._on_merge_mode_changed)

        # Format de sortie
        self._format_segments = SegmentedControl(_FORMATS, columns=3)
        self._format_segments.changed.connect(self._on_format_changed)
        self._quality_combo = QComboBox()
        self._quality_label = label("Débit", "sliderName")
        self._sample_rate_combo = QComboBox()
        for name, _value in _SAMPLE_RATES:
            self._sample_rate_combo.addItem(name)
        self._sample_rate_combo.setCurrentIndex(_DEFAULT_SAMPLE_RATE_INDEX)

        # Aperçu du résultat fusionné
        self._preview_duration_label = label("—", "valueMono")
        self._preview_button = icon_button("play", size=56)
        self._preview_button.setProperty("accent", "true")
        set_button_icon(self._preview_button, "play", size=22)
        self._preview_button.clicked.connect(self._on_preview_clicked)
        self._preview_strip = MergedWaveStrip()
        self._preview_player = QMediaPlayer(self)
        self._preview_player.setAudioOutput(QAudioOutput(self))
        self._preview_player.positionChanged.connect(self._on_preview_position)
        self._preview_player.mediaStatusChanged.connect(self._on_preview_status)

        # Ce qui est exporté
        self._single_file_radio = QRadioButton("Un seul fichier fusionné")
        self._single_file_radio.setChecked(True)
        self._separate_radio = QRadioButton("")
        self._separate_radio.toggled.connect(self._on_separate_toggled)
        self._normalize_cb = QCheckBox("Normaliser le volume à l'export")
        self._normalize_cb.toggled.connect(lambda checked: self._lufs_spin.setEnabled(checked))
        self._lufs_spin = QDoubleSpinBox()
        self._lufs_spin.setRange(-30.0, -5.0)
        self._lufs_spin.setSingleStep(1.0)
        self._lufs_spin.setValue(-16.0)
        self._lufs_spin.setSuffix(" LUFS")
        self._lufs_spin.setEnabled(False)
        self._lufs_spin.setFixedWidth(120)

        # Destination
        self._path_edit = QLineEdit()
        self._browse_button = QPushButton("Parcourir…")
        self._browse_button.setMinimumHeight(44)
        self._browse_button.clicked.connect(self._on_browse_clicked)
        self._open_folder_cb = QCheckBox("Ouvrir le dossier à la fin de l'export")

        # Progression
        self._progress_title = label("", "settingName")
        self._progress_percent = label("0 %", "accentValue")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.valueChanged.connect(self._refresh_remaining)
        self._progress_hint = label(_CANCEL_NOTE, "settingHint")
        self._status_label = label("", "footerNote")

        # Pied de page
        self._cancel_button = QPushButton("Annuler")
        self._cancel_button.setMinimumHeight(46)
        self._cancel_button.setMinimumWidth(150)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        self._export_button = accent_button("Exporter")
        self._export_button.setMinimumHeight(46)
        self._export_button.setMinimumWidth(180)
        self._export_button.setDefault(True)
        self._export_button.setToolTip("Lancer l'export (Entrée)")
        self._export_button.clicked.connect(self._on_export_clicked)

    def _build_layout(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        grid.addWidget(self._build_merge_card(), 0, 0)
        grid.addWidget(self._build_format_card(), 0, 1)
        grid.addWidget(self._build_preview_card(), 1, 0)
        grid.addWidget(self._build_exported_card(), 1, 1)
        grid.addWidget(self._build_destination_card(), 2, 0, 1, 2)
        grid.addWidget(self._build_progress_card(), 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 20)
        content_layout.addLayout(grid)
        content_layout.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(area, 1)
        layout.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label("Fusion et export", "dialogTitle"))
        texts.addWidget(self._subtitle_label)

        header = QWidget()
        header.setObjectName("dialogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 20, 20, 20)
        layout.addLayout(texts, 1)
        layout.addWidget(self._close_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_merge_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Fusion des séquences"))
        layout.addWidget(self._simple_merge_radio)
        layout.addWidget(self._crossfade_radio)
        layout.addWidget(self._crossfade_slider)
        layout.addWidget(self._merge_hint)
        layout.addStretch(1)
        return card

    def _build_format_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Format de sortie"))
        layout.addWidget(self._format_segments)

        fields = QGridLayout()
        fields.setHorizontalSpacing(16)
        fields.setVerticalSpacing(6)
        fields.addWidget(self._quality_label, 0, 0)
        fields.addWidget(label("Échantillonnage", "sliderName"), 0, 1)
        fields.addWidget(self._quality_combo, 1, 0)
        fields.addWidget(self._sample_rate_combo, 1, 1)
        layout.addLayout(fields)
        layout.addStretch(1)
        return card

    def _build_preview_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Aperçu du résultat fusionné", self._preview_duration_label))

        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(self._preview_button)
        row.addWidget(self._preview_strip, 1)
        layout.addLayout(row)
        layout.addWidget(label(_JUNCTION_NOTE, "settingHint"))
        layout.addStretch(1)
        return card

    def _build_exported_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Ce qui est exporté"))
        layout.addWidget(self._single_file_radio)
        layout.addWidget(self._separate_radio)
        layout.addWidget(_separator())

        normalize_row = QHBoxLayout()
        normalize_row.setSpacing(10)
        normalize_row.addWidget(self._normalize_cb, 1)
        normalize_row.addWidget(self._lufs_spin)
        layout.addLayout(normalize_row)
        layout.addStretch(1)
        return card

    def _build_destination_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Destination", label("proposée à côté de la vidéo source", "cardHint")))

        row = QHBoxLayout()
        row.setSpacing(12)
        self._path_edit.setMinimumHeight(44)
        row.addWidget(self._path_edit, 1)
        row.addWidget(self._browse_button)
        layout.addLayout(row)
        layout.addWidget(self._open_folder_cb)
        return card

    def _build_progress_card(self) -> QWidget:
        card, layout = card_layout(spacing=10, margin=18)
        header = QHBoxLayout()
        header.addWidget(self._progress_title, 1)
        header.addWidget(self._progress_percent)
        layout.addLayout(header)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._progress_hint)
        self._progress_card = card
        card.hide()
        return card

    def _build_footer(self) -> QWidget:
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label(_FOOTER_NOTE, "footerNote"))
        texts.addWidget(self._status_label)

        footer = QWidget()
        footer.setObjectName("dialogFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(12)
        layout.addLayout(texts, 1)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._export_button)
        return footer

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # La hauteur d'un libellé replié dépend de la police, que la feuille de style n'impose
        # qu'une fois la fenêtre affichée : on fige ici la hauteur voulue pour que la dernière
        # ligne de l'explication du fondu ne soit pas rognée.
        hint = self._merge_hint
        hint.setMinimumHeight(hint.heightForWidth(max(hint.width(), 1)))

    # --- Thème ------------------------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self._preview_strip.set_theme(theme)

    # --- En-tête et fusion --------------------------------------------------------

    @property
    def _ordered_sequences(self) -> list:
        return sorted(self._project.sequences, key=lambda seq: seq.order)

    def _crossfade_seconds(self) -> float:
        """Durée du fondu retenue : zéro tant que « fusion simple » est choisie."""
        if not self._crossfade_radio.isChecked():
            return 0.0
        return self._crossfade_slider.value() / 1000.0

    def _estimated_duration(self) -> float:
        sequences = self._ordered_sequences
        total = sum(seq.duration for seq in sequences)
        junctions = max(len(sequences) - 1, 0)
        return max(total - self._crossfade_seconds() * junctions, 0.0)

    def _refresh_header(self) -> None:
        count = len(self._project.sequences)
        plural = "s" if count > 1 else ""
        self._subtitle_label.setText(
            f"{count} séquence{plural} · durée estimée du résultat {format_timecode(self._estimated_duration())[:8]}"
        )
        self._separate_radio.setText(f"Un fichier par séquence ({count} fichier{plural})")

    def _on_merge_mode_changed(self, *_args) -> None:
        """Le fondu ne se règle que s'il est choisi, et son effet est chiffré sous le curseur."""
        active = self._crossfade_radio.isChecked()
        self._crossfade_slider.setEnabled(active)
        junctions = max(len(self._project.sequences) - 1, 0)
        if not active or junctions == 0:
            self._merge_hint.setText("Les séquences sont mises bout à bout, sans transition.")
        else:
            lost = self._crossfade_seconds() * junctions
            self._merge_hint.setText(
                f"Le fondu est appliqué sur les {junctions} jonctions ; "
                f"la durée totale diminue de {lost:.2f} s.".replace(".", ",")
            )
        if self.isVisible():
            self._merge_hint.setMinimumHeight(self._merge_hint.heightForWidth(max(self._merge_hint.width(), 1)))
        self._project.crossfade_duration = self._crossfade_seconds()
        self._invalidate_preview()
        self._refresh_header()

    # --- Format et destination ------------------------------------------------------

    def _on_format_changed(self, fmt: str) -> None:
        self._quality_combo.clear()
        for name, _code in _QUALITY_OPTIONS[fmt]:
            self._quality_combo.addItem(name)
        self._quality_label.setText("Résolution" if fmt in _BIT_DEPTH_FORMATS else "Débit")
        self._refresh_suggested_path()

    def _selected_quality_code(self) -> str:
        fmt = self._format_segments.value()
        return _QUALITY_OPTIONS[fmt][max(self._quality_combo.currentIndex(), 0)][1]

    def _selected_sample_rate(self) -> int | None:
        rate = _SAMPLE_RATES[self._sample_rate_combo.currentIndex()][1]
        return rate or None

    def _suggested_path(self) -> str:
        """Destination proposée : à côté de la vidéo source, nommée d'après elle."""
        source = self._project.source_video
        if source is None:
            return ""
        video = Path(source.path)
        if self._separate_radio.isChecked():
            return str(video.parent / f"{video.stem}_sequences")
        return str(video.parent / f"{video.stem}_audio.{self._format_segments.value().lower()}")

    def _refresh_suggested_path(self) -> None:
        """Met à jour la destination proposée sans écraser un chemin saisi par l'utilisateur."""
        current = self._path_edit.text().strip()
        if current and current != self._auto_path:
            return
        self._auto_path = self._suggested_path()
        self._path_edit.setText(self._auto_path)

    def _on_separate_toggled(self, _checked: bool) -> None:
        self._path_edit.clear()
        self._refresh_suggested_path()

    def _on_browse_clicked(self) -> None:
        if self._separate_radio.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Dossier d'export")
            if path:
                self._path_edit.setText(path)
            return
        fmt = self._format_segments.value().lower()
        path, _ = QFileDialog.getSaveFileName(self, "Exporter vers…", "", f"Fichier {fmt.upper()} (*.{fmt})")
        if path:
            self._path_edit.setText(path)

    # --- Aperçu du résultat fusionné --------------------------------------------------

    def _junction_fractions(self, total_duration: float) -> list[float]:
        """Positions des raccords dans le résultat, en fraction de sa durée."""
        sequences = self._ordered_sequences
        if total_duration <= 0 or len(sequences) < 2:
            return []
        crossfade = self._crossfade_seconds()
        fractions, elapsed = [], 0.0
        for sequence in sequences[:-1]:
            elapsed += sequence.duration - crossfade
            fractions.append(min(max(elapsed / total_duration, 0.0), 1.0))
        return fractions

    def _invalidate_preview(self) -> None:
        """Les réglages de fusion ont changé : l'aperçu déjà calculé ne les reflète plus."""
        self._preview_player.stop()
        self._preview_path = ""
        self._preview_strip.clear()
        self._preview_duration_label.setText("—")
        set_button_icon(self._preview_button, "play", size=22)

    def _on_preview_clicked(self) -> None:
        if self._preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._preview_player.pause()
            set_button_icon(self._preview_button, "play", size=22)
            return
        if self._preview_path:
            self._preview_player.play()
            set_button_icon(self._preview_button, "pause", size=22)
            return
        if not self._project.sequences or self._preview_worker is not None:
            return

        self._preview_button.setEnabled(False)
        self._preview_duration_label.setText("…")
        project, service = self._project, self._ffmpeg_service
        self._preview_worker = FFmpegTaskWorker(lambda: merge_sequences(project, service))
        self._preview_worker.succeeded.connect(self._on_preview_ready)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()

    def _on_preview_ready(self, path: str) -> None:
        self._preview_worker = None
        self._preview_button.setEnabled(True)
        self._preview_path = path
        duration = wav_duration(path)
        self._preview_duration_label.setText(format_clock(duration))
        self._preview_strip.set_wave(compute_peaks(path, _PREVIEW_PEAKS), self._junction_fractions(duration))
        self._preview_player.setSource(QUrl.fromLocalFile(path))
        self._preview_player.play()
        set_button_icon(self._preview_button, "pause", size=22)

    def _on_preview_failed(self, message: str) -> None:
        self._preview_worker = None
        self._preview_button.setEnabled(True)
        self._preview_duration_label.setText("—")
        self._status_label.setText("L'aperçu n'a pas pu être préparé.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def _on_preview_position(self, position_ms: int) -> None:
        duration = self._preview_player.duration()
        if duration > 0:
            self._preview_strip.set_progress(position_ms / duration)

    def _on_preview_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._preview_strip.set_progress(None)
            set_button_icon(self._preview_button, "play", size=22)

    # --- Export -----------------------------------------------------------------------

    @property
    def _exporting(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _on_export_clicked(self) -> None:
        out_path = self._path_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "AudioCut Studio", "Veuillez choisir une destination.")
            return

        fmt = self._format_segments.value()
        quality = self._selected_quality_code()
        sample_rate = self._selected_sample_rate()
        separate = self._separate_radio.isChecked()
        normalize_lufs = self._lufs_spin.value() if self._normalize_cb.isChecked() else None
        self._exported_folder = out_path if separate else str(Path(out_path).parent)

        self._set_exporting(True)
        exporter = export_sequences_separately if separate else export_project
        project, service = self._project, self._ffmpeg_service
        self._worker = ExportWorker(
            lambda report, announce, should_cancel: exporter(
                project,
                service,
                out_path,
                fmt,
                quality,
                normalize_lufs,
                on_progress=report,
                sample_rate=sample_rate,
                on_stage=announce,
                should_cancel=should_cancel,
            )
        )
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.stage.connect(lambda stage: self._progress_title.setText(f"Export en cours — {stage}"))
        self._worker.succeeded.connect(lambda _: self._on_export_succeeded(out_path))
        self._worker.failed.connect(self._on_export_failed)
        self._worker.cancelled.connect(self._on_export_cancelled)
        self._worker.start()

    def _set_exporting(self, exporting: bool) -> None:
        self._export_button.setEnabled(not exporting)
        self._cancel_button.setText("Interrompre l'export" if exporting else "Annuler")
        self._progress_card.setVisible(exporting)
        if exporting:
            self._progress_bar.setValue(0)
            self._progress_title.setText("Export en cours…")
            self._progress_percent.setText("0 %")
            self._progress_hint.setText(_CANCEL_NOTE)
            self._elapsed.restart()
            self._status_label.setText("")

    def _refresh_remaining(self, percent: int) -> None:
        """Temps restant déduit du temps déjà passé : une estimation, annoncée comme telle."""
        self._progress_percent.setText(f"{percent} %")
        if percent <= 0 or not self._elapsed.isValid():
            self._progress_hint.setText(_CANCEL_NOTE)
            return
        elapsed = self._elapsed.elapsed() / 1000.0
        remaining = elapsed * (100 - percent) / percent
        self._progress_hint.setText(f"Temps restant estimé : {remaining:.0f} s. {_CANCEL_NOTE}")

    def _on_cancel_clicked(self) -> None:
        if self._exporting:
            self._worker.cancel()
            self._progress_title.setText("Interruption en cours…")
            return
        self.reject()

    def _on_export_succeeded(self, out_path: str) -> None:
        self._set_exporting(False)
        self._status_label.setText(f"Export terminé : {out_path}")
        QMessageBox.information(self, "AudioCut Studio", f"Export terminé avec succès :\n{out_path}")
        if self._open_folder_cb.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._exported_folder))
        self.accept()

    def _on_export_cancelled(self) -> None:
        self._set_exporting(False)
        self._status_label.setText("Export interrompu — le projet est intact.")

    def _on_export_failed(self, message: str) -> None:
        self._set_exporting(False)
        self._status_label.setText("Échec de l'export.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def closeEvent(self, event) -> None:
        """Ferme sans laisser d'export en cours : on l'interrompt plutôt que de le laisser orphelin."""
        if self._exporting:
            self._worker.cancel()
            self._worker.wait(3000)
        self._preview_player.stop()
        super().closeEvent(event)
