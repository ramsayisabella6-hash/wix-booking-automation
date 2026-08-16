import os
import requests
from dotenv import load_dotenv

load_dotenv()


def send_owner_notification(message):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Telegram notification skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return

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
    send_owner_notification(message)


def notify_booking_auto_confirmed(booking, calendar_link=None):
    message = f"""
✅ Booking confirmed

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}

Calendar:
{calendar_link or "No calendar link available"}
"""
    send_owner_notification(message)


def notify_booking_approved(booking):
    message = f"""
✅ Booking approved

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}
"""
    send_owner_notification(message)


def notify_booking_rejected(booking):
    message = f"""
❌ Booking rejected

Name: {booking.name}
Guests: {booking.guests}
Time: {booking.start_time}
"""
    send_owner_notification(message)


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
    send_owner_notification(message)