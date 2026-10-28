"""
/wix-enquiry - an optional second doorway for the wholesale / private label
forms.

You do NOT need this for the Telegram alerts to work: /wix-booking now
recognises those forms by name on its own. It exists so that a Wix
Automation pointed straight at it also works:

    /wix-enquiry?type=wholesale&secret=...
    /wix-enquiry?type=private-label&secret=...

Nothing is saved, no calendar event is made and no email is sent. It only
posts the short Telegram heads-up (the full submission already reaches the
venue manager by email from Wix itself).
"""

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query

from notification_service import notify_enquiry

router = APIRouter()


def _check_webhook_secret(provided):
    expected = os.getenv("WIX_WEBHOOK_SECRET")

    if not expected:
        raise RuntimeError("WIX_WEBHOOK_SECRET environment variable must be set")

    if not provided or not secrets.compare_digest(str(provided), expected):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/wix-enquiry")
def receive_enquiry(
    payload: dict,
    enquiry_type: Annotated[str, Query(alias="type")],
    secret: str | None = None,
    x_webhook_secret: str | None = Header(default=None),
):
    _check_webhook_secret(x_webhook_secret or secret)

    notify_enquiry(enquiry_type)

    return {"status": "received", "type": enquiry_type}