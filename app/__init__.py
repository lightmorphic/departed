import logging
import threading
import time
from logging.handlers import RotatingFileHandler

from flask import Flask

from .auth import Auth
from .config import VERSION, Boot
from .db import Database
from .engine import Engine, utcnow
from .mailer import Mailer
from .store import SettingsStore, load_key

log = logging.getLogger("departed")


def setup_logging(boot):
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        try:
            boot.data_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(boot.data_dir / "departed.log", maxBytes=2_000_000, backupCount=3)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError as e:
            root.warning("Cannot write the log file in %s: %s", boot.data_dir, e)


class Switches:
    """Builds one engine per person, sharing the database and the mail sender."""

    def __init__(self, boot, db, key, mailer_factory, now):
        self.boot = boot
        self.db = db
        self.key = key
        self.now = now
        self._mailer_factory = mailer_factory
        self._tokens = {}

    def archive_dir(self, user_id):
        return self.boot.data_dir / "archives" / str(user_id)

    def store(self, user_id):
        return SettingsStore(self.db, self.key, user_id, self.archive_dir(user_id))

    def engine(self, user_id):
        store = self.store(user_id)
        return Engine(user_id, store.current, self.db,
                      self._mailer_factory(store.current), self.now, self._tokens)

    def tick_all(self):
        for user in self.db.users():
            try:
                self.engine(user.id).tick()
            except Exception:  # noqa: BLE001 - one person's problem never stops the others
                log.exception("The timer tick failed for user %s", user.id)


def create_app(boot=None, mailer_factory=None, now=utcnow, start_scheduler=False):
    boot = boot or Boot()
    setup_logging(boot)
    db = Database(boot.data_dir / "departed.db", now)
    key = load_key(boot.data_dir)
    switches = Switches(boot, db, key, mailer_factory or Mailer, now)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = boot.max_upload_mb * 1024 * 1024
    app.extensions["departed"] = switches
    app.extensions["departed_auth"] = Auth(db, boot.data_dir)
    app.extensions["departed_boot"] = boot

    from .routes import bp
    app.register_blueprint(bp)

    if not db.any_users():
        log.info("No accounts yet. Open the app in a browser to make the first one.")

    if start_scheduler:
        def loop():
            while True:
                try:
                    switches.tick_all()
                except Exception:  # noqa: BLE001
                    log.exception("The timer failed")
                time.sleep(boot.tick_seconds)
        threading.Thread(target=loop, name="departed-timer", daemon=True).start()
        log.info("Departed %s started, checking every %ss", VERSION, boot.tick_seconds)
    return app
