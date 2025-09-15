# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: FastAPI app (routes: `/`, `/upload`, `/download/{fid}`, `/delete/{fid}`).
- `resources/`: Stored file blobs (created at startup).
- `mapping.json`: ID→original filename map, saved on shutdown.
- `add_manually.py`: Helper to add a file to `resources/` and update `mapping.json`.

## Build, Test, and Development Commands
- Create venv and install deps: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.
- Run API (auto-reload): `uvicorn main:app --reload`.
- Quick endpoint checks:
  - List page: `open http://127.0.0.1:8000` (or use a browser).
  - Upload via curl: `curl -F file=@/path/to/file http://127.0.0.1:8000/upload`.
  - Download: `curl -OJ http://127.0.0.1:8000/download/<fid>`.
  - Delete: `curl -X DELETE http://127.0.0.1:8000/delete/<fid>`.

## Coding Style & Naming Conventions
- Python 3.10+, 4‑space indentation, PEP 8, prefer type hints.
- Function and module names: `snake_case`; constants: `UPPER_SNAKE_CASE`.
- Keep handlers small; isolate filesystem ops under clear helpers when adding features.
- Optional format/lint: `pip install black ruff` then `black . && ruff check .`.

## Testing Guidelines
- No formal suite yet. Add `pytest` tests under `tests/` mirroring route names, e.g., `tests/test_upload.py`.
- Use `httpx.AsyncClient` to exercise endpoints; include edge cases (missing fid, large files, orphan cleanup).
- Target coverage: aim for critical paths (>80% of `main.py`). Run with: `pytest -q`.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject; body explains why, not just what. Example: "Handle missing file in delete route; return 404 JSON".
- PRs: clear description, steps to test, screenshots of UI where relevant, link issues, note breaking changes/migrations.
- Keep changes focused; include small updates to `README.md` when user-visible behavior changes.

## Security & Operations Tips
- Ensure `resources/` is writable; avoid storing secrets in repo.
- Validate filenames and sizes; never trust client input. Consider limits and content-type checks when extending.
- Back up `mapping.json` if running in production; handle concurrent writes via the existing lock.
