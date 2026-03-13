from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime
from app.config.constants import AdminRole


class Admin(Document):
    email: str
    username: str
    name: str = ""  # Added for frontend compatibility
    role: AdminRole = AdminRole.ADMIN
    is_active: bool = True
    last_login: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "admins"
        indexes = ["email"]
