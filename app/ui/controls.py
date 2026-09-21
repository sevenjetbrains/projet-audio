"""Contrôles réutilisables de la maquette : interrupteur, boutons segmentés, ligne de curseur.

Qt n'a pas d'interrupteur à bascule ni de groupe de boutons segmenté ; les deux sont
dessinés/assemblés ici pour que les écrans n'aient qu'à les composer. Les couleurs
viennent du thème courant : les widgets peints exposent `set_theme`, appelé par la
fenêtre comme pour la waveform.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QWidget,
)

from app.config.themes import Theme, get_theme
from app.ui.design import label

_SWITCH_WIDTH = 52
_SWITCH_HEIGHT = 28
_SWITCH_MARGIN = 3.0


class ToggleSwitch(QAbstractButton):
    """Interrupteur pilule : accent quand il est actif, gris sinon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(_SWITCH_WIDTH, _SWITCH_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme: Theme = get_theme("")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        track = QRectF(0, 0, self.width(), self.height())
        radius = self.height() / 2
        token = "accent" if self.isChecked() else "border_strong"
        painter.setBrush(QColor(self._theme.color(token if self.isEnabled() else "border")))
        painter.drawRoundedRect(track, radius, radius)

        knob_radius = radius - _SWITCH_MARGIN
        # Bouton à droite quand l'interrupteur est actif, à gauche sinon.
        centre_x = self.width() - radius if self.isChecked() else radius
        painter.setBrush(QColor(self._theme.color("bg" if self.isChecked() else "text_on_accent")))
        painter.drawEllipse(QPointF(centre_x, radius), knob_radius, knob_radius)
        painter.end()


class SegmentedControl(QWidget):
    """Suite de boutons exclusifs (« Aucune · Faible · Moyenne · Forte »), le choix en accent.

    `columns` répartit les options sur plusieurs lignes (les six formats d'export tiennent
    en 3 × 2) ; par défaut elles restent toutes sur une seule ligne."""

    changed = Signal(str)

    def __init__(self, options: tuple[str, ...], columns: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._options = options
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        per_row = columns or len(options)
        for index, option in enumerate(options):
            button = QPushButton(option)
            button.setCheckable(True)
            button.setProperty("segment", "true")
            button.setMinimumHeight(40)
            self._group.addButton(button, index)
            layout.addWidget(button, index // per_row, index % per_row)
        for column in range(per_row):
            layout.setColumnStretch(column, 1)
        self._group.idToggled.connect(self._on_toggled)
        self.set_value(options[0])

    def _on_toggled(self, index: int, checked: bool) -> None:
        if checked:
            self._repolish()
            self.changed.emit(self._options[index])

    def _repolish(self) -> None:
        """La feuille de style cible `:checked` : il faut la réappliquer au changement."""
        for button in self._group.buttons():
            button.style().unpolish(button)
            button.style().polish(button)

    def value(self) -> str:
        button = self._group.checkedButton()
        return button.text() if button is not None else self._options[0]

    def set_value(self, option: str) -> None:
        if option not in self._options:
            return
        button = self._group.button(self._options.index(option))
        was_blocked = self._group.signalsBlocked()
        self._group.blockSignals(True)
        button.setChecked(True)
        self._group.blockSignals(was_blocked)
        self._repolish()


class ProfileCard(QFrame):
    """Vignette de profil : son nom, et une coche à droite quand c'est celui qui est appliqué.

    Un profil enregistré par l'utilisateur (`removable`) se supprime par un clic droit ;
    les profils prédéfinis, eux, font partie de l'application."""

    clicked = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, name: str, removable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._removable = removable
        if removable:
            self.setToolTip("Profil enregistré — clic droit pour le supprimer")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # sans quoi le `:hover` de la feuille de style dort
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._name_label = label(name, "profileName")
        self._check_label = label("✓", "profileNameSelected")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(self._name_label)
        layout.addStretch(1)
        layout.addWidget(self._check_label)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("profile", "true" if selected else "false")
        self._name_label.setObjectName("profileNameSelected" if selected else "profileName")
        self._check_label.setVisible(selected)
        for widget in (self, self._name_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def mouseReleaseEvent(self, event) -> None:
        if not self.rect().contains(event.position().toPoint()):
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._name)
        elif event.button() == Qt.MouseButton.RightButton and self._removable:
            self.delete_requested.emit(self._name)
        super().mouseReleaseEvent(event)


class SliderRow(QWidget):
    """Ligne « libellé ——●—— valeur » : un QSlider entier qui expose une valeur décimale.

    QSlider ne connaît que les entiers ; `scale` est le nombre de crans par unité (10 pour
    un dixième de dB), ce qui garde le réglage fin tout en affichant « -3,0 dB »."""

    value_changed = Signal(float)

    def __init__(
        self,
        name: str,
        minimum: float,
        maximum: float,
        unit: str,
        scale: int = 10,
        decimals: int = 1,
        signed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scale = scale
        self._decimals = decimals
        self._unit = unit
        self._signed = signed

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setProperty("plain", "true")  # gorge unie : une valeur signée n'a pas d'origine à gauche
        self._slider.setRange(int(minimum * scale), int(maximum * scale))
        self._slider.valueChanged.connect(self._on_slider_moved)

        self._value_label = label("", "valueMono")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._value_label.setMinimumWidth(92)
        self._value_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        name_label = label(name, "sliderName")
        name_label.setMinimumWidth(86)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(name_label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value_label)
        self._refresh_label()

    def _on_slider_moved(self, _raw: int) -> None:
        self._refresh_label()
        self.value_changed.emit(self.value())

    def _refresh_label(self) -> None:
        text = f"{self.value():+.{self._decimals}f}" if self._signed else f"{self.value():.{self._decimals}f}"
        self._value_label.setText(f"{text.replace('.', ',')} {self._unit}")

    def value(self) -> float:
        return self._slider.value() / self._scale

    def set_value(self, value: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(round(value * self._scale)))
        self._slider.blockSignals(False)
        self._refresh_label()

    @property
    def slider(self) -> QSlider:
        return self._slider
