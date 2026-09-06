# Changelog

All notable changes to Departed are recorded here.

## [0.6.1] — 2026-09-06

- The top bar stays put as you scroll, rather than disappearing off the top of a long settings page.
- The Lightmorphic app launcher sits at the right-hand end of it. It is the one thing in the app loaded from another address, `apps.lightmorphic.com`.

## [0.6.0] — 2026-09-06

- **Up to three people can receive your files.** One address was one point of failure: if the only person who has it is in the same car as you, or dies first and their family cannot get into their email, nothing arrives. Now you can name a second and a third.
- Each of them gets their own copy, sent separately, so none of them sees that the others were written to. Each needs the passphrase, so give it to each of them yourself.
- If one address fails, the others still go, and the ones that worked are never sent to twice. It keeps retrying only the ones that did not, and only calls itself done when every one of them has been delivered.

## [0.5.0] — 2026-09-05

- **Every email is designed now.** They go out as plain words and as a small, quiet page alongside, with the check-in as a proper button and the address underneath for anyone whose mail reader will not show it. No images, no fonts, nothing loaded from anywhere, and a test that fails if one ever gains an outside address.
- The one that reaches your person was written with more care than the rest. Your letter sits at the top in its own block, then a short plain explanation of what happened, then how to open the file.
- **A mail test on the settings page.** One button sends a short message to you and nothing else, so you can prove the mail server works before trusting anything to it. When it fails it says so in English: nothing answered at that server and port, or the server did not accept that username and password, rather than an error number.
- **The settings save themselves.** No save button. Each box saves when you finish with it and a small tick appears beside its label for a moment.

## [0.4.8] — 2026-09-05

- The web address setting explains itself and fills itself in. It now says why it exists at all: the app only ever sees requests arriving on its own machine, so the address you reach it on is the one thing it cannot work out. The box arrives filled with the address your browser is using, there is a button to put it back, and it shows what a check-in link built from it will look like.
- If the address would only work at home, it says so, because a link built from it will not open on a phone.

## [0.4.7] — 2026-09-05

**Fixes a crash on first run.** If the folder you mounted belonged to root, which is what happens when a Docker manager makes it for you, the app could not write to it and stopped at once with a database error and nothing useful to say. The web address in front of it then returned a 502, because there was nothing behind it.

- It now takes ownership of the mounted folder as it starts, then drops to its own ordinary user before anything else happens. Root is held for a fraction of a second and never used to serve anything.
- If it still cannot write there, it says so in plain words and gives the one command to fix it, rather than printing a stack trace.
- The setup instructions lost a step as a result.

## [0.4.6] — 2026-09-05

- No particular schedule is stated anywhere on the website or in the README any more. The steps describe what happens rather than when: it asks as often as you told it to, asks again as many times as you asked for, and sends when the asking runs out. One worked example is given as an example, and nothing else assumes a number.

## [0.4.4] — 2026-09-05

- The settings page now adds your timing up and says it back in words: how often it asks, how many times it asks again, and roughly when your files would go. The three numbers were always settings; nothing in the wording said so.

## [0.4.3] — 2026-09-05

- The compose file is nine lines with no commentary. Anyone installing it can read a port mapping and a volume without being told what they are.

## [0.4.2] — 2026-09-05

- The `.env` file is gone. The port and the folder sit in the compose file itself, which is now the whole of the server-side setup: one file, twelve lines, nothing secret in it and nothing to fill in.

## [0.4.1] — 2026-09-05

- **What gets sent is now a single file that opens itself.** The recipient saves it, double-clicks it, and types the passphrase. It opens in whatever browser their computer already has, lists the files, and saves them. Nothing to install, on Windows, a Mac or Linux, and no internet connection needed: the file carries both the sealed archive and the code that opens it, and reaches out to nothing.
- The plain encrypted file is still in there, and the page has a button to save it out for anyone who would rather use one OpenSSL command.
- The firing email now explains the double-click rather than a command line.
- The opening page takes either kind of file, and there is a test that fails if the sent file ever gains an external address.

## [0.4.0] — 2026-09-05

- **The app can lock your files for you, without ever being able to read them.** Choose your files on the settings page and the locking happens in your own browser: they are zipped and encrypted there, and only the sealed result is sent to the server. The passphrase is made in the browser, shown to you once, and never sent, never stored and never written to the log. If you lose it, nobody can get it back, and the page says so before you leave it.
- **You can go back in and change what is inside.** Give the passphrase, and the browser fetches the sealed file, opens it locally, lets you add or remove things, and seals it again. There is also a "check I can still open it" button, which proves your passphrase works without changing anything.
- **The recipient does not need this program.** The sealed file is an ordinary OpenSSL container holding an ordinary zip, so one standard command opens it on any Mac or Linux machine. The email that carries it says exactly what to type.
- **A page for opening one**, at `/open` in the app and on the website. It works entirely in the browser, uploads nothing, and tells the reader the command to use instead if they would rather not trust a web page.
- Uploading a file you encrypted yourself still works, and is still the right choice for anyone who would rather not trust a web page with the job.

### The website

- Narrower. The text column is a normal reading width now rather than stretching across a wide screen.
- A page for opening a sealed archive, and a shorter beta line.

## [0.3.0] — 2026-09-05

Everything moved out of the server and into the app.

- **Accounts.** Several people can share one copy. Each has their own settings, their own files, their own letter, their own timer and their own log, and nobody can see anybody else's. The first visit makes the first account, which is the administrator, and administrators get a People page to add and remove others.
- **A settings page.** Email addresses, mail server, timing, timezone and web address are all set in the browser now. The mail password is stored encrypted and never shown again once saved.
- **Your files are uploaded through the app.** Add them, see them listed with their size and date, remove them. There is no folder to copy things into over SSH any more. They are still encrypted by you first: the app never opens them.
- **A letter.** A few words that go in the body of the email carrying your files. Stored encrypted at rest, but the app can read it, so the page says plainly to keep anything private inside the locked files instead.
- **The compose file has no settings in it at all.** Only a port and a folder. Nothing in `.env` is a secret.
- Sign-in now has a username as well as a password, and the password is stored as a slow salted hash rather than compared against an environment variable.

## [0.2.0] — 2026-09-05

- The dashboard now asks for a password, set as `DASHBOARD_PASSWORD` in `.env`. One password, no usernames. Signing in lasts 30 days on that browser, and changing the password signs everyone out.
- The check-in links emailed to you still work without the password, so you can always check in from a phone with one tap.
- Repeated wrong passwords are slowed down, and every attempt is logged.
- With no password set the switch keeps running and the emailed links keep working, but the dashboard shows a page telling you to set one.

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
