# Inventory system plan

This plan is the design for the program. Code that follows it lands in pull requests, after this file.

The program is a small SQLite inventory tool. It tracks suppliers, products, sales, and stock changes. A terminal menu searches the catalog, records stock changes and sales, prints reports, and backs up the database. Money is stored as whole cents and shown with two decimal places.

This machine has SQLite 3.54.0, which is newer than 3.37, so every table is `STRICT`. The Docker image pins Python 3.12. Local Python is 3.9.6, so modules start with `from __future__ import annotations` and the code stays valid on both.

## Tables

Every table is created with `CREATE TABLE IF NOT EXISTS`. Indexes use `CREATE INDEX IF NOT EXISTS`. The schema file contains no `DROP` and no `INSERT`, so running it again does nothing to existing rows.

### suppliers

A supplier name is shared by many products, so it lives in one row.

| Column | Constraints | Why |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Stable id for the product foreign key |
| name | TEXT NOT NULL UNIQUE | Required, and two suppliers cannot share a name |

### products

The catalog. Current stock lives here. Price is integer cents.

| Column | Constraints | Why |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Referenced by sale lines and stock movements |
| sku | TEXT NOT NULL UNIQUE | Business key. The database rejects a duplicate SKU |
| name | TEXT NOT NULL | Required label |
| category | TEXT NOT NULL | Required, and used as a search filter |
| supplier_id | INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT | Every product belongs to a real supplier |
| unit_price_cents | INTEGER NOT NULL CHECK (unit_price_cents >= 0) | No negative price |
| quantity_on_hand | INTEGER NOT NULL CHECK (quantity_on_hand >= 0) | No negative stock |
| reorder_level | INTEGER NOT NULL CHECK (reorder_level >= 0) | Low stock means quantity at or below this level |

`idx_products_supplier_id` on `products(supplier_id)` supports the join in `get_product` and the stock-value report.

### sales

One header per checkout. The lines hang off this row, and the header is the row a failed sale rolls back.

| Column | Constraints | Why |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Referenced by each line |
| sold_at | TEXT NOT NULL | ISO-8601 time, passed in by the caller |

### sale_items

One row per product on a sale. The price is copied onto the line so a later price change leaves history alone.

| Column | Constraints | Why |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Identity for the line |
| sale_id | INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT | The line belongs to a real sale |
| product_id | INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT | A product that appears here cannot be deleted |
| quantity | INTEGER NOT NULL CHECK (quantity > 0) | A line sells at least one unit |
| unit_price_cents | INTEGER NOT NULL CHECK (unit_price_cents >= 0) | Price charged at the time of the sale |

`idx_sale_items_product_id` on `sale_items(product_id)` supports the delete check, the sales-by-product report, and the never-sold report.

### stock_movements

The log of quantity changes made through restock, adjust, and record-a-sale. The seed leaves this table empty. Sample sales are history, and `quantity_on_hand` is the current snapshot. Movements start when those three operations run.

| Column | Constraints | Why |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Identity for the log row |
| product_id | INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT | The change belongs to a real product |
| quantity_change | INTEGER NOT NULL CHECK (quantity_change != 0) | Signed change. Zero is not a movement |
| reason | TEXT NOT NULL CHECK (reason IN ('restock', 'adjustment', 'sale')) | Only those three reasons |
| happened_at | TEXT NOT NULL | ISO-8601 time, passed in by the caller |

A restock writes a positive change. A sale writes a negative change. An adjustment writes either sign, and the check rejects zero.

## Relationships

- A supplier has many products. `products.supplier_id` points at `suppliers.id`. Deleting a supplier that still has products fails.
- A sale has many sale items. `sale_items.sale_id` points at `sales.id`.
- A product has many sale items. `sale_items.product_id` points at `products.id` with `ON DELETE RESTRICT`, so the database rejects deleting a product that has been sold.
- A product has many stock movements. `stock_movements.product_id` points at `products.id` with `ON DELETE RESTRICT`. `delete_product` removes that product's movements in the same transaction, then deletes the product. If a sale line still points at the product, the product delete fails and the movement deletes roll back with it.

`connect()` runs `PRAGMA foreign_keys = ON` on every connection. SQLite leaves foreign keys off unless that pragma runs. The schema declares the keys. The connection turns checking on.

## Sample data

