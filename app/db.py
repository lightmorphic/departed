"""SQLite persistence on the mounted volume.

Everything is per user: each person has their own settings, their own timer,
their own log and their own folder of files.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  user_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS state (
  user_id INTEGER PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'waiting',
  last_checkin_at TEXT NOT NULL,
  cycle_started_at TEXT,
  last_sent_at TEXT,
  reminders_sent INTEGER NOT NULL DEFAULT 0,
  token_hash TEXT,
  fire_pending INTEGER NOT NULL DEFAULT 0,
  fire_attempts INTEGER NOT NULL DEFAULT 0,
  last_fire_attempt_at TEXT,
  last_fire_error TEXT,
  fired_at TEXT,
  last_alert_at TEXT,
  last_test_at TEXT,
  last_test_result TEXT,
  fired_to TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_user ON events (user_id, id DESC);
"""

DT_FIELDS = ("last_checkin_at", "cycle_started_at", "last_sent_at", "last_fire_attempt_at",
             "fired_at", "last_alert_at", "last_test_at")


def to_iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def from_iso(s):
    return datetime.fromisoformat(s) if s else None


class State:
    """Plain attribute bag for one person's state row."""

    def __init__(self, row):
        for key in row.keys():
            value = row[key]
            setattr(self, key, from_iso(value) if key in DT_FIELDS else value)
        self.fire_pending = bool(self.fire_pending)

    def as_row(self):
        out = {}
        for key, value in vars(self).items():
            if key in DT_FIELDS:
                value = to_iso(value)
            elif key == "fire_pending":
                value = int(value)
            out[key] = value
        return out


class User:
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.is_admin = bool(row["is_admin"])
        self.created_at = from_iso(row["created_at"])
        self.password_hash = row["password_hash"]
        self.password_salt = row["password_salt"]


class Database:
    def __init__(self, path, now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._add_missing_columns(c)

    @staticmethod
    def _add_missing_columns(c):
        """Older databases pre-date some columns. Add them rather than asking
        anybody to start again."""
        have = {row["name"] for row in c.execute("PRAGMA table_info(state)")}
        for name, kind in (("fired_to", "TEXT"),):
            if name not in have:
                c.execute(f"ALTER TABLE state ADD COLUMN {name} {kind}")

    def _conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    # ---- people ---------------------------------------------------------

    def any_users(self):
        with self._conn() as c:
            return c.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def users(self):
        with self._conn() as c:
            return [User(r) for r in c.execute("SELECT * FROM users ORDER BY id").fetchall()]

    def user(self, user_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(row) if row else None

    def user_by_name(self, username):
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return User(row) if row else None

    def add_user(self, username, password_hash, password_salt, is_admin):
        now = self._now()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO users (username, password_hash, password_salt, is_admin, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, password_salt, int(is_admin), to_iso(now)))
            user_id = cur.lastrowid
            c.execute("INSERT INTO state (user_id, last_checkin_at) VALUES (?, ?)",
                      (user_id, to_iso(now)))
            c.execute("INSERT INTO events (user_id, at, kind, message) VALUES (?, ?, ?, ?)",
                      (user_id, to_iso(now), "armed",
                       "Switch armed for the first time. Setting it up counts as a check-in."))
        return user_id

    def set_user_password(self, user_id, password_hash, password_salt):
        with self._conn() as c:
            c.execute("UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                      (password_hash, password_salt, user_id))

    def set_user_admin(self, user_id, is_admin):
        with self._conn() as c:
            c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))

    def delete_user(self, user_id):
        with self._conn() as c:
            c.execute("DELETE FROM users WHERE id = ?", (user_id,))
            c.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM state WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM events WHERE user_id = ?", (user_id,))

    def admin_count(self):
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) n FROM users WHERE is_admin = 1").fetchone()["n"]

    # ---- state ----------------------------------------------------------

    def get_state(self, user_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM state WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                c.execute("INSERT INTO state (user_id, last_checkin_at) VALUES (?, ?)",
                          (user_id, to_iso(self._now())))
                row = c.execute("SELECT * FROM state WHERE user_id = ?", (user_id,)).fetchone()
        return State(row)

    def save_state(self, state):
        row = state.as_row()
        user_id = row.pop("user_id")
        assignments = ", ".join(f"{k} = :{k}" for k in row)
        row["user_id"] = user_id
        with self._conn() as c:
            c.execute(f"UPDATE state SET {assignments} WHERE user_id = :user_id", row)

    def state_by_token_hash(self, token_hash):
        with self._conn() as c:
            row = c.execute("SELECT * FROM state WHERE token_hash = ?", (token_hash,)).fetchone()
        return State(row) if row else None

    # ---- settings -------------------------------------------------------

    def get_setting(self, user_id, key):
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?",
                            (user_id, key)).fetchone()
        return row["value"] if row else None

    def set_setting(self, user_id, key, value):
        with self._conn() as c:
            c.execute("INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
                      "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                      (user_id, key, value))

    # ---- log ------------------------------------------------------------

    def log_event(self, user_id, kind, message, at=None):
        with self._conn() as c:
            c.execute("INSERT INTO events (user_id, at, kind, message) VALUES (?, ?, ?, ?)",
                      (user_id, to_iso(at or self._now()), kind, message))

    def recent_events(self, user_id, limit=40):
        with self._conn() as c:
            rows = c.execute("SELECT at, kind, message FROM events WHERE user_id = ? "
                             "ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        return [{"at": from_iso(r["at"]), "kind": r["kind"], "message": r["message"]} for r in rows]
