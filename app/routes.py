from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from . import archive
from .config import VERSION

bp = Blueprint("main", __name__)

STATE_WORDS = {
    "waiting": ("✓", "Waiting", "Timer running. No check-in is outstanding."),
    "reminding": ("!", "Reminding", "A check-in email has been sent and not yet answered."),
    "fired": ("●", "Fired", "The archive has been sent. Nothing more will be sent."),
}


def _engine():
    return current_app.extensions["departed"]


def _fmt(dt, tz):
    return dt.astimezone(tz).strftime("%a %-d %b %Y, %H:%M") if dt else "never"


def _size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


@bp.app_context_processor
def inject():
    return {"app_version": VERSION}


@bp.get("/")
def index():
    eng = _engine()
    cfg = eng.cfg
    s = eng.db.get_state()
    arc = archive.summary(cfg.archive_dir)
    mark, word, blurb = STATE_WORDS.get(s.state, ("?", s.state, ""))
    if s.fire_pending:
        mark, word = "!", "Firing"
        blurb = ("Due to fire. " + ("The archive folder is empty, so an alert was sent instead."
                 if s.last_fire_error == "Archive folder is empty." else
                 "Sending the archive; retrying until the mail goes through."))
    fmt = lambda dt: _fmt(dt, cfg.tz)  # noqa: E731
    return render_template(
        "index.html",
        s=s, cfg=cfg, mark=mark, word=word, blurb=blurb, fmt=fmt, size=_size,
        next_email=eng.next_email_at(s),
        fire_at=eng.expected_fire_at(s),
        archive=arc,
        big_attachment=arc["total_size"] > 20 * 1024 * 1024,
        events=eng.db.recent_events(),
        done=request.args.get("done"),
        interval_days=cfg.checkin_interval.total_seconds() / 86400,
    )


@bp.post("/checkin")
def checkin_button():
    _engine().checkin_now()
    return redirect("/?done=checkin")


@bp.get("/checkin/<token>")
def checkin_link(token):
    eng = _engine()
    ok = eng.checkin_with_token(token) if 20 <= len(token) <= 128 else False
    s = eng.db.get_state()
    return render_template("checkin.html", ok=ok,
                           next_due=_fmt(eng.next_email_at(s), eng.cfg.tz)), (200 if ok else 410)


@bp.post("/test-email")
def test_email():
    _engine().send_test()
    return redirect("/?done=test")


@bp.get("/health")
def health():
    s = _engine().db.get_state()
    return jsonify(ok=True, state=s.state, fire_pending=s.fire_pending, version=VERSION)
