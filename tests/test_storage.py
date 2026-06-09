# Tests for the storage layer (backend/storage/notebooks.py).
# All tests use a temporary directory via the NCONOTES_STORAGE_ROOT env var
# so they never touch ~/MyNotebooks/.

import os
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from backend.storage import notebooks as storage
from backend.storage.models import Page, TextItem, ImageItem, ViewState


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    """Point the storage layer at a fresh temporary directory for each test."""
    monkeypatch.setenv("NCONOTES_STORAGE_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------

class TestCreateNotebook:
    def test_returns_notebook_with_name_and_id(self):
        nb = storage.create_notebook("Work")
        assert nb.name == "Work"
        assert nb.id

    def test_creates_page0_automatically(self):
        nb = storage.create_notebook("Work")
        assert len(nb.pages) == 1
        assert nb.pages[0].title == ""

    def test_directories_created_on_disk(self, tmp_path):
        nb = storage.create_notebook("Work")
        assert (tmp_path / nb.id / "pages").is_dir()
        assert (tmp_path / nb.id / "images").is_dir()

    def test_notebook_json_written(self, tmp_path):
        nb = storage.create_notebook("Work")
        data = json.loads((tmp_path / nb.id / "notebook.json").read_text())
        assert data["name"] == "Work"
        assert data["id"] == nb.id

    def test_page0_json_written(self, tmp_path):
        nb = storage.create_notebook("Work")
        page0_id = nb.pages[0].id
        page_path = tmp_path / nb.id / "pages" / f"{page0_id}.json"
        assert page_path.exists()


class TestListNotebooks:
    def test_empty_when_no_notebooks(self):
        assert storage.list_notebooks() == []

    def test_returns_created_notebooks(self):
        storage.create_notebook("A")
        storage.create_notebook("B")
        names = {nb.name for nb in storage.list_notebooks()}
        assert names == {"A", "B"}

    def test_excludes_trashed_notebooks(self):
        nb = storage.create_notebook("ToDelete")
        storage.delete_notebook(nb.id)
        assert storage.list_notebooks() == []


class TestDeleteNotebook:
    def test_moves_to_trash(self, tmp_path):
        nb = storage.create_notebook("Gone")
        storage.delete_notebook(nb.id)
        assert not (tmp_path / nb.id).exists()
        assert (tmp_path / ".trash" / nb.id).is_dir()

    def test_trash_notebook_json_has_deleted_at(self, tmp_path):
        nb = storage.create_notebook("Gone")
        storage.delete_notebook(nb.id)
        data = json.loads((tmp_path / ".trash" / nb.id / "notebook.json").read_text())
        assert data["deleted_at"] is not None

    def test_raises_not_found_for_unknown_id(self):
        with pytest.raises(storage.NotFoundError):
            storage.delete_notebook("does-not-exist")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class TestListPages:
    def test_empty_for_new_notebook(self):
        # A new notebook has only page_0 (the notebook canvas). list_pages must
        # not return it — the notebook canvas is not a user page.
        nb = storage.create_notebook("NB")
        assert storage.list_pages(nb.id) == []

    def test_returns_user_pages_only(self):
        # page_0 must never appear even when user pages exist alongside it.
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "Chapter 1")
        pages = storage.list_pages(nb.id)
        assert len(pages) == 1
        assert pages[0].id == meta.id
        assert pages[0].title == "Chapter 1"

    def test_raises_not_found_for_unknown_notebook(self):
        with pytest.raises(storage.NotFoundError):
            storage.list_pages("no-such-notebook")


