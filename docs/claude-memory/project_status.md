---
name: project-status
description: État d'avancement d'AudioCut Studio et prochaine étape (point de reprise)
metadata:
  type: project
---

Dernier point de reprise : commit `d197244` sur `main`, 211 tests verts (`pytest`).

**Fait depuis la reprise :** formats d'export FLAC/M4A/OGG/Opus, export un fichier par séquence, normalisation loudness à l'export, destination proposée, contrôles de lecture (stop, ±5 s, volume), menu Projets récents, raccourcis I/O/Entrée, barre d'état, thème clair (Affichage > Thème), glisser-déposer (vidéo ou .acsproject), suivi des modifications non sauvegardées (astérisque + confirmations), traitements audio annulables, sélection multiple (supprimer/dupliquer/traiter en lot), découpage automatique selon les silences, raccourcis clavier des boutons + aide F1, progression réelle (%), séquences en zones colorées sur la forme d'onde (clic = sélection, double-clic = lecture).

**Prochaine étape prévue :** la tête de lecture de la forme d'onde suit la position dans le fichier de la *séquence* jouée, pas dans la source : afficher la bonne position (source_start + position) pendant la lecture d'une séquence.

**Pièges connus :**
- `grab()` renvoie des pixels physiques (écran à 125 %) : convertir avec `devicePixelRatio()` dans les tests de rendu.
- `QMessageBox.question` est neutralisé par une fixture autouse de `tests/conftest.py` (sinon la fermeture d'une fenêtre « modifiée » bloque les tests).
- Un `QMimeData` passé à un événement Qt doit rester référencé par le test (sinon crash).
- Éditer les fichiers en conservant leurs fins de ligne (CRLF sur Windows).
