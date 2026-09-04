"""Reads the archive folder. Never encrypts, never decrypts - attaches files as they are."""
import io
import zipfile
from datetime import datetime, timezone


def list_files(folder):
    """Every regular file under the folder, recursively, ignoring dotfiles and dot-folders."""
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.is_file():
            st = path.stat()
            out.append({
                "name": str(rel),
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


def build_attachment(folder, stamp):
    """(filename, bytes) to attach, or None when the folder is empty.
    One file goes as-is. Several are zipped, uncompressed, keeping their relative paths."""
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
