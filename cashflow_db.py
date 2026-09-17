"""
cashflow_db.py
----------------
Modul database SQLite terpisah untuk aplikasi Cashflow (Kivy).

File database (cashflow.db) akan otomatis dibuat di folder yang sama
dengan modul ini saat pertama kali dijalankan.

Struktur tabel:
    books
        id      INTEGER PRIMARY KEY
        name    TEXT UNIQUE

    transactions
        id          INTEGER PRIMARY KEY
        book_id     INTEGER  (FK -> books.id)
        tx_type     TEXT     ('Menerima' / 'Membayar')
        date_str    TEXT
        amount      REAL
        note        TEXT
        created_at  TEXT     (timestamp otomatis)
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cashflow.db")


class CashflowDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id    INTEGER NOT NULL,
                tx_type    TEXT NOT NULL CHECK (tx_type IN ('Menerima', 'Membayar')),
                date_str   TEXT NOT NULL,
                time_str   TEXT,
                amount     REAL NOT NULL,
                note       TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                edited_at  TEXT,
                FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
            )
        """)
        conn.commit()

        # Migrasi untuk database lama (dibuat sebelum kolom time_str / edited_at ada)
        # supaya data yang sudah tersimpan tidak hilang.
        existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(transactions)").fetchall()}
        if "time_str" not in existing_cols:
            cur.execute("ALTER TABLE transactions ADD COLUMN time_str TEXT")
        if "edited_at" not in existing_cols:
            cur.execute("ALTER TABLE transactions ADD COLUMN edited_at TEXT")
        conn.commit()

        # Buku kas default, hanya dibuat kalau tabel books masih kosong
        cur.execute("SELECT COUNT(*) FROM books")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO books (name) VALUES (?)", ("Buku Kas Utama",))
            conn.commit()

        conn.close()

    def _get_book_id(self, conn, book_name):
        row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
        return row["id"] if row else None

    # ------------------------------------------------------------------ #
    # Buku Kas (books)
    # ------------------------------------------------------------------ #
    def get_books(self):
        """Mengembalikan list nama semua buku kas, urut sesuai dibuat."""
        conn = self._get_conn()
        rows = conn.execute("SELECT name FROM books ORDER BY id").fetchall()
        conn.close()
        return [r["name"] for r in rows]

    def add_book(self, name: str) -> bool:
        """Menambah buku kas baru. Return False jika nama sudah ada."""
        conn = self._get_conn()
        try:
            conn.execute("INSERT INTO books (name) VALUES (?)", (name,))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def rename_book(self, old_name: str, new_name: str) -> bool:
        """Mengubah nama buku kas. Return False jika nama baru sudah dipakai."""
        conn = self._get_conn()
        try:
            conn.execute("UPDATE books SET name = ? WHERE name = ?", (new_name, old_name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def delete_book(self, name: str):
        """Menghapus buku kas beserta seluruh transaksinya (cascade)."""
        conn = self._get_conn()
        conn.execute("DELETE FROM books WHERE name = ?", (name,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # Transaksi (transactions)
    # ------------------------------------------------------------------ #
    def get_transactions(self, book_name: str):
        """Mengembalikan list dict transaksi milik satu buku kas."""
        conn = self._get_conn()
        book_id = self._get_book_id(conn, book_name)
        if book_id is None:
            conn.close()
            return []

        rows = conn.execute(
            """SELECT id, tx_type, date_str, time_str, amount, note, edited_at
               FROM transactions
               WHERE book_id = ?
               ORDER BY id""",
            (book_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_transaction(self, book_name: str, tx_type: str, date_str: str,
                         time_str: str, amount: float, note: str) -> int:
        """Menambah transaksi baru, mengembalikan id transaksi yang baru dibuat.
        edited_at sengaja dibiarkan kosong karena ini transaksi baru, bukan hasil edit."""
        conn = self._get_conn()
        book_id = self._get_book_id(conn, book_name)
        if book_id is None:
            conn.close()
            raise ValueError(f"Buku kas '{book_name}' tidak ditemukan")

        cur = conn.execute(
            """INSERT INTO transactions (book_id, tx_type, date_str, time_str, amount, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (book_id, tx_type, date_str, time_str, amount, note),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id

    def update_transaction(self, tx_id: int, tx_type: str, date_str: str,
                            time_str: str, amount: float, note: str) -> str:
        """Mengubah transaksi yang sudah ada dan mencatat kapan diedit.
        Mengembalikan string waktu edit (edited_at) yang baru disimpan."""
        edited_at = datetime.now().strftime("%d-%b-%Y %H:%M")
        conn = self._get_conn()
        conn.execute(
            """UPDATE transactions
               SET tx_type = ?, date_str = ?, time_str = ?, amount = ?, note = ?, edited_at = ?
               WHERE id = ?""",
            (tx_type, date_str, time_str, amount, note, edited_at, tx_id),
        )
        conn.commit()
        conn.close()
        return edited_at

    def delete_transaction(self, tx_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    # Test cepat: jalankan file ini langsung untuk membuat cashflow.db
    db = CashflowDB()
    print("Database siap di:", db.db_path)
    print("Buku kas:", db.get_books())
