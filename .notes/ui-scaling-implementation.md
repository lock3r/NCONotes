# UI Scaling Implementation

## Current Implementation

The UI scaling system allows users to change the overall font size of the application through Settings > UI Scale. The system is implemented in two main components:

### 1. New Text (widgets.py:67-72)
When a new `TextAreaWidget` is created, it reads the current `ui_scale` from QSettings and applies it:
```python
settings = QSettings("NCONotes", "NCONotes")
scale = settings.value("ui_scale", 1.0, type=float)
font = self.text_edit.font()
font.setPointSize(int(11 * scale))
```

### 2. Existing Text (widgets.py:91-114)
The `update_font_size()` method updates all existing text in a text editor:
- Called when loading pages from JSON (ResizableTextEdit.from_dict())
- Called when user changes scale in settings (SettingsWindow.apply_scale())

**Key behavior**: Sets ALL text to `11 * scale` point size, regardless of what size it was before.

## Current Limitation: Assumes Single Font Size

The current implementation **assumes all text is the same size** (11pt baseline). This works fine when:
- All text in notes is uniform size
- Users cannot change font sizes within a note

**This will break when** users can set different font sizes within notes (e.g., headlines, body text, annotations).

### Example of Breakage

If a user creates a note with:
- Headline: 18pt
- Body: 12pt
- Caption: 9pt

Then changes UI scale from 1.0 → 1.5, the current code will:
- Set headline to 16.5pt (11 * 1.5) ❌ Should be 27pt (18 * 1.5)
- Set body to 16.5pt (11 * 1.5) ❌ Should be 18pt (12 * 1.5)
- Set caption to 16.5pt (11 * 1.5) ❌ Should be 13.5pt (9 * 1.5)

**All text becomes the same size**, losing the intentional size differences.

## Future: Supporting Mixed Font Sizes

To support mixed font sizes and formatting, we need **proportional scaling** instead of absolute scaling.

### Implementation Approach

1. **Track Previous Scale**
   - Store the scale value that was active when text was last updated
   - Could store in QSettings or as metadata in each text document

2. **Calculate Scaling Ratio**
   ```python
   old_scale = settings.value("last_applied_scale", 1.0, type=float)
   new_scale = settings.value("ui_scale", 1.0, type=float)
   ratio = new_scale / old_scale
   ```

3. **Scale Each Text Fragment Proportionally**
   Instead of setting all text to `11 * scale`, iterate through the document and scale each fragment:
   ```python
   cursor = QTextCursor(text_edit.document())
   cursor.movePosition(QTextCursor.MoveOperation.Start)

   while not cursor.atEnd():
       cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,
                          QTextCursor.MoveMode.KeepAnchor)

       char_format = cursor.charFormat()
       current_size = char_format.fontPointSize()
       new_size = current_size * ratio

       char_format.setFontPointSize(new_size)
       cursor.setCharFormat(char_format)

       cursor.clearSelection()
   ```

4. **Update Last Applied Scale**
   ```python
   settings.setValue("last_applied_scale", new_scale)
   ```

### Edge Cases to Handle

- **First time loading old documents**: If no `last_applied_scale` exists, assume 1.0
- **Empty text areas**: Handle gracefully, just set default font
- **Formatted text with no explicit size**: QTextEdit defaults to widget font, need to handle these specially
- **Very small/large sizes**: May need min/max bounds after scaling

### Files to Modify

1. **widgets.py**: Update `TextAreaWidget.update_font_size()` method
2. **main.py**: Update `SettingsWindow.apply_scale()` to track previous scale
3. **Settings persistence**: Add `last_applied_scale` to QSettings

## Related Qt Concepts

### QTextCursor Iteration
QTextCursor can iterate through a document character-by-character or block-by-block. For font size updates, character-by-character is safer but slower. Consider block-level optimization if performance becomes an issue.

### QTextCharFormat
Contains formatting for text fragments. Key properties:
- `fontPointSize()`: Current font size in points
- `setFontPointSize()`: Set new font size
- `mergeCharFormat()`: Apply format changes while preserving other properties

### Rich Text HTML Storage
QTextEdit stores rich text as HTML with inline styles. Font sizes are stored as `style="font-size:12pt"` in the HTML. The cursor-based approach bypasses HTML and works directly with Qt's text document model, which is more reliable for programmatic updates.
