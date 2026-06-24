"""pdfAIdit – Einstiegspunkt der Anwendung."""
import sys

from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("pdfAIdit")
    app.setOrganizationName("pdfaidit")

    window = MainWindow()
    window.show()

    # Optionaler Dateipfad als Kommandozeilenargument
    if len(sys.argv) > 1:
        window.open_path(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
