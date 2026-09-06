import os
import requests
from dotenv import load_dotenv

load_dotenv()

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send_email(to_email, subject, body):
    """
    Sends email via SendGrid's HTTP API rather than raw SMTP.
    Render (and many cloud hosts) block outbound SMTP connections entirely
    at the network level - this is not a credentials issue, it's why SMTP
    always failed with "Network is unreachable" no matter what mail server
    or password was used. HTTPS-based APIs like SendGrid are not blocked.
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("EMAIL_FROM")

    if not api_key or not from_email:
        print("Email skipped: Missing SENDGRID_API_KEY or EMAIL_FROM.")
        return

    if not to_email:
        print("Email skipped: No recipient provided.")
        return

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(SENDGRID_URL, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 202):
            print(f"Email sent to {to_email}")
        else:
            print(f"Email failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"Email failed (exception): {e}")


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