"""The emails.

Every message goes out twice in the same envelope: as plain text, and as a small
piece of HTML for anything that can show it. The HTML is laid out with tables and
inline styles, because that is the only thing every mail client agrees on, and it
carries no images and nothing loaded from anywhere else.

Each builder returns (plain_text, html).
"""
import html as _html

FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "'Helvetica Neue', Arial, sans-serif")
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

BG = "#f4f1ec"
CARD = "#ffffff"
LINE = "#e5e0d8"
INK = "#14161d"
SOFT = "#454b59"
MUTED = "#6d7280"
ACCENT = "#fbc711"
ON_ACCENT = "#42340a"
WARN_BG = "#fff6e0"
WARN_INK = "#7a5c02"


def _esc(text):
    return _html.escape(text, quote=False)


def _paragraph(text, colour=SOFT, size="16px", weight="400"):
    return (f'<p style="margin:0 0 16px;font-family:{FONT};font-size:{size};'
            f'line-height:1.6;color:{colour};font-weight:{weight}">{text}</p>')


def _button(label, url):
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 20px"><tr><td '
        f'style="background:{ACCENT};border-radius:12px">'
        f'<a href="{_esc(url)}" style="display:inline-block;padding:14px 30px;'
        f'font-family:{FONT};font-size:16px;font-weight:700;color:{ON_ACCENT};'
        'text-decoration:none">' + _esc(label) + '</a></td></tr></table>')


def _fallback_link(url):
    return (f'<p style="margin:0 0 20px;font-family:{FONT};font-size:13px;'
            f'line-height:1.6;color:{MUTED}">Or copy this into your browser:<br>'
            f'<span style="font-family:{MONO};font-size:12px;color:{SOFT};'
            f'word-break:break-all">{_esc(url)}</span></p>')


def _quote(text):
    lines = "<br>".join(_esc(line) if line.strip() else "&nbsp;"
                        for line in text.splitlines())
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="margin:0 0 22px"><tr><td '
            f'style="background:{BG};border-radius:12px;padding:20px 22px">'
            f'<div style="font-family:{FONT};font-size:16px;line-height:1.7;'
            f'color:{INK}">{lines}</div></td></tr></table>')


def _note(text, tint=False):
    bg = WARN_BG if tint else BG
    ink = WARN_INK if tint else MUTED
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="margin:0 0 20px"><tr><td '
            f'style="background:{bg};border-radius:12px;padding:16px 18px">'
            f'<div style="font-family:{FONT};font-size:14px;line-height:1.6;'
            f'color:{ink}">{text}</div></td></tr></table>')


def _code(text):
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="margin:0 0 20px"><tr><td '
            f'style="background:{BG};border-radius:12px;padding:16px 18px">'
            f'<div style="font-family:{MONO};font-size:12px;line-height:1.7;'
            f'color:{SOFT};word-break:break-all;white-space:pre-wrap">'
            f'{_esc(text)}</div></td></tr></table>')


def _mark():
    """The clock, drawn with a border rather than an image so nothing loads."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
        '<tr>'
        f'<td style="width:26px;height:26px;background:{ACCENT};border-radius:13px"></td>'
        '<td style="width:10px"></td>'
        f'<td style="font-family:{FONT};font-size:17px;font-weight:700;'
        f'letter-spacing:-0.2px;color:{INK}">Departed</td>'
        '</tr></table>')


def page(heading, body_html, footer_text):
    """Wraps the pieces in the envelope every message shares."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_esc(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
       style="background:{BG};padding:32px 16px">
<tr><td align="center">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
         style="max-width:560px;width:100%">
    <tr><td style="padding:0 4px 20px">{_mark()}</td></tr>
    <tr><td style="background:{CARD};border:1px solid {LINE};border-radius:18px;padding:32px 30px">
      <h1 style="margin:0 0 18px;font-family:{FONT};font-size:23px;line-height:1.25;
                 letter-spacing:-0.4px;font-weight:700;color:{INK}">{_esc(heading)}</h1>
      {body_html}
    </td></tr>
    <tr><td style="padding:20px 4px 0">
      <p style="margin:0;font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED}">
        {footer_text}</p>
    </td></tr>
  </table>
