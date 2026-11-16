# migrate_email_hmac.py
"""Migration script to add deterministic email HMAC support.

* Creates a timestamped backup of the existing SQLite database.
* Adds an ``email_hmac`` column to the ``users`` table if missing.
* Populates the column for all existing users by decrypting the stored
  ``email_encrypted`` value and computing ``email_hmac(email)``.
* Detects duplicate HMAC values and aborts with a clear error.
* Creates a UNIQUE index on ``email_hmac``.
* All operations run inside a transaction; any failure rolls back the
  schema changes.
* The script is safe to re‑run – if the column and index already exist
  and all rows have non‑NULL ``email_hmac`` values, it exits without changes.

Run with ``python migrate_email_hmac.py``. **Do not** run automatically
from the application.
"""
import os
import sys
import sqlite3
import datetime
import shutil
from backend.security import email_hmac, decrypt_data
from backend.database import DB_PATH

def backup_database(db_path: str) -> str:
    """Create a timestamped copy of the SQLite database using the backup API.
    Returns the path to the backup file.
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}.sqlite"
    # Use SQLite backup API for a consistent copy
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return backup_path

def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
    return cur.fetchone() is not None

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    print("Backing up database...")
    backup_path = backup_database(DB_PATH)
    print(f"Backup created at {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Start transaction
    conn.isolation_level = None  # autocommit off
    cur.execute('BEGIN')
    try:
        # Ensure column exists
        if not column_exists(conn, 'users', 'email_hmac'):
            cur.execute('ALTER TABLE users ADD COLUMN email_hmac TEXT')
            print('Added column email_hmac')

        # Populate HMAC for rows where it is NULL
        cur.execute('SELECT id, email_encrypted FROM users WHERE email_hmac IS NULL')
        rows = cur.fetchall()
        hmac_set = set()
        for row in rows:
            user_id = row['id']
            encrypted = row['email_encrypted']
            # Decrypt; if fails, abort
            try:
                email = decrypt_data(encrypted)
            except Exception as e:
                raise RuntimeError(f"Failed to decrypt email for user id {user_id}: {e}")
            hmac_val = email_hmac(email)
            # Check for existing HMAC in other rows to avoid duplicate index violation
            cur.execute('SELECT id FROM users WHERE email_hmac = ? AND id != ?', (hmac_val, user_id))
            duplicate = cur.fetchone()
            if duplicate:
                raise RuntimeError(f'Duplicate HMAC detected for email {email} (conflicts with user id {duplicate["id"]})')
            if hmac_val in hmac_set:
                raise RuntimeError(f'Duplicate HMAC detected for email {email}')
            hmac_set.add(hmac_val)
            cur.execute('UPDATE users SET email_hmac = ? WHERE id = ?', (hmac_val, user_id))
        print(f'Populated HMAC for {len(rows)} users')

        # Ensure UNIQUE index
        index_name = 'idx_users_email_hmac'
        if not index_exists(conn, index_name):
            cur.execute('CREATE UNIQUE INDEX idx_users_email_hmac ON users(email_hmac)')
            print('Created unique index on email_hmac')
        else:
            print('Unique index already exists')

        conn.commit()
        print('Migration completed successfully')
    except Exception as e:
        conn.rollback()
        print('Migration failed, rolled back changes:')
        print(e)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
