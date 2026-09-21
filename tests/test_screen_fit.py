"""Tests : les fenêtres s'adaptent à n'importe quelle résolution d'écran (aucune ne dépasse la zone de travail).

Cas signalé : la fenêtre « Fusion et export » (900 px de haut) dépassait la zone de travail d'un écran 1080p à 125 %
(824 px) : son bas, avec les boutons Annuler / Exporter, passait sous la barre des tâches.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui import screen_fit
from app.ui.export_dialog import ExportDialog
from app.ui.processing_dialog import ProcessingDialog
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.screen_fit import (
    ABSOLUTE_MIN_SIZE,
    FRAME_ALLOWANCE,
    SCREEN_MARGIN,
    ScreenFittedDialog,
    fit_size,
    position_within,
)
from app.ui.split_preview_dialog import SplitPreviewDialog

# Zones de travail (barre des tâches exclue), en pixels logiques : de l'écran très petit au 4K.
_AREAS = {
    "800x600": QRect(0, 0, 800, 560),
    "1024x768": QRect(0, 0, 1024, 728),
    "1280x720": QRect(0, 0, 1280, 680),
    "1366x768": QRect(0, 0, 1366, 728),
    "1080p à 125 % (l'écran signalé)": QRect(0, 0, 1536, 824),
    "1080p à 100 %": QRect(0, 0, 1920, 1040),
    "1440p": QRect(0, 0, 2560, 1400),
    "4K à 150 %": QRect(0, 0, 2560, 1400),
    "4K à 100 %": QRect(0, 0, 3840, 2100),
    "second écran décalé": QRect(1920, -120, 1600, 900),
}
_AREA_IDS = list(_AREAS)


def _use_area(monkeypatch, area: QRect) -> None:
    """Simule l'écran : toutes les fenêtres mesurent la zone de travail donnée."""
    monkeypatch.setattr(screen_fit, "available_rect", lambda widget=None: area)
    monkeypatch.setattr("app.ui.main_window.available_rect", lambda widget=None: area)
    monkeypatch.setattr("app.ui.main_window.available_size", lambda widget=None: (area.width(), area.height()))


def _frame(widget) -> QRect:
    """Cadre de la fenêtre tel que `move()` le place : la zone cliente plus la barre de titre."""
    return QRect(widget.x(), widget.y(), widget.width(), widget.height() + FRAME_ALLOWANCE)


def _inside(rect: QRect, area: QRect) -> bool:
    return area.contains(rect.topLeft()) and area.contains(rect.bottomRight())


# ============================ règle de dimensionnement (fonctions pures) =====================================


@pytest.mark.parametrize("area_name", _AREA_IDS)
def test_fitted_size_always_fits_the_work_area(area_name):
    area = _AREAS[area_name]

    fitted = fit_size((1280, 900), (1120, 620), area)

    assert fitted.size.width() <= max(area.width() - 2 * SCREEN_MARGIN, ABSOLUTE_MIN_SIZE.width())
    assert fitted.size.height() + FRAME_ALLOWANCE + SCREEN_MARGIN <= max(area.height(), ABSOLUTE_MIN_SIZE.height() + FRAME_ALLOWANCE + SCREEN_MARGIN)
    assert fitted.minimum.width() <= fitted.size.width() and fitted.minimum.height() <= fitted.size.height()


def test_a_roomy_screen_keeps_the_preferred_size():
    fitted = fit_size((1280, 900), (1120, 620), QRect(0, 0, 3840, 2100))

    assert (fitted.size.width(), fitted.size.height()) == (1280, 900)
    assert (fitted.minimum.width(), fitted.minimum.height()) == (1120, 620)


def test_the_reported_screen_gets_a_window_that_leaves_room_for_the_title_bar():
    fitted = fit_size((1220, 900), (1080, 620), QRect(0, 0, 1536, 824))  # 1080p à 125 % : le cas signalé

    assert fitted.size.height() == 824 - FRAME_ALLOWANCE - SCREEN_MARGIN  # 764 au lieu de 900
    assert fitted.size.width() == 1220  # la largeur, elle, tient


