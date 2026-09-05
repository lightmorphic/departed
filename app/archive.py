"""Reads and writes the folder of files.

It never encrypts, never decrypts and never looks inside. Files arrive already
locked by you and are attached exactly as they are.
"""
import io
import re
import zipfile
from datetime import datetime, timezone

SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name):
    """A filename we are willing to write. No paths, no surprises."""
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = SAFE.sub("_", name).lstrip(".")
    return name[:120] or "file"


def list_files(folder):
    """Every regular file in the folder, ignoring dotfiles."""
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        st = path.stat()
        out.append({
            "name": path.name,
            "size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
            "path": path,
        })
    return out


def summary(folder):
    files = list_files(folder)
    return {
        "exists": folder.is_dir(),
        "files": files,
        "count": len(files),
        "total_size": sum(f["size"] for f in files),
        "last_modified": max((f["modified"] for f in files), default=None),
    }


def save_upload(folder, filename, stream):
    """Write one uploaded file into the folder. Returns the name it was given."""
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_name(filename)
    target = folder / name
    stem, dot, ext = name.partition(".")
    n = 2
    while target.exists():
        name = f"{stem}-{n}{dot}{ext}"
        target = folder / name
        n += 1
    stream.save(target)
    return name


def delete_file(folder, filename):
    """Remove one file by name. Returns True if something was removed."""
    target = folder / safe_name(filename)
    if target.is_file() and target.parent == folder:
        target.unlink()
        return True
    return False


def build_attachment(folder, stamp):
    """(filename, bytes) to attach, or None when there is nothing to send.
    One file goes as it is. Several are zipped, uncompressed."""
    files = list_files(folder)
    if not files:
        return None
    if len(files) == 1:
        f = files[0]
        return f["path"].name, f["path"].read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f["path"], arcname=f["name"])
    return f"departed-archive-{stamp:%Y%m%d-%H%M}.zip", buf.getvalue()
