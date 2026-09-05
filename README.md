# Departed

> **Beta.** Departed is new, and nobody has run it for long. Try it, read the code, and tell me what breaks. Do not trust it yet with something that matters. Test the whole path with the **Send a test email** button before you rely on any of it.

A dead man's switch. A small self-hosted service that emails an archive you locked yourself to one trusted person if you stop responding to check-in emails.

- Every 10 days it emails you a check-in link. Click it and the clock resets.
- Ignore it and it sends the same link once a day for 10 more days.
- Still nothing, and it emails your files to the person you chose, about 21 days after your last check-in. Once. Then it stops.

You encrypt the files yourself, outside the app, and add them on the settings page. The app never sees the passphrase, never encrypts and never decrypts. It attaches the files as they are. A stolen server or a read email yields only an encrypted blob.

Several people can share one copy. Each has their own account, their own settings, their own files and their own timer, and nobody can see anybody else's.

## Run it

You need Docker. There are no settings in the compose file: everything is set in the browser afterwards.

```bash
sudo mkdir -p /opt/departed
sudo chown -R 1000:1000 /opt/departed
cp .env.example .env
docker compose up -d
```

Open `http://<your-server>:4160`. The first visit asks you to make an account, and that first account is the administrator. Then fill in the settings page, add your files, and press **Send a test email**. You get exactly what your person would get, so you can prove the whole path works without firing anything.

The app runs as user 1000 inside the container, which is why the folder is owned by 1000 on the host.

### The only two settings on the server

| Setting | What it does | Default |
|---|---|---|
| `DEPARTED_PORT` | Port you open in the browser | `4160` |
| `DEPARTED_DATA` | Host folder holding the database, your files and the log | `/opt/departed` |

`MAX_UPLOAD_MB` (default 64) caps a single upload. `SECRET_KEY` is optional: set it and it is used to encrypt stored secrets instead of the key file the app makes for itself.

### Everything else is on the settings page

Signed in, you set:

- Your email address, and your person's.
- Your mail server, port, encryption, username, password and from-address. The password is stored encrypted and never shown again.
- The timing: days between check-ins, how many reminders, and days between them. Fractions are allowed, so `0.01` is about a quarter of an hour, which is handy for testing.
- The web address you open it at. Your check-in links are built from this, so it has to work from wherever you read your email.
- Your timezone.
- **Your files.** Upload them, see them listed, remove them. One file is attached as it is; several are zipped, uncompressed. Lock them yourself before you add them.
- **Your letter.** A few words that go in the body of the email carrying your files. It is stored encrypted at rest but the app can read it, unlike your files, so keep anything private inside the locked files instead.
- Your own sign-in password.

### Accounts

The first visit makes the first account, and it is the administrator. Administrators get a **People** page to add and remove others, and can hand out administrator rights.

Removing somebody deletes their settings, their timer, their log and their files. There is no undo. The last administrator cannot be removed, and nobody can remove their own account.

Sign-ins last 30 days on a browser. Changing a password ends that person's other sign-ins. Repeated wrong passwords are slowed down and every attempt is logged.

The check-in links emailed to you deliberately do **not** ask for a password. They carry their own long single-use token and have to work with one tap from a phone.

### Things it is careful about

- **The link is single-use.** A fresh token is issued for each check-in cycle and cleared when used. An old email cannot reset the timer. The token is stored hashed.
- **Firing that fails is retried** every five minutes, for ever, logged as an error each time. It is never marked sent until the mail server accepts it.
- **It will not send an empty envelope.** With no files, it does not fire. It emails you an alert once a day instead, and fires as soon as files appear.
- **State survives restarts.** Everything is in `departed.db` on the mounted volume.
- **A long outage does not cause an instant firing.** Timing runs from when emails were actually sent, so the check-in and all the reminders go out first.
- **If it fires by mistake** you get an email. Change the passphrase, then press **Check in now** to arm it again.
- Logs go to the container output and to `departed.log` in the data folder.

### What is stored, and how

Everything lives in the one folder you mounted:

| | |
|---|---|
| `departed.db` | accounts, settings, timers and the log |
| `archives/<id>/` | each person's files, exactly as they were uploaded |
| `secret.key` | encrypts the mail passwords and letters in the database |
| `session.key` | signs the sign-in cookies |
| `departed.log` | the log |

Both key files are made on first run and are readable only by the app's own user. Encrypting the mail password and the letter protects a copy of the database on its own, a backup or a screenshot. It does not protect against somebody who has taken the whole folder, because the key is in it. Your archive is different: that is locked with a passphrase this program never has.

### Updating

```bash
docker compose pull
docker compose up -d
```

## Access

Departed has no business being on the open internet. Keep it on your own network, and reach it from outside through whatever private connection you already use for that. Setting that up is your business, not this app's.

Whatever address it gives you, put it in the web address setting. That is what the links in your check-in emails are built from, so it has to work from wherever you read your email.

The sign-in password is a second lock, not the first one. Do not treat it as a reason to expose the app.

## Licence

GPL-3.0. See `LICENSE`.
