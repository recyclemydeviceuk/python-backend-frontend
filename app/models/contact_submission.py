from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class ContactSubmission(Document):
    name: str
    email: str
    phone: Optional[str] = None
    subject: str
    message: str
    status: str = "new"
    source_ip: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "contactsubmissions"
        indexes = [
            [("status", 1), ("created_at", -1)],
            [("created_at", -1)]
        ]
