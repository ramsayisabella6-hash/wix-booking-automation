from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

from calendar_service import create_booking_event
from email_service import send_customer_email, send_staff_email

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
    if booking.guests < 20:
        raise HTTPException(status_code=400, detail="Minimum 20 guests required")

    if booking.start_time.hour >= 22:
        raise HTTPException(status_code=400, detail="No bookings after 10pm")

    end_time = booking.start_time + timedelta(hours=3)

    calendar_link = create_booking_event(
        name=booking.name,
        email=booking.email,
        phone=booking.phone,
        guests=booking.guests,
        start_time=booking.start_time,
        end_time=end_time,
        details=booking.details
    )

    send_customer_email(
        to_email=booking.email,
        name=booking.name,
        start_time=booking.start_time
    )

    send_staff_email(booking)

    return {
        "status": "success",
        "message": "Booking processed",
        "calendar_link": calendar_link
    }