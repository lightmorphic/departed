"""All settings come from the environment (.env via docker-compose)."""
import os
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()


def _str(name, default=""):
    return os.environ.get(name, default).strip()


def _float(name, default):
    raw = _str(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _int(name, default):
    raw = _str(name)
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


class Config:
    def __init__(self):
        self.owner_email = _str("OWNER_EMAIL")
        self.recipient_email = _str("RECIPIENT_EMAIL")
        self.smtp_host = _str("SMTP_HOST")
        self.smtp_port = _int("SMTP_PORT", 587)
        self.smtp_username = _str("SMTP_USERNAME")
        self.smtp_password = _str("SMTP_PASSWORD")
        self.smtp_from = _str("SMTP_FROM") or self.smtp_username
        self.smtp_security = _str("SMTP_SECURITY", "starttls").lower()  # starttls | ssl | none
        self.base_url = _str("BASE_URL").rstrip("/")
        self.dashboard_password = _str("DASHBOARD_PASSWORD")
        self.checkin_interval = timedelta(days=_float("CHECKIN_INTERVAL_DAYS", 10))
        self.reminder_count = _int("REMINDER_COUNT", 10)
        self.reminder_interval = timedelta(days=_float("REMINDER_INTERVAL_DAYS", 1))
        self.fire_retry_interval = timedelta(minutes=_float("FIRE_RETRY_MINUTES", 5))
        self.tick_seconds = _int("TICK_SECONDS", 60)
        self.data_dir = Path(_str("DEPARTED_DATA_DIR", "/data"))
        self.archive_dir = Path(_str("DEPARTED_ARCHIVE_DIR", "/archive"))
        self.port = _int("DEPARTED_PORT", 8080)
        tz_name = _str("TZ", "Europe/London")
        try:
            self.tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            self.tz = ZoneInfo("UTC")
        self.tz_name = tz_name

    @property
    def problems(self):
        """Plain-English list of settings that stop the app from doing its job."""
        out = []
        if not self.owner_email:
            out.append("OWNER_EMAIL is not set - nobody to send check-ins to.")
        if not self.recipient_email:
            out.append("RECIPIENT_EMAIL is not set - nobody to send the archive to.")
        if not self.smtp_host:
            out.append("SMTP_HOST is not set - no mail server to send through.")
        if not self.smtp_from:
            out.append("SMTP_FROM is not set - no from-address for outgoing mail.")
        if not self.base_url:
            out.append("BASE_URL is not set - check-in links cannot be built.")
        if self.smtp_security not in ("starttls", "ssl", "none"):
            out.append("SMTP_SECURITY must be starttls, ssl or none.")
        return out

    def checkin_url(self, token):
        return f"{self.base_url}/checkin/{token}"
