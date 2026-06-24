"""Eigenschaften-Panel für das aktuell ausgewählte Element."""
from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.items.image_item import ImageItem
from app.items.text_item import TextItem


class PropertiesPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._item = None

        self.info = QLabel("Kein Element ausgewählt.")
        self.info.setWordWrap(True)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1.0, 400.0)
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(self._on_size_changed)

        self.color_btn = QPushButton("Farbe wählen…")
        self.color_btn.clicked.connect(self._on_color)

        self.delete_btn = QPushButton("Element löschen")
        self.delete_btn.clicked.connect(self._on_delete)

        form = QFormLayout()
        self.size_row = QLabel("Schriftgröße:")
        form.addRow(self.size_row, self.size_spin)
        form.addRow(self.color_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addLayout(form)
        layout.addWidget(self.delete_btn)
        layout.addStretch(1)

        self.set_item(None)

    def set_item(self, item) -> None:
        self._item = item
        is_text = isinstance(item, TextItem)
        is_image = isinstance(item, ImageItem)

        self.size_spin.setVisible(is_text)
        self.size_row.setVisible(is_text)
        self.color_btn.setVisible(is_text)
        self.delete_btn.setVisible(is_text or is_image)

        if is_text:
            self.info.setText(f"Textblock\n„{item.orig_text[:60]}…"
                              if len(item.orig_text) > 60 else f"Textblock\n„{item.orig_text}")
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(item.fontsize)
            self.size_spin.blockSignals(False)
        elif is_image:
            self.info.setText("Bild (verschiebbar / löschbar)")
        else:
            self.info.setText("Kein Element ausgewählt.")

    def _on_size_changed(self, value: float) -> None:
        if isinstance(self._item, TextItem):
            self._item.set_fontsize(value)

    def _on_color(self) -> None:
        if not isinstance(self._item, TextItem):
            return
        initial = QColor.fromRgbF(*self._item.color)
        color = QColorDialog.getColor(initial, self, "Textfarbe")
        if color.isValid():
            self._item.set_color((color.redF(), color.greenF(), color.blueF()))

    def _on_delete(self) -> None:
        if self._item is not None and hasattr(self._item, "mark_deleted"):
            self._item.mark_deleted()
            self.set_item(None)
