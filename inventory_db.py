"""SQLite connection, schema, sample catalog, products, search, and reports."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
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


class InvalidAmountError(Exception):
    """Raised when a quantity is zero, negative, or missing."""


class NotEnoughStockError(Exception):
    """Raised when a change would make stock negative."""


class UnknownProductError(Exception):
    """Raised when a product id does not exist."""


class DuplicateSaleLineError(Exception):
    """Raised when one sale lists the same product twice."""


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


def format_cents(cents: int) -> str:
    """Render whole cents as a decimal string with two places."""
    sign = "-" if cents < 0 else ""
    amount = abs(cents)
    return sign + str(amount // 100) + "." + f"{amount % 100:02d}"


def report_stock_value_by_supplier(
    connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """Return each supplier's stock value in cents, highest value first."""
    return list(
        connection.execute(
            """
            SELECT suppliers.name AS supplier_name,
                   SUM(products.unit_price_cents * products.quantity_on_hand)
                       AS stock_value_cents
            FROM suppliers
            JOIN products ON products.supplier_id = suppliers.id
            GROUP BY suppliers.id
            ORDER BY stock_value_cents DESC, suppliers.name
            """
        ).fetchall()
    )


def report_low_stock(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return products at or below their reorder level, largest shortfall first."""
    return list(
        connection.execute(
            """
            SELECT sku, name, quantity_on_hand, reorder_level,
                   reorder_level - quantity_on_hand AS units_short
            FROM products
            WHERE quantity_on_hand <= reorder_level
            ORDER BY units_short DESC, name
            """
        ).fetchall()
    )


def report_sales_by_product(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return units sold and revenue in cents, highest revenue first.

    Revenue uses the price stored on each sale line.
    """
    return list(
        connection.execute(
            """
            SELECT products.sku, products.name,
                   SUM(sale_items.quantity) AS units_sold,
                   SUM(sale_items.quantity * sale_items.unit_price_cents)
                       AS revenue_cents
            FROM products
            JOIN sale_items ON sale_items.product_id = products.id
            GROUP BY products.id
            ORDER BY revenue_cents DESC, products.name
            """
        ).fetchall()
    )


def report_never_sold(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return products that appear on no sale, sorted by name."""
    return list(
        connection.execute(
            """
            SELECT products.sku, products.name
            FROM products
            WHERE NOT EXISTS (
                SELECT 1 FROM sale_items
                WHERE sale_items.product_id = products.id
            )
            ORDER BY products.name
            """
        ).fetchall()
    )


def _timestamp(when: str | None) -> str:
    """Use the caller's time, or the current UTC time when it was omitted."""
    if when is None:
        # timezone.utc works on Python 3.9. datetime.UTC needs 3.11.
        return datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: UP017
    return when


def _insert_movement(
    connection: sqlite3.Connection,
    product_id: int,
    quantity_change: int,
    reason: str,
    happened_at: str,
) -> None:
    """Log one stock change. Does not commit."""
    connection.execute(
        """
        INSERT INTO stock_movements (
            product_id, quantity_change, reason, happened_at
        ) VALUES (?, ?, ?, ?)
        """,
        (product_id, quantity_change, reason, happened_at),
    )


def restock(
    connection: sqlite3.Connection,
    product_id: int,
    amount: int,
    when: str | None = None,
) -> None:
    """Add stock and log one restock movement. Both writes commit together."""
    if amount <= 0:
        raise InvalidAmountError("Restock amount must be positive.")
    happened_at = _timestamp(when)
    with connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET quantity_on_hand = quantity_on_hand + ?
            WHERE id = ?
            """,
            (amount, product_id),
        )
        if cursor.rowcount == 0:
            raise UnknownProductError(f"Unknown product {product_id}.")
        _insert_movement(connection, product_id, amount, "restock", happened_at)


def adjust_stock(
    connection: sqlite3.Connection,
    product_id: int,
    amount: int,
    when: str | None = None,
) -> None:
    """Apply a signed stock change and log one adjustment movement.

    An amount of zero is refused. A change that would make stock negative
    raises NotEnoughStockError and leaves the database unchanged.
    """
    if amount == 0:
        raise InvalidAmountError("An adjustment cannot be zero.")
    happened_at = _timestamp(when)
    with connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET quantity_on_hand = quantity_on_hand + ?
            WHERE id = ? AND quantity_on_hand + ? >= 0
            """,
            (amount, product_id, amount),
        )
        if cursor.rowcount == 0:
            row = connection.execute(
                "SELECT id FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            if row is None:
                raise UnknownProductError(f"Unknown product {product_id}.")
            raise NotEnoughStockError("That adjustment would make stock negative.")
        _insert_movement(connection, product_id, amount, "adjustment", happened_at)


def record_sale(
    connection: sqlite3.Connection,
    lines: list[tuple[int, int]],
    when: str | None = None,
) -> int:
    """Record a sale, its lines, the stock reductions, and one movement per line.

    lines is a list of (product_id, quantity) pairs. Each line stores the
    product's current price. Any failure rolls the whole sale back.
    """
    if not lines:
        raise InvalidAmountError("A sale needs at least one line.")
    happened_at = _timestamp(when)
    with connection:
        cursor = connection.execute(
            "INSERT INTO sales (sold_at) VALUES (?)",
            (happened_at,),
        )
        sale_id = cursor.lastrowid
        seen: set[int] = set()
        for product_id, quantity in lines:
            if quantity <= 0:
                raise InvalidAmountError("Sale quantity must be positive.")
            if product_id in seen:
                raise DuplicateSaleLineError(
                    "The same product cannot appear twice in one sale."
                )
            seen.add(product_id)
            row = connection.execute(
                """
                SELECT unit_price_cents, quantity_on_hand
                FROM products
                WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if row is None:
                raise UnknownProductError(f"Unknown product {product_id}.")
            if row["quantity_on_hand"] < quantity:
                raise NotEnoughStockError(
                    f"Not enough stock for product {product_id}."
                )
            connection.execute(
                """
                INSERT INTO sale_items (
                    sale_id, product_id, quantity, unit_price_cents
                ) VALUES (?, ?, ?, ?)
                """,
                (sale_id, product_id, quantity, row["unit_price_cents"]),
            )
            updated = connection.execute(
                """
                UPDATE products
                SET quantity_on_hand = quantity_on_hand - ?
                WHERE id = ? AND quantity_on_hand >= ?
                """,
                (quantity, product_id, quantity),
            )
            if updated.rowcount == 0:
                raise NotEnoughStockError(
                    f"Not enough stock for product {product_id}."
                )
            _insert_movement(connection, product_id, -quantity, "sale", happened_at)
        return sale_id


def backup_database(connection: sqlite3.Connection, destination: str | Path) -> None:
    """Copy the open database with SQLite's backup API."""
    with closing(sqlite3.connect(destination)) as target:
        connection.backup(target)
