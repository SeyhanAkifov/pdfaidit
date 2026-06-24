"""Editierbarer, verschiebbarer Text-Span als Overlay über der Seite.

Im Ruhezustand ist das Item *transparent* (der Originaltext aus dem
gerenderten Hintergrund bleibt sichtbar). Sobald der Span verschoben oder
editiert wird, wird der Originalbereich über ein weißes „Cover"-Rechteck
verdeckt (siehe ``PageView.update_cover``) und der neue Text vom Item gezeichnet.
"""
from __future__ import annotations

import re

import fitz
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsItem, QStyle

from app.edits.edit_model import TextEdit

_SELECT_PEN = QPen(QColor(0, 120, 215), 0, Qt.PenStyle.DashLine)
_HOVER_PEN = QPen(QColor(0, 120, 215, 130), 0, Qt.PenStyle.DotLine)
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


def qfont_from_pdf(font_name: str, size: float, family_override: str | None = None) -> QFont:
    """Baut eine möglichst passende QFont aus dem PDF-Fontnamen.

    Ist ``family_override`` gesetzt (die echte, in Qt geladene eingebettete
    Schrift), wird genau diese Familie verwendet -> pixelgenaue Vorschau.
    Sonst wird die Familie aus dem Namen erraten; Fett/Kursiv kommen immer
    aus dem Namen, damit auch ohne exakte Familie der Stil stimmt.
    """
    name = _SUBSET_PREFIX.sub("", font_name or "")
    lower = name.lower()
    bold = any(k in lower for k in ("bold", "black", "heavy", "semibold", "demi"))
    italic = "italic" in lower or "oblique" in lower

    if family_override:
        family = family_override
    else:
        family = re.split(r"[-,]", name)[0].strip() or "Helvetica"
        # Häufige PostScript-Schreibweisen leserlicher machen
        family = re.sub(r"(MT|PSMT|PS|Std)$", "", family).strip() or "Helvetica"

    font = QFont(family)
    font.setPointSizeF(max(size, 1.0))
    font.setBold(bold)
    font.setItalic(italic)
    return font


