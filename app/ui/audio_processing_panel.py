"""Fenêtre de traitement audio : profils à gauche, réglages en cartes à droite.

Disposition conforme à la maquette : un en-tête qui rappelle sur quoi le traitement
portera, une colonne de profils qui pré-règlent tout, des cartes thématiques
(bruit, nettoyage, compression / égaliseur, normalisation, gain), et un pied de page
qui rappelle que rien n'est destructif avant de lancer le traitement.
"""

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.audio_profiles import AUDIO_PROFILES, CUSTOM_PROFILE_LABEL
from app.config.themes import Theme
from app.models.audio_settings import AudioSettings
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import audio_processor
from app.services.ffmpeg_service import FFmpegService
from app.ui.controls import ProfileCard, SegmentedControl, SliderRow, ToggleSwitch
from app.ui.design import accent_button, card_layout, flat_button, label, section_label
from app.ui.icons import set_button_icon
from app.ui.shortcuts import set_button_shortcut
from app.ui.undo_commands import CallbackCommand
from app.utils.progress import sub_progress
from app.workers.ffmpeg_worker import FFmpegTaskWorker

_PROFILES_WIDTH = 300
_NOISE_LEVELS = ("Aucune", "Faible", "Moyenne", "Forte")
_PROFILE_HINT = "Un profil pré-règle tous les paramètres à droite. Chaque réglage reste modifiable ensuite."
_NON_DESTRUCTIVE_NOTE = (
    "Traitement non destructif : vous pourrez revenir au son brut de chaque séquence, "
    "ou annuler avec Ctrl+Z."
)
_COMPRESSION_NOTE = (
    "Réglage adapté à la voix : resserre les écarts sans écraser la dynamique."
)


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


def _setting_row(name: str, hint: str, *trailing: QWidget) -> QWidget:
    """Ligne « intitulé / explication ………… contrôle(s) », comme les bascules du nettoyage."""
    texts = QVBoxLayout()
    texts.setSpacing(2)
    texts.addWidget(label(name, "settingName"))
    if hint:
        texts.addWidget(label(hint, "settingHint"))

    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addLayout(texts, 1)
    for widget in trailing:
        layout.addWidget(widget)
    return row


