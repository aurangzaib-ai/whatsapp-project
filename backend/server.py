# server.py
import os
import time
import json
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI(title="WhatsApp Webhook + Events Store")

VERIFY_TOKEN = os.getenv("WH_VERIFY_TOKEN", "CHANGE_ME_VERIFY_TOKEN")

# Simple in-memory store (OK for demo). Production: Redis/DB.
EVENTS: List[Dict[str, Any]] = []
MAX_EVENTS = 500


def push_event(event: Dict[str, Any]) -> None:
    event["_received_at"] = int(time.time())
    EVENTS.append(event)
    if len(EVENTS) > MAX_EVENTS:
        del EVENTS[: len(EVENTS) - MAX_EVENTS]


@app.get("/health")
def health():
    return {"ok": True, "events": len(EVENTS)}


# Meta webhook verify (GET)
@app.get("/webhook")
def verify_webhook(
    hub_mode: str = "",
    hub_verify_token: str = "",
    hub_challenge: str = "",
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


# Meta webhook events (POST)
@app.post("/webhook")
async def receive_webhook(req: Request):
    payload = await req.json()
    push_event(payload)
    return JSONResponse({"ok": True})


# Streamlit polls this for real-time UI
@app.get("/events")
def get_events(limit: int = 50):
    limit = max(1, min(limit, 200))
    return {"events": EVENTS[-limit:]}


# Optional: proxy send (so you can log outgoing + keep token off Streamlit if you want)
@app.post("/send")
async def send_message(body: Dict[str, Any]):
    """
    body:
      mode: "text" | "template"
      access_token
      phone_number_id
      to
      text (for text mode)
      template_name, language_code, variables(list[str]) (for template mode)
      api_version (default v20.0)
    """
    mode = body.get("mode", "text")
    token = body.get("access_token")
    phone_id = body.get("phone_number_id")
    to = str(body.get("to", "")).strip()
    api_version = body.get("api_version", "v20.0")

    if not token or not phone_id or not to:
        raise HTTPException(status_code=422, detail="Missing access_token / phone_number_id / to")

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if mode == "text":
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(status_code=422, detail="Missing text")
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }

    elif mode == "template":
        tname = str(body.get("template_name", "")).strip()
        lang = str(body.get("language_code", "en")).strip()
        if not tname:
            raise HTTPException(status_code=422, detail="Missing template_name")

        template_obj = {"name": tname, "language": {"code": lang}}

        variables = body.get("variables") or []
        if isinstance(variables, list) and any(str(v).strip() for v in variables):
            params = [{"type": "text", "text": str(v)} for v in variables if str(v).strip()]
            template_obj["components"] = [{"type": "body", "parameters": params}]

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template_obj,
        }
    else:
        raise HTTPException(status_code=422, detail="Invalid mode. Use text|template")

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    # store outgoing attempt as event (for UI timeline)
    push_event(
        {
            "type": "outgoing_attempt",
            "request": {"url": url, "payload": payload},
            "response": {"status_code": r.status_code, "data": data},
        }
    )

    return {"status_code": r.status_code, "data": data, "payload": payload}
