# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communicating with Claude Code

Always respond to the developer in **Spanish**, regardless of the language of his message.
This is about chat responses only — it does not change the "Conventions" section below
(code, branch names and commit messages stay in English).

## Project

**This repository is a GitHub template**, not an application. It carries the infrastructure
a new project would otherwise rebuild from scratch, and deliberately carries no domain: no
business models, no endpoints beyond `/health`, no tables.

Monorepo: `backend/` (FastAPI + SQLAlchemy + Alembic) and `frontend/` (React + Vite +
TypeScript). Backend deploys to Render, frontend to Vercel, database is Neon Postgres.

`backend/` is complete and green: settings, database wiring, security headers, Sentry with
PII scrubbing, Alembic with an empty baseline migration, a test suite isolated from the
environment, and CI covering lint, types, tests, migrations, the Docker build, secret
scanning, dependency audit and CodeQL. `frontend/` is an empty placeholder — its four CI
jobs exist but stay skipped until `frontend/package.json` does.

**`TEMPLATE.md` is the checklist for anyone starting a project from this repo.** Keep it up
to date whenever the infrastructure changes — a renamed service, a new required status
check, a new environment variable. It is the kind of document that rots silently, because
nothing fails when it goes stale.

The placeholder name is `myapp` (`myapp-backend`, the `myapp` database, `MyApp API`). It is
deliberately not `app`: that is the Python package name and appears throughout every import,
so a search-and-replace on it would be destructive.

## Commands you must NOT run

The developer runs these himself. Write the code and the files, then stop and tell him
what to run — never execute them yourself:

- `git add`, `git commit`, `git push`, `git merge`, `git rebase`, `git reset`
- **Any `alembic` command**, including `revision`, `revision --autogenerate`, `upgrade`
  and `downgrade`. Do not create or edit migration files under `alembic/versions/` either
  — the developer generates and reviews every migration himself.
- Any command that deploys, or that writes to a remote database

You may read git state (`git status`, `git diff`, `git log`).

When a change requires a migration, say so explicitly and describe what the migration
should contain — then stop.

## Backend commands

Run from `backend/`:

Dependencies are managed with **uv**, and `uv.lock` is committed — it pins every
transitive dependency, so local, CI and the Docker image all install identical versions.
Install uv with `brew install uv` (or `pip install uv` inside the venv).

```bash
uv sync --extra dev             # create/update .venv from uv.lock (exact versions)
uv run uvicorn app.main:app --reload   # dev server: http://localhost:8000, docs at /docs
uv run ruff check .             # lint
uv run ruff format .            # format
uv run mypy app                 # type check (strict mode)
uv run pytest                   # tests (needs Postgres: docker compose up -d postgres)
uv run pytest -m "not db"       # the subset that needs no database
uv run pip-audit                # audit locked deps against the PyPI advisory database
```

Changing dependencies — always commit the resulting `uv.lock` in the same PR:

```bash
uv add <package>                # add a runtime dependency (updates pyproject + lock)
uv add --optional dev <package> # add a dev dependency
uv lock --upgrade               # refresh every pin to the latest allowed version
```

Note that `uv sync` makes the venv match the lock exactly, so it removes anything not
in it. CI and Docker use `uv sync --frozen`, which fails instead of re-resolving when
`uv.lock` is out of sync with `pyproject.toml`.

## Frontend commands

Run from `frontend/` once the scaffold exists:

```bash
npm install
cp .env.example .env
npm run dev
```

## Docker / local environment

```bash
docker compose up --build       # from repo root: backend + local postgres together
docker build -t myapp-backend ./backend   # backend image alone
```

Local Postgres credentials in `docker-compose.yml` (`postgres`/`postgres`/`myapp`)
are fixed dev-only values, not secrets — they never touch real data and don't apply to
Neon (staging/production).

## Architecture

- **Settings**: `app/core/config.py` — a `pydantic-settings` `Settings` class, cached via
  `get_settings()` (`lru_cache`), reads `.env`. Add new env-driven config here. Which file
  it reads comes from `ENV_FILE` (default `.env`); setting it to an empty string means
  "read no file", which is how the test suite opts out — see the Testing bullet below.
  `ENV_FILE` is deliberately **not** in `.env.example`: it is the variable that chooses
  that file.
