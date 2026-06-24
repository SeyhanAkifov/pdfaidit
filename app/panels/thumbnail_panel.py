"""Seitenleiste mit Seiten-Miniaturen und Seiten-Operationen."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from app.qt_utils import fitz_pixmap_to_qpixmap


class ThumbnailPanel(QWidget):
    pageSelected = pyqtSignal(int)
    requestDelete = pyqtSignal(int)
    requestInsert = pyqtSignal(int)
    requestRotate = pyqtSignal(int)
    requestMove = pyqtSignal(int, int)  # from_index, to_index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.list = QListWidget()
        self.list.setIconSize(QSize(120, 160))
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.currentRowChanged.connect(self._on_row_changed)

        # Seiten-Operationen
        btn_add = QPushButton("＋ Seite")
        btn_del = QPushButton("🗑")
        btn_up = QPushButton("▲")
        btn_down = QPushButton("▼")
        btn_rot = QPushButton("⟳")
        for b in (btn_add, btn_del, btn_up, btn_down, btn_rot):
            b.setMaximumWidth(60)
        btn_add.clicked.connect(lambda: self.requestInsert.emit(self._row() + 1))
        btn_del.clicked.connect(lambda: self.requestDelete.emit(self._row()))
        btn_rot.clicked.connect(lambda: self.requestRotate.emit(self._row()))
        btn_up.clicked.connect(lambda: self._move(-1))
        btn_down.clicked.connect(lambda: self._move(1))

        ops = QHBoxLayout()
        for b in (btn_add, btn_del, btn_up, btn_down, btn_rot):
            ops.addWidget(b)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(ops)
        layout.addWidget(self.list)

    def _row(self) -> int:
        return max(self.list.currentRow(), 0)

    def _move(self, delta: int) -> None:
        src = self.list.currentRow()
        dst = src + delta
        if src < 0 or not (0 <= dst < self.list.count()):
            return
        self.requestMove.emit(src, dst)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.pageSelected.emit(row)

    def populate(self, document, thumb_zoom: float = 0.2) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for index in range(document.page_count):
            pix = document.render_pixmap(index, thumb_zoom)
            icon = QIcon(fitz_pixmap_to_qpixmap(pix))
            item = QListWidgetItem(icon, f"{index + 1}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def set_current(self, index: int) -> None:
        self.list.blockSignals(True)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
