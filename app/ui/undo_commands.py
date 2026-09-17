"""Commande Undo/Redo générique (§17/§34) : encapsule une paire de callables réversibles."""

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand


class CallbackCommand(QUndoCommand):
    """QUndoCommand générique : `redo_fn`/`undo_fn` doivent être idempotents et symétriques."""

    def __init__(self, description: str, redo_fn: Callable[[], None], undo_fn: Callable[[], None]) -> None:
        super().__init__(description)
        self._redo_fn = redo_fn
        self._undo_fn = undo_fn

    def redo(self) -> None:
        self._redo_fn()

    def undo(self) -> None:
        self._undo_fn()