- **Database**: `app/core/db.py` holds the SQLAlchemy `engine` (built from
  `settings.database_url`, driver forced to `postgresql+psycopg` via `URL.set()`, with
  `pool_pre_ping=True` since Neon suspends idle compute), the `SessionLocal` session
  factory, and the `get_db()` generator dependency for use with FastAPI's `Depends()`.
  `app/main.py` registers a `lifespan` context manager that calls `check_db_connection()`
  (`app/core/db.py`) — `engine.connect()` + `SELECT 1`, no ORM session — at startup, and
  fails fast (raises) if the DB is unreachable.
- **Routing**: routers live under `app/api/` (e.g. `health.py`) and are registered on the
  `FastAPI` app in `main.py` via `app.include_router(...)`.
- **Security headers**: `app/core/security_headers.py` holds `SecurityHeadersMiddleware`, a
  pure ASGI middleware (not `BaseHTTPMiddleware`) that stamps `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` and a CSP onto every response.
  The CSP is `default-src 'none'` everywhere — this API only returns JSON — except on
  `/docs`, `/docs/oauth2-redirect` and `/redoc`, which get a relaxed policy so Swagger UI
  and ReDoc still load their CDN assets. `Strict-Transport-Security` is sent whenever
  `environment != "local"`: Render terminates TLS and speaks HTTP to the container, so the
  request scheme cannot be used to decide, and sending HSTS over `http://localhost` would
  poison the browser's HSTS cache for every other local project. It is registered **last**
  in `main.py`, which makes it the outermost middleware, so CORS preflight responses —
  which `CORSMiddleware` answers without reaching the router — carry the headers too.
- **Models**: `app/models/base.py` holds `Base`, whose `MetaData` carries a
  `NAMING_CONVENTION` so every index and constraint gets a deterministic name. This is
  what makes `alembic check` trustworthy: left to itself Postgres names constraints
  differently from what SQLAlchemy would emit, and the job reports drift that is not
  there. It ships already set because it can only be settled while the schema is empty —
  adding it later means renaming live constraints. The `ck` pattern deliberately forces
  every `CheckConstraint` to carry `name=`, so a violation reports `ck_<table>_<name>`;
  an unnamed one fails when you generate the migration, locally rather than in
  production. `app/models/mixins.py` has `TimestampMixin` (`created_at` / `updated_at`,
  filled by the database so rows written outside the ORM are stamped too). Every model
  must be imported in `app/models/__init__.py`: autogenerate only sees imported tables,
  so one missing from there yields an *empty* migration without complaining.
  `app/schemas/` is still empty scaffolding for Pydantic schemas.
