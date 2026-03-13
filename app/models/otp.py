from beanie import Document
from pydantic import Field
from datetime import datetime


class OTP(Document):
    email: str
    code: str
    expires_at: datetime
    is_used: bool = False
    attempts: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "otps"
        indexes = [
            [("email", 1), ("created_at", -1)],
            "expires_at"
        ]
