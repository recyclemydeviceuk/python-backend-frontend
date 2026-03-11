from beanie import Document
from pydantic import Field
from datetime import datetime


class OTP(Document):
    email: str
    code: str
    expires_at: datetime
    used: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "otps"
        indexes = [
            [("email", 1), ("created_at", -1)],
            "expires_at"
        ]
