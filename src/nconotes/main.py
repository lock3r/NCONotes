"""
Main application module for NCONotes.
OneNote-like application with infinite canvas.

Features:
- Click anywhere to create a resizable text editor
- Drag and drop images
- Move, resize, and crop images
- Save/load notebooks
- Undo/redo support
"""

import sys
import json
import os
import uuid
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsProxyWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QListWidget, QSplitter, QFileDialog,
    QGraphicsPixmapItem, QGraphicsRectItem, QMessageBox, QToolBar,
    QGraphicsItem, QInputDialog
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, Signal
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QTransform, QAction, QKeySequence, QUndoStack, QUndoCommand
)

from nconotes.models import TextBoxData, ImageData
from nconotes.widgets import ResizableTextEdit


class ResizableImage(QGraphicsPixmapItem):
    """A resizable, movable image on the canvas"""

    def __init__(self, pixmap, pos, image_id=None):
        super().__init__(pixmap)

        # Generate new UUID if not provided (new image), use existing if provided (loading)
        self.image_id = image_id if image_id else str(uuid.uuid4())
        self.original_pixmap = pixmap

        self.setPos(pos)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        self.is_resizing = False
        self.resize_start_pos = None
        self.resize_start_scale = 1.0
        self.current_scale = 1.0

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)

        # Draw resize handle and border when selected
        if self.isSelected():
            rect = self.boundingRect()

            # Draw border
            pen = QPen(QColor(100, 100, 255), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Draw resize handle
            handle_size = 10
            handle_rect = QRectF(
                rect.right() - handle_size,
                rect.bottom() - handle_size,
                handle_size,
                handle_size
            )
            painter.fillRect(handle_rect, QColor(100, 100, 255))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on resize handle
            rect = self.boundingRect()
            handle_size = 10
            handle_rect = QRectF(
                rect.right() - handle_size,
                rect.bottom() - handle_size,
                handle_size,
                handle_size
            )

            if handle_rect.contains(event.pos()):
                self.is_resizing = True
                self.resize_start_pos = event.scenePos()
                self.resize_start_scale = self.current_scale
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            delta = event.scenePos() - self.resize_start_pos
            scale_change = 1.0 + (delta.x() + delta.y()) / 200.0
            new_scale = max(0.1, self.resize_start_scale * scale_change)

            self.setScale(new_scale)
            self.current_scale = new_scale
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_resizing:
            self.is_resizing = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def to_dict(self):
        """Serialize to dictionary for saving"""
        pixmap = self.original_pixmap
        data = ImageData(
            image_id=self.image_id,
            x=self.pos().x(),
            y=self.pos().y(),
            scale=self.current_scale,
            width=pixmap.width(),
            height=pixmap.height()
        )
        return data.to_dict()

    def save_to_file(self, images_dir):
        """Save image to disk as PNG"""
        images_dir.mkdir(exist_ok=True)
        image_path = images_dir / f"{self.image_id}.png"
        self.original_pixmap.save(str(image_path), "PNG")

    @staticmethod
    def from_dict(data, images_dir):
        """Deserialize from dictionary and load image from disk"""
        image_data = ImageData.from_dict(data)
        image_path = images_dir / f"{image_data.image_id}.png"

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        pixmap = QPixmap(str(image_path))
        pos = QPointF(image_data.x, image_data.y)
        widget = ResizableImage(pixmap, pos, image_id=image_data.image_id)
        widget.setScale(image_data.scale)
        widget.current_scale = image_data.scale
        return widget


class InfiniteCanvas(QGraphicsView):
    """Infinite canvas that supports click-to-create text editors"""

    def __init__(self):
        super().__init__()

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Make canvas "infinite" with large scene
        self.scene.setSceneRect(-10000, -10000, 20000, 20000)

        # Enable dragging
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Smooth rendering
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Grid background
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250)))

        # Accept drops
        self.setAcceptDrops(True)

    def mouseDoubleClickEvent(self, event):
        """Double-click to create a text editor"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Convert view coordinates to scene coordinates
            scene_pos = self.mapToScene(event.pos())

            # Check if there's already an item at this position
            item = self.scene.itemAt(scene_pos, self.transform())

            # Only create a new editor if clicking on empty canvas
            if item is None:
                # Create text editor at click position
                text_editor = ResizableTextEdit(scene_pos)
                self.scene.addItem(text_editor)

                # Focus the new editor
                text_editor.text_area.text_edit.setFocus()

                event.accept()
            else:
                # Let the item handle the double-click (e.g., text selection)
                super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        """Accept image drops"""
        if event.mimeData().hasImage() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle dropped images"""
        scene_pos = self.mapToScene(event.pos())

        # Handle image from mime data
        if event.mimeData().hasImage():
            image = QImage(event.mimeData().imageData())
            pixmap = QPixmap.fromImage(image)
            image_item = ResizableImage(pixmap, scene_pos)
            self.scene.addItem(image_item)
            event.acceptProposedAction()

        # Handle file drops
        elif event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    pixmap = QPixmap(file_path)
                    image_item = ResizableImage(pixmap, scene_pos)
                    self.scene.addItem(image_item)
            event.acceptProposedAction()

    def wheelEvent(self, event):
        """Zoom with Ctrl+Wheel"""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(zoom_factor, zoom_factor)
            event.accept()
        else:
            super().wheelEvent(event)


