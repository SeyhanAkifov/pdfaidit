"""Wrapper um ein PyMuPDF-Dokument (öffnen, rendern, extrahieren, speichern)."""
from __future__ import annotations

import fitz

from app.edits.edit_model import AnnotEdit, FormEdit, ImageEdit, TextEdit


class PdfDocument:
    def __init__(self) -> None:
        self.doc: fitz.Document | None = None
        self.path: str | None = None

    # --- Lebenszyklus ---------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self.doc is not None

    def open(self, path: str) -> None:
        self.close()
        self.doc = fitz.open(path)
        self.path = path

    def close(self) -> None:
        if self.doc is not None:
            self.doc.close()
        self.doc = None
        self.path = None

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0

    # --- Lesen / Rendern ------------------------------------------------
    def page_rect(self, index: int) -> fitz.Rect:
        return self.doc[index].rect

    def render_pixmap(self, index: int, zoom: float = 2.0) -> fitz.Pixmap:
        page = self.doc[index]
        matrix = fitz.Matrix(zoom, zoom)
        return page.get_pixmap(matrix=matrix, alpha=False)

    def get_text_spans(self, index: int) -> list[dict]:
        """Liefert alle Text-Spans der Seite mit bbox/font/size/color."""
        page = self.doc[index]
        data = page.get_text("dict")
        spans: list[dict] = []
        for block in data.get("blocks", []):
            if block.get("type", 0) != 0:  # 0 = Textblock
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        spans.append(span)
        return spans

    def get_images(self, index: int) -> list[dict]:
        """Liefert Bildinfos (bbox + xref) der Seite."""
        page = self.doc[index]
        return page.get_image_info(xrefs=True)

    def get_widgets(self, index: int) -> list:
        """Liefert die Formularfelder (Widgets) der Seite."""
        page = self.doc[index]
        return list(page.widgets())

    # --- Seitenoperationen ---------------------------------------------
    def delete_page(self, index: int) -> None:
        self.doc.delete_page(index)

    def move_page(self, from_index: int, to_index: int) -> None:
        self.doc.move_page(from_index, to_index)

    def insert_blank_page(self, index: int) -> None:
        # new_page fügt VOR der angegebenen Position ein
        self.doc.new_page(pno=index)

    def rotate_page(self, index: int, degrees: int) -> None:
        page = self.doc[index]
        page.set_rotation((page.rotation + degrees) % 360)

    # --- Speichern ------------------------------------------------------
    def apply_edits(self, model) -> None:
        """Schreibt alle ausstehenden Änderungen in das fitz-Dokument."""
        for page_index, edits in model.edits_by_page().items():
            page = self.doc[page_index]
            text_edits = [e for e in edits if isinstance(e, TextEdit) and e.is_changed]
            image_edits = [e for e in edits if isinstance(e, ImageEdit)]
            annot_edits = [e for e in edits if isinstance(e, AnnotEdit)]
            form_edits = [e for e in edits if isinstance(e, FormEdit)]

            # 1. Redaktionen sammeln (Original-Inhalte entfernen)
            for edit in text_edits:
                page.add_redact_annot(fitz.Rect(*edit.orig_rect))
            for edit in image_edits:
                page.add_redact_annot(fitz.Rect(*edit.orig_rect))
            if text_edits or image_edits:
                page.apply_redactions()

            # 2. Texte neu einfügen
            for edit in text_edits:
                if edit.deleted:
                    continue
                self._insert_text(page, edit)

            # 3. Bilder neu einfügen
            for edit in image_edits:
                if edit.deleted:
                    continue
                self._insert_image(page, edit)

            # 4. Annotationen erzeugen
            for edit in annot_edits:
                self._add_annotation(page, edit)

            # 5. Formularfelder ausfüllen
            if form_edits:
                values = {e.field_name: e.value for e in form_edits}
                for widget in page.widgets():
                    if widget.field_name in values:
                        widget.field_value = values[widget.field_name]
                        widget.update()

    def _insert_text(self, page: fitz.Page, edit: TextEdit) -> None:
        if not edit.new_text.strip():
            return
        x, y = edit.new_origin
        # Großzügige Box bis zum rechten/unteren Seitenrand, damit der neue Text
        # (der länger als das Original sein kann) sicher hineinpasst. Der Text
        # wird links-oben in der Box gesetzt -> Position bleibt korrekt.
        right = max(x + (edit.orig_rect[2] - edit.orig_rect[0]) + 6, page.rect.width - 4)
        bottom = page.rect.height - 4
        rect = fitz.Rect(x, y, right, bottom)
        rc = page.insert_textbox(
            rect,
            edit.new_text,
            fontname=edit.fontname,
            fontsize=edit.fontsize,
            color=edit.color,
        )
        if rc < 0:
            # Fallback: einzeilig direkt an der Grundlinie einfügen (kein Clipping)
            page.insert_text(
                (x, y + edit.fontsize * 0.8),
                edit.new_text,
                fontname=edit.fontname,
                fontsize=edit.fontsize,
                color=edit.color,
            )

    def _insert_image(self, page: fitz.Page, edit: ImageEdit) -> None:
        try:
            extracted = self.doc.extract_image(edit.xref)
        except Exception:
            return
        page.insert_image(fitz.Rect(*edit.new_rect), stream=extracted["image"])

    def _add_annotation(self, page: fitz.Page, edit: AnnotEdit) -> None:
        kind = edit.kind
        if kind == "highlight" and edit.rect:
            page.add_highlight_annot(fitz.Rect(*edit.rect))
        elif kind == "rect" and edit.rect:
            annot = page.add_rect_annot(fitz.Rect(*edit.rect))
            annot.set_colors(stroke=edit.color)
            annot.set_border(width=edit.width)
            annot.update()
        elif kind == "ink" and edit.points:
            annot = page.add_ink_annot(edit.points)
            annot.set_colors(stroke=edit.color)
            annot.set_border(width=edit.width)
            annot.update()
        elif kind == "note" and edit.rect:
            page.add_text_annot((edit.rect[0], edit.rect[1]), edit.text or "Notiz")
        elif kind == "text" and edit.rect:
            page.insert_textbox(
                fitz.Rect(*edit.rect),
                edit.text,
                fontname="helv",
                fontsize=max(edit.width * 6, 11),
                color=edit.color,
            )

    def save(self, path: str | None = None) -> str:
        """Speichert das Dokument. Ohne Pfad -> inkrementell an Originalort."""
        if path is None or path == self.path:
            target = self.path
            self.doc.save(target, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        else:
            target = path
            self.doc.save(target, garbage=4, deflate=True)
        return target
