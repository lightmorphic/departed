"""One shared password for the dashboard.

The check-in link that arrives by email is deliberately left open: it carries its
own long single-use token, and it has to work with one click from any phone.
"""
import hashlib
import hmac
import logging
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger("departed.auth")

COOKIE = "departed_session"
SESSION_DAYS = 30
MAX_TRIES = 5
LOCKOUT_SECONDS = 60


def _key_file(data_dir):
    """A random key kept beside the database, so logins survive a restart."""
    path = Path(data_dir) / "session.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


class Auth:
    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = bool(cfg.dashboard_password)
        self._failures = {}
        if self.enabled:
            # Salting with the password means changing it logs everyone out.
            salt = "departed-login-" + hashlib.sha256(cfg.dashboard_password.encode()).hexdigest()[:16]
            self._signer = URLSafeTimedSerializer(_key_file(cfg.data_dir), salt=salt)

    # ---- attempts -------------------------------------------------------

    def locked_for(self, who):
        tries, until = self._failures.get(who, (0, 0))
        return max(0, int(until - time.time()))

    def _record_failure(self, who):
        tries, _ = self._failures.get(who, (0, 0))
        tries += 1
        wait = 0
        if tries >= MAX_TRIES:
            wait = min(LOCKOUT_SECONDS * 2 ** (tries - MAX_TRIES), 3600)
        self._failures[who] = (tries, time.time() + wait)
        log.warning("Failed dashboard login from %s (attempt %d)%s",
                    who, tries, f", locked for {wait}s" if wait else "")

    def check_password(self, given, who):
        if self.locked_for(who):
            return False
        ok = hmac.compare_digest(given or "", self.cfg.dashboard_password)
        if ok:
            self._failures.pop(who, None)
            log.info("Dashboard login from %s", who)
        else:
            self._record_failure(who)
        return ok

    # ---- the cookie -----------------------------------------------------

    def new_cookie_value(self):
        return self._signer.dumps("in")

    def cookie_is_valid(self, value):
        if not value:
            return False
        try:
            self._signer.loads(value, max_age=SESSION_DAYS * 86400)
            return True
        except (BadSignature, SignatureExpired):
            return False
