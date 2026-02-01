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
    QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QTreeWidget, QTreeWidgetItem, QSplitter,
    QGraphicsPixmapItem, QGraphicsRectItem, QMessageBox, QToolBar,
    QGraphicsItem, QInputDialog, QDialog, QListWidget, QStackedWidget,
    QLabel, QComboBox, QFormLayout, QSizePolicy, QTextEdit
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSettings
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QTransform, QAction, QKeySequence, QUndoStack, QUndoCommand, QIcon, QFont
)

from nconotes.models import ImageData
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

        # Enable scrollbars for navigation
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Smooth rendering
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Grid background
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250)))

        # Accept drops
        self.setAcceptDrops(True)

        # Track panning state
        self.is_panning = False
        self.pan_start_pos = None

    def mousePressEvent(self, event):
        """Handle mouse press for panning (Ctrl+drag or middle-mouse)"""
        if (event.button() == Qt.MouseButton.LeftButton and
            event.modifiers() == Qt.KeyboardModifier.ControlModifier) or \
           event.button() == Qt.MouseButton.MiddleButton:
            # Start panning
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for panning"""
        if self.is_panning and self.pan_start_pos is not None:
            # Calculate delta and pan the view
            delta = event.pos() - self.pan_start_pos
            self.pan_start_pos = event.pos()

            # Move scrollbars (negative because we're moving the viewport)
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for panning"""
        if self.is_panning and (
            event.button() == Qt.MouseButton.LeftButton or
            event.button() == Qt.MouseButton.MiddleButton):
            # End panning
            self.is_panning = False
            self.pan_start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

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


