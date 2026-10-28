"""
Busy-day blocking.

The owner/manager opens /blocked-dates?secret=<APPROVAL_SECRET>, picks a date
(a home game, an event, a public holiday...) and from then on EVERY booking
request for that day is declined automatically - the customer gets the usual
"unable to accept your booking" email and staff get the usual Telegram alert.

Bookings that already exist for that day are NOT cancelled; the page warns
you if there are any so you can deal with them by hand.

This file is self-contained: it defines its own database table and its own
set of pages, so main.py only needs a couple of lines to switch it on.
"""

import html
import os
import secrets
from datetime import datetime, time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Column, Date, DateTime, Integer, String

from database import Base, BookingRecord, SessionLocal, engine

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

router = APIRouter()


class BlockedDate(Base):
    __tablename__ = "blocked_dates"

    id = Column(Integer, primary_key=True, index=True)
    blocked_date = Column(Date, nullable=False, unique=True, index=True)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


# Create just this one table if it doesn't exist yet. Safe to run on every
# start-up, and it never touches the bookings table.
BlockedDate.__table__.create(bind=engine, checkfirst=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_blocked_reason(db, day):
    """
    None  -> the day is open for bookings.
    text  -> the day is blocked (text is the reason, possibly empty).
    """
    row = db.query(BlockedDate).filter(BlockedDate.blocked_date == day).first()

    if row is None:
        return None

    return row.reason or ""


def list_upcoming_blocked_dates(db, from_day):
    return (
        db.query(BlockedDate)
        .filter(BlockedDate.blocked_date >= from_day)
        .order_by(BlockedDate.blocked_date.asc())
        .all()
    )


def add_blocked_date(db, day, reason=""):
    """Returns True if newly blocked, False if it was already blocked."""
    existing = db.query(BlockedDate).filter(BlockedDate.blocked_date == day).first()

    if existing:
        if reason:
            existing.reason = reason
            db.commit()
        return False

    db.add(BlockedDate(blocked_date=day, reason=reason))
    db.commit()
    return True


def remove_blocked_date(db, block_id):
    row = db.query(BlockedDate).filter(BlockedDate.id == block_id).first()

    if row is None:
        return False

    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _secret_ok(provided):
    expected = os.getenv("APPROVAL_SECRET")
    return bool(expected) and bool(provided) and secrets.compare_digest(str(provided), expected)


def _back_to_page(secret, message):
    return RedirectResponse(
        url=f"/blocked-dates?secret={quote(secret, safe='')}&message={quote(message, safe='')}",
        status_code=303,
    )


def render_blocked_dates_page(secret, rows, message=None, using_sqlite=False):
    """rows is a list of (id, date, reason)."""
    safe_secret = quote(secret, safe="")

    warning_html = ""
    if using_sqlite:
        warning_html = (
            '<div style="background:#fff3cd; border:1px solid #e0a800; padding:15px; margin-bottom:20px;">'
            "<b>Warning: blocked days are not being saved permanently.</b> "
            "The app is currently using a temporary database, so every day listed below "
            "will be forgotten the next time the app restarts or is updated. "
            "Move the app to a permanent (Postgres) database before relying on this page."
            "</div>"
        )

    message_html = ""
    if message:
        message_html = (
            '<p style="background:#e7f5e7; border:1px solid #9bd19b; padding:12px;">'
            f"{html.escape(message)}</p>"
        )

    table_rows = ""
    for block_id, day, reason in rows:
        table_rows += (
            "<tr>"
            f"<td>{day.strftime('%A %d %B %Y')}</td>"
            f"<td>{html.escape(reason or '')}</td>"
            f'<td><a href="/blocked-dates/remove/{block_id}?secret={safe_secret}" '
            "onclick=\"return confirm('Open this day for bookings again?');\">Remove</a></td>"
            "</tr>"
        )

    if not table_rows:
        table_rows = '<tr><td colspan="3">No upcoming days are blocked.</td></tr>'

    return f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Blocked days</title>
        </head>
        <body style="font-family: Arial; padding: 30px; max-width: 800px; margin: auto;">
            <h1>Blocked days</h1>

            <p>
                Block off a busy day (a home game, an event, a public holiday) and every
                booking request for that day is declined automatically. The customer gets
                the usual "unable to accept your booking" email and you get a Telegram alert.
                Bookings that were already made for that day are not touched.
            </p>

            {warning_html}
            {message_html}

            <h2>Block a new day</h2>
            <form method="get" action="/blocked-dates/add">
                <input type="hidden" name="secret" value="{html.escape(secret, quote=True)}">

                <p>
                    <label>Date<br>
                    <input type="date" name="blocked_date" required
                           style="font-size:18px; padding:8px;"></label>
                </p>

                <p>
                    <label>Reason (only staff see this)<br>
                    <input type="text" name="reason" maxlength="100"
                           placeholder="e.g. Manly home game"
                           style="font-size:18px; padding:8px; width:100%; box-sizing:border-box;"></label>
                </p>

                <button type="submit"
                        style="font-size:20px; padding:12px 20px; background:#b00020; color:white; border:none; border-radius:8px;">
                    Block this day
                </button>
            </form>

            <h2>Upcoming blocked days</h2>
            <table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse; width:100%;">
                <tr>
                    <th align="left">Date</th>
                    <th align="left">Reason</th>
                    <th></th>
                </tr>
                {table_rows}
            </table>

            <p><a href="/bookings?secret={safe_secret}">Back to bookings dashboard</a></p>
        </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/blocked-dates", response_class=HTMLResponse)
def blocked_dates_dashboard(secret: str, message: str | None = None):
    if not _secret_ok(secret):
        return "<h1>Unauthorized</h1>"

    db = SessionLocal()
    try:
        today = datetime.now(SYDNEY_TZ).date()
        rows = [
            (row.id, row.blocked_date, row.reason or "")
            for row in list_upcoming_blocked_dates(db, today)
        ]
    finally:
        db.close()

    using_sqlite = os.getenv("DATABASE_URL", "sqlite:///bookings.db").startswith("sqlite")

    return render_blocked_dates_page(secret, rows, message, using_sqlite)


@router.get("/blocked-dates/add")
def add_blocked_date_route(secret: str, blocked_date: str, reason: str = ""):
    if not _secret_ok(secret):
        return HTMLResponse("<h1>Unauthorized</h1>")

    try:
        day = datetime.strptime(blocked_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return _back_to_page(secret, "That date wasn't understood - please choose it from the date box.")

    if day < datetime.now(SYDNEY_TZ).date():
        return _back_to_page(secret, "That date has already passed, so nothing was blocked.")

    db = SessionLocal()
    try:
        added = add_blocked_date(db, day, reason.strip()[:100])

        existing_bookings = (
            db.query(BookingRecord)
            .filter(BookingRecord.status.in_(["approved", "pending"]))
            .filter(BookingRecord.start_time >= datetime.combine(day, time.min))
            .filter(BookingRecord.start_time <= datetime.combine(day, time.max))
            .count()
        )
    finally:
        db.close()

    pretty = day.strftime("%A %d %B %Y")

    if added:
        message = f"Blocked {pretty}. New booking requests for that day will now be declined automatically."
    else:
        message = f"{pretty} was already blocked."

    if existing_bookings:
        message += (
            f" Note: {existing_bookings} booking(s) already exist on that day. "
            "Blocking does not cancel them - please check the calendar."
        )

    return _back_to_page(secret, message)


@router.get("/blocked-dates/remove/{block_id}")
def remove_blocked_date_route(block_id: int, secret: str):
    if not _secret_ok(secret):
        return HTMLResponse("<h1>Unauthorized</h1>")

    db = SessionLocal()
    try:
        removed = remove_blocked_date(db, block_id)
    finally:
        db.close()

    if removed:
        return _back_to_page(secret, "That day is open for bookings again.")

    return _back_to_page(secret, "That blocked day had already been removed.")