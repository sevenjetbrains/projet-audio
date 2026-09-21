"""Tests des repères (marqueurs) : service, ordre, navigation et persistance dans le projet."""

import json
from pathlib import Path

import pytest

from app.models.marker import Marker
from app.models.project import Project
from app.services import marker_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video, load_project, save_project


@pytest.fixture
def project() -> Project:
    return Project(name="test")


def _add(project: Project, position: float, label: str | None = None) -> Marker:
    marker = marker_service.create_marker(project, position, label)
    marker_service.insert_marker(project, marker)
    return marker


def test_markers_are_kept_in_chronological_order(project):
    _add(project, 3.0)
    _add(project, 1.0)
    _add(project, 2.0)

    assert [m.position for m in project.markers] == [1.0, 2.0, 3.0]


def test_default_label_numbers_markers_in_order_of_creation(project):
    first = _add(project, 5.0)
    second = _add(project, 1.0)

    assert (first.label, second.label) == ("Repère 1", "Repère 2")


def test_explicit_label_is_kept_and_renaming_works(project):
    marker = _add(project, 1.0, "Question du public")
    assert marker.label == "Question du public"

    marker_service.rename_marker(project, marker.id, "Réponse")

    assert marker_service.find(project, marker.id).label == "Réponse"


def test_negative_position_is_clamped_to_zero(project):
    assert _add(project, -2.0).position == 0.0


def test_remove_marker_returns_it_so_that_undo_can_reinsert_it(project):
    marker = _add(project, 2.0, "Chapitre")

    removed = marker_service.remove_marker(project, marker.id)

    assert project.markers == []
    marker_service.insert_marker(project, removed)
    assert project.markers == [marker]


def test_find_and_remove_raise_for_an_unknown_marker(project):
    with pytest.raises(KeyError):
        marker_service.find(project, "inconnu")
    with pytest.raises(KeyError):
        marker_service.remove_marker(project, "inconnu")


def test_move_marker_keeps_the_list_sorted(project):
    first = _add(project, 1.0)
    _add(project, 2.0)

    marker_service.move_marker(project, first.id, 5.0)

    assert [m.position for m in project.markers] == [2.0, 5.0]


def test_marker_near_finds_the_closest_within_tolerance(project):
    _add(project, 1.0)
    close = _add(project, 4.0)

    assert marker_service.marker_near(project, 4.01, tolerance=0.1) is close
    assert marker_service.marker_near(project, 4.5, tolerance=0.1) is None


def test_next_and_previous_marker_skip_the_current_position(project):
    first = _add(project, 1.0)
    second = _add(project, 2.0)

    assert marker_service.next_marker(project, 1.0) is second
    assert marker_service.previous_marker(project, 2.0) is first
    assert marker_service.next_marker(project, 2.0) is None
    assert marker_service.previous_marker(project, 1.0) is None


def test_surrounding_range_uses_file_edges_when_a_marker_is_missing(project):
    _add(project, 4.0)

    assert marker_service.surrounding_range(project, 1.0, duration=10.0) == (0.0, 4.0)
    assert marker_service.surrounding_range(project, 6.0, duration=10.0) == (4.0, 10.0)


def test_surrounding_range_between_two_markers(project):
    _add(project, 2.0)
    _add(project, 6.0)

    assert marker_service.surrounding_range(project, 4.0, duration=10.0) == (2.0, 6.0)


def test_surrounding_range_is_none_without_markers(project):
    assert marker_service.surrounding_range(project, 4.0, duration=10.0) is None


# --- Persistance -----------------------------------------------------------


@pytest.fixture
def saved_project(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    return project, ffmpeg_service, ffprobe_service


def test_markers_survive_a_save_load_roundtrip(saved_project, tmp_path):
    project, ffmpeg_service, ffprobe_service = saved_project
    _add(project, 0.6, "Deuxième")
    _add(project, 0.2, "Premier")
    out_path = tmp_path / "avec_reperes.acsproject"

    save_project(project, str(out_path))
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert [m["label"] for m in data["markers"]] == ["Premier", "Deuxième"]

    reloaded = load_project(str(out_path), ffprobe_service, ffmpeg_service)

    assert [(m.position, m.label) for m in reloaded.markers] == [(0.2, "Premier"), (0.6, "Deuxième")]


def test_project_without_markers_key_still_loads(saved_project, tmp_path):
    """Compatibilité : les projets enregistrés avant les repères n'ont pas la clé."""
    project, ffmpeg_service, ffprobe_service = saved_project
    out_path = tmp_path / "ancien.acsproject"
    save_project(project, str(out_path))
    data = json.loads(out_path.read_text(encoding="utf-8"))
    del data["markers"]
    out_path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = load_project(str(out_path), ffprobe_service, ffmpeg_service)

    assert reloaded.markers == []
