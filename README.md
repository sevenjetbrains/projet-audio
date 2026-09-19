# AudioCut Studio

Application desktop pour extraire, nettoyer, organiser et fusionner des séquences audio à partir de vidéos. Fonctionne entièrement en local (aucun envoi de fichier sur Internet).

État actuel : application fonctionnelle (extraction, nettoyage, fusion, export, sauvegarde de projet).

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

## Fonctionnalités

- Import vidéo/audio, forme d'onde, lecture avec contrôles de transport
- Création et gestion de séquences (début/fin, sélection, réorganisation)
- Traitement audio non destructif : réduction de bruit, anti-ronflement (de-hum), de-click, compression, gain, normalisation (pic ou loudness LUFS)
- Profils prédéfinis : Voix parlée, Interview, Podcast, Conférence, Enregistrement microphone, Voix faible
- Suppression des silences et fusion avec fondu enchaîné (crossfade)
- Export de la fusion ou des séquences
- Sauvegarde/chargement de projet (.acsproject), annuler/rétablir (Ctrl+Z / Ctrl+Y), sauvegarde automatique toutes les 2 minutes avec récupération après plantage

## Tests

```bash
pytest
```

## Architecture

```
app/
  config/      # settings, constantes, profils audio, détection ffmpeg/ffprobe
  models/      # dataclasses Project, MediaInfo, Sequence, AudioSettings
  services/    # logique métier (ffmpeg, ffprobe, séquences, projet, export, traitement audio)
  audio/       # DSP (waveform, filtres, détection de silences)
  workers/     # exécution asynchrone Qt (ffmpeg, waveform)
  ui/          # fenêtres et widgets PySide6
  utils/       # helpers (fichiers, temps, logging)
tests/
resources/     # icônes, feuilles de style
```

Le fichier vidéo/audio source n'est jamais modifié : tous les traitements passent par des fichiers intermédiaires dans `temp/`.

## Problèmes connus

- Aucun recensé pour l'instant.