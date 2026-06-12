from datetime import time

OPENING_HOURS = {
    0: None,  # Monday closed
    1: None,  # Tuesday closed
    2: {"open": time(17, 0), "close": time(20, 0)},  # Wednesday
    3: {"open": time(17, 0), "close": time(20, 0)},  # Thursday
    4: {"open": time(12, 0), "close": time(0, 0)},   # Friday
    5: {"open": time(12, 0), "close": time(0, 0)},   # Saturday
    6: {"open": time(12, 0), "close": time(18, 0)},  # Sunday
}

MAX_GUESTS_BEFORE_ALERT = 100
MIN_GUESTS = 0


def is_within_opening_hours(start_time):
    day = start_time.weekday()
    hours = OPENING_HOURS.get(day)

    if hours is None:
        return False

    booking_time = start_time.time()
    open_time = hours["open"]
    close_time = hours["close"]

    if close_time == time(0, 0):
        return booking_time >= open_time

    return open_time <= booking_time <= close_time


def validate_booking_rules(booking):
    if booking.guests < MIN_GUESTS:
        return False, f"Minimum {MIN_GUESTS} guests required"

    if not is_within_opening_hours(booking.start_time):
        return False, "Booking is outside opening hours"

    return True, "Booking is valid"