"""Start-up.

Docker hands the app a folder from the host, and that folder usually arrives
owned by root, because whatever made it was root. The app itself runs as an
ordinary user and cannot write there, so it used to fall over at the first
line with a database error and nothing helpful to say.

So: if we start as root, we make the folder, hand it to the app's own user, and
only then drop to that user for good. Nothing after this line runs as root. If
we were started as somebody else already, we leave the folder alone and simply
check we can write to it, saying so plainly if we cannot.
"""
import os
import pwd
import sys
from pathlib import Path

APP_UID = 1000
APP_GID = 1000


def take_ownership(folder):
    """Hand the folder, and anything already in it, to the app's own user."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = [folder]
    try:
        paths += list(folder.rglob("*"))
    except OSError:
        pass
    changed = 0
    for path in paths:
        try:
            info = path.stat()
            if info.st_uid != APP_UID or info.st_gid != APP_GID:
                os.chown(path, APP_UID, APP_GID)
                changed += 1
        except OSError as e:
            print(f"departed: could not take ownership of {path}: {e}", file=sys.stderr)
    if changed:
        print(f"departed: took ownership of {changed} item(s) in {folder}", flush=True)


def become(uid, gid):
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def check_writable(folder):
    probe = folder / ".departed-write-test"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def main():
    data = Path(os.environ.get("DEPARTED_DATA_DIR", "/data"))

    if os.geteuid() == 0:
        take_ownership(data)
        become(APP_UID, APP_GID)

    if not check_writable(data):
        who = pwd.getpwuid(os.geteuid()).pw_name if os.geteuid() else "root"
        print(
            "\ndeparted: cannot write to its data folder.\n\n"
            f"  The folder is {data} inside the container, and it is running as {who} "
            f"(user {os.geteuid()}).\n"
            "  On the machine, give the folder you mounted to that user:\n\n"
            f"      sudo chown -R {APP_UID}:{APP_GID} /opt/departed\n\n"
            "  Then start it again.\n",
            file=sys.stderr, flush=True)
        raise SystemExit(1)

    here = Path(__file__).resolve().parent
    os.execv(sys.executable, [sys.executable, str(here / "run.py")])


if __name__ == "__main__":
    main()
