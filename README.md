# Departed

> **Beta.** Departed is new, and nobody has run it for long. Try it, read the code, and tell me what breaks. Do not trust it yet with something that matters. Test the whole path with the **Send a test email** button before you rely on any of it.

A dead man's switch. A small self-hosted service that emails a pre-encrypted archive to one trusted person if you stop responding to check-in emails.

- Every 10 days it emails you a check-in link. Click it and the clock resets.
- Ignore it and it sends the same link once a day for 10 more days.
- Still nothing, and it emails the archive to your recipient as an attachment, about 21 days after your last check-in. Once. Then it stops.

The archive is encrypted by you, outside the app, and dropped into a folder. The app never sees the passphrase, never encrypts, never decrypts. It attaches the file as it is. A stolen server or a read email yields only an encrypted blob.

## Run it

You need Docker. Everything you might change lives in `.env`.

```bash
sudo mkdir -p /opt/departed/data /opt/departed/archive
sudo chown -R 1000:1000 /opt/departed/data
cp .env.example .env
docker compose up -d
```

Put your encrypted archive in `/opt/departed/archive`, then open `http://<your-server>:4160` and press **Send a test email**. You get exactly what the recipient would get, so you can prove the whole path works without firing anything.

The app runs as user 1000 inside the container, which is why the data folder is owned by 1000 on the host. The archive folder is mounted read-only.

### Settings (`.env`)

| Setting | What it does | Default |
|---|---|---|
| `OWNER_EMAIL` | Where check-ins go | required |
| `RECIPIENT_EMAIL` | Who gets the archive | required |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Outbound mail | required |
| `SMTP_SECURITY` | `starttls`, `ssl` or `none` | `starttls` |
| `BASE_URL` | Address the check-in links point at | required |
| `CHECKIN_INTERVAL_DAYS` | Days between successful check-in and the next check-in email | `10` |
| `REMINDER_COUNT` | Reminders after the first check-in email | `10` |
| `REMINDER_INTERVAL_DAYS` | Days between reminders, and between the last reminder and firing | `1` |
| `DEPARTED_PORT` | Port you open in the browser | `4160` |
| `DEPARTED_DATA` | Host folder for database and log | `/opt/departed` |
| `ARCHIVE_DIR` | Host folder holding the encrypted archive | `/opt/departed/archive` |
| `TZ` | Timezone for dates in emails and on the dashboard | `Europe/London` |

Days can be fractions for testing: `0.01` is about 15 minutes.

### The archive folder

One file is attached as-is. Several files are zipped, uncompressed, keeping folder structure. Hidden files (names starting with a dot) are ignored. Many mail servers refuse attachments over about 25 MB; the dashboard warns at 20 MB. Send a test to be sure.

If the folder is empty when the switch is due to fire, it does not fire. It emails you an alert once a day instead, and fires as soon as files appear.

### What the dashboard shows

Current state (waiting, reminding, fired), last check-in, next check-in email, how many reminders have gone, roughly when it would fire, what is in the archive folder and when it last changed, a **Check in now** button, a **Send a test email** button, and a log of every check-in, reminder, alert, error and firing.

### Things it is careful about

- **The link is single-use.** A fresh token is issued for each check-in cycle and cleared when used. An old email cannot reset the timer. The token is stored hashed.
- **Firing that fails is retried** every five minutes, for ever, logged as an error each time. It is never marked sent until the mail server accepts it.
- **State survives restarts.** Everything is in `data/departed.db` on the mounted volume.
- **A long outage does not cause an instant firing.** Timing runs from when emails were actually sent, so the check-in and all the reminders go out first.
- **If it fires by mistake** you get an email. Change the passphrase, then press **Check in now** to arm it again.
- Logs go to the container output and to `data/departed.log`.

### Updating

```bash
docker compose pull
docker compose down
docker compose up -d
```

If you build locally instead, use `docker compose up -d --build`.

## Access

There is no login. Put it behind Tailscale (or another private network) and keep it off the internet. Over Tailscale Serve: `tailscale serve --bg --https=4160 http://127.0.0.1:4160`, and set `BASE_URL` to that `https://...ts.net:4160` address so the links in the emails work from your phone.

## Licence

GPL-3.0. See `LICENSE`.
