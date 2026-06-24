"""Hilfsfunktionen für die Brücke zwischen PyMuPDF und Qt."""
from __future__ import annotations

import fitz
from PyQt6.QtGui import QImage, QPixmap


def fitz_pixmap_to_qpixmap(pix: "fitz.Pixmap") -> QPixmap:
    """Konvertiert eine PyMuPDF-Pixmap in eine Qt-QPixmap.

    Der Sample-Puffer gehört der fitz-Pixmap, daher kopieren wir das QImage
    (``copy()``), bevor wir die QPixmap erzeugen.
    """
    if pix.alpha:
        fmt = QImage.Format.Format_RGBA8888
    else:
        fmt = QImage.Format.Format_RGB888

    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    return QPixmap.fromImage(image.copy())
