"""
Module: database.py
Manages SQLite storage for Job Descriptions catalog and Analysis History logs.

Privacy safeguard per Section 10 of the proposal:
Provides full record deletion and history clearance capabilities.
"""

import os
import sqlite3
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.security import encrypt_data, decrypt_data, hash_password, verify_password, email_hmac


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumescope.db")


def get_db_connection() -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database with row factory enabled.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # Existing init logic unchanged
    """
    Initializes database tables and pre-seeds standard benchmark job descriptions.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table 1: Job Descriptions Catalog
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_descriptions (

            title TEXT NOT NULL,
            domain TEXT NOT NULL,
            description TEXT NOT NULL,
            required_skills TEXT NOT NULL
        )
    """)

    # Table 2: Candidate Analysis History
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (

            user_id INTEGER NOT NULL DEFAULT 1,
            resume_name TEXT NOT NULL,
            top_job_role TEXT NOT NULL,
            match_score REAL NOT NULL,
            date_analyzed TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            details_json TEXT
        )
    """)

    # Table 3: User Accounts (Separated from Analysis Records)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email_encrypted TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Ensure deterministic email HMAC column exists for new databases
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "email_hmac" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN email_hmac TEXT")
    # Create a unique index on email_hmac if not present
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_users_email_hmac'")
    if not cursor.fetchone():
        cursor.execute("CREATE UNIQUE INDEX idx_users_email_hmac ON users(email_hmac)")


    # Migrate existing analysis_history table if user_id column is missing
    cursor.execute("PRAGMA table_info(analysis_history)")
    existing_cols = [c[1] for c in cursor.fetchall()]
    if "user_id" not in existing_cols:
        cursor.execute("ALTER TABLE analysis_history ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
        conn.commit()

    # Pre-seed default user if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    if user_count == 0:
        default_email_enc = encrypt_data("madhu@email.com")
        default_email_hmac = email_hmac("madhu@email.com")
        default_pw_hash = hash_password("ResumeScope@2025!")
        cursor.execute("""
            INSERT INTO users (username, email_encrypted, password_hash, email_hmac)
            VALUES (?, ?, ?, ?)
        """, ("madhu", default_email_enc, default_pw_hash, default_email_hmac))
        conn.commit()

    # Pre-seed job descriptions or sync new jobs from catalog
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "job_descriptions.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            catalog_jobs = json.load(f)
        cursor.execute("SELECT title FROM job_descriptions")
        existing_titles = {row[0] for row in cursor.fetchall()}
        for j in catalog_jobs:
            if j["title"] not in existing_titles:
                cursor.execute("""
                    INSERT INTO job_descriptions (title, domain, description, required_skills)
                    VALUES (?, ?, ?, ?)
                """, (
                    j["title"],
                    j["domain"],
                    j["description"],
                    json.dumps(j.get("required_skills", []))
                ))
        conn.commit()

    # Seed initial sample history from mockups if empty to match exact references
    cursor.execute("SELECT COUNT(*) FROM analysis_history")
    hist_count = cursor.fetchone()[0]
    if hist_count == 0:
        initial_history = [
            ("Resume_JohnDoe.pdf", "ML Engineer", 96.2, "Oct 28, 2025"),
            ("Resume_Anika.pdf", "Data Scientist", 93.7, "Oct 25, 2025"),
            ("Resume_Madhu.pdf", "Data Analyst", 90.5, "Oct 20, 2025")
        ]
        for name, role, score, dt in initial_history:
            cursor.execute("""
                INSERT INTO analysis_history (resume_name, top_job_role, match_score, date_analyzed, details_json, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, role, score, dt, json.dumps({"status": "completed", "score": score}), 1))
        conn.commit()

    conn.close()


def get_all_jobs() -> List[Dict[str, Any]]:
    """
    Retrieves all job descriptions from SQLite.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_descriptions ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for r in rows:
        jobs.append({
            "id": r["id"],
            "title": r["title"],
            "domain": r["domain"],
            "description": r["description"],
            "required_skills": json.loads(r["required_skills"])
        })
    return jobs

# ---------- New Functions for Job Management ----------
import difflib

def add_job(title: str, domain: str, description: str, required_skills: List[str]) -> int:
    """Insert a new job description into the catalog and return its new ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO job_descriptions (title, domain, description, required_skills) VALUES (?,?,?,?)",
        (title, domain, description, json.dumps(required_skills))
    )
    conn.commit()
    job_id = cursor.lastrowid
    conn.close()
    return job_id

def search_jobs(query: str, limit: int = 3, cutoff: float = 0.5) -> List[Dict[str, Any]]:
    """Return up to `limit` jobs whose titles closely match the query.
    Uses difflib.get_close_matches on job titles.
    """
    all_jobs = get_all_jobs()
    titles = [job["title"] for job in all_jobs]
    matches = difflib.get_close_matches(query, titles, n=limit, cutoff=cutoff)
    matched_jobs = [job for job in all_jobs if job["title"] in matches]
    return matched_jobs


def save_analysis_record(
    resume_name: str,
    top_job_role: str,
    match_score: float,
    details: Dict[str, Any],
    date_str: Optional[str] = None,
    user_id: int = 1
) -> int:
    """
    Inserts an analysis record into the history table.
    """
    if not date_str:
        date_str = datetime.now().strftime("%b %d, %Y")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analysis_history (resume_name, top_job_role, match_score, date_analyzed, details_json, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        resume_name,
        top_job_role,
        float(match_score),
        date_str,
        json.dumps(details),
                user_id
    ))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id


def get_history_records() -> List[Dict[str, Any]]:
    """
    Retrieves all analysis history records sorted newest first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    history = []
    for r in rows:
        history.append({
            "id": r["id"],
            "resume_name": r["resume_name"],
            "top_job_role": r["top_job_role"],
            "match_score": float(r["match_score"]),
            "date_analyzed": r["date_analyzed"],
            "timestamp": r["timestamp"],
            "details": json.loads(r["details_json"]) if r["details_json"] else {}
        })
    return history


def get_history_record_by_id(record_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single analysis history record by ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_history WHERE id = ?", (record_id,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r["id"],
        "resume_name": r["resume_name"],
        "top_job_role": r["top_job_role"],
        "match_score": float(r["match_score"]),
        "date_analyzed": r["date_analyzed"],
        "timestamp": r["timestamp"],
        "details": json.loads(r["details_json"]) if r["details_json"] else {}
    }


def delete_history_record(record_id: int) -> bool:
    """
    Deletes a single analysis record by ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analysis_history WHERE id = ?", (record_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def clear_all_history() -> int:
    """
    Deletes all analysis records from the database for user privacy compliance.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analysis_history")
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count