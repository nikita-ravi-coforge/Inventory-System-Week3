"""SQLite connection, schema, sample catalog, products, and search."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "inventory.db"

# Complete statements only. Table names are not interpolated into SQL text.
COUNT_SQL = {
    "suppliers": "SELECT COUNT(*) AS n FROM suppliers",
    "products": "SELECT COUNT(*) AS n FROM products",
    "sales": "SELECT COUNT(*) AS n FROM sales",
    "sale_items": "SELECT COUNT(*) AS n FROM sale_items",
    "stock_movements": "SELECT COUNT(*) AS n FROM stock_movements",
}

SUPPLIERS = (
    (1, "Northwind Supply"),
    (2, "Harbor Goods"),
    (3, "Peak Outfitters"),
    (4, "Lane Paper"),
)

PRODUCTS = (
    (1, "HW-001", "Claw Hammer", "Hardware", 1, 1299, 20, 5),
    (2, "HW-002", "Box of Nails", "Hardware", 1, 499, 3, 10),
    (3, "HW-003", "Screwdriver", "Hardware", 1, 899, 0, 4),
    (4, "OF-001", "Notebook", "Office", 4, 349, 40, 15),
    (5, "OF-002", "Pen Pack", "Office", 4, 599, 8, 8),
    (6, "OF-003", "Stapler", "Office", 4, 1499, 12, 3),
    (7, "OF-004", "Printer Paper", "Office", 4, 799, 25, 10),
    (8, "OD-001", "Trail Tent", "Outdoor", 3, 15999, 4, 2),
    (9, "OD-002", "Camp Lantern", "Outdoor", 3, 2499, 2, 5),
    (10, "OD-003", "Climbing Rope", "Outdoor", 3, 1099, 15, 5),
    (11, "HG-001", "Travel Mug", "Outdoor", 2, 999, 10, 4),
    (12, "HG-002", "Water Bottle", "Outdoor", 2, 1899, 6, 4),
)

SALES = (
    (1, "2026-01-05T10:00:00"),
    (2, "2026-01-12T14:30:00"),
    (3, "2026-02-01T09:15:00"),
    (4, "2026-02-14T16:45:00"),
    (5, "2026-03-01T11:00:00"),
)

SALE_ITEMS = (
    (1, 1, 2, 1299),
    (1, 2, 5, 499),
    (1, 4, 3, 349),
    (2, 5, 4, 599),
    (2, 6, 1, 1499),
    (3, 8, 1, 15999),
    (3, 9, 2, 2499),
    (4, 11, 3, 999),
    (4, 12, 2, 1899),
    (4, 1, 1, 1299),
    (5, 4, 10, 349),
    (5, 5, 2, 599),
)


def connect(database: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection with foreign keys on and rows readable by column name.

    isolation_level is DEFERRED so a ``with connection`` block stays one
    transaction on Python 3.9 and on Python 3.12.
    """
    connection = sqlite3.connect(database, isolation_level="DEFERRED")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def db_path() -> str:
    """Return INVENTORY_DB, or inventory.db next to this file when it is unset."""
    configured = os.environ.get("INVENTORY_DB")
    if configured:
        return configured
    return str(DEFAULT_DB_PATH)


def init_db(connection: sqlite3.Connection) -> None:
    """Create any missing tables. Existing rows are left in place.

    executescript commits before it runs, so call this before a data transaction.
    """
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_sample_data(connection: sqlite3.Connection) -> None:
    """Insert the fixed sample rows. The caller commits. Movements stay empty."""
    connection.executemany(
        "INSERT INTO suppliers (id, name) VALUES (?, ?)",
        SUPPLIERS,
    )
    connection.executemany(
        """
        INSERT INTO products (
            id, sku, name, category, supplier_id,
            unit_price_cents, quantity_on_hand, reorder_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        PRODUCTS,
    )
    connection.executemany(
        "INSERT INTO sales (id, sold_at) VALUES (?, ?)",
        SALES,
    )
    connection.executemany(
        """
        INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents)
        VALUES (?, ?, ?, ?)
        """,
        SALE_ITEMS,
    )


def table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return the row count of each table, in schema order."""
    counts = {}
    for table_name, statement in COUNT_SQL.items():
        row = connection.execute(statement).fetchone()
        counts[table_name] = row["n"]
    return counts