class AudioProcessingPanel(QWidget):
    processed = Signal()
    close_requested = Signal()

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None
        self._sequence: Sequence | None = None
        self._worker: FFmpegTaskWorker | None = None
        self._selected_sequences: list[Sequence] = []
        self._undo_stack: QUndoStack | None = None
        self._pending: tuple[str, list[Sequence], list[tuple]] | None = None
        self._current_profile = CUSTOM_PROFILE_LABEL

        self._build_widgets()
        self.setLayout(self._build_layout())
        self._set_editing_enabled(False)

    # --- Construction ---------------------------------------------------------

    def _build_widgets(self) -> None:
        self._title_label = label("Traitement audio", "dialogTitle")
        self._subtitle_label = label("", "dialogSubtitle")

        self._profile_cards: dict[str, ProfileCard] = {}
        for name in AUDIO_PROFILES:
            card = ProfileCard(name)
            card.clicked.connect(self._select_profile)
            self._profile_cards[name] = card

        self._noise_segments = SegmentedControl(_NOISE_LEVELS)
        self._noise_segments.changed.connect(self._on_setting_edited)

        self._bass_slider = SliderRow("Basses", -12.0, 12.0, "dB", signed=True)
        self._mid_slider = SliderRow("Médiums", -12.0, 12.0, "dB", signed=True)
        self._treble_slider = SliderRow("Aigus", -12.0, 12.0, "dB", signed=True)

        self._dehum_toggle = ToggleSwitch()
        self._dehum_freq_combo = QComboBox()
        self._dehum_freq_combo.addItems(["50 Hz", "60 Hz"])
        self._dehum_freq_combo.setFixedWidth(96)
        self._declick_toggle = ToggleSwitch()

        self._normalize_toggle = ToggleSwitch()
        self._peak_radio = QRadioButton("Par crête (peak) — cible")
        self._loudness_radio = QRadioButton("Par loudness (LUFS)")
        self._peak_spin = QDoubleSpinBox()
        self._peak_spin.setRange(-12.0, 0.0)
        self._peak_spin.setSingleStep(0.5)
        self._peak_spin.setDecimals(1)
        self._peak_spin.setSuffix(" dBFS")
        self._peak_spin.setFixedWidth(110)
        self._lufs_slider = SliderRow("Cible", -30.0, -5.0, "LUFS", scale=1, decimals=0)

        self._compression_toggle = ToggleSwitch()
        self._ratio_slider = SliderRow("Ratio", 1.0, 10.0, ": 1")
        self._threshold_slider = SliderRow("Seuil", -60.0, 0.0, "dB", scale=1, decimals=0)

        self._gain_slider = SliderRow("Gain", -12.0, 12.0, "dB", signed=True)
        self._fade_in_spin = self._make_ms_spin()
        self._fade_out_spin = self._make_ms_spin()

        self._silence_toggle = ToggleSwitch()
        self._silence_threshold_slider = SliderRow("Seuil", -60.0, -10.0, "dB", scale=1, decimals=0)
        self._silence_min_duration_spin = self._make_ms_spin(maximum=5000, step=50)
        self._silence_keep_padding_spin = self._make_ms_spin(maximum=2000, step=10)

        self._close_button = QPushButton()
        self._close_button.setFixedSize(44, 44)
        self._close_button.setProperty("flat", "true")
        self._close_button.setToolTip("Fermer")
        set_button_icon(self._close_button, "close", size=18)
        self._close_button.clicked.connect(self.close_requested.emit)

        self._apply_button = accent_button("Appliquer")
        self._apply_button.setMinimumHeight(46)
        self._apply_button.setMinimumWidth(210)
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._cancel_button = QPushButton("Annuler")
        self._cancel_button.setMinimumHeight(46)
        self._cancel_button.setMinimumWidth(150)
        self._cancel_button.clicked.connect(self.close_requested.emit)
        self._reset_button = flat_button("Réinitialiser le traitement")
        self._reset_button.clicked.connect(self._on_reset_clicked)

        set_button_shortcut(self._apply_button, "Ctrl+Return", "Appliquer le traitement")
        set_button_shortcut(self._reset_button, "Ctrl+R", "Réinitialiser le traitement")

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        self._status_label = label("Sélectionnez une séquence.", "footerNote")

        for toggle in self._toggles:
            toggle.toggled.connect(self._on_setting_edited)
        for slider in self._sliders:
            slider.value_changed.connect(self._on_setting_edited)
        self._dehum_freq_combo.currentTextChanged.connect(self._on_setting_edited)
        for spin in (self._peak_spin, self._fade_in_spin, self._fade_out_spin):
            spin.valueChanged.connect(self._on_setting_edited)
        for radio in (self._peak_radio, self._loudness_radio):
            radio.toggled.connect(self._on_normalize_mode_changed)

    @property
    def _toggles(self) -> tuple[ToggleSwitch, ...]:
        return (
            self._dehum_toggle,
            self._declick_toggle,
            self._normalize_toggle,
            self._compression_toggle,
            self._silence_toggle,
        )

    @property
    def _sliders(self) -> tuple[SliderRow, ...]:
        return (
            self._bass_slider,
            self._mid_slider,
            self._treble_slider,
            self._lufs_slider,
            self._ratio_slider,
            self._threshold_slider,
            self._gain_slider,
            self._silence_threshold_slider,
        )

    @staticmethod
    def _make_ms_spin(maximum: int = 10000, step: int = 10) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.setSingleStep(step)
        spin.setSuffix(" ms")
        return spin

    def _build_layout(self) -> QVBoxLayout:
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_profiles_column())
        body.addWidget(self._build_settings_area(), 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addLayout(body, 1)
        layout.addWidget(self._build_footer())
        return layout

    def _build_header(self) -> QWidget:
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(self._title_label)
        texts.addWidget(self._subtitle_label)

        header = QWidget()
        header.setObjectName("dialogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 20, 20, 20)
        layout.addLayout(texts, 1)
        layout.addWidget(self._close_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_profiles_column(self) -> QWidget:
        hint_card, hint_layout = card_layout("soft", margin=14)
        hint = label(_PROFILE_HINT, "settingHint")
        hint.setWordWrap(True)
        # Un libellé replié n'annonce sa hauteur que si sa largeur est fixée : sans cela, la
        # carte est dimensionnée pour une seule ligne et la fin du texte disparaît.
        hint.setFixedWidth(_PROFILES_WIDTH - 2 * 22 - 2 * 14)
        self._profile_hint = hint
        hint_layout.addWidget(hint)

        column = QWidget()
        column.setObjectName("profilesColumn")
        column.setFixedWidth(_PROFILES_WIDTH)
        self._profiles_column = column
        layout = QVBoxLayout(column)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(section_label("Profils"))
        layout.addSpacing(4)
        for card in self._profile_cards.values():
            layout.addWidget(card)
        layout.addStretch(1)
        layout.addWidget(hint_card)
        layout.addWidget(self._reset_button)
        return column

    def _build_settings_area(self) -> QWidget:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        grid.addWidget(self._build_noise_card(), 0, 0)
        grid.addWidget(self._build_equalizer_card(), 0, 1)
        grid.addWidget(self._build_cleanup_card(), 1, 0)
        grid.addWidget(self._build_normalize_card(), 1, 1)
        grid.addWidget(self._build_compression_card(), 2, 0)
        grid.addWidget(self._build_gain_card(), 2, 1)
        grid.addWidget(self._build_silence_card(), 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(4, 1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 20)
        content_layout.addLayout(grid)
        content_layout.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(content)
        self._settings_area = area
        return area

    def _build_noise_card(self) -> QWidget:
        card, layout = card_layout(spacing=14, margin=18)
        layout.addLayout(_card_header("Réduction de bruit", label("souffle, climatisation", "cardHint")))
        layout.addWidget(self._noise_segments)
        layout.addStretch(1)
        return card

    def _build_equalizer_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Égaliseur 3 bandes"))
        for slider in (self._bass_slider, self._mid_slider, self._treble_slider):
            layout.addWidget(slider)
        layout.addStretch(1)
        return card

    def _build_cleanup_card(self) -> QWidget:
        card, layout = card_layout(spacing=14, margin=18)
        layout.addLayout(_card_header("Nettoyage"))
        layout.addWidget(
            _setting_row(
                "Anti-ronflement (de-hum)",
                "fondamentale et harmoniques",
                self._dehum_freq_combo,
                self._dehum_toggle,
            )
        )
        layout.addWidget(_separator())
        layout.addWidget(_setting_row("De-click", "clics de bouche et craquements", self._declick_toggle))
        layout.addStretch(1)
        return card

    def _build_normalize_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Normalisation", self._normalize_toggle))

        peak_row = QHBoxLayout()
        peak_row.setSpacing(10)
        peak_row.addWidget(self._peak_radio)
        peak_row.addStretch(1)
        peak_row.addWidget(self._peak_spin)

        layout.addLayout(peak_row)
        layout.addWidget(self._loudness_radio)
        layout.addWidget(self._lufs_slider)
        layout.addStretch(1)
        return card

    def _build_compression_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Compression légère", self._compression_toggle))
        note = label(_COMPRESSION_NOTE, "settingHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self._ratio_slider)
        layout.addWidget(self._threshold_slider)
        layout.addStretch(1)
        return card

    def _build_gain_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Gain et fondus"))
        layout.addWidget(self._gain_slider)

        fades = QGridLayout()
        fades.setHorizontalSpacing(16)
        fades.setVerticalSpacing(6)
        fades.addWidget(label("Fondu d'entrée", "sliderName"), 0, 0)
        fades.addWidget(label("Fondu de sortie", "sliderName"), 0, 1)
        fades.addWidget(self._fade_in_spin, 1, 0)
        fades.addWidget(self._fade_out_spin, 1, 1)
        layout.addLayout(fades)
        layout.addStretch(1)
        return card

    def _build_silence_card(self) -> QWidget:
        card, layout = card_layout(spacing=12, margin=18)
        layout.addLayout(_card_header("Suppression des silences", self._silence_toggle))
        layout.addWidget(self._silence_threshold_slider)

        durations = QGridLayout()
        durations.setHorizontalSpacing(16)
        durations.setVerticalSpacing(6)
        durations.addWidget(label("Durée minimale d'un silence", "sliderName"), 0, 0)
        durations.addWidget(label("Marge conservée autour", "sliderName"), 0, 1)
        durations.addWidget(self._silence_min_duration_spin, 1, 0)
        durations.addWidget(self._silence_keep_padding_spin, 1, 1)
        layout.addLayout(durations)
        return card

    def _build_footer(self) -> QWidget:
        note = label(_NON_DESTRUCTIVE_NOTE, "footerNote")
        note.setWordWrap(True)
        note.setMaximumWidth(520)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(note)
        texts.addWidget(self._status_label)
        texts.addWidget(self._progress_bar)

        footer = QWidget()
        footer.setObjectName("dialogFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(12)
        layout.addLayout(texts, 1)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._apply_button)
        return footer

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # La hauteur d'un libellé replié dépend de la police, que la feuille de style n'impose
        # qu'une fois la fenêtre affichée : on fige ici la hauteur voulue pour que la carte ne
        # puisse plus être rognée quand la colonne manque de place.
        hint = self._profile_hint
        hint.setMinimumHeight(hint.heightForWidth(hint.width()))

    # --- Thème ---------------------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        """Répercute le thème sur les interrupteurs, qui sont peints au QPainter."""
        for toggle in self._toggles:
            toggle.set_theme(theme)

    # --- Accès de la fenêtre principale ---------------------------------------

    def set_undo_stack(self, undo_stack: QUndoStack | None) -> None:
        """Pile Undo/Redo partagée avec la liste des séquences : traitements et réinitialisations y sont annulables."""
        self._undo_stack = undo_stack

    def set_project(self, project: Project) -> None:
        self._project = project

    def set_selected_sequences(self, sequences: list[Sequence]) -> None:
        """Séquences ciblées par « Appliquer » : la sélection entière dès qu'il y en a plusieurs."""
        self._selected_sequences = list(sequences)
        self._refresh_target_labels()

    def _set_editing_enabled(self, enabled: bool) -> None:
        """Grise ce qui n'a pas de sens sans séquence — mais jamais la croix ni « Annuler »,
        sans quoi la fenêtre ouverte sur aucune séquence ne pourrait plus être refermée."""
        self._settings_area.setEnabled(enabled)
        self._profiles_column.setEnabled(enabled)
        self._apply_button.setEnabled(enabled)
        self._reset_button.setEnabled(enabled)

    def set_sequence(self, sequence: Sequence | None) -> None:
        self._sequence = sequence
        self._set_editing_enabled(sequence is not None)
        self._select_profile(CUSTOM_PROFILE_LABEL, load=False)
        self._load_settings(sequence.audio_settings if sequence else AudioSettings())
        self._refresh_target_labels()
        self._status_label.setText(
            f"Séquence : {sequence.name}" if sequence else "Sélectionnez une séquence."
        )

    @property
    def _target_sequences(self) -> list[Sequence]:
        """Séquences que « Appliquer » traitera : la sélection multiple, sinon la séquence courante."""
        if len(self._selected_sequences) > 1:
            return list(self._selected_sequences)
        return [self._sequence] if self._sequence is not None else []

    def _refresh_target_labels(self) -> None:
        count = len(self._target_sequences)
        if count > 1:
            self._subtitle_label.setText(
                f"{count} séquences sélectionnées · le fichier brut de chaque séquence est conservé"
            )
            self._apply_button.setText(f"Appliquer aux {count} séquences")
        else:
            self._subtitle_label.setText("le fichier brut de la séquence est conservé")
            self._apply_button.setText("Appliquer à la séquence")
        set_button_shortcut(self._apply_button, "Ctrl+Return", self._apply_button.text())

    # --- Profils ---------------------------------------------------------------

    def _select_profile(self, profile_name: str, load: bool = True) -> None:
        """Met le profil en évidence et, sauf indication contraire, charge ses réglages."""
        self._current_profile = profile_name
        for name, card in self._profile_cards.items():
            card.set_selected(name == profile_name)
        settings = AUDIO_PROFILES.get(profile_name)
        if load and settings is not None:
            self._load_settings(settings)

    def _on_setting_edited(self, *_args) -> None:
        """Toucher un réglage quitte le profil : il ne décrit plus ce qui est à l'écran."""
        if self._current_profile != CUSTOM_PROFILE_LABEL:
            self._select_profile(CUSTOM_PROFILE_LABEL, load=False)

    def _on_normalize_mode_changed(self, _checked: bool) -> None:
        self._peak_spin.setEnabled(self._peak_radio.isChecked())
        self._lufs_slider.setEnabled(self._loudness_radio.isChecked())
        self._on_setting_edited()

    # --- Lecture / écriture des réglages ----------------------------------------

    def _load_settings(self, settings: AudioSettings) -> None:
        widgets = (*self._toggles, *self._sliders, self._noise_segments, self._dehum_freq_combo,
                   self._peak_spin, self._fade_in_spin, self._fade_out_spin,
                   self._peak_radio, self._loudness_radio,
                   self._silence_min_duration_spin, self._silence_keep_padding_spin)
        for widget in widgets:
            widget.blockSignals(True)

        level = settings.noise_reduction_level.capitalize() if settings.noise_reduction else "Aucune"
        self._noise_segments.set_value(level if level in _NOISE_LEVELS else "Moyenne")
        self._dehum_toggle.setChecked(settings.de_hum)
        self._dehum_freq_combo.setCurrentText(f"{settings.de_hum_freq} Hz")
        self._declick_toggle.setChecked(settings.de_click)
        self._bass_slider.set_value(settings.eq_bass_db)
        self._mid_slider.set_value(settings.eq_mid_db)
        self._treble_slider.set_value(settings.eq_treble_db)
        self._compression_toggle.setChecked(settings.compression)
        self._ratio_slider.set_value(settings.compression_ratio)
        self._threshold_slider.set_value(settings.compression_threshold_db)
        self._normalize_toggle.setChecked(settings.normalize)
        self._peak_radio.setChecked(settings.normalize_mode == "peak")
        self._loudness_radio.setChecked(settings.normalize_mode != "peak")
        self._peak_spin.setValue(settings.normalize_peak_dbfs)
        self._lufs_slider.set_value(settings.normalize_target_lufs)
        self._gain_slider.set_value(settings.gain)
        self._fade_in_spin.setValue(int(round(settings.fade_in * 1000)))
        self._fade_out_spin.setValue(int(round(settings.fade_out * 1000)))
        self._silence_toggle.setChecked(settings.silence_removal)
        self._silence_threshold_slider.set_value(settings.silence_threshold_db)
        self._silence_min_duration_spin.setValue(int(round(settings.silence_min_duration * 1000)))
        self._silence_keep_padding_spin.setValue(int(round(settings.silence_keep_padding * 1000)))

        for widget in widgets:
            widget.blockSignals(False)
        self._peak_spin.setEnabled(self._peak_radio.isChecked())
        self._lufs_slider.setEnabled(self._loudness_radio.isChecked())

    def _read_settings(self) -> AudioSettings:
        level = self._noise_segments.value()
        return AudioSettings(
            gain=self._gain_slider.value(),
            fade_in=self._fade_in_spin.value() / 1000.0,
            fade_out=self._fade_out_spin.value() / 1000.0,
            noise_reduction=level != "Aucune",
            noise_reduction_level=level.lower() if level != "Aucune" else "moyenne",
            de_hum=self._dehum_toggle.isChecked(),
            de_hum_freq=int(self._dehum_freq_combo.currentText().split()[0]),
            de_click=self._declick_toggle.isChecked(),
            eq_bass_db=self._bass_slider.value(),
            eq_mid_db=self._mid_slider.value(),
            eq_treble_db=self._treble_slider.value(),
            compression=self._compression_toggle.isChecked(),
            compression_ratio=self._ratio_slider.value(),
            compression_threshold_db=self._threshold_slider.value(),
            normalize=self._normalize_toggle.isChecked(),
            normalize_mode="peak" if self._peak_radio.isChecked() else "loudness",
            normalize_target_lufs=self._lufs_slider.value(),
            normalize_peak_dbfs=self._peak_spin.value(),
            silence_removal=self._silence_toggle.isChecked(),
            silence_threshold_db=self._silence_threshold_slider.value(),
            silence_min_duration=self._silence_min_duration_spin.value() / 1000.0,
            silence_keep_padding=self._silence_keep_padding_spin.value() / 1000.0,
        )

    # --- Undo/redo --------------------------------------------------------------

    @staticmethod
    def _capture(sequence: Sequence) -> tuple:
        return (copy.deepcopy(sequence.audio_settings), sequence.processed_audio_path)

    @staticmethod
    def _restore(sequence: Sequence, state: tuple) -> None:
        sequence.audio_settings = copy.deepcopy(state[0])
        sequence.processed_audio_path = state[1]

    def _push_state_change(self, description: str, sequences: list[Sequence], before: list[tuple], after: list[tuple]) -> None:
        """Enregistre le passage de `before` à `after` comme une seule action annulable."""

        def apply(states: list[tuple]) -> None:
            for sequence, state in zip(sequences, states):
                self._restore(sequence, state)
            if self._sequence in sequences:
                self._load_settings(self._sequence.audio_settings)
            self.processed.emit()

        if self._undo_stack is None:
            apply(after)
            return
        self._undo_stack.push(CallbackCommand(description, lambda: apply(after), lambda: apply(before)))

    # --- Application du traitement ------------------------------------------------

    def _on_apply_clicked(self) -> None:
        """Applique les réglages courants à la séquence, ou à toute la sélection s'il y en a plusieurs."""
        sequences = self._target_sequences
        if self._project is None or not sequences:
            return

        settings = self._read_settings()
        description = (
            f"Traiter « {sequences[0].name} »" if len(sequences) == 1 else f"Traiter {len(sequences)} séquences"
        )
        self._pending = (description, sequences, [self._capture(seq) for seq in sequences])
        for sequence in sequences:
            sequence.audio_settings = copy.deepcopy(settings)

        self._set_busy(True, "Traitement en cours…" if len(sequences) == 1 else f"Traitement de {len(sequences)} séquences…")
        project = self._project
        total = len(sequences)
        self._worker = FFmpegTaskWorker(
            lambda report: [
                audio_processor.process_sequence(
                    project, seq, self._ffmpeg_service, sub_progress(report, i / total, (i + 1) / total)
                )
                for i, seq in enumerate(sequences)
            ],
            with_progress=True,
        )
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.succeeded.connect(self._on_processing_succeeded)
        self._worker.failed.connect(self._on_processing_failed)
        self._worker.start()

    def _set_busy(self, busy: bool, message: str) -> None:
        self._apply_button.setEnabled(not busy)
        if busy:
            self._progress_bar.setValue(0)
        self._progress_bar.setVisible(busy)
        self._status_label.setText(message)

    def _on_processing_succeeded(self, _result) -> None:
        self._set_busy(False, "Traitement appliqué.")
        pending, self._pending = self._pending, None
        if pending is None:
            self.processed.emit()
            return
        description, sequences, before = pending
        self._push_state_change(description, sequences, before, [self._capture(seq) for seq in sequences])

    def _on_processing_failed(self, message: str) -> None:
        # Le traitement a échoué : on rétablit les réglages/fichiers d'avant pour rester cohérent.
        pending, self._pending = self._pending, None
        if pending is not None:
            _description, sequences, before = pending
            for sequence, state in zip(sequences, before):
                self._restore(sequence, state)
        self._set_busy(False, "Échec du traitement.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def _on_reset_clicked(self) -> None:
        if self._sequence is None:
            return
        sequence = self._sequence
        before = self._capture(sequence)
        audio_processor.reset_processing(sequence)
        after = self._capture(sequence)
        self._push_state_change(f"Réinitialiser « {sequence.name} »", [sequence], [before], [after])
        self._select_profile(CUSTOM_PROFILE_LABEL, load=False)
        self._status_label.setText("Traitement réinitialisé.")
