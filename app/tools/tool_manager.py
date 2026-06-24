"""Hält das aktuell aktive Werkzeug."""
from __future__ import annotations

from enum import Enum


class Tool(str, Enum):
    SELECT = "select"      # Auswählen / Verschieben / Doppelklick zum Editieren
    HIGHLIGHT = "highlight"
    RECT = "rect"
    INK = "ink"            # Freihand zeichnen
    NOTE = "note"          # Textnotiz-Stempel
    TEXTBOX = "text"       # Neuen Text auf die Seite setzen


class ToolManager:
    def __init__(self) -> None:
        self.current: Tool = Tool.SELECT
        self.color: tuple[float, float, float] = (1.0, 0.0, 0.0)
        self.width: float = 1.5

    def set_tool(self, tool: Tool) -> None:
        self.current = tool

    @property
    def is_select(self) -> bool:
        return self.current == Tool.SELECT
