from app.models import Base
from app.models.base import NAMING_CONVENTION


def test_metadata_carries_the_naming_convention() -> None:
    """A cheap guard on something whose absence fails silently.

    Without the convention, Postgres names constraints itself and `alembic check`
    starts reporting drift that is not there -- or, worse, stops being trusted. It
    can only be set while the schema is empty, so a refactor dropping it would be
    expensive to undo once there are tables.
    """
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_composite_indexes_get_distinct_names() -> None:
    """Why the convention uses column_0_N_name and not column_0_name: two composite
    indexes starting on the same column must not collide."""
    assert "column_0_N_name" in NAMING_CONVENTION["ix"]
    assert "column_0_N_name" in NAMING_CONVENTION["uq"]
