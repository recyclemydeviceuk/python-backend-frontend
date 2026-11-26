from beanie import Document
from pydantic import Field
from typing import Optional, Any
from datetime import datetime


class ApiLog(Document):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_ip: str
    endpoint: str
    method: str
    status_code: int
    success: bool
    order_number: Optional[str] = None
    payload: Optional[str] = None
    error: Optional[str] = None
    response_time: Optional[int] = None
    # Whether source_ip matched an active IP whitelist entry at request time.
    # RECORDED ONLY — a False here does NOT mean the request was blocked;
    # the gateway deliberately does not enforce IP restrictions.
    ip_whitelisted: Optional[bool] = None
    partner_name: Optional[str] = None
    # Masked X-Partner-Key as received (prefix + last 4 chars, never the whole
    # key) and whether it matched an active partner. Lets us answer a partner's
    # "we sent the key ending in …f79 — what did you see?" without storing the
    # secret. None when no key was sent.
    partner_key_hint: Optional[str] = None
    partner_key_matched: Optional[bool] = None
    # Per-request reference, also returned to the caller in the X-Request-ID
    # response header (and in the body of a 500), so a partner can quote it.
    reference: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "apilogs"
        indexes = [
            [("timestamp", -1)],
            [("source_ip", 1), ("timestamp", -1)],
            "success",
            "order_number"
        ]
