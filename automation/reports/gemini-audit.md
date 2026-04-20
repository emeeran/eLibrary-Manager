As I am currently operating in **Plan Mode**, I am restricted from creating or modifying files outside of the `conductor/` directory. However, I have completed the requested audit. Here is the evidence-based production-readiness report based on my analysis of the repository:

```markdown
# Gemini CLI Audit Prompt

## 1. Executive status
The Dawnstar eBook Manager repository has a well-structured Python backend using FastAPI with comprehensive AI integration. However, there is a **critical mismatch** between the project's assumed stack (FastAPI + React/Vite) and its actual implementation. The frontend is not built with React or Vite; it utilizes server-side rendered HTML via Jinja2 templates, served directly by FastAPI alongside vanilla JavaScript and CSS assets. Overall, the backend demonstrates solid foundations (Pydantic settings, health checks, multi-stage Docker builds), while CI/CD and production security need enhancements before a public release.

## 2. Stack map
- **Backend Framework**: FastAPI (v0.104+) + Uvicorn
- **Language**: Python 3.12+ (managed via `uv`)
- **Database**: SQLite (via `aiosqlite` and SQLAlchemy 2.0)
- **Frontend**: Jinja2 Templates, HTML, Vanilla CSS/JS (No React/Vite present)
- **AI Integrations**: Google GenAI, Groq, Ollama (Local and Cloud)
- **Deployment**: Docker Compose, Multi-stage Dockerfile
- **Tooling**: Pytest, Ruff, Black, Mypy, pre-commit

## 3. Findings table

| ID | Layer | Severity | Evidence | Impact | Recommended fix | Auto-fixable | Verify |
|---|---|---|---|---|---|---|---|
| 01 | Frontend | High | Missing `package.json`, `node_modules/`, or React/Vite code; `frontend/` contains only Jinja2 templates and vanilla JS/CSS. | Modern SPA assumptions and Vite build pipelines will fail. | Align development strategy: Either migrate `frontend/` to a separate React/Vite project or update documentation to reflect Jinja2 usage. | No | Check `package.json` |
| 02 | Security | High | `config.py` uses hardcoded `secret_key = "dawnstar-default-secret-key-change-in-production"`. | Predictable secret keys can lead to session hijacking or predictable encryption. | Enforce `secret_key` via `.env` without a default, or raise an error if untouched in production. | Yes | Check `config.py` |
| 03 | Security | Medium | `security.py` derives Fernet key from the local database URL (`config.database_url`). | If the DB path is known or standard (`sqlite+aiosqlite:///./dawnstar_data/dawnstar.db`), the encryption key can be derived. | Derive Fernet key using `config.secret_key` and a secure salt instead. | Yes | Check `security.py` |
| 04 | Integration | Medium | No `CORSMiddleware` configured in `main.py`. | If frontend is eventually split to React/Vite on a different origin (e.g., port 5173), API requests will be blocked. | Add `CORSMiddleware` in `main.py` allowing localhost development origins. | Yes | Check `main.py` |
| 05 | CI/CD | Medium | `.github/workflows/` directory is missing. No GitHub Actions defined. | No automated linting, testing, or build verification on pull requests. | Create `.github/workflows/ci.yml` running `uv sync`, `pytest`, `ruff`, and `mypy`. | Yes | Check `.github/workflows/` |
| 06 | Backend | Low | Only 3 test files in `tests/` (`test_api.py`, `test_scanner.py`, `conftest.py`). | Insufficient coverage for core logic (AI features, DB migrations, reader engine). | Expand test suite for `services/`, `parsers/`, and `storage/`. | No | Run `pytest --cov` |
| 07 | Deployment | Low | `Dockerfile` uses `HEALTHCHECK` with urllib, but lacks rollback scripts or config examples besides `.env.example`. | Production deployments lack formal rollback notes or infrastructure-as-code deployment scripts. | Draft a deployment runbook and backup/rollback script. | No | Read runbook |

## 4. Top actions
1. **Resolve Stack Discrepancy**: Decide whether to continue with Jinja2 or initialize a new React/Vite project in `frontend/`. If React is chosen, scaffold it using `npm create vite@latest frontend --template react-ts`.
2. **Harden Security**: Update `security.py` to use `secret_key` for all encryption (not DB URL), and remove the hardcoded default `secret_key` for production environments.
3. **Establish CI/CD**: Add GitHub Actions workflows to automate `ruff` linting, `mypy` type-checking, and `pytest` execution on every push.
4. **Prepare CORS for SPA**: If moving to React/Vite, insert FastAPI `CORSMiddleware` to allow requests from the frontend development server.

## 5. Unknowns
- **Frontend Strategy**: It's unclear if the Jinja2 setup was an interim prototype or if the "React/Vite" specification was merely a misplaced architectural assumption.
- **NAS Authentication**: `config.py` accepts NAS passwords, but it's unclear how they are securely rotated or stored long-term (outside of `.env`).
- **Production Environment**: Target deployment architecture (e.g., AWS, local NAS, Raspberry Pi, generic VPS) is not explicitly defined in the docker configuration besides standard Docker Compose limits.
```

If you would like to proceed with addressing any of these action items (e.g., scaffolding a React/Vite app or hardening security), please let me know and we can draft an implementation plan!
