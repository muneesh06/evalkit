"""Builds store.db — the small SQLite database our text-to-SQL eval runs against.

Kept deliberately small (4 tables, ~30 rows) so you can eyeball every answer by
hand. That matters: you can only trust a golden set you were able to verify
yourself.

    python db/build_db.py
"""

import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "store.db"

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    city    TEXT NOT NULL,
    signup_date TEXT NOT NULL
);

CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    REAL NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT NOT NULL,
    status      TEXT NOT NULL
);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL
);
"""

CUSTOMERS = [
    (1, "Ava Patel",     "Atlanta",  "2024-01-15"),
    (2, "Ben Ortiz",     "Chicago",  "2024-02-02"),
    (3, "Chen Wei",      "Atlanta",  "2024-02-20"),
    (4, "Dana Kim",      "Seattle",  "2024-03-11"),
    (5, "Eli Novak",     "Chicago",  "2024-05-30"),
    (6, "Farah Haddad",  "Atlanta",  "2024-06-18"),
    # Deliberately has no orders — makes the "never ordered" question answerable.
    (7, "Grace Lund",    "Atlanta",  "2024-07-22"),
]

PRODUCTS = [
    (1, "Espresso Machine", "Appliances", 499.00),
    (2, "Burr Grinder",     "Appliances", 149.50),
    (3, "Pour Over Kettle", "Accessories", 79.00),
    (4, "Ethiopia Beans",   "Coffee",      22.00),
    (5, "Colombia Beans",   "Coffee",      18.00),
    (6, "Ceramic Mug",      "Accessories", 14.00),
]

ORDERS = [
    (1, 1, "2024-03-01", "shipped"),
    (2, 1, "2024-04-12", "shipped"),
    (3, 2, "2024-03-15", "cancelled"),
    (4, 3, "2024-04-02", "shipped"),
    (5, 4, "2024-05-20", "pending"),
    (6, 1, "2024-06-05", "pending"),
    (7, 6, "2024-07-01", "shipped"),
    (8, 5, "2024-07-04", "shipped"),
]

# (id, order_id, product_id, quantity)
ORDER_ITEMS = [
    (1,  1, 1, 1),
    (2,  1, 4, 2),
    (3,  2, 5, 3),
    (4,  3, 2, 1),
    (5,  4, 6, 4),
    (6,  4, 4, 1),
    (7,  5, 3, 2),
    (8,  6, 5, 1),
    (9,  6, 6, 2),
    (10, 7, 1, 1),
    (11, 7, 2, 1),
    (12, 8, 4, 5),
]


def main() -> None:
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)", CUSTOMERS)
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", PRODUCTS)
    con.executemany("INSERT INTO orders VALUES (?,?,?,?)", ORDERS)
    con.executemany("INSERT INTO order_items VALUES (?,?,?,?)", ORDER_ITEMS)
    con.commit()
    con.close()
    print(f"built {DB} — 4 tables, "
          f"{len(CUSTOMERS)} customers, {len(PRODUCTS)} products, "
          f"{len(ORDERS)} orders, {len(ORDER_ITEMS)} line items")


if __name__ == "__main__":
    main()
