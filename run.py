"""Single runtime command: python run.py"""
from waitress import serve

from app import create_app
from app.config import Boot

if __name__ == "__main__":
    boot = Boot()
    serve(create_app(boot, start_scheduler=True), host="0.0.0.0", port=boot.port, threads=4)
