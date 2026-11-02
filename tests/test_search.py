"""Case-insensitive product search and the optional filters."""

import pytest

from inventory_db import load_sample_data, search_products

INJECTION = "'; DROP TABLE products; --"


def _load(connection):
    with connection:
        load_sample_data(connection)


def _skus(connection, text, **filters):
    rows = search_products(connection, text, **filters)
    return [row["sku"] for row in rows]


def test_search_results_are_sorted_by_name(connection):
    _load(connection)
    names = [row["name"] for row in search_products(connection, "")]
    assert names == sorted(names)
    assert len(names) == 12


@pytest.mark.parametrize(
    ("text", "sku"),
    [
        ("hammer", "HW-001"),
        ("HAMMER", "HW-001"),
        ("hw-001", "HW-001"),
        ("Hw-001", "HW-001"),
        ("peak outfitters", "OD-001"),
        ("PEAK", "OD-002"),
    ],
)
def test_search_matches_name_sku_or_supplier_ignoring_case(connection, text, sku):
    _load(connection)
    assert sku in _skus(connection, text)


def test_search_filter_category(connection):
    _load(connection)
    assert _skus(connection, "", category="Hardware") == [
        "HW-002",
        "HW-001",
        "HW-003",
    ]


def test_search_filter_max_price(connection):
    _load(connection)
    assert _skus(connection, "", max_price_cents=599) == [
        "HW-002",
        "OF-001",
        "OF-002",
    ]


def test_search_filter_in_stock_only(connection):
    _load(connection)
    skus = _skus(connection, "", in_stock_only=True)
    assert "HW-003" not in skus
    assert len(skus) == 11


def test_search_filter_low_stock_only(connection):
    _load(connection)
    assert _skus(connection, "", low_stock_only=True) == [
        "HW-002",
        "OD-002",
        "OF-002",
        "HW-003",
    ]


def test_search_filters_combine(connection):
    _load(connection)
    assert _skus(
        connection,
        "",
        category="Hardware",
        max_price_cents=1000,
        in_stock_only=True,
        low_stock_only=True,
    ) == ["HW-002"]


def test_search_injection_does_not_drop_table(connection):
    _load(connection)
    assert search_products(connection, INJECTION) == []
    count = connection.execute("SELECT COUNT(*) AS n FROM products").fetchone()
    assert count["n"] == 12
