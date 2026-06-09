# Phase 1 Implementation Report — Project Scaffolding

Date: 2026-06-09

## What was done

### 1. Backend package skeleton

Created the following empty packages as specified in the plan:

```
backend/__init__.py
backend/api/__init__.py
backend/storage/__init__.py
```

Each file contains only a module-level docstring. No logic was added — this is scaffolding only, per the phase 1 spec.

### 2. Frontend — Vite + React + TypeScript

Ran `npm create vite@latest frontend -- --template react-ts` from the project root. This created the `frontend/` directory with the standard Vite scaffold (vite.config.ts, tsconfig.json, index.html, src/main.tsx, etc.).

Then installed the required dependencies from the plan:

```
npm install @tiptap/react @tiptap/starter-kit @tiptap/pm zustand
```

All deps landed in `frontend/package.json` as production dependencies.

Actual versions installed (not specified in the plan — latest at time of install):
- `@tiptap/react`: ^3.26.0
- `@tiptap/starter-kit`: ^3.26.0
- `@tiptap/pm`: ^3.26.0
- `zustand`: ^5.0.14
- `react`: ^19.2.6
- `vite`: ^8.0.12
- `typescript`: ~6.0.2

### 3. Stub main.py

Created `main.py` at the project root with a single `print("hello")` as specified.

### 4. Build verification

`cd frontend && npm run build` completed successfully. Output:

```
dist/index.html                   0.45 kB
dist/assets/index-DfKp6xNp.js   193.35 kB (gzip: 60.67 kB)
dist/assets/index-D64VDMd1.css    4.10 kB
```

TypeScript compilation (`tsc -b`) also passed clean — no type errors.

---

## Divergences from the plan

### 1. `tiptap` package name does not exist

The plan lists `tiptap` as one of the packages to install:
> Install: `tiptap`, `@tiptap/react`, `@tiptap/starter-kit`, `zustand`

There is no npm package named `tiptap` (bare, without scope). TipTap v2+ is distributed
exclusively as scoped packages. The correct peer dependency for the React integration is
`@tiptap/pm` (ProseMirror bindings). Installing `@tiptap/react` and `@tiptap/starter-kit`
already pulls in everything needed. `@tiptap/pm` was added explicitly to satisfy peer dependency
warnings. The bare `tiptap` package was **not installed** — it does not exist and would have failed.

### 2. TipTap version: v3 (not v2)

At the time of install, `@tpit/react` resolved to **v3.26.0**. The plan was written against
TipTap v2. The React API surface is the same for our use case (the `useEditor` hook, `<EditorContent>`,
`StarterKit` extension), but the package structure changed slightly in v3. No issues were observed
during the build. Phase 5 (Editor.tsx) will need to use v3 import paths if they differ — to be verified
when Editor.tsx is implemented.

### 3. `.gitignore` — frontend/dist and node_modules

The existing `.gitignore` was not modified. It should already exclude `node_modules/` and `dist/`
but this was not audited during phase 1. Should be confirmed before the first commit that includes
the frontend scaffold.

---

## Files created

```
main.py
backend/__init__.py
backend/api/__init__.py
backend/storage/__init__.py
frontend/               (Vite scaffold — full contents)
frontend/package.json   (with tiptap + zustand deps)
frontend/dist/          (build artifact — should be gitignored)
```
