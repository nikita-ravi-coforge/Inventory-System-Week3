"""The menu turns bad input and database errors into short messages."""

from inventory_db import load_sample_data
from main import run_menu


def _run(connection, answers):
    pending = iter(answers)
    lines = []
    run_menu(
        connection,
        input_func=lambda _prompt: next(pending),
        output_func=lines.append,
    )
    return lines


def test_menu_shows_low_stock_banner_for_the_sample_catalog(connection):
    with connection:
        load_sample_data(connection)
    lines = _run(connection, ["0"])
    assert lines[0] == "Low stock: 4 products"


def test_menu_shows_zero_when_nothing_is_low(connection):
    lines = _run(connection, ["0"])
    assert lines[0] == "Low stock: 0 products"


def test_menu_rejects_text_where_a_number_is_expected(connection):
    lines = _run(connection, ["2", "abc", "0"])
    assert "Please enter a whole number." in lines


def test_menu_duplicate_sku_is_friendly(connection):
    connection.execute("INSERT INTO suppliers (id, name) VALUES (?, ?)", (1, "Acme"))
    connection.commit()
    lines = _run(
        connection,
        [
            "3",
            "SKU-1",
            "Mallet",
            "Hardware",
            "1",
            "1000",
            "4",
            "1",
            "3",
            "SKU-1",
            "Other",
            "Hardware",
            "1",
            "500",
            "1",
            "0",
            "0",
        ],
    )
    assert "That SKU already exists." in lines
    assert "Added product 1." in lines


def test_menu_refuses_to_delete_a_sold_product(connection):
    with connection:
        load_sample_data(connection)
    lines = _run(connection, ["5", "1", "0"])
    assert "That product has sales history and cannot be deleted." in lines
