"""Point d'entrée AudioCut Studio : vérifie FFmpeg/FFprobe puis lance la fenêtre principale."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config.settings import PROJECT_ROOT, find_ffmpeg_binaries
from app.config.settings import FFmpegNotFoundError
from app.ui.main_window import MainWindow
from app.utils.logger import setup_logging


def main() -> int:
    logger = setup_logging()
    logger.info("Démarrage d'AudioCut Studio")

    app = QApplication(sys.argv)

    qss_path = PROJECT_ROOT / "resources" / "styles" / "dark_theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    try:
        binaries = find_ffmpeg_binaries()
        logger.info("FFmpeg détecté : %s", binaries.ffmpeg_path)
        logger.info("FFprobe détecté : %s", binaries.ffprobe_path)
    except FFmpegNotFoundError as exc:
        logger.error("FFmpeg/FFprobe introuvable : %s", exc)
        QMessageBox.critical(None, "AudioCut Studio — Erreur", str(exc))
        return 1

    window = MainWindow(binaries)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
