import logging
import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Waits between the startup connection attempts, in seconds. Neon suspends idle
# compute, so the first connection of a deploy can land while it is still waking.
STARTUP_RETRY_DELAYS = (1.0, 2.0, 4.0)

engine = create_engine(
    make_url(settings.database_url).set(drivername="postgresql+psycopg"),
    pool_pre_ping=True,
    # Without this a hung database blocks startup indefinitely, until Render's
    # 15 minute health check window expires. Ten seconds fails fast enough to be
    # worth retrying.
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> None:
    """Verify the database answers, retrying while it may still be waking up.

    Raises the last error once the retries run out: failing the deploy is the
    right outcome when the database is genuinely unreachable. Render keeps the
    previous version serving, so a red deploy is not an outage.
    """
    attempts = len(STARTUP_RETRY_DELAYS) + 1

    for attempt, delay in enumerate((*STARTUP_RETRY_DELAYS, None), start=1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            if delay is None:
                logger.error("Database unreachable after %d attempts", attempts)
                raise
            logger.warning(
                "Database connection failed (attempt %d/%d), retrying in %.0fs: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)
        else:
            logger.info("Database connection OK")
            return