`load_sample_data` inserts this fixed set with `executemany` and placeholders. `seed_db.py` creates the tables, loads the data, and prints each table's row count.

Expected counts:

| Table | Rows |
| --- | --- |
| suppliers | 4 |
| products | 12 |
| sales | 5 |
| sale_items | 12 |
| stock_movements | 0 |

Suppliers: Northwind Supply, Harbor Goods, Peak Outfitters, Lane Paper.

Categories: Hardware, Office, Outdoor.

| id | SKU | Name | Category | Supplier | Cents | On hand | Reorder |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | HW-001 | Claw Hammer | Hardware | Northwind Supply | 1299 | 20 | 5 |
| 2 | HW-002 | Box of Nails | Hardware | Northwind Supply | 499 | 3 | 10 |
| 3 | HW-003 | Screwdriver | Hardware | Northwind Supply | 899 | 0 | 4 |
| 4 | OF-001 | Notebook | Office | Lane Paper | 349 | 40 | 15 |
| 5 | OF-002 | Pen Pack | Office | Lane Paper | 599 | 8 | 8 |
| 6 | OF-003 | Stapler | Office | Lane Paper | 1499 | 12 | 3 |
| 7 | OF-004 | Printer Paper | Office | Lane Paper | 799 | 25 | 10 |
| 8 | OD-001 | Trail Tent | Outdoor | Peak Outfitters | 15999 | 4 | 2 |
| 9 | OD-002 | Camp Lantern | Outdoor | Peak Outfitters | 2499 | 2 | 5 |
| 10 | OD-003 | Climbing Rope | Outdoor | Peak Outfitters | 1099 | 15 | 5 |
| 11 | HG-001 | Travel Mug | Outdoor | Harbor Goods | 999 | 10 | 4 |
| 12 | HG-002 | Water Bottle | Outdoor | Harbor Goods | 1899 | 6 | 4 |

Twelve products, three categories. Screwdriver, Printer Paper, and Climbing Rope appear on no sale. Box of Nails (short 7), Screwdriver (short 4), Camp Lantern (short 3), and Pen Pack (short 0) are at or below their reorder level.

Sales, with line prices copied from the product at seed time:

| Sale | Time | Lines |
| --- | --- | --- |
| 1 | 2026-01-05T10:00:00 | Hammer x2 @ 1299, Nails x5 @ 499, Notebook x3 @ 349 |
| 2 | 2026-01-12T14:30:00 | Pen Pack x4 @ 599, Stapler x1 @ 1499 |
| 3 | 2026-02-01T09:15:00 | Trail Tent x1 @ 15999, Camp Lantern x2 @ 2499 |
| 4 | 2026-02-14T16:45:00 | Travel Mug x3 @ 999, Water Bottle x2 @ 1899, Hammer x1 @ 1299 |
| 5 | 2026-03-01T11:00:00 | Notebook x10 @ 349, Pen Pack x2 @ 599 |

That is 12 lines across 5 sales.

### What the reports return

Stock value by supplier, highest first. Value is `unit_price_cents * quantity_on_hand`.

| Supplier | Cents | Display |
| --- | --- | --- |
| Peak Outfitters | 85479 | 854.79 |
| Lane Paper | 56715 | 567.15 |
| Northwind Supply | 27477 | 274.77 |
| Harbor Goods | 21384 | 213.84 |

Low stock, largest shortfall first. Units short is `reorder_level - quantity_on_hand`.

| Product | On hand | Reorder | Short |
| --- | --- | --- | --- |
| Box of Nails | 3 | 10 | 7 |
| Screwdriver | 0 | 4 | 4 |
| Camp Lantern | 2 | 5 | 3 |
| Pen Pack | 8 | 8 | 0 |

Sales by product, highest revenue first. Revenue uses the price stored on each sale line.

| Product | Units | Cents | Display |
| --- | --- | --- | --- |
| Trail Tent | 1 | 15999 | 159.99 |
| Camp Lantern | 2 | 4998 | 49.98 |
| Notebook | 13 | 4537 | 45.37 |
| Claw Hammer | 3 | 3897 | 38.97 |
| Water Bottle | 2 | 3798 | 37.98 |
| Pen Pack | 6 | 3594 | 35.94 |
| Travel Mug | 3 | 2997 | 29.97 |
| Box of Nails | 5 | 2495 | 24.95 |
| Stapler | 1 | 1499 | 14.99 |

