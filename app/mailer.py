"""Outbound mail over SMTP using only the standard library."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("departed.mail")


class Mailer:
    def __init__(self, cfg):
        self.cfg = cfg

    def send(self, to, subject, body, attachment=None):
        """Send one plain-text email. attachment is (filename, bytes) or None.
        Raises on failure so the caller decides what to do."""
        cfg = self.cfg
        msg = EmailMessage()
        msg["From"] = cfg.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if attachment:
            name, data = attachment
            msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=name)

        context = ssl.create_default_context()
        if cfg.smtp_security == "ssl":
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=90, context=context)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=90)
        with server:
            server.ehlo()
            if cfg.smtp_security == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if cfg.smtp_username:
                server.login(cfg.smtp_username, cfg.smtp_password)
            server.send_message(msg)
        log.info("Sent '%s' to %s%s", subject, to, f" with {attachment[0]}" if attachment else "")
