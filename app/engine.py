"""The switch itself: decides what to send and when, and remembers it in the database.

Timing is driven by when things were actually sent, not by fixed deadlines, so a
server that has been off for a while picks up where it left off and still runs the
whole reminder sequence before it fires.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timezone

from . import archive

log = logging.getLogger("departed")


def utcnow():
    return datetime.now(timezone.utc)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Engine:
    """One person's switch."""

    def __init__(self, user_id, settings, db, mailer, now=utcnow, token_cache=None):
        self.user_id = user_id
        self.settings = settings
        self.db = db
        self.mailer = mailer
        self.now = now
        self._warned_at = None
        # Shared across requests so a reminder can carry the same link as the
        # check-in email that came before it.
        self._tokens = token_cache if token_cache is not None else {}

    @property
    def _token_cache(self):
        return self._tokens.get(self.user_id)

    @_token_cache.setter
    def _token_cache(self, value):
        self._tokens[self.user_id] = value

    @property
    def cfg(self):
        return self.settings()

    # ---- helpers -------------------------------------------------------

    def local(self, dt):
        return dt.astimezone(self.cfg.tz).strftime("%A %-d %B %Y at %H:%M") if dt else "never"

    def _sign_off(self, cfg):
        return f"\n\nDeparted, running at {cfg.base_url}" if cfg.base_url else "\n\nDeparted"

    def _checkin_body(self, cfg, token, reminder_no):
        if reminder_no:
            opening = (f"This is reminder {reminder_no} of {cfg.reminder_count}. "
                       "You have not clicked the check-in link yet.")
        else:
            opening = "Time to check in."
        left = cfg.reminder_count - reminder_no + 1
        fire_at = self.now() + left * cfg.reminder_interval
        return (f"{opening}\n\nClick this link to reset the timer:\n\n{cfg.checkin_url(token)}\n\n"
                f"If nobody clicks, the archive will be emailed to your recipient around "
                f"{self.local(fire_at)}. Clicking the link stops that." + self._sign_off(cfg))

    # ---- public state for the UI ---------------------------------------

    def next_email_at(self, s):
        cfg = self.cfg
        if s.state == "waiting":
            return s.last_checkin_at + cfg.checkin_interval
        if s.state == "reminding" and s.last_sent_at:
            return s.last_sent_at + cfg.reminder_interval
        return None

    def expected_fire_at(self, s):
        cfg = self.cfg
        if s.state == "fired":
            return s.fired_at
        if s.state == "waiting":
            start = s.last_checkin_at + cfg.checkin_interval
            return start + (cfg.reminder_count + 1) * cfg.reminder_interval
        base = s.last_sent_at or self.now()
        remaining = max(0, cfg.reminder_count - s.reminders_sent)
        return base + (remaining + 1) * cfg.reminder_interval

    # ---- check-ins -----------------------------------------------------

    def checkin_with_token(self, token):
        s = self.db.get_state(self.user_id)
        if not s.token_hash or not secrets.compare_digest(s.token_hash, _hash(token)):
            self.db.log_event(self.user_id, "rejected", "A check-in link was used that is no longer valid.")
            log.warning("Rejected check-in for user %s with an invalid or used token", self.user_id)
            return False
        self._checkin(s, "the emailed link")
        return True

    def checkin_now(self):
        self._checkin(self.db.get_state(self.user_id), "the dashboard button")

    def _checkin(self, s, via):
        cfg = self.cfg
        now = self.now()
        was = s.state
        s.state = "waiting"
        s.last_checkin_at = now
        s.cycle_started_at = None
        s.last_sent_at = None
        s.reminders_sent = 0
        s.token_hash = None
        s.fire_pending = False
        s.fire_attempts = 0
        s.last_fire_error = None
        s.last_alert_at = None
        self.db.save_state(s)
        self._token_cache = None
        note = "Check-in received via " + via + "."
        if was == "fired":
            note += " The switch had already fired; it is now armed again."
        self.db.log_event(self.user_id, "checkin", note, now)
        log.info(note)
        if cfg.ready:
            self._send_quietly(cfg.owner_email, "Departed: check-in received",
                               f"Your check-in was received on {self.local(now)}.\n\n"
                               f"The next check-in email is due on {self.local(now + cfg.checkin_interval)}."
                               + self._sign_off(cfg))

    def _send_quietly(self, to, subject, body, attachment=None):
        try:
            self.mailer.send(to, subject, body, attachment)
            return True
        except Exception as e:  # noqa: BLE001 - any mail failure is logged, never fatal
            log.error("Could not send '%s' to %s: %s", subject, to, e)
            self.db.log_event(self.user_id, "error", f"Could not send '{subject}': {e}")
            return False

    # ---- the tick ------------------------------------------------------

    def tick(self):
        cfg = self.cfg
        now = self.now()
        if cfg.problems:
            if not self._warned_at or (now - self._warned_at).total_seconds() > 600:
                self._warned_at = now
                for p in cfg.problems:
                    log.error("Not set up yet: %s", p)
            return
        s = self.db.get_state(self.user_id)

        if s.fire_pending:
            if not s.last_fire_attempt_at or now - s.last_fire_attempt_at >= cfg.fire_retry_interval:
                self._fire(cfg, s, now)
            return
        if s.state == "fired":
            return

        if s.state == "waiting":
            if now >= s.last_checkin_at + cfg.checkin_interval:
                self._start_cycle(cfg, s, now)
            return

        if s.state == "reminding":
            if now < s.last_sent_at + cfg.reminder_interval:
                return
            if s.reminders_sent < cfg.reminder_count:
                self._send_reminder(cfg, s, now)
            else:
                self._fire(cfg, s, now)

    def _start_cycle(self, cfg, s, now):
        token = secrets.token_urlsafe(32)
        s.token_hash = _hash(token)
        self.db.save_state(s)  # persist the hash before the email goes out
        body = self._checkin_body(cfg, token, 0)
        if not self._send_quietly(cfg.owner_email, "Departed: please check in", body):
            s.token_hash = None
            self.db.save_state(s)
            return
        s.state = "reminding"
        s.cycle_started_at = now
        s.last_sent_at = now
        s.reminders_sent = 0
        self.db.save_state(s)
        self.db.log_event(self.user_id, "checkin-sent", f"Check-in email sent to {cfg.owner_email}.", now)
        self._token_cache = token

    def _send_reminder(self, cfg, s, now):
        # The reminder carries the same link, so the token is kept in memory for the
        # cycle. After a restart it is gone, so a fresh token is issued and the old
        # link stops working, which is the safe direction to fail.
        token = self._token_cache
        if not token or _hash(token) != s.token_hash:
            token = secrets.token_urlsafe(32)
            s.token_hash = _hash(token)
            self.db.save_state(s)
            self._token_cache = token
        n = s.reminders_sent + 1
        subject = f"Departed: reminder {n} of {cfg.reminder_count} - please check in"
        if not self._send_quietly(cfg.owner_email, subject, self._checkin_body(cfg, token, n)):
            return
        s.reminders_sent = n
        s.last_sent_at = now
        self.db.save_state(s)
        self.db.log_event(self.user_id, "reminder", f"Reminder {n} of {cfg.reminder_count} sent to {cfg.owner_email}.", now)

    def _firing_body(self, cfg, name):
        letter = (cfg.letter or "").strip()
        parts = []
        if letter:
            parts.append(letter)
            parts.append("-" * 40)
        parts.append("This message was sent automatically because the owner stopped responding "
                     "to check-ins.\n\nThe attached file is encrypted. You were given the "
                     "passphrase in person.\n\nAttached: " + name)
        return "\n\n".join(parts) + self._sign_off(cfg)

    def _fire(self, cfg, s, now):
        if not s.fire_pending:
            s.fire_pending = True
            self.db.save_state(s)
            self.db.log_event(self.user_id, "fire-due", "No check-in received. The archive is due to be sent.", now)
            log.warning("FIRING: no check-in received, sending the archive to %s", cfg.recipient_email)

        attachment = archive.build_attachment(cfg.archive_dir, now.astimezone(cfg.tz))
        if attachment is None:
            log.error("The archive folder is empty - NOT firing. Alerting %s instead.", cfg.owner_email)
            if not s.last_alert_at or now - s.last_alert_at >= cfg.reminder_interval:
                sent = self._send_quietly(cfg.owner_email, "Departed: ALERT - no files to send",
                                          "The switch was due to fire but there are no files to send, "
                                          "so nothing was sent. Add your encrypted archive on the "
                                          "settings page, or check in." + self._sign_off(cfg))
                if sent:
                    s.last_alert_at = now
                    self.db.log_event(self.user_id, "alert", "No files to send when due to fire. Alert emailed instead.", now)
            s.last_fire_attempt_at = now
            s.last_fire_error = "There are no files to send."
            self.db.save_state(s)
            return

        name, data = attachment
        s.fire_attempts += 1
        s.last_fire_attempt_at = now
        try:
            self.mailer.send(cfg.recipient_email, "Departed: the archive",
                             self._firing_body(cfg, name), (name, data))
        except Exception as e:  # noqa: BLE001
            s.last_fire_error = str(e)
            self.db.save_state(s)
            log.error("FIRING FAILED (attempt %d): %s - will retry in %s",
                      s.fire_attempts, e, cfg.fire_retry_interval)
            self.db.log_event(self.user_id, "error", f"Sending the archive failed (attempt {s.fire_attempts}): {e}. Will keep retrying.", now)
            return

        s.state = "fired"
        s.fired_at = now
        s.fire_pending = False
        s.last_fire_error = None
        s.token_hash = None
        self.db.save_state(s)
        self.db.log_event(self.user_id, "fired", f"Archive '{name}' ({len(data)} bytes) emailed to {cfg.recipient_email}.", now)
        log.warning("FIRED: archive '%s' sent to %s after %d attempt(s)", name, cfg.recipient_email, s.fire_attempts)
        self._send_quietly(cfg.owner_email, "Departed: the switch has fired",
                           f"The archive was emailed to {cfg.recipient_email} on {self.local(now)}.\n\n"
                           "If this was a mistake, change the passphrase and check in on the dashboard "
                           "to arm the switch again." + self._sign_off(cfg))

    # ---- test email ----------------------------------------------------

    def send_test(self):
        """Mail the archive to the owner, exactly as the recipient would get it."""
        cfg = self.cfg
        now = self.now()
        s = self.db.get_state(self.user_id)
        s.last_test_at = now
        if cfg.problems:
            s.last_test_result = "Not sent: " + cfg.problems[0]
        else:
            attachment = archive.build_attachment(cfg.archive_dir, now.astimezone(cfg.tz))
            if attachment:
                body = ("This is a test from Departed. It is what your recipient would receive, "
                        "sent to you instead.\n\n" + self._firing_body(cfg, attachment[0]))
            else:
                body = ("This is a test from Departed. There are no files to send yet, so nothing "
                        "is attached." + self._sign_off(cfg))
            try:
                self.mailer.send(cfg.owner_email, "Departed: test email", body, attachment)
                s.last_test_result = (f"Sent to {cfg.owner_email} with {attachment[0]}" if attachment
                                      else f"Sent to {cfg.owner_email}, but there are no files to send")
            except Exception as e:  # noqa: BLE001
                s.last_test_result = f"Failed: {e}"
                log.error("Test email failed: %s", e)
        self.db.save_state(s)
        self.db.log_event(self.user_id, "test", "Test email: " + s.last_test_result, now)
        return s.last_test_result