class ProductHasSalesError(Exception):
    """Raised when a product that appears on a sale is deleted."""


PRODUCT_WITH_SUPPLIER = (
    "SELECT products.id, products.sku, products.name, products.category, "
    "products.supplier_id, products.unit_price_cents, "
    "products.quantity_on_hand, products.reorder_level, "
    "suppliers.name AS supplier_name "
    "FROM products "
    "JOIN suppliers ON suppliers.id = products.supplier_id "
)


def add_product(
    connection: sqlite3.Connection,
    sku: str,
    name: str,
    category: str,
    supplier_id: int,
    unit_price_cents: int,
    quantity_on_hand: int,
    reorder_level: int,
) -> int:
    """Insert a product and return its new id.

    A duplicate SKU, an unknown supplier, or a negative price or quantity
    raises sqlite3.IntegrityError.
    """
    cursor = connection.execute(
        """
        INSERT INTO products (
            sku, name, category, supplier_id,
            unit_price_cents, quantity_on_hand, reorder_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sku,
            name,
            category,
            supplier_id,
            unit_price_cents,
            quantity_on_hand,
            reorder_level,
        ),
    )
    return cursor.lastrowid


def get_product(
    connection: sqlite3.Connection,
    product_id: int,
) -> sqlite3.Row | None:
    """Return one product with its supplier name, or None when the id is missing."""
    return connection.execute(
        PRODUCT_WITH_SUPPLIER + "WHERE products.id = ?",
        (product_id,),
    ).fetchone()


def change_price(
    connection: sqlite3.Connection,
    product_id: int,
    unit_price_cents: int,
) -> bool:
    """Set a product's price. Return False when the id is missing."""
    cursor = connection.execute(
        "UPDATE products SET unit_price_cents = ? WHERE id = ?",
        (unit_price_cents, product_id),
    )
    return cursor.rowcount == 1


def delete_product(connection: sqlite3.Connection, product_id: int) -> bool:
    """Delete a product that has never been sold.

    Movements for that product are removed in the same transaction. A product
    with a sale line raises ProductHasSalesError and nothing is deleted.
    """
    with connection:
        sold = connection.execute(
            "SELECT 1 FROM sale_items WHERE product_id = ? LIMIT 1",
            (product_id,),
        ).fetchone()
        if sold is not None:
            raise ProductHasSalesError(
                "That product has sales history and cannot be deleted."
            )
        connection.execute(
            "DELETE FROM stock_movements WHERE product_id = ?",
            (product_id,),
        )
        cursor = connection.execute(
            "DELETE FROM products WHERE id = ?",
            (product_id,),
        )
        return cursor.rowcount == 1


def search_products(
    connection: sqlite3.Connection,
    text: str,
    category: str | None = None,
    max_price_cents: int | None = None,
    in_stock_only: bool = False,
    low_stock_only: bool = False,
) -> list[sqlite3.Row]:
    """Find products whose name, SKU, or supplier name contains text.

    The match ignores ASCII case. Category, maximum price, in-stock, and
    low-stock filters combine with AND. Results are sorted by product name.
    """
    text_match = (
        "(lower(products.name) LIKE ? "
        "OR lower(products.sku) LIKE ? "
        "OR lower(suppliers.name) LIKE ?)"
    )
    clauses = [text_match]
    pattern = "%" + text.lower() + "%"
    parameters: list[object] = [pattern, pattern, pattern]
    if category is not None:
        clauses.append("products.category = ?")
        parameters.append(category)
    if max_price_cents is not None:
        clauses.append("products.unit_price_cents <= ?")
        parameters.append(max_price_cents)
    if in_stock_only:
        clauses.append("products.quantity_on_hand > 0")
    if low_stock_only:
        clauses.append("products.quantity_on_hand <= products.reorder_level")
    statement = (
        PRODUCT_WITH_SUPPLIER
        + "WHERE "
        + " AND ".join(clauses)
        + " ORDER BY products.name"
    )
    return list(connection.execute(statement, parameters).fetchall())