def test_minimum_never_exceeds_the_available_room():
    fitted = fit_size((1280, 900), (1120, 620), QRect(0, 0, 800, 560))

    assert fitted.minimum.width() <= 800 - 2 * SCREEN_MARGIN
    assert fitted.minimum.height() <= 560 - FRAME_ALLOWANCE - SCREEN_MARGIN  # le contenu défile plutôt que déborder


def test_a_tiny_screen_keeps_a_usable_floor():
    fitted = fit_size((1280, 900), (1120, 620), QRect(0, 0, 200, 150))

    assert fitted.size.width() >= ABSOLUTE_MIN_SIZE.width() and fitted.size.height() >= ABSOLUTE_MIN_SIZE.height()


@pytest.mark.parametrize("area_name", _AREA_IDS)
def test_position_keeps_the_whole_window_including_its_title_bar_on_screen(area_name):
    area = _AREAS[area_name]
    size = fit_size((1280, 900), (1120, 620), area).size

    corner = position_within(size, area)
    window = QRect(corner.x(), corner.y(), size.width(), size.height() + FRAME_ALLOWANCE)

    assert _inside(window, area), f"{window} dépasse {area}"


def test_position_is_centered_on_the_parent_when_there_is_room():
    area = QRect(0, 0, 2560, 1400)
    parent = QRect(600, 300, 800, 600)

    corner = position_within(QSize(400, 300), area, parent)

    assert abs((corner.x() + 200) - parent.center().x()) <= 1


def test_position_is_pulled_back_when_the_parent_sits_at_the_edge():
    area = QRect(0, 0, 1536, 824)
    parent = QRect(1200, 600, 400, 300)  # parent qui déborde de l'écran

    corner = position_within(QSize(900, 500), area, parent)
    window = QRect(corner.x(), corner.y(), 900, 500 + FRAME_ALLOWANCE)

    assert _inside(window, area)


def test_position_on_a_secondary_screen_stays_on_that_screen():
    area = _AREAS["second écran décalé"]

    corner = position_within(QSize(900, 600), area)

    assert area.left() <= corner.x() and corner.x() + 900 <= area.right() + 1
    assert corner.y() >= area.top() and corner.y() + 600 + FRAME_ALLOWANCE <= area.bottom() + 1


# ============================ mesure réelle de l'écran =====================================================


def test_available_size_matches_qt_logical_geometry_without_dividing_by_the_scale(qtbot):
    """Qt 6 donne déjà des pixels logiques : diviser par le facteur d'échelle rapetissait un écran à 125 %."""
    widget = QWidget()
    qtbot.addWidget(widget)
    screen = widget.screen()

    width, height = screen_fit.available_size(widget)

    assert (width, height) == (screen.availableGeometry().width(), screen.availableGeometry().height())


def test_area_defaults_to_the_primary_screen_without_a_widget():
    rect = screen_fit.available_rect(None)

    assert rect.width() > 0 and rect.height() > 0


# ============================ fenêtres de dialogue ========================================================


class _Dialog(ScreenFittedDialog):
    PREFERRED_SIZE = (1200, 900)
    MINIMUM_SIZE = (1000, 600)


@pytest.mark.parametrize("area_name", _AREA_IDS)
def test_dialog_fits_and_stays_on_screen_at_every_resolution(qtbot, monkeypatch, area_name):
    area = _AREAS[area_name]
    _use_area(monkeypatch, area)
    dialog = _Dialog()
    qtbot.addWidget(dialog)

    dialog.show()

    window = _frame(dialog)
    assert _inside(window, area), f"{window} dépasse {area}"
    assert dialog.minimumWidth() <= dialog.width() and dialog.minimumHeight() <= dialog.height()


