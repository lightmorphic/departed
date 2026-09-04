"""SQLite persistence: one state row plus an event log. Lives on the mounted volume."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
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
  last_test_result TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL
);
"""

DT_FIELDS = ("last_checkin_at", "cycle_started_at", "last_sent_at", "last_fire_attempt_at",
             "fired_at", "last_alert_at", "last_test_at")


def to_iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def from_iso(s):
    return datetime.fromisoformat(s) if s else None


class State:
    """Plain attribute bag for the single state row."""

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


class Database:
    def __init__(self, path, now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        with self._conn() as c:
            c.executescript(SCHEMA)
            if c.execute("SELECT 1 FROM state WHERE id = 1").fetchone() is None:
                c.execute("INSERT INTO state (id, last_checkin_at) VALUES (1, ?)", (to_iso(now()),))
                c.execute("INSERT INTO events (at, kind, message) VALUES (?, ?, ?)",
                          (to_iso(now()), "armed", "Switch armed for the first time. The install counts as a check-in."))

    def _conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def get_state(self):
        with self._conn() as c:
            return State(c.execute("SELECT * FROM state WHERE id = 1").fetchone())

    def save_state(self, state):
        row = state.as_row()
        row.pop("id", None)
        assignments = ", ".join(f"{k} = :{k}" for k in row)
        with self._conn() as c:
            c.execute(f"UPDATE state SET {assignments} WHERE id = 1", row)

    def log_event(self, kind, message, at=None):
        with self._conn() as c:
            c.execute("INSERT INTO events (at, kind, message) VALUES (?, ?, ?)",
                      (to_iso(at or self._now()), kind, message))

    def recent_events(self, limit=40):
        with self._conn() as c:
            rows = c.execute("SELECT at, kind, message FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"at": from_iso(r["at"]), "kind": r["kind"], "message": r["message"]} for r in rows]
