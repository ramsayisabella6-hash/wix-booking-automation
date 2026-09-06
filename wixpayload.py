"""
Translates a Wix Automations "form submitted" webhook into the flat shape
that BookingRequest in main.py expects.

Why this file exists
--------------------
Wix Forms V2 is a single sealed element, so there is no way to read its
fields from Velo page code. The data instead arrives from a Wix Automation
as a webhook, and it does NOT look like the flat JSON the backend was
originally written for. A real submission looks like this:

    {
      "data": {
        "field:first_name_abae": "Booking",
        "field:last_name_d97c": "Test",
        "field:email_5139": "someone@example.com",
        "field:phone_4c77": "+61424048281",
        "field:reservation_number_of_people": 4,
        "field:date_picker_d4fa": "2026-09-12",
        "field:time_006f": "16:30:00",
        "field:long_answer_3524": "Birthday drinks",
        "submissions": [ {"label": "First name", "value": "Booking"}, ... ],
        "contact": {"name": {"first": "Booking", "last": "Test"}, ...}
      }
    }

Three things about that shape drive the design here:

1. Everything is wrapped in "data".
2. Field keys carry a random suffix that Wix generates ("_abae", "_d4fa").
   These are NOT stable - editing the form can change them. We saw this
   happen live: replacing the Time text box with a time picker changed the
   key from "field:time" to "field:time_006f".
3. The same values appear a second time in the "submissions" list, keyed by
   the human-readable label shown on the form.

So every value is looked up twice: first by field-key prefix (ignoring the
random suffix), then by label as a fallback. If Wix changes a key again,
the label lookup keeps the booking flowing.

Date and time arrive as two separate values and are combined here into the
single naive Sydney datetime the rest of the app assumes.
"""

from datetime import datetime

# Tried in order. The date picker sends "2026-09-12"; the rest are fallbacks
# in case the field is ever changed to free text.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
)

# The time picker sends "16:30:00". The remainder cover a free-text field
# so that a form change can never silently drop a booking.
TIME_FORMATS = (
    "%H:%M:%S",
    "%H:%M",
    "%I:%M:%S%p",
    "%I:%M%p",
    "%I%p",
)

EMPTY = (None, "", [], {})


def _unwrap(payload):
    """Wix nests everything under 'data'. Tolerate it being absent."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _field_map(data):
    """{'first_name_abae': 'Booking', ...} - the 'field:' prefix stripped."""
    out = {}
    for key, value in data.items():
        if key.startswith("field:") and len(key) > len("field:"):
            out[key[len("field:"):]] = value
    return out


def _label_map(data):
    """{'first name': 'Booking', ...} from the submissions list."""
    out = {}
    for item in data.get("submissions") or []:
        if isinstance(item, dict) and item.get("label"):
            out[str(item["label"]).strip().lower()] = item.get("value")
    return out


def _pick(fields, labels, key_prefixes, label_keywords):
    """Find one value: by field-key prefix first, then by form label."""
    for prefix in key_prefixes:
        for key, value in fields.items():
            if key.startswith(prefix) and value not in EMPTY:
                return value

    for keyword in label_keywords:
        for label, value in labels.items():
            if keyword in label and value not in EMPTY:
                return value

    return None


def _parse_date(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Epoch milliseconds, just in case Wix ever sends that instead.
        return datetime.utcfromtimestamp(value / 1000).date()

    text = str(value).strip()

    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Could not understand the booking date: {value!r}")


def _parse_time(value):
    text = str(value).strip().lower().replace(".", "")
    compact = text.replace(" ", "")

    for candidate in (text, compact):
        for fmt in TIME_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).time()
            except ValueError:
                continue

    raise ValueError(f"Could not understand the booking time: {value!r}")


def _parse_guests(value):
    if isinstance(value, bool):
        raise ValueError(f"Could not understand the guest count: {value!r}")

    if isinstance(value, (int, float)):
        return int(value)

    digits = "".join(c for c in str(value) if c.isdigit())

    if not digits:
        raise ValueError(f"Could not understand the guest count: {value!r}")

    return int(digits)


def parse_wix_payload(payload):
    """
    Returns a dict with exactly the keys BookingRequest wants:
    name, email, phone, guests, start_time, details.

    Raises ValueError with a plain-English message if anything essential
    is missing or unreadable, so the caller can alert staff rather than
    losing the booking silently.
    """
    data = _unwrap(payload)
    fields = _field_map(data)
    labels = _label_map(data)

    contact = data.get("contact") or {}
    contact_name = contact.get("name") or {}

    first = (
        _pick(fields, labels, ("first_name",), ("first name",))
        or contact_name.get("first")
        or ""
    )
    last = (
        _pick(fields, labels, ("last_name",), ("last name",))
        or contact_name.get("last")
        or ""
    )
    name = " ".join(part for part in (str(first).strip(), str(last).strip()) if part)

    email = (
        _pick(fields, labels, ("email",), ("email",))
        or contact.get("email")
    )

    phone = (
        _pick(fields, labels, ("phone",), ("phone",))
        or contact.get("phone")
    )

    guests_raw = _pick(
        fields,
        labels,
        ("reservation_number", "number_of_people", "guests"),
        ("people", "guests"),
    )

    date_raw = _pick(fields, labels, ("date_picker", "date"), ("date",))
    time_raw = _pick(fields, labels, ("time",), ("time",))

    details = _pick(
        fields,
        labels,
        ("long_answer", "message", "details"),
        ("message", "details", "request"),
    )

    missing = [
        label
        for label, value in (
            ("name", name),
            ("email", email),
            ("guest count", guests_raw),
            ("date", date_raw),
            ("time", time_raw),
        )
        if value in EMPTY
    ]

    if missing:
        raise ValueError("Missing required field(s): " + ", ".join(missing))

    start_time = datetime.combine(_parse_date(date_raw), _parse_time(time_raw))

    return {
        "name": name,
        "email": str(email).strip(),
        "phone": str(phone).strip() if phone else None,
        "guests": _parse_guests(guests_raw),
        "start_time": start_time,
        "details": str(details).strip() if details else "",
    }