r"""Diagnose: Welche Schriften nutzt ein PDF – und sind sie wiederverwendbar?

Aufruf:
    .\.venv\Scripts\python.exe inspect_fonts.py "C:\\Pfad\\zur\\datei.pdf"

Zeigt pro Seite die eingebetteten Schriften (xref, Typ, Endung, Name) und prüft
für jede im Text vorkommende Schrift, ob die App sie beim Verschieben/Editieren
mit der Originalschrift einfügen kann (oder auf eine Standardschrift ausweichen muss).
"""
import os
import sys

os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
from app.document import PdfDocument


def main(path: str) -> None:
    doc = PdfDocument()
    doc.open(path)
    print(f"Datei: {path}")
    print(f"Seiten: {doc.page_count}\n")

    for index in range(min(doc.page_count, 3)):  # erste bis zu 3 Seiten
        page = doc.doc[index]
        print(f"=== Seite {index + 1} ===")
        print("Eingebettete Schriften (xref, endung, typ, name):")
        for f in page.get_fonts(full=False):
            embedded = "✓ extrahierbar" if f[1] in ("ttf", "otf", "cff", "ttc") else "✗ nicht direkt"
            print(f"   xref={f[0]:<4} {f[1]:<5} {f[2]:<8} {f[3]:<30} {embedded}")

        span_fonts = sorted({s["font"] for s in doc.get_text_spans(index)})
        print("\nIm Text verwendete Schriften -> wird Originalschrift genutzt?")
        for name in span_fonts:
            fontfile = doc._embedded_fontfile(page, name)
            verdict = "ORIGINAL bleibt erhalten ✅" if fontfile else "Fallback (Standardschrift) ⚠️"
            print(f"   {name:<32} {verdict}")
        doc._cleanup_fontfiles()
        print()

    doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Bitte PDF-Pfad angeben:  python inspect_fonts.py "C:\\...\\datei.pdf"')
        sys.exit(1)
    main(sys.argv[1])
