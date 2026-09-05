"""The container has to cope with the folder Docker gives it, which is usually
owned by root because whatever made it was root."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import entrypoint  # noqa: E402


def test_it_notices_a_folder_it_cannot_write_to(tmp_path):
    good = tmp_path / "fine"
    assert entrypoint.check_writable(good) is True
    assert good.is_dir()

    if os.geteuid() == 0:
        import pytest
        pytest.skip("root can write anywhere")
    bad = tmp_path / "locked"
    bad.mkdir()
    bad.chmod(0o500)
    try:
        assert entrypoint.check_writable(bad) is False
    finally:
        bad.chmod(0o700)


def test_it_says_what_to_do_rather_than_throwing_a_stack_trace(tmp_path):
    if os.geteuid() == 0:
        import pytest
        pytest.skip("root can write anywhere")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        out = subprocess.run([sys.executable, str(ROOT / "entrypoint.py")],
                             env={**os.environ, "DEPARTED_DATA_DIR": str(locked)},
                             capture_output=True, text=True, timeout=60)
    finally:
        locked.chmod(0o700)
    assert out.returncode == 1
    assert "cannot write to its data folder" in out.stderr
    assert "chown -R 1000:1000" in out.stderr
    assert "Traceback" not in out.stderr


def test_it_hands_the_whole_folder_over(tmp_path, monkeypatch):
    """Everything already in the folder is handed over too, not just the folder."""
    folder = tmp_path / "data"
    (folder / "archives" / "1").mkdir(parents=True)
    (folder / "departed.db").write_bytes(b"x")
    (folder / "archives" / "1" / "Open-me.html").write_bytes(b"y")

    asked = []
    monkeypatch.setattr(entrypoint.os, "chown", lambda p, u, g: asked.append((str(p), u, g)))
    # Pretend the app's user is somebody these files do not belong to, which is
    # what happens on a real machine when Docker made the folder as root.
    monkeypatch.setattr(entrypoint, "APP_UID", 4242)
    monkeypatch.setattr(entrypoint, "APP_GID", 4242)
    entrypoint.take_ownership(folder)

    handed = {p for p, _, _ in asked}
    assert str(folder) in handed
    assert str(folder / "departed.db") in handed
    assert str(folder / "archives" / "1" / "Open-me.html") in handed
    assert all(u == 4242 and g == 4242 for _, u, g in asked)


def test_it_makes_the_folder_if_it_is_not_there(tmp_path):
    folder = tmp_path / "not-yet"
    entrypoint.take_ownership(folder)
    assert folder.is_dir()
