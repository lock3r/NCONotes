# NCONotes

No Cognitive Overflow Notes — a minimalistic and unstructured note-taking application.

Notes live on an infinite canvas rather than in a document. A notebook is a canvas
with pages; a page is a canvas of freely placed text and image items.

## Architecture

- **Backend** — FastAPI, serving a local HTTP API on a random free port
  (`src/backend/`). Storage is plain JSON files on disk, no database.
- **Frontend** — React + TypeScript + Vite, with TipTap for rich text
  (`src/frontend/`).
- **Desktop shell** — pywebview, hosting the built frontend in the platform's
  native webview (`src/main.py`).

Every API call is authenticated with a token generated at startup, so the local
server is not usable by other processes on the machine.

## Storage

Notebooks are written to `~/MyNotebooks/` by default. Set `NCONOTES_STORAGE_ROOT`
to use a different directory.

Deletion is soft everywhere: deleted notebooks, pages and notes go to trash and are
purged automatically 60 days later.

## Setup

Python dependencies are managed with Poetry, installed inside the virtualenv:

```
source ~/.virtualenvs/NCONotes/bin/activate
poetry install
```

Frontend dependencies:

```
cd src/frontend && npm install
```

## Running the desktop app

```
source ~/.virtualenvs/NCONotes/bin/activate
nconotes
```

This serves the pre-built frontend from `src/frontend/dist/`, so after changing
frontend code you need to rebuild:

```
cd src/frontend && npm run build
```

## Running in development

The backend and the Vite dev server run as two separate processes. In one terminal:

```
source ~/.virtualenvs/NCONotes/bin/activate
python src/devserver.py
```

In another:

```
cd src/frontend && npm run dev
```

Then open http://localhost:5173. The backend writes its randomly chosen port and
token to `src/frontend/.nconotes-dev.json`, which the Vite proxy reads on every
request; the file exists only while `devserver.py` is running.

## Tests

```
source ~/.virtualenvs/NCONotes/bin/activate
python -m pytest
```

Tests run against real storage in a temporary directory — there are no mocks.

Frontend checks:

```
cd src/frontend
npx tsc -b --noEmit
npm run lint
```

## TODO

- make EVERYTHING semantically searchable
- add doc/notes upload from structured files (e.g. pdfs, md, docx) with the ability
  to link to notes or projects or both (same doc linked to different projects would
  be huge)
- add possibility to tag stuff
