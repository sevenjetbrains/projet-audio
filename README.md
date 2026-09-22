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

- Écran d'accueil tant qu'aucun projet n'est ouvert : zone de dépôt (vidéo ou .acsproject), boutons d'import et d'ouverture, formats acceptés, projets récents avec leur nombre de séquences et leur date, progression de l'import annulable, et bandeau de récupération d'une sauvegarde automatique ; les menus sans objet y sont grisés
- Plein écran de l'aperçu vidéo avec barre de contrôle (lecture/pause, progression cliquable, temps écoulé et durée, masquage automatique ; Échap ou double-clic pour revenir)
- Clic sur l'image vidéo (fenêtré ou plein écran) : lecture / pause, comme la plupart des lecteurs
- Aperçu fluide : copie allégée de la vidéo préparée en arrière-plan pour se déplacer instantanément (avant comme arrière)
- Bornes de la sélection ajustables directement sur la waveform (poignées à tirer, en direct)
- Boucle de la sélection (bouton ou L) : les bornes se règlent en écoutant, la boucle suit les changements
- Écouter la sélection (bouton ou Maj+Espace) : lit uniquement la plage choisie puis s'arrête ; touche F / F11 pour le plein écran
- Import vidéo par dialogue ou par glisser-déposer (un projet .acsproject déposé est ouvert), forme d'onde, lecture avec contrôles de transport (lecture/pause avec Espace, stop, ±5 s, volume) ; touches I / O pour marquer le début / la fin de la sélection à la position de lecture, Entrée pour créer la séquence
- Lecteur vidéo intégré : la vidéo source est visualisée pendant la lecture et le déplacement sur la forme d'onde, pour repérer visuellement les passages à extraire (repli automatique sur l'audio extrait si le format n'est pas décodable par Qt)
- Séquences existantes affichées en zones colorées, avec leur nom, sur la forme d'onde ; un clic sur une zone sélectionne la séquence, un double-clic (zone ou ligne de la liste) la lit
- Repères sur la timeline (M pour en poser un à la tête de lecture, Maj+M pour le retirer, Alt+↑/↓ pour aller au précédent/suivant, Alt+S pour sélectionner l'intervalle entre les deux repères encadrants) : affichés en traits étiquetés sur la forme d'onde, où on les tire pour les déplacer et on les double-clique pour les renommer ; toutes ces actions sont annulables et les repères sont enregistrés dans le projet
- Ajustement des bornes d'une séquence existante (poignées sur la waveform) et division à la tête de lecture, annulables ; les traitements sont conservés
- Création et gestion de séquences (début/fin, réorganisation par glisser-déposer, sélection multiple : suppression, duplication et traitement en lot)
- Découpage aux repères (menu Séquences) : chaque tranche délimitée par deux repères devient une séquence, nommée d'après le repère qui l'ouvre, avec le même aperçu à cocher que le découpage automatique
- Découpage aux repères (menu Séquences) : chaque tranche délimitée par deux repères devient une séquence, nommée d'après le repère qui l'ouvre, avec le même aperçu à cocher que le découpage automatique
- Découpage automatique en séquences selon les silences, avec aperçu des passages détectés (à cocher), annulable en une action
- Écouter avant / après dans la fenêtre de traitement : les 15 premières secondes de la séquence sont extraites puis traitées avec les réglages à l'écran, jouées brutes puis traitées à la suite, les deux formes d'onde côte à côte
- Comparaison A/B (bouton Original, Ctrl+B) : bascule en cours d'écoute entre l'audio brut et l'audio traité, à la même position
- Traitement audio non destructif : réduction de bruit, anti-ronflement (de-hum), de-click, compression réglable (ratio et seuil), gain, fondus, normalisation par crête (cible en dBFS, mesurée puis corrigée au gain constant) ou en loudness (LUFS)
- Fenêtre de traitement en cartes : profils cliquables à gauche (Voix parlée, Interview, Podcast, Conférence, Enregistrement micro, Voix faible), réglages groupés par thème à droite (réduction de bruit, nettoyage, égaliseur, normalisation, compression, gain et fondus, suppression des silences) ; toucher un réglage quitte le profil, « Enregistrer comme profil… » garde les réglages courants sous un nom (clic droit sur la vignette pour le supprimer), et « Appliquer » traite la sélection entière
- Deux dispositions de la fenêtre au choix (menu Affichage > Disposition, ou le bouton « Disposition » de la barre d'outils), choix mémorisé : « A » lecteur vidéo et source à gauche, waveform et outils au centre, séquences à droite ; « B » séquences à gauche, lecteur au centre, source et séquence sélectionnée à droite, waveform sur toute la largeur en bas (hauteur du bandeau réglable à la poignée)
- Chaque colonne se redimensionne à la souris (poignées entre les panneaux, dans les deux dispositions), avec une largeur minimale lisible
- Thèmes sombre et clair (menu Affichage), choix mémorisé
- Titre de fenêtre avec astérisque si modifications non sauvegardées, confirmation avant fermeture, nouvel import ou ouverture d'un autre projet
- Raccourcis clavier des boutons (infobulles) : Suppr, Ctrl+D, F2, Ctrl+L (séquences) ; Ctrl+Entrée, Ctrl+Maj+Entrée, Ctrl+R (traitement) ; Ctrl+M (fusion) ; F1 : liste complète des raccourcis ; Alt+←/→, Ctrl+Espace (lecture)
- Barres de progression réelles (pourcentage) pour l'export et les traitements audio
- Barre d'état : nombre de séquences et durée fusionnée estimée
- Suppression des silences et fusion avec fondu enchaîné (crossfade)
- Normalisation optionnelle du volume à l'export (loudness LUFS)
- Option « ouvrir le dossier » à la fin de l'export
- Fenêtre « Fusion et export » en cartes : mode de fusion (bout à bout ou fondu enchaîné, dont l'effet sur la durée est chiffré), format et qualité en WAV, MP3, FLAC, M4A (AAC), OGG ou Opus, fréquence d'échantillonnage, aperçu écoutable du résultat fusionné avec ses jonctions marquées, un seul fichier ou un par séquence, destination proposée à côté de la vidéo source
- Export interruptible : la progression nomme la séquence en cours et estime le temps restant ; l'interrompre laisse le projet intact
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