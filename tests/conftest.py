from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.config import Config


class Clock:
    def __init__(self):
        self.t = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, body, attachment=None):
        if self.fail:
            raise ConnectionError("smtp down")
        self.sent.append({"to": to, "subject": subject, "body": body, "attachment": attachment})

    def last(self):
        return self.sent[-1]

    def link(self):
        """Token from the most recent check-in style email."""
        for m in reversed(self.sent):
            for word in m["body"].split():
                if "/checkin/" in word:
                    return word.rsplit("/", 1)[1]
        return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("OWNER_EMAIL", "me@example.com")
    monkeypatch.setenv("RECIPIENT_EMAIL", "them@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    monkeypatch.setenv("BASE_URL", "https://departed.test")
    monkeypatch.setenv("DEPARTED_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEPARTED_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("CHECKIN_INTERVAL_DAYS", "10")
    monkeypatch.setenv("REMINDER_COUNT", "3")
    monkeypatch.setenv("REMINDER_INTERVAL_DAYS", "1")
    (tmp_path / "archive").mkdir()
    return tmp_path


@pytest.fixture
def world(env):
    clock = Clock()
    mailer = FakeMailer()
    app = create_app(Config(), mailer=mailer, now=clock)
    app.testing = True
    engine = app.extensions["departed"]
    return type("W", (), {"app": app, "client": app.test_client(), "engine": engine,
                          "clock": clock, "mailer": mailer, "archive": env / "archive"})
