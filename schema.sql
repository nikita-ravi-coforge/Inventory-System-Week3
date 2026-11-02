-- Running this file again is safe: every statement is IF NOT EXISTS, and nothing is dropped or inserted.

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers (id) ON DELETE RESTRICT,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0),
    reorder_level INTEGER NOT NULL CHECK (reorder_level >= 0)
) STRICT;

-- Used by the product lookup join and the stock-value-by-supplier report.
CREATE INDEX IF NOT EXISTS idx_products_supplier_id ON products (supplier_id);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY,
    sold_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY,
    sale_id INTEGER NOT NULL REFERENCES sales (id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
) STRICT;

-- Used when checking sales history, totaling units sold, and finding never-sold products.
CREATE INDEX IF NOT EXISTS idx_sale_items_product_id ON sale_items (product_id);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    quantity_change INTEGER NOT NULL CHECK (quantity_change != 0),
    reason TEXT NOT NULL CHECK (reason IN ('restock', 'adjustment', 'sale')),
    happened_at TEXT NOT NULL
) STRICT;