- **Testing**: `backend/tests/conftest.py` isolates the suite from the environment before
  anything imports `app.*` — it empties `ENV_FILE`, defaults `DATABASE_URL` to the
  docker-compose Postgres (via `setdefault`, so CI's own value still wins), pins
  `CORS_ORIGINS` to `TEST_CORS_ORIGIN`, and forces `SENTRY_DSN` empty so a test run can
  never reach the real Sentry project. The ordering is load-bearing: `app/core/db.py` and
  `app/main.py` call `get_settings()` at import time and `lru_cache` freezes the result,
  so no fixture can correct it afterwards — which is why nothing in `conftest.py` imports
  `app.*` at module level. Without it, `uv run pytest` picks up `backend/.env` and runs
  against the Neon dev branch. Fixtures: `db_session` (a session inside a transaction that
  is rolled back afterwards, so even a `commit()` in the test is undone, and which starts
  by emptying every model table — the rollback undoes what the *test* writes, this undoes
  what was committed before pytest even started, so poking at the dev database by hand
  cannot quietly break the suite while CI stays green on its fresh Postgres),
  `client`/`running_client` (the real app without/with its lifespan, i.e. without/with a
  database connection) and `clean_env`. Tests needing a live database carry
  `@pytest.mark.db`, and a guard fails them with one readable sentence naming the host and
  database when the schema has not been migrated, instead of a page of `UndefinedTable`.
  Note `alembic/env.py` still reads `.env` on purpose: you do want
  `alembic upgrade head` to migrate the database you have configured — which is also why
  the `pytest` CI job runs its own `alembic upgrade head`. Jobs do not share service
  containers, so the schema built by the `migrations` job is gone by the time it starts.
- **Docker build**: `backend/Dockerfile` is a two-stage build — `builder` installs the
  locked dependencies into a venv at `/opt/venv` (via `uv sync --frozen
  --no-install-project`, so only `pyproject.toml` + `uv.lock` are copied and dependency
  installs aren't invalidated by every code change); `runtime` copies that venv plus the
  `app/` source straight from the build context. The project itself is deliberately never
  installed as a package — `app` is importable because it sits in the working directory.
  Runs as a non-root user, and honors `$PORT` (falling back to 8000) for Render, whose CMD
  uses shell form so the env var expands.
- **Pinning**: both stages pin `python:3.13-slim` by digest, and the uv binary comes from
  a digest-pinned `ghcr.io/astral-sh/uv` image — same reasoning as pinning GitHub Actions
  by SHA. Dependabot (`.github/dependabot.yml`) keeps the lockfile, the image digests and
  the action SHAs up to date.
- `docker-compose.yml` (repo root) wires `backend` + `postgres` together for local dev
  only — production uses Render + Neon instead, not this compose file.

## Conventions

- Code, branch names and commit messages in **English**. UI text and emails in **Spanish**.
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:` — keep
  commit messages to a single line.
- Type hints everywhere in Python. Strict TypeScript in the frontend.

## Git workflow

- Trunk-based. `main` is protected — direct pushes are rejected by GitHub.
- Branches: `feature/<name>`, `fix/<name>`, `chore/<name>`, branched off `main`.
- All changes go through a PR. Squash merge only.

## Architecture decisions

Do not propose or add infrastructure beyond this without being asked:

- **No** Redis, message broker, Kubernetes, service workers, or microservices.
- Migrations with Alembic, applied on deploy — never at application startup.
- All timestamps stored in **UTC**; convert at the boundary.
- Backend runs on Render free tier — cold start (~40s) is handled in the UI, not by paying.

## Security

This is a **public repository**.

- Never commit secrets. All configuration through environment variables.
  `.env` is gitignored; `.env.example` is committed with placeholder values.
- Secret scanning: `gitleaks` runs on every PR (`.github/workflows/secret-scan.yml`) over
  the **full** git history, so a secret that ever landed keeps failing CI until it is
  purged from history — not just removed in a later commit. It runs the MIT CLI from a
  digest-pinned image instead of `gitleaks-action`, which requires a paid licence for
  org-owned repositories. Dependabot does not track that digest; bump it by hand.
- SAST: CodeQL analyses the Python source on every PR, on pushes to `main` and weekly
  (`.github/workflows/codeql.yml`), publishing to the Security tab. Deliberately the
  *advanced* setup — a committed workflow — and not the one-click default setup, which
  lives in repository settings and so would not be inherited by an app generated from
  this template. Never enable both: they conflict.
- Dependency scanning: `pip-audit` gates every backend PR and `npm audit
  --audit-level=high` every frontend PR. Dependabot proposes the upgrades; these jobs
  are what stop an advisory from being ignored while that weekly cadence catches up.
  The npm one is dormant until `frontend/package.json` exists — see the `changes` guard
  in `frontend-ci.yml`.
- CORS: explicit origin allow-list per environment. Never `*` combined with credentials.
  `Settings.cors_origins` defaults to an empty list, so an environment that forgets
  `CORS_ORIGINS` allows nothing instead of falling back to a developer's localhost.
  Local setups declare it in `.env` / `docker-compose.yml`.
- Sentry: `send_default_pii=False`, plus a `before_send` hook — `scrub_event` in
  `app/core/observability.py` — that walks the whole event redacting values under
  sensitive key names and any email or Spanish phone number found in free text.
  `send_default_pii=False` only stops Sentry from collecting PII itself; it does nothing
  about PII the app hands it in a log message or a captured local variable, which is
  where it realistically leaks. Events are always scrubbed, never dropped.
- Rate limiting on public endpoints. **Not implemented yet** — it needs a real public
  endpoint to be worth anything. See the known gaps in `TEMPLATE.md`.
- Security headers: HSTS, X-Content-Type-Options, X-Frame-Options, basic CSP.

## Stack constraints

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL. Ruff for lint and format, mypy for
  types, uv for dependency management (`uv.lock` is committed).
- Frontend: React + Vite + TypeScript, Zustand (global state), TanStack Query (server state).
- Tests: pytest (backend), Vitest (frontend). Business logic tests are written alongside
  the logic, not deferred to a later phase.
