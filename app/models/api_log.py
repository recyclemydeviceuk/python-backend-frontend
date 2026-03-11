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
