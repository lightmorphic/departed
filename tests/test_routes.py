def test_dashboard_renders(world):
    r = world.client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Waiting" in html and "The folder is empty" in html
    assert "Check in now" in html and "Send a test email" in html


def test_button_checkin(world):
    world.clock.advance(days=3)
    r = world.client.post("/checkin")
    assert r.status_code == 302
    s = world.engine.db.get_state()
    assert s.last_checkin_at == world.clock()
    assert "Checked in" in world.client.get("/?done=checkin").get_data(as_text=True)


def test_link_page(world):
    world.clock.advance(days=11)
    world.engine.tick()
    token = world.mailer.link()
    r = world.client.get(f"/checkin/{token}")
    assert r.status_code == 200 and "Check-in received" in r.get_data(as_text=True)
    r = world.client.get(f"/checkin/{token}")
    assert r.status_code == 410 and "no longer valid" in r.get_data(as_text=True)
    assert world.client.get("/checkin/short").status_code == 410


def test_test_email_route(world):
    (world.archive / "a.gpg").write_bytes(b"a")
    assert world.client.post("/test-email").status_code == 302
    html = world.client.get("/?done=test").get_data(as_text=True)
    assert "Sent to me@example.com with a.gpg" in html


def test_health(world):
    j = world.client.get("/health").get_json()
    assert j["ok"] and j["state"] == "waiting"


def test_fired_state_shows_and_rearms(world):
    (world.archive / "a.gpg").write_bytes(b"a")
    world.clock.advance(days=15)
    for _ in range(5):
        world.clock.advance(hours=24)
        world.engine.tick()
    assert "Fired" in world.client.get("/").get_data(as_text=True)
    world.client.post("/checkin")
    assert world.engine.db.get_state().state == "waiting"


# ---- the password on the dashboard ----------------------------------------

def test_dashboard_needs_the_password(world):
    r = world.anon.get("/")
    assert r.status_code == 302 and r.headers["Location"] == "/login"
    assert world.anon.post("/checkin").headers["Location"] == "/login"
    assert world.anon.post("/test-email").headers["Location"] == "/login"
    assert world.engine.db.get_state().last_test_at is None


def test_signing_in_and_out(world):
    c = world.anon
    assert "password" in c.get("/login").get_data(as_text=True)
    bad = c.post("/login", data={"password": "wrong"})
    assert bad.status_code == 401 and "not right" in bad.get_data(as_text=True)
    assert c.get("/").status_code == 302

    ok = c.post("/login", data={"password": world.password})
    assert ok.status_code == 302 and ok.headers["Location"] == "/"
    assert c.get("/").status_code == 200
    assert "Sign out" in c.get("/").get_data(as_text=True)

    c.post("/logout")
    assert c.get("/").status_code == 302


def test_emailed_checkin_link_never_asks_for_the_password(world):
    world.clock.advance(days=11)
    world.engine.tick()
    token = world.mailer.link()
    r = world.anon.get(f"/checkin/{token}")
    assert r.status_code == 200 and "Check-in received" in r.get_data(as_text=True)
    assert world.engine.db.get_state().state == "waiting"


def test_repeated_wrong_passwords_are_slowed_down(world):
    c = world.anon
    for _ in range(5):
        c.post("/login", data={"password": "wrong"})
    blocked = c.post("/login", data={"password": world.password})
    assert blocked.status_code == 429
    assert c.get("/").status_code == 302


def test_no_password_set_locks_the_dashboard_but_not_the_switch(env, monkeypatch):
    from tests.conftest import Clock, FakeMailer
    from app import create_app
    from app.config import Config
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    (env / "archive" / "a.gpg").write_bytes(b"a")
    clock, mailer = Clock(), FakeMailer()
    app = create_app(Config(), mailer=mailer, now=clock)
    app.testing = True
    c = app.test_client()
    r = c.get("/")
    assert r.status_code == 503 and "Set a password" in r.get_data(as_text=True)
    assert c.get("/login").status_code == 503

    eng = app.extensions["departed"]
    for _ in range(21):
        clock.advance(days=1)
        eng.tick()
    assert eng.db.get_state().state == "fired"


def test_health_stays_open_for_the_container_check(world):
    assert world.anon.get("/health").get_json()["ok"] is True
