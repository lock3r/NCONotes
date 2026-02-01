"""
Data models for NCONotes.

This module contains data-only classes representing canvas items.
Data models are separate from UI/logic to enable clean serialization and testing.

Main access points:
- TextBoxData: Represents a text box on the canvas
- ImageData: Represents an image on the canvas
"""


class TextBoxData:
    """Data model for a text box on the canvas"""

    def __init__(self, content='', x=0.0, y=0.0, width=300, height=200):
        self.content = content
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def to_dict(self):
        """Serialize to dictionary for JSON storage"""
        return {
            'type': 'text',
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'content': self.content
        }

    @staticmethod
    def from_dict(data):
        """Deserialize from dictionary"""
        return TextBoxData(
            content=data['content'],
            x=data['x'],
            y=data['y'],
            width=data['width'],
            height=data['height']
        )


class ImageData:
    """Data model for an image on the canvas"""

    def __init__(self, image_id='', x=0.0, y=0.0, scale=1.0, width=0, height=0):
        self.image_id = image_id
        self.x = x
        self.y = y
        self.scale = scale
        self.width = width
        self.height = height

    def to_dict(self):
        """Serialize to dictionary for JSON storage"""
        return {
            'type': 'image',
            'image_id': self.image_id,
            'x': self.x,
            'y': self.y,
            'scale': self.scale,
            'width': self.width,
            'height': self.height
        }

    @staticmethod
    def from_dict(data):
        """Deserialize from dictionary"""
        return ImageData(
            image_id=data['image_id'],
            x=data['x'],
            y=data['y'],
            scale=data['scale'],
            width=data['width'],
            height=data['height']
        )
