import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()


def send_sms_alert(message):
    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    recipients = [
        os.getenv("OWNER_PHONE"),
        os.getenv("MANAGER_PHONE")
    ]

    for number in recipients:
        if number:
            client.messages.create(
                body=message,
                from_=os.getenv("TWILIO_PHONE_NUMBER"),
                to=number
            )