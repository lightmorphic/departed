"""Single runtime command: python run.py"""
from waitress import serve

from app import create_app
from app.config import Config

if __name__ == "__main__":
    cfg = Config()
    serve(create_app(cfg, start_scheduler=True), host="0.0.0.0", port=cfg.port, threads=4)