class TestCreatePage:
    def test_returns_page_meta_with_title(self):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "Chapter 1")
        assert meta.title == "Chapter 1"
        assert meta.id

    def test_page_json_written(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P1")
        assert (tmp_path / nb.id / "pages" / f"{meta.id}.json").exists()

    def test_page_added_to_notebook_json(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P1")
        data = json.loads((tmp_path / nb.id / "notebook.json").read_text())
        page_ids = [p["id"] for p in data["pages"]]
        assert meta.id in page_ids

    def test_raises_not_found_for_unknown_notebook(self):
        with pytest.raises(storage.NotFoundError):
            storage.create_page("no-such-notebook", "P1")


class TestLoadSavePage:
    def test_round_trip(self):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, meta.id)
        page.items.append(TextItem(x=10, y=20, width=200, height=100, z_index=1, content="<p>hi</p>"))
        storage.save_page(nb.id, meta.id, page)
        loaded = storage.load_page(nb.id, meta.id)
        assert len(loaded.items) == 1
        assert loaded.items[0].content == "<p>hi</p>"

    def test_load_raises_not_found(self):
        nb = storage.create_notebook("NB")
        with pytest.raises(storage.NotFoundError):
            storage.load_page(nb.id, "no-such-page")

    def test_save_raises_not_found_for_unknown_page(self):
        nb = storage.create_notebook("NB")
        page = Page(id="ghost")
        with pytest.raises(storage.NotFoundError):
            storage.save_page(nb.id, "ghost", page)

    def test_view_state_persisted(self):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, meta.id)
        page.view_state = ViewState(pan_x=100.0, pan_y=-50.0, scale=1.5)
        storage.save_page(nb.id, meta.id, page)
        loaded = storage.load_page(nb.id, meta.id)
        assert loaded.view_state.pan_x == 100.0
        assert loaded.view_state.scale == 1.5


