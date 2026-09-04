def run_days(w, days):
    """Tick once an hour for the given number of days."""
    for _ in range(days * 24):
        w.clock.advance(hours=1)
        w.engine.tick()


def test_nothing_happens_before_interval(world):
    run_days(world, 9)
    assert world.mailer.sent == []
    assert world.engine.db.get_state().state == "waiting"


def test_checkin_email_then_reminders_then_fire(world):
    (world.archive / "secret.gpg").write_bytes(b"blob")
    run_days(world, 10)
    subjects = [m["subject"] for m in world.mailer.sent]
    assert subjects == ["Departed: please check in"]
    assert world.engine.db.get_state().state == "reminding"

    run_days(world, 3)
    subjects = [m["subject"] for m in world.mailer.sent]
    assert [s for s in subjects if "reminder" in s] == [
        "Departed: reminder 1 of 3 - please check in",
        "Departed: reminder 2 of 3 - please check in",
        "Departed: reminder 3 of 3 - please check in",
    ]
    assert world.engine.db.get_state().state == "reminding"

    run_days(world, 1)
    s = world.engine.db.get_state()
    assert s.state == "fired"
    fire = [m for m in world.mailer.sent if m["to"] == "them@example.com"]
    assert len(fire) == 1
    assert fire[0]["attachment"] == ("secret.gpg", b"blob")
    assert "passphrase" in fire[0]["body"]
    assert "Departed: the switch has fired" in [m["subject"] for m in world.mailer.sent]

    # It fires once and then stops.
    before = len(world.mailer.sent)
    run_days(world, 30)
    assert len(world.mailer.sent) == before
    kinds = [e["kind"] for e in world.engine.db.recent_events()]
    assert kinds.count("fired") == 1


def test_link_resets_the_clock_and_is_single_use(world):
    run_days(world, 10)
    token = world.mailer.link()
    assert token and len(token) >= 32
    assert world.engine.checkin_with_token(token) is True
    s = world.engine.db.get_state()
    assert s.state == "waiting" and s.token_hash is None
    assert world.mailer.last()["subject"] == "Departed: check-in received"
    assert world.engine.checkin_with_token(token) is False
    assert world.engine.checkin_with_token("nonsense") is False
    # A fresh cycle starts 10 days after the click, not from the old timer.
    run_days(world, 9)
    assert world.engine.db.get_state().state == "waiting"
    run_days(world, 1)
    assert world.engine.db.get_state().state == "reminding"


def test_reminders_use_the_same_link(world):
    run_days(world, 11)
    first = world.mailer.sent[0]["body"]
    second = world.mailer.sent[1]["body"]
    assert world.mailer.link() in first and world.mailer.link() in second


def test_empty_archive_alerts_instead_of_firing(world):
    run_days(world, 15)
    s = world.engine.db.get_state()
    assert s.state == "reminding" and s.fire_pending
    assert not any(m["to"] == "them@example.com" for m in world.mailer.sent)
    alerts = [m for m in world.mailer.sent if "ALERT" in m["subject"]]
    assert len(alerts) == 2  # one a day, not one a tick
    # Files appear later: it fires.
    (world.archive / "a.gpg").write_bytes(b"a")
    world.clock.advance(minutes=6)
    world.engine.tick()
    assert world.engine.db.get_state().state == "fired"


def test_smtp_failure_on_firing_keeps_retrying(world):
    (world.archive / "a.gpg").write_bytes(b"a")
    run_days(world, 13)
    world.mailer.fail = True
    run_days(world, 2)
    s = world.engine.db.get_state()
    assert s.state != "fired" and s.fire_pending and s.fire_attempts > 5
    assert "smtp down" in s.last_fire_error
    world.mailer.fail = False
    world.clock.advance(minutes=6)
    world.engine.tick()
    assert world.engine.db.get_state().state == "fired"


def test_long_outage_runs_the_reminders_before_firing(world):
    (world.archive / "a.gpg").write_bytes(b"a")
    world.clock.advance(days=60)  # server was off
    world.engine.tick()
    assert world.engine.db.get_state().state == "reminding"
    assert not any(m["to"] == "them@example.com" for m in world.mailer.sent)
    run_days(world, 3)
    assert world.engine.db.get_state().state == "reminding"
    run_days(world, 1)
    assert world.engine.db.get_state().state == "fired"


def test_state_survives_restart(world):
    from app import create_app
    from app.config import Config
    run_days(world, 11)
    app2 = create_app(Config(), mailer=world.mailer, now=world.clock)
    s = app2.extensions["departed"].db.get_state()
    assert s.state == "reminding" and s.reminders_sent == 1


def test_config_problems_stop_everything(env, monkeypatch):
    from tests.conftest import Clock, FakeMailer
    from app import create_app
    from app.config import Config
    monkeypatch.setenv("SMTP_HOST", "")
    clock, mailer = Clock(), FakeMailer()
    app = create_app(Config(), mailer=mailer, now=clock)
    eng = app.extensions["departed"]
    for _ in range(30):
        clock.advance(days=1)
        eng.tick()
    assert mailer.sent == []
    assert eng.db.get_state().state == "waiting"


def test_test_email_goes_to_owner_with_zip(world):
    (world.archive / "a.gpg").write_bytes(b"a")
    (world.archive / "b.gpg").write_bytes(b"b")
    (world.archive / ".hidden").write_bytes(b"x")
    result = world.engine.send_test()
    m = world.mailer.last()
    assert m["to"] == "me@example.com"
    assert m["attachment"][0].startswith("departed-archive-") and m["attachment"][0].endswith(".zip")
    assert result.startswith("Sent")
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(m["attachment"][1])).namelist()
    assert sorted(names) == ["a.gpg", "b.gpg"]
