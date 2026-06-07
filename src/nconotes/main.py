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
from PySide6.QtCore import Qt, QRectF, QPointF, QSettings, Signal, QObject
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QTransform, QAction, QKeySequence, QUndoStack, QUndoCommand, QIcon, QFont
)

from nconotes.models import ImageData
from nconotes.widgets import ResizableTextEdit


class ResizableImage(QObject, QGraphicsPixmapItem):
    """A resizable, movable image on the canvas"""

    # Signals for document operations
    move_finished = Signal(QPointF, QPointF)    # (old_pos, new_pos)
    resize_finished = Signal(tuple, tuple)       # (old_size, new_size)

    def __init__(self, pixmap, pos, image_id=None):
        QObject.__init__(self)
        QGraphicsPixmapItem.__init__(self, pixmap)

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

        # Track state for undo/redo commands
        self.drag_start_position = None  # Position when drag started
        self.resize_start_dimensions = None  # (width, height) when resize started
        self.is_moving = False

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
                # Track starting dimensions for undo/redo
                pixmap = self.original_pixmap
                self.resize_start_dimensions = (pixmap.width(), pixmap.height())
                event.accept()
                return
            else:
                # Track starting position for move operation
                self.is_moving = True
                self.drag_start_position = QPointF(self.pos())

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
            # Emit signal if size changed
            if self.resize_start_dimensions is not None:
                pixmap = self.original_pixmap
                new_size = (pixmap.width(), pixmap.height())
                if new_size != self.resize_start_dimensions:
                    self.resize_finished.emit(self.resize_start_dimensions, new_size)
                self.resize_start_dimensions = None
            event.accept()
            return

        if self.is_moving:
            self.is_moving = False
            # Emit signal if position changed
            if self.drag_start_position is not None:
                new_pos = self.pos()
                if new_pos != self.drag_start_position:
                    self.move_finished.emit(self.drag_start_position, new_pos)
                self.drag_start_position = None

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

    @staticmethod
    def from_image_data(data, images_dir):
        """Create ResizableImage from ImageData object"""
        image_path = images_dir / f"{data.image_id}.png"

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        pixmap = QPixmap(str(image_path))
        pos = QPointF(data.x, data.y)
        widget = ResizableImage(pixmap, pos, image_id=data.image_id)
        widget.setScale(data.scale)
        widget.current_scale = data.scale
        return widget

    def update_from_data(self, data):
        """
        Update widget state from ImageData object.

        Used when document state changes (e.g., during undo/redo).
        """
        self.setPos(QPointF(data.x, data.y))
        self.setScale(data.scale)
        self.current_scale = data.scale


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

        # Document integration
        self.document = None
        self.item_widgets = {}  # item_id → widget mapping
        self.images_dir = None  # Path to images directory for current notebook

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
                # Notify parent window to handle creation (via command pattern)
                if hasattr(self.parent(), 'on_canvas_double_click'):
                    self.parent().on_canvas_double_click(scene_pos)
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
            # Notify parent window to handle creation (via command pattern)
            if hasattr(self.parent(), 'on_image_dropped'):
                self.parent().on_image_dropped(pixmap, scene_pos)
            event.acceptProposedAction()

        # Handle file drops
        elif event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    pixmap = QPixmap(file_path)
                    # Notify parent window to handle creation (via command pattern)
                    if hasattr(self.parent(), 'on_image_dropped'):
                        self.parent().on_image_dropped(pixmap, scene_pos)
            event.acceptProposedAction()

    def wheelEvent(self, event):
        """Zoom with Ctrl+Wheel"""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(zoom_factor, zoom_factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def set_document(self, document, images_dir):
        """
        Connect canvas to a PageDocument.

        Args:
            document: PageDocument instance
            images_dir: Path to images directory for loading image files

        Connects to document signals and populates the scene with existing items.
        """
        # Disconnect from old document if any
        if self.document:
            self.document.item_added.disconnect(self._on_item_added)
            self.document.item_removed.disconnect(self._on_item_removed)
            self.document.item_modified.disconnect(self._on_item_modified)

        self.document = document
        self.images_dir = images_dir

        # Clear scene and widget mapping
        self.scene.clear()
        self.item_widgets.clear()

        # Connect to document signals
        self.document.item_added.connect(self._on_item_added)
        self.document.item_removed.connect(self._on_item_removed)
        self.document.item_modified.connect(self._on_item_modified)

        # Populate scene with existing items
        for item_id, data in self.document.get_all_items().items():
            self._on_item_added(item_id, data)

    def _on_item_added(self, item_id, data):
        """Create and add a widget when an item is added to the document"""
        from nconotes.models import TextBoxData, ImageData

        if isinstance(data, TextBoxData):
            # Create text box widget
            pos = QPointF(data.x, data.y)
            size = (data.width, data.height)
            widget = ResizableTextEdit(pos, size)
            widget.text_area.set_content(data.content)
        elif isinstance(data, ImageData):
            # Create image widget
            try:
                widget = ResizableImage.from_image_data(data, self.images_dir)
            except FileNotFoundError as e:
                print(f"Warning: {e}")
                return
        else:
            return

        # Store item_id in widget for later reference
        widget.item_id = item_id

        # Connect widget signals to parent window controller methods
        if hasattr(self.parent(), 'on_item_moved'):
            widget.move_finished.connect(
                lambda old_pos, new_pos: self.parent().on_item_moved(item_id, old_pos, new_pos)
            )
        if hasattr(self.parent(), 'on_item_resized'):
            widget.resize_finished.connect(
                lambda old_size, new_size: self.parent().on_item_resized(item_id, old_size, new_size)
            )

        # Add to scene and mapping
        self.scene.addItem(widget)
        self.item_widgets[item_id] = widget

    def _on_item_removed(self, item_id):
        """Remove widget when an item is removed from the document"""
        if item_id in self.item_widgets:
            widget = self.item_widgets[item_id]
            self.scene.removeItem(widget)
            del self.item_widgets[item_id]

    def _on_item_modified(self, item_id, data):
        """Update widget when an item is modified in the document"""
        if item_id in self.item_widgets:
            widget = self.item_widgets[item_id]
            widget.update_from_data(data)


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

            # Update existing text editors on the current page
            # Get the main window (parent of this dialog)
            if self.parent():
                main_window = self.parent()
                if hasattr(main_window, 'canvas'):
                    for item in main_window.canvas.scene.items():
                        if isinstance(item, ResizableTextEdit):
                            item.text_area.update_font_size()


class NCONotesWindow(QMainWindow):
    """Main application window for NCONotes"""

    def __init__(self):
        super().__init__()

        self.current_notebook = None
        self.current_page = None
        self.notebooks_dir = Path.home() / "MyNotebooks"
        self.notebooks_dir.mkdir(exist_ok=True)

        # Document layer
        self.current_document = None

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

        # Undo/Redo (shortcuts handled by event filter for context-aware routing)
        undo_action = QAction("Undo", self)
        undo_action.triggered.connect(self.undo_stack.undo)
        toolbar.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.triggered.connect(self.undo_stack.redo)
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

        # Install event filter for context-aware undo/redo routing
        self.installEventFilter(self)

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
        """Load page content into canvas using document pattern"""
        from nconotes.document import PageDocument
        from nconotes.models import TextBoxData, ImageData

        # Create new document for this page
        self.current_document = PageDocument()

        notebook_path = self.notebooks_dir / self.current_notebook
        page_path = notebook_path / "pages" / f"{page_id}.json"
        images_dir = notebook_path / "images"

        # Load existing items if page exists
        if page_path.exists():
            with open(page_path, 'r') as f:
                page_data = json.load(f)

            # Populate document with items
            for item_data in page_data.get('items', []):
                # Generate ID if missing (backward compatibility)
                item_id = item_data.get('id')
                if not item_id:
                    item_id = self.current_document.generate_id()

                # Create data object based on type
                if item_data['type'] == 'text':
                    data = TextBoxData.from_dict(item_data)
                elif item_data['type'] == 'image':
                    data = ImageData.from_dict(item_data)
                else:
                    continue

                # Add to document (not through command - this is loading)
                self.current_document.add_item(item_id, data)

        # Connect canvas to document
        self.canvas.set_document(self.current_document, images_dir)

        # Clear undo stack (new page means fresh history)
        self.undo_stack.clear()

    def save_page(self):
        """Save current page using document pattern"""
        if not self.current_page or not self.current_notebook or not self.current_document:
            return

        from nconotes.models import TextBoxData, ImageData

        notebook_path = self.notebooks_dir / self.current_notebook
        images_dir = notebook_path / "images"

        # Sync text content from widgets to document
        # (Text content is managed by QTextEdit, not the document)
        for item_id, widget in self.canvas.item_widgets.items():
            if isinstance(widget, ResizableTextEdit):
                data = self.current_document.get_item(item_id)
                if data and isinstance(data, TextBoxData):
                    # Update content but keep position/size from document
                    updated_data = TextBoxData(
                        content=widget.text_area.get_content(),
                        x=data.x,
                        y=data.y,
                        width=data.width,
                        height=data.height
                    )
                    self.current_document.modify_item(item_id, updated_data)

        # Collect all items from document
        items = []
        for item_id, data in self.current_document.get_all_items().items():
            # Serialize data to dict and add ID
            item_dict = data.to_dict()
            item_dict['id'] = item_id
            items.append(item_dict)

            # Save image files to disk
            if isinstance(data, ImageData):
                # Find the widget to save its pixmap
                if item_id in self.canvas.item_widgets:
                    widget = self.canvas.item_widgets[item_id]
                    if isinstance(widget, ResizableImage):
                        widget.save_to_file(images_dir)

        # Save to file
        page_path = notebook_path / "pages" / f"{self.current_page}.json"
        page_data = {'items': items}
        with open(page_path, 'w') as f:
            json.dump(page_data, f, indent=2)

        self.statusBar().showMessage(f"Saved page", 2000)

    def on_canvas_double_click(self, pos):
        """
        Handle double-click on canvas to create text box.

        Creates a command and pushes it to the undo stack.
        """
        if not self.current_document:
            return

        from nconotes.models import TextBoxData
        from nconotes.commands import CreateItemCommand

        # Generate ID and create data
        item_id = self.current_document.generate_id()
        data = TextBoxData(
            content='',
            x=pos.x(),
            y=pos.y(),
            width=300,
            height=200
        )

        # Create and execute command
        command = CreateItemCommand(self.current_document, item_id, data)
        self.undo_stack.push(command)

        # Focus the new text editor
        if item_id in self.canvas.item_widgets:
            widget = self.canvas.item_widgets[item_id]
            if isinstance(widget, ResizableTextEdit):
                widget.text_area.text_edit.setFocus()

    def on_image_dropped(self, pixmap, pos):
        """
        Handle image drop on canvas.

        Saves image to disk and creates a command.
        """
        if not self.current_document or not self.current_notebook:
            return

        from nconotes.models import ImageData
        from nconotes.commands import CreateItemCommand

        # Generate IDs
        item_id = self.current_document.generate_id()
        image_id = str(uuid.uuid4())

        # Save image to disk
        notebook_path = self.notebooks_dir / self.current_notebook
        images_dir = notebook_path / "images"
        images_dir.mkdir(exist_ok=True)
        image_path = images_dir / f"{image_id}.png"
        pixmap.save(str(image_path), "PNG")

        # Create data
        data = ImageData(
            image_id=image_id,
            x=pos.x(),
            y=pos.y(),
            scale=1.0,
            width=pixmap.width(),
            height=pixmap.height()
        )

        # Create and execute command
        command = CreateItemCommand(self.current_document, item_id, data)
        self.undo_stack.push(command)

    def on_item_moved(self, item_id, old_pos, new_pos):
        """
        Handle item move operation.

        Creates a command and pushes it to the undo stack.
        """
        if not self.current_document:
            return

        from nconotes.commands import MoveItemCommand

        command = MoveItemCommand(self.current_document, item_id, old_pos, new_pos)
        self.undo_stack.push(command)

    def on_item_resized(self, item_id, old_size, new_size):
        """
        Handle item resize operation.

        Creates a command and pushes it to the undo stack.
        """
        if not self.current_document:
            return

        from nconotes.commands import ResizeItemCommand

        command = ResizeItemCommand(self.current_document, item_id, old_size, new_size)
        self.undo_stack.push(command)

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

    def eventFilter(self, obj, event):
        """
        Event filter for context-aware undo/redo routing.

        Routes Ctrl+Z/Ctrl+Shift+Z based on focus:
        - If QTextEdit has focus: let it handle typing undo
        - Otherwise: use document undo stack
        """
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.KeyPress:
            # Check for Undo shortcut
            if event.matches(QKeySequence.StandardKey.Undo):
                focused = QApplication.focusWidget()
                if isinstance(focused, QTextEdit):
                    # Let QTextEdit handle its own undo
                    return False
                else:
                    # Use document undo stack
                    self.undo_stack.undo()
                    return True

            # Check for Redo shortcut
            if event.matches(QKeySequence.StandardKey.Redo):
                focused = QApplication.focusWidget()
                if isinstance(focused, QTextEdit):
                    # Let QTextEdit handle its own redo
                    return False
                else:
                    # Use document undo stack
                    self.undo_stack.redo()
                    return True

        return super().eventFilter(obj, event)


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
