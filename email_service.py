import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def send_email(to_email, subject, body):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")

    # Configurable so you can point this at Gmail for testing and the
    # real nomadbrewingco.com.au mail server later, without code changes.
    # For Gmail: EMAIL_HOST=smtp.gmail.com, EMAIL_PORT=465 (SSL) and
    # EMAIL_PASSWORD must be a 16-character Gmail "App Password", not
    # your normal Gmail password.
    smtp_host = os.getenv("EMAIL_HOST", "mail.nomadbrewingco.com.au")
    smtp_port = int(os.getenv("EMAIL_PORT", "465"))

    if not sender or not password:
        print("Email skipped: Missing EMAIL_USER or EMAIL_PASSWORD.")
        return

    if not to_email:
        print("Email skipped: No recipient provided.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
            print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Email failed ({smtp_host}:{smtp_port}): {e}")


def send_staff_review_email(booking, rule_status, review_link):
    staff_email = os.getenv("STAFF_EMAIL")

    body = f"""
New booking needs review.

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Start time: {booking.start_time}
Details: {booking.details}

Rule check:
{rule_status}

Review booking here:
{review_link}
"""

    send_email(staff_email, f"Booking needs review: {booking.name}", body)


def send_staff_alert_email(subject, body):
    staff_email = os.getenv("STAFF_EMAIL")
    send_email(staff_email, subject, body)


def send_customer_pending_review_email(to_email, name, start_time):
    body = f"""
Hi {name},

Thanks for your booking request.

Your booking has been received and is currently pending manager approval because it needs manual review.

Requested booking time:
{start_time}

We will email you once your booking has been approved or declined.

Thanks,
Nomad Brewing Co
"""

    send_email(to_email, "Booking request received - pending approval", body)


def send_customer_approved_email(to_email, name, start_time, high_demand_note=None):
    extra_note = ""

    if high_demand_note:
        extra_note = f"""

Important note:
{high_demand_note}

Because this is a high-demand day, your table will not be held if you are late.
"""

    body = f"""
Hi {name},

Your booking has been confirmed.

Booking time:
{start_time}
{extra_note}

Thanks,
Nomad Brewing Co
"""

    send_email(to_email, "Booking confirmed", body)


def send_customer_rejected_email(to_email, name, start_time):
    body = f"""
Hi {name},

Thanks for your booking request.

Unfortunately, we are unable to accept your booking at:
{start_time}

Please contact us directly if you would like to discuss another time.

Thanks,
Nomad Brewing Co
"""

    send_email(to_email, "Booking request update", body)


def send_customer_reminder_email(to_email, name, start_time, confirm_link, cancel_link, adjust_link, high_demand_note=None):
    extra_note = ""

    if high_demand_note:
        extra_note = f"""

Important note:
{high_demand_note}

Because this is a high-demand day, your table will not be held if you are late.
"""

    body = f"""
Hi {name},

This is a reminder for your upcoming booking.

Booking time:
{start_time}

Please confirm, cancel, or request an adjustment:

Confirm:
{confirm_link}

Cancel:
{cancel_link}

Request adjustment:
{adjust_link}
{extra_note}

Thanks,
Nomad Brewing Co
"""

    send_email(to_email, "Reminder: please confirm your booking", body)