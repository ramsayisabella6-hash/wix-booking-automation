import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def send_email(to_email, subject, body):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")

    if not sender or not password or not to_email:
        print("Email skipped. Missing EMAIL_USER, EMAIL_PASSWORD, or recipient.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)


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

    send_email(
        to_email=staff_email,
        subject=f"Booking needs review: {booking.name}",
        body=body,
    )


def send_customer_approved_email(to_email, name, start_time):
    body = f"""
Hi {name},

Your booking has been confirmed.

Booking time:
{start_time}

Thanks,
The Bar Team
"""

    send_email(
        to_email=to_email,
        subject="Booking confirmed",
        body=body,
    )


def send_customer_rejected_email(to_email, name, start_time):
    body = f"""
Hi {name},

Thanks for your booking request.

Unfortunately, we are unable to accept your booking at:
{start_time}

Please contact us directly if you would like to discuss another time.

Thanks,
The Bar Team
"""

    send_email(
        to_email=to_email,
        subject="Booking request update",
        body=body,
    )