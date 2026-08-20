from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import config
from app.core.config import get_settings
from tests.conftest import transactional_session

BACKEND_DIR = Path(__file__).resolve().parent.parent
DOTENV = BACKEND_DIR / ".env"


def _dotenv_database_url() -> str | None:
    for line in DOTENV.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("DATABASE_URL="):
            return stripped.removeprefix("DATABASE_URL=").strip().strip("\"'")
    return None


def test_the_suite_reads_no_dotenv_file() -> None:
    """conftest.py empties ENV_FILE before app.core.config is ever imported."""
    assert config._ENV_FILE is None


@pytest.mark.skipif(not DOTENV.exists(), reason="no local .env to be shadowed (CI)")
def test_settings_ignore_the_developers_dotenv() -> None:
    """The regression this whole setup exists for: backend/.env names the Neon dev
    branch, and pytest used to connect to it unless you prefixed DATABASE_URL by hand."""
    configured = _dotenv_database_url()

    assert configured, ".env exists but declares no DATABASE_URL, revisit this test"
    assert get_settings().database_url != configured


def test_sentry_is_unreachable_from_the_suite() -> None:
    """An exported SENTRY_DSN must not let test runs reach the real project."""
    assert not get_settings().sentry_dsn


@pytest.mark.db
def test_db_session_rolls_back_even_after_commit() -> None:
    """Checked from outside the context manager, so it proves the teardown undid the
    write rather than that the write was never visible."""
    from app.core.db import engine

    with transactional_session() as session:
        session.execute(text("CREATE TABLE conftest_probe (id integer)"))
        session.execute(text("INSERT INTO conftest_probe VALUES (1)"))
        session.commit()

        assert session.execute(text("SELECT count(*) FROM conftest_probe")).scalar_one() == 1

    with engine.connect() as connection:
        survived = connection.execute(text("SELECT to_regclass('conftest_probe')")).scalar_one()

    assert survived is None


def test_client_does_not_open_a_database_connection(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """The client fixture skips the lifespan on purpose: most tests need the app, not a
    database, and CI should not slow down waiting for one."""
    from app.core import db

    def explode() -> None:
        raise AssertionError("the lifespan ran, so the client fixture touched the database")

    monkeypatch.setattr(db, "check_db_connection", explode)

    assert client.get("/health").status_code == 200
