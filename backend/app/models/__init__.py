"""The mapped models, all of them.

Importing every model here is load-bearing, not tidiness. alembic/env.py does
`from app.models import Base` and autogenerate only sees the tables whose module has
actually been imported, so a model missing from this file produces an *empty* migration
without warning about anything.
"""

from app.models.base import Base
from app.models.mixins import TimestampMixin

__all__ = ["Base", "TimestampMixin"]
