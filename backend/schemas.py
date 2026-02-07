from __future__ import annotations

from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field


# ----------------------------
# MEMBERS
# ----------------------------
class MemberCreate(BaseModel):
    phone_number: str = Field(..., min_length=7, max_length=32)
    status: str = "active"
    city: Optional[str] = None
    plan: Optional[str] = None
    is_opted_in: bool = True
    expiry_date: Optional[date] = None


class MemberUpdate(BaseModel):
    status: Optional[str] = None
    city: Optional[str] = None
    plan: Optional[str] = None
    is_opted_in: Optional[bool] = None
    expiry_date: Optional[date] = None


class MemberResponse(BaseModel):
    id: int
    phone_number: str
    status: str
    city: Optional[str] = None
    plan: Optional[str] = None
    is_opted_in: bool
    expiry_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ----------------------------
# CAMPAIGNS
# ----------------------------
class CampaignResponse(BaseModel):
    id: int
    name: str
    template_name: str
    description: Optional[str] = None

    target_count: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int = 0

    status: str = "queued"
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    status_filter: Optional[str] = None
    plan_filter: Optional[str] = None
    city_filter: Optional[str] = None
    expiry_days_filter: Optional[int] = None

    class Config:
        from_attributes = True


# ----------------------------
# SEND TEMPLATE
# ----------------------------
class SendTemplateRequest(BaseModel):
    campaign_name: str = Field(..., min_length=1)
    template_name: str = Field(..., min_length=1)  # e.g. hello_world
    description: Optional[str] = None

    status_filter: Optional[str] = None
    plan_filter: Optional[str] = None
    city_filter: Optional[str] = None
    expiry_days_filter: Optional[int] = None

    # session creds (UI se aate hain)
    access_token: str = Field(..., min_length=1)
    phone_number_id: str = Field(..., min_length=1)

    language_code: str = "en_US"

    # ✅ Test mode
    test_numbers: Optional[List[str]] = None

    # ✅ One-click dispatch
    auto_dispatch: bool = True


class SendTemplateResponse(BaseModel):
    campaign_id: int
    message: str
    total_recipients: int
    queued_count: int
    dispatch_started: bool = False
