"""SQLite storage for staff accounts, login sessions, the document list, usage metrics, reviews and an audit log."""
import contextlib
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  uploaded_by TEXT NOT NULL,
  uploaded_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  rating TEXT NOT NULL,
  language TEXT NOT NULL,
  category TEXT NOT NULL,
  answered INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS chat_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  language TEXT NOT NULL,
  category TEXT NOT NULL,
  outcome TEXT NOT NULL,          -- answered | no_info | small_talk | crisis | blocked | error
  latency_ms INTEGER NOT NULL,
  top_score REAL NOT NULL DEFAULT 0,
  channel TEXT NOT NULL DEFAULT 'page');   -- page | widget
CREATE TABLE IF NOT EXISTS unanswered(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  language TEXT NOT NULL,
  category TEXT NOT NULL,
  question TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS staff_reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  language TEXT NOT NULL,
  accuracy INTEGER NOT NULL,
  completeness INTEGER NOT NULL,
  clarity INTEGER NOT NULL,
  tone INTEGER NOT NULL,
  safe INTEGER NOT NULL,
  comment TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  username TEXT NOT NULL,
  action TEXT NOT NULL,
  doc_id TEXT,
  detail TEXT);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first version. Older databases get them on start-up.
MIGRATIONS = {
    "feedback": {"reason": "TEXT", "channel": "TEXT NOT NULL DEFAULT 'page'"},
    "users": {"role": "TEXT NOT NULL DEFAULT 'admin'"},                 # admin | reviewer (lecturer)
    "staff_reviews": {"reviewer_role": "TEXT NOT NULL DEFAULT 'admin'"},
}


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, kind in columns.items():
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def audit(username: str, action: str, doc_id: str | None = None, detail: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(ts, username, action, doc_id, detail) VALUES (?,?,?,?,?)",
            (now_iso(), username, action, doc_id, detail),
        )
