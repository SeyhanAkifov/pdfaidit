# pdfAIdit

Eine Windows-Desktop-App zum **Bearbeiten von PDFs**: Elemente verschieben, Text direkt
editieren, Seiten verwalten, Formulare ausfüllen sowie Annotationen/Zeichnungen hinzufügen.

Gebaut mit **Python + PyQt6** (Oberfläche) und **PyMuPDF / `fitz`** (PDF-Engine).

## Funktionen

- 📄 **Viewer**: PDF öffnen, blättern, zoomen (Strg + Mausrad), Seiten-Miniaturen
- ✋ **Verschieben**: Textblöcke und Bilder per Drag & Drop neu positionieren
- ✏️ **Text editieren**: Doppelklick auf einen Textblock → Inhalt direkt ändern
  (Original wird entfernt, neuer Text neu gesetzt – „Redact + Re-Insert")
- 🎨 **Annotationen**: Markieren, Rechteck, Freihand zeichnen, Notiz, Text einfügen
- 📑 **Seiten**: hinzufügen, löschen, verschieben (▲▼), drehen
- 🧾 **Formulare**: vorhandene Formularfelder (grün umrandet) per Doppelklick ausfüllen
- ↩️ **Undo/Redo** (Strg+Z / Strg+Y) und Speichern unter

## Installation & Start (Entwicklung)

```powershell
# Virtuelle Umgebung anlegen und Abhängigkeiten installieren
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# App starten
.\.venv\Scripts\python.exe main.py
# optional direkt eine Datei öffnen:
.\.venv\Scripts\python.exe main.py "C:\Pfad\zur\datei.pdf"
```

## Bedienung (Kurz)

1. **Öffnen** (Strg+O) – PDF laden.
2. Werkzeug **Auswahl**: Elemente anklicken, ziehen (verschieben) oder doppelklicken (Text editieren).
   Im rechten **Eigenschaften**-Panel: Schriftgröße/Farbe ändern oder Element löschen.
3. Werkzeuge **Markieren / Rechteck / Zeichnen / Notiz / Text**: auf die Seite ziehen.
4. Links die **Seiten**-Leiste: Seiten hinzufügen/löschen/verschieben/drehen.
5. **Formularfelder** (grün) doppelklicken zum Ausfüllen.
6. **Speichern unter** (Strg+Umschalt+S).

## .exe bauen (Auslieferung)

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --windowed --onefile --name pdfAIdit main.py
```

Das Ergebnis liegt unter `dist\pdfAIdit.exe`.

## Hinweise & Grenzen

- **Schrift bleibt erhalten – zwei Wege:**
  - *Eingebettete Schrift vorhanden:* Sie wird extrahiert und sowohl in der Vorschau (über
    `QFontDatabase`) als auch im gespeicherten PDF 1:1 wiederverwendet → echter Vektortext.
  - *Keine (extrahierbare) Schrift eingebettet:* Beim **reinen Verschieben** wird der
    Originalbereich **pixelgenau als Bild** an die neue Stelle übernommen → die Optik stimmt
    immer, unabhängig von der Schrift. (Der verschobene Text ist dann nicht mehr markierbar.)
  - *Editieren neuer Zeichen ohne eingebettete Schrift:* Hier ist kein Bild möglich (der Text
    ändert sich), daher greift eine Standard-Schrift (Helvetica/Times/Courier); Größe/Farbe
    sind im Eigenschaften-Panel anpassbar.
  - Hinweis: Ein per Bild verschobener Block trägt seinen ursprünglichen Hintergrundausschnitt
    mit. Auf Farbverläufen kann das bei großen Verschiebungen minimal sichtbar sein.
- Verschieben/Editieren verdeckt den Originalbereich. Den **Modus der Abdeckung** stellst du
  unter **Optionen → Hintergrund-Abdeckung** ein:
  - *Automatisch* (Standard): die Hintergrundfarbe wird neben dem Text abgetastet – ideal für
    farbige Seiten. Bei Farbverläufen wird eine passende Mischfarbe verwendet (kleiner Versatz möglich).
  - *Weiß*: feste weiße Abdeckung (für weißes Papier).
  - *Eigene Farbe…*: feste Wunschfarbe.
  Die gewählte Farbe wird auch beim Speichern in das PDF übernommen.
- **Seiten-Operationen** (löschen/verschieben/drehen) werden sofort auf das Dokument angewendet
  und setzen ausstehende Span-Änderungen zurück (sie speichern implizit den Strukturzustand).
- **Lizenz PyMuPDF:** AGPL (oder kommerzielle Lizenz). Für private/interne Nutzung unkritisch;
  bei kommerzieller Weitergabe Lizenz prüfen.

## Projektstruktur

```
main.py                     App-Start
app/document.py             PyMuPDF-Wrapper (öffnen, rendern, speichern, apply_edits)
app/page_view.py            Leinwand: Rendering + Overlays + Zeichenwerkzeuge
app/edits/edit_model.py     Änderungs-Modell (Text/Bild/Annotation/Formular) + Undo/Redo
app/items/                  Overlay-Items (Text, Bild, Formularfeld)
app/tools/tool_manager.py   Aktives Werkzeug
app/panels/                 Thumbnails + Eigenschaften
app/main_window.py          Fenster, Menü, Toolbar, Verdrahtung
```
