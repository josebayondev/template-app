from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """created_at / updated_at for any table that wants them.

    Both are filled by the database (server_default / onupdate) rather than by Python,
    so a row written from psql or from a data migration is stamped too -- those paths
    never run the ORM.

    timezone=True maps to TIMESTAMPTZ. Every instant is stored in UTC and converted at
    the boundary, never on the way into the database.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
