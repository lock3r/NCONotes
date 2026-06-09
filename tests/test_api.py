# Integration tests for the FastAPI REST API.
# Uses TestClient with a real storage layer pointing at a temp directory.

import pytest
from fastapi.testclient import TestClient

from backend.server import _build_app

_TOKEN = "test-token-abc123"
_HEADER = {"X-NCONotes-Token": _TOKEN}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NCONOTES_STORAGE_ROOT", str(tmp_path))
    app = _build_app(_TOKEN)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Auth middleware (already tested in Phase 2 smoke tests, but keep it)
# ---------------------------------------------------------------------------

def test_health_no_token(client):
    assert client.get("/health").status_code == 200


def test_api_without_token_returns_401(client):
    assert client.get("/api/notebooks").status_code == 401


def test_api_with_wrong_token_returns_401(client):
    r = client.get("/api/notebooks", headers={"X-NCONotes-Token": "wrong"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------

class TestNotebooksAPI:
    def test_list_empty(self, client):
        r = client.get("/api/notebooks", headers=_HEADER)
        assert r.status_code == 200
        assert r.json() == []

    def test_create_and_list(self, client):
        r = client.post("/api/notebooks", json={"name": "Work"}, headers=_HEADER)
        assert r.status_code == 201
        nb = r.json()
        assert nb["name"] == "Work"
        assert nb["id"]

        r2 = client.get("/api/notebooks", headers=_HEADER)
        assert any(n["id"] == nb["id"] for n in r2.json())

    def test_delete_notebook(self, client):
        nb = client.post("/api/notebooks", json={"name": "Del"}, headers=_HEADER).json()
        r = client.delete(f"/api/notebooks/{nb['id']}", headers=_HEADER)
        assert r.status_code == 204
        remaining = client.get("/api/notebooks", headers=_HEADER).json()
        assert not any(n["id"] == nb["id"] for n in remaining)

    def test_delete_unknown_notebook_returns_404(self, client):
        r = client.delete("/api/notebooks/no-such-id", headers=_HEADER)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class TestPagesAPI:
    def _make_notebook(self, client):
        return client.post("/api/notebooks", json={"name": "NB"}, headers=_HEADER).json()

    def test_list_pages_excludes_notebook_canvas(self, client):
        # A freshly created notebook has only page_0 (the notebook canvas).
        # The pages endpoint must not expose it — it is accessed by selecting
        # the notebook itself, not by navigating the page list.
        nb = self._make_notebook(client)
        r = client.get(f"/api/notebooks/{nb['id']}/pages", headers=_HEADER)
        assert r.status_code == 200
        assert r.json() == []

    def test_create_page(self, client):
        nb = self._make_notebook(client)
        r = client.post(f"/api/notebooks/{nb['id']}/pages", json={"title": "Chapter 1"}, headers=_HEADER)
        assert r.status_code == 201
        assert r.json()["title"] == "Chapter 1"

    def test_delete_page(self, client):
        nb = self._make_notebook(client)
        page = client.post(f"/api/notebooks/{nb['id']}/pages", json={"title": "P"}, headers=_HEADER).json()
        r = client.delete(f"/api/notebooks/{nb['id']}/pages/{page['id']}", headers=_HEADER)
        assert r.status_code == 204

    def test_load_page_returns_page_structure(self, client):
        nb = self._make_notebook(client)
        meta = client.post(f"/api/notebooks/{nb['id']}/pages", json={"title": "P"}, headers=_HEADER).json()
        r = client.get(f"/api/notebooks/{nb['id']}/pages/{meta['id']}", headers=_HEADER)
        assert r.status_code == 200
        page = r.json()
        assert page["id"] == meta["id"]
        assert "items" in page
        assert "view_state" in page

    def test_save_and_load_page(self, client):
        nb = self._make_notebook(client)
        meta = client.post(f"/api/notebooks/{nb['id']}/pages", json={"title": "P"}, headers=_HEADER).json()
        page_data = {
            "id": meta["id"],
            "view_state": {"pan_x": 10.0, "pan_y": -5.0, "scale": 1.2},
            "items": [
                {
                    "type": "text",
                    "id": "item-1",
                    "x": 0, "y": 0, "width": 200, "height": 100,
                    "z_index": 1,
                    "content": "<p>hello</p>",
                    "deleted_at": None,
                }
            ],
        }
        r = client.put(f"/api/notebooks/{nb['id']}/pages/{meta['id']}", json=page_data, headers=_HEADER)
        assert r.status_code == 204

        loaded = client.get(f"/api/notebooks/{nb['id']}/pages/{meta['id']}", headers=_HEADER).json()
        assert loaded["view_state"]["scale"] == 1.2
        assert loaded["items"][0]["content"] == "<p>hello</p>"

    def test_load_unknown_page_returns_404(self, client):
        nb = self._make_notebook(client)
        r = client.get(f"/api/notebooks/{nb['id']}/pages/no-such-page", headers=_HEADER)
        assert r.status_code == 404

    def test_list_pages_unknown_notebook_returns_404(self, client):
        r = client.get("/api/notebooks/no-such-nb/pages", headers=_HEADER)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class TestImagesAPI:
    def _make_notebook(self, client):
        return client.post("/api/notebooks", json={"name": "NB"}, headers=_HEADER).json()

    def test_upload_and_retrieve_image(self, client):
        nb = self._make_notebook(client)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        r = client.post(
            f"/api/notebooks/{nb['id']}/images",
            files={"file": ("image.png", fake_png, "image/png")},
            headers=_HEADER,
        )
        assert r.status_code == 201
        body = r.json()
        assert "image_id" in body
        assert body["url"].startswith(f"/api/notebooks/{nb['id']}/images/")

        r2 = client.get(body["url"], headers=_HEADER)
        assert r2.status_code == 200
        assert r2.content == fake_png

    def test_get_unknown_image_returns_404(self, client):
        nb = self._make_notebook(client)
        r = client.get(f"/api/notebooks/{nb['id']}/images/no-such-id", headers=_HEADER)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

class TestTrashAPI:
    def _make_notebook(self, client):
        return client.post("/api/notebooks", json={"name": "NB"}, headers=_HEADER).json()

    def test_list_trash_empty(self, client):
        r = client.get("/api/trash", headers=_HEADER)
        assert r.status_code == 200
        assert r.json() == []

    def test_deleted_notebook_appears_in_trash(self, client):
        nb = self._make_notebook(client)
        client.delete(f"/api/notebooks/{nb['id']}", headers=_HEADER)
        trash = client.get("/api/trash", headers=_HEADER).json()
        assert any(i["id"] == nb["id"] and i["type"] == "notebook" for i in trash)

    def test_restore_notebook_from_trash(self, client):
        nb = self._make_notebook(client)
        client.delete(f"/api/notebooks/{nb['id']}", headers=_HEADER)
        r = client.post(f"/api/trash/{nb['id']}/restore?type=notebook", headers=_HEADER)
        assert r.status_code == 204
        nbs = client.get("/api/notebooks", headers=_HEADER).json()
        assert any(n["id"] == nb["id"] for n in nbs)

    def test_purge_notebook_from_trash(self, client):
        nb = self._make_notebook(client)
        client.delete(f"/api/notebooks/{nb['id']}", headers=_HEADER)
        r = client.delete(f"/api/trash/{nb['id']}?type=notebook", headers=_HEADER)
        assert r.status_code == 204
        trash = client.get("/api/trash", headers=_HEADER).json()
        assert not any(i["id"] == nb["id"] for i in trash)

    def test_restore_unknown_item_returns_404(self, client):
        r = client.post("/api/trash/no-such-id/restore?type=notebook", headers=_HEADER)
        assert r.status_code == 404
