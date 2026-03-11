from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class Brand(Document):
    name: str
    logo: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "brands"
        indexes = ["name", "sort_order", "is_active"]
