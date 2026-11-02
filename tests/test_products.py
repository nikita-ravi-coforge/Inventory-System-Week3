"""Adding, reading, repricing, and deleting products."""

import sqlite3

import pytest

from inventory_db import (
    ProductHasSalesError,
    add_product,
    change_price,
    delete_product,
    get_product,
    load_sample_data,
)


def _supplier_id(connection, name="Acme"):
    connection.execute("INSERT INTO suppliers (name) VALUES (?)", (name,))
    row = connection.execute(
        "SELECT id FROM suppliers WHERE name = ?",
        (name,),
    ).fetchone()
    return row["id"]


def test_add_product_returns_new_id(connection):
    supplier_id = _supplier_id(connection)
    product_id = add_product(
        connection,
        "NEW-1",
        "Mallet",
        "Hardware",
        supplier_id,
        1000,
        4,
        1,
    )
    row = get_product(connection, product_id)
    assert row["id"] == product_id
    assert row["sku"] == "NEW-1"
    assert row["supplier_name"] == "Acme"


def test_duplicate_sku_is_refused(connection):
    supplier_id = _supplier_id(connection)
    add_product(connection, "NEW-1", "Mallet", "Hardware", supplier_id, 1000, 4, 1)
    with pytest.raises(sqlite3.IntegrityError):
        add_product(
            connection,
            "NEW-1",
            "Other Mallet",
            "Hardware",
            supplier_id,
            500,
            1,
            0,
        )


def test_unknown_supplier_is_refused(connection):
    with pytest.raises(sqlite3.IntegrityError):
        add_product(connection, "NEW-1", "Mallet", "Hardware", 999, 1000, 4, 1)


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
        add_product(
            connection,
            "NEW-1",
            "Mallet",
            "Hardware",
            supplier_id,
            unit_price_cents,
            quantity_on_hand,
            0,
        )


def test_get_product_includes_supplier_name(connection):
    with connection:
        load_sample_data(connection)
    row = get_product(connection, 8)
    assert row["name"] == "Trail Tent"
    assert row["supplier_name"] == "Peak Outfitters"


def test_get_product_missing_returns_none(connection):
    assert get_product(connection, 999) is None


def test_change_price_updates_product(connection):
    with connection:
        load_sample_data(connection)
    assert change_price(connection, 8, 17000) is True
    assert get_product(connection, 8)["unit_price_cents"] == 17000


def test_change_price_missing_product_returns_false(connection):
    assert change_price(connection, 999, 17000) is False


def test_cannot_delete_sold_product(connection):
    with connection:
        load_sample_data(connection)
    with pytest.raises(ProductHasSalesError):
        delete_product(connection, 1)
    assert get_product(connection, 1)["sku"] == "HW-001"


def test_can_delete_never_sold_product(connection):
    with connection:
        load_sample_data(connection)
    assert delete_product(connection, 3) is True
    assert get_product(connection, 3) is None


def test_delete_missing_product_returns_false(connection):
    assert delete_product(connection, 999) is False
