"""Overlay für ein vorhandenes Formularfeld (zum Ausfüllen per Doppelklick)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem, QInputDialog

from app.edits.edit_model import FormEdit

_FIELD_PEN = QPen(QColor(40, 160, 90, 200), 0)
_FIELD_BRUSH = QBrush(QColor(40, 160, 90, 28))


class FormFieldItem(QGraphicsItem):
    """Zeigt ein Formularfeld als grün umrandeten Bereich; Doppelklick = ausfüllen."""

    def __init__(self, widget, page_index: int, edit_model, page_view) -> None:
        super().__init__()
        self.page_index = page_index
        self.item_id = widget.field_name or f"feld@{tuple(widget.rect)}"
        self.field_name = widget.field_name or self.item_id
        self.edit_model = edit_model
        self.page_view = page_view

        r = widget.rect
        self.orig_rect = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
        self._w = self.orig_rect[2] - self.orig_rect[0]
        self._h = self.orig_rect[3] - self.orig_rect[1]
        self._current = widget.field_value or ""

        self.setAcceptHoverEvents(True)
        self.setPos(self.orig_rect[0], self.orig_rect[1])

    def _value(self) -> str:
        edit = self.edit_model.get(self.page_index, self.item_id)
        return edit.value if isinstance(edit, FormEdit) else self._current

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, max(self._w, 1), max(self._h, 1))

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None) -> None:
        rect = self.boundingRect()
        painter.setPen(_FIELD_PEN)
        painter.setBrush(_FIELD_BRUSH)
        painter.drawRect(rect)
        value = self._value()
        if value:
            painter.setPen(QPen(QColor(0, 0, 0)))
            font = QFont()
            font.setPointSizeF(max(min(self._h * 0.6, 12), 6))
            painter.setFont(font)
            painter.drawText(rect.adjusted(2, 0, -2, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, value)

    def mouseDoubleClickEvent(self, event) -> None:
        value, ok = QInputDialog.getText(
            self.page_view, "Formularfeld ausfüllen",
            f'Wert für „{self.field_name}":', text=self._value()
        )
        if ok:
            self.edit_model.set(FormEdit(self.page_index, self.item_id, self.field_name, value))
            self.page_view.document_modified()
            self.update()
        super().mouseDoubleClickEvent(event)