Never sold, by name: Climbing Rope, Printer Paper, Screwdriver.

## Public functions

All of these live in `inventory_db.py`. Each takes the connection as its first argument. No function builds SQL by pasting a caller-supplied value into the statement text. Search assembles a list of fixed clause strings and joins them. Every value is bound with `?`.

`connect(database=":memory:")` returns a `sqlite3.Connection`. It sets `row_factory` to `sqlite3.Row`, runs `PRAGMA foreign_keys = ON`, and sets `isolation_level` to `"DEFERRED"`. Python 3.12 defaults to autocommit, which would make `with connection` commit each statement on its own. `DEFERRED` keeps a multi-step change in one transaction on 3.9 and on 3.12. Callers close the connection with `contextlib.closing`.

`init_db(connection)` runs `schema.sql` through `executescript`. `executescript` commits first, so it is called before any data transaction, during startup and in the test fixture.

`load_sample_data(connection)` inserts the rows above. It does not commit. The caller wraps it in `with connection`.

`table_counts(connection)` returns a dict of row counts for the five tables, in table order.

`format_cents(cents)` returns a string with two decimals, such as `"854.79"`.

`add_product(connection, sku, name, category, supplier_id, unit_price_cents, quantity_on_hand, reorder_level)` inserts one product and returns the new integer id. A duplicate SKU, an unknown supplier, or a negative price, quantity, or reorder level raises `sqlite3.IntegrityError`.

`get_product(connection, product_id)` returns one `Row` with the product columns plus `supplier_name` from a join, or `None` when the id is missing.

`change_price(connection, product_id, unit_price_cents)` sets the price and returns `True`. It returns `False` when the id is missing. A negative price raises `sqlite3.IntegrityError`.

`delete_product(connection, product_id)` returns `True` when the product is deleted and `False` when the id is missing. When any sale line points at the product it raises `ProductHasSalesError` and leaves every table unchanged. The body runs inside `with connection`.

`search_products(connection, text, category=None, max_price_cents=None, in_stock_only=False, low_stock_only=False)` returns a list of rows sorted by product name. A row matches when the name, SKU, or supplier name contains `text`, compared with `lower()` so ASCII case does not matter. The optional filters combine with `AND`. `in_stock_only` keeps `quantity_on_hand > 0`. `low_stock_only` keeps `quantity_on_hand <= reorder_level`. The search text `'; DROP TABLE products; --` is bound as a value, matches nothing, and the products table stays in place.

`report_stock_value_by_supplier(connection)` returns `supplier_name` and `stock_value_cents`, highest value first.

`report_low_stock(connection)` returns `sku`, `name`, `quantity_on_hand`, `reorder_level`, and `units_short`, largest shortfall first.

`report_sales_by_product(connection)` returns `sku`, `name`, `units_sold`, and `revenue_cents` for products that have at least one sale line, highest revenue first.

`report_never_sold(connection)` returns `sku` and `name` for products with no sale line, sorted by name.

`backup_database(connection, destination)` copies the open database with `Connection.backup` into the destination path.

`db_path()` returns the `INVENTORY_DB` environment variable, or `inventory.db` next to the code when the variable is unset.

### Errors the menu translates

| Situation | Error |
| --- | --- |
| Duplicate SKU, unknown supplier, negative price or quantity | `sqlite3.IntegrityError` |
| Delete of a product that has sale lines | `ProductHasSalesError` |
| Restock amount of zero or less, adjustment of zero, empty sale, sale quantity below 1 | `InvalidAmountError` |
| Adjustment or sale that would push stock below zero | `NotEnoughStockError` |
| Unknown product id on adjust, restock, or sale | `UnknownProductError` |
| Same product twice on one sale | `DuplicateSaleLineError` |
| Letters typed where a number is required | `ValueError` from `int()` |

These inventory errors subclass `Exception` directly. The menu catches each one by name, plus `sqlite3.IntegrityError`. It does not catch bare `Exception`.

## Restock, adjust, and record a sale

Each one is a single `with connection` block. A helper used inside that block, including `_insert_movement`, only runs statements. It does not call `commit()`.

`when` is a `str` argument. When the caller omits it, the function uses `datetime.now(timezone.utc).isoformat(timespec="seconds")`.

### Restock

