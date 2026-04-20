# Full Findings Report — Tech Lead

Date: 2026-04-18T23:01:15
Project: /home/em/code/wip/dawstar-eBook

## All Findings

| ID | Sev | Domain | Source | Title | Status | Auto-fix | First Seen |
|---|---|---|---|---|---|---|---|
| F1 | high | audit | gemini | Missing React/Vite configuration. Stack relies on  | open |  | 2026-04-18 |
| F2 | medium | audit | gemini | `app.config.AppConfig.secret_key` has a hardcoded  | open | Y | 2026-04-18 |
| F3 | medium | audit | gemini | `CORS` middleware is not configured in `main.py`. | open | Y | 2026-04-18 |
| F4 | medium | audit | gemini | No `.github/workflows/` directory or equivalent CI | open | Y | 2026-04-18 |
| F5 | low | audit | gemini | Docker healthcheck calls `http://localhost:8000/ap | open |  | 2026-04-18 |
| 01 | high | audit | gemini | Missing `package.json`, `node_modules/`, or React/ | open |  | 2026-04-18 |
| 02 | high | audit | gemini | `config.py` uses hardcoded `secret_key = "dawnstar | open | Y | 2026-04-18 |
| 03 | medium | audit | gemini | `security.py` derives Fernet key from the local da | open | Y | 2026-04-18 |
| 04 | medium | audit | gemini | No `CORSMiddleware` configured in `main.py`. | open | Y | 2026-04-18 |
| 05 | medium | audit | gemini | `.github/workflows/` directory is missing. No GitH | open | Y | 2026-04-18 |
| 06 | low | audit | gemini | Only 3 test files in `tests/` (`test_api.py`, `tes | open |  | 2026-04-18 |
| 07 | low | audit | gemini | `Dockerfile` uses `HEALTHCHECK` with urllib, but l | open |  | 2026-04-18 |
