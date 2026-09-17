# AudioCut Studio

Application desktop pour extraire, nettoyer, organiser et fusionner des séquences audio à partir de vidéos. Fonctionne entièrement en local (aucun envoi de fichier sur Internet).

État actuel : squelette du projet (Phase 1 — infrastructure). Aucune fonctionnalité métier n'est encore implémentée.

## Prérequis

- Python 3.12+ (le projet a été initialisé avec Python 3.14)
- FFmpeg et FFprobe installés et accessibles sur le PATH

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Lancement

```bash
python -m app.main
```

## Tests

```bash
pytest
```

## Architecture

```
app/
  config/      # settings, constantes, détection ffmpeg/ffprobe
  models/      # dataclasses Project, MediaInfo, Sequence, AudioSettings
  services/    # logique métier (ffmpeg, séquences, export) — Phase 2+
  audio/       # traitement DSP (waveform, filtres) — Phase 3+
  workers/     # exécution asynchrone Qt (QThread/QRunnable) — Phase 2+
  ui/          # fenêtres et widgets PySide6
  utils/       # helpers (fichiers, temps, logging)
tests/
resources/     # icônes, feuilles de style
```

Le fichier vidéo/audio source n'est jamais modifié : tous les traitements passent par des fichiers intermédiaires dans `temp/`.

## Problèmes connus

- Aucun pour l'instant (squelette uniquement).
