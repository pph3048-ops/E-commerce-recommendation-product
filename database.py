"""
database.py  –  Database Initialization & Connection Management

Handles all SQLite setup:
  - Schema creation (users, products, interactions)
  - Sample data seeding (runs once on first launch)
  - Connection factory used by app.py and recommender.py
"""

import sqlite3
from datetime import datetime, timedelta

# Path to the SQLite database file (created in the project root)
DATABASE = 'ecommerce.db'


def get_db():
    """
    Open and return a new SQLite connection.
    row_factory = sqlite3.Row lets us access columns by name, e.g. row['name'].
    WAL mode and a generous timeout prevent 'database is locked' errors.
    """
    conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    """
    Create tables and seed sample data if the database is empty.
    Called once at Flask application startup.
    """
    conn = get_db()
    cursor = conn.cursor()

    # ── Create tables (idempotent) ─────────────────────────────────────────
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE,
            password_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            price       REAL    NOT NULL,
            description TEXT,
            image       TEXT,
            stock       INTEGER DEFAULT 100
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            product_id  INTEGER NOT NULL,
            action      TEXT    NOT NULL,   -- click | wishlist | rate | purchase | search
            rating      REAL,              -- only for 'rate' action, value 1-5
            timestamp   TEXT    NOT NULL,
            FOREIGN KEY (user_id)    REFERENCES users(user_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            status         TEXT    NOT NULL DEFAULT 'placed',
            total          REAL    NOT NULL,
            discount       REAL    NOT NULL DEFAULT 0,
            coupon_code    TEXT,
            address        TEXT    NOT NULL,
            payment_method TEXT    NOT NULL DEFAULT 'cod',
            payment_id     TEXT,
            created_at     TEXT    NOT NULL,
            updated_at     TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity   INTEGER NOT NULL DEFAULT 1,
            unit_price REAL    NOT NULL,
            FOREIGN KEY (order_id)   REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS coupons (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            code           TEXT    NOT NULL UNIQUE,
            discount_type  TEXT    NOT NULL,
            discount_value REAL    NOT NULL,
            min_order      REAL    NOT NULL DEFAULT 0,
            max_uses       INTEGER NOT NULL DEFAULT 1000,
            used_count     INTEGER NOT NULL DEFAULT 0,
            expires_at     TEXT,
            is_active      INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS flash_sales (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id     INTEGER NOT NULL UNIQUE,
            sale_price     REAL    NOT NULL,
            original_price REAL    NOT NULL,
            discount_pct   INTEGER NOT NULL,
            end_time       TEXT    NOT NULL,
            is_active      INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
    ''')
    conn.commit()

    # ── Indexes for query performance ─────────────────────────────────────
    cursor.executescript('''
        CREATE INDEX IF NOT EXISTS idx_interactions_user    ON interactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_product ON interactions(product_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_action  ON interactions(action);
        CREATE INDEX IF NOT EXISTS idx_interactions_ts      ON interactions(timestamp);
        CREATE INDEX IF NOT EXISTS idx_products_category    ON products(category);
        CREATE INDEX IF NOT EXISTS idx_products_name        ON products(name);
        CREATE INDEX IF NOT EXISTS idx_interactions_rating  ON interactions(product_id, rating);
    ''')
    conn.commit()

    # ── Migration: add new columns to existing DBs ─────────────────────────
    # Note: SQLite ALTER TABLE does not support UNIQUE constraints inline;
    # uniqueness for email is enforced at the application layer (app.py).
    for col, defn in [('password_hash', 'TEXT'), ('email', 'TEXT'),
                       ('image', 'TEXT')]:
        if col == 'image':
            try:
                cursor.execute('ALTER TABLE products ADD COLUMN image TEXT')
                conn.commit()
            except Exception:
                pass
            continue
    for col, defn in [('password_hash', 'TEXT'), ('email', 'TEXT')]:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {col} {defn}')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists – safe to ignore

    # ── Migration: add stock to products ──────────────────────────────────
    try:
        cursor.execute('ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 100')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already exists

    # ── Populate NULL stock values with random quantities ──────────────────
    conn.execute("UPDATE products SET stock = (ABS(RANDOM()) % 91 + 10) WHERE stock IS NULL")
    conn.commit()

    # ── Seed demo coupon codes (once) ──────────────────────────────────────
    if conn.execute('SELECT COUNT(*) FROM coupons').fetchone()[0] == 0:
        exp = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')
        demo_coupons = [
            ('SAVE10',    'percent', 10,  0,    1000, exp),
            ('FLAT50',    'fixed',   50,  200,  500,  exp),
            ('FLAT100',   'fixed',   100, 500,  200,  exp),
            ('WELCOME20', 'percent', 20,  0,    2000, exp),
            ('BIGDEAL',   'percent', 25,  1000, 100,  exp),
        ]
        cursor.executemany(
            'INSERT INTO coupons (code, discount_type, discount_value, min_order, max_uses, expires_at)'
            ' VALUES (?,?,?,?,?,?)',
            demo_coupons
        )
        conn.commit()

    # ── Seed flash sales (once, 48-hour window) ────────────────────────────
    if conn.execute('SELECT COUNT(*) FROM flash_sales').fetchone()[0] == 0:
        prods = conn.execute(
            'SELECT product_id, price FROM products WHERE price > 100 ORDER BY RANDOM() LIMIT 12'
        ).fetchall()
        end_time = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
        for p in prods:
            sale_price = round(p['price'] * 0.70, 2)
            try:
                cursor.execute(
                    'INSERT OR IGNORE INTO flash_sales'
                    ' (product_id, sale_price, original_price, discount_pct, end_time)'
                    ' VALUES (?,?,?,?,?)',
                    (p['product_id'], sale_price, p['price'], 30, end_time)
                )
            except Exception:
                pass
        conn.commit()

    # ── Migration: add loyalty_points to users ─────────────────────────────
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN loyalty_points INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already exists

    # Seed only once (guard: check user count)
    user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if user_count == 0:
        # Load real Amazon product & review data from CSV files
        from load_dataset import load_csv_to_db
        load_csv_to_db(conn)

    conn.close()


# NOTE: hardcoded _seed_data() replaced by load_dataset.load_csv_to_db()
# which reads data/amazon_products.csv and data/amazon_reviews.csv instead.
