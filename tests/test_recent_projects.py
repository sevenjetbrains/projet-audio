"""Tests de app.services.recent_projects."""

from pathlib import Path

from app.services.recent_projects import MAX_RECENT_PROJECTS, add_recent_project, load_recent_projects


def _make(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_text("{}", encoding="utf-8")
    return str(path)


def test_empty_when_no_store(tmp_path):
    assert load_recent_projects(tmp_path / "recent.json") == []


def test_most_recent_first_without_duplicates(tmp_path):
    store = tmp_path / "recent.json"
    a, b = _make(tmp_path, "a.acsproject"), _make(tmp_path, "b.acsproject")

    add_recent_project(a, store)
    add_recent_project(b, store)
    add_recent_project(a, store)

    assert [Path(p).name for p in load_recent_projects(store)] == ["a.acsproject", "b.acsproject"]


def test_missing_files_are_dropped(tmp_path):
    store = tmp_path / "recent.json"
    a, b = _make(tmp_path, "a.acsproject"), _make(tmp_path, "b.acsproject")
    add_recent_project(a, store)
    add_recent_project(b, store)

    Path(a).unlink()

    assert [Path(p).name for p in load_recent_projects(store)] == ["b.acsproject"]


def test_list_is_capped(tmp_path):
    store = tmp_path / "recent.json"
    for i in range(MAX_RECENT_PROJECTS + 3):
        add_recent_project(_make(tmp_path, f"p{i}.acsproject"), store)

    recent = load_recent_projects(store)
    assert len(recent) == MAX_RECENT_PROJECTS
    assert Path(recent[0]).name == f"p{MAX_RECENT_PROJECTS + 2}.acsproject"


def test_corrupted_store_is_ignored(tmp_path):
    store = tmp_path / "recent.json"
    store.write_text("pas du json", encoding="utf-8")

    assert load_recent_projects(store) == []
