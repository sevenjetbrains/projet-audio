"""Fenêtre principale d'AudioCut Studio."""

from PySide6.QtWidgets import QMainWindow

from app.config.constants import APP_NAME
from app.config.settings import FFmpegBinaries
from app.ui.video_panel import VideoPanel


class MainWindow(QMainWindow):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)
        self.setCentralWidget(VideoPanel(ffmpeg_binaries))
