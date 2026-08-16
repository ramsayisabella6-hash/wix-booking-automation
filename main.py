from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import os
import html

from calendar_service import create_booking_event, update_booking_event_status
from email_service import (
    send_staff_review_email,
    send_staff_alert_email,
    send_customer_pending_review_email,
    send_customer_approved_email,
    send_customer_rejected_email,
    send_customer_reminder_email,
)
from rules import validate_booking_rules
from database import SessionLocal, BookingRecord, create_tables

from notification_service import (
    notify_booking_needs_review,
    notify_booking_auto_confirmed,
    notify_booking_approved,
    notify_booking_rejected,
    notify_customer_action,
)

app = FastAPI()
create_tables()

DAILY_GUEST_LIMIT = 150
OWNER_APPROVAL_GUEST_LIMIT = 20
SYDNEY_TZ = ZoneInfo("Australia/Sydney")


class BookingRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    start_time: datetime
    guests: int
    details: str | None = ""


def normalize_to_sydney(dt: datetime) -> datetime:
    """
    Wix may send a timezone-aware datetime (e.g. UTC with a 'Z' suffix)
    or a naive one. Everywhere else in this app (rules.py, opening hours,
    "hours until close", daily capacity by calendar day) assumes the
    stored start_time is a *naive* Sydney wall-clock time. This function
    is the single place that guarantees that assumption is true.

    - If dt has no tzinfo, we assume it was already given in Sydney time.
    - If dt has tzinfo, we convert it to Sydney time and drop the tzinfo.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(SYDNEY_TZ).replace(tzinfo=None)


def get_secret():
    secret = os.getenv("APPROVAL_SECRET")
    if not secret:
        # Fail fast if secret is not configured
        raise RuntimeError("APPROVAL_SECRET environment variable must be set")
    return secret


def check_secret(secret: str):
    return secret == get_secret()


def check_webhook_secret(provided: str | None):
    """
    Protects /wix-booking from randoms hitting the endpoint directly and
    spamming your calendar/inbox/Telegram with fake bookings. Set
    WIX_WEBHOOK_SECRET in your environment and send the same value as an
    'X-Webhook-Secret' header from your Wix backend code.
    """
    expected = os.getenv("WIX_WEBHOOK_SECRET")
    if not expected:
        # Fail fast in production if this hasn't been configured, so you
        # don't accidentally ship the endpoint wide open.
        raise RuntimeError("WIX_WEBHOOK_SECRET environment variable must be set")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def get_base_url():
    return os.getenv("BASE_URL", "https://wix-booking-automation.onrender.com")


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


def get_high_demand_note(booking_date):
    """
    Add high-demand dates in Render env like this:

    HIGH_DEMAND_DATES=2026-07-12:Manly home game,2026-08-03:Public holiday
    """

    raw_dates = os.getenv("HIGH_DEMAND_DATES", "")
    booking_date_text = booking_date.isoformat()

    for item in raw_dates.split(","):
        item = item.strip()

        if not item:
            continue

        if ":" in item:
            date_text, label = item.split(":", 1)
        else:
            date_text, label = item, "High-demand day"

        if date_text.strip() == booking_date_text:
            return label.strip()

    return None


@app.get("/")
def home():
    return {"message": "Wix booking automation is running"}


@app.get("/manager")
def manager_redirect(secret: str):
    return RedirectResponse(url=f"/bookings?secret={secret}")


@app.post("/wix-booking")
def receive_booking(booking: BookingRequest, x_webhook_secret: str | None = Header(default=None)):
    check_webhook_secret(x_webhook_secret)

    # Normalize the incoming time to a naive Sydney wall-clock datetime
    # before anything else touches it (rules checks, storage, calendar).
    booking.start_time = normalize_to_sydney(booking.start_time)

    db = SessionLocal()
    try:
        is_valid, rule_message = validate_booking_rules(booking)

        current_daily_total = get_daily_approved_guest_total(db, booking.start_time.date())
        total_if_approved = current_daily_total + booking.guests
        high_demand_note = get_high_demand_note(booking.start_time.date())

        warnings = []

        # Normal booking-rule warnings, such as closed days or invalid times.
        if not is_valid and rule_message:
            warnings.append(rule_message)

        # More than 20 guests must be approved by the owner.
        if booking.guests > OWNER_APPROVAL_GUEST_LIMIT:
            warnings.append(
                f"Owner approval required: this booking is for {booking.guests} guests. "
                f"Bookings above {OWNER_APPROVAL_GUEST_LIMIT} guests need approval."
            )

        # Warn if approving this booking would exceed the daily guest limit.
        if total_if_approved > DAILY_GUEST_LIMIT:
            warnings.append(
                f"Daily capacity warning: currently {current_daily_total} approved guests. "
                f"This booking would bring the day to {total_if_approved}, "
                f"over the limit of {DAILY_GUEST_LIMIT}."
            )

        # High-demand dates also require owner review.
        if high_demand_note:
            warnings.append(f"High-demand day: {high_demand_note}")

        needs_owner_approval = len(warnings) > 0
        end_time = booking.start_time + timedelta(hours=3)

        if needs_owner_approval:
            status = "pending"
            customer_response = "not_sent"
            rule_status = "⚠️ Owner review required:\n" + "\n".join(warnings)
            calendar_title = f"REVIEW REQUIRED - {booking.name}"
            calendar_color = "5"
            calendar_details = f"""STATUS: PENDING APPROVAL

