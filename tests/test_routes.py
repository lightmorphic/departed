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


def test_the_web_address_is_offered_rather_than_asked_for(world):
    """The app cannot know what address you reach it on, so it offers the one
    the browser is using rather than leaving an empty box."""
    world.switches.store(world.user_id).set("base_url", "")
    page = world.client.get("/settings").get_data(as_text=True)
    assert 'value="http://localhost"' in page
    assert "Use the address I am on now" in page


def test_it_believes_the_proxy_about_the_address(world):
    """Behind a tunnel or a proxy the app is reached on https at a name it never
    sees, so the forwarded headers are what it offers."""
    from app.routes import _origin
    with world.app.test_request_context("/settings", headers={
            "Host": "127.0.0.1:8080",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "departed.example.com"}):
        assert _origin() == "https://departed.example.com"
    with world.app.test_request_context("/settings", headers={"Host": "box.local:4160"}):
        assert _origin() == "http://box.local:4160"


def test_it_warns_when_the_address_only_works_at_home(world):
    store = world.switches.store(world.user_id)
    for local in ("http://localhost:4160", "http://127.0.0.1:4160", "http://homelab:4160",
                  "http://192.168.1.20:4160"):
        store.set("base_url", local)
        assert store.current().base_url_is_local is True
        assert "only works on this network" in world.client.get("/settings").get_data(as_text=True)

    for reachable in ("https://departed.example.com", "https://homelab.something.ts.net:4160"):
        store.set("base_url", reachable)
        assert store.current().base_url_is_local is False
        assert "only works on this network" not in world.client.get("/settings").get_data(as_text=True)


def test_it_shows_what_a_check_in_link_will_look_like(world):
    store = world.switches.store(world.user_id)
    store.set("base_url", "https://departed.example.com")
    assert store.current().example_checkin_url.startswith("https://departed.example.com/checkin/")
    assert "https://departed.example.com/checkin/" in world.client.get("/settings").get_data(as_text=True)


def test_settings_save_one_field_at_a_time(world):
    c = world.client
    store = world.switches.store(world.user_id)
    r = c.post("/settings/field", data={"name": "owner_email", "value": "new@example.com"})
    assert r.get_json() == {"ok": True}
    assert store.get("owner_email") == "new@example.com"

    # saving the same value again changes nothing and says so
    assert c.post("/settings/field", data={"name": "owner_email", "value": "new@example.com"}
                  ).get_json()["unchanged"] is True

    # an empty mail password means "leave it alone"
    store.set("smtp_password", "hunter2222")
    assert c.post("/settings/field", data={"name": "smtp_password", "value": ""}
                  ).get_json()["unchanged"] is True
    assert store.get("smtp_password") == "hunter2222"

    # and nothing outside the known settings can be written
    assert c.post("/settings/field", data={"name": "password_hash", "value": "x"}).status_code == 400
    assert c.post("/settings/field", data={"name": "sealed", "value": "1"}).status_code == 400

    assert world.anon.post("/settings/field", data={"name": "owner_email", "value": "x"}
                           ).headers["Location"] == "/login"


def test_the_mail_test_sends_only_to_you(world):
    r = world.client.post("/settings/test-mail").get_json()
    assert r["ok"] is True and r["sent_to"] == "me@example.com"
    m = world.mailer.last()
    assert m["to"] == "me@example.com"
    assert m["attachment"] is None
    assert "mail settings work" in m["subject"]
    assert not any(x["to"] == "them@example.com" for x in world.mailer.sent)
    assert world.db.get_state(world.user_id).state == "waiting"


def test_the_mail_test_reports_a_failure_plainly(world):
    world.mailer.fail = True
    r = world.client.post("/settings/test-mail").get_json()
    assert r["ok"] is False and "smtp down" in r["error"]
    # and the jargon gets translated
    import smtplib
    from app.mailer import in_plain_words
    assert "username and password" in in_plain_words(smtplib.SMTPAuthenticationError(535, b"nope"))
    assert "could not be found" in in_plain_words(OSError("Name or service not known"))
    assert "Nothing answered" in in_plain_words(ConnectionRefusedError(111, "Connection refused"))
    assert "did not answer in time" in in_plain_words(TimeoutError("timed out"))
    world.mailer.fail = False
    world.switches.store(world.user_id).set("smtp_host", "")
    assert "Fill in" in world.client.post("/settings/test-mail").get_json()["error"]


def test_the_top_bar_carries_the_launcher_and_stays_put(world):
    page = world.client.get("/").get_data(as_text=True)
    assert '<div id="all-apps"></div>' in page
    assert 'apps.lightmorphic.com/launcher.js' in page
    # last thing in the bar
    bar = page[page.index('class="top-actions"'):page.index("</header>")]
    assert bar.rindex('id="all-apps"') > bar.rindex("Sign out")


def test_nothing_else_in_the_app_reaches_outside(world):
    """The launcher is the one exception, and it must stay the only one."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    allowed = {
        "apps.lightmorphic.com/launcher.js",   # the app launcher, the one exception
        "www.w3.org/2000/svg",                 # an XML namespace, not an address
        "departed.example.com",                # a placeholder in a form
    }
    found = set()
    for f in list(root.rglob("*.html")) + list(root.rglob("*.js")) + list(root.rglob("*.css")):
        for url in re.findall(r'https?://[^\s"\')]+', f.read_text()):
            host = url.split("://", 1)[1]
            if not any(host.startswith(a) for a in allowed):
                found.add(f"{f.name}: {url}")
    assert not found, f"something new reaches outside: {found}"



def test_there_is_no_light_mode_left(world):
    """One palette, dark, with nothing to switch and nothing remembered."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for f in list((root / "app").rglob("*.html")) + list((root / "app" / "static" / "css").rglob("*.css")):
        text = f.read_text()
        for gone in ("data-theme", "prefers-color-scheme", "theme-toggle", "localStorage"):
            assert gone not in text, f"{f.name} still mentions {gone}"
    page = world.client.get("/").get_data(as_text=True)
    assert "theme" not in page.lower()
    css = (root / "app" / "static" / "css" / "main.css").read_text()
    assert "color-scheme: dark" in css
