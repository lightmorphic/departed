"""Sign-in, one account per person.

The check-in link that arrives by email is deliberately left open: it carries its
own long single-use token, and it has to work with one tap from any phone.
"""
import logging
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .store import password_matches

log = logging.getLogger("departed.auth")

COOKIE = "departed_session"
SESSION_DAYS = 30
MAX_TRIES = 5
LOCKOUT_SECONDS = 60


def _key_file(data_dir):
    """A random key kept beside the database, so sign-ins survive a restart."""
    path = Path(data_dir) / "session.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


class Auth:
    def __init__(self, db, data_dir):
        self.db = db
        self._failures = {}
        self._signer = URLSafeTimedSerializer(_key_file(data_dir), salt="departed-login")

    # ---- attempts -------------------------------------------------------

    def locked_for(self, who):
        _, until = self._failures.get(who, (0, 0))
        return max(0, int(until - time.time()))

    def _record_failure(self, who, username):
        tries, _ = self._failures.get(who, (0, 0))
        tries += 1
        wait = 0
        if tries >= MAX_TRIES:
            wait = min(LOCKOUT_SECONDS * 2 ** (tries - MAX_TRIES), 3600)
        self._failures[who] = (tries, time.time() + wait)
        log.warning("Failed sign-in for '%s' from %s (attempt %d)%s",
                    username, who, tries, f", locked for {wait}s" if wait else "")

    def sign_in(self, username, password, who):
        """Returns the user on success, None otherwise."""
        if self.locked_for(who):
            return None
        user = self.db.user_by_name((username or "").strip())
        if not password_matches(user, password):
            self._record_failure(who, username)
            return None
        self._failures.pop(who, None)
        log.info("Signed in as '%s' from %s", user.username, who)
        return user

    # ---- the cookie -----------------------------------------------------

    def new_cookie_value(self, user):
        # The password fingerprint means changing a password ends that person's
        # other sign-ins.
        return self._signer.dumps({"u": user.id, "p": user.password_hash[:22]})

    def user_from_cookie(self, value):
        if not value:
            return None
        try:
            data = self._signer.loads(value, max_age=SESSION_DAYS * 86400)
        except (BadSignature, SignatureExpired):
            return None
        user = self.db.user(data.get("u"))
        if not user or user.password_hash[:22] != data.get("p"):
            return None
        return user
