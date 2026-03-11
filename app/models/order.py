from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional
from datetime import datetime


class PayoutDetails(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None


class CounterOfferEmbed(BaseModel):
    has_counter_offer: bool = False
    latest_offer_id: Optional[str] = None
    status: Optional[str] = None


class Order(Document):
    order_number: str
    source: str
    status: str = "PENDING"
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    customer_address: str
    postcode: Optional[str] = None
    device_id: Optional[str] = None
    device_name: str
    network: str
    device_grade: str
    storage: str
    offered_price: float
    final_price: Optional[float] = None
    counter_offer: CounterOfferEmbed = Field(default_factory=CounterOfferEmbed)
    postage_method: str
    tracking_number: Optional[str] = None
    payment_method: str = "bank"
    payment_status: str = "PENDING"
    payout_details: Optional[PayoutDetails] = None
    transaction_id: Optional[str] = None
    partner_name: Optional[str] = None
    notes: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "orders"
        indexes = [
            "order_number",
            [("status", 1), ("created_at", -1)],
            "source",
            "customer_email",
            "customer_phone",
            [("created_at", -1)]
        ]
