"""The only things that still come from the environment.

Everything else - email addresses, mail server, timing, the letter - is set on
the settings page and kept in the app's own database, so the compose file never
has to be edited.
"""
import os
from pathlib import Path

VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()


def _str(name, default=""):
    return os.environ.get(name, default).strip()


def _int(name, default):
    try:
        return int(_str(name) or default)
    except ValueError:
        return default


class Boot:
    """Where things live and which port to serve on. Nothing secret in here."""

    def __init__(self):
        self.data_dir = Path(_str("DEPARTED_DATA_DIR", "/data"))
        self.archive_dir = Path(_str("DEPARTED_ARCHIVE_DIR", "") or self.data_dir / "archive")
        self.port = _int("DEPARTED_PORT", 8080)
        self.tick_seconds = _int("TICK_SECONDS", 60)
        self.max_upload_mb = _int("MAX_UPLOAD_MB", 64)
