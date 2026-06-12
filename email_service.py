import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def send_customer_email(to_email, name, start_time):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")

    msg = EmailMessage()
    msg["Subject"] = "Booking request received"
    msg["From"] = sender
    msg["To"] = to_email

    msg.set_content(f"""
Hi {name},

Thanks for your booking request.

We have received your request for:
{start_time.strftime("%A %d %B %Y at %I:%M %p")}

Our team will review it and confirm shortly.

Thanks,
The Bar Team
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)


def send_staff_email(booking):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    staff_email = os.getenv("STAFF_EMAIL")

    msg = EmailMessage()
    msg["Subject"] = f"New booking request: {booking.name}"
    msg["From"] = sender
    msg["To"] = staff_email

    msg.set_content(f"""
New booking request received.

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Start time: {booking.start_time}
Details: {booking.details}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)