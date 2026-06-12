from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import os

from calendar_service import create_booking_event, update_booking_event_status
from email_service import (
    send_staff_review_email,
    send_customer_approved_email,
    send_customer_rejected_email,
)
from rules import validate_booking_rules
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
        rule_status = f"⚠️ Rule warning:\n{rule_message}"
        calendar_title = f"REVIEW REQUIRED - {booking.name}"

    calendar_result = create_booking_event(
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
""",
        color_id="5",
    )

    calendar_link = calendar_result["link"]
    calendar_event_id = calendar_result["event_id"]

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
        calendar_link=calendar_link,
        calendar_event_id=calendar_event_id,
    )

    db.add(booking_record)
    db.commit()
    db.refresh(booking_record)

    booking_id = booking_record.id
    db.close()

    base_url = os.getenv("BASE_URL", "https://wix-booking-automation.onrender.com")
    approval_secret = os.getenv("APPROVAL_SECRET", "change-this-secret")

    review_link = f"{base_url}/review-booking/{booking_id}?secret={approval_secret}"

    send_staff_review_email(booking, rule_status, review_link)

    return {
        "status": "pending",
        "message": "Booking received and awaiting approval",
        "rule_check": rule_status,
        "review_link": review_link,
        "calendar_link": calendar_link,
    }


@app.get("/review-booking/{booking_id}", response_class=HTMLResponse)
def review_booking(booking_id: int, secret: str):
    if secret != os.getenv("APPROVAL_SECRET", "change-this-secret"):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()
    db.close()

    if not booking:
        return "<h1>Booking not found</h1>"

    approval_secret = os.getenv("APPROVAL_SECRET", "change-this-secret")

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px; max-width: 750px; margin: auto;">
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
            <pre style="font-size: 16px; white-space: pre-wrap;">{booking.rule_warnings}</pre>

            <p>
                <a href="{booking.calendar_link}" target="_blank">
                    View Google Calendar Event
                </a>
            </p>

            <br>

            <a href="/approve-booking/{booking.id}?secret={approval_secret}">
                <button style="font-size: 24px; padding: 15px 25px; background: green; color: white; border: none; border-radius: 8px;">
                    APPROVE BOOKING
                </button>
            </a>

            <br><br>

            <a href="/reject-booking/{booking.id}?secret={approval_secret}">
                <button style="font-size: 24px; padding: 15px 25px; background: red; color: white; border: none; border-radius: 8px;">
                    REJECT BOOKING
                </button>
            </a>
        </body>
    </html>
    """


@app.get("/approve-booking/{booking_id}", response_class=HTMLResponse)
def approve_booking(booking_id: int, secret: str):
    if secret != os.getenv("APPROVAL_SECRET", "change-this-secret"):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

    if not booking:
        db.close()
        return "<h1>Booking not found</h1>"

    if booking.status == "approved":
        db.close()
        return "<h1>Booking was already approved</h1>"

    booking.status = "approved"

    if booking.calendar_event_id:
        update_booking_event_status(
            booking.calendar_event_id,
            f"CONFIRMED - {booking.name} - {booking.guests} guests",
            "10",
        )

    customer_email = booking.email
    customer_name = booking.name
    start_time = booking.start_time

    db.commit()
    db.close()

    send_customer_approved_email(customer_email, customer_name, start_time)

    return """
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Approved</h1>
            <p>The Google Calendar event has been marked as confirmed.</p>
            <p>If email settings are configured, the customer has been sent a confirmation email.</p>
        </body>
    </html>
    """


@app.get("/reject-booking/{booking_id}", response_class=HTMLResponse)
def reject_booking(booking_id: int, secret: str):
    if secret != os.getenv("APPROVAL_SECRET", "change-this-secret"):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

    if not booking:
        db.close()
        return "<h1>Booking not found</h1>"

    booking.status = "rejected"

    if booking.calendar_event_id:
        update_booking_event_status(
            booking.calendar_event_id,
            f"❌ REJECTED - {booking.name} - {booking.guests} guests",
            "11",
        )

    customer_email = booking.email
    customer_name = booking.name
    start_time = booking.start_time

    db.commit()
    db.close()

    send_customer_rejected_email(customer_email, customer_name, start_time)

    return """
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Rejected</h1>
            <p>The Google Calendar event has been marked as rejected.</p>
            <p>If email settings are configured, the customer has been sent a rejection email.</p>
        </body>
    </html>
    """


@app.get("/bookings", response_class=HTMLResponse)
def bookings_dashboard(secret: str):
    if secret != os.getenv("APPROVAL_SECRET", "change-this-secret"):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    bookings = db.query(BookingRecord).order_by(BookingRecord.created_at.desc()).all()
    db.close()

    approval_secret = os.getenv("APPROVAL_SECRET", "change-this-secret")

    rows = ""

    for booking in bookings:
        rows += f"""
        <tr>
            <td>{booking.id}</td>
            <td>{booking.status}</td>
            <td>{booking.name}</td>
            <td>{booking.guests}</td>
            <td>{booking.start_time}</td>
            <td><pre style="white-space: pre-wrap;">{booking.rule_warnings}</pre></td>
            <td><a href="/review-booking/{booking.id}?secret={approval_secret}">Review</a></td>
        </tr>
        """

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Dashboard</h1>

            <table border="1" cellpadding="10" cellspacing="0">
                <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Name</th>
                    <th>Guests</th>
                    <th>Start Time</th>
                    <th>Warnings</th>
                    <th>Review</th>
                </tr>
                {rows}
            </table>
        </body>
    </html>
    """