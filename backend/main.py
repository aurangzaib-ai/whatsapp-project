"""
FastAPI backend for WhatsApp Business API Notification System

Design:
- One-way notifications using approved templates
- Webhook receiver for delivery statuses + button replies + STOP opt-out
- Access Token / Phone Number ID are provided per request (NOT stored)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    File,
    BackgroundTasks,
    Request,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from dotenv import load_dotenv
from pydantic import BaseModel

# ---- local imports (make sure these files exist) ----
from db import SessionLocal, init_db
import models
from schemas import (
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    CampaignResponse,
    SendTemplateRequest,
    SendTemplateResponse,
)
from whatsapp_client import get_whatsapp_client
import utils

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ----------------------------
# Environment
# ----------------------------
load_dotenv()
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "test_token")  # webhook verification only

# ----------------------------
# App lifespan
# ----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Application started")
    yield
    logger.info("Application shutting down...")

app = FastAPI(
    title="WhatsApp Notification System",
    description="One-way notification system with templates and webhooks",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------
# DB helpers
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session() -> Session:
    return SessionLocal()

# ============================
# WEBHOOK
# ============================

@app.get("/webhook")
async def webhook_get(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid mode")
    if hub_verify_token != VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return PlainTextResponse(hub_challenge or "")

@app.post("/webhook")
async def webhook_post(
    request: Request,
    background_tasks: BackgroundTasks,
):
    data = await request.json()

    try:
        if data.get("object") != "whatsapp_business_account":
            return {"status": "ok"}

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                for status in value.get("statuses", []) or []:
                    background_tasks.add_task(process_status_update_task, status)

                for message in value.get("messages", []) or []:
                    background_tasks.add_task(process_incoming_message_task, message)

        return {"status": "ok"}

    except Exception as e:
        logger.error("Webhook error: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}

def process_status_update_task(status_data: dict):
    db = get_db_session()
    try:
        process_status_update(db, status_data)
    finally:
        db.close()

def process_incoming_message_task(message_data: dict):
    db = get_db_session()
    try:
        process_incoming_message(db, message_data)
    finally:
        db.close()

def process_status_update(db: Session, status_data: dict):
    info = utils.extract_message_status(status_data)
    if not info:
        return

    msg_id = info.get("whatsapp_message_id")
    status = info.get("status")
    if not msg_id:
        return

    msg = db.query(models.Message).filter(models.Message.whatsapp_message_id == msg_id).first()
    if not msg:
        return

    now = datetime.utcnow()
    if status == "sent":
        msg.status = models.MessageStatus.SENT
        msg.sent_at = now
    elif status == "delivered":
        msg.status = models.MessageStatus.DELIVERED
        msg.delivered_at = now
        msg.campaign.delivered_count += 1
    elif status == "read":
        msg.status = models.MessageStatus.READ
        msg.read_at = now
        msg.campaign.read_count += 1
    elif status == "failed":
        msg.status = models.MessageStatus.FAILED
        msg.error_message = str(info.get("error"))
        msg.campaign.failed_count += 1

    db.commit()

def process_incoming_message(db: Session, message_data: dict):
    sender = message_data.get("from")
    if not sender:
        return

    member = db.query(models.Member).filter(models.Member.phone_number == sender).first()
    if not member:
        return

    text = (message_data.get("text") or {}).get("body", "") or ""
    if utils.is_stop_command(text):
        member.is_opted_in = False
        db.add(models.OptOut(member_id=member.id, phone_number=sender, reason="stop"))
        db.commit()
        return

    payload = utils.extract_button_payload(message_data)
    if not payload:
        return

    last_msg = (
        db.query(models.Message)
        .filter(models.Message.member_id == member.id)
        .order_by(desc(models.Message.created_at))
        .first()
    )
    if not last_msg:
        return

    db.add(
        models.Response(
            message_id=last_msg.id,
            member_id=member.id,
            campaign_id=last_msg.campaign_id,
            response_type=payload.get("response_type"),
            button_title=payload.get("button_title"),
            button_id=payload.get("button_id"),
            received_at=datetime.utcnow(),
        )
    )
    db.commit()

# ============================
# TEMPLATES (UI helper)
# ============================

@app.get("/templates")
async def list_templates():
    return {
        "templates": [
            {"template_name": "hello_world", "language_code": "en_US"},
        ]
    }

# ============================
# MEMBERS
# ============================

@app.get("/members", response_model=List[MemberResponse])
async def list_members(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    status: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    plan: Optional[str] = Query(None),
    opted_in: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.Member)
    if status:
        q = q.filter(models.Member.status == status)
    if city:
        q = q.filter(models.Member.city == city)
    if plan:
        q = q.filter(models.Member.plan == plan)
    if opted_in is not None:
        q = q.filter(models.Member.is_opted_in == opted_in)
    return q.offset(skip).limit(limit).all()

@app.post("/members", response_model=MemberResponse)
async def create_member(member: MemberCreate, db: Session = Depends(get_db)):
    if not utils.validate_phone_number(member.phone_number):
        raise HTTPException(status_code=400, detail="Invalid phone number")
    if db.query(models.Member).filter(models.Member.phone_number == member.phone_number).first():
        raise HTTPException(status_code=409, detail="Member exists")
    m = models.Member(**member.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m

@app.put("/members/{member_id}", response_model=MemberResponse)
async def update_member(member_id: int, update: MemberUpdate, db: Session = Depends(get_db)):
    m = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in update.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    m.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(m)
    return m

@app.post("/members/import")
async def import_members(file: UploadFile = File(...), db: Session = Depends(get_db)):
    csv = (await file.read()).decode("utf-8")
    rows = utils.parse_csv_members(csv)
    created = skipped = 0
    for r in rows:
        if db.query(models.Member).filter(models.Member.phone_number == r["phone_number"]).first():
            skipped += 1
            continue
        db.add(models.Member(**r))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "total": len(rows)}

# ============================
# CAMPAIGNS
# ============================

@app.post("/send-template", response_model=SendTemplateResponse)
async def create_campaign_and_queue(
    request: SendTemplateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    members = db.query(models.Member).filter(models.Member.is_opted_in == True).all()
    if not members:
        raise HTTPException(status_code=400, detail="No opted-in members")

    campaign = models.Campaign(
        name=request.campaign_name,
        template_name=request.template_name,
        description=request.description,
        target_count=len(members),
        status="queued",
    )
    db.add(campaign)
    db.flush()

    for m in members:
        db.add(
            models.Message(
                campaign_id=campaign.id,
                member_id=m.id,
                status=models.MessageStatus.QUEUED,
                template_name=request.template_name,
            )
        )
    db.commit()

    if request.auto_dispatch:
        background_tasks.add_task(
            send_campaign_messages_task,
            campaign.id,
            request.access_token,
            request.phone_number_id,
        )
        return SendTemplateResponse(
            campaign_id=campaign.id,
            message="Campaign created and dispatch started.",
            total_recipients=len(members),
            queued_count=len(members),
            dispatch_started=True,
        )

    return SendTemplateResponse(
        campaign_id=campaign.id,
        message="Campaign created and queued.",
        total_recipients=len(members),
        queued_count=len(members),
        dispatch_started=False,
    )

class DispatchCampaignRequest(BaseModel):
    access_token: str
    phone_number_id: str

@app.post("/campaigns/{campaign_id}/dispatch")
async def dispatch_campaign(
    campaign_id: int,
    body: DispatchCampaignRequest,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        send_campaign_messages_task,
        campaign_id,
        body.access_token,
        body.phone_number_id,
    )
    return {"status": "dispatch_started", "campaign_id": campaign_id}

def send_campaign_messages_task(campaign_id: int, access_token: str, phone_number_id: str):
    db = get_db_session()
    try:
        send_campaign_messages(db, campaign_id, access_token, phone_number_id)
    finally:
        db.close()

def send_campaign_messages(db: Session, campaign_id: int, access_token: str, phone_number_id: str):
    camp = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not camp:
        return

    camp.status = "sending"
    camp.sent_at = datetime.utcnow()
    db.commit()

    wa = get_whatsapp_client(access_token=access_token, phone_number_id=phone_number_id)

    msgs = (
        db.query(models.Message)
        .filter(
            and_(
                models.Message.campaign_id == campaign_id,
                models.Message.status == models.MessageStatus.QUEUED,
            )
        )
        .all()
    )

    for msg in msgs:
        try:
            res = wa.send_template_message_sync(
                recipient_phone=msg.member.phone_number,
                template_name=camp.template_name,
                template_params=None,
            )
            if res.get("success"):
                msg.status = models.MessageStatus.SENT
                msg.whatsapp_message_id = res.get("message_id")
                msg.sent_at = datetime.utcnow()
                camp.sent_count += 1
            else:
                msg.status = models.MessageStatus.FAILED
                msg.error_message = str(res.get("error"))
                camp.failed_count += 1
            db.commit()
        except Exception as e:
            msg.status = models.MessageStatus.FAILED
            msg.error_message = str(e)
            camp.failed_count += 1
            db.commit()

    camp.status = "sent"
    db.commit()

# ============================
# REPORTS / HEALTH
# ============================

@app.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.Campaign)
    if status:
        q = q.filter(models.Campaign.status == status)
    return q.order_by(desc(models.Campaign.created_at)).offset(skip).limit(limit).all()

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
