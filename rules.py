from datetime import time, datetime, timedelta

OPENING_HOURS = {
    0: None,
    1: None,
    2: {"open": time(17, 0), "close": time(22, 0)},
    3: {"open": time(17, 0), "close": time(22, 0)},
    4: {"open": time(17, 0), "close": time(0, 0)},
    5: {"open": time(12, 0), "close": time(0, 0)},
    6: {"open": time(12, 0), "close": time(22, 0)},
}

MIN_GUESTS = 20
MIN_HOURS_NOTICE = 2
MINUTES_BEFORE_CLOSE_WARNING = 60


def get_booking_warnings(booking):
    warnings = []

    if booking.guests < MIN_GUESTS:
        warnings.append(f"Minimum guests is {MIN_GUESTS}, but booking has {booking.guests}.")

    day = booking.start_time.weekday()
    hours = OPENING_HOURS.get(day)

    if hours is None:
        warnings.append("Booking is on a closed day.")
    else:
        booking_time = booking.start_time.time()
        open_time = hours["open"]
        close_time = hours["close"]

        if close_time == time(0, 0):
            if booking_time < open_time:
                warnings.append("Booking is before opening time.")
        else:
            if booking_time < open_time:
                warnings.append("Booking is before opening time.")

            if booking_time > close_time:
                warnings.append("Booking is after closing time.")

            close_datetime = datetime.combine(booking.start_time.date(), close_time)
            booking_datetime = booking.start_time.replace(tzinfo=None)

            if close_datetime - booking_datetime <= timedelta(minutes=MINUTES_BEFORE_CLOSE_WARNING):
                warnings.append("Booking is too close to closing time.")

    now = datetime.now()
    booking_naive = booking.start_time.replace(tzinfo=None)

    if booking_naive - now < timedelta(hours=MIN_HOURS_NOTICE):
        warnings.append(f"Booking is less than {MIN_HOURS_NOTICE} hours away.")

    return warnings


def validate_booking_rules(booking):
    warnings = get_booking_warnings(booking)

    if warnings:
        return False, "\n".join(warnings)

    return True, "Booking meets current rules."