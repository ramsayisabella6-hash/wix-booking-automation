from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, time
import os
import html

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

DAILY_GUEST_LIMIT = 100


class BookingRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    start_time: datetime
    guests: int
    details: str | None = ""


def get_secret():
    return os.getenv("APPROVAL_SECRET", "change-this-secret")


def check_secret(secret: str):
    return secret == get_secret()


def get_daily_approved_guest_total(db, booking_date):
    day_start = datetime.combine(booking_date, time.min)
    day_end = datetime.combine(booking_date, time.max)

    approved_bookings = (
        db.query(BookingRecord)
        .filter(BookingRecord.status == "approved")
        .filter(BookingRecord.start_time >= day_start)
        .filter(BookingRecord.start_time <= day_end)
        .all()
    )

    return sum(b.guests or 0 for b in approved_bookings)


@app.get("/")
def home():
    return {"message": "Wix booking automation is running"}


@app.get("/manager")
def manager_redirect(secret: str):
    return RedirectResponse(url=f"/bookings?secret={secret}")


@app.post("/wix-booking")
def receive_booking(booking: BookingRequest):
    db = SessionLocal()

    is_valid, rule_message = validate_booking_rules(booking)

    current_daily_total = get_daily_approved_guest_total(db, booking.start_time.date())
    total_if_approved = current_daily_total + booking.guests

    warnings = []

    if not is_valid:
        warnings.append(rule_message)

    if total_if_approved > DAILY_GUEST_LIMIT:
        warnings.append(
            f"Daily guest warning: currently {current_daily_total} approved guests. "
            f"This booking would bring the day to {total_if_approved}, over the limit of {DAILY_GUEST_LIMIT}."
        )

    if warnings:
        rule_status = "⚠️ Rule warnings:\n" + "\n".join(warnings)
        calendar_title = f"REVIEW REQUIRED - {booking.name}"
    else:
        rule_status = "✅ Booking meets current rules"
        calendar_title = f"PENDING - {booking.name}"

    end_time = booking.start_time + timedelta(hours=3)

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
        calendar_link=calendar_result["link"],
        calendar_event_id=calendar_result["event_id"],
    )

    db.add(booking_record)
    db.commit()
    db.refresh(booking_record)

    booking_id = booking_record.id
    db.close()

    base_url = os.getenv("BASE_URL", "https://wix-booking-automation.onrender.com")
    review_link = f"{base_url}/review-booking/{booking_id}?secret={get_secret()}"

    send_staff_review_email(booking, rule_status, review_link)

    return {
        "status": "pending",
        "message": "Booking received and awaiting approval",
        "rule_check": rule_status,
        "review_link": review_link,
        "calendar_link": calendar_result["link"],
    }


@app.get("/review-booking/{booking_id}", response_class=HTMLResponse)
def review_booking(booking_id: int, secret: str):
    if not check_secret(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()
    db.close()

    if not booking:
        return "<h1>Booking not found</h1>"

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px; max-width: 750px; margin: auto;">
            <h1>Booking Request</h1>
            <h2>Status: {html.escape(booking.status.upper())}</h2>

            <p><b>Name:</b> {html.escape(booking.name or "")}</p>
            <p><b>Email:</b> {html.escape(booking.email or "")}</p>
            <p><b>Phone:</b> {html.escape(booking.phone or "")}</p>
            <p><b>Guests:</b> {booking.guests}</p>
            <p><b>Start:</b> {booking.start_time}</p>
            <p><b>End:</b> {booking.end_time}</p>
            <p><b>Details:</b> {html.escape(booking.details or "")}</p>

            <h2>Warnings</h2>
            <pre style="background:#f6f6f6; padding:15px; white-space:pre-wrap;">{html.escape(booking.rule_warnings or "")}</pre>

            <p><a href="{booking.calendar_link}" target="_blank">View Calendar Event</a></p>

            <a href="/approve-booking/{booking.id}?secret={secret}">
                <button style="font-size:22px; padding:15px 25px; background:green; color:white; border:none; border-radius:8px;">
                    APPROVE
                </button>
            </a>

            <br><br>

            <a href="/reject-booking/{booking.id}?secret={secret}">
                <button style="font-size:22px; padding:15px 25px; background:red; color:white; border:none; border-radius:8px;">
                    REJECT
                </button>
            </a>

            <br><br>
            <a href="/bookings?secret={secret}">Back to dashboard</a>
        </body>
    </html>
    """


@app.get("/approve-booking/{booking_id}", response_class=HTMLResponse)
def approve_booking(booking_id: int, secret: str):
    if not check_secret(secret):
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

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Approved</h1>
            <p>The customer confirmation email has been attempted.</p>
            <p>The calendar event has been marked as confirmed.</p>
            <a href="/bookings?secret={secret}">Back to dashboard</a>
        </body>
    </html>
    """


@app.get("/reject-booking/{booking_id}", response_class=HTMLResponse)
def reject_booking(booking_id: int, secret: str):
    if not check_secret(secret):
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

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Rejected</h1>
            <p>The customer rejection email has been attempted.</p>
            <p>The calendar event has been marked as rejected.</p>
            <a href="/bookings?secret={secret}">Back to dashboard</a>
        </body>
    </html>
    """


@app.get("/bookings", response_class=HTMLResponse)
def bookings_dashboard(secret: str):
    if not check_secret(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    bookings = db.query(BookingRecord).order_by(BookingRecord.created_at.desc()).all()
    db.close()

    pending = [b for b in bookings if b.status == "pending"]
    approved = [b for b in bookings if b.status == "approved"]
    rejected = [b for b in bookings if b.status == "rejected"]

    def render_table(title, items):
        rows = ""

        for booking in items:
            status_badge = {
                "pending": "🟡 Pending",
                "approved": "🟢 Approved",
                "rejected": "🔴 Rejected",
            }.get(booking.status, booking.status)

            actions = f"""
            <a href="/review-booking/{booking.id}?secret={secret}">Review</a>
            """

            if booking.status == "pending":
                actions += f"""
                <br><br>
                <a href="/approve-booking/{booking.id}?secret={secret}">Approve</a>
                |
                <a href="/reject-booking/{booking.id}?secret={secret}">Reject</a>
                """

            rows += f"""
            <tr>
                <td>{booking.id}</td>
                <td>{status_badge}</td>
                <td>{html.escape(booking.name or "")}</td>
                <td>{booking.guests}</td>
                <td>{booking.start_time}</td>
                <td><pre style="white-space:pre-wrap;">{html.escape(booking.rule_warnings or "")}</pre></td>
                <td>{actions}</td>
            </tr>
            """

        return f"""
        <h2>{title} ({len(items)})</h2>
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <tr style="background:#eee;">
                <th>ID</th>
                <th>Status</th>
                <th>Name</th>
                <th>Guests</th>
                <th>Start Time</th>
                <th>Warnings</th>
                <th>Actions</th>
            </tr>
            {rows if rows else '<tr><td colspan="7">No bookings</td></tr>'}
        </table>
        """

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Nomad Booking Dashboard</h1>

            <p>
                <b>Pending:</b> {len(pending)} |
                <b>Approved:</b> {len(approved)} |
                <b>Rejected:</b> {len(rejected)}
            </p>

            {render_table("Pending Bookings", pending)}
            <br>
            {render_table("Approved Bookings", approved)}
            <br>
            {render_table("Rejected Bookings", rejected)}
        </body>
    </html>
    """