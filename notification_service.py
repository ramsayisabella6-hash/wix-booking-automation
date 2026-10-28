import os
import requests
from dotenv import load_dotenv

from email_service import send_staff_alert_email

load_dotenv()


def send_owner_notification(message, subject=None, email_too=True):
    """
    Sends a Telegram alert to the owner/manager group, AND (by default) a
    matching email to STAFF_EMAIL, so anyone without Telegram access still
    sees every alert. This is the single place all owner/staff
    notifications pass through.

    Set email_too=False for alerts that should go to Telegram ONLY - used
    for wholesale / private label enquiries, which are not bookings and
    are already emailed to the venue manager by Wix itself. Sending those
    to the staff booking inbox as well would just be noise.
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

    if not email_too:
        return

    # Build a short subject line from the message if one wasn't given -
    # use the first non-empty line, stripped of emoji-heavy symbols so
    # it reads cleanly in an inbox subject line.
    if not subject:
        first_line = next((line.strip() for line in message.splitlines() if line.strip()), "Booking notification")
        subject = first_line[:120]

    send_staff_alert_email(subject, message)


# Wording for each non-booking enquiry form. The key is what the Wix
# automation sends in the URL as ?type=... - add a new entry here if
# another enquiry form is ever pointed at /wix-enquiry.
ENQUIRY_MESSAGES = {
    "wholesale": "📩 A wholesale enquiry was made, check the venue manager email for more details.",
    "private-label": "📩 A private label brewing enquiry was made, check the venue manager email for more details.",
}


def notify_enquiry(enquiry_type):
    """
    Telegram-only alert for the wholesale / private label forms.

    These are deliberately vague: the full submission already goes to the
    venue manager's inbox via Wix's own email automation, so this is just
    a nudge that something arrived, not a copy of the customer's details.
    """
    message = ENQUIRY_MESSAGES.get(
        enquiry_type,
        f"📩 A {str(enquiry_type)[:40]} enquiry was made, check the venue manager email for more details.",
    )
    send_owner_notification(message, email_too=False)


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


# ---------------------------------------------------------------------------
# Non-booking forms (wholesale, private label, anything else)
# ---------------------------------------------------------------------------
# The Wix automation fires for forms on the whole site. Anything that is not
# the booking form must be recognised here BEFORE the booking code runs,
# otherwise it is wrongly reported as "a booking could not be read".

# Words that identify each enquiry form by the form's NAME in Wix
# (Wix Dashboard > Forms). Hyphens/underscores/capitals are ignored.
# To recognise another form, add a line here.
ENQUIRY_FORM_KEYWORDS = {
    "wholesale": ("wholesale",),
    "private-label": ("private label", "privatelabel"),
}

# A form that mentions any of these in a field label or key is treated as a
# booking form, even if it is not recognised by name.
BOOKING_FIELD_WORDS = ("date", "time", "reservation", "guest", "people")


def _form_data(payload):
    """Wix nests the submission under 'data'. Tolerate it being absent."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def get_form_name(payload):
    return str(_form_data(payload).get("formName") or "").strip()


def detect_enquiry_type(payload):
    """Returns 'wholesale', 'private-label' or None, based on the form name."""
    name = get_form_name(payload).lower().replace("-", " ").replace("_", " ")
    name = " ".join(name.split())

    for enquiry_type, keywords in ENQUIRY_FORM_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return enquiry_type

    return None


def looks_like_booking(payload):
    """
    True if the submission has booking-style fields (a date, a time, a
    guest count). Wholesale / private label / newsletter forms do not.
    """
    data = _form_data(payload)

    # The flat shape used by direct API tests.
    if "start_time" in data and "guests" in data:
        return True

    for key in data:
        key_text = str(key).lower()
        if key_text.startswith("field:") and any(w in key_text for w in BOOKING_FIELD_WORDS):
            return True

    for item in data.get("submissions") or []:
        label = str(item.get("label", "")).lower() if isinstance(item, dict) else ""
        if any(w in label for w in BOOKING_FIELD_WORDS):
            return True

    return False


def notify_other_form(form_name):
    """Telegram-only heads-up for a form we don't recognise and that isn't a booking."""
    name = form_name or "unnamed form"
    send_owner_notification(
        f"\U0001F4E9 A form that isn't a booking was submitted ({name}), "
        "check the venue manager email for more details.",
        email_too=False,
    )


def handle_non_booking_form(payload):
    """
    Called at the top of /wix-booking.

    Returns a response dict (and has already sent the Telegram alert) if the
    submission is NOT a booking, or None if it should carry on through the
    normal booking code.
    """
    data = _form_data(payload)
    form_name = get_form_name(payload)
    print(f"Wix form received: name={form_name!r} id={data.get('formId')!r}")

    enquiry_type = detect_enquiry_type(payload)
    if enquiry_type:
        notify_enquiry(enquiry_type)
        return {
            "status": "received",
            "type": enquiry_type,
            "message": "Enquiry form - not a booking",
        }

    if not looks_like_booking(payload):
        notify_other_form(form_name)
        return {
            "status": "received",
            "type": "other",
            "message": "Not a booking form",
        }

    return None