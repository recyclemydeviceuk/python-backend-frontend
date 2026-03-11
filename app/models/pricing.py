from beanie import Document
from pydantic import Field, field_validator
from bson import ObjectId
from typing import Optional, Union
from datetime import datetime


class Pricing(Document):
    device_id: Optional[str] = Field(None, alias="deviceId")
    device_name: Optional[str] = Field(None, alias="deviceName")
    network: str
    storage: str
    grade_new: float = Field(0, alias="gradeNew")
    grade_good: float = Field(0, alias="gradeGood")
    grade_broken: float = Field(0, alias="gradeBroken")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    
    @field_validator('device_id', mode='before')
    @classmethod
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Settings:
        name = "pricings"
        use_state_management = True
        validate_on_save = True
        indexes = [
            [("device_id", 1), ("network", 1), ("storage", 1)],
            "device_name",
            "network",
            "storage"
        ]

    class Config:
        populate_by_name = True
