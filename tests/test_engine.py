def run_days(w, days):
    """Tick once an hour for the given number of days."""
    for _ in range(days * 24):
        w.clock.advance(hours=1)
        w.tick()


def test_nothing_happens_before_the_interval(world):
    run_days(world, 9)
    assert world.mailer.sent == []
    assert world.db.get_state(world.user_id).state == "waiting"


def test_checkin_then_reminders_then_fire(world, files):
    (files / "secret.gpg").write_bytes(b"blob")
    run_days(world, 10)
    assert [m["subject"] for m in world.mailer.sent] == ["Departed: please check in"]
    assert world.db.get_state(world.user_id).state == "reminding"

    run_days(world, 3)
    assert [m["subject"] for m in world.mailer.sent if "reminder" in m["subject"]] == [
        "Departed: reminder 1 of 3 - please check in",
        "Departed: reminder 2 of 3 - please check in",
        "Departed: reminder 3 of 3 - please check in",
    ]
    assert world.db.get_state(world.user_id).state == "reminding"

    run_days(world, 1)
    assert world.db.get_state(world.user_id).state == "fired"
    fire = [m for m in world.mailer.sent if m["to"] == "them@example.com"]
    assert len(fire) == 1
    assert fire[0]["attachment"] == ("secret.gpg", b"blob")
    assert "passphrase" in fire[0]["body"]

    before = len(world.mailer.sent)
    run_days(world, 30)
    assert len(world.mailer.sent) == before
    kinds = [e["kind"] for e in world.db.recent_events(world.user_id)]
    assert kinds.count("fired") == 1


def test_the_letter_goes_with_the_files(world, files):
    (files / "a.gpg").write_bytes(b"a")
    world.switches.store(world.user_id).set("letter", "Dear Sam, the box under the stairs.")
    run_days(world, 15)
    fire = [m for m in world.mailer.sent if m["to"] == "them@example.com"][0]
    assert fire["body"].startswith("Dear Sam, the box under the stairs.")


def test_link_resets_the_clock_and_is_single_use(world):
    run_days(world, 10)
    token = world.mailer.link()
    assert token and len(token) >= 32
    assert world.engine.checkin_with_token(token) is True
    s = world.db.get_state(world.user_id)
    assert s.state == "waiting" and s.token_hash is None
    assert world.mailer.last()["subject"] == "Departed: check-in received"
    assert world.engine.checkin_with_token(token) is False
    run_days(world, 9)
    assert world.db.get_state(world.user_id).state == "waiting"
    run_days(world, 1)
    assert world.db.get_state(world.user_id).state == "reminding"


def test_reminders_carry_the_same_link(world):
    run_days(world, 11)
    assert world.mailer.link() in world.mailer.sent[0]["body"]
    assert world.mailer.link() in world.mailer.sent[1]["body"]


def test_nothing_to_send_alerts_instead_of_firing(world):
    run_days(world, 15)
    s = world.db.get_state(world.user_id)
    assert s.state == "reminding" and s.fire_pending
    assert not any(m["to"] == "them@example.com" for m in world.mailer.sent)
    assert len([m for m in world.mailer.sent if "ALERT" in m["subject"]]) == 2

    world.archive.mkdir(parents=True, exist_ok=True)
    (world.archive / "a.gpg").write_bytes(b"a")
    world.clock.advance(minutes=6)
    world.tick()
    assert world.db.get_state(world.user_id).state == "fired"


def test_smtp_failure_on_firing_keeps_retrying(world, files):
    (files / "a.gpg").write_bytes(b"a")
    run_days(world, 13)
    world.mailer.fail = True
    run_days(world, 2)
    s = world.db.get_state(world.user_id)
    assert s.state != "fired" and s.fire_pending and s.fire_attempts > 5
    assert "smtp down" in s.last_fire_error
    world.mailer.fail = False
    world.clock.advance(minutes=6)
    world.tick()
    assert world.db.get_state(world.user_id).state == "fired"


def test_a_long_outage_still_runs_the_reminders(world, files):
    (files / "a.gpg").write_bytes(b"a")
    world.clock.advance(days=60)
    world.tick()
    assert world.db.get_state(world.user_id).state == "reminding"
    assert not any(m["to"] == "them@example.com" for m in world.mailer.sent)
    run_days(world, 3)
    assert world.db.get_state(world.user_id).state == "reminding"
    run_days(world, 1)
    assert world.db.get_state(world.user_id).state == "fired"


def test_state_survives_a_restart(world):
    from app import create_app
    from app.config import Boot
    run_days(world, 11)
    again = create_app(Boot(), mailer_factory=world.mailer, now=world.clock)
    s = again.extensions["departed"].db.get_state(world.user_id)
    assert s.state == "reminding" and s.reminders_sent == 1


def test_an_unfinished_setup_sends_nothing(world):
    world.switches.store(world.user_id).set("smtp_host", "")
    run_days(world, 40)
    assert world.mailer.sent == []
    assert world.db.get_state(world.user_id).state == "waiting"


def test_test_email_goes_to_the_owner_with_a_zip(world, files):
    (files / "a.gpg").write_bytes(b"a")
    (files / "b.gpg").write_bytes(b"b")
    (files / ".hidden").write_bytes(b"x")
    result = world.engine.send_test()
    m = world.mailer.last()
    assert m["to"] == "me@example.com"
    assert m["attachment"][0].startswith("departed-archive-") and m["attachment"][0].endswith(".zip")
    assert result.startswith("Sent")
    import io, zipfile
    assert sorted(zipfile.ZipFile(io.BytesIO(m["attachment"][1])).namelist()) == ["a.gpg", "b.gpg"]


def test_the_timing_is_whatever_you_set_it_to(world, files):
    """Not 10 and 10 and 1. Whatever the settings page says."""
    (files / "a.gpg").write_bytes(b"a")
    world.switches.store(world.user_id).set_many({
        "checkin_interval_days": "5",
        "reminder_count": "2",
        "reminder_interval_days": "3",
    })
    cfg = world.switches.store(world.user_id).current()
    assert cfg.days_to_fire == 5 + 3 * 3

    run_days(world, 4)
    assert world.mailer.sent == []
    run_days(world, 1)
    assert [m["subject"] for m in world.mailer.sent] == ["Departed: please check in"]

    run_days(world, 3)
    assert "reminder 1 of 2" in world.mailer.last()["subject"]
    run_days(world, 3)
    assert "reminder 2 of 2" in world.mailer.last()["subject"]
    run_days(world, 2)
    assert world.db.get_state(world.user_id).state == "reminding"

    run_days(world, 1)
    assert world.db.get_state(world.user_id).state == "fired"
    fired = [e for e in world.db.recent_events(world.user_id) if e["kind"] == "fired"]
    assert len(fired) == 1


def test_the_timing_can_be_minutes_for_testing(world, files):
    (files / "a.gpg").write_bytes(b"a")
    world.switches.store(world.user_id).set_many({
        "checkin_interval_days": "0.01",
        "reminder_count": "1",
        "reminder_interval_days": "0.01",
    })
    for _ in range(200):
        world.clock.advance(minutes=1)
        world.tick()
    assert world.db.get_state(world.user_id).state == "fired"
    subjects = [m["subject"] for m in world.mailer.sent]
    assert "Departed: please check in" in subjects
    assert "Departed: reminder 1 of 1 - please check in" in subjects
