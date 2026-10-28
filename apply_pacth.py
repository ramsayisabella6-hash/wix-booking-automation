"""
One-time helper. Adds the new features to your EXISTING main.py (and makes a
tiny safety tweak to database.py) without you editing anything by hand.

How to use it (from the project folder, in the VS Code terminal):

    python apply_patch.py

What it does:
  * saves a backup first  ->  main.py.bak  and  database.py.bak
  * finds the exact lines it needs; if it cannot find one (or finds it twice)
    it changes NOTHING in that file and tells you why
  * checks the edited file is valid Python before saving it
  * is safe to run twice - it skips anything already done
"""

import ast
import pathlib
import shutil
import sys


def load(path):
    raw = pathlib.Path(path).read_bytes().decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), eol


def save(path, text, eol):
    pathlib.Path(path).write_bytes(text.replace("\n", eol).encode("utf-8"))


def find_line(lines, wanted):
    """Index of the one line whose stripped text equals `wanted`, else None."""
    hits = [i for i, line in enumerate(lines) if line.strip() == wanted]
    return hits[0] if len(hits) == 1 else None


def indent_of(line):
    return line[: len(line) - len(line.lstrip())]


def insert_after(lines, anchor, new_lines, marker):
    """Insert new_lines after the anchor line, at the anchor's indentation."""
    if any(marker in line for line in lines):
        return "already done"

    i = find_line(lines, anchor)
    if i is None:
        return f"COULD NOT find exactly one line: {anchor}"

    pad = indent_of(lines[i])
    lines[i + 1:i + 1] = [(pad + t if t else "") for t in new_lines]
    return "done"


def replace_line(lines, anchor, new_lines, marker):
    """Replace the anchor line with new_lines, at the anchor's indentation."""
    if any(marker in line for line in lines):
        return "already done"

    i = find_line(lines, anchor)
    if i is None:
        return f"COULD NOT find exactly one line: {anchor}"

    pad = indent_of(lines[i])
    lines[i:i + 1] = [(pad + t if t else "") for t in new_lines]
    return "done"


def patch_main():
    path = "main.py"
    text, eol = load(path)
    lines = text.split("\n")
    results = []

    results.append((
        "1. imports",
        insert_after(
            lines,
            "from wix_payload import parse_wix_payload",
            [
                "from notification_service import handle_non_booking_form",
                "from blocked_dates import router as blocked_dates_router, get_blocked_reason",
                "from enquiries import router as enquiries_router",
            ],
            marker="handle_non_booking_form",
        ),
    ))

    results.append((
        "2. switch on the new pages",
        insert_after(
            lines,
            "create_tables()",
            [
                "app.include_router(blocked_dates_router)",
                "app.include_router(enquiries_router)",
            ],
            marker="app.include_router(blocked_dates_router)",
        ),
    ))

    results.append((
        "3. wholesale / private label / other forms",
        insert_after(
            lines,
            "check_webhook_secret(x_webhook_secret or secret)",
            [
                "",
                "# Wholesale, private label and any other NON-booking form must never",
                "# be treated as a booking: send the short Telegram heads-up and stop.",
                "non_booking_reply = handle_non_booking_form(payload)",
                "if non_booking_reply is not None:",
                "    return non_booking_reply",
            ],
            marker="non_booking_reply = handle_non_booking_form",
        ),
    ))

    results.append((
        "4. blocked busy days",
        replace_line(
            lines,
            'hard_stops = rule_result["hard_stops"]',
            [
                'hard_stops = list(rule_result["hard_stops"])',
                "",
                "# Days the owner/manager has blocked off on the Blocked days page.",
                "blocked_reason = get_blocked_reason(db, booking.start_time.date())",
                "if blocked_reason is not None:",
                "    hard_stops.append(",
                '        "Bookings are blocked on this date"',
                '        + (f" ({blocked_reason})." if blocked_reason else ".")',
                "    )",
            ],
            marker="get_blocked_reason(db,",
        ),
    ))

    results.append((
        "5. link on the bookings dashboard (optional)",
        replace_line(
            lines,
            "<h1>Nomad Booking Dashboard</h1>",
            [
                "<h1>Nomad Booking Dashboard</h1>",
                '<p><a href="/blocked-dates?secret={secret}">Manage blocked days</a></p>',
            ],
            marker="Manage blocked days",
        ),
    ))

    new_text = "\n".join(lines)

    failed = [name for name, outcome in results if outcome.startswith("COULD NOT")
              and not name.endswith("(optional)")]

    print("\nmain.py")
    for name, outcome in results:
        print(f"  {name}: {outcome}")

    if failed:
        print("\n  main.py was NOT changed, because a required line wasn't found.")
        print("  Send me a screenshot of this message and I'll fix it.")
        return False

    try:
        ast.parse(new_text)
    except SyntaxError as error:
        print(f"\n  main.py was NOT changed - the edited file wasn't valid Python ({error}).")
        return False

    if new_text != text:
        shutil.copyfile(path, path + ".bak")
        save(path, new_text, eol)
        print("  Saved. Backup kept as main.py.bak")
    else:
        print("  Nothing to change - already up to date.")

    return True


def patch_database():
    """
    Render's Postgres address starts 'postgres://' but the database library
    needs 'postgresql://'. This lets either work, so the later switch to a
    permanent database can't fail on that. No effect on the current setup.
    """
    path = "database.py"

    try:
        text, eol = load(path)
    except FileNotFoundError:
        print("\ndatabase.py not found - skipped.")
        return True

    lines = text.split("\n")

    outcome = insert_after(
        lines,
        'DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bookings.db")',
        [
            'if DATABASE_URL.startswith("postgres://"):',
            '    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)',
        ],
        marker='DATABASE_URL.startswith("postgres://")',
    )

    print("\ndatabase.py")
    print(f"  postgres address tweak: {outcome}")

    if outcome.startswith("COULD NOT"):
        print("  (optional - skipped. Only matters when you move to a permanent database.)")
        return True

    new_text = "\n".join(lines)

    try:
        ast.parse(new_text)
    except SyntaxError:
        print("  database.py was NOT changed (edited file wasn't valid Python).")
        return True

    if new_text != text:
        shutil.copyfile(path, path + ".bak")
        save(path, new_text, eol)
        print("  Saved. Backup kept as database.py.bak")

    return True


if __name__ == "__main__":
    if not pathlib.Path("main.py").exists():
        print("main.py not found. Open a terminal IN the project folder, then run this again.")
        sys.exit(1)

    ok = patch_main()
    patch_database()

    print("\nDone." if ok else "\nStopped.")
    sys.exit(0 if ok else 1)