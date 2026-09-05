"""Settings, kept in the app's own database rather than in the environment.

Anything sensitive is encrypted with a key that lives beside the database, so a
copy of the database on its own gives nothing away. This is not the same thing
as the archive: the archive is encrypted by you, with a passphrase this program
never sees, and nothing in here can open it.
"""
import base64
import hashlib
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("departed.settings")

PBKDF_ROUNDS = 240_000

# key, is it a secret, default
FIELDS = [
    ("owner_email", False, ""),
    ("recipient_email", False, ""),
    ("smtp_host", False, ""),
    ("smtp_port", False, "587"),
    ("smtp_security", False, "starttls"),
    ("smtp_username", False, ""),
    ("smtp_password", True, ""),
    ("smtp_from", False, ""),
    ("base_url", False, ""),
    ("checkin_interval_days", False, "10"),
    ("reminder_count", False, "10"),
    ("reminder_interval_days", False, "1"),
    ("timezone", False, "Europe/London"),
    ("letter", True, ""),
    # Only whether a sealed archive is present. Never anything about what is in it.
    ("sealed", False, ""),
]
SECRET_FIELDS = {name for name, is_secret, _ in FIELDS if is_secret}
DEFAULTS = {name: default for name, _, default in FIELDS}

SECURITY_CHOICES = [
    ("starttls", "STARTTLS, the usual choice, normally port 587"),
    ("ssl", "SSL or TLS from the start, normally port 465"),
    ("none", "No encryption. Only sensible for a mail server on this machine"),
]


def load_key(data_dir):
    """The encryption key. From the environment if one is given, otherwise a
    file beside the database that is made once and then left alone."""
    from_env = os.environ.get("SECRET_KEY", "").strip()
    if from_env:
        return base64.urlsafe_b64encode(hashlib.sha256(from_env.encode()).digest())
    path = Path(data_dir) / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
        log.info("Made a new encryption key at %s", path)
    return path.read_bytes().strip()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ROUNDS)
    return base64.b64encode(digest).decode(), base64.b64encode(salt).decode()


def password_matches(user, password):
    if not user or not user.password_hash:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                                 base64.b64decode(user.password_salt), PBKDF_ROUNDS)
    return secrets.compare_digest(base64.b64encode(digest).decode(), user.password_hash)


def _int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _float(value, default):
    try:
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return out if out > 0 else default


class Settings:
    """A snapshot of one person's settings, in the shapes the app wants."""

    def __init__(self, values, archive_dir):
        self.archive_dir = Path(archive_dir)
        for name in DEFAULTS:
            setattr(self, name, values.get(name, DEFAULTS[name]))
        self.raw = dict(values)
        self.smtp_port = _int(self.smtp_port, 587)
        self.reminder_count = max(0, _int(self.reminder_count, 10))
        self.checkin_interval = timedelta(days=_float(self.checkin_interval_days, 10))
        self.reminder_interval = timedelta(days=_float(self.reminder_interval_days, 1))
        self.fire_retry_interval = timedelta(minutes=5)
        self.base_url = self.base_url.rstrip("/")
        try:
            self.tz = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            self.tz = ZoneInfo("UTC")

    @property
    def problems(self):
        """Plain-English list of what still stops it doing its job."""
        out = []
        if not self.owner_email:
            out.append("Your own email address is missing, so there is nobody to send check-ins to.")
        if not self.recipient_email:
            out.append("Your person's email address is missing, so there is nobody to send the archive to.")
        if not self.smtp_host:
            out.append("The mail server is missing, so nothing can be sent at all.")
        if not self.from_address:
            out.append("The from-address is missing, so outgoing mail has no sender.")
        if not self.base_url:
            out.append("The web address is missing, so the check-in links cannot be built.")
        if self.smtp_security not in dict(SECURITY_CHOICES):
            out.append("The mail security setting is not one of the three choices.")
        return out

    @property
    def days_to_fire(self):
        """Days from a check-in to the archive going out, on the numbers set."""
        total = self.checkin_interval + (self.reminder_count + 1) * self.reminder_interval
        return total.total_seconds() / 86400

    @property
    def ready(self):
        return not self.problems

    @property
    def from_address(self):
        return self.smtp_from or self.smtp_username

    def checkin_url(self, token):
        return f"{self.base_url}/checkin/{token}"

    @property
    def example_checkin_url(self):
        """What a link in your emails will look like."""
        return self.checkin_url("k3f9x2...") if self.base_url else ""

    @property
    def base_url_is_local(self):
        """True when the address would only work on this network, which means
        the links in the emails will not open on a phone away from home."""
        if not self.base_url:
            return False
        host = self.base_url.split("://", 1)[-1].split("/")[0].split(":")[0].lower()
        if host in ("localhost", "0.0.0.0", "::1", "[::1]"):
            return True
        if host.startswith("127.") or host.startswith("192.168.") or host.startswith("10."):
            return True
        return "." not in host


class SettingsStore:
    """Reads and writes one person's settings."""

    def __init__(self, db, key, user_id, archive_dir):
        self.db = db
        self.user_id = user_id
        self.archive_dir = Path(archive_dir)
        self._fernet = Fernet(key)

    def get(self, name, default=""):
        raw = self.db.get_setting(self.user_id, name)
        if raw is None:
            return DEFAULTS.get(name, default)
        if name in SECRET_FIELDS:
            try:
                return self._fernet.decrypt(raw.encode()).decode()
            except (InvalidToken, ValueError):
                log.error("Could not read the stored value for %s. The encryption key has changed.", name)
                return ""
        return raw

    def set(self, name, value):
        value = "" if value is None else str(value)
        if name in SECRET_FIELDS:
            value = self._fernet.encrypt(value.encode()).decode()
        self.db.set_setting(self.user_id, name, value)

    def set_many(self, values):
        for name, value in values.items():
            if name in DEFAULTS:
                self.set(name, value)

    def current(self):
        return Settings({name: self.get(name) for name in DEFAULTS}, self.archive_dir)
