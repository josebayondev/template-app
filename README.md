# template-app

A GitHub template for FastAPI + PostgreSQL + React projects. Infrastructure only — it ships
no domain, so a new project starts from working CI, Docker, migrations, observability and
security instead of rebuilding them.

> **Starting a new project from this template?** Read [TEMPLATE.md](TEMPLATE.md) first — it
> lists what to rename, which services to create, and the GitHub settings a template does
> not carry over.

## What you get

- **Backend** — FastAPI with settings via `pydantic-settings`, SQLAlchemy + Alembic (empty
  baseline migration), `/health`, security headers middleware, and Sentry with
  `send_default_pii=False` plus a `before_send` hook that redacts PII from free text.
- **Tests** — pytest with a `conftest.py` that isolates the suite from `.env`, a
  transactional `db_session` fixture, and a `db` marker for the tests that need Postgres.
- **CI** — ruff, mypy (strict), pytest, migrations replayed from empty, Docker build,
  `pip-audit`, `npm audit`, gitleaks over the full history, and CodeQL. Actions pinned by
  SHA, base images pinned by digest, Dependabot keeping all of it current.
- **Local dev** — `docker-compose.yml` with Postgres and the backend wired together.

## Stack

| Layer     | Tech                                              |
| --------- | ------------------------------------------------- |
| Frontend  | React + Vite + TypeScript → Vercel                |
| Backend   | FastAPI + SQLAlchemy + Alembic, Docker → Render   |
| Database  | PostgreSQL (Neon)                                 |
| CI        | GitHub Actions                                    |
| Deps      | uv (`uv.lock`), Dependabot                        |
| Errors    | Sentry                                            |

## Structure

```
template-app/
├── backend/            FastAPI application
├── frontend/           React + Vite application
└── .github/workflows/  CI pipelines
```

## Getting started

### Backend

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

API docs available at `http://localhost:8000/docs`.

`uv.lock` is committed and pins every transitive dependency, so local, CI and the Docker
image install byte-identical versions. Use `uv add <package>` to add one and
`uv lock --upgrade` to refresh the pins — always commit the updated lockfile.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Local database + backend (Docker)

```bash
docker compose up -d
```

Starts Postgres and the backend together; the backend connects to Postgres on startup
and fails fast if it can't. Useful as an alternative to running `uvicorn --reload` directly
against the local Postgres started here.

## Database migrations

Migrations are managed with Alembic (`backend/alembic/`, configured in
`backend/app/core/db.py` and `backend/alembic/env.py`). Run these from `backend/`. The
migration file is committed and reviewed in the PR; it is applied automatically on
deploy, never at application startup.

```bash
uv run alembic revision --autogenerate -m "description"   # generate (always review the output)
uv run alembic upgrade head                                # apply
uv run alembic downgrade -1                                # roll back one revision
```

Test migrations against a staging database branch before they reach production.

## Branching

Trunk-based. `main` is always deployable.

- Branch off `main`: `git checkout -b feature/<name>`
- Open a PR against `main` — direct pushes are blocked
- CI must pass before merging
- Squash merge; the remote branch is deleted automatically
- Rebase onto `main` instead of merging it in, to keep history linear

Prefixes: `feature/`, `fix/`, `chore/`, `docs/`

## Conventions

- Code, branch names and commit messages in **English**
- User-facing UI and emails in **Spanish**
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- No secrets in the repository — all configuration through environment variables
| Production  | Vercel          | Render         | Neon (main) |