"""
Main application module for NCONotes.
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel


class NCONotesWindow(QMainWindow):
    """Main window for NCONotes application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCONotes")
        self.setGeometry(100, 100, 800, 600)

        # Placeholder label
        label = QLabel("NCONotes - Coming Soon", self)
        label.setGeometry(300, 250, 200, 50)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = NCONotesWindow()
    window.show()
    sys.exit(app.exec())