class NCONotesWindow(QMainWindow):
    """Main application window for NCONotes"""

    def __init__(self):
        super().__init__()

        self.current_notebook = None
        self.current_page = None
        self.notebooks_dir = Path.home() / "MyNotebooks"
        self.notebooks_dir.mkdir(exist_ok=True)

        # Undo stack
        self.undo_stack = QUndoStack(self)

        self.init_ui()
        self.load_notebooks()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("NCONotes")
        self.setGeometry(100, 100, 1200, 800)

        # Create toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Actions
        new_notebook_action = QAction("New Notebook", self)
        new_notebook_action.triggered.connect(self.new_notebook)
        toolbar.addAction(new_notebook_action)

        new_page_action = QAction("New Page", self)
        new_page_action.triggered.connect(self.new_page)
        toolbar.addAction(new_page_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_page)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # Undo/Redo (basic - you'd extend this)
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        toolbar.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        toolbar.addAction(redo_action)

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Splitter for resizable sidebar
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left sidebar
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)

        # Notebook list
        self.notebook_list = QListWidget()
        self.notebook_list.currentItemChanged.connect(self.on_notebook_selected)
        sidebar_layout.addWidget(self.notebook_list)

        # Page list
        self.page_list = QListWidget()
        self.page_list.currentItemChanged.connect(self.on_page_selected)
        sidebar_layout.addWidget(self.page_list)

        splitter.addWidget(sidebar)

        # Canvas
        self.canvas = InfiniteCanvas()
        splitter.addWidget(self.canvas)

        # Set splitter sizes
        splitter.setSizes([200, 1000])

        main_layout.addWidget(splitter)

    def new_notebook(self):
        """Create a new notebook with a default page.

        Every notebook gets a mandatory default page (pages[0]) that represents
        the notebook itself. This page is automatically loaded when the notebook
        is selected and never appears in the page list UI.
        """
        name, ok = QInputDialog.getText(self, "New Notebook", "Notebook name:")
        if ok and name:
            notebook_path = self.notebooks_dir / name
            notebook_path.mkdir(exist_ok=True)
            (notebook_path / "pages").mkdir(exist_ok=True)

            # Create default page (pages[0]) that represents the notebook itself
            default_page_id = "page_0"
            default_page_data = {'items': []}
            page_path = notebook_path / "pages" / f"{default_page_id}.json"
            with open(page_path, 'w') as f:
                json.dump(default_page_data, f, indent=2)

            # Save metadata with default page
            metadata = {
                'name': name,
                'pages': [{'id': default_page_id, 'name': name}]
            }
            with open(notebook_path / "notebook.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            self.load_notebooks()

    def new_page(self):
        """Create a new page in the current notebook"""
        if not self.current_notebook:
            QMessageBox.warning(self, "No Notebook", "Please select or create a notebook first.")
            return

        name, ok = QInputDialog.getText(self, "New Page", "Page name:")
        if ok and name:
            # Load notebook metadata
            notebook_path = self.notebooks_dir / self.current_notebook
            with open(notebook_path / "notebook.json", 'r') as f:
                metadata = json.load(f)

            # Add page
            page_id = f"page_{len(metadata['pages']) + 1}"
            metadata['pages'].append({
                'id': page_id,
                'name': name
            })

            # Save metadata
            with open(notebook_path / "notebook.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            # Create empty page file
            page_data = {'items': []}
            page_path = notebook_path / "pages" / f"{page_id}.json"
            with open(page_path, 'w') as f:
                json.dump(page_data, f, indent=2)

            self.load_pages()

    def load_notebooks(self):
        """Load all notebooks"""
        self.notebook_list.clear()

        for item in self.notebooks_dir.iterdir():
            if item.is_dir() and (item / "notebook.json").exists():
                self.notebook_list.addItem(item.name)

    def on_notebook_selected(self, current, previous):
        """Handle notebook selection.

        When a notebook is selected, automatically loads the default page (page_0).
        This makes the notebook immediately ready for work without requiring the
        user to manually select a page first.
        """
        if current:
            self.current_notebook = current.text()
            self.load_pages()

            # Auto-load the default page (pages[0])
            self.current_page = "page_0"
            self.load_page_content("page_0")

    def load_pages(self):
        """Load pages for current notebook into the page list UI.

        Skips pages[0] (the default page) since it's accessed by selecting
        the notebook itself, not from the page list. Only user-created pages
        (pages[1], pages[2], etc.) appear in the list.
        """
        self.page_list.clear()

        if not self.current_notebook:
            return

        notebook_path = self.notebooks_dir / self.current_notebook
        with open(notebook_path / "notebook.json", 'r') as f:
            metadata = json.load(f)

        # Skip pages[0] (default page) - it's accessed by selecting the notebook
        for page in metadata['pages'][1:]:
            self.page_list.addItem(page['name'])

    def on_page_selected(self, current, previous):
        """Handle page selection"""
        if current:
            # Save previous page if exists
            if self.current_page:
                self.save_page()

            # Load new page
            page_name = current.text()
            notebook_path = self.notebooks_dir / self.current_notebook

            with open(notebook_path / "notebook.json", 'r') as f:
                metadata = json.load(f)

            # Find page ID
            page_id = None
            for page in metadata['pages']:
                if page['name'] == page_name:
                    page_id = page['id']
                    break

            if page_id:
                self.current_page = page_id
                self.load_page_content(page_id)

    def load_page_content(self, page_id):
        """Load page content into canvas"""
        # Clear canvas
        self.canvas.scene.clear()

        notebook_path = self.notebooks_dir / self.current_notebook
        page_path = notebook_path / "pages" / f"{page_id}.json"

        if not page_path.exists():
            return

        with open(page_path, 'r') as f:
            page_data = json.load(f)

        images_dir = notebook_path / "images"

        # Restore items
        for item_data in page_data.get('items', []):
            if item_data['type'] == 'text':
                item = ResizableTextEdit.from_dict(item_data)
                self.canvas.scene.addItem(item)
            elif item_data['type'] == 'image':
                try:
                    item = ResizableImage.from_dict(item_data, images_dir)
                    self.canvas.scene.addItem(item)
                except FileNotFoundError as e:
                    print(f"Warning: {e}")

    def save_page(self):
        """Save current page"""
        if not self.current_page or not self.current_notebook:
            return

        notebook_path = self.notebooks_dir / self.current_notebook
        images_dir = notebook_path / "images"

        # Collect all items
        items = []
        for item in self.canvas.scene.items():
            if isinstance(item, ResizableTextEdit):
                items.append(item.to_dict())
            elif isinstance(item, ResizableImage):
                item.save_to_file(images_dir)
                items.append(item.to_dict())

        # Save to file
        page_path = notebook_path / "pages" / f"{self.current_page}.json"

        page_data = {'items': items}
        with open(page_path, 'w') as f:
            json.dump(page_data, f, indent=2)

        self.statusBar().showMessage(f"Saved page", 2000)

    def closeEvent(self, event):
        """Save before closing"""
        if self.current_page:
            self.save_page()
        event.accept()


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = NCONotesWindow()
    window.show()
    sys.exit(app.exec())
