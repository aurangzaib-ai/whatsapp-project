from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import json
import os

app = FastAPI()

# =====================================================
# CONFIG (ENV VARIABLES)
# =====================================================
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_verify_token")

# =====================================================
# WEBHOOK VERIFICATION (META REQUIREMENT)
# =====================================================
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully")
        return PlainTextResponse(challenge, status_code=200)

    print("❌ Webhook verification failed")
    return PlainTextResponse("Verification failed", status_code=403)

# =====================================================
# RECEIVE INCOMING MESSAGES / EVENTS
# =====================================================
@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()

    # Debug print (optional)
    print("📩 Incoming Webhook Payload:")
    print(json.dumps(payload, indent=2))

    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # ---------------------------------------------
        # Incoming Messages
        # ---------------------------------------------
        messages = value.get("messages")
        if messages:
            msg = messages[0]
            from_number = msg.get("from")

            # TEXT MESSAGE
            if msg.get("type") == "text":
                text = msg["text"]["body"]
                print(f"📝 Text from {from_number}: {text}")

            # BUTTON REPLY
            if msg.get("type") == "button":
                button_text = msg["button"]["text"]
                print(f"🔘 Button clicked by {from_number}: {button_text}")

        # ---------------------------------------------
        # STATUS UPDATES (DELIVERED / READ)
        # ---------------------------------------------
        statuses = value.get("statuses")
        if statuses:
            status = statuses[0]
            print(
                f"📊 Message ID {status['id']} status: {status['status']}"
            )

    except Exception as e:
        print("⚠️ Error processing webhook:", str(e))

    return {"status": "received"}
