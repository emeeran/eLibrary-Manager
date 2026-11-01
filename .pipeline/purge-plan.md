# Phase 1 — Purge Plan (APPLIED 2026-11-01)

Generated 2026-11-01 from `.pipeline/inventory.csv` + content scans.
All moves executed via `git mv` into `trash2review/<same-path>`.

## Move candidates

| path | reason | confidence | inbound refs |
|---|---|---|---|
| `uploads/` (12 ebook files, ~90 MB) | User content committed to VCS. 0 of 220 DB book rows reference `uploads/`; the upload endpoint recreates the dir on demand (`library.py:517`). Books belong in the (untracked) `library/` dir. | high | 0 |
| `conductor/plan.md` | Completed one-off session plan ("Node 24 in CI"); the change it describes is already applied in `.github/workflows/ci.yml`. | high | 0 |
| `docs/calibre-web-elibrary.user.js` | Superseded by spec 013's server-side `/calibre/launch` endpoint; the userscript only matched a third-party demo host (`*.ashiknesin.com`). | medium | 0 |
| `scripts/setup_nas_mount.sh` | One-off ops script under the old "Dawnstar" branding; NAS setup is now in-app (spec 009). Decision-fork rule applied: parked, not deleted. | medium | 0 |

## Already parked (pre-existing, untracked — no action)

`trash2review/` already contained, from an earlier session: PRD documents,
`automation/`, `automation-reports/`, `icecream UI/`, `readiness.md`. These
stay untracked in the pen for human review.

## Explicitly NOT moving (false positives / load-bearing)

- `alembic/versions/*` (10 files flagged zero-ref) — referenced through the
  alembic revision chain, not by name. Load-bearing.
- `packaging/deb/build-deb.sh`, `run-dev.sh`, `start.sh` — launchers.
- `docker-compose.yml` + `Dockerfile` — valid, referenced pair.
- `backups/`, `local/` — untracked local data (DB snapshots, session notes,
  APK); never tracked, nothing to move.
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` — referenced
  project documentation (staleness is a Phase 4 audit question, not a purge).

## Accompanying change (required by the uploads move)

`.gitignore` gains `uploads/` — the upload endpoint recreates the dir at
runtime, and without the ignore the next upload would re-pollute the repo.
