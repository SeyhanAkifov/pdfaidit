"""Die Seitenleinwand: rendert eine Seite und legt interaktive Overlays darüber."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
)

from app.edits.edit_model import AnnotEdit
from app.items.form_item import FormFieldItem
from app.items.image_item import ImageItem
from app.items.text_item import TextItem
from app.qt_utils import fitz_pixmap_to_qpixmap
from app.tools.tool_manager import Tool

_WHITE = QBrush(QColor(255, 255, 255))


class PageView(QGraphicsView):
    itemSelected = pyqtSignal(object)   # ausgewähltes Item oder None
    modified = pyqtSignal()             # Dokument wurde verändert

    RENDER_ZOOM = 2.0  # Render-Auflösung des Hintergrundbildes (Schärfe)

    def __init__(self, document, edit_model, tool_manager, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.edit_model = edit_model
        self.tools = tool_manager

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.current_page = -1
        self.text_items: list[TextItem] = []
        self.image_items: list[ImageItem] = []
        self.form_items: list = []
        self._view_zoom = 1.0
        self._annot_seq = 0

        # Zustand fürs Zeichnen
        self._drawing = False
        self._draw_start = None
        self._draw_points: list[tuple[float, float]] = []
        self._temp_item = None

    # --- Seite laden ----------------------------------------------------
    def load_page(self, index: int) -> None:
        if not self.document.is_open or not (0 <= index < self.document.page_count):
            return
        self.current_page = index
        self.scene.clear()
        self.text_items.clear()
        self.image_items.clear()
        self.form_items = []

        rect = self.document.page_rect(index)
        self.scene.setSceneRect(0, 0, rect.width, rect.height)

        # Hintergrund (gerendertes Seitenbild, auf Punkte herunterskaliert)
        pix = self.document.render_pixmap(index, self.RENDER_ZOOM)
        qpix = fitz_pixmap_to_qpixmap(pix)
        bg = self.scene.addPixmap(qpix)
        bg.setScale(1.0 / self.RENDER_ZOOM)
        bg.setZValue(-100)
        bg.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._page_pixmap = qpix

        # Text-Overlays
        for i, span in enumerate(self.document.get_text_spans(index)):
            item = TextItem(span, index, i, self.edit_model, self)
            item.setZValue(10)
            self.scene.addItem(item)
            self.text_items.append(item)
            self._restore_text(item)

        # Bild-Overlays
        for i, info in enumerate(self.document.get_images(index)):
            if "bbox" not in info:
                continue
            preview = self._image_preview(info["bbox"], qpix)
            item = ImageItem(info, index, f"img{i}", self.edit_model, self, preview)
            item.setZValue(5)
            self.scene.addItem(item)
            self.image_items.append(item)
            self._restore_image(item)

        # Formularfeld-Overlays
        self.form_items = []
        for widget in self.document.get_widgets(index):
            item = FormFieldItem(widget, index, self.edit_model, self)
            item.setZValue(6)
            self.scene.addItem(item)
            self.form_items.append(item)

        # Annotation-Overlays aus dem Modell wiederherstellen
        for edit in self.edit_model.edits_by_page().get(index, []):
            if isinstance(edit, AnnotEdit):
                self._add_annot_overlay(edit)

        self._apply_tool_interactivity()
        self.itemSelected.emit(None)

    def _image_preview(self, bbox, qpix: QPixmap) -> QPixmap | None:
        """Schneidet die Bildregion aus dem Seitenbild als Verschiebe-Vorschau aus."""
        z = self.RENDER_ZOOM
        x0, y0, x1, y1 = bbox
        rect = QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z).toRect()
        rect = rect.intersected(qpix.rect())
        if rect.isEmpty():
            return None
        return qpix.copy(rect)

    def _restore_text(self, item: TextItem) -> None:
        edit = self.edit_model.get(item.page_index, item.item_id)
        if edit is None:
            return
        item._ready = False
        item.setPlainText(edit.new_text)
        item.fontsize = edit.fontsize
        item.color = edit.color
        item.setPos(*edit.new_origin)
        item.setVisible(not edit.deleted)
        item._ready = True
        self.update_cover(item)

    def _restore_image(self, item: ImageItem) -> None:
        edit = self.edit_model.get(item.page_index, item.item_id)
        if edit is None:
            return
        item._ready = False
        item.setPos(edit.new_rect[0], edit.new_rect[1])
        item.setVisible(not edit.deleted)
        item._ready = True
        self.update_cover(item)

    # --- Cover-Rechtecke (verdecken das Original) -----------------------
    def update_cover(self, item) -> None:
        edit = self.edit_model.get(item.page_index, item.item_id)
        needs = edit is not None
        cover = getattr(item, "_cover", None)
        if needs and cover is None:
            x0, y0, x1, y1 = item.orig_rect
            cover = QGraphicsRectItem(QRectF(x0, y0, x1 - x0, y1 - y0))
            cover.setBrush(_WHITE)
            cover.setPen(QPen(Qt.PenStyle.NoPen))
            cover.setZValue(0)
            self.scene.addItem(cover)
            item._cover = cover
        elif not needs and cover is not None:
            self.scene.removeItem(cover)
            item._cover = None

    # --- Auswahl / Änderungen ------------------------------------------
    def selection_changed(self, item) -> None:
        self.itemSelected.emit(item)

    def document_modified(self) -> None:
        self.modified.emit()

    def selected_item(self):
        items = self.scene.selectedItems()
        return items[0] if items else None

    def delete_selected(self) -> None:
        item = self.selected_item()
        if item is not None and hasattr(item, "mark_deleted"):
            item.mark_deleted()
            self.modified.emit()

    # --- Werkzeuge ------------------------------------------------------
    def set_active_tool(self, tool: Tool) -> None:
        self.tools.set_tool(tool)
        self._apply_tool_interactivity()

    def _apply_tool_interactivity(self) -> None:
        select = self.tools.is_select
        for item in self.text_items + self.image_items:
            item.set_movable(select)
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag if select else QGraphicsView.DragMode.NoDrag
        )

    # --- Zoom -----------------------------------------------------------
    def set_zoom(self, zoom: float) -> None:
        zoom = max(0.1, min(zoom, 8.0))
        factor = zoom / self._view_zoom
        self._view_zoom = zoom
        self.scale(factor, factor)

    def zoom_in(self) -> None:
        self.set_zoom(self._view_zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._view_zoom / 1.25)

    def fit_width(self) -> None:
        if self.current_page < 0:
            return
        rect = self.document.page_rect(self.current_page)
        if rect.width:
            avail = self.viewport().width() - 24
            self.set_zoom(avail / rect.width)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    # --- Zeichnen von Annotationen -------------------------------------
    def mousePressEvent(self, event) -> None:
        if self.tools.is_select or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drawing = True
        pos = self.mapToScene(event.position().toPoint())
        self._draw_start = pos
        self._draw_points = [(pos.x(), pos.y())]
        self._begin_temp(pos)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._drawing:
            super().mouseMoveEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        self._draw_points.append((pos.x(), pos.y()))
        self._update_temp(pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._drawing:
            super().mouseReleaseEvent(event)
            return
        self._drawing = False
        pos = self.mapToScene(event.position().toPoint())
        self._finish_temp(pos)
        event.accept()

    def _begin_temp(self, pos) -> None:
        color = QColor.fromRgbF(*self.tools.color)
        tool = self.tools.current
        if tool in (Tool.HIGHLIGHT, Tool.RECT, Tool.TEXTBOX, Tool.NOTE):
            self._temp_item = QGraphicsRectItem(QRectF(pos, pos))
            self._temp_item.setPen(QPen(color, 0, Qt.PenStyle.DashLine))
            self.scene.addItem(self._temp_item)
        elif tool == Tool.INK:
            path = QPainterPath(pos)
            self._temp_item = QGraphicsPathItem(path)
            pen = QPen(color, self.tools.width)
            pen.setCosmetic(True)
            self._temp_item.setPen(pen)
            self.scene.addItem(self._temp_item)

    def _update_temp(self, pos) -> None:
        if self._temp_item is None:
            return
        tool = self.tools.current
        if isinstance(self._temp_item, QGraphicsRectItem):
            self._temp_item.setRect(QRectF(self._draw_start, pos).normalized())
        elif isinstance(self._temp_item, QGraphicsPathItem):
            path = self._temp_item.path()
            path.lineTo(pos)
            self._temp_item.setPath(path)

    def _finish_temp(self, pos) -> None:
        if self._temp_item is not None:
            self.scene.removeItem(self._temp_item)
            self._temp_item = None

        tool = self.tools.current
        self._annot_seq += 1
        item_id = f"annot{self._annot_seq}"
        x0, y0 = self._draw_start.x(), self._draw_start.y()
        x1, y1 = pos.x(), pos.y()
        rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

        edit: AnnotEdit | None = None
        if tool == Tool.HIGHLIGHT:
            edit = AnnotEdit(self.current_page, item_id, "highlight", rect=rect,
                             color=self.tools.color, width=self.tools.width)
        elif tool == Tool.RECT:
            edit = AnnotEdit(self.current_page, item_id, "rect", rect=rect,
                             color=self.tools.color, width=self.tools.width)
        elif tool == Tool.INK:
            edit = AnnotEdit(self.current_page, item_id, "ink", points=[list(self._draw_points)],
                             color=self.tools.color, width=self.tools.width)
        elif tool == Tool.NOTE:
            text, ok = QInputDialog.getMultiLineText(self, "Notiz", "Text der Notiz:")
            if ok:
                edit = AnnotEdit(self.current_page, item_id, "note", rect=rect, text=text,
                                 color=self.tools.color)
        elif tool == Tool.TEXTBOX:
            text, ok = QInputDialog.getMultiLineText(self, "Text einfügen", "Text:")
            if ok and text:
                edit = AnnotEdit(self.current_page, item_id, "text", rect=rect, text=text,
                                 color=self.tools.color, width=self.tools.width)

        if edit is not None:
            self.edit_model.set(edit)
            self._add_annot_overlay(edit)
            self.modified.emit()

    def _add_annot_overlay(self, edit: AnnotEdit) -> None:
        """Zeigt eine Annotation als Overlay (Vorschau) auf der Leinwand."""
        color = QColor.fromRgbF(*edit.color)
        if edit.kind == "highlight" and edit.rect:
            item = QGraphicsRectItem(QRectF(edit.rect[0], edit.rect[1],
                                            edit.rect[2] - edit.rect[0],
                                            edit.rect[3] - edit.rect[1]))
            fill = QColor(255, 235, 60, 90)
            item.setBrush(QBrush(fill))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setZValue(3)
            self.scene.addItem(item)
        elif edit.kind == "rect" and edit.rect:
            item = QGraphicsRectItem(QRectF(edit.rect[0], edit.rect[1],
                                            edit.rect[2] - edit.rect[0],
                                            edit.rect[3] - edit.rect[1]))
            pen = QPen(color, edit.width)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(8)
            self.scene.addItem(item)
        elif edit.kind == "ink" and edit.points:
            path = QPainterPath()
            for stroke in edit.points:
                if not stroke:
                    continue
                path.moveTo(stroke[0][0], stroke[0][1])
                for px, py in stroke[1:]:
                    path.lineTo(px, py)
            item = QGraphicsPathItem(path)
            pen = QPen(color, edit.width)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(8)
            self.scene.addItem(item)
        elif edit.kind == "note" and edit.rect:
            item = QGraphicsSimpleTextItem("📝")
            item.setPos(edit.rect[0], edit.rect[1])
            item.setBrush(QBrush(color))
            item.setZValue(8)
            self.scene.addItem(item)
        elif edit.kind == "text" and edit.rect:
            item = QGraphicsSimpleTextItem(edit.text)
            item.setPos(edit.rect[0], edit.rect[1])
            item.setBrush(QBrush(color))
            item.setZValue(8)
            self.scene.addItem(item)