class SettingsWindow(QDialog):
    """Settings dialog with category sidebar and content panels"""

    # Scale options with their multipliers
    SCALE_OPTIONS = {
        "Very Small": 0.8,
        "Small": 1.0,
        "Big": 1.3,
        "Very Big": 1.8
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(600, 400)

        self.settings = QSettings("NCONotes", "NCONotes")
        self.init_ui()

    def init_ui(self):
        """Initialize the settings UI with category sidebar and content panel"""
        layout = QHBoxLayout(self)

        # Left sidebar - categories
        self.category_list = QListWidget()
        self.category_list.setMaximumWidth(150)
        self.category_list.addItem("UI")
        self.category_list.currentRowChanged.connect(self.change_category)
        layout.addWidget(self.category_list)

        # Right panel - stacked widget for different category content
        self.content_stack = QStackedWidget()
        layout.addWidget(self.content_stack)

        # Add UI category panel
        self.ui_panel = self.create_ui_panel()
        self.content_stack.addWidget(self.ui_panel)

        # Select first category by default
        self.category_list.setCurrentRow(0)

    def create_ui_panel(self):
        """Create the UI settings panel with scale dropdown"""
        panel = QWidget()
        layout = QFormLayout(panel)

        # Scale dropdown
        self.scale_combo = QComboBox()
        for scale_name in self.SCALE_OPTIONS.keys():
            self.scale_combo.addItem(scale_name)

        # Load current scale from settings
        current_scale = self.settings.value("ui_scale", 1.0, type=float)
        # Find matching scale option
        for i, (name, scale) in enumerate(self.SCALE_OPTIONS.items()):
            if abs(scale - current_scale) < 0.01:  # Float comparison tolerance
                self.scale_combo.setCurrentIndex(i)
                break

        # Connect to immediate apply
        self.scale_combo.currentTextChanged.connect(self.apply_scale)

        layout.addRow("UI Scale:", self.scale_combo)

        return panel

    def change_category(self, index):
        """Switch to the selected category panel"""
        self.content_stack.setCurrentIndex(index)

    def apply_scale(self, scale_name):
        """Apply the selected scale immediately"""
        scale_value = self.SCALE_OPTIONS[scale_name]
        self.settings.setValue("ui_scale", scale_value)

        # Get the QApplication instance and apply scale
        app = QApplication.instance()
        if app:
            # Reset to default first
            app.setStyleSheet("")
            # Apply new scale using stylesheet font scaling
            app.setStyleSheet(f"""
                * {{
                    font-size: {int(10 * scale_value)}pt;
                }}
                QTreeWidget, QListWidget {{
                    font-size: {int(10 * scale_value)}pt;
                }}
                QTextEdit {{
                    font-size: {int(11 * scale_value)}pt;
                }}
            """)

            # Update existing text editors in the canvas
            # Get the main window (parent of this dialog)
            if self.parent():
                main_window = self.parent()
                if hasattr(main_window, 'canvas'):
                    for item in main_window.canvas.scene.items():
                        if isinstance(item, ResizableTextEdit):
                            # Directly set the font size
                            font = item.text_area.text_edit.font()
                            font.setPointSize(int(11 * scale_value))
                            item.text_area.text_edit.setFont(font)


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

        # Settings for persisting UI state
        self.settings = QSettings("NCONotes", "NCONotes")

        self.init_ui()
        self.load_notebooks()
        self.restore_tree_state()

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

        # Add spacer to push settings button to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Settings button (anchored to right)
        settings_action = QAction(QIcon("icons/settings_icon_black.svg"), "Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Splitter for resizable sidebar
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left sidebar
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)

        # Notebook tree (notebooks with their pages)
        self.notebook_tree = QTreeWidget()
        self.notebook_tree.setHeaderHidden(True)
        self.notebook_tree.currentItemChanged.connect(self.on_tree_item_selected)
        self.notebook_tree.itemExpanded.connect(self.save_tree_state)
        self.notebook_tree.itemCollapsed.connect(self.save_tree_state)
        sidebar_layout.addWidget(self.notebook_tree)

        splitter.addWidget(sidebar)

        # Canvas
        self.canvas = InfiniteCanvas()
        splitter.addWidget(self.canvas)

        # Set splitter sizes
        splitter.setSizes([200, 1000])

        main_layout.addWidget(splitter)

    def open_settings(self):
        """Open the settings dialog"""
        settings_dialog = SettingsWindow(self)
        settings_dialog.exec()

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

            self.load_notebooks()

    def load_notebooks(self):
        """Load all notebooks and their pages into the tree"""
        self.notebook_tree.clear()

        for item in self.notebooks_dir.iterdir():
            if item.is_dir() and (item / "notebook.json").exists():
                # Create notebook item
                notebook_item = QTreeWidgetItem([item.name])
                notebook_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'notebook',
                    'notebook_name': item.name
                })
                self.notebook_tree.addTopLevelItem(notebook_item)

                # Load pages for this notebook
                notebook_path = self.notebooks_dir / item.name
                with open(notebook_path / "notebook.json", 'r') as f:
                    metadata = json.load(f)

                # Add pages (skip page_0 which represents the notebook itself)
                for page in metadata['pages'][1:]:
                    page_item = QTreeWidgetItem([page['name']])
                    page_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'page',
                        'notebook_name': item.name,
                        'page_id': page['id']
                    })
                    notebook_item.addChild(page_item)

    def on_tree_item_selected(self, current, _previous):
        """Handle tree item selection (notebook or page).

        When a notebook is selected, loads the default page (page_0).
        When a page is selected, loads that specific page.
        """
        if not current:
            return

        # Save previous page if exists
        if self.current_page:
            self.save_page()

        # Get item data
        item_data = current.data(0, Qt.ItemDataRole.UserRole)
        if not item_data:
            return

        item_type = item_data['type']
        notebook_name = item_data['notebook_name']

        if item_type == 'notebook':
            # Notebook selected - load its default page (page_0)
            self.current_notebook = notebook_name
            self.current_page = "page_0"
            self.load_page_content("page_0")
        elif item_type == 'page':
            # Page selected - load that page
            self.current_notebook = notebook_name
            page_id = item_data['page_id']
            self.current_page = page_id
            self.load_page_content(page_id)

        # Save state after selection changes
        self.save_tree_state()

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

    def save_tree_state(self):
        """Save tree expansion state and current selection"""
        expanded_notebooks = []
        for i in range(self.notebook_tree.topLevelItemCount()):
            item = self.notebook_tree.topLevelItem(i)
            if item.isExpanded():
                expanded_notebooks.append(item.text(0))

        self.settings.setValue("expanded_notebooks", expanded_notebooks)
        self.settings.setValue("current_notebook", self.current_notebook)
        self.settings.setValue("current_page", self.current_page)

    def restore_tree_state(self):
        """Restore tree expansion state and selection from previous session"""
        expanded_notebooks = self.settings.value("expanded_notebooks", [])
        saved_notebook = self.settings.value("current_notebook", None)
        saved_page = self.settings.value("current_page", None)

        # Restore expansion state
        for i in range(self.notebook_tree.topLevelItemCount()):
            item = self.notebook_tree.topLevelItem(i)
            if item.text(0) in expanded_notebooks:
                item.setExpanded(True)

        # Restore selection if previous session had one
        if saved_notebook and saved_page:
            self.restore_selection(saved_notebook, saved_page)

    def restore_selection(self, notebook_name, page_id):
        """Restore the selected item in the tree"""
        # Find and select the appropriate tree item
        for i in range(self.notebook_tree.topLevelItemCount()):
            notebook_item = self.notebook_tree.topLevelItem(i)
            item_data = notebook_item.data(0, Qt.ItemDataRole.UserRole)

            if item_data and item_data['notebook_name'] == notebook_name:
                if page_id == "page_0":
                    # Select the notebook itself
                    self.notebook_tree.setCurrentItem(notebook_item)
                    return
                else:
                    # Find the page child
                    for j in range(notebook_item.childCount()):
                        page_item = notebook_item.child(j)
                        page_data = page_item.data(0, Qt.ItemDataRole.UserRole)
                        if page_data and page_data['page_id'] == page_id:
                            self.notebook_tree.setCurrentItem(page_item)
                            return

    def closeEvent(self, event):
        """Save before closing"""
        if self.current_page:
            self.save_page()
        self.save_tree_state()
        event.accept()


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)

    # Load and apply saved UI scale
    settings = QSettings("NCONotes", "NCONotes")
    scale = settings.value("ui_scale", 1.0, type=float)
    app.setStyleSheet(f"""
        * {{
            font-size: {int(10 * scale)}pt;
        }}
        QTreeWidget, QListWidget {{
            font-size: {int(10 * scale)}pt;
        }}
        QTextEdit {{
            font-size: {int(11 * scale)}pt;
        }}
    """)

    window = NCONotesWindow()
    window.show()
    sys.exit(app.exec())
