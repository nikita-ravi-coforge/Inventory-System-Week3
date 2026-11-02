"""The four inventory reports against the sample catalog."""

import pytest

from inventory_db import (
    format_cents,
    load_sample_data,
    report_low_stock,
    report_never_sold,
    report_sales_by_product,
    report_stock_value_by_supplier,
)


def _load(connection):
    with connection:
        load_sample_data(connection)


def test_report_stock_value_by_supplier(connection):
    _load(connection)
    rows = [
        (row["supplier_name"], row["stock_value_cents"])
        for row in report_stock_value_by_supplier(connection)
    ]
    assert rows == [
        ("Peak Outfitters", 85479),
        ("Lane Paper", 56715),
        ("Northwind Supply", 27477),
        ("Harbor Goods", 21384),
    ]


def test_report_low_stock(connection):
    _load(connection)
    rows = [
        (row["name"], row["quantity_on_hand"], row["reorder_level"], row["units_short"])
        for row in report_low_stock(connection)
    ]
    assert rows == [
        ("Box of Nails", 3, 10, 7),
        ("Screwdriver", 0, 4, 4),
        ("Camp Lantern", 2, 5, 3),
        ("Pen Pack", 8, 8, 0),
    ]


def test_report_sales_by_product(connection):
    _load(connection)
    rows = [
        (row["name"], row["units_sold"], row["revenue_cents"])
        for row in report_sales_by_product(connection)
    ]
    assert rows == [
        ("Trail Tent", 1, 15999),
        ("Camp Lantern", 2, 4998),
        ("Notebook", 13, 4537),
        ("Claw Hammer", 3, 3897),
        ("Water Bottle", 2, 3798),
        ("Pen Pack", 6, 3594),
        ("Travel Mug", 3, 2997),
        ("Box of Nails", 5, 2495),
        ("Stapler", 1, 1499),
    ]


def test_report_never_sold(connection):
    _load(connection)
    rows = [(row["sku"], row["name"]) for row in report_never_sold(connection)]
    assert rows == [
        ("OD-003", "Climbing Rope"),
        ("OF-004", "Printer Paper"),
        ("HW-003", "Screwdriver"),
    ]


@pytest.mark.parametrize(
    ("cents", "display"),
    [
        (85479, "854.79"),
        (56715, "567.15"),
        (27477, "274.77"),
        (21384, "213.84"),
        (0, "0.00"),
        (5, "0.05"),
    ],
)
def test_format_cents(cents, display):
    assert format_cents(cents) == display
