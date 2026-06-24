"""Verschiebbares Overlay über einem Bild der Seite.

Wie beim Text bleibt das Originalbild im Hintergrund sichtbar, bis es
verschoben wird; dann verdeckt ein Cover-Rechteck das Original und das Item
zeigt eine Vorschau des Bildes an seiner neuen Position.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from app.edits.edit_model import ImageEdit

_SELECT_PEN = QPen(QColor(0, 120, 215), 0, Qt.PenStyle.DashLine)
_HOVER_PEN = QPen(QColor(0, 120, 215, 130), 0, Qt.PenStyle.DotLine)


class ImageItem(QGraphicsItem):
    def __init__(self, info: dict, page_index: int, item_id: str, edit_model, page_view,
                 preview: QPixmap | None = None) -> None:
        super().__init__()
        self._ready = False
        self.page_index = page_index
        self.item_id = item_id
        self.edit_model = edit_model
        self.page_view = page_view
        self._hover = False

        self.xref = int(info.get("xref", 0))
        self.orig_rect = tuple(float(v) for v in info["bbox"])
        self._w = self.orig_rect[2] - self.orig_rect[0]
        self._h = self.orig_rect[3] - self.orig_rect[1]
        self._preview = preview

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setPos(self.orig_rect[0], self.orig_rect[1])
        self._ready = True

    def has_edit(self) -> bool:
        return self.edit_model.get(self.page_index, self.item_id) is not None

    def set_movable(self, movable: bool) -> None:
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)

    def mark_deleted(self) -> None:
        edit = self._build_edit()
        edit.deleted = True
        self.edit_model.set(edit)
        self.setVisible(False)
        self.page_view.update_cover(self)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None) -> None:
        rect = self.boundingRect()
        if self.has_edit() and self._preview is not None:
            painter.drawPixmap(rect.toRect(), self._preview)
        if self.isSelected():
            painter.setPen(_SELECT_PEN)
            painter.drawRect(rect)
        elif self._hover:
            painter.setPen(_HOVER_PEN)
            painter.drawRect(rect)

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if not self._ready:
            return super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._register_edit()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.page_view.selection_changed(self if value else None)
            self.update()
        return super().itemChange(change, value)

    def _build_edit(self) -> ImageEdit:
        pos = self.pos()
        new_rect = (pos.x(), pos.y(), pos.x() + self._w, pos.y() + self._h)
        return ImageEdit(
            page=self.page_index,
            item_id=self.item_id,
            xref=self.xref,
            orig_rect=self.orig_rect,
            new_rect=new_rect,
        )

    def _register_edit(self) -> None:
        if not self._ready:
            return
        pos = self.pos()
        moved = abs(pos.x() - self.orig_rect[0]) > 0.5 or abs(pos.y() - self.orig_rect[1]) > 0.5
        if not moved:
            self.edit_model.remove(self.page_index, self.item_id)
        else:
            self.edit_model.set(self._build_edit())
        self.page_view.update_cover(self)
        self.page_view.document_modified()
