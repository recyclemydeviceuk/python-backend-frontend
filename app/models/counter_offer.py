from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId


class DeviceImage(BaseModel):
    url: str
    key: str
    uploaded_at: datetime


class CounterOffer(Document):
    order_id: str
    order_number: str
    original_price: float
    revised_price: float
    reason: str
    device_images: List[DeviceImage] = Field(default_factory=list)
    status: str = "PENDING"
    customer_response: Optional[str] = None
    customer_feedback: Optional[str] = None
    responded_at: Optional[datetime] = None
    expires_at: datetime
    review_token: str
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def is_expired(self) -> bool:
        # expires_at is usually naive UTC, but documents written by other
        # services may carry a timezone — comparing naive vs aware raises
        # TypeError (a 500 for the customer), so match whichever form we get.
        if self.expires_at.tzinfo is not None:
            return datetime.now(timezone.utc) > self.expires_at
        return datetime.utcnow() > self.expires_at

    class Settings:
        name = "counteroffers"
        indexes = [
            "order_id",
            "order_number",
            "status",
            "expires_at",
            [("review_token", 1)]
        ]
