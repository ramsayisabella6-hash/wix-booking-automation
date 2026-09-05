from datetime import time, datetime, timedelta
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

OPENING_HOURS = {
    0: None,  # Monday
    1: None,  # Tuesday
    2: {"open": time(16, 0), "close": time(20, 0)},  # Wednesday
    3: {"open": time(16, 0), "close": time(20, 0)},  # Thursday
    4: {"open": time(12, 0), "close": time(21, 0)},  # Friday
    5: {"open": time(12, 0), "close": time(22, 0)},  # Saturday
    6: {"open": time(12, 0), "close": time(18, 0)},  # Sunday
}

MIN_GUESTS = 2
MIN_HOURS_NOTICE = 2
MINUTES_BEFORE_CLOSE_WARNING = 60


def get_booking_rule_result(booking):
    """
    IMPORTANT: booking.start_time must already be a *naive* datetime
    representing Sydney local wall-clock time (see normalize_to_sydney
    in main.py, which does this before rules are checked).

    Returns a dict with two separate lists:
      - "hard_stops": violations that should cause an automatic REJECTION
        (the booking is impossible - wrong day/time/notice - no amount of
        owner judgment changes that).
      - "soft_warnings": things that are still a *legitimate* booking but
        need a human to look at it (big group, near capacity, etc).
        These are combined with the guest/capacity checks in main.py.
    """
    hard_stops = []
    soft_warnings = []

    day = booking.start_time.weekday()
    hours = OPENING_HOURS.get(day)

    if hours is None:
        hard_stops.append("Booking is on a closed day.")
    else:
        booking_time = booking.start_time.time()
        open_time = hours["open"]
        close_time = hours["close"]

        if booking_time < open_time:
            hard_stops.append("Booking is before opening time.")

        if booking_time > close_time:
            hard_stops.append("Booking is after closing time.")

        close_datetime = datetime.combine(
            booking.start_time.date(),
            close_time,
        )
        booking_datetime = booking.start_time.replace(tzinfo=None)
        time_until_close = close_datetime - booking_datetime

        if timedelta(0) <= time_until_close <= timedelta(
            minutes=MINUTES_BEFORE_CLOSE_WARNING
        ):
            soft_warnings.append("Booking is within 1 hour of closing.")

    now_sydney_naive = datetime.now(SYDNEY_TZ).replace(tzinfo=None)
    booking_naive = booking.start_time.replace(tzinfo=None)

    if booking_naive - now_sydney_naive < timedelta(hours=MIN_HOURS_NOTICE):
        soft_warnings.append(
            f"Booking is less than {MIN_HOURS_NOTICE} hours away."
        )

    if booking.guests < MIN_GUESTS:
        hard_stops.append(
            f"Minimum guests is {MIN_GUESTS}, but booking has {booking.guests}."
        )

    return {"hard_stops": hard_stops, "soft_warnings": soft_warnings}
