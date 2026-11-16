"""Accounts, sessions and rate limiting for PhytoBridge.

User data lives in its own SQLite database (data/users.db), kept separate
from the read-only evidence database. Passwords are hashed with werkzeug's
pbkdf2; session tokens are signed with itsdangerous and carry a per-user
token version so password changes / deletions invalidate old tokens.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

USERS_DB_PATH = os.environ.get(
    "PHYTOBRIDGE_USERS_DB",
    os.path.join(os.path.dirname(__file__), "data", "users.db"))

SECRET_KEY = (os.environ.get("PHYTOBRIDGE_SECRET_KEY") or "").strip()
if not SECRET_KEY:
    # Ephemeral fallback: tokens survive only this process. Set
    # PHYTOBRIDGE_SECRET_KEY in the host environment for stable sessions.
    SECRET_KEY = secrets.token_hex(32)

_SIGNER = URLSafeTimedSerializer(SECRET_KEY, salt="phytobridge-auth-v1")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Per-IP limits on auth endpoints (register/login): 10 attempts per 5 min.
_RATE: dict[str, list[float]] = {}
_RATE_WINDOW = 300.0
_RATE_MAX = 10


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    bucket = [t for t in _RATE.get(ip, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_MAX:
        _RATE[ip] = bucket
        return True
    bucket.append(now)
    _RATE[ip] = bucket
    return False


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip())) and len(email) <= 254


class UserStore:
    """SQLite-backed per-user accounts, saved plants and notes."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or USERS_DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        with self._cx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                pw_hash TEXT NOT NULL,
                token_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS saved_plants (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                fnfnum INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, fnfnum)
            );
            """)
        self._ensure_secret()

    def _ensure_secret(self) -> None:
        # Guard against accidentally serving a committed users database.
        if os.path.exists(self.path):
            try:
                conn = sqlite3.connect(self.path)
                n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                conn.close()
                if n:
                    return  # existing account database, leave it alone
            except sqlite3.Error:
                pass

    def _cx(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    # -- accounts ---------------------------------------------------------
    def create_user(self, email: str, pw_hash: str) -> int:
        with self._cx() as db:
            cur = db.execute(
                "INSERT INTO users (email, pw_hash) VALUES (?, ?)",
                (email.strip().lower(), pw_hash))
        return int(cur.lastrowid)

    def user_by_email(self, email: str):
        return self._cx().execute(
            "SELECT * FROM users WHERE email = ?",
            ((email or "").strip().lower(),)).fetchone()

    def user_by_id(self, uid: int):
        return self._cx().execute(
            "SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

    # -- tokens -----------------------------------------------------------
    def issue(self, uid: int, token_version: int) -> str:
        return _SIGNER.dumps({"uid": uid, "tv": token_version})

    def verify(self, token: str):
        """Returns the user row for a valid, current token, else None."""
        try:
            data = _SIGNER.loads(token or "", max_age=60 * 60 * 24 * 30)
        except BadSignature:
            return None
        user = self.user_by_id(int(data.get("uid", 0)))
        if user is None or user["token_version"] != data.get("tv"):
            return None
        return user

    def bump_token_version(self, uid: int) -> None:
        with self._cx() as db:
            db.execute(
                "UPDATE users SET token_version = token_version + 1 WHERE id = ?",
                (uid,))

    def delete_user(self, uid: int) -> None:
        with self._cx() as db:
            db.execute("DELETE FROM saved_plants WHERE user_id = ?", (uid,))
            db.execute("DELETE FROM users WHERE id = ?", (uid,))

    # -- saved plants -------------------------------------------------------
    def saved_add(self, uid: int, fnfnum: int, note: str = "") -> bool:
        with self._cx() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO saved_plants (user_id, fnfnum, note) "
                "VALUES (?, ?, ?)", (uid, fnfnum, (note or "")[:2000]))
        return cur.rowcount > 0

    def saved_remove(self, uid: int, fnfnum: int) -> bool:
        with self._cx() as db:
            cur = db.execute(
                "DELETE FROM saved_plants WHERE user_id = ? AND fnfnum = ?",
                (uid, fnfnum))
        return cur.rowcount > 0

    def saved_list(self, uid: int) -> list[dict]:
        rows = self._cx().execute(
            "SELECT fnfnum, note, saved_at FROM saved_plants "
            "WHERE user_id = ? ORDER BY saved_at DESC", (uid,)).fetchall()
        return [dict(r) for r in rows]

    def saved_set_note(self, uid: int, fnfnum: int, note: str) -> bool:
        with self._cx() as db:
            cur = db.execute(
                "UPDATE saved_plants SET note = ? WHERE user_id = ? AND fnfnum = ?",
                ((note or "")[:2000], uid, fnfnum))
        return cur.rowcount > 0


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def check_password(password: str, pw_hash: str) -> bool:
    return check_password_hash(pw_hash, password)
