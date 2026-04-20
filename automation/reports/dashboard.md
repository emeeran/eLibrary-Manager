# Production Readiness Dashboard

- Generated: 2026-04-18T23:01:15
- Project: /home/em/code/wip/dawstar-eBook
- Schema: 3.0.0
- Score: **55 / 100**  Grade: **D**
- Total findings: 12  Open: 12  Accepted: 0

## Gate Results

| Gate | Status | Findings | Duration (s) |
|---|---|---:|---:|
| gate-1 | SKIP | 0 | 0.0 |
| gate-2 | SKIP | 0 | 0.0 |
| gate-3 | WARN | 7 | 1411.5 |
| gate-4 | SKIP | 0 | 0.0 |

## Open Findings by Severity

| Blocker | High | Medium | Low |
|---:|---:|---:|---:|
| 0 | 3 | 6 | 3 |

## Open Findings

| ID | Severity | Domain | Source | Title | Status |
|---|---|---|---|---|---|
| F1 | high | audit | gemini | Missing React/Vite configuration. Stack relies on `frontend/ | open |
| F2 | medium | audit | gemini | `app.config.AppConfig.secret_key` has a hardcoded default `" | open |
| F3 | medium | audit | gemini | `CORS` middleware is not configured in `main.py`. | open |
| F4 | medium | audit | gemini | No `.github/workflows/` directory or equivalent CI pipelines | open |
| F5 | low | audit | gemini | Docker healthcheck calls `http://localhost:8000/api/health`. | open |
| 01 | high | audit | gemini | Missing `package.json`, `node_modules/`, or React/Vite code; | open |
| 02 | high | audit | gemini | `config.py` uses hardcoded `secret_key = "dawnstar-default-s | open |
| 03 | medium | audit | gemini | `security.py` derives Fernet key from the local database URL | open |
| 04 | medium | audit | gemini | No `CORSMiddleware` configured in `main.py`. | open |
| 05 | medium | audit | gemini | `.github/workflows/` directory is missing. No GitHub Actions | open |
| 06 | low | audit | gemini | Only 3 test files in `tests/` (`test_api.py`, `test_scanner. | open |
| 07 | low | audit | gemini | `Dockerfile` uses `HEALTHCHECK` with urllib, but lacks rollb | open |