`restock(connection, product_id, amount, when=None)`

1. If `amount` is less than or equal to zero, raise `InvalidAmountError` before opening the transaction.
2. Inside `with connection`, add `amount` to `quantity_on_hand` for that product.
3. If no row was updated, raise `UnknownProductError`.
4. Insert one `stock_movements` row with that positive amount, reason `restock`, and `when`.
5. Leaving the block on success commits both the update and the log. Leaving on an exception rolls both back.

### Adjust

`adjust_stock(connection, product_id, amount, when=None)`

1. If `amount` is zero, raise `InvalidAmountError` before opening the transaction.
2. Inside `with connection`, add `amount` only when `quantity_on_hand + amount >= 0`.
3. If no row was updated, look the product up. A missing id raises `UnknownProductError`. A product that is present raises `NotEnoughStockError`, because the new quantity would be negative.
4. Insert one movement with the signed amount and reason `adjustment`.
5. The raised error exits the `with` block, so the update is rolled back and no movement row remains.

### Record a sale

`record_sale(connection, lines, when=None)` takes a list of `(product_id, quantity)` pairs and returns the new sale id.

1. If `lines` is empty, raise `InvalidAmountError` before opening the transaction.
2. Inside `with connection`, insert the `sales` row and keep `lastrowid`.
3. For each line, in order:
   - A quantity below 1 raises `InvalidAmountError`.
   - A product id already seen in this sale raises `DuplicateSaleLineError`.
   - Load the product. A missing id raises `UnknownProductError`.
   - If `quantity_on_hand` is less than the requested quantity, raise `NotEnoughStockError`.
   - Insert the sale line using the product's current `unit_price_cents`.
   - Subtract the quantity from stock, with a `WHERE` clause that also requires enough stock.
   - Insert a movement with `quantity_change` equal to the negative of the quantity and reason `sale`.
4. Any exception leaves the `with` block. SQLite rolls back the sale header, every line already inserted, every stock update, and every movement from this attempt.
5. A normal exit commits all of those writes and returns the sale id.

### Failed sale, for the README

Start with two products and empty sales tables:

| id | SKU | Name | On hand | Cents |
| --- | --- | --- | --- | --- |
| 1 | HW-001 | Claw Hammer | 20 | 1299 |
| 9 | OD-002 | Camp Lantern | 2 | 2499 |

`sales`, `sale_items`, and `stock_movements` each have 0 rows.

```python
record_sale(connection, [(1, 2), (9, 5)], when="2026-04-01T12:00:00")
```

The hammer line fits. Inside the transaction the function inserts the sale, inserts a hammer line for 2 units at 1299 cents, reduces the hammer from 20 to 18, and logs a sale movement of -2. The lantern line then asks for 5 units while 2 are on hand, and the function raises:

```text
NotEnoughStockError: Not enough stock for product 9.
```

After the exception, the hammer is back to 20, the lantern is still 2, and the three tables are empty again. The writes from the hammer line were part of the same transaction, so they leave with the error.

## Menu

`main.py` loops on a numbered menu:

1. Search, with optional category, maximum price, in-stock, and low-stock filters
2. Look up a product by id
3. Add a product
4. Restock
5. Record a sale, one product and quantity per line, blank line to finish
6. Stock value by supplier
7. Low stock
8. Sales by product
9. Never sold
10. Back up the database
0. Quit

Each database error above prints a short sentence and returns to the menu. Text typed where a number is required prints `Please enter a whole number.` Reports print money with `format_cents`. The process stays up.

Version 1.1.0 prints one banner line before the loop, using the low-stock report:

```text
Low stock: 4 products
```

Version 1.0.0 has the same menu and no banner. The banner reads data. It does not change the schema, so a 1.0.0 process can open a database written by 1.1.0.

## Container

`INVENTORY_DB` is the database path. Unset, it is `inventory.db` beside the code. In Docker it is `/data/inventory.db`, with a named volume mounted at `/data`.

Dockerfile order, so dependency installs stay cached when only the code changes:

1. `FROM python:3.12.<patch>-slim` with the patch tag that exists on Docker Hub at build time
2. `WORKDIR /app`
3. `COPY requirements.txt .`
4. `RUN pip install --no-cache-dir -r requirements.txt`
5. `COPY . .`
6. `CMD ["python", "main.py"]`

