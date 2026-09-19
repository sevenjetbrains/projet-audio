---
name: feedback-commit-push-autonomy
description: Commit et push automatiques après chaque fonctionnalité terminée, enchaîner sans demander
metadata:
  type: feedback
---

L'utilisateur a demandé : commit à chaque fonctionnalité terminée « sans me demander », puis push GitHub « sans me demander », et d'enchaîner les fonctionnalités (y compris celles liées aux raccourcis) sans validation intermédiaire.

**Why:** les confirmations répétées le gênaient.

**How to apply:** fonctionnalité finie + tests verts → commit atomique puis `git push origin HEAD` (branche `main` de https://github.com/sevenjetbrains/projet-audio.git), rapport bref. Pas de `--force`. Voir aussi [[feedback-autonomous-phases]].
