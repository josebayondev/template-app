import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# --------------------------------------------------------------------------------------
# Environment isolation. This block runs when pytest loads this conftest, which is before
# it imports any tests/test_*.py -- and that ordering is the whole point. app/core/db.py
# and app/main.py both call get_settings() at import time, and lru_cache freezes the
# result for the rest of the session, so no fixture can correct it afterwards. Nothing in
# this module may import app.* at module level; the fixtures below import it lazily.
#
# Without this, `uv run pytest` reads backend/.env, which names the Neon dev branch, and
# the database tests open real connections to it.
# --------------------------------------------------------------------------------------

os.environ["ENV_FILE"] = ""

# The same database the postgres service in docker-compose.yml serves, and the same one
# the CI jobs point at. setdefault rather than a hard assignment so CI's own DATABASE_URL
# still wins, and so a developer can aim the suite elsewhere without editing anything.
TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/myapp"
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

# Pinned rather than left at the empty default so the CORS tests can assert an accepted
# preflight, not merely a rejected one. Deliberately not a real front-end origin: nothing
# outside the suite should recognise it.
TEST_CORS_ORIGIN = "http://front.test"
os.environ["CORS_ORIGINS"] = TEST_CORS_ORIGIN

# Not setdefault: there is no legitimate reason for the suite to reach the real Sentry
# project, and an exported SENTRY_DSN would otherwise send test noise to production.
os.environ["SENTRY_DSN"] = ""

SETTINGS_ENV_VARS = (
    "ENVIRONMENT",
    "PROJECT_NAME",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "SENTRY_DSN",
)


@contextmanager
def transactional_session() -> Iterator[Session]:
    """A session whose writes never outlive the block, so tests cannot leak into
    each other.

    join_transaction_mode="create_savepoint" is what makes this hold even when the test
    calls commit(): the session commits into a savepoint nested inside the outer
    transaction, and rolling that transaction back discards everything.

    Exposed as a context manager and not only as the db_session fixture so a test can
    watch it tear down and check the rollback from outside.
    """
    from app.core.db import SessionLocal, engine

    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def _migrated_schema() -> None:
    """Turn "you forgot to migrate" into one sentence instead of a page of traceback.

    A db-marked test hitting a table that does not exist fails deep inside psycopg with
    UndefinedTable, repeated once per test, which buries the one thing worth knowing.
    Checking the model tables against the database up front says it once, and says what
    to run about it.

    Compared against Base.metadata rather than against alembic's revision history on
    purpose: what these tests need is the tables, and that stays true whether the schema
    is behind, was rolled back, or was pointed at the wrong database entirely.

    The message names the host and database because "run alembic upgrade head" is not by
    itself enough to act on. There is no backend/.env in the template, so alembic and
    this suite both reach the same local Postgres -- but the moment you add one, they
    stop being the same database, and a plain `alembic upgrade head` will migrate the
    deployed one and leave these tests failing against localhost with no hint that
    anything moved at all.
    """
    from sqlalchemy import inspect

    from app.core.db import engine
    from app.models import Base

    missing = sorted(set(Base.metadata.tables) - set(inspect(engine).get_table_names()))
    if missing:
        # Host and database only. The password is never interpolated into the message.
        target = f"{engine.url.database} at {engine.url.host}"
        pytest.fail(
            f"{target} has no {', '.join(missing)}. Alembic follows backend/.env when you "
            f"have one, which may be a different database, so migrate this one explicitly:\n"
            f"  DATABASE_URL={TEST_DATABASE_URL} uv run alembic upgrade head",
            pytrace=False,
        )


@pytest.fixture
def db_session(_migrated_schema: None) -> Iterator[Session]:
    """A session on genuinely empty tables. Mark the test with @pytest.mark.db.

    The emptying is not redundant with the rollback. The rollback undoes what the *test*
    writes; this undoes what was already committed before pytest started -- and that is
    not hypothetical, because poking at the development database by hand, or running a
    seed script against it, is a normal thing to do.

    Without this, using the application breaks the suite: a test asserting `.one()` finds
    the pre-existing row alongside its own, and one asserting a unique constraint passes
    for the wrong reason, colliding with ambient data instead of with the row it created.
    CI gets a fresh Postgres every run and would stay green throughout, which is the
    worst version of the problem.

    The DELETEs run inside the fixture's transaction, so anything committed beforehand is
    back the moment it rolls back. Reversed order so foreign keys are respected.
    """
    from app.models import Base

    with transactional_session() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        yield session


@pytest.fixture
def client() -> TestClient:
    """The real app without its lifespan, so no database connection is opened.

    TestClient only runs the lifespan inside a `with` block, and this fixture
    deliberately does not use one.
    """
    from app.main import app

    return TestClient(app)


@pytest.fixture
def running_client() -> Iterator[TestClient]:
    """The real app with its lifespan, so check_db_connection() actually runs."""
    from app.main import app

    with TestClient(app) as started:
        yield started


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsets every Settings variable, for tests asserting on defaults or on
    .env.example. Without it the isolation block above would shadow what they read."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
