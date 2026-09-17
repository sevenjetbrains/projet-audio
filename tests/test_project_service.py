"""Tests de project_service.create_project_for_video."""

from pathlib import Path

from app.models.media import MediaInfo
from app.services.project_service import create_project_for_video


def test_create_project_for_video_sets_up_temp_dir():
    media_info = MediaInfo(
        path="C:/videos/interview.mp4",
        duration=120.0,
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        video_codec="h264",
        audio_codec="aac",
        sample_rate=44100,
        channels=2,
        resolution=(1920, 1080),
        bitrate=5_000_000,
        size_bytes=10_000_000,
    )

    project = create_project_for_video(media_info)

    assert project.name == "interview"
    assert project.source_video is media_info
    assert project.temp_dir
    assert Path(project.temp_dir).is_dir()
    assert Path(project.temp_dir).name.startswith("project_")
