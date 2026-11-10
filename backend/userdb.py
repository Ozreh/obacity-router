import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

from config import BASE_DIR

SQLITE_FILE = BASE_DIR / "users.db"
URL_FILE = BASE_DIR / "database_url.txt"


def _load_database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value and URL_FILE.exists():
        value = URL_FILE.read_text(encoding="utf-8").strip()
    return value


DATABASE_URL = _load_database_url()
USE_PG = bool(DATABASE_URL)

if USE_PG:
    if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("DATABASE_URL должен начинаться с postgresql://")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:
        raise RuntimeError('Для Neon нужен драйвер: pip install "psycopg[binary]"') from e
    IntegrityError = psycopg.IntegrityError
else:
    IntegrityError = sqlite3.IntegrityError


SCHEMA_PG = (
    "CREATE TABLE IF NOT EXISTS users ("
    "id BIGSERIAL PRIMARY KEY, "
    "email TEXT NOT NULL UNIQUE, "
    "name TEXT NOT NULL, "
    "password_hash TEXT, "
    "google_sub TEXT UNIQUE, "
    "created_at BIGINT NOT NULL)"
)
SCHEMA_SQLITE = (
    "CREATE TABLE IF NOT EXISTS users ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "email TEXT NOT NULL UNIQUE, "
    "name TEXT NOT NULL, "
    "password_hash TEXT, "
    "google_sub TEXT UNIQUE, "
    "created_at INTEGER NOT NULL)"
)
PUBLIC_COLUMNS = "id, email, name"


def _connect():
    if USE_PG:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
    conn = sqlite3.connect(SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _run(conn, sql: str, params: tuple = ()):
    return conn.execute(sql.replace("?", "%s") if USE_PG else sql, params)


@contextmanager
def session():
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _one(cur) -> Optional[dict]:
    row = cur.fetchone()
    return dict(row) if row is not None else None


def init_db() -> None:
    with session() as conn:
        _run(conn, SCHEMA_PG if USE_PG else SCHEMA_SQLITE)


def _insert(conn, email: str, name: str, password_hash: Optional[str], google_sub: Optional[str]) -> dict:
    sql = (
        "INSERT INTO users (email, name, password_hash, google_sub, created_at) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    params = (email, name, password_hash, google_sub, int(time.time()))
    if USE_PG:
        return _one(_run(conn, sql + f" RETURNING {PUBLIC_COLUMNS}", params))
    cur = _run(conn, sql, params)
    return _one(_run(conn, f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id = ?", (cur.lastrowid,)))


def create_user(email: str, name: str, password_hash: Optional[str] = None,
                google_sub: Optional[str] = None) -> dict:
    with session() as conn:
        return _insert(conn, email, name, password_hash, google_sub)


def user_by_id(user_id: int) -> Optional[dict]:
    with session() as conn:
        return _one(_run(conn, f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id = ?", (user_id,)))


def user_for_login(email: str) -> Optional[dict]:
    with session() as conn:
        return _one(_run(
            conn, f"SELECT {PUBLIC_COLUMNS}, password_hash FROM users WHERE email = ?", (email,)
        ))


def google_user(email: str, sub: str, name: str) -> dict:
    with session() as conn:
        row = _one(_run(conn, f"SELECT {PUBLIC_COLUMNS} FROM users WHERE google_sub = ?", (sub,)))
        if row is None:
            row = _one(_run(conn, f"SELECT {PUBLIC_COLUMNS} FROM users WHERE email = ?", (email,)))
            if row is not None:
                _run(conn, "UPDATE users SET google_sub = ? WHERE id = ?", (sub, row["id"]))
        if row is None:
            row = _insert(conn, email, name, None, sub)
        return row