class TestDeletePage:
    def test_moves_page_to_trash(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P1")
        storage.delete_page(nb.id, meta.id)
        assert not (tmp_path / nb.id / "pages" / f"{meta.id}.json").exists()
        assert (tmp_path / ".trash" / "pages" / f"{meta.id}.json").exists()

    def test_trashed_page_has_metadata(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "MyPage")
        storage.delete_page(nb.id, meta.id)
        data = json.loads((tmp_path / ".trash" / "pages" / f"{meta.id}.json").read_text())
        assert data["deleted_at"] is not None
        assert data["notebook_id"] == nb.id
        assert data["title"] == "MyPage"

    def test_removed_from_notebook_pages_list(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "P1")
        storage.delete_page(nb.id, meta.id)
        data = json.loads((tmp_path / nb.id / "notebook.json").read_text())
        page_ids = [p["id"] for p in data["pages"]]
        assert meta.id not in page_ids

    def test_raises_not_found_for_unknown_page(self):
        nb = storage.create_notebook("NB")
        with pytest.raises(storage.NotFoundError):
            storage.delete_page(nb.id, "no-such-page")


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class TestImages:
    def test_save_and_load_round_trip(self):
        nb = storage.create_notebook("NB")
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        image_id = storage.save_image(nb.id, data)
        assert storage.load_image(nb.id, image_id) == data

    def test_save_returns_uuid_string(self):
        nb = storage.create_notebook("NB")
        image_id = storage.save_image(nb.id, b"fake-png")
        import uuid
        uuid.UUID(image_id)  # Raises if not valid UUID.

    def test_load_raises_not_found_for_unknown_image(self):
        nb = storage.create_notebook("NB")
        with pytest.raises(storage.NotFoundError):
            storage.load_image(nb.id, "no-such-image")

    def test_save_raises_not_found_for_unknown_notebook(self):
        with pytest.raises(storage.NotFoundError):
            storage.save_image("no-such-notebook", b"data")


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

class TestTrash:
    def test_list_deleted_notebook(self):
        nb = storage.create_notebook("Deleted NB")
        storage.delete_notebook(nb.id)
        items = storage.list_trash()
        assert any(i.id == nb.id and i.type == "notebook" for i in items)

    def test_list_deleted_page(self):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "Deleted Page")
        storage.delete_page(nb.id, meta.id)
        items = storage.list_trash()
        assert any(i.id == meta.id and i.type == "page" for i in items)

    def test_list_soft_deleted_note(self):
        from datetime import datetime, timezone
        nb = storage.create_notebook("NB")
        p_meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, p_meta.id)
        item = TextItem(x=0, y=0, width=100, height=50, z_index=1, content="<p>gone</p>",
                        deleted_at=datetime.now(timezone.utc).isoformat())
        page.items.append(item)
        storage.save_page(nb.id, p_meta.id, page)
        items = storage.list_trash()
        assert any(i.id == item.id and i.type == "note" for i in items)

    def test_restore_notebook(self):
        nb = storage.create_notebook("Restore Me")
        storage.delete_notebook(nb.id)
        storage.restore_trash_item(nb.id, "notebook")
        nbs = storage.list_notebooks()
        assert any(n.id == nb.id for n in nbs)

    def test_restore_page(self):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "Restore Page")
        storage.delete_page(nb.id, meta.id)
        storage.restore_trash_item(meta.id, "page")
        # Page should be back in the notebook's pages list.
        nbs = storage.list_notebooks()
        nb_restored = next(n for n in nbs if n.id == nb.id)
        assert any(p.id == meta.id for p in nb_restored.pages)

    def test_restore_note(self):
        from datetime import datetime, timezone
        nb = storage.create_notebook("NB")
        p_meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, p_meta.id)
        item = TextItem(x=0, y=0, width=100, height=50, z_index=1, content="<p>note</p>",
                        deleted_at=datetime.now(timezone.utc).isoformat())
        page.items.append(item)
        storage.save_page(nb.id, p_meta.id, page)
        storage.restore_trash_item(item.id, "note")
        restored_page = storage.load_page(nb.id, p_meta.id)
        restored_item = next(i for i in restored_page.items if i.id == item.id)
        assert restored_item.deleted_at is None

    def test_purge_notebook(self, tmp_path):
        nb = storage.create_notebook("Purge Me")
        storage.delete_notebook(nb.id)
        storage.purge_trash_item(nb.id, "notebook")
        assert not (tmp_path / ".trash" / nb.id).exists()

    def test_purge_page(self, tmp_path):
        nb = storage.create_notebook("NB")
        meta = storage.create_page(nb.id, "Purge Page")
        storage.delete_page(nb.id, meta.id)
        storage.purge_trash_item(meta.id, "page")
        assert not (tmp_path / ".trash" / "pages" / f"{meta.id}.json").exists()

    def test_purge_note_removes_from_page(self):
        from datetime import datetime, timezone
        nb = storage.create_notebook("NB")
        p_meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, p_meta.id)
        item = TextItem(x=0, y=0, width=100, height=50, z_index=1, content="<p>gone</p>",
                        deleted_at=datetime.now(timezone.utc).isoformat())
        page.items.append(item)
        storage.save_page(nb.id, p_meta.id, page)
        storage.purge_trash_item(item.id, "note")
        final_page = storage.load_page(nb.id, p_meta.id)
        assert not any(i.id == item.id for i in final_page.items)

    def test_purge_note_deletes_referenced_images(self, tmp_path):
        nb = storage.create_notebook("NB")
        img_data = b"\x89PNG" + b"\x00" * 20
        image_id = storage.save_image(nb.id, img_data)
        p_meta = storage.create_page(nb.id, "P")
        page = storage.load_page(nb.id, p_meta.id)
        from datetime import datetime, timezone
        html = f'<img src="/api/notebooks/{nb.id}/images/{image_id}">'
        item = TextItem(x=0, y=0, width=100, height=50, z_index=1, content=html,
                        deleted_at=datetime.now(timezone.utc).isoformat())
        page.items.append(item)
        storage.save_page(nb.id, p_meta.id, page)
        storage.purge_trash_item(item.id, "note")
        assert not (tmp_path / nb.id / "images" / f"{image_id}.png").exists()


class TestPurgeExpiredTrash:
    def test_purges_items_older_than_60_days(self, tmp_path):
        nb = storage.create_notebook("Old NB")
        storage.delete_notebook(nb.id)
        # Backdate the deleted_at timestamp to 61 days ago.
        nb_json = tmp_path / ".trash" / nb.id / "notebook.json"
        data = json.loads(nb_json.read_text())
        old_date = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat()
        data["deleted_at"] = old_date
        nb_json.write_text(json.dumps(data))
        storage.purge_expired_trash()
        assert not (tmp_path / ".trash" / nb.id).exists()

    def test_preserves_recent_items(self, tmp_path):
        nb = storage.create_notebook("New NB")
        storage.delete_notebook(nb.id)
        storage.purge_expired_trash()
        assert (tmp_path / ".trash" / nb.id).exists()
