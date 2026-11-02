"""Restock, stock adjustments, and sales, including a sale that rolls back."""

import pytest

from inventory_db import (
    DuplicateSaleLineError,
    InvalidAmountError,
    NotEnoughStockError,
    UnknownProductError,
    adjust_stock,
    get_product,
    record_sale,
    restock,
    table_counts,
)

WHEN = "2026-04-01T12:00:00"

PRODUCT_INSERT = """
    INSERT INTO products (
        id, sku, name, category, supplier_id,
        unit_price_cents, quantity_on_hand, reorder_level
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def _two_products(connection):
    """Hammer id 1 has 20 on hand. Lantern id 9 has 2. No sales yet."""
    connection.execute(
        "INSERT INTO suppliers (id, name) VALUES (?, ?)",
        (1, "Northwind Supply"),
    )
    connection.execute(
        "INSERT INTO suppliers (id, name) VALUES (?, ?)",
        (3, "Peak Outfitters"),
    )
    connection.execute(
        PRODUCT_INSERT,
        (1, "HW-001", "Claw Hammer", "Hardware", 1, 1299, 20, 5),
    )
    connection.execute(
        PRODUCT_INSERT,
        (9, "OD-002", "Camp Lantern", "Outdoor", 3, 2499, 2, 5),
    )
    connection.commit()


def _movements(connection):
    return connection.execute(
        """
        SELECT product_id, quantity_change, reason, happened_at
        FROM stock_movements
        ORDER BY id
        """
    ).fetchall()


def test_restock_increases_stock_and_logs_one_movement(connection):
    _two_products(connection)
    restock(connection, 1, 4, when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 24
    rows = _movements(connection)
    assert len(rows) == 1
    assert tuple(rows[0]) == (1, 4, "restock", WHEN)


@pytest.mark.parametrize("amount", [0, -1])
def test_restock_of_zero_or_less_is_refused(connection, amount):
    _two_products(connection)
    with pytest.raises(InvalidAmountError):
        restock(connection, 1, amount, when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 20
    assert _movements(connection) == []


def test_adjustment_logs_a_signed_movement(connection):
    _two_products(connection)
    adjust_stock(connection, 1, -3, when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 17
    assert tuple(_movements(connection)[0]) == (1, -3, "adjustment", WHEN)


def test_adjustment_cannot_make_stock_negative(connection):
    _two_products(connection)
    with pytest.raises(NotEnoughStockError):
        adjust_stock(connection, 9, -5, when=WHEN)


def test_refused_adjustment_changes_nothing(connection):
    _two_products(connection)
    with pytest.raises(NotEnoughStockError):
        adjust_stock(connection, 9, -5, when=WHEN)
    assert get_product(connection, 9)["quantity_on_hand"] == 2
    assert _movements(connection) == []
    assert table_counts(connection)["stock_movements"] == 0


def test_sale_records_lines_at_current_prices_reduces_stock_and_logs_movements(
    connection,
):
    _two_products(connection)
    sale_id = record_sale(connection, [(1, 2), (9, 1)], when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 18
    assert get_product(connection, 9)["quantity_on_hand"] == 1
    lines = connection.execute(
        """
        SELECT sale_id, product_id, quantity, unit_price_cents
        FROM sale_items
        ORDER BY id
        """
    ).fetchall()
    assert [tuple(row) for row in lines] == [
        (sale_id, 1, 2, 1299),
        (sale_id, 9, 1, 2499),
    ]
    assert [tuple(row) for row in _movements(connection)] == [
        (1, -2, "sale", WHEN),
        (9, -1, "sale", WHEN),
    ]


def test_sale_that_fails_halfway_changes_nothing(connection):
    _two_products(connection)
    with pytest.raises(NotEnoughStockError, match="Not enough stock for product 9."):
        record_sale(connection, [(1, 2), (9, 5)], when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 20
    assert get_product(connection, 9)["quantity_on_hand"] == 2
    counts = table_counts(connection)
    assert counts["sales"] == 0
    assert counts["sale_items"] == 0
    assert counts["stock_movements"] == 0


def test_sale_for_unknown_product_changes_nothing(connection):
    _two_products(connection)
    with pytest.raises(UnknownProductError):
        record_sale(connection, [(999, 1)], when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 20
    counts = table_counts(connection)
    assert counts["sales"] == 0
    assert counts["sale_items"] == 0
    assert counts["stock_movements"] == 0


def test_duplicate_product_in_one_sale_changes_nothing(connection):
    _two_products(connection)
    with pytest.raises(DuplicateSaleLineError):
        record_sale(connection, [(1, 1), (1, 1)], when=WHEN)
    assert get_product(connection, 1)["quantity_on_hand"] == 20
    counts = table_counts(connection)
    assert counts["sales"] == 0
    assert counts["sale_items"] == 0
    assert counts["stock_movements"] == 0
