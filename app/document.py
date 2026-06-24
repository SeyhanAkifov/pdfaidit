"""Wrapper um ein PyMuPDF-Dokument (öffnen, rendern, extrahieren, speichern)."""
from __future__ import annotations

import os
import re
import tempfile

import fitz

from app.edits.edit_model import AnnotEdit, FormEdit, ImageEdit, TextEdit


class PdfDocument:
    def __init__(self) -> None:
        self.doc: fitz.Document | None = None
        self.path: str | None = None
        self._fontfile_cache: dict[str, str | None] = {}

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

    # --- Schrift-Einbettung --------------------------------------------
    @staticmethod
    def _alpha(s: str) -> str:
        # Nur Buchstaben, ohne Subset-Präfix -> robust gegen "ArialMT" vs "Arial Regular"
        return re.sub(r"[^a-z]", "", re.sub(r"^[A-Z]{6}\+", "", s or "").lower())

    def _find_embedded_font(self, page: fitz.Page, basefont: str) -> tuple[int | None, str | None]:
        """Findet die am besten passende eingebettete Schrift -> (xref, endung)."""
        if not basefont:
            return None, None
        target = self._alpha(basefont)
        best_xref: int | None = None
        best_ext: str | None = None
        best_score = -1
        try:
            for finfo in page.get_fonts(full=False):
                xref, ext, bname = finfo[0], finfo[1], self._alpha(finfo[3])
                if ext not in ("ttf", "otf", "cff", "ttc"):
                    continue
                # Länge des gemeinsamen Präfixes als Ähnlichkeitsmaß
                n = 0
                while n < min(len(bname), len(target)) and bname[n] == target[n]:
                    n += 1
                score = n
                if bname and (bname in target or target in bname):
                    score = max(score, min(len(bname), len(target)))
                if score > best_score:
                    best_score, best_xref, best_ext = score, xref, ext
        except Exception:
            return None, None
        if best_xref is not None and best_score >= 4:
            return best_xref, best_ext
        return None, None

    def font_bytes(self, page_index: int, basefont: str) -> bytes | None:
        """Liefert die rohen Bytes der eingebetteten Schrift (für die Qt-Vorschau)."""
        page = self.doc[page_index]
        xref, _ = self._find_embedded_font(page, basefont)
        if xref is None:
            return None
        try:
            return self.doc.extract_font(xref)[-1] or None
        except Exception:
            return None

    def _embedded_fontfile(self, page: fitz.Page, basefont: str) -> str | None:
        """Extrahiert die eingebettete Schrift `basefont` als temporäre Datei.

        Liefert einen Pfad oder None, wenn die Schrift nicht eingebettet/
        extrahierbar ist (dann Basis-14-Fallback beim Speichern).
        """
        if not basefont:
            return None
        if basefont in self._fontfile_cache:
            return self._fontfile_cache[basefont]
        xref, ext = self._find_embedded_font(page, basefont)
        path: str | None = None
        try:
            if xref is not None:
                extracted = self.doc.extract_font(xref)
                content = extracted[-1]
                real_ext = extracted[1] or ext or "ttf"
                if content:
                    fd, tmp = tempfile.mkstemp(suffix=f".{real_ext}")
                    with os.fdopen(fd, "wb") as fh:
                        fh.write(content)
                    path = tmp
        except Exception:
            path = None
        self._fontfile_cache[basefont] = path
        return path

    def _cleanup_fontfiles(self) -> None:
        for path in self._fontfile_cache.values():
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._fontfile_cache = {}

    # --- Speichern ------------------------------------------------------
    def apply_edits(self, model) -> None:
        """Schreibt alle ausstehenden Änderungen in das fitz-Dokument."""
        try:
            self._apply_edits(model)
        finally:
            self._cleanup_fontfiles()

    def _apply_edits(self, model) -> None:
        for page_index, edits in model.edits_by_page().items():
            page = self.doc[page_index]
            text_edits = [e for e in edits if isinstance(e, TextEdit) and e.is_changed]
            image_edits = [e for e in edits if isinstance(e, ImageEdit)]
            annot_edits = [e for e in edits if isinstance(e, AnnotEdit)]
            form_edits = [e for e in edits if isinstance(e, FormEdit)]

            # 0. SOLANGE der Originaltext noch da ist:
            #    a) eingebettete Schriften sichern (für Vektor-Neusatz)
            #    b) für reine Verschiebungen OHNE einbettbare Schrift die Originalstelle
            #       als Bild rendern -> pixelgenaue Übernahme, schriftunabhängig
            move_pixmaps: dict[int, fitz.Pixmap] = {}
            for edit in text_edits:
                fontfile = self._embedded_fontfile(page, edit.orig_font)
                move_only = (not edit.deleted) and (edit.new_text == edit.orig_text)
                if move_only and not fontfile:
                    clip = fitz.Rect(*edit.orig_rect)
                    move_pixmaps[edit.item_id] = page.get_pixmap(
                        matrix=fitz.Matrix(3, 3), clip=clip, alpha=False
                    )

            # 1. Redaktionen sammeln (Original-Inhalte entfernen, in Cover-Farbe füllen)
            for edit in text_edits:
                page.add_redact_annot(fitz.Rect(*edit.orig_rect), fill=edit.cover_color)
            for edit in image_edits:
                page.add_redact_annot(fitz.Rect(*edit.orig_rect), fill=edit.cover_color)
            if text_edits or image_edits:
                page.apply_redactions()

            # 2. Texte neu einfügen (als Bild bei reiner Verschiebung ohne Schrift, sonst Vektor)
            for edit in text_edits:
                if edit.deleted:
                    continue
                if edit.item_id in move_pixmaps:
                    x, y = edit.new_origin
                    w = edit.orig_rect[2] - edit.orig_rect[0]
                    h = edit.orig_rect[3] - edit.orig_rect[1]
                    page.insert_image(fitz.Rect(x, y, x + w, y + h),
                                      pixmap=move_pixmaps[edit.item_id])
                else:
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

        # Originalschrift bevorzugen (gleiche Optik, v. a. beim Verschieben)
        fontfile = self._embedded_fontfile(page, edit.orig_font)
        if fontfile:
            alias = "F" + (re.sub(r"\W", "", edit.orig_font)[:24] or "embed")
            rc = page.insert_textbox(
                rect, edit.new_text, fontname=alias, fontfile=fontfile,
                fontsize=edit.fontsize, color=edit.color,
            )
            if rc >= 0:
                return  # erfolgreich mit Originalschrift gesetzt

        # Fallback 1: Basis-14-Schrift in der Box
        rc = page.insert_textbox(
            rect, edit.new_text, fontname=edit.fontname,
            fontsize=edit.fontsize, color=edit.color,
        )
        if rc >= 0:
            return

        # Fallback 2: einzeilig an der Grundlinie (kein Clipping)
        page.insert_text(
            (x, y + edit.fontsize * 0.8), edit.new_text,
            fontname=edit.fontname, fontsize=edit.fontsize, color=edit.color,
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
