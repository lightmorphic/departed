from flask import (Blueprint, abort, current_app, g, jsonify, make_response,
                   redirect, render_template, request)

from . import archive
from .auth import COOKIE, SESSION_DAYS
from .config import VERSION
from .engine import _hash
from .store import SECURITY_CHOICES, hash_password, password_matches

bp = Blueprint("main", __name__)

STATE_WORDS = {
    "waiting": ("✓", "Waiting", "Timer running. No check-in is outstanding."),
    "reminding": ("!", "Reminding", "A check-in email has been sent and not yet answered."),
    "fired": ("●", "Fired", "The archive has been sent. Nothing more will be sent."),
}

OPEN_ENDPOINTS = {"main.setup", "main.do_setup", "main.login", "main.do_login",
                  "main.checkin_link", "main.health", "static"}


def _switches():
    return current_app.extensions["departed"]


def _auth():
    return current_app.extensions["departed_auth"]


def _who():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _secure_cookie(cfg):
    return bool(cfg.base_url.startswith("https")) or request.is_secure


def _fmt(dt, tz):
    return dt.astimezone(tz).strftime("%a %-d %b %Y, %H:%M") if dt else "never"


def _size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


@bp.before_app_request
def load_user():
    """Work out who is asking, and send everyone else to the right door."""
    g.user = None
    g.engine = None
    switches = _switches()
    if request.endpoint == "static":
        return None
    if not switches.db.any_users():
        if request.endpoint in ("main.setup", "main.do_setup", "main.health"):
            return None
        return redirect("/setup")
    g.user = _auth().user_from_cookie(request.cookies.get(COOKIE))
    if g.user:
        g.engine = switches.engine(g.user.id)
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if not g.user:
        return redirect("/login")
    return None


@bp.app_context_processor
def inject():
    return {"app_version": VERSION, "user": g.get("user")}


# ---- first run --------------------------------------------------------------

@bp.get("/setup")
def setup():
    if _switches().db.any_users():
        return redirect("/login")
    return render_template("setup.html", error=None)


@bp.post("/setup")
def do_setup():
    db = _switches().db
    if db.any_users():
        return redirect("/login")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    error = _account_problem(db, username, password, request.form.get("confirm") or "")
    if error:
        return render_template("setup.html", error=error), 400
    digest, salt = hash_password(password)
    user_id = db.add_user(username, digest, salt, is_admin=True)
    resp = make_response(redirect("/settings"))
    _sign_in_cookie(resp, db.user(user_id))
    return resp


def _account_problem(db, username, password, confirm):
    if len(username) < 2:
        return "Pick a username of at least two characters."
    if not username.replace("-", "").replace("_", "").replace(".", "").isalnum():
        return "A username can have letters, numbers, dots, dashes and underscores."
    if db.user_by_name(username):
        return "There is already an account with that name."
    if len(password) < 10:
        return "Use a password of at least 10 characters."
    if password != confirm:
        return "The two passwords are not the same."
    return None


def _sign_in_cookie(resp, user):
    cfg = _switches().store(user.id).current()
    resp.set_cookie(COOKIE, _auth().new_cookie_value(user), max_age=SESSION_DAYS * 86400,
                    httponly=True, samesite="Lax", secure=_secure_cookie(cfg))


# ---- signing in -------------------------------------------------------------

@bp.get("/login")
def login():
    if not _switches().db.any_users():
        return redirect("/setup")
    if g.user:
        return redirect("/")
    return render_template("login.html", error=None, wait=_auth().locked_for(_who()))


@bp.post("/login")
def do_login():
    auth = _auth()
    who = _who()
    wait = auth.locked_for(who)
    if wait:
        return render_template("login.html", error="Too many attempts.", wait=wait), 429
    user = auth.sign_in(request.form.get("username"), request.form.get("password"), who)
    if not user:
        return render_template("login.html", error="That username and password do not match.",
                               wait=auth.locked_for(who)), 401
    resp = make_response(redirect("/"))
    _sign_in_cookie(resp, user)
    return resp


