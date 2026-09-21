---
name: project-status
description: État d'avancement d'AudioCut Studio et prochaine étape (point de reprise)
metadata:
  type: project
---

Dernier point de reprise : commit `7edd0ca` sur `main` (github.com/sevenjetbrains/projet-audio), 507 tests verts (`pytest`).

**Fait avant cette session :** tout le pipeline (extraction, sélection, séquences, traitement audio non destructif, fusion, export multi-formats, projet .acsproject, undo/redo, autosave, thèmes, raccourcis + aide F1), puis la maquette de la fenêtre principale, le lecteur vidéo intégré, le plein écran avec barre de contrôle, l'aperçu fluide (copie allégée), l'écoute de la sélection, la boucle, les poignées de bornes sur la waveform, l'ajustement/division des séquences existantes et la comparaison A/B.

**Fait dans cette session (repères) :**
- `app/models/marker.py` (`Marker`), `project.markers`, `app/services/marker_service.py` ; les repères sont sérialisés dans `.acsproject` (clé `markers`, absente = aucun repère, les anciens projets se chargent).
- Affichage sur la waveform : trait pointillé + fanion étiqueté en bas (pour ne pas masquer les pastilles de séquences en haut), jeton de palette `marker` ajouté aux deux thèmes.
- Raccourcis : `M` poser, `Maj+M` retirer, `Alt+↑/↓` naviguer, `Alt+S` sélectionner l'intervalle encadrant. Tout passe par la pile d'undo partagée (`_push_marker_command`) et marque le projet modifié.
- Souris : glisser un repère le déplace (position émise une seule fois au relâchement = un seul pas d'undo), double-clic le renomme. Un repère gagne le double-clic contre une zone de séquence (cible fine) ; une poignée de sélection gagne l'appui contre un repère (geste plus fréquent).
- « Créer les séquences depuis les repères… » (menu Séquences) : `marker_service.intervals()` découpe aux repères, `SplitPreviewDialog` (partagé avec le découpage auto) affiche une colonne « Nom » et laisse décocher, `create_sequences_from_ranges(..., names=...)` nomme chaque séquence d'après le repère qui l'ouvre.

**Prochaine étape :** aucune identifiée — demander à l'utilisateur, ou proposer une amélioration (pistes non traitées : export d'un rapport/liste des séquences, recherche-filtre dans la liste, aimantation des bornes sur les silences détectés ou sur un passage par zéro).

**Pièges connus :**
- `grab()` renvoie des pixels physiques (écran à 125 %) : convertir avec `devicePixelRatio()` dans les tests de rendu.
- `QMessageBox.question` est neutralisé par une fixture autouse de `tests/conftest.py` (sinon la fermeture d'une fenêtre « modifiée » bloque les tests).
- Un `QMimeData` passé à un événement Qt doit rester référencé par le test (sinon crash).
- Fins de ligne mélangées dans le dépôt (`core.autocrlf=true`) : `app/ui/*.py` et `README.md` sont en CRLF, `app/models/*.py` et `app/services/project_service.py` en LF. Éditer en réécrivant avec le même `newline=` qu'à la lecture, sinon le diff couvre tout le fichier.
- `SequenceListWidget.play_requested` émet `(name, audio_path, source_start)` — 3 arguments.
- Les raccourcis à une seule touche (`I`, `O`, `L`, `M`, `F`) sont des `QShortcut` de fenêtre : ils volent la frappe aux champs de saisie non modaux. Le renommage passe par un `QInputDialog` modal, donc sans conflit — garder cette contrainte en tête avant d'ajouter un champ éditable en ligne.

Voir aussi [[feedback-commit-push-autonomy]] et [[feedback-autonomous-phases]].