def map_pdf_fontname(font: str) -> str:
    """Bildet einen eingebetteten Fontnamen auf einen PDF-Basis-14-Font ab."""
    name = (font or "").lower()
    bold = "bold" in name or "black" in name or "heavy" in name
    italic = "italic" in name or "oblique" in name

    if "times" in name or "serif" in name and "sans" not in name:
        return {(0, 0): "tiro", (1, 0): "tibo", (0, 1): "tiit", (1, 1): "tibi"}[(bold, italic)]
    if "courier" in name or "mono" in name:
        return {(0, 0): "cour", (1, 0): "cobo", (0, 1): "coit", (1, 1): "cobi"}[(bold, italic)]
    # Standard: Helvetica-Familie
    return {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"}[(bold, italic)]


class TextItem(QGraphicsTextItem):
    def __init__(self, span: dict, page_index: int, item_id: int, edit_model, page_view,
                 qt_family: str | None = None, orig_pixmap=None) -> None:
        super().__init__()
        self._ready = False
        self.page_index = page_index
        self.item_id = item_id
        self.edit_model = edit_model
        self.page_view = page_view
        self.qt_family = qt_family
        self._orig_pixmap = orig_pixmap  # Bildausschnitt des Originals (für schriftfreie Verschiebung)
        self._editing = False
        self._hover = False

        self.orig_text = span["text"]
        self.orig_rect = tuple(float(v) for v in span["bbox"])
        self.fontsize = float(span.get("size", 11) or 11)
        self.orig_font = span.get("font", "")
        self.fontname_pdf = map_pdf_fontname(self.orig_font)

        srgb = span.get("color", 0) or 0
        try:
            self.color = tuple(fitz.sRGB_to_pdf(srgb))
        except Exception:
            self.color = (0.0, 0.0, 0.0)

        # Darstellung
        self.document().setDocumentMargin(0)
        self.setPlainText(self.orig_text)
        self.setFont(qfont_from_pdf(self.orig_font, self.fontsize, self.qt_family))
        self.setDefaultTextColor(QColor.fromRgbF(*self.color))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.setPos(self.orig_rect[0], self.orig_rect[1])
        self._ready = True

    # --- Zustand --------------------------------------------------------
    def has_edit(self) -> bool:
        return self.edit_model.get(self.page_index, self.item_id) is not None

    def set_movable(self, movable: bool) -> None:
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)

    # --- Eigenschaften (vom Properties-Panel genutzt) -------------------
    def set_fontsize(self, size: float) -> None:
        self.fontsize = float(size)
        font = self.font()
        font.setPointSizeF(max(size, 1.0))
        self.setFont(font)
        self._register_edit(force=True)
        self.update()

    def set_color(self, color: tuple[float, float, float]) -> None:
        self.color = color
        self.setDefaultTextColor(QColor.fromRgbF(*color))
        self._register_edit(force=True)
        self.update()

    def mark_deleted(self) -> None:
        edit = self._build_edit()
        edit.deleted = True
        self.edit_model.set(edit)
        self.setVisible(False)
        self.page_view.update_cover(self)

    # --- Geometrie / Zeichnen ------------------------------------------
    def _orig_size(self) -> tuple[float, float]:
        return (self.orig_rect[2] - self.orig_rect[0], self.orig_rect[3] - self.orig_rect[1])

    def boundingRect(self) -> QRectF:
        # Text-Bereich UND Original-Bildbereich abdecken (sonst Clipping)
        base = super().boundingRect()
        ow, oh = self._orig_size()
        return base.united(QRectF(0, 0, ow, oh))

    def shape(self) -> QPainterPath:
        # Gesamten Bounding-Bereich klickbar machen (nicht nur Glyphen)
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None) -> None:
        # Qt-eigene Auswahlmarkierung unterdrücken (wir zeichnen selbst)
        option.state &= ~QStyle.StateFlag.State_Selected

        edit = self.edit_model.get(self.page_index, self.item_id)
        text_changed = self._editing or (edit is not None and edit.new_text != self.orig_text)
        move_only = edit is not None and not text_changed

        if text_changed:
            # Inhalt wird geändert -> echten (editierbaren) Text rendern
            super().paint(painter, option, widget)
        elif move_only:
            # Reine Verschiebung: bei einbettbarer Schrift Vektortext, sonst Bildausschnitt
            if self.qt_family is None and self._orig_pixmap is not None:
                ow, oh = self._orig_size()
                painter.drawPixmap(QRectF(0, 0, ow, oh), self._orig_pixmap,
                                   QRectF(self._orig_pixmap.rect()))
            else:
                super().paint(painter, option, widget)

        if self.isSelected():
            painter.setPen(_SELECT_PEN)
            painter.drawRect(self.boundingRect())
        elif self._hover:
            painter.setPen(_HOVER_PEN)
            painter.drawRect(self.boundingRect())

    # --- Interaktion ----------------------------------------------------
    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._register_edit()
        super().focusOutEvent(event)
        self.update()

    def itemChange(self, change, value):
        if not self._ready:
            return super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._register_edit()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.page_view.selection_changed(self if value else None)
            self.update()
        return super().itemChange(change, value)

    # --- Edit-Modell ----------------------------------------------------
    def _build_edit(self) -> TextEdit:
        pos = self.pos()
        return TextEdit(
            page=self.page_index,
            item_id=self.item_id,
            orig_rect=self.orig_rect,
            orig_text=self.orig_text,
            fontname=self.fontname_pdf,
            orig_font=self.orig_font,
            fontsize=self.fontsize,
            color=self.color,
            new_text=self.toPlainText(),
            new_origin=(pos.x(), pos.y()),
        )

    def _register_edit(self, force: bool = False) -> None:
        if not self._ready:
            return
        edit = self._build_edit()
        if not force and not edit.is_changed:
            self.edit_model.remove(self.page_index, self.item_id)
        else:
            self.edit_model.set(edit)
        self.page_view.update_cover(self)
        self.page_view.document_modified()
