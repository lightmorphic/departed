"""Outbound mail over SMTP using only the standard library."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

log = logging.getLogger("departed.mail")


def in_plain_words(error):
    """Mail servers fail in jargon. This says the same thing in English."""
    name = type(error).__name__
    text = str(error)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "The mail server did not accept that username and password."
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "The mail server would not send from that address."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "The mail server would not deliver to that address."
    if isinstance(error, ConnectionRefusedError) or "Connection refused" in text:
        return "Nothing answered at that server and port. Check both."
    if name == "gaierror" or "Name or service not known" in text or "nodename nor servname" in text:
        return "That mail server name could not be found."
    if isinstance(error, TimeoutError) or "timed out" in text:
        return "The mail server did not answer in time."
    if isinstance(error, ssl.SSLError) or "SSL" in text or "WRONG_VERSION" in text:
        return ("The encryption setting does not match the server. Try a different one of the "
                "three, and check the port.")
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return "The mail server does not support that encryption. Try a different one."
    return text or name


class Mailer:
    def __init__(self, settings):
        """settings is a callable returning the current settings."""
        self._settings = settings

    def send(self, to, subject, body, attachment=None, html=None):
        """Send one email, as plain text and, where given, as HTML alongside it.
        attachment is (filename, bytes) or None. Raises on failure so the caller
        decides what to do."""
        cfg = self._settings()
        msg = EmailMessage()
        msg["From"] = cfg.from_address
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
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
