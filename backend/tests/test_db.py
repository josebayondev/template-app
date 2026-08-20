import pytest
from sqlalchemy import text

from app.core.db import check_db_connection, engine, get_db

pytestmark = pytest.mark.db


def test_check_db_connection_succeeds() -> None:
    check_db_connection()


def test_engine_uses_psycopg_driver() -> None:
    assert engine.url.drivername == "postgresql+psycopg"


def test_get_db_yields_working_session_and_closes_it() -> None:
    gen = get_db()
    db = next(gen)

    assert db.execute(text("SELECT 1")).scalar_one() == 1

    with pytest.raises(StopIteration):
        next(gen)
