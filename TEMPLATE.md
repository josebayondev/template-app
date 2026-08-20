# Starting a new project from this template

This repository is infrastructure without a domain. Everything that cannot live in code —
names, credentials, external services, and the GitHub settings a template does not carry —
is listed here.

Work through it top to bottom, then **delete this file**. It is the last commit of the
setup, not part of the project.

---

## 1. Rename the project

The placeholder is `myapp`. Find every occurrence first:

```bash
grep -rn "myapp-backend\|myapp\|MyApp API" \
  --exclude-dir=.git --exclude-dir=.venv --exclude=uv.lock --exclude=TEMPLATE.md .
```

| String | Where | What it is |
| --- | --- | --- |
| `myapp-backend` | `backend/pyproject.toml`, `CLAUDE.md`, `.github/workflows/backend-ci.yml` | Python package name and Docker image tag |
| `MyApp API` | `backend/app/core/config.py`, `backend/.env.example` | `PROJECT_NAME`, the title FastAPI shows in `/docs` |
| `myapp` | `docker-compose.yml`, `backend/.env.example`, `backend/app/core/config.py`, `backend/tests/conftest.py`, `.github/workflows/backend-ci.yml` | Local and CI database name |

One pass does all of it (GNU sed; on macOS use `sed -i ''`):

```bash
grep -rl "myapp\|MyApp API" \
  --exclude-dir=.git --exclude-dir=.venv --exclude=uv.lock --exclude=TEMPLATE.md . \
| xargs sed -i \
  -e 's/MyApp API/<Your Project> API/g' \
  -e 's/myapp/<your_project>/g'
```

Order matters: replacing `myapp` first would also eat the `myapp` inside `myapp-backend`,
which is fine, but doing `MyApp API` first keeps the title readable.

> **Never search-and-replace `app`.** It is the Python package name and appears in every
> import (`from app.core.config import ...`, `app.main:app`, `packages = ["app"]`).
> Renaming it breaks the entire backend. That is exactly why the placeholder is `myapp`.

Then re-run the `grep` to confirm nothing is left, and `cd backend && uv sync --extra dev`
so the lockfile picks up the new package name.

Do **not** rename `backend/alembic/versions/3168153d1c43_baseline.py` or its revision id.
It is an empty baseline; your migrations stack on top of it.

## 2. Create the external services

| Service | What to create | Notes |
| --- | --- | --- |
| **Neon** | A project with a `production` branch and a `dev` branch | Pick the region **before** creating anything else; moving it later means recreating the project |
| **Render** | A Web Service, Docker runtime, autodeploy from `main` | Same region as Neon, or every query pays a transatlantic round trip |
| **Vercel** | A project pointing at `frontend/` | Only once the frontend scaffold exists |
| **Sentry** | A project, Python/FastAPI platform | Optional; leaving `SENTRY_DSN` empty disables it cleanly |

Then set the variables. None of these belongs in the repository:

| Where | Variable | Value |
| --- | --- | --- |
| Render → Environment | `ENVIRONMENT` | `production` (or `preview`) |
| Render → Environment | `DATABASE_URL` | Neon `production` connection string |
| Render → Environment | `CORS_ORIGINS` | The deployed frontend origin. Comma-separated for several; **never** `*` |
| Render → Environment | `SENTRY_DSN` | From Sentry, or leave unset |
| GitHub → Secrets → Actions | `DATABASE_URL_PRODUCTION` | Neon `production` connection string, used by `migrate-production.yml` |
| Local | `backend/.env` | `cp backend/.env.example backend/.env`, pointing at local Postgres |

Until `DATABASE_URL_PRODUCTION` exists, the migrations workflow finishes green and logs a
notice saying it skipped. That is deliberate — see the guard step in
`.github/workflows/migrate-production.yml`.

`CORS_ORIGINS` defaults to an empty list on purpose: an environment that forgets it allows
nothing, rather than silently falling back to a developer's localhost.

## 3. GitHub settings the template does not carry

A template copies files. It does not copy repository configuration, and this is the part
that silently goes missing. One script applies all of it:

```bash
scripts/setup-github.sh          # or: scripts/setup-github.sh owner/repo
```

It sets the merge policy (squash only, delete the branch afterwards), creates the branch
ruleset from `scripts/ruleset-main.json`, and turns on secret scanning and push protection.
It is idempotent, so re-running it is safe. The rest of this section explains what it does,
in case you would rather click through it or need to change something first.

**Branch ruleset on `main`** — require a pull request, block deletion and force pushes, and
require these status checks by their exact names:

```
ruff   mypy   pytest   migrations   docker-build   pip-audit   gitleaks
CodeQL   analyze (python)
lint   typecheck   build   audit
```

The last four are the frontend jobs. They report `skipped` while `frontend/package.json`
does not exist, which counts as passing, so adding them now costs nothing and saves you from
remembering once the scaffold lands.

The ruleset targets `~DEFAULT_BRANCH` rather than the literal name `main`, so renaming the
default branch does not silently leave it unprotected.

**Secret scanning and push protection** — Settings → Advanced Security. Free on public
repositories. `gitleaks` in CI scans the full history; push protection catches a secret
before it is ever pushed. They are complementary, keep both.

> **If your repository is private:** `codeql.yml` will fail. Code scanning is free only on
> public repositories; on a private one it needs paid GitHub Code Security. Either pay for
> it, or delete `.github/workflows/codeql.yml` and drop `CodeQL` and `analyze (python)` from
> `scripts/ruleset-main.json` **before** running the script. Do not leave the workflow in
> place and failing.

## 4. Rewrite the documentation

- **`README.md`** — title, description, the "What you get" list. Remove the pointer to this
  file.
- **`CLAUDE.md`** — rewrite `## Project` to describe your actual domain, and revisit
  `## Architecture decisions`. Everything else (commands, the architecture of `config.py` /
  `db.py` / middleware / `conftest.py`, the security section, git workflow, stack
  constraints, and the list of commands Claude must not run) applies unchanged and is the
  reason this template exists.
- **`.claude/README.md`** — accurate as-is; fill in `hooks/`, `skills/`, `commands/` and
  `agents/` once you see a pattern repeat, not before.

## 5. Known gaps

Inherited as-is. None of them breaks the build; all of them are work you still owe:

- **No rate limiting.** `CLAUDE.md` lists it under Security, but it is not implemented — it
  needs a real public endpoint to be worth anything.
- **No authentication or authorisation.** There is no user model, no login, and no
  `require_role` dependency. That is a feature of your project, not of the infrastructure.
- **`frontend/` is an empty placeholder.** Its four CI jobs (`lint`, `typecheck`, `build`,
  `audit`) are written but have **never executed** — the `changes` guard in
  `frontend-ci.yml` keeps them skipped until `frontend/package.json` exists. Review the
  first frontend PR carefully: those jobs will be running for the very first time.
- **The gitleaks image digest is not tracked by Dependabot.** It lives inside a `run:` step
  in `secret-scan.yml` and has to be bumped by hand.

---

## Done

```bash
git rm TEMPLATE.md
```

Then check the setup end to end: `docker compose up --build` should serve
`http://localhost:8000/health`, and a throwaway pull request should turn every required
check green without any code changes.
