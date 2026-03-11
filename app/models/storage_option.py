from beanie import Document
from pydantic import Field
from datetime import datetime


class StorageOption(Document):
    name: str
    value: str
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "storageoptions"
        indexes = ["name", "sort_order", "is_active"]
