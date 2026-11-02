"""Shared pytest fixtures.

Every test gets a new in-memory database opened by inventory_db.connect.
"""

from contextlib import closing

import pytest

from inventory_db import connect, init_db


@pytest.fixture
def connection():
    """Yield a fresh in-memory database and close it when the test ends."""
    with closing(connect(":memory:")) as db:
        init_db(db)
        yield db
