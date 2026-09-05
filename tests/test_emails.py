"""Every message goes out as plain words and as a small piece of HTML, and the
HTML must not reach out to anything."""
import re

from app import emails


def collect(world):
    """Every kind of message this app can send, in one place."""
    from app.store import Settings
    cfg = world.switches.store(world.user_id).current()
    cfg_letter = Settings({**cfg.raw, "letter": "Dear Sam,\n\nThe blue box is in the loft."},
                          cfg.archive_dir)
    return {
        "check-in": emails.check_in(cfg, "https://departed.test/checkin/abc123", 0, "Friday"),
        "reminder": emails.check_in(cfg, "https://departed.test/checkin/abc123", 3, "Friday"),
        "received": emails.check_in_received(cfg, "Friday", "next Friday"),
        "nothing to send": emails.nothing_to_send(cfg),
        "it fired": emails.it_fired(cfg, "Friday"),
        "to the recipient": emails.to_the_recipient(cfg_letter, "Open-me.html", True),
        "the test": emails.to_the_recipient(cfg_letter, "Open-me.html", True, is_test=True),
        "mail test": emails.mail_test(cfg, "me@example.com"),
    }


def test_every_email_has_both_a_plain_and_a_pretty_version(world):
    for name, (text, html) in collect(world).items():
        assert text.strip(), f"{name} has no plain text"
        assert html.startswith("<!doctype html>"), f"{name} is not a page"
        assert "Departed" in html, f"{name} is not branded"
        assert len(text) > 60, f"{name} is too thin"


def test_no_email_loads_anything_from_anywhere(world):
    """No images, no fonts, no trackers. Only links a person can choose to click."""
    for name, (_, html) in collect(world).items():
        assert "<img" not in html, f"{name} has an image"
        assert "background-image" not in html, f"{name} has a background image"
        assert "<script" not in html, f"{name} has a script"
        for url in re.findall(r'(?:src|@import|url\()\s*["\']?(https?://[^"\'\s)]+)', html):
            raise AssertionError(f"{name} loads {url}")


def test_the_check_in_email_carries_the_link_both_ways(world):
    text, html = emails.check_in(world.switches.store(world.user_id).current(),
                                 "https://departed.test/checkin/abc123", 0, "Friday")
    assert "https://departed.test/checkin/abc123" in text
    assert 'href="https://departed.test/checkin/abc123"' in html
    assert html.count("https://departed.test/checkin/abc123") >= 2  # button and plain copy


def test_the_recipients_email_never_carries_the_passphrase(world):
    from app.store import Settings
    cfg = world.switches.store(world.user_id).current()
    cfg = Settings({**cfg.raw, "letter": "Sam, it is the word I said in the kitchen."},
                   cfg.archive_dir)
    text, html = emails.to_the_recipient(cfg, "Open-me.html", True)
    for part in (text, html):
        assert "double-click" in part
        assert "not in this email" in part
    assert "Sam, it is the word I said in the kitchen." in text
    assert "the word I said in the kitchen" in html


def test_the_letter_keeps_its_shape_in_the_html(world):
    from app.store import Settings
    cfg = world.switches.store(world.user_id).current()
    cfg = Settings({**cfg.raw, "letter": "One.\n\nTwo.\n<b>not bold</b>"}, cfg.archive_dir)
    _, html = emails.to_the_recipient(cfg, "Open-me.html", True)
    assert "One.<br>" in html
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html


def test_what_actually_goes_out_has_both_parts(world, files):
    (files / "a.gpg").write_bytes(b"a")
    world.engine.send_test()
    m = world.mailer.last()
    assert m["html"] and m["html"].startswith("<!doctype html>")
    assert m["body"] and "<" not in m["body"].split("\n")[0]
