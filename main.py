from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

from calendar_service import create_booking_event
from email_service import send_customer_email, send_staff_email
from rules import validate_booking_rules, MAX_GUESTS_BEFORE_ALERT
from sms_service import send_sms_alert

app = FastAPI()


class BookingRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    start_time: datetime
    guests: int
    details: str | None = ""


@app.get("/")
def home():
    return {"message": "Wix booking automation is running"}


@app.post("/wix-booking")
def receive_booking(booking: BookingRequest):
    is_valid, message = validate_booking_rules(booking)

    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    end_time = booking.start_time + timedelta(hours=3)

    calendar_link = create_booking_event(
        name=f"PENDING - {booking.name}",
        email=booking.email,
        phone=booking.phone,
        guests=booking.guests,
        start_time=booking.start_time,
        end_time=end_time,
        details=f"""
STATUS: PENDING APPROVAL

Customer has NOT been sent confirmation yet.

{booking.details}
"""
    )

    send_staff_email(booking)

    if booking.guests >= MAX_GUESTS_BEFORE_ALERT:
        send_sms_alert(
    f"Large booking request: {booking.name}, {booking.guests} guests, {booking.start_time}"
)

    return {
        "status": "pending",
        "message": "Booking received and awaiting approval",
        "calendar_link": calendar_link
    }