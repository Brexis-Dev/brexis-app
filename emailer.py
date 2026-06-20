import os
import logging
import database as db

logger = logging.getLogger(__name__)


def get_sendgrid_key():
    return os.environ.get("SENDGRID_API_KEY") or db.get_config("SENDGRID_API_KEY")


def get_email_to():
    return os.environ.get("EMAIL_TO") or db.get_config("EMAIL_TO") or ""


def get_email_from():
    return os.environ.get("EMAIL_FROM") or db.get_config("EMAIL_FROM") or ""


def send_email(subject, body, to_email=None, from_email=None):
    api_key = get_sendgrid_key()
    if not api_key:
        logger.warning("SendGrid API key not configured — email not sent.")
        db.log_task("email", "send_failed", f"No API key. Subject: {subject}", "failed")
        return False

    to_email = to_email or get_email_to()
    from_email = from_email or get_email_from()

    if not to_email or not from_email:
        logger.warning("Email addresses not configured.")
        db.log_task("email", "send_failed", f"No addresses configured. Subject: {subject}", "failed")
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        mail = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=body.replace("\n", "<br>"),
        )
        response = sg.send(mail)
        success = response.status_code in (200, 201, 202)
        db.log_task("email", "send", f"{'Sent' if success else 'Failed'}: {subject}", "success" if success else "failed")
        return success
    except Exception as e:
        logger.error(f"Email send error: {e}")
        db.log_task("email", "send_error", f"{subject}: {e}", "failed")
        return False