`.dockerignore` excludes `.git`, virtualenvs, caches, and `*.db`. It keeps the source and the tests, because CI runs pytest inside the image.

Run the menu:

```bash
docker run --rm -it -e INVENTORY_DB=/data/inventory.db -v inventory-data:/data inventory:1.0.0
```

A second container that mounts `inventory-data` sees the same file.

## Tests

pytest, with a new in-memory database on every test. The `connection` fixture calls `connect(":memory:")` and `init_db`. Tests do not share a file.

Collected cases, including each parametrized input:

- Add product returns the new id
- Duplicate SKU is refused
- Unknown supplier is refused
- Negative price is refused
- Negative quantity is refused
- Change price updates the stored cents
- Change price of a missing product returns false
- A product with a sale line cannot be deleted, and the row remains
- A product with no sale line can be deleted
- Get product returns the supplier name from the join
- Search by name, by SKU, and by supplier name, ignoring case
- Category filter, maximum price, in stock only, low stock only
- Those filters combined
- The text `'; DROP TABLE products; --` matches nothing and the table still has its rows
- Restock adds the amount and writes one restock movement
- Restock of 0 is refused
- Restock of a negative amount is refused
- An adjustment that would make stock negative is refused
- That refused adjustment leaves the quantity and the movement count unchanged
- A sale stores each line at the current price, reduces stock, and writes one sale movement per line
- A sale that fails on a later line leaves no sale, no lines, no movements, and the original quantities
- A sale of an unknown product leaves the same empty trail
- The same product twice on one sale leaves the same empty trail
- Each of the four reports matches the sample rows above
- A backup into `tmp_path` returns `ok` from `PRAGMA integrity_check` and the same five counts
- Running the schema a second time keeps existing rows
- `PRAGMA foreign_keys` is 1 on a connection from `connect()`

That is more than 23 collected tests. New behavior is written as a failing test first, then the function that makes it pass.

## Git and CI

The only commit made straight to `main` is the setup commit: `.gitignore`, `conftest.py`, `requirements.txt`, and this plan. Every later change arrives through a pull request. Commit subjects start with a verb. The branch is deleted after the merge.

| Order | Branch | What it brings |
| --- | --- | --- |
| 1 | feature/database-and-seed | Schema, seed, `connect`, `init_db`, sample data, schema tests, the pytest and ruff CI job |
| 2 | feature/products-and-search | Product functions, search, and their tests |
| 3 | feature/reports | The four reports and their tests |
| 4 | feature/stock-and-sales | Restock, adjust, record a sale, and their tests |
| 5 | feature/menu-and-container | Menu, backup, Dockerfile, `.dockerignore`, the `docker-build` CI job, changelog entry 1.0.0, README |
| 6 | feature/low-stock-banner | Startup banner, changelog entry 1.1.0, the rollback write-up |

CI on the first four pull requests runs ruff and pytest on Python 3.12. The fifth pull request adds a `docker-build` job that builds the image and runs pytest inside it. Each pull request is merged only after that run is green. The title and the two or three sentence body say what changed and how it was tested.

The `docker-build` job waits for the Dockerfile, which arrives in the fifth pull request. The earlier pull requests still have a real CI run.

## Release

1. Merge pull requests 1 through 5.
2. Tag that commit `v1.0.0`. Build and tag the image `inventory:1.0.0`.
3. Branch `feature/low-stock-banner` from that commit. Open the sixth pull request.
4. Merge it after CI is green. Tag the merge `v1.1.0`. Build and tag the image `inventory:1.1.0`.
5. Both tags are pushed to GitHub. `CHANGELOG.md` has an entry for 1.0.0 and an entry for 1.1.0.

Rollback is the 1.0.0 image pointed at the same volume. The banner is the only difference between the versions, so the file written by 1.1.0 still opens under 1.0.0 and the row counts stay the same.

Backup uses `Connection.backup`. Restore is: stop the program, copy the backup file onto the `INVENTORY_DB` path, start the program again. The README shows `PRAGMA integrity_check` returning `ok` and the five row counts matching the original. The README also pastes the real output of the image build, the second-container persistence check, and the 1.1.0 to 1.0.0 rollback.

The README self-review covers a rebuild from scratch, and one review question: confirm that `isolation_level="DEFERRED"` in `connect()` is what keeps a failed sale atomic on the Python 3.12 image.
