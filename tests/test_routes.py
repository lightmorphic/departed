import io


def test_first_run_asks_for_an_account(tmp_path, monkeypatch):
    from app import create_app
    from app.config import Boot
    from tests.conftest import Clock, FakeMailer
    monkeypatch.setenv("DEPARTED_DATA_DIR", str(tmp_path / "fresh"))
    FakeMailer.reset()
    app = create_app(Boot(), mailer_factory=FakeMailer, now=Clock())
    app.testing = True
    c = app.test_client()
    assert c.get("/").headers["Location"] == "/setup"
    assert c.get("/login").headers["Location"] == "/setup"
    assert "Make the first account" in c.get("/setup").get_data(as_text=True)

    short = c.post("/setup", data={"username": "sam", "password": "short", "confirm": "short"})
    assert short.status_code == 400 and "at least 10" in short.get_data(as_text=True)

    r = c.post("/setup", data={"username": "sam", "password": "a-long-password",
                               "confirm": "a-long-password"})
    assert r.status_code == 302 and r.headers["Location"] == "/settings"
    assert c.get("/").status_code == 200
    # and it is not offered a second time
    assert c.get("/setup").headers["Location"] == "/login"
    assert app.extensions["departed"].db.user_by_name("sam").is_admin


def test_dashboard_and_settings_need_signing_in(world):
    for path in ("/", "/settings", "/people"):
        assert world.anon.get(path).headers["Location"] == "/login"
    for path in ("/checkin", "/test-email", "/files", "/settings/password"):
        assert world.anon.post(path).headers["Location"] == "/login"


def test_signing_in_and_out(world):
    c = world.anon
    bad = c.post("/login", data={"username": "charlie", "password": "wrong"})
    assert bad.status_code == 401 and "do not match" in bad.get_data(as_text=True)
    ok = c.post("/login", data={"username": "charlie", "password": world.password})
    assert ok.status_code == 302 and ok.headers["Location"] == "/"
    assert "Sign out" in c.get("/").get_data(as_text=True)
    c.post("/logout")
    assert c.get("/").headers["Location"] == "/login"


def test_repeated_wrong_passwords_are_slowed_down(world):
    c = world.anon
    for _ in range(5):
        c.post("/login", data={"username": "charlie", "password": "wrong"})
    blocked = c.post("/login", data={"username": "charlie", "password": world.password})
    assert blocked.status_code == 429


def test_the_emailed_link_never_asks_for_a_password(world):
    world.clock.advance(days=11)
    world.tick()
    r = world.anon.get(f"/checkin/{world.mailer.link()}")
    assert r.status_code == 200 and "Check-in received" in r.get_data(as_text=True)
    assert world.db.get_state(world.user_id).state == "waiting"
    assert world.anon.get("/checkin/nonsense").status_code == 410


def test_settings_save_and_keep_the_mail_password(world):
    c = world.client
    c.post("/settings", data={"owner_email": "new@example.com", "smtp_host": "mail.example.com",
                              "smtp_password": "hunter2222", "recipient_email": "them@example.com",
                              "smtp_from": "new@example.com", "base_url": "http://departed.test",
                              "smtp_security": "starttls"})
    store = world.switches.store(world.user_id)
    assert store.get("owner_email") == "new@example.com"
    assert store.get("smtp_password") == "hunter2222"
    # an empty password box means "leave it alone"
    c.post("/settings", data={"owner_email": "new@example.com", "smtp_password": ""})
    assert store.get("smtp_password") == "hunter2222"
    # and it is never rendered back into the page
    assert "hunter2222" not in c.get("/settings").get_data(as_text=True)


def test_the_mail_password_is_encrypted_on_disk(world):
    world.switches.store(world.user_id).set("smtp_password", "hunter2222")
    raw = (world.switches.boot.data_dir / "departed.db").read_bytes()
    assert b"hunter2222" not in raw


def test_upload_list_and_delete_files(world):
    c = world.client
    r = c.post("/files", data={"files": (io.BytesIO(b"sealed"), "vault.gpg")},
               content_type="multipart/form-data")
    assert r.headers["Location"] == "/settings?done=uploaded"
    assert (world.archive / "vault.gpg").read_bytes() == b"sealed"
    assert "vault.gpg" in c.get("/settings").get_data(as_text=True)

    # a nasty filename cannot escape the folder
    c.post("/files", data={"files": (io.BytesIO(b"x"), "../../etc/passwd")},
           content_type="multipart/form-data")
    assert not (world.switches.boot.data_dir / "etc").exists()

    c.post("/files/delete", data={"name": "vault.gpg"})
    assert not (world.archive / "vault.gpg").exists()


def test_the_letter_is_saved_and_encrypted(world):
    world.client.post("/settings/letter", data={"letter": "Dear Sam, look under the stairs."})
    assert world.switches.store(world.user_id).get("letter").startswith("Dear Sam")
    raw = (world.switches.boot.data_dir / "departed.db").read_bytes()
    assert b"under the stairs" not in raw


def test_changing_your_password(world):
    c = world.client
    c.post("/settings/password", data={"current": "wrong", "password": "another-long-one",
                                       "confirm": "another-long-one"})
    assert world.anon.post("/login", data={"username": "charlie", "password": "another-long-one"}).status_code == 401
    c.post("/settings/password", data={"current": world.password, "password": "another-long-one",
                                       "confirm": "another-long-one"})
    assert world.anon.post("/login", data={"username": "charlie", "password": "another-long-one"}).status_code == 302
    assert c.get("/").status_code == 200  # the browser that changed it stays signed in


def test_health_is_open(world):
    assert world.anon.get("/health").get_json()["ok"] is True