def test_dialog_keeps_its_preferred_size_on_a_roomy_screen(qtbot, monkeypatch):
    _use_area(monkeypatch, _AREAS["4K à 100 %"])
    dialog = _Dialog()
    qtbot.addWidget(dialog)

    dialog.show()

    assert (dialog.width(), dialog.height()) == (1200, 900)


def test_dialog_refits_when_opened_on_a_smaller_screen(qtbot, monkeypatch):
    _use_area(monkeypatch, _AREAS["4K à 100 %"])
    dialog = _Dialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.hide()

    _use_area(monkeypatch, _AREAS["1366x768"])  # rouverte sur un autre écran, plus petit
    dialog.show()

    window = _frame(dialog)
    assert _inside(window, _AREAS["1366x768"])
    assert dialog.height() < 900


def test_dialog_remembers_a_smaller_size_chosen_by_the_user(qtbot, monkeypatch):
    _use_area(monkeypatch, _AREAS["4K à 100 %"])
    dialog = _Dialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(1050, 700)
    dialog.hide()

    dialog.show()

    assert (dialog.width(), dialog.height()) == (1050, 700)


def test_dialog_never_reopens_larger_than_the_current_screen_allows(qtbot, monkeypatch):
    _use_area(monkeypatch, _AREAS["4K à 100 %"])
    dialog = _Dialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(1200, 900)
    dialog.hide()

    _use_area(monkeypatch, _AREAS["1024x768"])
    dialog.show()

    assert dialog.width() <= 1024 - 2 * SCREEN_MARGIN and dialog.height() <= 728 - FRAME_ALLOWANCE - SCREEN_MARGIN