Customer has been told that the booking is waiting for approval.

Rule check:
{rule_status}

Customer details:
{booking.details}
"""
        else:
            status = "approved"
            customer_response = "not_sent"
            rule_status = "✅ Booking automatically confirmed"
            calendar_title = f"CONFIRMED - {booking.name} - {booking.guests} guests"
            calendar_color = "10"
            calendar_details = f"""STATUS: CONFIRMED

This booking was automatically confirmed because it has between 2 and 20 guests
and meets the current booking rules.

Customer details:
{booking.details}
"""

        calendar_result = create_booking_event(
            name=calendar_title,
            email=booking.email,
            phone=booking.phone,
            guests=booking.guests,
            start_time=booking.start_time,
            end_time=end_time,
            details=calendar_details,
            color_id=calendar_color,
        )

        booking_record = BookingRecord(
            name=booking.name,
            email=booking.email,
            phone=booking.phone,
            start_time=booking.start_time,
            end_time=end_time,
            guests=booking.guests,
            details=booking.details,
            status=status,
            customer_response=customer_response,
            rule_warnings=rule_status,
            high_demand_note=high_demand_note,
            calendar_link=calendar_result["link"],
            calendar_event_id=calendar_result["event_id"],
        )

        db.add(booking_record)
        db.commit()
        db.refresh(booking_record)
        booking_id = booking_record.id

    finally:
        db.close()

    if needs_owner_approval:
        review_link = f"{get_base_url()}/review-booking/{booking_id}?secret={get_secret()}"

        send_staff_review_email(booking, rule_status, review_link)
        notify_booking_needs_review(booking, rule_status, review_link)

        # Every pending booking receives this email.
        send_customer_pending_review_email(
            booking.email,
            booking.name,
            booking.start_time,
        )

        return {
            "status": "pending",
            "message": "Booking received and awaiting owner approval",
            "rule_check": rule_status,
        }

    send_customer_approved_email(
        booking.email,
        booking.name,
        booking.start_time,
        high_demand_note,
    )
    notify_booking_auto_confirmed(booking, calendar_result["link"])

    return {
        "status": "approved",
        "message": "Booking automatically confirmed",
        "rule_check": rule_status,
    }


@app.get("/review-booking/{booking_id}", response_class=HTMLResponse)
def review_booking(booking_id: int, secret: str):
    if not check_secret(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()
    finally:
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
            <p><b>Customer response:</b> {html.escape(booking.customer_response or "")}</p>

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
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

        if not booking:
            return "<h1>Booking not found</h1>"

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
        high_demand_note = booking.high_demand_note

        db.commit()
    finally:
        db.close()

    send_customer_approved_email(customer_email, customer_name, start_time, high_demand_note)
    notify_booking_approved(booking)

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Approved</h1>
            <p>The customer confirmation email has been attempted.</p>
            <a href="/bookings?secret={secret}">Back to dashboard</a>
        </body>
    </html>
    """