@bp.post("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.delete_cookie(COOKIE)
    return resp


# ---- the dashboard ----------------------------------------------------------

@bp.get("/")
def index():
    eng = g.engine
    cfg = eng.cfg
    s = eng.db.get_state(g.user.id)
    arc = archive.summary(cfg.archive_dir)
    mark, word, blurb = STATE_WORDS.get(s.state, ("?", s.state, ""))
    if s.fire_pending:
        mark, word = "!", "Firing"
        blurb = ("Due to fire. " + ("There are no files to send, so an alert was sent instead."
                 if s.last_fire_error == "There are no files to send." else
                 "Sending the archive; retrying until the mail goes through."))
    return render_template(
        "index.html",
        s=s, cfg=cfg, mark=mark, word=word, blurb=blurb,
        fmt=lambda dt: _fmt(dt, cfg.tz), size=_size,
        next_email=eng.next_email_at(s),
        fire_at=eng.expected_fire_at(s),
        archive=arc,
        big_attachment=arc["total_size"] > 20 * 1024 * 1024,
        events=eng.db.recent_events(g.user.id),
        done=request.args.get("done"),
        interval_days=cfg.checkin_interval.total_seconds() / 86400,
    )


@bp.post("/checkin")
def checkin_button():
    g.engine.checkin_now()
    return redirect("/?done=checkin")


@bp.get("/checkin/<token>")
def checkin_link(token):
    """Open on purpose: this arrives by email and has to work with one tap."""
    switches = _switches()
    ok = False
    next_due = "never"
    if 20 <= len(token) <= 128:
        state = switches.db.state_by_token_hash(_hash(token))
        if state:
            eng = switches.engine(state.user_id)
            ok = eng.checkin_with_token(token)
            if ok:
                next_due = _fmt(eng.next_email_at(eng.db.get_state(state.user_id)), eng.cfg.tz)
    return render_template("checkin.html", ok=ok, next_due=next_due), (200 if ok else 410)


@bp.post("/test-email")
def test_email():
    g.engine.send_test()
    return redirect("/?done=test")


@bp.get("/health")
def health():
    return jsonify(ok=True, version=VERSION, accounts=_switches().db.any_users())


# ---- settings ---------------------------------------------------------------

@bp.get("/settings")
def settings():
    switches = _switches()
    cfg = switches.store(g.user.id).current()
    return render_template("settings.html", cfg=cfg, security_choices=SECURITY_CHOICES,
                           archive=archive.summary(cfg.archive_dir), size=_size,
                           fmt=lambda dt: _fmt(dt, cfg.tz),
                           max_mb=current_app.extensions["departed_boot"].max_upload_mb,
                           done=request.args.get("done"), error=request.args.get("error"))


@bp.post("/settings")
def save_settings():
    store = _switches().store(g.user.id)
    form = {name: request.form.get(name, "") for name in request.form}
    # An untouched password field means "leave it as it was".
    if not form.get("smtp_password"):
        form.pop("smtp_password", None)
    store.set_many(form)
    g.engine.db.log_event(g.user.id, "settings", "Settings changed.")
    return redirect("/settings?done=saved")


@bp.post("/settings/letter")
def save_letter():
    _switches().store(g.user.id).set("letter", request.form.get("letter", ""))
    g.engine.db.log_event(g.user.id, "settings", "The letter was changed.")
    return redirect("/settings?done=letter")


@bp.post("/settings/password")
def change_password():
    db = _switches().db
    current = request.form.get("current") or ""
    new = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""
    if not password_matches(db.user(g.user.id), current):
        return redirect("/settings?error=Your+current+password+is+not+right")
    if len(new) < 10:
        return redirect("/settings?error=Use+a+password+of+at+least+10+characters")
    if new != confirm:
        return redirect("/settings?error=The+two+new+passwords+are+not+the+same")
    digest, salt = hash_password(new)
    db.set_user_password(g.user.id, digest, salt)
    db.log_event(g.user.id, "settings", "The sign-in password was changed.")
    resp = make_response(redirect("/settings?done=password"))
    _sign_in_cookie(resp, db.user(g.user.id))
    return resp


# ---- the files --------------------------------------------------------------

@bp.post("/files")
def upload_files():
    cfg = _switches().store(g.user.id).current()
    saved = []
    for item in request.files.getlist("files"):
        if item and item.filename:
            saved.append(archive.save_upload(cfg.archive_dir, item.filename, item))
    if not saved:
        return redirect("/settings?error=No+file+was+chosen")
    g.engine.db.log_event(g.user.id, "files", f"Added to the archive: {', '.join(saved)}.")
    return redirect("/settings?done=uploaded")


@bp.post("/files/delete")
def delete_file():
    cfg = _switches().store(g.user.id).current()
    name = request.form.get("name", "")
    if archive.delete_file(cfg.archive_dir, name):
        g.engine.db.log_event(g.user.id, "files", f"Removed from the archive: {name}.")
        return redirect("/settings?done=deleted")
    return redirect("/settings?error=That+file+is+not+there")


# ---- people -----------------------------------------------------------------

@bp.get("/people")
def people():
    if not g.user.is_admin:
        abort(403)
    db = _switches().db
    rows = []
    for u in db.users():
        cfg = _switches().store(u.id).current()
        state = db.get_state(u.id)
        rows.append({"user": u, "state": state.state, "ready": cfg.ready,
                     "files": archive.summary(cfg.archive_dir)["count"]})
    return render_template("people.html", rows=rows, error=request.args.get("error"),
                           done=request.args.get("done"))


@bp.post("/people")
def add_person():
    if not g.user.is_admin:
        abort(403)
    db = _switches().db
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    problem = _account_problem(db, username, password, request.form.get("confirm") or "")
    if problem:
        return redirect("/people?error=" + problem.replace(" ", "+"))
    digest, salt = hash_password(password)
    db.add_user(username, digest, salt, is_admin=bool(request.form.get("is_admin")))
    return redirect("/people?done=added")


@bp.post("/people/delete")
def delete_person():
    if not g.user.is_admin:
        abort(403)
    switches = _switches()
    db = switches.db
    user_id = int(request.form.get("user_id", 0))
    if user_id == g.user.id:
        return redirect("/people?error=You+cannot+remove+your+own+account")
    victim = db.user(user_id)
    if not victim:
        return redirect("/people?error=No+such+account")
    if victim.is_admin and db.admin_count() <= 1:
        return redirect("/people?error=That+is+the+only+administrator")
    folder = switches.archive_dir(user_id)
    if folder.is_dir():
        for f in archive.list_files(folder):
            f["path"].unlink()
        folder.rmdir()
    db.delete_user(user_id)
    return redirect("/people?done=removed")


@bp.errorhandler(413)
def too_big(_):
    mb = current_app.extensions["departed_boot"].max_upload_mb
    return redirect(f"/settings?error=That+file+is+bigger+than+{mb}+MB")
