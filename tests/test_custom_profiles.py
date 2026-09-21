"""Tests des profils enregistrés par l'utilisateur : stockage, colonne des profils, suppression."""

import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.config.audio_profiles import AUDIO_PROFILES
from app.models.audio_settings import AudioSettings
from app.services.custom_profiles import (
    delete_custom_profile,
    load_custom_profiles,
    save_custom_profile,
)
from app.services.ffmpeg_service import FFmpegService
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.controls import ProfileCard

# --- Stockage ------------------------------------------------------------------


def test_a_saved_profile_comes_back_with_its_settings(tmp_path):
    store = tmp_path / "custom.json"
    settings = AudioSettings(gain=4.0, compression=True, compression_ratio=3.5)

    save_custom_profile("Ma voix", settings, store)

    assert load_custom_profiles(store) == {"Ma voix": settings}


def test_saving_the_same_name_replaces_the_profile(tmp_path):
    store = tmp_path / "custom.json"
    save_custom_profile("Ma voix", AudioSettings(gain=2.0), store)

    save_custom_profile("Ma voix", AudioSettings(gain=8.0), store)

    profiles = load_custom_profiles(store)
    assert len(profiles) == 1 and profiles["Ma voix"].gain == 8.0


def test_deleting_a_profile_removes_only_that_one(tmp_path):
    store = tmp_path / "custom.json"
    save_custom_profile("A", AudioSettings(gain=1.0), store)
    save_custom_profile("B", AudioSettings(gain=2.0), store)

    delete_custom_profile("A", store)

    assert list(load_custom_profiles(store)) == ["B"]


def test_deleting_an_unknown_profile_is_harmless(tmp_path):
    store = tmp_path / "custom.json"
    save_custom_profile("A", AudioSettings(), store)

    delete_custom_profile("Inconnu", store)

    assert list(load_custom_profiles(store)) == ["A"]


def test_no_file_yet_means_no_profile(tmp_path):
    assert load_custom_profiles(tmp_path / "jamais_ecrit.json") == {}


@pytest.mark.parametrize("content", ["pas du json", "[1, 2]", '"texte"'])
def test_an_unreadable_file_does_not_break_the_application(tmp_path, content):
    store = tmp_path / "custom.json"
    store.write_text(content, encoding="utf-8")

    assert load_custom_profiles(store) == {}


def test_a_setting_from_a_newer_version_is_ignored(tmp_path):
    """Un profil écrit par une version ultérieure doit rester utilisable, sans son réglage inconnu."""
    store = tmp_path / "custom.json"
    store.write_text(json.dumps({"Futur": {"gain": 3.0, "reverb": True}}), encoding="utf-8")

    profiles = load_custom_profiles(store)

    assert profiles["Futur"].gain == 3.0


# --- Colonne des profils ----------------------------------------------------------


@pytest.fixture
def panel(qtbot, monkeypatch, tmp_path, ffmpeg_binaries):
    from app.models.sequence import Sequence

    monkeypatch.setattr("app.services.custom_profiles.CUSTOM_PROFILES_FILE", tmp_path / "custom.json")
    widget = AudioProcessingPanel(FFmpegService(ffmpeg_binaries.ffmpeg_path))
    qtbot.addWidget(widget)
    widget.set_sequence(Sequence(id="a", name="Q1", source_start=0.0, source_end=30.0, order=0))
    return widget


def _card_names(panel) -> list[str]:
    return [card._name for card in panel._profiles_container.findChildren(ProfileCard)]


def test_the_column_starts_with_the_predefined_profiles(panel):
    assert _card_names(panel) == list(AUDIO_PROFILES)


def test_saving_adds_the_profile_at_the_end_and_selects_it(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma conférence", True))
    panel._gain_slider.set_value(5.0)

    panel._save_profile_button.click()

    assert _card_names(panel)[-1] == "Ma conférence"
    assert panel._current_profile == "Ma conférence"
    assert panel._profile_cards["Ma conférence"].property("profile") == "true"


def test_a_saved_profile_reloads_the_settings_it_was_given(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma conférence", True))
    panel._gain_slider.set_value(5.0)
    panel._compression_toggle.setChecked(True)
    panel._save_profile_button.click()

    panel._select_profile("Voix parlée")
    panel._select_profile("Ma conférence")

    assert panel._gain_slider.value() == pytest.approx(5.0)
    assert panel._compression_toggle.isChecked()


def test_an_empty_or_cancelled_name_saves_nothing(panel, monkeypatch):
    for answer in (("", True), ("   ", True), ("Ignoré", False)):
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, _r=answer, **k: _r)
        panel._save_profile_button.click()

    assert _card_names(panel) == list(AUDIO_PROFILES)


def test_a_predefined_name_is_refused(panel, monkeypatch):
    warnings = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Podcast", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))

    panel._save_profile_button.click()

    assert "prédéfini" in warnings[0]
    assert _card_names(panel) == list(AUDIO_PROFILES)


def test_overwriting_a_saved_profile_is_confirmed_first(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma voix", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._gain_slider.set_value(2.0)
    panel._save_profile_button.click()

    panel._gain_slider.set_value(9.0)
    panel._save_profile_button.click()

    assert _card_names(panel).count("Ma voix") == 1
    panel._select_profile("Ma voix")
    assert panel._gain_slider.value() == pytest.approx(9.0)


def test_declining_the_overwrite_keeps_the_previous_settings(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma voix", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._gain_slider.set_value(2.0)
    panel._save_profile_button.click()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    panel._gain_slider.set_value(9.0)
    panel._save_profile_button.click()

    panel._select_profile("Ma voix")
    assert panel._gain_slider.value() == pytest.approx(2.0)


# --- Suppression -------------------------------------------------------------------


def test_only_a_saved_profile_offers_to_be_deleted(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma voix", True))
    panel._save_profile_button.click()

    assert panel._profile_cards["Ma voix"]._removable
    assert not panel._profile_cards["Podcast"]._removable


def test_right_clicking_a_saved_profile_deletes_it_after_confirmation(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma voix", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._save_profile_button.click()
    card = panel._profile_cards["Ma voix"]
    card.resize(200, 50)

    QTest.mouseClick(card, Qt.MouseButton.RightButton, pos=QPoint(20, 20))

    assert _card_names(panel) == list(AUDIO_PROFILES)
    assert panel._current_profile == "Personnalisé"


def test_a_declined_deletion_keeps_the_profile(panel, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ma voix", True))
    panel._save_profile_button.click()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    panel._on_delete_profile("Ma voix")

    assert "Ma voix" in _card_names(panel)


def test_right_clicking_a_predefined_profile_does_nothing(panel, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Yes)
    card = panel._profile_cards["Podcast"]
    card.resize(200, 50)

    QTest.mouseClick(card, Qt.MouseButton.RightButton, pos=QPoint(20, 20))

    assert asked == []
    assert _card_names(panel) == list(AUDIO_PROFILES)
