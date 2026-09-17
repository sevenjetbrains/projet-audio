"""Smoke test : VideoPanel s'instancie sans planter."""

from app.ui.video_panel import VideoPanel


def test_video_panel_instantiates(qtbot, ffmpeg_binaries):
    panel = VideoPanel(ffmpeg_binaries)
    qtbot.addWidget(panel)

    assert panel._import_button.text() == "Importer une vidéo"
    assert panel._progress_bar.isHidden()
