import sqlite3
from contextlib import closing

from config import DATABASE_NAME


def get_connection():
    return sqlite3.connect(DATABASE_NAME)


def init_db():
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        # Users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Payments
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments(
            payment_id TEXT PRIMARY KEY,
            telegram_id INTEGER,
            amount REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Orders (generic digital products/services)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            product TEXT,
            amount REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()


# -----------------------
# Users
# -----------------------

def add_user(user):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT OR IGNORE INTO users
        (telegram_id, username, first_name)
        VALUES (?, ?, ?)
        """, (
            user.id,
            user.username,
            user.first_name
        ))

        conn.commit()


def get_user(user_id):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT *
        FROM users
        WHERE telegram_id=?
        """, (user_id,))

        return cur.fetchone()


def get_balance(user_id):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT balance
        FROM users
        WHERE telegram_id=?
        """, (user_id,))

        row = cur.fetchone()

        if row:
            return row[0]

        return 0.0


def update_balance(user_id, amount):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        UPDATE users
        SET balance=?
        WHERE telegram_id=?
        """, (
            amount,
            user_id
        ))

        conn.commit()


def add_balance(user_id, amount):
    balance = get_balance(user_id)

    update_balance(
        user_id,
        balance + amount
    )


def deduct_balance(user_id, amount):
    balance = get_balance(user_id)

    if balance < amount:
        return False

    update_balance(
        user_id,
        balance - amount
    )

    return True


# -----------------------
# Payments
# -----------------------

def create_payment(payment_id, user_id, amount):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO payments
        (payment_id, telegram_id, amount, status)
        VALUES (?, ?, ?, ?)
        """, (
            payment_id,
            user_id,
            amount,
            "pending"
        ))

        conn.commit()


def complete_payment(payment_id):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        UPDATE payments
        SET status='paid'
        WHERE payment_id=?
        """, (payment_id,))

        conn.commit()


# -----------------------
# Orders
# -----------------------

def create_order(user_id, product, amount):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO orders
        (telegram_id, product, amount, status)
        VALUES (?, ?, ?, ?)
        """, (
            user_id,
            product,
            amount,
            "Pending"
        ))

        conn.commit()


def get_orders(user_id):
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT
            id,
            product,
            amount,
            status,
            created_at
        FROM orders
        WHERE telegram_id=?
        ORDER BY id DESC
        """, (user_id,))

        return cur.fetchall()
