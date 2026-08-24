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
