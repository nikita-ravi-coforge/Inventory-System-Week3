"""Rules the database enforces, and the shape of the sample catalog."""

import sqlite3

import pytest

from inventory_db import init_db, load_sample_data, table_counts

TABLES = (
    "suppliers",
    "products",
    "sales",
    "sale_items",
    "stock_movements",
)

PRODUCT_INSERT = """
    INSERT INTO products (
        sku, name, category, supplier_id,
        unit_price_cents, quantity_on_hand, reorder_level
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _supplier_id(connection, name="Acme"):
    connection.execute("INSERT INTO suppliers (name) VALUES (?)", (name,))
    row = connection.execute(
        "SELECT id FROM suppliers WHERE name = ?",
        (name,),
    ).fetchone()
    return row["id"]


def test_connection_enables_foreign_keys_and_named_rows(connection):
    row = connection.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
    _supplier_id(connection, "Acme")
    supplier = connection.execute(
        "SELECT name FROM suppliers WHERE name = ?",
        ("Acme",),
    ).fetchone()
    assert supplier["name"] == "Acme"


def test_tables_are_strict(connection):
    for table_name in TABLES:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        assert row is not None
        assert "STRICT" in row["sql"]


def test_supplier_index_exists(connection):
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        ("idx_products_supplier_id",),
    ).fetchone()
    assert row is not None


def test_schema_can_run_twice_without_erasing_data(connection):
    connection.execute("INSERT INTO suppliers (name) VALUES (?)", ("Acme",))
    connection.commit()
    init_db(connection)
    row = connection.execute("SELECT name FROM suppliers").fetchone()
    assert row["name"] == "Acme"


def test_duplicate_sku_is_refused(connection):
    supplier_id = _supplier_id(connection)
    connection.execute(
        PRODUCT_INSERT,
        ("HW-001", "Claw Hammer", "Hardware", supplier_id, 1299, 1, 0),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            PRODUCT_INSERT,
            ("HW-001", "Other Hammer", "Hardware", supplier_id, 500, 1, 0),
        )


def test_unknown_supplier_is_refused(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            PRODUCT_INSERT,
            ("HW-001", "Claw Hammer", "Hardware", 999, 1299, 1, 0),
        )


@pytest.mark.parametrize(
    ("unit_price_cents", "quantity_on_hand"),
    [(-1, 1), (100, -1)],
)
def test_negative_price_or_quantity_is_refused(
    connection,
    unit_price_cents,
    quantity_on_hand,
):
    supplier_id = _supplier_id(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            PRODUCT_INSERT,
            (
                "HW-001",
                "Claw Hammer",
                "Hardware",
                supplier_id,
                unit_price_cents,
                quantity_on_hand,
                0,
            ),
        )


def test_invalid_movement_reason_is_refused(connection):
    supplier_id = _supplier_id(connection)
    cursor = connection.execute(
        PRODUCT_INSERT,
        ("HW-001", "Claw Hammer", "Hardware", supplier_id, 1299, 5, 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO stock_movements (
                product_id, quantity_change, reason, happened_at
            ) VALUES (?, ?, ?, ?)
            """,
            (cursor.lastrowid, 1, "theft", "2026-04-01T00:00:00"),
        )


def test_sample_data_has_the_required_shape(connection):
    with connection:
        load_sample_data(connection)

    assert table_counts(connection) == {
        "suppliers": 4,
        "products": 12,
        "sales": 5,
        "sale_items": 12,
        "stock_movements": 0,
    }

    categories = connection.execute(
        "SELECT DISTINCT category FROM products"
    ).fetchall()
    assert len(categories) >= 3

    never_sold = connection.execute(
        """
        SELECT COUNT(*) AS n FROM products
        WHERE NOT EXISTS (
            SELECT 1 FROM sale_items WHERE sale_items.product_id = products.id
        )
        """
    ).fetchone()
    assert never_sold["n"] >= 2

    low_stock = connection.execute(
        """
        SELECT COUNT(*) AS n FROM products
        WHERE quantity_on_hand <= reorder_level
        """
    ).fetchone()
    assert low_stock["n"] >= 2
