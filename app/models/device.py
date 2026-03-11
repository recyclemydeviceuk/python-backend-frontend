from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional
from datetime import datetime


class Specifications(BaseModel):
    screen_size: Optional[str] = None
    processor: Optional[str] = None
    camera: Optional[str] = None
    battery: Optional[str] = None
    release_year: Optional[int] = None


class Device(Document):
    brand: str
    name: str
    full_name: Optional[str] = Field(None, alias="fullName")
    category: str
    image_url: Optional[str] = Field(None, alias="imageUrl")
    is_active: bool = Field(True, alias="isActive")
    specifications: Optional[Specifications] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    class Settings:
        name = "devices"
        use_state_management = True
        validate_on_save = True
        indexes = [
            [("brand", 1), ("name", 1)],
            "category",
            "is_active",
            [("created_at", -1)]
        ]

    class Config:
        populate_by_name = True
