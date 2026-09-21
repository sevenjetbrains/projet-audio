"""Tests de l'écran d'accueil : vignettes de projets récents, bandeau d'autosave, progression,
et la bascule accueil ↔ éditeur de la fenêtre principale."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config.settings import find_ffmpeg_binaries
from app.models.project import Project
from app.services.project_service import describe_autosave
from app.services.recent_projects import RecentProject, describe_recent_project
from app.ui.main_window import MainWindow
from app.ui.welcome_view import RecentProjectCard, WelcomeView


def _recent(name="projet.acsproject", count=8, when=None) -> RecentProject:
    return RecentProject(f"C:/Videos/{name}", name, count, when or datetime(2026, 9, 17, 9, 51))


@pytest.fixture
def welcome(qtbot):
    view = WelcomeView()
    qtbot.addWidget(view)
    return view


# --- Projets récents ---------------------------------------------------------


def _card_texts(welcome, index: int = 0) -> list[str]:
    from PySide6.QtWidgets import QLabel

    card = welcome.findChildren(RecentProjectCard)[index]
    return [child.text() for child in card.findChildren(QLabel)]


def test_recent_projects_are_listed_as_cards(welcome):
    welcome.set_recent_projects([_recent("a.acsproject", 8), _recent("b.acsproject", 1)])

    assert len(welcome.findChildren(RecentProjectCard)) == 2
    assert _card_texts(welcome, 0)[0] == "a.acsproject"
    assert _card_texts(welcome, 1)[0] == "b.acsproject"
    assert not welcome._recent_empty.isVisibleTo(welcome)


def test_a_card_spells_out_the_sequence_count_date_and_folder(welcome):
    welcome.set_recent_projects([_recent("a.acsproject", 8)])

    texts = _card_texts(welcome)
    assert "8 séquences · 17 sept. à 09:51" in texts
    assert "C:/Videos/" in texts


def test_a_single_sequence_is_not_pluralised(welcome):
    welcome.set_recent_projects([_recent("a.acsproject", 1)])

    assert any(text.startswith("1 séquence ·") for text in _card_texts(welcome))


def test_clicking_a_card_asks_to_open_that_project(qtbot, welcome):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    welcome.set_recent_projects([_recent("a.acsproject")])
    chosen = []
    welcome.recent_project_chosen.connect(chosen.append)
    card = welcome.findChildren(RecentProjectCard)[0]

    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))

    assert chosen == ["C:/Videos/a.acsproject"]


def test_refreshing_the_list_replaces_the_previous_cards(welcome):
    welcome.set_recent_projects([_recent("a.acsproject"), _recent("b.acsproject")])
    welcome.set_recent_projects([_recent("c.acsproject")])

    assert len(welcome.findChildren(RecentProjectCard)) == 1


def test_without_any_recent_project_a_hint_takes_their_place(welcome):
    welcome.set_recent_projects([_recent("a.acsproject")])
    welcome.set_recent_projects([])

    assert welcome.findChildren(RecentProjectCard) == []
    assert welcome._recent_empty.text() == "Aucun projet ouvert récemment."


def test_describe_recent_project_counts_the_sequences(tmp_path):
    file = tmp_path / "demo.acsproject"
    file.write_text(json.dumps({"sequences": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")

    info = describe_recent_project(str(file))

    assert (info.file_name, info.sequence_count) == ("demo.acsproject", 2)
    assert isinstance(info.modified_at, datetime)


@pytest.mark.parametrize("content", ["pas du json", "[]", '{"sequences": "trois"}'])
def test_an_unreadable_project_file_is_described_as_empty(tmp_path, content):
    """Un fichier abîmé doit rester listé (pour être ouvert et diagnostiqué), sans compter faux."""
    file = tmp_path / "abime.acsproject"
    file.write_text(content, encoding="utf-8")

    assert describe_recent_project(str(file)).sequence_count == 0


# --- Bandeau de sauvegarde automatique ---------------------------------------


def test_autosave_banner_names_the_project_and_its_age(welcome):
    welcome.show_autosave_offer("entretien_marc", datetime.now() - timedelta(minutes=3))

    assert welcome._autosave_card.isVisibleTo(welcome)
    assert welcome._autosave_detail.text() == (
        "« entretien_marc » — enregistrée il y a 3 min, après une fermeture inattendue."
    )


def test_autosave_banner_is_hidden_by_default_and_can_be_hidden_again(welcome):
    assert not welcome._autosave_card.isVisibleTo(welcome)

    welcome.show_autosave_offer("x", datetime.now())
    welcome.hide_autosave_offer()

    assert not welcome._autosave_card.isVisibleTo(welcome)


def test_describe_autosave_reads_the_project_name(tmp_path):
    file = tmp_path / "autosave.acsproject"
    file.write_text(json.dumps({"project_name": "entretien_marc"}), encoding="utf-8")

    info = describe_autosave(str(file))

    assert info.project_name == "entretien_marc"
    assert info.path == str(file)


def test_describe_autosave_falls_back_to_the_folder_name(tmp_path):
    folder = tmp_path / "project_ab12"
    folder.mkdir()
    file = folder / "autosave.acsproject"
    file.write_text("illisible", encoding="utf-8")

    assert describe_autosave(str(file)).project_name == "project_ab12"


# --- Progression de l'import --------------------------------------------------


def test_import_progress_card_shows_the_file_and_percentage(welcome):
    assert not welcome.import_in_progress

    welcome.start_import_progress("conference.mp4")
    welcome.set_import_progress(42)

    assert welcome._progress_name.text() == "conference.mp4"
    assert welcome._progress_percent.text() == "42 %"
    assert welcome._progress_card.isVisibleTo(welcome)

    welcome.hide_import_progress()
    assert not welcome._progress_card.isVisibleTo(welcome)


def test_a_new_import_restarts_the_progress_from_zero(welcome):
    welcome.start_import_progress("a.mp4")
    welcome.set_import_progress(80)

    welcome.start_import_progress("b.mp4")

    assert welcome._progress_percent.text() == "0 %"


def test_buttons_of_the_drop_zone_emit_their_intent(welcome):
    events = []
    welcome.import_requested.connect(lambda: events.append("import"))
    welcome.open_project_requested.connect(lambda: events.append("open"))

    welcome._import_button.click()
    welcome._open_button.click()

    assert events == ["import", "open"]


def test_drop_highlight_is_a_reversible_visual_state(welcome):
    welcome.set_drop_active(True)
    assert welcome._drop_zone.property("hover") == "true"

    welcome.set_drop_active(False)
    assert welcome._drop_zone.property("hover") == "false"


# --- Fenêtre principale --------------------------------------------------------


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.describe_recent_projects", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    return window


def _menu_state(window) -> dict[str, bool]:
    return {action.text(): action.isEnabled() for action in window.menuBar().actions() if action.text()}


def test_the_window_opens_on_the_welcome_page(window):
    assert window._pages.currentWidget() is window._welcome_view
    assert window.menuBar().cornerWidget().text() == "Aucun projet ouvert"


def test_menus_without_a_project_are_greyed_out(window, monkeypatch):
    state = _menu_state(window)
    assert state["Fichier"] and state["Affichage"] and state["Aide"]
    assert not (state["Édition"] or state["Séquences"] or state["Traitement"])

    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: Project(name="demo")))
    window._on_audio_ready("C:/x/source.wav", 10.0)

    state = _menu_state(window)
    assert state["Édition"] and state["Séquences"] and state["Traitement"]


def test_loading_audio_switches_to_the_editor(window, monkeypatch):
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: Project(name="demo")))

    window._on_audio_ready("C:/x/source.wav", 10.0)

    assert window._pages.currentWidget() is not window._welcome_view


def test_recent_projects_are_pushed_to_the_welcome_screen(qtbot, monkeypatch, tmp_path):
    file = tmp_path / "demo.acsproject"
    file.write_text(json.dumps({"sequences": [{"id": "a"}]}), encoding="utf-8")
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr(
        "app.ui.main_window.describe_recent_projects", lambda: [describe_recent_project(str(file))]
    )

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    cards = window._welcome_view.findChildren(RecentProjectCard)
    assert len(cards) == 1
    opened = []
    monkeypatch.setattr(window, "_start_project_load", lambda path, remember=True: opened.append(path))
    window._welcome_view.recent_project_chosen.emit(str(file))
    assert opened == [str(file)]


def test_a_recoverable_autosave_is_offered_in_the_banner_not_a_dialog(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    file = tmp_path / "autosave.acsproject"
    file.write_text(json.dumps({"project_name": "entretien_marc"}), encoding="utf-8")
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [str(file)])
    monkeypatch.setattr("app.ui.main_window.describe_recent_projects", lambda: [])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No)

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    window._check_for_recoverable_autosave()

    assert asked == []
    assert window._welcome_view._autosave_detail.text().startswith("« entretien_marc »")

    loaded = []
    monkeypatch.setattr(window, "_start_project_load", lambda path, remember=True: loaded.append((path, remember)))
    window._welcome_view.autosave_recovery_requested.emit()

    assert loaded == [(str(file), False)]
    assert window._pending_autosave is None


def test_dismissing_the_autosave_offer_loads_nothing(window, monkeypatch, tmp_path):
    file = tmp_path / "autosave.acsproject"
    file.write_text(json.dumps({"project_name": "x"}), encoding="utf-8")
    window._pending_autosave = describe_autosave(str(file))
    window._welcome_view.show_autosave_offer("x", datetime.now())
    loaded = []
    monkeypatch.setattr(window, "_start_project_load", lambda *a, **k: loaded.append(a))

    window._welcome_view.autosave_dismissed.emit()

    assert loaded == []
    assert window._pending_autosave is None
    window._welcome_view.autosave_recovery_requested.emit()
    assert loaded == []


def test_extraction_progress_reaches_the_welcome_screen(window):
    window._video_panel.extraction_started.emit("conference.mp4")
    window._video_panel.extraction_progress.emit(42)

    assert window._welcome_view._progress_percent.text() == "42 %"
    assert window._welcome_view.import_in_progress

    window._video_panel.extraction_finished.emit()
    assert not window._welcome_view.import_in_progress


def test_cancelling_from_the_welcome_screen_reaches_the_video_panel(window, monkeypatch):
    cancelled = []
    monkeypatch.setattr(window._video_panel, "cancel_extraction", lambda: cancelled.append(True))

    window._welcome_view.import_cancel_requested.emit()

    assert cancelled == [True]
