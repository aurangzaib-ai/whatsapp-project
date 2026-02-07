"""
SQLAlchemy models for WhatsApp notification system.
"""

from __future__ import annotations

import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    Text,
    Enum,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from db import Base


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)

    phone_number = Column(String(32), unique=True, index=True, nullable=False)
    full_name = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)

    status = Column(String(50), nullable=True)   # e.g. active, expired
    city = Column(String(100), nullable=True)
    plan = Column(String(100), nullable=True)

    expiry_date = Column(Date, nullable=True)
    is_opted_in = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = relationship("Message", back_populates="member", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="member", cascade="all, delete-orphan")
    optouts = relationship("OptOut", back_populates="member", cascade="all, delete-orphan")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(200), nullable=False)
    template_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    target_count = Column(Integer, default=0, nullable=False)

    sent_count = Column(Integer, default=0, nullable=False)
    delivered_count = Column(Integer, default=0, nullable=False)
    read_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)

    # segmentation fields
    status_filter = Column(String(50), nullable=True)
    plan_filter = Column(String(100), nullable=True)
    city_filter = Column(String(100), nullable=True)
    expiry_days_filter = Column(Integer, nullable=True)

    status = Column(String(50), default="queued", nullable=False)  # queued, sending, sent, etc.

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)

    messages = relationship("Message", back_populates="campaign", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="campaign", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(MessageStatus), default=MessageStatus.QUEUED, nullable=False)

    template_name = Column(String(200), nullable=True)
    whatsapp_message_id = Column(String(200), nullable=True, index=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)

    campaign = relationship("Campaign", back_populates="messages")
    member = relationship("Member", back_populates="messages")
    responses = relationship("Response", back_populates="message", cascade="all, delete-orphan")


class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)

    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True)

    response_type = Column(String(50), nullable=True)  # button_reply, list_reply, button, etc.
    button_title = Column(String(255), nullable=True)
    button_id = Column(String(255), nullable=True)

    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    message = relationship("Message", back_populates="responses")
    member = relationship("Member", back_populates="responses")
    campaign = relationship("Campaign", back_populates="responses")


class OptOut(Base):
    __tablename__ = "optouts"

    id = Column(Integer, primary_key=True, index=True)

    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=True)
    phone_number = Column(String(32), index=True, nullable=False)

    reason = Column(String(100), nullable=True)  # stop, unsubscribe, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    member = relationship("Member", back_populates="optouts")
