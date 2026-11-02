"""Shared pytest fixtures.

Every test gets a new in-memory database. The first feature pull request
points this fixture at inventory_db.connect so foreign keys are turned on
in one place.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


@pytest.fixture
def connection():
    """Yield a fresh in-memory database and close it when the test ends."""
    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        if SCHEMA_PATH.is_file():
            db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        yield db
