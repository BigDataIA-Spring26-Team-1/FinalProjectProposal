# Work Split For 3 Contributors

## Current Repo State

- Local git history currently shows only one committed revision: `ebb29cd Initial commit`.
- No feature PR history is available from the local repository state.
- Most project work is still untracked locally, so the split below is based on the files that exist now.

## Recommended PR 1

- Owner: Contributor 1
- Branch: `feature/frontend-console`
- PR title: `Frontend digital twin console`
- Suggested commits:
  - `feat(frontend): build digital twin console UI`
  - `test(frontend): add frontend tooling and smoke coverage`

Files:

- `industrial-digital-twin/src/App.jsx`
- `industrial-digital-twin/src/styles.css`
- `industrial-digital-twin/src/main.jsx`
- `industrial-digital-twin/index.html`
- `industrial-digital-twin/vite.config.js`
- `industrial-digital-twin/package.json`
- `industrial-digital-twin/package-lock.json`
- `industrial-digital-twin/playwright.config.js`
- `industrial-digital-twin/tests/ui-smoke.spec.js`
- `industrial-digital-twin/.env.example`

## Recommended PR 2

- Owner: Contributor 2
- Branch: `feature/backend-live-sources`
- PR title: `Backend live source aggregation API`
- Suggested commits:
  - `feat(api): add FastAPI endpoints and response models`
  - `feat(sources): add source aggregation and settings`

Files:

- `backend_service/sources.py`
- `backend_service/main.py`
- `backend_service/config.py`
- `backend_service/models.py`
- `backend_service/__init__.py`
- `pyproject.toml`
- `poetry.lock`
- `.env.example`

## Recommended PR 3

- Owner: Contributor 3
- Branch: `feature/advisor-rag-integration`
- PR title: `Advisor, RAG, and integration layer`
- Suggested commits:
  - `feat(advisor): add chat and RAG services`
  - `feat(integration): add frontend API client and demo payloads`
  - `test(docs): add chat-context coverage and project documentation`

Files:

- `backend_service/chat.py`
- `backend_service/rag.py`
- `industrial-digital-twin/src/api.js`
- `industrial-digital-twin/src/data/demoData.js`
- `tests/test_chat_context.py`
- `README.md`
- `LICENSE`
- `.gitignore`

## Keep Out Of Commits And PRs

These are local-only, generated, or secret-bearing files and should not be divided as team ownership:

- `.env`
- `.rag_cache/`
- `backend_service/__pycache__/`
- `tests/__pycache__/`
- `industrial-digital-twin/node_modules/`
- `industrial-digital-twin/dist/`
- `industrial-digital-twin/test-results/`

## Notes

- This split avoids putting `backend_service/sources.py`, `backend_service/chat.py`, and `backend_service/rag.py` in the same PR, which keeps the backend work easier to review.
- `industrial-digital-twin/src/App.jsx` is large and should stay with one owner to avoid merge conflicts.
- `package-lock.json` and `poetry.lock` should be committed only with the PR that owns their related dependency changes.
