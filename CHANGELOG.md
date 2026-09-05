# Changelog

All notable changes to Departed are recorded here.

## Unreleased

- Website at departed.lightmorphic.com, served from `docs/` on GitHub Pages. Plain HTML and CSS, self-hosted Manrope, nothing loaded from anywhere else, no cookies and no analytics.
- `pytest.ini` so the test suite finds the app package when run from a clean checkout.

## [0.1.0] — 2026-09-04

First working version.

- Check-in email every 10 days with a single-use link; clicking it resets the clock and sends a confirmation.
- Ten daily reminders carrying the same link, then the archive is emailed to the recipient once, about 21 days after the last check-in.
- Archive folder mounted read-only. One file is attached as-is, several are zipped uncompressed. The app never encrypts or decrypts anything.
- Empty archive folder: does not fire, emails an alert instead, and fires once files appear.
- Firing email that fails is retried every five minutes for ever, logged loudly, never marked sent.
- Timing runs from when emails were actually sent, so after an outage the full reminder sequence still runs before firing.
- Dashboard: state, last and next check-in, expected firing date, archive folder contents, "Check in now", "Send a test email", event log.
- State and log persisted to SQLite on a mounted volume. Everything configured from `.env`.
