# tests/test_email_hmac.py

import os
import unittest
import tempfile
import shutil
import sqlite3
import importlib
import importlib.util
import sys
from backend.security import email_hmac, _load_email_hmac_key
from backend.database import init_db, DB_PATH as ORIGINAL_DB_PATH, get_db_connection

# Load the migration module without executing it
from pathlib import Path
# Resolve migration script path relative to this test file's location
migration_path = Path(__file__).resolve().parent.parent / "migrate_email_hmac.py"
spec = importlib.util.spec_from_file_location("migrate", str(migration_path))
migrate_mod = importlib.util.module_from_spec(spec)
sys.modules["migrate"] = migrate_mod
spec.loader.exec_module(migrate_mod)

class EmailHMACTest(unittest.TestCase):
    def test_hmac_consistency(self):
        email1 = "  Example@Domain.COM  "
        email2 = "example@domain.com"
        self.assertEqual(email_hmac(email1), email_hmac(email2))

    def test_hmac_uniqueness(self):
        h1 = email_hmac("alice@example.com")
        h2 = email_hmac("bob@example.com")
        self.assertNotEqual(h1, h2)

    def test_hmac_key_stability_across_imports(self):
        # Reload the security module in a fresh interpreter context
        import backend.security as sec1
        key1 = sec1._EMAIL_HMAC_KEY
        import importlib
        importlib.reload(sec1)
        key2 = sec1._EMAIL_HMAC_KEY
        self.assertEqual(key1, key2)

    def _create_temp_db(self):
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, "resumescope.db")
        # Point the DB_PATH in backend.database to the temp db for init
        import backend.database as db_mod
        db_mod.DB_PATH = tmp_path
        # Initialise schema (this will also add email_hmac column and index)
        init_db()
        return tmp_path, tmp_dir



    def test_migration_population(self):
        db_path, tmp_dir = self._create_temp_db()
        # Insert a synthetic user with encrypted email, HMAC NULL
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            from backend.security import encrypt_data
            email = "testuser@example.com"
            encrypted = encrypt_data(email)
            cur.execute(
                "INSERT INTO users (username, email_encrypted, password_hash) VALUES (?,?,?)",
                ("testuser", encrypted, "dummyhash")
            )
            conn.commit()
        finally:
            conn.close()
        # Run migration on this temp DB
        migrate_mod.DB_PATH = db_path
        migrate_mod.migrate()
        # Verify column populated correctly
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT email_encrypted, email_hmac FROM users WHERE username = ?", ("testuser",))
            row = cur.fetchone()
            self.assertIsNotNone(row["email_hmac"])
            # Decrypt and compare HMAC
            from backend.security import decrypt_data
            decrypted = decrypt_data(row["email_encrypted"])
            self.assertEqual(email_hmac(decrypted), row["email_hmac"])
        finally:
            conn.close()
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                # On Windows the database file may still be locked; ignore cleanup error
                pass

    def test_migration_rollback_on_failure(self):
        db_path, tmp_dir = self._create_temp_db()
        # Insert a user with corrupted encrypted email to force failure
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email_encrypted, password_hash) VALUES (?,?,?)",
            ("baduser", "corrupted", "dummyhash")
        )
        conn.commit()
        conn.close()
        migrate_mod.DB_PATH = db_path
        with self.assertRaises(SystemExit):
            migrate_mod.migrate()
        # Ensure migration rolled back (email_hmac column should exist but be NULL)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cur.fetchall()]
        self.assertIn('email_hmac', cols)
        # Ensure no rows have non‑NULL email_hmac
        cur.execute("SELECT email_hmac FROM users WHERE username = ?", ("baduser",))
        self.assertIsNone(cur.fetchone()[0])
        conn.close()
        shutil.rmtree(tmp_dir)

    def test_migration_idempotent(self):
        db_path, tmp_dir = self._create_temp_db()
        # Insert a user
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        from backend.security import encrypt_data
        email = "idem@example.com"
        encrypted = encrypt_data(email)
        cur.execute(
            "INSERT INTO users (username, email_encrypted, password_hash) VALUES (?,?,?)",
            ("idemuser", encrypted, "dummyhash")
        )
        conn.commit()
        conn.close()
        migrate_mod.DB_PATH = db_path
        # First migration
        migrate_mod.migrate()
        # Capture HMAC count
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE email_hmac IS NOT NULL")
        count1 = cur.fetchone()[0]
        conn.close()
        # Second migration – should be a no‑op
        migrate_mod.migrate()
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE email_hmac IS NOT NULL")
        count2 = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count1, count2)
        shutil.rmtree(tmp_dir)

if __name__ == '__main__':
    unittest.main()



