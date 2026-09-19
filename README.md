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

- Import vidéo par dialogue ou par glisser-déposer (un projet .acsproject déposé est ouvert), forme d'onde, lecture avec contrôles de transport (lecture/pause avec Espace, stop, ±5 s, volume) ; touches I / O pour marquer le début / la fin de la sélection à la position de lecture, Entrée pour créer la séquence
- Création et gestion de séquences (début/fin, réorganisation par glisser-déposer, sélection multiple : suppression, duplication et traitement en lot)
- Découpage automatique en séquences selon les silences (menu Édition), annulable en une action
- Traitement audio non destructif : réduction de bruit, anti-ronflement (de-hum), de-click, compression, gain, normalisation (pic ou loudness LUFS)
- Profils prédéfinis : Voix parlée, Interview, Podcast, Conférence, Enregistrement microphone, Voix faible
- Thèmes sombre et clair (menu Affichage), choix mémorisé
- Titre de fenêtre avec astérisque si modifications non sauvegardées, confirmation avant fermeture, nouvel import ou ouverture d'un autre projet
- Raccourcis clavier des boutons (infobulles) : Suppr, Ctrl+D, F2, Ctrl+L (séquences) ; Ctrl+Entrée, Ctrl+Maj+Entrée, Ctrl+R (traitement) ; Ctrl+M (fusion) ; F1 : liste complète des raccourcis ; Alt+←/→, Ctrl+Espace (lecture)
- Barres de progression réelles (pourcentage) pour l'export et les traitements audio
- Barre d'état : nombre de séquences et durée fusionnée estimée
- Suppression des silences et fusion avec fondu enchaîné (crossfade)
- Normalisation optionnelle du volume à l'export (loudness LUFS)
- Export de la fusion (ou d'un fichier par séquence) en WAV, MP3, FLAC, M4A (AAC), OGG ou Opus
- Sauvegarde/chargement de projet (.acsproject), annuler/rétablir (Ctrl+Z / Ctrl+Y) y compris pour les traitements audio, menu Projets récents, sauvegarde automatique toutes les 2 minutes avec récupération après plantage

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