import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
SERVICE_ACCOUNT_FILE = "service-account.json"


def get_calendar_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    return build("calendar", "v3", credentials=credentials)


def create_booking_event(name, email, phone, guests, start_time, end_time, details, color_id="5"):
    service = get_calendar_service()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

    event = {
        "summary": name,
        "description": f"""
Customer name: {name}
Email: {email}
Phone: {phone}
Guests: {guests}

{details}
""",
        "colorId": color_id,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "Australia/Sydney",
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "Australia/Sydney",
        },
    }

    created_event = service.events().insert(
        calendarId=calendar_id,
        body=event,
    ).execute()

    return {
        "link": created_event.get("htmlLink"),
        "event_id": created_event.get("id"),
    }


def update_booking_event_status(event_id, new_title, color_id):
    service = get_calendar_service()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

    event = service.events().get(
        calendarId=calendar_id,
        eventId=event_id,
    ).execute()

    event["summary"] = new_title
    event["colorId"] = color_id

    updated_event = service.events().update(
        calendarId=calendar_id,
        eventId=event_id,
        body=event,
    ).execute()

    return updated_event.get("htmlLink")