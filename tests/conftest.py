from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.config import Boot

PASSWORD = "a-long-enough-password"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class FakeMailer:
    """Stands in for the real one. Every account shares this, as they share a server."""

    sent = []
    fail = False

    def __init__(self, settings=None):
        self._settings = settings

    def send(self, to, subject, body, attachment=None):
        if FakeMailer.fail:
            raise ConnectionError("smtp down")
        FakeMailer.sent.append({"to": to, "subject": subject, "body": body, "attachment": attachment})

    @classmethod
    def reset(cls):
        cls.sent = []
        cls.fail = False

    @classmethod
    def last(cls):
        return cls.sent[-1]

    @classmethod
    def link(cls):
        for m in reversed(cls.sent):
            for word in m["body"].split():
                if "/checkin/" in word:
                    return word.rsplit("/", 1)[1]
        return None


SETTINGS = {
    "owner_email": "me@example.com",
    "recipient_email": "them@example.com",
    "smtp_host": "smtp.example.com",
    "smtp_from": "me@example.com",
    "base_url": "http://departed.test",
    "checkin_interval_days": "10",
    "reminder_count": "3",
    "reminder_interval_days": "1",
    "timezone": "Europe/London",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPARTED_DATA_DIR", str(tmp_path / "data"))
    FakeMailer.reset()
    clock = Clock()
    app = create_app(Boot(), mailer_factory=FakeMailer, now=clock)
    app.testing = True
    switches = app.extensions["departed"]

    def make(username, password=PASSWORD, admin=True, settings=SETTINGS):
        from app.store import hash_password
        digest, salt = hash_password(password)
        user_id = switches.db.add_user(username, digest, salt, admin)
        if settings:
            switches.store(user_id).set_many(settings)
        return user_id

    def client_for(username, password=PASSWORD):
        c = app.test_client()
        c.post("/login", data={"username": username, "password": password})
        return c

    user_id = make("charlie")
    client = client_for("charlie")

    return type("W", (), {
        "app": app, "switches": switches, "db": switches.db,
        "client": client, "anon": app.test_client(),
        "engine": switches.engine(user_id), "user_id": user_id,
        "clock": clock, "mailer": FakeMailer, "password": PASSWORD,
        "archive": switches.archive_dir(user_id),
        "make": staticmethod(make), "client_for": staticmethod(client_for),
        "tick": staticmethod(switches.tick_all),
    })


@pytest.fixture
def files(world):
    world.archive.mkdir(parents=True, exist_ok=True)
    return world.archive
