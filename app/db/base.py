"""Declarative base and model imports for Alembic metadata discovery."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""


# Import models after Base exists so Alembic sees every mapped table.
def load_models() -> None:
    from app import models  # noqa: F401

