from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class IpWhitelist(Document):
    ip: str
    label: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "ipwhitelists"
        indexes = ["ip", "is_active"]
