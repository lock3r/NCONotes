
"""
Reusable UI widgets for NCONotes.

This module contains standalone UI components that can be used across the application.

Main access points:
- TextAreaWidget: Standalone text editor widget with styling
- ResizableTextEdit: Canvas-ready text editor with title bar and resize handle
"""

from PySide6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QGraphicsProxyWidget, QGraphicsItem
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF
from PySide6.QtGui import QColor

from nconotes.models import TextBoxData


class TitleBarWidget(QWidget):
    """Title bar widget for dragging canvas items"""

    def __init__(self, height=10):
        super().__init__()
        self.setFixedHeight(height)
        self.is_visible = False
        self.update_style()

    def set_visible(self, visible):
        """Show or hide the title bar background"""
        self.is_visible = visible
        self.update_style()

    def update_style(self):
        """Update the title bar appearance"""
        if self.is_visible:
            self.setStyleSheet("background-color: rgb(220, 220, 220);")
        else:
            self.setStyleSheet("background-color: transparent;")


class TextAreaWidget(QWidget):
    """Standalone text editor widget with styling"""

    def __init__(self, width=300, height=200):
        super().__init__()
        self.init_ui(width, height)

    def init_ui(self, width, height):
        """Initialize the text editor with proper styling"""
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create text edit
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Start typing...")
        self.text_edit.setAcceptRichText(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid rgb(200, 200, 200);
            }
        """)

        layout.addWidget(self.text_edit)

        # Set initial size
        self.resize(width, height)

    def resize_widget(self, width, height):
        """Resize the widget to specified dimensions"""
        self.resize(int(width), int(height))

    def get_content(self):
        """Get HTML content from text editor"""
        return self.text_edit.toHtml()

    def set_content(self, html):
        """Set HTML content in text editor"""
        self.text_edit.setHtml(html)


class ResizableTextEdit(QGraphicsProxyWidget):
    """A resizable text editor with title bar that can be placed on the canvas"""

    def __init__(self, pos, size=None):
        super().__init__()

        # Create container widget
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create title bar
        self.title_bar = TitleBarWidget(height=10)
        container_layout.addWidget(self.title_bar)

        # Create text area widget
        if size:
            self.text_area = TextAreaWidget(int(size[0]), int(size[1]))
        else:
            self.text_area = TextAreaWidget(300, 200)
        container_layout.addWidget(self.text_area)

        # Set the container as the proxy widget
        self.setWidget(container)
        self.setPos(pos)

        # Make it selectable (movable only via title bar)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Resize handle
        self.resize_handle = None
        self.is_resizing = False
        self.resize_start_pos = None
        self.resize_start_size = None

        # Title bar state
        self.is_hovered = False
        self.is_title_bar_drag = False
        self.title_bar_drag_start_pos = None
        self.title_bar_drag_start_widget_pos = None

        # Enable hover events
        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)

        rect = self.boundingRect()

        # Update title bar visibility based on hover/focus state
        should_show_title = self.is_hovered or self.text_area.text_edit.hasFocus()
        self.title_bar.set_visible(should_show_title)

        # Draw resize handle (always visible)
        handle_size = 10
        handle_rect = QRectF(
            rect.right() - handle_size,
            rect.bottom() - handle_size,
            handle_size,
            handle_size
        )
        painter.fillRect(handle_rect, QColor(100, 100, 255))

    def hoverEnterEvent(self, event):
        """Track when mouse enters widget"""
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Track when mouse leaves widget"""
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self.boundingRect()

            # Check if clicking on title bar (top 10 pixels)
            title_bar_height = self.title_bar.height()
            title_bar_rect = QRectF(
                rect.left(),
                rect.top(),
                rect.width(),
                title_bar_height
            )

            if title_bar_rect.contains(event.pos()):
                self.is_title_bar_drag = True
                self.title_bar_drag_start_pos = event.scenePos()
                self.title_bar_drag_start_widget_pos = self.pos()
                event.accept()
                return

            # Check if clicking on resize handle
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
                self.resize_start_size = QSizeF(
                    self.text_area.width(),
                    self.text_area.height()
                )
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_title_bar_drag:
            delta = event.scenePos() - self.title_bar_drag_start_pos
            new_pos = self.title_bar_drag_start_widget_pos + delta
            self.setPos(new_pos)
            event.accept()
            return

        if self.is_resizing:
            delta = event.scenePos() - self.resize_start_pos
            new_width = max(100, self.resize_start_size.width() + delta.x())
            new_height = max(50, self.resize_start_size.height() + delta.y())

            # Notify Qt that geometry is about to change
            self.prepareGeometryChange()

            # Resize text area widget
            self.text_area.resize_widget(new_width, new_height)

            # Resize the proxy widget itself to match
            # Add title bar height to the total height
            total_height = new_height + self.title_bar.height()
            self.resize(int(new_width), int(total_height))

            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_title_bar_drag:
            self.is_title_bar_drag = False
            event.accept()
            return

        if self.is_resizing:
            self.is_resizing = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def to_dict(self):
        """Serialize to dictionary for saving"""
        data = TextBoxData(
            content=self.text_area.get_content(),
            x=self.pos().x(),
            y=self.pos().y(),
            width=self.text_area.width(),
            height=self.text_area.height()
        )
        return data.to_dict()

    @staticmethod
    def from_dict(data):
        """Deserialize from dictionary"""
        text_data = TextBoxData.from_dict(data)
        pos = QPointF(text_data.x, text_data.y)
        size = (text_data.width, text_data.height)
        widget = ResizableTextEdit(pos, size)
        widget.text_area.set_content(text_data.content)
        return widget
