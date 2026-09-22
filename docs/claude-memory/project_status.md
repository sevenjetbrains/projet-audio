---
name: project-status
description: État d'avancement d'AudioCut Studio et prochaine étape (point de reprise)
metadata:
  type: project
---

Dernier point de reprise : `main` à jour (github.com/sevenjetbrains/projet-audio), 821 tests verts (`pytest`).

**Fait avant cette session :** tout le pipeline (extraction, sélection, séquences, traitement audio non destructif, fusion, export multi-formats, projet .acsproject, undo/redo, autosave, thèmes, raccourcis + aide F1), puis la maquette de la fenêtre principale, le lecteur vidéo intégré, le plein écran avec barre de contrôle, l'aperçu fluide (copie allégée), l'écoute de la sélection, la boucle, les poignées de bornes sur la waveform, l'ajustement/division des séquences existantes et la comparaison A/B.

**Fait dans cette session (repères) :**
- `app/models/marker.py` (`Marker`), `project.markers`, `app/services/marker_service.py` ; les repères sont sérialisés dans `.acsproject` (clé `markers`, absente = aucun repère, les anciens projets se chargent).
- Affichage sur la waveform : trait pointillé + fanion étiqueté en bas (pour ne pas masquer les pastilles de séquences en haut), jeton de palette `marker` ajouté aux deux thèmes.
- Raccourcis : `M` poser, `Maj+M` retirer, `Alt+↑/↓` naviguer, `Alt+S` sélectionner l'intervalle encadrant. Tout passe par la pile d'undo partagée (`_push_marker_command`) et marque le projet modifié.
- Souris : glisser un repère le déplace (position émise une seule fois au relâchement = un seul pas d'undo), double-clic le renomme. Un repère gagne le double-clic contre une zone de séquence (cible fine) ; une poignée de sélection gagne l'appui contre un repère (geste plus fréquent).
- « Créer les séquences depuis les repères… » (menu Séquences) : `marker_service.intervals()` découpe aux repères, `SplitPreviewDialog` (partagé avec le découpage auto) affiche une colonne « Nom » et laisse décocher, `create_sequences_from_ranges(..., names=...)` nomme chaque séquence d'après le repère qui l'ouvre.

**Fait ensuite (écran d'accueil, d'après une maquette fournie par l'utilisateur) :**
- `app/ui/welcome_view.py` + `QStackedWidget` dans la fenêtre : page 0 l'accueil, page 1 l'éditeur ; on bascule sur l'éditeur à `audio_ready`.
- Zone de dépôt (mise en évidence pendant un survol de fichier), boutons import/ouverture, pastilles de formats, projets récents décrits par `recent_projects.describe_recent_projects()` (nombre de séquences lu dans le `.acsproject`, date de modification), pied de page des raccourcis.
- Menus « Édition / Séquences / Traitement » grisés sans projet, coin de barre de menus « Aucun projet ouvert », version de FFmpeg en barre d'état (`FFmpegService.version()`).
- La récupération d'autosave est un bandeau de l'accueil, plus une `QMessageBox` au lancement (`project_service.describe_autosave`).
- Progression de l'import sur l'accueil, annulable : `extract_audio(..., should_cancel=...)` lève `FFmpegCancelled`, `ExtractAudioWorker.cancel()`, `VideoPanel.cancel_extraction()` nettoie le projet à demi créé.
- Nouveautés transverses : `app/utils/date_utils.py` (dates FR), jetons `warning`/`warning_soft`, icônes `upload`/`folder`/`alert`, `set_label_icon(..., size=)`, `design.kbd()` et `design.labelled_icon_button()`.

**Fait ensuite (fenêtre de traitement audio, d'après une seconde maquette) :**
- Réglages ajoutés au modèle : `compression_ratio`, `compression_threshold_db`, `normalize_peak_dbfs`. La normalisation « peak » était en fait `dynaudnorm` (un niveleur dynamique) : c'est maintenant une mesure `volumedetect` (`FFmpegService.measure_peak_db`) suivie d'un gain constant ; `build_filter_chain(..., measured_peak_db=None)` saute l'étape sans mesure plutôt que d'inventer un gain.
- `app/ui/controls.py` : `ToggleSwitch` (peint), `SegmentedControl`, `SliderRow` (QSlider entier → valeur décimale), `ProfileCard`. Qt n'a ni interrupteur ni groupe segmenté.
- `audio_processing_panel.py` entièrement redessiné : en-tête, colonne de profils, cartes thématiques, pied de page. `ProcessingDialog` n'est plus qu'un hôte sans marge. Un seul bouton « Appliquer » (la sélection entière s'il y a plusieurs séquences) : `Ctrl+Maj+Entrée` a disparu.
- Aperçu « Écouter avant / après » : `audio_processor.build_preview()` (15 s, brut + traité, deux fichiers fixes réécrits), `app/ui/preview_strip.py` (les deux formes d'onde côte à côte + tête de lecture), lecteur `QMediaPlayer` propre au panneau qui enchaîne brut → traité.
- Profils enregistrés : `app/services/custom_profiles.py` (`custom_profiles.json`, ignoré par git), bouton « Enregistrer comme profil… », suppression par clic droit sur la vignette.

**Fait ensuite (fenêtre « Fusion et export », troisième maquette) :**
- `export_dialog.py` refait en cartes : mode de fusion (le fondu enchaîné se règle désormais ici et est réécrit dans `project.crossfade_duration`), format en `SegmentedControl(columns=3)` + qualité + échantillonnage, aperçu du résultat fusionné, « ce qui est exporté », destination, progression.
- `MergedWaveStrip` (dans `preview_strip.py`) : forme d'onde du résultat avec les jonctions peintes en clair ; `ExportDialog._junction_fractions()` les calcule depuis les durées et le fondu.
- Export interruptible : `export_audio`/`apply_filters` prennent `should_cancel`, `export_project`/`export_sequences_separately` le vérifient entre les étapes et annoncent l'étape via `on_stage`, `ExportWorker` (workers/ffmpeg_worker.py) émet `cancelled` au lieu de `failed`.
- `export_audio(..., sample_rate=)` ajoute `-ar` ; temps restant estimé depuis le temps écoulé (`QElapsedTimer`).

**Fait ensuite (mise en page vs taille d'écran, trouvé en lançant l'application) :**
- L'écran de test fait 1024×544 logiques ; la fenêtre en exigeait 1357×767, et Windows rognait le bord droit et le bas. Minimum ramené à 650×449 pour l'accueil.
- Les deux pages (accueil et éditeur) sont dans un `QScrollArea` (`MainWindow._scrollable`) : une fenêtre trop petite fait défiler au lieu de perdre du contenu. La page d'accueil n'est donc plus l'enfant direct de `_pages` — d'où `setCurrentIndex(0)` et `currentWidget().widget()` dans les tests.
- Colonnes latérales de l'éditeur rognées à parts égales quand l'écran est trop étroit (`_column_widths`), colonne de l'accueil dimensionnée dans `WelcomeView.resizeEvent` d'après la largeur réelle de la page.
- Le libellé d'aide de la waveform imposait 555 px au panneau central : passé en `QSizePolicy.Ignored`.

**Fait ensuite (deuxième disposition de la fenêtre principale, d'après une maquette fournie) :**
- `app/ui/editor_layouts.py` : les panneaux de l'éditeur sont construits par disposition (`build_body(name, EditorWidgets)`), la fenêtre ne fait plus que les posséder. Changer de disposition rebâtit ce seul arbre ; les widgets partagés sont reparentés et gardent leur état, leurs connexions et la lecture en cours.
- Disposition « B » : séquences à gauche, lecteur au centre, colonne « inspecteur » à droite (source, séquence sélectionnée, traitement, découpage par silences, fusion), waveform + sélection sur toute la largeur en bas, dans un `QSplitter` vertical (sans lui, l'aperçu vidéo pleine largeur monte à 420 px et écrase le bandeau).
- `app/ui/selected_sequence_card.py` : carte « séquence sélectionnée », propre à la disposition B. Elle n'existe donc pas en A : la fenêtre la récupère par `findChild` après chaque bascule (`_adopt_layout_extras`) et `_selected_sequence_card` vaut `None` en A. Le profil de traitement de la maquette n'est pas affiché : il n'est mémorisé nulle part (seul l'existence d'un `processed_audio_path` est vérifiable).
- `app/config/layouts.py` : identifiants + préférence persistée dans `layout.json` (ignoré par git), calqué sur `themes.py`. Bouton « Disposition A/B » dans la barre d'outils (il tourne en rond) et sous-menu Affichage > Disposition.
- QSS : `#bottomPanel` (bandeau du bas) et la poignée `QSplitter#editorSplitter`.
- Corrigé en lançant l'application (fenêtre de 814 px) : le bandeau de la waveform passait sous la ligne de flottaison et la carte « Découpage par silences » débordait de la colonne de droite. Les trois colonnes de B défilent maintenant chacune pour elle-même (`_scrollable_column`), le découpage par silences est passé à côté de la carte Sélection dans le bandeau (il lui faut de la largeur), et l'aide « l'image suit la waveform » est masquée en B (`VideoPlayerPanel.set_hint_visible`). Minimum du corps : 816 px → 578.
- `_EditorSplitter` répartit au premier `showEvent`, pas à la construction : un `setSizes()` posé avant que le splitter ait sa hauteur est ramené à la taille par défaut, et toute la place allait au bandeau.

**Prochaine étape :** aucune identifiée — demander à l'utilisateur, ou proposer une amélioration (pistes non traitées : export d'un rapport/liste des séquences, recherche-filtre dans la liste, aimantation des bornes sur les silences détectés ou sur un passage par zéro).

**Pièges connus :**
- Écran à 125 % : `QScreen.availableGeometry()` est en pixels écran, les widgets en pixels logiques. Diviser par `devicePixelRatio()` avant de comparer (`MainWindow._available_size`).
- Demander une fenêtre à la taille exacte de la zone de travail la fait maximiser par Windows, qui la fait déborder de ~7 px par côté : garder une marge (`_SCREEN_MARGIN`).
- Une capture d'écran faite par un outil non adapté au DPI (PowerShell + `GetWindowRect`/`CopyFromScreen`) renvoie la fenêtre à 80 % de sa taille réelle et tronque l'image : on croit à tort que la mise en page déborde. Capturer depuis Qt (`window.grab()`) pour juger un rendu.
- `grab()` renvoie des pixels physiques (écran à 125 %) : convertir avec `devicePixelRatio()` dans les tests de rendu.
- `QMessageBox.question` est neutralisé par une fixture autouse de `tests/conftest.py` (sinon la fermeture d'une fenêtre « modifiée » bloque les tests).
- Un `QMimeData` passé à un événement Qt doit rester référencé par le test (sinon crash).
- Fins de ligne mélangées dans le dépôt (`core.autocrlf=true`) : `app/ui/*.py` et `README.md` sont en CRLF, `app/models/*.py` et `app/services/project_service.py` en LF. Éditer en réécrivant avec le même `newline=` qu'à la lecture, sinon le diff couvre tout le fichier.
- `SequenceListWidget.play_requested` émet `(name, audio_path, source_start)` — 3 arguments.
- `deleteLater()` seul ne retire pas un widget de l'arbre : les vignettes de projets récents sont détachées par `setParent(None)` avant, sinon elles restent visibles (et dans `findChildren`) jusqu'au prochain tour de boucle.
- Tester la visibilité d'une carte d'un écran non affiché demande `isVisibleTo(parent)`, pas `isVisible()`.
- Ne pas écrire une séquence d'échappement `backslash-n` dans une chaîne Python passée par heredoc à `python -` : elle est convertie en vrai saut de ligne avant d'arriver à Python, et un `str.replace` ciblant ce littéral échoue. Passer par une expression régulière sur les lignes.
- La fenêtre de traitement ne se désactive plus en bloc sans séquence : la croix et « Annuler » restent actifs, sinon la fenêtre ne pourrait plus se fermer. Voir `_set_editing_enabled`.
- Une fenêtre qui importe une fonction de service par son nom ne voit pas un `monkeypatch` du module de service : patcher `app.ui.<fenêtre>.<fonction>`.
- `should_cancel` est consulté pendant l'encodage, pas seulement entre deux étapes : un test qui compte les appels annule plus tôt qu'il ne croit.
- `SliderRow.set_value()` est silencieux (c'est un chargement) ; simuler une édition utilisateur dans un test demande `row.slider.setValue(...)`.
- Une disposition doit poser **tous** les widgets partagés : un widget oublié se retrouve sans parent, donc en fenêtre flottante. `tests/test_editor_layouts.py::test_every_layout_hosts_every_shared_panel` monte la garde.
- `QScrollArea.setWidget()` détruit le widget précédent : détacher l'ancien corps par `takeWidget()` **avant** de construire le nouveau, sinon les panneaux partagés partent avec lui.
- Les raccourcis à une seule touche (`I`, `O`, `L`, `M`, `F`) sont des `QShortcut` de fenêtre : ils volent la frappe aux champs de saisie non modaux. Le renommage passe par un `QInputDialog` modal, donc sans conflit — garder cette contrainte en tête avant d'ajouter un champ éditable en ligne.

Voir aussi [[feedback-commit-push-autonomy]] et [[feedback-autonomous-phases]].
