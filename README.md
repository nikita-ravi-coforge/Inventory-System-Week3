# Inventory system

A small SQLite inventory program. It tracks suppliers, products, sales, and stock changes. Prices are stored as whole cents and shown with two decimal places. A terminal menu searches the catalog, changes stock, records sales, prints reports, and backs up the database.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed_db.py
python main.py
```

`seed_db.py` creates the tables, loads the sample catalog, and prints:

```text
suppliers: 4
products: 12
sales: 5
sale_items: 12
stock_movements: 0
```

Run `seed_db.py` once on a new database file. Loading it again fails on the unique SKUs. Running `schema.sql` again does not delete rows.

The menu can search, look up a product, add a product, change a price, delete a product, restock, record a sale, print each report, and back up the database. Prices are entered as whole cents. Text typed where a number is required prints `Please enter a whole number.` and returns to the menu.

Version 1.1.0 prints one line before the menu. With the sample catalog that line is `Low stock: 4 products`. Version 1.0.0 has the same menu and does not print it. The tables are the same in both versions.

## Configuration

`INVENTORY_DB` is the database file. When it is unset, the file is `inventory.db` next to the code.

```bash
INVENTORY_DB=/tmp/inventory.db python main.py
```

## Sample reports

Stock value by supplier, highest first:

| Supplier | Value |
| --- | --- |
| Peak Outfitters | 854.79 |
| Lane Paper | 567.15 |
| Northwind Supply | 274.77 |
| Harbor Goods | 213.84 |

Low stock, largest shortfall first: Box of Nails short 7, Screwdriver short 4, Camp Lantern short 3, Pen Pack short 0.

Sales by product, highest revenue first, use the price stored on the sale line. Trail Tent is 1 unit and 159.99. Notebook is 13 units and 45.37. Nine products have sales.

Never sold, by name: Climbing Rope, Printer Paper, Screwdriver.

## A sale that fails halfway

The hammer has 20 on hand. The lantern has 2. Sales, sale items, and stock movements are empty.

```python
record_sale(connection, [(1, 2), (9, 5)], when="2026-04-01T12:00:00")
```

The hammer line fits, so inside the transaction the function inserts the sale, a hammer line for 2 units at 1299 cents, reduces the hammer to 18, and logs a sale movement of -2. The lantern line asks for 5 units. This is the output of that call:

```text
before
hammer quantity 20
lantern quantity 2
sales 0
sale_items 0
stock_movements 0
NotEnoughStockError: Not enough stock for product 9.
after
hammer quantity 20
lantern quantity 2
sales 0
sale_items 0
stock_movements 0
```

The hammer line was in the same `with connection` block, so it is rolled back with the error.

## Tests

```bash
pytest
ruff check .
```

Each test gets a new in-memory database. The current suite is 61 tests.

## Backup and restore

The menu copies the open database with SQLite's `backup` method. Restore by stopping the program and copying the backup file onto the `INVENTORY_DB` path, then starting the program again.

A backup of the sample database produced:

```text
integrity_check ok
suppliers: original 4 backup 4
products: original 12 backup 12
sales: original 5 backup 5
sale_items: original 12 backup 12
stock_movements: original 0 backup 0
```

## Docker

The image is `python:3.12.16-slim`. Dependencies are installed before the application code is copied, so a code change does not reinstall packages. `v1.0.0` has no low-stock banner. `v1.1.0` prints one. The tables are the same.

```bash
git checkout v1.0.0
docker build -t inventory:1.0.0 .
git checkout v1.1.0
docker build -t inventory:1.1.0 .
```

Both builds finished. Each ended with `DONE`.

```bash
docker run --rm -it \
  -e INVENTORY_DB=/data/inventory.db \
  -v inventory-data:/data \
  inventory:1.1.0
```

One container writes the sample catalog. A second container reads the same volume:

```bash
docker volume rm -f inventory-data
docker run --rm \
  -e INVENTORY_DB=/data/inventory.db \
  -v inventory-data:/data \
  inventory:1.1.0 python seed_db.py
docker run --rm \
  -e INVENTORY_DB=/data/inventory.db \
  -v inventory-data:/data \
  inventory:1.1.0 python -c "from contextlib import closing; from inventory_db import connect, db_path, table_counts
with closing(connect(db_path())) as connection:
    for name, count in table_counts(connection).items():
        print(f'{name}: {count}')"
```

The second container printed:

```text
suppliers: 4
products: 12
sales: 5
sale_items: 12
stock_movements: 0
```

## Rollback

`v1.1.0` does not change the tables. Open the same volume with `v1.0.0`.

```bash
printf '0\n' | docker run --rm -i \
  -e INVENTORY_DB=/data/inventory.db \
  -v inventory-data:/data \
  inventory:1.1.0
printf '0\n' | docker run --rm -i \
  -e INVENTORY_DB=/data/inventory.db \
  -v inventory-data:/data \
  inventory:1.0.0
```

`v1.1.0` started with `Low stock: 4 products`, then the menu, then `Goodbye.` `v1.0.0` printed the menu with no banner, then `Goodbye.` The row counts were still 4, 12, 5, 12, and 0.

## Self-review

If I rebuilt this, I would give every seeded product an opening stock movement. The assignment requires `stock_movements` to start empty, so the seed is a snapshot of current stock plus past sales, and the log starts with the first restock, adjustment, or sale. That is honest about the requirement, and it is also the part I trust least: a reader cannot rebuild the on-hand quantity from the log. An opening balance row would make the snapshot and the log the same story.

I would also stop asking the menu for whole cents. The database should keep cents, and the menu should accept a decimal price and convert it with `Decimal`. The current prompt is simple, and it is easy to type 12.99 where the program expects 1299.

The check I want from a reviewer is `isolation_level="DEFERRED"` in `connect()`. Python 3.12 opens SQLite in autocommit unless that is set, and then `with connection` would commit each statement on its own. The failed sale above was run on Python 3.9. The image is Python 3.12.16, and the `docker-build` job runs the same tests inside that image. That job is the proof that the rollback still holds on the version we ship. I want someone to confirm the job is actually running `pytest` in the image, and not only on the runner.
