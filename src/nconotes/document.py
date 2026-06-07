"""
Document layer for NCONotes - single source of truth for page data.

This module implements the Document/Controller pattern where PageDocument owns
all item data for a single page. The document is the model layer that emits
signals when data changes, allowing view components to react.

Main access points:
- PageDocument: Manages all items (text boxes, images) for a single page
"""

import uuid
from PySide6.QtCore import QObject, Signal


class PageDocument(QObject):
    """
    Single source of truth for all items on a page.

    Manages item lifecycle and emits signals when data changes.
    Views listen to these signals to update their display.
    """

    # Signals emitted when document state changes
    item_added = Signal(str, object)      # (item_id, TextBoxData|ImageData)
    item_removed = Signal(str)            # (item_id)
    item_modified = Signal(str, object)   # (item_id, TextBoxData|ImageData)

    def __init__(self):
        super().__init__()
        self._items = {}  # item_id → TextBoxData|ImageData

    def generate_id(self):
        """Generate a unique ID for a new item"""
        return str(uuid.uuid4())

    def add_item(self, item_id, data):
        """
        Add an item to the document.

        Args:
            item_id: Unique identifier for the item
            data: TextBoxData or ImageData instance
        """
        self._items[item_id] = data
        self.item_added.emit(item_id, data)

    def remove_item(self, item_id):
        """
        Remove an item from the document.

        Args:
            item_id: ID of the item to remove
        """
        if item_id in self._items:
            del self._items[item_id]
            self.item_removed.emit(item_id)

    def modify_item(self, item_id, data):
        """
        Update an existing item's data.

        Args:
            item_id: ID of the item to modify
            data: New TextBoxData or ImageData instance
        """
        if item_id in self._items:
            self._items[item_id] = data
            self.item_modified.emit(item_id, data)

    def get_item(self, item_id):
        """
        Retrieve an item by ID.

        Args:
            item_id: ID of the item to retrieve

        Returns:
            TextBoxData or ImageData instance, or None if not found
        """
        return self._items.get(item_id)

    def get_all_items(self):
        """
        Get all items in the document.

        Returns:
            Dict mapping item_id → TextBoxData|ImageData
        """
        return self._items.copy()
