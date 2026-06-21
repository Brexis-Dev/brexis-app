import logging
import database as db

logger = logging.getLogger(__name__)


def _get_config(key):
    return db.get_config(key) or ""


def get_sendgrid_key():
    return _get_config("SENDGRID_API_KEY")


def get_email_to():
    return _get_config("EMAIL_TO")


def get_email_from():
    return _get_config("EMAIL_FROM")


def send_email(subject, body, to_emails=None, from_email=None):
    api_key = get_sendgrid_key()
    if not api_key:
        msg = "SendGrid API key not configured — add it in /settings"
        logger.warning(msg)
        db.log_task("email", "send_failed", f"No API key. Subject: {subject}", "failed")
        return {"ok": False, "error": msg}

    from_email = from_email or get_email_from()
    if not from_email:
        msg = "EMAIL_FROM not configured — add sender address in /settings"
        logger.warning(msg)
        db.log_task("email", "send_failed", msg, "failed")
        return {"ok": False, "error": msg}

    # Resolve recipients — accepts str, list, or falls back to EMAIL_TO config
    if to_emails is None:
        fallback = get_email_to()
        if not fallback:
            msg = "No recipients specified and EMAIL_TO not configured in /settings"
            logger.warning(msg)
            db.log_task("email", "send_failed", msg, "failed")
            return {"ok": False, "error": msg}
        to_emails = [fallback]
    elif isinstance(to_emails, str):
        to_emails = [to_emails]

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, To

        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        mail = Mail(
            from_email=from_email,
            to_emails=[To(addr) for addr in to_emails],
            subject=subject,
            html_content=body.replace("\n", "<br>") if "<" not in body else body,
        )
        response = sg.send(mail)
        status = response.status_code
        success = status in (200, 201, 202)

        if success:
            logger.info(f"Email sent [{status}]: {subject} → {to_emails}")
            db.log_task("email", "send", f"Sent [{status}]: {subject} → {', '.join(to_emails)}", "success")
            return {"ok": True, "status_code": status, "recipients": to_emails}
        else:
            body_preview = getattr(response, "body", b"")[:200]
            msg = f"SendGrid returned {status}: {body_preview}"
            logger.error(f"Email failed: {msg}")
            db.log_task("email", "send_failed", f"{subject}: {msg}", "failed")
            return {"ok": False, "error": msg, "status_code": status}

    except Exception as e:
        logger.error(f"Email send exception: {e}")
        db.log_task("email", "send_error", f"{subject}: {e}", "failed")
        return {"ok": False, "error": str(e)}
