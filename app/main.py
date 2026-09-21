"""Point d'entrée AudioCut Studio : vérifie FFmpeg/FFprobe puis lance la fenêtre principale."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config.settings import find_ffmpeg_binaries
from app.config.settings import FFmpegNotFoundError
from app.config.themes import get_theme, load_stylesheet, load_theme_preference
from app.ui.main_window import MainWindow
from app.utils.logger import setup_logging


def main() -> int:
    logger = setup_logging()
    logger.info("Démarrage d'AudioCut Studio")

    app = QApplication(sys.argv)

    app.setStyleSheet(load_stylesheet(get_theme(load_theme_preference())))

    try:
        binaries = find_ffmpeg_binaries()
        logger.info("FFmpeg détecté : %s", binaries.ffmpeg_path)
        logger.info("FFprobe détecté : %s", binaries.ffprobe_path)
    except FFmpegNotFoundError as exc:
        logger.error("FFmpeg/FFprobe introuvable : %s", exc)
        QMessageBox.critical(None, "AudioCut Studio — Erreur", str(exc))
        return 1

    window = MainWindow(binaries)
    # Écran plus petit que la mise en page : l'ouvrir en plein écran évite de démarrer
    # sur une fenêtre où les colonnes latérales demandent déjà de défiler.
    if window.needs_maximised_start:
        window.showMaximized()
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
