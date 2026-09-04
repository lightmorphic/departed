import logging
import threading
import time
from logging.handlers import RotatingFileHandler

from flask import Flask

from .config import VERSION, Config
from .db import Database
from .engine import Engine, utcnow
from .mailer import Mailer


def setup_logging(cfg):
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
    try:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(cfg.data_dir / "departed.log", maxBytes=2_000_000, backupCount=3)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        root.warning("Cannot write the log file in %s: %s", cfg.data_dir, e)


def create_app(cfg=None, mailer=None, now=utcnow, start_scheduler=False):
    cfg = cfg or Config()
    setup_logging(cfg)
    db = Database(cfg.data_dir / "departed.db", now)
    engine = Engine(cfg, db, mailer or Mailer(cfg), now)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.extensions["departed"] = engine

    from .routes import bp
    app.register_blueprint(bp)

    for p in cfg.problems:
        logging.getLogger("departed").error("Configuration problem: %s", p)

    if start_scheduler:
        def loop():
            while True:
                try:
                    engine.tick()
                except Exception:  # noqa: BLE001
                    logging.getLogger("departed").exception("The timer tick failed")
                time.sleep(cfg.tick_seconds)
        threading.Thread(target=loop, name="departed-timer", daemon=True).start()
        logging.getLogger("departed").info("Departed %s started, checking every %ss", VERSION, cfg.tick_seconds)
    return app
