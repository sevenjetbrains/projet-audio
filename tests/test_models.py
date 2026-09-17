"""Tests des dataclasses de base."""

from app.models.project import Project
from app.models.sequence import Sequence


def test_sequence_duration():
    seq = Sequence(id="seq1", name="Intro", source_start=10.0, source_end=25.5, order=0)
    assert seq.duration == 15.5


def test_project_default_sequences_empty():
    project = Project(name="mon_projet")
    assert project.sequences == []
    assert project.source_video is None
