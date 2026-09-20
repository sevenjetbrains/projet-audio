---
name: project-status
description: État d'avancement d'AudioCut Studio et prochaine étape (point de reprise)
metadata:
  type: project
---

Dernier point de reprise : commit `1252d12` sur `main` (github.com/sevenjetbrains/projet-audio), 216 tests verts (`pytest`).

**Fait depuis la reprise (session distante) :** formats d'export FLAC/M4A/OGG/Opus, export un fichier par séquence, normalisation loudness à l'export, destination proposée, contrôles de lecture (stop, ±5 s, volume), menu Projets récents, raccourcis I/O/Entrée, barre d'état, thème clair (Affichage > Thème), glisser-déposer (vidéo ou .acsproject), suivi des modifications non sauvegardées (astérisque + confirmations), traitements audio annulables, sélection multiple (supprimer/dupliquer/traiter en lot), découpage automatique selon les silences, raccourcis clavier des boutons + aide F1, progression réelle (%), séquences en zones colorées sur la forme d'onde (clic = sélection, double-clic = lecture).

**Fait dans cette session (locale) :** correction de la tête de lecture pendant la lecture d'une séquence — elle affiche maintenant `source_start + position` au lieu de la position brute dans le fichier de la séquence. Le clic sur la waveform pour chercher une position recharge désormais la piste source si une séquence (ou le résultat fusionné) était en cours de lecture. Le résultat fusionné (ordre différent, crossfades) n'a pas de correspondance simple avec la timeline source : la tête de lecture n'y est plus mise à jour (au lieu d'afficher une position erronée).

**Lecteur vidéo (demandé par l'utilisateur) :** `app/ui/video_preview.py` (QVideoWidget + placeholder) branché sur le QMediaPlayer de `TransportControls` via `set_video_output`. La lecture de la *source* utilise désormais le fichier **vidéo** (image + son synchronisés nativement, aucune dérive) et non plus `source.wav` ; le WAV reste utilisé pour la waveform, les découpes et la lecture des séquences/fusion. Si Qt ne décode pas le format, `playback_error` déclenche un repli unique sur le WAV extrait (message en barre d'état).

**Prochaine étape :** aucune identifiée pour l'instant — demander à l'utilisateur, ou proposer une amélioration (ex. la timeline visuelle avancée §13 du spec original, ou le "aperçu avant suppression" des silences détectés côté UI qui manque encore).

**Pièges connus :**
- `grab()` renvoie des pixels physiques (écran à 125 %) : convertir avec `devicePixelRatio()` dans les tests de rendu.
- `QMessageBox.question` est neutralisé par une fixture autouse de `tests/conftest.py` (sinon la fermeture d'une fenêtre « modifiée » bloque les tests).
- Un `QMimeData` passé à un événement Qt doit rester référencé par le test (sinon crash).
- Éditer les fichiers en conservant leurs fins de ligne (CRLF sur Windows).
- `SequenceListWidget.play_requested` émet désormais `(name, audio_path, source_start)` — 3 arguments, pas 2 (changé pour cette correction).

Voir aussi [[feedback-commit-push-autonomy]] et [[feedback-autonomous-phases]].
