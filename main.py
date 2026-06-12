from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import os

from calendar_service import create_booking_event, update_booking_event_title
from email_service import send_customer_email, send_staff_email
from rules import validate_booking_rules, MAX_GUESTS_BEFORE_ALERT
from database import SessionLocal, BookingRecord, create_tables


app = FastAPI()
create_tables()


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
    is_valid, rule_message = validate_booking_rules(booking)

    end_time = booking.start_time + timedelta(hours=3)

    if is_valid:
        rule_status = "✅ Booking meets current rules"
        calendar_title = f"PENDING - {booking.name}"
    else:
        rule_status = f"⚠️ Rule warning: {rule_message}"
        calendar_title = f"REVIEW REQUIRED - {booking.name}"

    calendar_result = create_booking_event(
        calendar_link = calendar_result["link"]
        calendar_event_id = calendar_result["event_id"]
        name=calendar_title,
        email=booking.email,
        phone=booking.phone,
        guests=booking.guests,
        start_time=booking.start_time,
        end_time=end_time,
        details=f"""
        
STATUS: PENDING APPROVAL

Customer has NOT been sent confirmation yet.

Rule check:
{rule_status}

Customer details:
{booking.details}
"""
    )

    db = SessionLocal()

    booking_record = BookingRecord(
        name=booking.name,
        email=booking.email,
        phone=booking.phone,
        start_time=booking.start_time,
        end_time=end_time,
        guests=booking.guests,
        details=booking.details,
        status="pending",
        rule_warnings=rule_status,
        calendar_link=calendar_link
        calendar_event_id=calendar_event_id,
    )

    db.add(booking_record)
    db.commit()
    db.refresh(booking_record)

    booking_id = booking_record.id
    db.close()

    base_url = os.getenv(
        "BASE_URL",
        "https://wix-booking-automation.onrender.com"
    )

    review_link = f"{base_url}/review-booking/{booking_id}"

    # Sends staff an email with the review link.
    send_staff_email_with_review_link(booking, rule_status, review_link)

    # Optional SMS alert. Leave commented unless you have sms_service.py working.
    """
    if booking.guests >= MAX_GUESTS_BEFORE_ALERT or not is_valid:
        send_sms_alert(
            f"Booking needs review: {booking.name}, "
            f"{booking.guests} guests, {booking.start_time}. "
            f"Review: {review_link}"
        )
    """

    return {
        "status": "pending",
        "message": "Booking received and awaiting approval",
        "rule_check": rule_status,
        "review_link": review_link,
        "calendar_link": calendar_link
    }


def send_staff_email_with_review_link(booking, rule_status, review_link):
    """
    This uses your existing send_staff_email function if you have it.
    If your email_service.py only prints test emails, this will still be okay
    once you update email_service.py later.
    """

    print("NEW BOOKING NEEDS REVIEW")
    print(f"Name: {booking.name}")
    print(f"Email: {booking.email}")
    print(f"Phone: {booking.phone}")
    print(f"Guests: {booking.guests}")
    print(f"Start time: {booking.start_time}")
    print(f"Rule check: {rule_status}")
    print(f"Review link: {review_link}")

    try:
        send_staff_email(booking)
    except Exception as error:
        print("Staff email failed, but booking was still saved.")
        print(error)


@app.get("/review-booking/{booking_id}", response_class=HTMLResponse)
def review_booking(booking_id: int):
    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()
    db.close()

    if not booking:
        return """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h1>Booking not found</h1>
            </body>
        </html>
        """

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px; max-width: 700px; margin: auto;">
            <h1>Booking Request</h1>

            <h2>Status: {booking.status.upper()}</h2>

            <p><b>Name:</b> {booking.name}</p>
            <p><b>Email:</b> {booking.email}</p>
            <p><b>Phone:</b> {booking.phone}</p>
            <p><b>Guests:</b> {booking.guests}</p>
            <p><b>Start time:</b> {booking.start_time}</p>
            <p><b>End time:</b> {booking.end_time}</p>
            <p><b>Details:</b> {booking.details}</p>

            <h2>Rule Check</h2>
            <p style="font-size: 18px;">{booking.rule_warnings}</p>

            <p>
                <a href="{booking.calendar_link}" target="_blank">
                    View Google Calendar Event
                </a>
            </p>

            <br>

            <a href="/approve-booking/{booking.id}">
                <button style="
                    font-size: 24px;
                    padding: 15px 25px;
                    background: green;
                    color: white;
                    border: none;
                    border-radius: 8px;
                ">
                    APPROVE BOOKING
                </button>
            </a>

            <br><br>

            <a href="/reject-booking/{booking.id}">
                <button style="
                    font-size: 24px;
                    padding: 15px 25px;
                    background: red;
                    color: white;
                    border: none;
                    border-radius: 8px;
                ">
                    REJECT BOOKING
                </button>
            </a>
        </body>
    </html>
    """


@app.get("/approve-booking/{booking_id}", response_class=HTMLResponse)
def approve_booking(booking_id: int):
    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

    if not booking:
        db.close()
        return """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h1>Booking not found</h1>
            </body>
        </html>
        """

    if booking.status == "approved":
        db.close()
        return """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h1>Booking was already approved</h1>
            </body>
        </html>
        """

    booking.status = "approved"
    if booking.calendar_event_id:
    update_booking_event_title(
        booking.calendar_event_id,
        f"CONFIRMED - {booking.name} - {booking.guests} guests"
    )db.commit()

    customer_email = booking.email
    customer_name = booking.name
    start_time = booking.start_time

    db.close()

    try:
        send_customer_email(
            to_email=customer_email,
            name=customer_name,
            start_time=start_time
        )
        email_status = "Confirmation email sent to customer."
    except Exception as error:
        print("Customer confirmation email failed.")
        print(error)
        email_status = "Booking approved, but confirmation email failed."

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Approved</h1>
            <p>{email_status}</p>
            <p>You can now close this page.</p>
        </body>
    </html>
    """


@app.get("/reject-booking/{booking_id}", response_class=HTMLResponse)
def reject_booking(booking_id: int):
    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

    if not booking:
        db.close()
        return """
        <html>
            <body style="font-family: Arial; padding: 30px;">
                <h1>Booking not found</h1>
            </body>
        </html>
        """

    booking.status = "rejected"
    if booking.calendar_event_id:
    update_booking_event_title(
        booking.calendar_event_id,
        f"❌ REJECTED - {booking.name} - {booking.guests} guests"
    )db.commit()
    db.close()

    return """
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Rejected</h1>
            <p>No confirmation email has been sent.</p>
            <p>You can now close this page.</p>
        </body>
    </html>
    """