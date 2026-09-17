---
name: feedback-autonomous-phases
description: User wants all remaining AudioCut Studio phases completed autonomously without per-phase confirmation
metadata:
  type: feedback
---

For the AudioCut Studio project, the user explicitly said: "tu termine tous les phase j'accepte tous sans me demande" (finish all the phases, I accept everything without asking me).

**Why:** Up through Phase 3, each phase was proposed via EnterPlanMode/ExitPlanMode and the user confirmed with "oui" each time. The user got tired of the confirmation loop and wants the remaining phases (séquences, fusion/export, nettoyage audio, silences/crossfade/undo, profils vocaux) built straight through.

**How to apply:** For this project, stop using EnterPlanMode to request approval between phases. Keep the same engineering discipline (tests after each step, atomic git commits, non-destructive source files, clear error messages) but move directly from one phase to the next without pausing for a yes/no. Still give brief status updates as work progresses. This preference is scoped to finishing out the phases of this specific spec — not a general "always skip plan mode" rule for other projects unless the user says so.
