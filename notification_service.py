import os
import requests
from dotenv import load_dotenv

from email_service import send_staff_alert_email

load_dotenv()


def send_owner_notification(message, subject=None):
    """
    Sends a Telegram alert to the owner/manager group, AND a matching
    email to STAFF_EMAIL, so anyone without Telegram access still sees
    every alert. This is the single place all owner/staff notifications
    pass through - every call site below (and any future one) gets both
    channels automatically just by calling this function.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Telegram notification skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
    else:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print("Telegram notification sent.")
        except Exception as e:
            print(f"Telegram notification failed: {e}")

    # Build a short subject line from the message if one wasn't given -
    # use the first non-empty line, stripped of emoji-heavy symbols so
    # it reads cleanly in an inbox subject line.
    if not subject:
        first_line = next((line.strip() for line in message.splitlines() if line.strip()), "Booking notification")
        subject = first_line[:120]

    send_staff_alert_email(subject, message)


def notify_booking_needs_review(booking, rule_status, review_link):
    message = f"""
New booking needs review

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Time: {booking.start_time}

Warnings:
{rule_status}

Review booking:
{review_link}
"""
    send_owner_notification(message, subject=f"Booking needs review: {booking.name}")


def notify_booking_auto_confirmed(booking, calendar_link=None):
    message = f"""
✅ Booking confirmed

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}

Calendar:
{calendar_link or "No calendar link available"}
"""
    send_owner_notification(message, subject=f"Booking auto-confirmed: {booking.name}")


def notify_booking_approved(booking):
    message = f"""
✅ Booking approved

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}
"""
    send_owner_notification(message, subject=f"Booking approved: {booking.name}")


def notify_booking_rejected(booking):
    message = f"""
❌ Booking rejected

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}
"""
    send_owner_notification(message, subject=f"Booking rejected: {booking.name}")


def notify_customer_action(booking, action):
    message = f"""
⚠️ Booking update

Action: {action}

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Time: {booking.start_time}
"""
    send_owner_notification(message, subject=f"{action}: {booking.name}")