</td></tr></table>
</body></html>
"""


def _sign_off(base_url):
    if base_url:
        return (f'Sent by Departed, running at <span style="font-family:{MONO};'
                f'font-size:11px">{_esc(base_url)}</span>')
    return "Sent by Departed"


# ---- the messages ---------------------------------------------------------

def _and_list(names):
    if len(names) <= 1:
        return names[0] if names else "nobody"
    return ", ".join(names[:-1]) + " and " + names[-1]


def check_in(cfg, url, reminder_no, fire_when):
    """The email that asks whether you are still here."""
    if reminder_no:
        heading = f"Still there? Reminder {reminder_no} of {cfg.reminder_count}"
        opening = ("You have not answered the last one, so here it is again. "
                   "Any single one of these will do.")
    else:
        heading = "Time to check in"
        opening = "One click and the clock goes back to the beginning."

    who = _and_list(cfg.recipients)
    text = (f"{heading}\n\n{opening}\n\nClick this link:\n\n{url}\n\n"
            f"If nobody clicks, your files go to {who} around "
            f"{fire_when}. Clicking stops that.\n")

    body = (_paragraph(_esc(opening))
            + _button("I am still here", url)
            + _fallback_link(url)
            + _note(f"If nobody clicks, your files go to "
                    f"<strong style=\"color:{SOFT}\">{_esc(who)}</strong> "
                    f"around {_esc(fire_when)}. Clicking stops that."))
    return text + _footer_text(cfg), page(heading, body, _sign_off(cfg.base_url))


def check_in_received(cfg, when, next_when):
    heading = "Thank you, that is noted"
    text = (f"{heading}\n\nYour check-in was received on {when}.\n\n"
            f"The next one is due on {next_when}.\n")
    body = (_paragraph(f"Your check-in was received on {_esc(when)}. "
                       "The clock is back at the beginning and there is nothing else to do.")
            + _note(f"The next one is due on <strong style=\"color:{SOFT}\">"
                    f"{_esc(next_when)}</strong>."))
    return text + _footer_text(cfg), page(heading, body, _sign_off(cfg.base_url))


def nothing_to_send(cfg):
    heading = "Nothing was sent, and nothing was lost"
    text = (f"{heading}\n\nThe switch was due to fire, but there are no files to send, "
            "so it sent nothing at all.\n\nAdd your files on the settings page, or check in "
            "to put the clock back.\n")
    body = (_paragraph("The switch was due to fire, but there are no files to send. "
                       "So it sent nothing, and it will keep holding until there is "
                       "something there.")
            + _note("Add your files on the settings page, or check in to put the clock "
                    "back to the beginning.", tint=True))
    return text + _footer_text(cfg), page(heading, body, _sign_off(cfg.base_url))


def it_fired(cfg, when):
    heading = "Your files have been sent"
    who = _and_list(cfg.recipients)
    text = (f"{heading}\n\nThey went to {who} on {when}.\n\n"
            "If this was a mistake, change the passphrase and check in on the dashboard "
            "to arm it again.\n")
    body = (_paragraph(f"They went to <strong style=\"color:{INK}\">"
                       f"{_esc(who)}</strong> on {_esc(when)}. "
                       "Nothing more will be sent.")
            + _note("If this was a mistake, change the passphrase on your files and check "
                    "in on the dashboard. That arms it again from the beginning.", tint=True))
    return text + _footer_text(cfg), page(heading, body, _sign_off(cfg.base_url))


def to_the_recipient(cfg, filename, sealed, is_test=False):
    """The one that matters. Gentle, short, and clear about what to do."""
    heading = "Somebody has left you something"
    letter = (cfg.letter or "").strip()

    lines = []
    if is_test:
        lines.append("This is a test. You are seeing what your person would receive.")
    if letter:
        lines.append(letter)
        lines.append("-" * 40)
    lines.append("This message was sent automatically because the person who set it up "
                 "stopped answering its emails.")
    lines.append(f"The file attached to it, {filename}, is locked. You were given the "
                 "passphrase in person. It is not in this email, and nobody else has it.")
    if sealed and filename.endswith(".html"):
        lines.append("How to open it\n\nSave the attached file somewhere you can find it, "
                     "then double-click it. It opens in your web browser and asks for the "
                     "passphrase. That is all there is to it. It works on Windows, on a Mac "
                     "and on Linux, it needs nothing installed, and it works with no "
                     "internet connection.\n\nThe file does the work on your own computer. "
                     "Nothing is uploaded and nobody is told that you opened it.")
    text = "\n\n".join(lines) + "\n"

    body = ""
    if is_test:
        body += _note("This is a test. You are seeing exactly what your person would "
                      "receive, sent to you instead. Nothing has fired.", tint=True)
    if letter:
        body += _quote(letter)
    body += _paragraph("This message was sent automatically, because the person who set "
                       "it up stopped answering its emails.")
    body += _paragraph(f"The file attached to it, <strong style=\"color:{INK}\">"
                       f"{_esc(filename)}</strong>, is locked. You were given the passphrase "
                       "in person. It is not in this email, and nobody else has it.")
    if sealed and filename.endswith(".html"):
        body += ('<div style="height:1px;background:' + LINE + ';margin:4px 0 24px"></div>'
                 + _paragraph("How to open it", colour=INK, size="17px", weight="700")
                 + _paragraph("Save the attached file somewhere you can find it, then "
                              "double-click it. It opens in your web browser and asks for "
                              "the passphrase. That is all there is to it.")
                 + _note("It works on Windows, on a Mac and on Linux. Nothing to install, "
                         "and no internet connection needed. The file does the work on your "
                         "own computer, nothing is uploaded, and nobody is told that you "
                         "opened it."))
    return text, page(heading, body, "Sent by Departed")


def mail_test(cfg, to):
    heading = "Your mail settings work"
    text = (f"{heading}\n\nThis went out through {cfg.smtp_host} and arrived at {to}, "
            "so the part that matters most is working.\n")
    body = (_paragraph("If you are reading this, the part that matters most is working.")
            + _note(f"Sent through <strong style=\"color:{SOFT}\">{_esc(cfg.smtp_host)}</strong> "
                    f"to <strong style=\"color:{SOFT}\">{_esc(to)}</strong>.")
            + _paragraph("Nothing else has changed and nothing has been sent to anybody else."))
    return text + _footer_text(cfg), page(heading, body, _sign_off(cfg.base_url))


def _footer_text(cfg):
    return f"\n\nDeparted, running at {cfg.base_url}\n" if cfg.base_url else "\n\nDeparted\n"