def test_dialog_is_centered_over_its_visible_parent(qtbot, monkeypatch):
    area = _AREAS["4K à 100 %"]
    _use_area(monkeypatch, area)
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.setGeometry(700, 400, 900, 700)
    parent.show()
    dialog = _Dialog(parent)
    dialog.PREFERRED_SIZE = (600, 400)
    dialog.MINIMUM_SIZE = (400, 300)
    dialog.fit_to_screen()

    dialog.show()

    assert abs((dialog.x() + dialog.width() // 2) - parent.frameGeometry().center().x()) <= 2


# ============================ les vraies fenêtres ==========================================================


@pytest.fixture
def project_and_service(ffmpeg_binaries, sample_video):
    info = FFprobeService(ffmpeg_binaries.ffprobe_path).probe(sample_video)
    project = create_project_for_video(info)
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original = str(Path(project.temp_dir) / "source.wav")
    service.extract_audio(sample_video, original, info.duration)
    project.original_audio_path = original
    sequence_service.add_sequence(project, service, 0.0, 0.4, name="Ouverture")
    sequence_service.add_sequence(project, service, 0.4, 0.9, name="Suite")
    return project, service


@pytest.mark.parametrize("area_name", _AREA_IDS)
def test_export_window_fits_and_keeps_its_action_buttons_visible(qtbot, monkeypatch, project_and_service, area_name):
    area = _AREAS[area_name]
    _use_area(monkeypatch, area)
    project, service = project_and_service
    dialog = ExportDialog(project, service)
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitExposed(dialog)

    window = _frame(dialog)
    assert _inside(window, area), f"{window} dépasse {area}"
    # Le pied de page (Annuler / Exporter) n'est pas sous la barre des tâches ni hors de la fenêtre.
    for button in (dialog._cancel_button, dialog._export_button):
        assert button.isVisible()
        corner_top = button.mapTo(dialog, QPoint(0, 0))
        button_rect = QRect(corner_top, button.size())
        assert dialog.rect().contains(button_rect), f"{button.text()} déborde de la fenêtre"
        assert area.contains(QPoint(dialog.x(), dialog.y() + FRAME_ALLOWANCE + button_rect.bottom()))  # cadre compris


def test_export_window_size_on_the_reported_screen(qtbot, monkeypatch, project_and_service):
    _use_area(monkeypatch, _AREAS["1080p à 125 % (l'écran signalé)"])
    project, service = project_and_service
    dialog = ExportDialog(project, service)
    qtbot.addWidget(dialog)

    dialog.show()

    assert dialog.height() <= 824 - FRAME_ALLOWANCE - SCREEN_MARGIN  # avant : 900, le bas passait sous la barre


@pytest.mark.parametrize("area_name", ["800x600", "1024x768", "1366x768", "1080p à 125 % (l'écran signalé)", "4K à 100 %"])
def test_processing_window_fits_at_every_resolution(qtbot, monkeypatch, project_and_service, area_name):
    area = _AREAS[area_name]
    _use_area(monkeypatch, area)
    _project, service = project_and_service
    dialog = ProcessingDialog(AudioProcessingPanel(service))
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitExposed(dialog)

    window = _frame(dialog)
    assert _inside(window, area), f"{window} dépasse {area}"


@pytest.mark.parametrize("area_name", ["800x600", "1366x768", "4K à 100 %"])
def test_split_preview_dialog_fits(qtbot, monkeypatch, area_name):
    area = _AREAS[area_name]
    _use_area(monkeypatch, area)
    dialog = SplitPreviewDialog([(0.0, 2.0), (3.0, 4.0)])
    qtbot.addWidget(dialog)

    dialog.show()

    window = _frame(dialog)
    assert _inside(window, area)


# ============================ fenêtre principale ===========================================================


@pytest.mark.parametrize("area_name", _AREA_IDS)
def test_main_window_fits_and_is_placed_inside_the_work_area(qtbot, monkeypatch, ffmpeg_binaries, area_name):
    from app.ui.main_window import MainWindow

    area = _AREAS[area_name]
    _use_area(monkeypatch, area)
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(ffmpeg_binaries)
    qtbot.addWidget(window)

    window.show()

    frame = _frame(window)
    assert _inside(frame, area), f"{frame} dépasse {area}"


def test_main_window_uses_the_real_logical_work_area_not_a_divided_one(qtbot, monkeypatch, ffmpeg_binaries):
    """Sur l'écran signalé (1536×824 logiques) la fenêtre ne doit pas être rapetissée comme sur un écran de 1229×659."""
    from app.ui.main_window import _WINDOW_SIZE, MainWindow

    _use_area(monkeypatch, _AREAS["1080p à 125 % (l'écran signalé)"])
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(ffmpeg_binaries)
    qtbot.addWidget(window)

    assert window._fitted_size() == (
        min(_WINDOW_SIZE[0], 1536 - 2 * SCREEN_MARGIN), min(_WINDOW_SIZE[1], 824 - FRAME_ALLOWANCE - SCREEN_MARGIN)
    )
    assert window._available_size() == (1536, 824)


def test_main_window_side_columns_keep_full_width_when_the_screen_is_wide_enough(qtbot, monkeypatch, ffmpeg_binaries):
    from app.ui.main_window import _RIGHT_PANEL_WIDTH, _SIDE_PANEL_WIDTH, MainWindow

    _use_area(monkeypatch, _AREAS["1080p à 125 % (l'écran signalé)"])

    assert MainWindow._column_widths() == (_SIDE_PANEL_WIDTH, _RIGHT_PANEL_WIDTH)  # plus rognées à tort


def test_main_window_side_columns_shrink_on_a_narrow_screen(qtbot, monkeypatch, ffmpeg_binaries):
    from app.ui.main_window import _RIGHT_PANEL_MIN_WIDTH, _RIGHT_PANEL_WIDTH, _SIDE_PANEL_MIN_WIDTH, _SIDE_PANEL_WIDTH, MainWindow

    _use_area(monkeypatch, _AREAS["1024x768"])

    side, right = MainWindow._column_widths()

    assert side < _SIDE_PANEL_WIDTH and right < _RIGHT_PANEL_WIDTH
    assert side >= _SIDE_PANEL_MIN_WIDTH and right >= _RIGHT_PANEL_MIN_WIDTH
