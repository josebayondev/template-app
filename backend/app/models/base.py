from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic names for every index and constraint. Postgres names anything left
# unnamed itself, and those generated names do not match what SQLAlchemy would emit,
# so `alembic check` -- the CI job that compares the models against the database --
# reports drift that is not there. With the convention in place both sides agree.
#
# This has to be settled while the schema is still empty, which is exactly why it ships
# with the template: applying it later means renaming live constraints in production.
#
# Two of the patterns are load-bearing:
#
# - "column_0_N_name" (not "column_0_name") on ix/uq spells out every column in the
#   index. With only the first, two composite indexes starting on the same column
#   would generate the same name and Postgres would reject the second.
#
# - "ck" builds on constraint_name, which forces every CheckConstraint to be named by
#   hand (name="duration_range"). That is the point: a violation then reports
#   ck_<table>_<name> instead of an opaque hash. An unnamed CHECK fails when the
#   migration is generated -- locally, not in production.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    # Table names are singular: one row is one thing, and the table then matches its
    # mapped class name character for character.
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
