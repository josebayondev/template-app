import logging

import pytest
from sqlalchemy.exc import OperationalError

from app.core import db

# Not purely a unit test: the happy path of the retry test lets the second attempt
# reach the real engine.connect().
pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps the retry backoff from actually delaying the suite."""
    monkeypatch.setattr(db.time, "sleep", lambda _seconds: None)


def _boom() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_retries_until_the_database_answers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Neon suspends idle compute, so the first attempt of a deploy can fail."""
    attempts = {"n": 0}
    real_connect = db.engine.connect

    def flaky():  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _boom()
        return real_connect()

    monkeypatch.setattr(db.engine, "connect", flaky)

    with caplog.at_level(logging.INFO):
        db.check_db_connection()

    assert attempts["n"] == 2
    assert "retrying" in caplog.text
    assert "Database connection OK" in caplog.text


def test_raises_once_the_retries_run_out(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A genuinely unreachable database must still fail the deploy."""
    attempts = {"n": 0}

    def always_fails():  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        raise _boom()

    monkeypatch.setattr(db.engine, "connect", always_fails)

    with caplog.at_level(logging.ERROR), pytest.raises(OperationalError):
        db.check_db_connection()

    assert attempts["n"] == len(db.STARTUP_RETRY_DELAYS) + 1
    assert "Database unreachable" in caplog.text
