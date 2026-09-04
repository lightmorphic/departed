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
