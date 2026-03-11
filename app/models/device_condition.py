from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class DeviceCondition(Document):
    name: str
    value: str
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "deviceconditions"
        indexes = ["name", "value", "sort_order", "is_active"]
