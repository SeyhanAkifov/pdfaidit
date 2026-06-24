"""Verwaltet alle ausstehenden Änderungen am Dokument inkl. Undo/Redo.

Das EditModel ist die *Quelle der Wahrheit*: Beim Wechseln zwischen Seiten
werden Overlay-Items aus dem Original-PDF neu erzeugt und anschließend mit den
hier gespeicherten Änderungen wiederhergestellt. Beim Speichern liest
``PdfDocument.apply_edits`` dieses Modell aus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class TextEdit:
    """Eine Änderung an einem Text-Span (verschoben, editiert oder gelöscht)."""

    page: int
    item_id: int
    orig_rect: tuple[float, float, float, float]  # (x0, y0, x1, y1) in Punkten
    orig_text: str
    fontname: str          # PDF-Basisfont-Name für insert_textbox (z. B. "helv")
    fontsize: float
    color: tuple[float, float, float]  # RGB 0..1
    new_text: str
    new_origin: tuple[float, float]    # (x, y) obere linke Ecke in Punkten
    deleted: bool = False

    @property
    def is_changed(self) -> bool:
        moved = (
            abs(self.new_origin[0] - self.orig_rect[0]) > 0.5
            or abs(self.new_origin[1] - self.orig_rect[1]) > 0.5
        )
        return self.deleted or moved or (self.new_text != self.orig_text)


@dataclass
class ImageEdit:
    """Eine Verschiebung (oder Löschung) eines Bildes."""

    page: int
    item_id: str
    xref: int
    orig_rect: tuple[float, float, float, float]
    new_rect: tuple[float, float, float, float]
    deleted: bool = False


@dataclass
class AnnotEdit:
    """Eine neu hinzugefügte Annotation/Zeichnung."""

    page: int
    item_id: str
    kind: str  # "highlight" | "rect" | "ink" | "note" | "text"
    # Geometrie je nach Art: rect=(x0,y0,x1,y1); ink=Liste von Punktlisten
    rect: tuple[float, float, float, float] | None = None
    points: list[list[tuple[float, float]]] = field(default_factory=list)
    color: tuple[float, float, float] = (1.0, 0.0, 0.0)
    width: float = 1.5
    text: str = ""


@dataclass
class FormEdit:
    """Ein ausgefülltes/geändertes Formularfeld (per Feldname identifiziert)."""

    page: int
    item_id: str       # = field_name
    field_name: str
    value: str


Edit = TextEdit | ImageEdit | AnnotEdit | FormEdit


class EditModel:
    """Hält alle Änderungen, gruppiert nach (Seite, Item-ID), mit Undo/Redo."""

    def __init__(self) -> None:
        self._edits: dict[tuple[int, object], Edit] = {}
        self._undo: list[tuple[tuple[int, object], Edit | None]] = []
        self._redo: list[tuple[tuple[int, object], Edit | None]] = []

    # --- Abfragen -------------------------------------------------------
    def get(self, page: int, item_id: object) -> Edit | None:
        return self._edits.get((page, item_id))

    def is_empty(self) -> bool:
        return not self._edits

    def edits_by_page(self) -> dict[int, list[Edit]]:
        result: dict[int, list[Edit]] = {}
        for edit in self._edits.values():
            result.setdefault(edit.page, []).append(edit)
        return result

    # --- Mutationen -----------------------------------------------------
    def set(self, edit: Edit) -> None:
        key = (edit.page, edit.item_id)
        previous = self._edits.get(key)
        self._undo.append((key, previous))
        self._redo.clear()
        self._edits[key] = edit

    def remove(self, page: int, item_id: object) -> None:
        key = (page, item_id)
        if key not in self._edits:
            return
        self._undo.append((key, self._edits[key]))
        self._redo.clear()
        del self._edits[key]

    def clear(self) -> None:
        self._edits.clear()
        self._undo.clear()
        self._redo.clear()

    # --- Undo / Redo ----------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> tuple[int, object] | None:
        if not self._undo:
            return None
        key, previous = self._undo.pop()
        current = self._edits.get(key)
        self._redo.append((key, current))
        if previous is None:
            self._edits.pop(key, None)
        else:
            self._edits[key] = previous
        return key

    def redo(self) -> tuple[int, object] | None:
        if not self._redo:
            return None
        key, value = self._redo.pop()
        current = self._edits.get(key)
        self._undo.append((key, current))
        if value is None:
            self._edits.pop(key, None)
        else:
            self._edits[key] = value
        return key
