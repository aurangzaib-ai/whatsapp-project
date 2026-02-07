"""
Utility helpers:
- phone validation
- CSV parsing
- webhook parsing (status + button payload)
- stop command detection
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional


E164_RE = re.compile(r"^\+?[1-9]\d{7,15}$")


def validate_phone_number(phone: str) -> bool:
    if not phone:
        return False
    phone = phone.strip()
    return bool(E164_RE.match(phone))


def is_stop_command(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return t in {"stop", "unsubscribe", "cancel", "end", "quit"}


def parse_csv_members(csv_content: str) -> List[Dict[str, Any]]:
    """
    Expect CSV columns (flexible):
      phone_number (required)
      full_name, email, status, city, plan, expiry_date, is_opted_in
    expiry_date accepted formats: YYYY-MM-DD, DD/MM/YYYY
    is_opted_in accepted: true/false/1/0/yes/no
    """
    f = io.StringIO(csv_content)
    reader = csv.DictReader(f)

    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    rows: List[Dict[str, Any]] = []

    for row in reader:
        phone = (row.get("phone_number") or row.get("phone") or row.get("msisdn") or "").strip()
        if not phone:
            continue
        if not validate_phone_number(phone):
            # skip invalid numbers
            continue

        expiry_raw = (row.get("expiry_date") or row.get("expiry") or "").strip()
        expiry_val: Optional[date] = None
        if expiry_raw:
            expiry_val = _parse_date(expiry_raw)

        opted_raw = (row.get("is_opted_in") or row.get("opted_in") or "").strip().lower()
        is_opted_in = True
        if opted_raw:
            is_opted_in = opted_raw in {"1", "true", "yes", "y"}

        rows.append(
            {
                "phone_number": phone,
                "full_name": (row.get("full_name") or row.get("name") or "").strip() or None,
                "email": (row.get("email") or "").strip() or None,
                "status": (row.get("status") or "").strip() or None,
                "city": (row.get("city") or "").strip() or None,
                "plan": (row.get("plan") or "").strip() or None,
                "expiry_date": expiry_val,
                "is_opted_in": is_opted_in,
            }
        )

    return rows


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def extract_message_status(status_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    WhatsApp webhook status object:
      {
        "id": "...",
        "status": "sent|delivered|read|failed",
        "timestamp": "...",
        "errors": [...]
      }
    """
    if not status_data:
        return None

    message_id = status_data.get("id")
    status = status_data.get("status")
    errors = status_data.get("errors")

    if not message_id or not status:
        return None

    err = None
    if isinstance(errors, list) and errors:
        err = errors[0]

    return {
        "whatsapp_message_id": message_id,
        "status": status,
        "error": err,
    }


def extract_button_payload(message_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Handle different button reply types:

    1) interactive.button_reply:
      "interactive": {"type":"button_reply","button_reply":{"id":"X","title":"Renew"}}

    2) interactive.list_reply:
      "interactive": {"type":"list_reply","list_reply":{"id":"X","title":"Option"}}

    3) legacy "button":
      "button": {"payload":"X","text":"Renew"}
    """
    if not message_data:
        return None

    interactive = message_data.get("interactive")
    if isinstance(interactive, dict):
        itype = interactive.get("type")
        if itype == "button_reply":
            br = interactive.get("button_reply") or {}
            return {
                "response_type": "button_reply",
                "button_id": str(br.get("id") or ""),
                "button_title": str(br.get("title") or ""),
            }
        if itype == "list_reply":
            lr = interactive.get("list_reply") or {}
            return {
                "response_type": "list_reply",
                "button_id": str(lr.get("id") or ""),
                "button_title": str(lr.get("title") or ""),
            }

    button = message_data.get("button")
    if isinstance(button, dict):
        return {
            "response_type": "button",
            "button_id": str(button.get("payload") or ""),
            "button_title": str(button.get("text") or ""),
        }

    return None
