"""Terminal menu for the inventory database."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from inventory_db import (
    DuplicateSaleLineError,
    InvalidAmountError,
    NotEnoughStockError,
    ProductHasSalesError,
    UnknownProductError,
    add_product,
    backup_database,
    change_price,
    connect,
    db_path,
    delete_product,
    format_cents,
    get_product,
    init_db,
    record_sale,
    report_low_stock,
    report_never_sold,
    report_sales_by_product,
    report_stock_value_by_supplier,
    restock,
    search_products,
)

MENU = """
1. Search products
2. Look up a product
3. Add a product
4. Change a price
5. Delete a product
6. Restock
7. Record a sale
8. Stock value by supplier
9. Low stock
10. Sales by product
11. Never sold
12. Back up the database
0. Quit
""".strip()


def read_required_int(prompt, input_func, output_func):
    """Read one whole number. Return None when the text is not a number."""
    raw = input_func(prompt).strip()
    try:
        return int(raw)
    except ValueError:
        output_func("Please enter a whole number.")
        return None


def read_yes_no(prompt, input_func, output_func):
    """Read y or n. A blank answer means no."""
    raw = input_func(prompt).strip().lower()
    if raw in ("y", "yes"):
        return True
    if raw in ("n", "no", ""):
        return False
    output_func("Please enter y or n.")
    return None


def friendly_integrity_message(error: sqlite3.IntegrityError) -> str:
    """Turn a database constraint failure into a sentence for the menu."""
    text = str(error).lower()
    if "sku" in text:
        return "That SKU already exists."
    if "foreign key" in text:
        return "That supplier does not exist."
    if "check constraint" in text:
        return "Price and quantity cannot be negative."
    return "That change was rejected by the database."


def _print_product(row, output_func) -> None:
    output_func(
        f"{row['sku']}  {row['name']}  {row['category']}  "
        f"{row['supplier_name']}  {format_cents(row['unit_price_cents'])}  "
        f"on hand {row['quantity_on_hand']}  reorder {row['reorder_level']}"
    )


def search_action(connection, input_func, output_func) -> None:
    text = input_func("Search text: ")
    category = input_func("Category (blank to skip): ").strip() or None
    raw_price = input_func("Maximum price in cents (blank to skip): ").strip()
    max_price = None
    if raw_price:
        try:
            max_price = int(raw_price)
        except ValueError:
            output_func("Please enter a whole number.")
            return
    in_stock_only = read_yes_no("In stock only? [y/N]: ", input_func, output_func)
    if in_stock_only is None:
        return
    low_stock_only = read_yes_no("Low stock only? [y/N]: ", input_func, output_func)
    if low_stock_only is None:
        return
    rows = search_products(
        connection,
        text,
        category=category,
        max_price_cents=max_price,
        in_stock_only=in_stock_only,
        low_stock_only=low_stock_only,
    )
    if not rows:
        output_func("No products matched.")
        return
    for row in rows:
        _print_product(row, output_func)


def lookup_action(connection, input_func, output_func) -> None:
    product_id = read_required_int("Product id: ", input_func, output_func)
    if product_id is None:
        return
    row = get_product(connection, product_id)
    if row is None:
        output_func("No product has that id.")
        return
    _print_product(row, output_func)


def add_action(connection, input_func, output_func) -> None:
    sku = input_func("SKU: ").strip()
    name = input_func("Name: ").strip()
    category = input_func("Category: ").strip()
    supplier_id = read_required_int("Supplier id: ", input_func, output_func)
    unit_price_cents = read_required_int("Price in cents: ", input_func, output_func)
    quantity_on_hand = read_required_int("Quantity on hand: ", input_func, output_func)
    reorder_level = read_required_int("Reorder level: ", input_func, output_func)
    numbers = (supplier_id, unit_price_cents, quantity_on_hand, reorder_level)
    if None in numbers:
        return
    product_id = add_product(
        connection,
        sku,
        name,
        category,
        supplier_id,
        unit_price_cents,
        quantity_on_hand,
        reorder_level,
    )
    connection.commit()
    output_func(f"Added product {product_id}.")


def change_price_action(connection, input_func, output_func) -> None:
    product_id = read_required_int("Product id: ", input_func, output_func)
    unit_price_cents = read_required_int("New price in cents: ", input_func, output_func)
    if product_id is None or unit_price_cents is None:
        return
    if not change_price(connection, product_id, unit_price_cents):
        output_func("No product has that id.")
        return
    connection.commit()
    output_func("Price updated.")


def delete_action(connection, input_func, output_func) -> None:
    product_id = read_required_int("Product id: ", input_func, output_func)
    if product_id is None:
        return
    if not delete_product(connection, product_id):
        output_func("No product has that id.")
        return
    output_func("Product deleted.")


def restock_action(connection, input_func, output_func) -> None:
    product_id = read_required_int("Product id: ", input_func, output_func)
    amount = read_required_int("Amount to add: ", input_func, output_func)
    if product_id is None or amount is None:
        return
    restock(connection, product_id, amount)
    output_func("Stock updated.")


def sale_action(connection, input_func, output_func) -> None:
    lines = []
    while True:
        raw_id = input_func("Product id (blank to finish): ").strip()
        if raw_id == "":
            break
        try:
            product_id = int(raw_id)
        except ValueError:
            output_func("Please enter a whole number.")
            return
        quantity = read_required_int("Quantity: ", input_func, output_func)
        if quantity is None:
            return
        lines.append((product_id, quantity))
    sale_id = record_sale(connection, lines)
    output_func(f"Sale {sale_id} recorded.")


def stock_value_action(connection, _input_func, output_func) -> None:
    for row in report_stock_value_by_supplier(connection):
        output_func(f"{row['supplier_name']}  {format_cents(row['stock_value_cents'])}")


def low_stock_action(connection, _input_func, output_func) -> None:
    rows = report_low_stock(connection)
    if not rows:
        output_func("No products are low on stock.")
        return
    for row in rows:
        output_func(
            f"{row['name']}  on hand {row['quantity_on_hand']}  "
            f"reorder {row['reorder_level']}  short {row['units_short']}"
        )


def sales_action(connection, _input_func, output_func) -> None:
    rows = report_sales_by_product(connection)
    if not rows:
        output_func("No sales yet.")
        return
    for row in rows:
        output_func(
            f"{row['name']}  units {row['units_sold']}  {format_cents(row['revenue_cents'])}"
        )


def never_sold_action(connection, _input_func, output_func) -> None:
    rows = report_never_sold(connection)
    if not rows:
        output_func("Every product has been sold.")
        return
    for row in rows:
        output_func(f"{row['sku']}  {row['name']}")


def backup_action(connection, input_func, output_func) -> None:
    destination = input_func("Backup file path: ").strip()
    if not destination:
        output_func("Enter a file path.")
        return
    backup_database(connection, destination)
    output_func(f"Backup written to {destination}.")


ACTIONS = {
    "1": search_action,
    "2": lookup_action,
    "3": add_action,
    "4": change_price_action,
    "5": delete_action,
    "6": restock_action,
    "7": sale_action,
    "8": stock_value_action,
    "9": low_stock_action,
    "10": sales_action,
    "11": never_sold_action,
    "12": backup_action,
}


def run_menu(connection, input_func=input, output_func=print) -> None:
    """Show the menu until the user quits. Bad input prints a message."""
    while True:
        output_func(MENU)
        try:
            choice = input_func("Choose an option: ").strip()
        except EOFError:
            output_func("")
            return
        if choice == "0":
            output_func("Goodbye.")
            return
        action = ACTIONS.get(choice)
        if action is None:
            output_func("Choose a number from the menu.")
            continue
        try:
            action(connection, input_func, output_func)
        except sqlite3.IntegrityError as error:
            output_func(friendly_integrity_message(error))
        except ProductHasSalesError:
            output_func("That product has sales history and cannot be deleted.")
        except InvalidAmountError as error:
            output_func(str(error))
        except NotEnoughStockError as error:
            output_func(f"{error} Nothing was saved.")
        except UnknownProductError as error:
            output_func(f"{error} Nothing was saved.")
        except DuplicateSaleLineError as error:
            output_func(f"{error} Nothing was saved.")
        except sqlite3.Error:
            output_func("The database could not finish that change.")


def main() -> None:
    with closing(connect(db_path())) as connection:
        init_db(connection)
        run_menu(connection)


if __name__ == "__main__":
    main()
