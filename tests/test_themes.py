"""Tests des thèmes (préférence persistée, feuilles de style, application via le menu Affichage)."""

import pytest

from app.config import themes
from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow
from app.ui.waveform_widget import WaveformWidget


def test_every_theme_has_an_existing_stylesheet():
    for theme in themes.THEMES.values():
        assert (themes.STYLES_DIR / theme.stylesheet_file).is_file()
        assert themes.load_stylesheet(theme).strip()


def test_get_theme_falls_back_to_default_for_unknown_name():
    assert themes.get_theme("Inconnu").name == themes.DEFAULT_THEME
    assert themes.get_theme("Clair").name == "Clair"


def test_theme_preference_roundtrip(tmp_path):
    store = tmp_path / "theme.json"
    assert themes.load_theme_preference(store) == themes.DEFAULT_THEME

    themes.save_theme_preference("Clair", store)

    assert themes.load_theme_preference(store) == "Clair"


@pytest.mark.parametrize("content", ["pas du json", '{"theme": "Fantaisie"}', "[1, 2]"])
def test_invalid_theme_preference_falls_back_to_default(tmp_path, content):
    store = tmp_path / "theme.json"
    store.write_text(content, encoding="utf-8")

    assert themes.load_theme_preference(store) == themes.DEFAULT_THEME


def test_waveform_widget_uses_theme_colors(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)

    widget.set_theme(themes.get_theme("Clair"))

    assert widget._theme.waveform_background == "#ffffff"
    widget.grab()  # le rendu ne doit pas planter avec le thème clair


def test_theme_menu_applies_and_persists_choice(qtbot, qapp, monkeypatch):
    saved = []
    previous_stylesheet = qapp.styleSheet()
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.load_theme_preference", lambda: "Sombre")
    monkeypatch.setattr("app.ui.main_window.save_theme_preference", saved.append)

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    view_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "Affichage")
    theme_menu = next(a.menu() for a in view_menu.actions() if a.text() == "Thème")
    actions = {a.text(): a for a in theme_menu.actions()}
    assert set(actions) == set(themes.THEMES)
    assert actions["Sombre"].isChecked() and not actions["Clair"].isChecked()

    try:
        actions["Clair"].trigger()

        assert saved == ["Clair"]
        assert window._waveform_widget._theme.name == "Clair"
        assert qapp.styleSheet() == themes.load_stylesheet(themes.get_theme("Clair"))
    finally:
        qapp.setStyleSheet(previous_stylesheet)
