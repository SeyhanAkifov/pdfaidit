"""Hauptfenster: Menü, Toolbar, Leinwand und Seitenleisten."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PyQt6.QtWidgets import (
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QWidget,
)

from app.document import PdfDocument
from app.edits.edit_model import EditModel
from app.page_view import PageView
from app.panels.properties_panel import PropertiesPanel
from app.panels.thumbnail_panel import ThumbnailPanel
from app.tools.tool_manager import Tool, ToolManager


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("pdfAIdit")
        self.resize(1280, 860)

        self.document = PdfDocument()
        self.edit_model = EditModel()
        self.tools = ToolManager()
        self._dirty = False

        # Zentrale Leinwand
        self.view = PageView(self.document, self.edit_model, self.tools, self)
        self.view.itemSelected.connect(self._on_item_selected)
        self.view.modified.connect(self._on_modified)
        self.setCentralWidget(self.view)

        # Docks
        self.thumbs = ThumbnailPanel(self)
        self.thumbs.pageSelected.connect(self.goto_page)
        self.thumbs.requestDelete.connect(self._delete_page)
        self.thumbs.requestInsert.connect(self._insert_page)
        self.thumbs.requestRotate.connect(self._rotate_page)
        self.thumbs.requestMove.connect(self._move_page)
        dock_l = QDockWidget("Seiten", self)
        dock_l.setWidget(self.thumbs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_l)

        self.props = PropertiesPanel(self)
        dock_r = QDockWidget("Eigenschaften", self)
        dock_r.setWidget(self.props)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_r)

        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self.status = self.statusBar()
        self._update_title()
        self._update_actions_enabled()

    # --- Aktionen / Menü / Toolbar -------------------------------------
    def _build_actions(self) -> None:
        self.act_open = QAction("Öffnen…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.open_dialog)

        self.act_save = QAction("Speichern", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.save)

        self.act_save_as = QAction("Speichern unter…", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self.save_as)

        self.act_undo = QAction("Rückgängig", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.undo)

        self.act_redo = QAction("Wiederholen", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.redo)

        self.act_prev = QAction("◀ Zurück", self)
        self.act_prev.triggered.connect(lambda: self.goto_page(self.view.current_page - 1))
        self.act_next = QAction("Weiter ▶", self)
        self.act_next.triggered.connect(lambda: self.goto_page(self.view.current_page + 1))

        self.act_zoom_in = QAction("Zoom +", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.triggered.connect(self.view.zoom_in)
        self.act_zoom_out = QAction("Zoom −", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.triggered.connect(self.view.zoom_out)
        self.act_fit = QAction("Breite einpassen", self)
        self.act_fit.triggered.connect(self.view.fit_width)

        self.act_delete = QAction("Element löschen", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self.view.delete_selected)

        # Werkzeuge (gegenseitig ausschließend)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_actions: dict[Tool, QAction] = {}
        for tool, label in [
            (Tool.SELECT, "Auswahl"),
            (Tool.HIGHLIGHT, "Markieren"),
            (Tool.RECT, "Rechteck"),
            (Tool.INK, "Zeichnen"),
            (Tool.NOTE, "Notiz"),
            (Tool.TEXTBOX, "Text"),
        ]:
            act = QAction(label, self, checkable=True)
            act.triggered.connect(lambda _checked, t=tool: self.view.set_active_tool(t))
            self.tool_group.addAction(act)
            self._tool_actions[tool] = act
        self._tool_actions[Tool.SELECT].setChecked(True)

        # Modus für die Überdeckung des entfernten Originals
        self.cover_group = QActionGroup(self)
        self.cover_group.setExclusive(True)
        self.act_cover_auto = QAction("Automatisch (Hintergrund abtasten)", self, checkable=True)
        self.act_cover_white = QAction("Weiß", self, checkable=True)
        self.act_cover_custom = QAction("Eigene Farbe…", self, checkable=True)
        self.act_cover_auto.setChecked(True)
        for a in (self.act_cover_auto, self.act_cover_white, self.act_cover_custom):
            self.cover_group.addAction(a)
        self.act_cover_auto.triggered.connect(lambda: self._set_cover_mode("auto"))
        self.act_cover_white.triggered.connect(lambda: self._set_cover_mode("white"))
        self.act_cover_custom.triggered.connect(self._set_cover_custom)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        m_file = bar.addMenu("&Datei")
        m_file.addAction(self.act_open)
        m_file.addSeparator()
        m_file.addAction(self.act_save)
        m_file.addAction(self.act_save_as)

        m_edit = bar.addMenu("&Bearbeiten")
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        m_edit.addSeparator()
        m_edit.addAction(self.act_delete)

        m_view = bar.addMenu("&Ansicht")
        for a in (self.act_prev, self.act_next, self.act_zoom_in, self.act_zoom_out, self.act_fit):
            m_view.addAction(a)

        m_opt = bar.addMenu("&Optionen")
        m_cover = m_opt.addMenu("Hintergrund-Abdeckung")
        for a in (self.act_cover_auto, self.act_cover_white, self.act_cover_custom):
            m_cover.addAction(a)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Haupt", self)
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.act_open)
        tb.addAction(self.act_save)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_prev)
        tb.addAction(self.act_next)
        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_fit)
        tb.addSeparator()
        for tool in (Tool.SELECT, Tool.HIGHLIGHT, Tool.RECT, Tool.INK, Tool.NOTE, Tool.TEXTBOX):
            tb.addAction(self._tool_actions[tool])

    # --- Datei öffnen / speichern --------------------------------------
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "PDF öffnen", "", "PDF-Dateien (*.pdf)")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if not self._confirm_discard():
            return
        try:
            self.document.open(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Fehler", f"Konnte PDF nicht öffnen:\n{exc}")
            return
        self.edit_model.clear()
        self._dirty = False
        self.view.reset_font_cache()
        self.thumbs.populate(self.document)
        self.goto_page(0)
        self.view.fit_width()
        self._update_title()
        self._update_actions_enabled()

    def save(self) -> None:
        if not self.document.is_open:
            return
        # „Speichern" mit ausstehenden Strukturänderungen am besten als neue Datei
        self.save_as(self.document.path)

    def save_as(self, suggested: str | None = None) -> None:
        if not self.document.is_open:
            return
        if not isinstance(suggested, str):
            base = self.document.path or "dokument.pdf"
            suggested = os.path.splitext(base)[0] + "_bearbeitet.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Speichern unter", suggested,
                                              "PDF-Dateien (*.pdf)")
        if not path:
            return
        try:
            self.document.apply_edits(self.edit_model)
            self.document.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{exc}")
            return
        # Nach dem Speichern: bearbeitete Datei neu laden (Änderungen sind nun „eingebrannt")
        self.document.open(path)
        self.edit_model.clear()
        self._dirty = False
        self.thumbs.populate(self.document)
        self.goto_page(min(self.view.current_page, self.document.page_count - 1))
        self._update_title()
        self.status.showMessage(f"Gespeichert: {path}", 5000)

    # --- Navigation -----------------------------------------------------
    def goto_page(self, index: int) -> None:
        if not self.document.is_open:
            return
        index = max(0, min(index, self.document.page_count - 1))
        self.view.load_page(index)
        self.thumbs.set_current(index)
        self.props.set_item(None)
        self._update_status()
        self._update_actions_enabled()

    # --- Seiten-Operationen --------------------------------------------
    def _delete_page(self, index: int) -> None:
        if self.document.page_count <= 1:
            QMessageBox.information(self, "Hinweis", "Die letzte Seite kann nicht gelöscht werden.")
            return
        self.document.delete_page(index)
        self._after_structure_change(min(index, self.document.page_count - 1))

    def _insert_page(self, index: int) -> None:
        self.document.insert_blank_page(index)
        self._after_structure_change(index)

    def _rotate_page(self, index: int) -> None:
        self.document.rotate_page(index, 90)
        self._after_structure_change(index)

    def _move_page(self, src: int, dst: int) -> None:
        self.document.move_page(src, dst)
        self._after_structure_change(dst)

    def _after_structure_change(self, focus_index: int) -> None:
        # Strukturänderungen lassen sich nicht mit Span-Edits mischen -> Modell leeren
        self.edit_model.clear()
        self._dirty = True
        self.thumbs.populate(self.document)
        self.goto_page(max(0, min(focus_index, self.document.page_count - 1)))
        self._update_title()

    # --- Undo / Redo ----------------------------------------------------
    def undo(self) -> None:
        if self.edit_model.undo() is not None:
            self.view.load_page(self.view.current_page)
            self._update_actions_enabled()

    def redo(self) -> None:
        if self.edit_model.redo() is not None:
            self.view.load_page(self.view.current_page)
            self._update_actions_enabled()

    # --- Hintergrund-Abdeckung -----------------------------------------
    def _set_cover_mode(self, mode: str) -> None:
        self.tools.cover_mode = mode
        self.view.refresh_covers()

    def _set_cover_custom(self) -> None:
        initial = QColor.fromRgbF(*self.tools.cover_rgb)
        color = QColorDialog.getColor(initial, self, "Farbe der Abdeckung")
        if color.isValid():
            self.tools.cover_rgb = (color.redF(), color.greenF(), color.blueF())
            self.tools.cover_mode = "custom"
            self.view.refresh_covers()
        else:
            # Abbruch -> vorherigen Modus-Knopf wiederherstellen
            if self.tools.cover_mode == "auto":
                self.act_cover_auto.setChecked(True)
            elif self.tools.cover_mode == "white":
                self.act_cover_white.setChecked(True)

    # --- UI-Status ------------------------------------------------------
    def _on_item_selected(self, item) -> None:
        self.props.set_item(item)

    def _on_modified(self) -> None:
        self._dirty = True
        self._update_title()
        self._update_actions_enabled()

    def _update_actions_enabled(self) -> None:
        has = self.document.is_open
        for a in (self.act_save, self.act_save_as, self.act_prev, self.act_next,
                  self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_delete):
            a.setEnabled(has)
        self.act_prev.setEnabled(has and self.view.current_page > 0)
        self.act_next.setEnabled(has and self.view.current_page < self.document.page_count - 1)
        self.act_undo.setEnabled(self.edit_model.can_undo())
        self.act_redo.setEnabled(self.edit_model.can_redo())

    def _update_status(self) -> None:
        if self.document.is_open:
            self.status.showMessage(
                f"Seite {self.view.current_page + 1} / {self.document.page_count}"
            )

    def _update_title(self) -> None:
        name = os.path.basename(self.document.path) if self.document.path else "—"
        star = "*" if self._dirty else ""
        self.setWindowTitle(f"pdfAIdit — {name}{star}")

    # --- Schließen ------------------------------------------------------
    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        res = QMessageBox.question(
            self, "Ungespeicherte Änderungen",
            "Es gibt ungespeicherte Änderungen. Trotzdem fortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return res == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