@app.get("/reject-booking/{booking_id}", response_class=HTMLResponse)
def reject_booking(booking_id: int, secret: str):
    if not check_secret(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

        if not booking:
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
    finally:
        db.close()

    send_customer_rejected_email(customer_email, customer_name, start_time)
    notify_booking_rejected(booking)

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Booking Rejected</h1>
            <p>The customer rejection email has been attempted.</p>
            <a href="/bookings?secret={secret}">Back to dashboard</a>
        </body>
    </html>
    """


@app.get("/customer-confirm/{booking_id}", response_class=HTMLResponse)
def customer_confirm(booking_id: int):
    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

        if not booking:
            return "<h1>Booking not found</h1>"

        booking.customer_response = "confirmed"
        db.commit()
    finally:
        db.close()

    notify_customer_action(booking, "Customer confirmed booking")

    return "<h1>Thanks, your booking has been confirmed.</h1>"


@app.get("/customer-cancel/{booking_id}", response_class=HTMLResponse)
def customer_cancel(booking_id: int):
    """
    Shows a confirmation page rather than cancelling immediately. This
    link goes out in emails, and email providers/security scanners
    routinely "prefetch" links in emails to check them for safety —
    which would silently trigger a real cancellation before the customer
    ever opens the email if this endpoint acted immediately. Requiring an
    explicit click on this page avoids that.
    """
    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()
    finally:
        db.close()

    if not booking:
        return "<h1>Booking not found</h1>"

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px; max-width: 600px; margin: auto;">
            <h1>Cancel your booking?</h1>
            <p>Booking for {html.escape(booking.name or "")} at {booking.start_time}.</p>
            <a href="/customer-cancel-confirm/{booking.id}">
                <button style="font-size:20px; padding:12px 20px; background:red; color:white; border:none; border-radius:8px;">
                    Yes, cancel my booking
                </button>
            </a>
        </body>
    </html>
    """


@app.get("/customer-cancel-confirm/{booking_id}", response_class=HTMLResponse)
def customer_cancel_confirm(booking_id: int):
    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

        if not booking:
            return "<h1>Booking not found</h1>"

        booking.customer_response = "cancel_requested"
        booking.status = "cancel_requested"

        db.commit()
    finally:
        db.close()

    notify_customer_action(booking, "Customer requested cancellation")

    send_staff_alert_email(
        f"Customer wants to cancel booking: {booking.name}",
        f"""
Customer cancellation request.

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Start time: {booking.start_time}
""",
    )

    return "<h1>Your cancellation request has been sent.</h1>"


@app.get("/customer-adjust/{booking_id}", response_class=HTMLResponse)
def customer_adjust(booking_id: int):
    db = SessionLocal()
    try:
        booking = db.query(BookingRecord).filter(BookingRecord.id == booking_id).first()

        if not booking:
            return "<h1>Booking not found</h1>"

        booking.customer_response = "adjustment_requested"

        db.commit()
    finally:
        db.close()

    notify_customer_action(booking, "Customer requested adjustment")

    send_staff_alert_email(
        f"Customer wants to adjust booking: {booking.name}",
        f"""
Customer adjustment request.

Name: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Guests: {booking.guests}
Start time: {booking.start_time}

Please contact the customer to adjust this booking.
""",
    )

    return "<h1>Your adjustment request has been sent. We will contact you soon.</h1>"


@app.get("/send-reminders")
def send_reminders(secret: str):
    if not check_secret(secret):
        return {"error": "Unauthorized"}

    db = SessionLocal()
    try:
        now = datetime.now(SYDNEY_TZ).replace(tzinfo=None)
        reminder_start = now + timedelta(hours=47)
        reminder_end = now + timedelta(hours=49)

        bookings = (
            db.query(BookingRecord)
            .filter(BookingRecord.status == "approved")
            .filter(BookingRecord.reminder_sent_at == None)
            .filter(BookingRecord.start_time >= reminder_start)
            .filter(BookingRecord.start_time <= reminder_end)
            .all()
        )

        sent_count = 0

        for booking in bookings:
            confirm_link = f"{get_base_url()}/customer-confirm/{booking.id}"
            cancel_link = f"{get_base_url()}/customer-cancel/{booking.id}"
            adjust_link = f"{get_base_url()}/customer-adjust/{booking.id}"

            send_customer_reminder_email(
                booking.email,
                booking.name,
                booking.start_time,
                confirm_link,
                cancel_link,
                adjust_link,
                booking.high_demand_note,
            )

            booking.reminder_sent_at = now
            sent_count += 1

        db.commit()
    finally:
        db.close()

    return {"sent_reminders": sent_count}


@app.get("/bookings", response_class=HTMLResponse)
def bookings_dashboard(secret: str):
    if not check_secret(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    try:
        bookings = db.query(BookingRecord).order_by(BookingRecord.created_at.desc()).all()
    finally:
        db.close()

    rows = ""

    for booking in bookings:
        rows += f"""
        <tr>
            <td>{booking.id}</td>
            <td>{html.escape(booking.status or "")}</td>
            <td>{html.escape(booking.customer_response or "")}</td>
            <td>{html.escape(booking.name or "")}</td>
            <td>{booking.guests}</td>
            <td>{booking.start_time}</td>
            <td><pre style="white-space:pre-wrap;">{html.escape(booking.rule_warnings or "")}</pre></td>
            <td><a href="/review-booking/{booking.id}?secret={secret}">Review</a></td>
        </tr>
        """

    return f"""
    <html>
        <body style="font-family: Arial; padding: 30px;">
            <h1>Nomad Booking Dashboard</h1>

            <table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse; width:100%;">
                <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Customer Response</th>
                    <th>Name</th>
                    <th>Guests</th>
                    <th>Start Time</th>
                    <th>Warnings</th>
                    <th>Actions</th>
                </tr>
                {rows}
            </table>
        </body>
    </html>
    """