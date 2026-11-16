import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app as app_module


class AuthFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth-test.db")
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email_encrypted TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    email_hmac TEXT UNIQUE
                )
            """)
            connection.commit()
        finally:
            connection.close()

        self.connections = []
        self.connection_patch = patch.object(
            app_module,
            "get_db_connection",
            side_effect=self.get_connection
        )
        self.connection_patch.start()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.connection_patch.stop()
        for connection in self.connections:
            connection.close()
        self.temp_dir.cleanup()

    def get_connection(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        self.connections.append(connection)
        return connection

    def test_signup_login_and_logout(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/signup").status_code, 200)

        signup = self.client.post("/api/signup", json={
            "username": "Ada Lovelace",
            "email": "ada@example.com",
            "password": "secure-pass-123"
        })
        self.assertEqual(signup.status_code, 201)

        login = self.client.post("/api/login", json={
            "email": "ADA@example.com",
            "password": "secure-pass-123"
        })
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json["success"])

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Ada Lovelace", dashboard.data)
        self.assertIn(b"ada@example.com", dashboard.data)
        self.assertEqual(self.client.get("/login").headers["Location"], "/")

        logout = self.client.post("/logout")
        self.assertEqual(logout.status_code, 302)
        self.assertEqual(logout.headers["Location"], "/login")
        self.assertEqual(self.client.get("/").headers["Location"], "/login")

    def test_duplicate_signup_shows_conflict(self):
        user = {
            "username": "Ada",
            "email": "ada@example.com",
            "password": "secure-pass-123"
        }
        self.assertEqual(self.client.post("/api/signup", json=user).status_code, 201)
        duplicate = self.client.post("/api/signup", json={
            **user,
            "username": "Another Ada"
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json["error"], "Email already registered")


if __name__ == "__main__":
    unittest.main()
