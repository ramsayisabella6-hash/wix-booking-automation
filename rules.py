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


def get_booking_warnings(booking):
    """
    IMPORTANT: booking.start_time must already be a *naive* datetime
    representing Sydney local wall-clock time (see normalize_to_sydney
    in main.py, which does this before rules are checked). If you ever
    call this function with a raw/unnormalized datetime, these checks
    will silently be wrong on any server not physically located in Sydney.
    """
    warnings = []

    if booking.guests < MIN_GUESTS:
        warnings.append(
            f"Minimum guests is {MIN_GUESTS}, but booking has {booking.guests}."
        )

    day = booking.start_time.weekday()
    hours = OPENING_HOURS.get(day)

    if hours is None:
        warnings.append("Booking is on a closed day.")
    else:
        booking_time = booking.start_time.time()
        open_time = hours["open"]
        close_time = hours["close"]

        if booking_time < open_time:
            warnings.append("Booking is before opening time.")

        if booking_time > close_time:
            warnings.append("Booking is after closing time.")

        close_datetime = datetime.combine(
            booking.start_time.date(),
            close_time,
        )
        booking_datetime = booking.start_time.replace(tzinfo=None)

        time_until_close = close_datetime - booking_datetime

        if timedelta(0) <= time_until_close <= timedelta(
            minutes=MINUTES_BEFORE_CLOSE_WARNING
        ):
            warnings.append("Booking is too close to closing time.")

    # Compare against the current time in Sydney, not server-local time
    # (Render's servers run in UTC, which would otherwise throw this off
    # by 10-11 hours).
    now_sydney_naive = datetime.now(SYDNEY_TZ).replace(tzinfo=None)
    booking_naive = booking.start_time.replace(tzinfo=None)

    if booking_naive - now_sydney_naive < timedelta(hours=MIN_HOURS_NOTICE):
        warnings.append(
            f"Booking is less than {MIN_HOURS_NOTICE} hours away."
        )

    return warnings


def validate_booking_rules(booking):
    warnings = get_booking_warnings(booking)

    if warnings:
        return False, "\n".join(warnings)

    return True, "Booking meets current rules."