from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class OrderStatus(Document):
    name: str
    value: str
    color: str = "bg-gray-100 text-gray-700"
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "orderstatuses"
        indexes = ["name", "sort_order", "is_active"]
