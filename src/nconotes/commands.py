"""
Undo/Redo commands for NCONotes document operations.

This module implements QUndoCommand subclasses for all operations that modify
the document state. Each command encapsulates the data needed to perform an
operation and reverse it.

Main access points:
- CreateItemCommand: Add a new item (text box or image) to the document
- DeleteItemCommand: Remove an item from the document
- MoveItemCommand: Change an item's position
- ResizeItemCommand: Change an item's size
"""

from PySide6.QtGui import QUndoCommand
from nconotes.models import TextBoxData, ImageData


class CreateItemCommand(QUndoCommand):
    """
    Command to create a new item in the document.

    On redo: adds item to document
    On undo: removes item from document
    """

    def __init__(self, document, item_id, data):
        """
        Args:
            document: PageDocument instance
            item_id: Unique ID for the new item
            data: TextBoxData or ImageData instance
        """
        super().__init__()
        self.document = document
        self.item_id = item_id
        self.data = data

        # Set user-visible text for undo menu
        item_type = "text box" if isinstance(data, TextBoxData) else "image"
        self.setText(f"Create {item_type}")

    def redo(self):
        """Add item to document"""
        self.document.add_item(self.item_id, self.data)

    def undo(self):
        """Remove item from document"""
        self.document.remove_item(self.item_id)


class DeleteItemCommand(QUndoCommand):
    """
    Command to delete an item from the document.

    On redo: removes item from document
    On undo: restores item to document
    """

    def __init__(self, document, item_id):
        """
        Args:
            document: PageDocument instance
            item_id: ID of item to delete
        """
        super().__init__()
        self.document = document
        self.item_id = item_id

        # Store item data before deletion so we can restore it
        self.data = document.get_item(item_id)

        item_type = "text box" if isinstance(self.data, TextBoxData) else "image"
        self.setText(f"Delete {item_type}")

    def redo(self):
        """Remove item from document"""
        self.document.remove_item(self.item_id)

    def undo(self):
        """Restore item to document"""
        self.document.add_item(self.item_id, self.data)


class MoveItemCommand(QUndoCommand):
    """
    Command to move an item to a new position.

    On redo: applies new position
    On undo: restores old position
    """

    def __init__(self, document, item_id, old_pos, new_pos):
        """
        Args:
            document: PageDocument instance
            item_id: ID of item to move
            old_pos: QPointF with original position
            new_pos: QPointF with new position
        """
        super().__init__()
        self.document = document
        self.item_id = item_id
        self.old_pos = old_pos
        self.new_pos = new_pos

        self.setText("Move item")

    def redo(self):
        """Apply new position"""
        data = self.document.get_item(self.item_id)
        if data:
            # Create new data object with updated position
            if isinstance(data, TextBoxData):
                new_data = TextBoxData(
                    content=data.content,
                    x=self.new_pos.x(),
                    y=self.new_pos.y(),
                    width=data.width,
                    height=data.height
                )
            else:  # ImageData
                new_data = ImageData(
                    image_id=data.image_id,
                    x=self.new_pos.x(),
                    y=self.new_pos.y(),
                    scale=data.scale,
                    width=data.width,
                    height=data.height
                )
            self.document.modify_item(self.item_id, new_data)

    def undo(self):
        """Restore old position"""
        data = self.document.get_item(self.item_id)
        if data:
            # Create new data object with old position
            if isinstance(data, TextBoxData):
                old_data = TextBoxData(
                    content=data.content,
                    x=self.old_pos.x(),
                    y=self.old_pos.y(),
                    width=data.width,
                    height=data.height
                )
            else:  # ImageData
                old_data = ImageData(
                    image_id=data.image_id,
                    x=self.old_pos.x(),
                    y=self.old_pos.y(),
                    scale=data.scale,
                    width=data.width,
                    height=data.height
                )
            self.document.modify_item(self.item_id, old_data)


class ResizeItemCommand(QUndoCommand):
    """
    Command to resize an item.

    On redo: applies new size
    On undo: restores old size
    """

    def __init__(self, document, item_id, old_size, new_size):
        """
        Args:
            document: PageDocument instance
            item_id: ID of item to resize
            old_size: Tuple (width, height) with original size
            new_size: Tuple (width, height) with new size
        """
        super().__init__()
        self.document = document
        self.item_id = item_id
        self.old_size = old_size
        self.new_size = new_size

        self.setText("Resize item")

    def redo(self):
        """Apply new size"""
        data = self.document.get_item(self.item_id)
        if data:
            # Create new data object with updated size
            if isinstance(data, TextBoxData):
                new_data = TextBoxData(
                    content=data.content,
                    x=data.x,
                    y=data.y,
                    width=self.new_size[0],
                    height=self.new_size[1]
                )
            else:  # ImageData
                new_data = ImageData(
                    image_id=data.image_id,
                    x=data.x,
                    y=data.y,
                    scale=data.scale,
                    width=self.new_size[0],
                    height=self.new_size[1]
                )
            self.document.modify_item(self.item_id, new_data)

    def undo(self):
        """Restore old size"""
        data = self.document.get_item(self.item_id)
        if data:
            # Create new data object with old size
            if isinstance(data, TextBoxData):
                old_data = TextBoxData(
                    content=data.content,
                    x=data.x,
                    y=data.y,
                    width=self.old_size[0],
                    height=self.old_size[1]
                )
            else:  # ImageData
                old_data = ImageData(
                    image_id=data.image_id,
                    x=data.x,
                    y=data.y,
                    scale=data.scale,
                    width=self.old_size[0],
                    height=self.old_size[1]
                )
            self.document.modify_item(self.item_id, old_data)
