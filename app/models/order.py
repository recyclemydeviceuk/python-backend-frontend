from beanie import Document
from pydantic import Field, BaseModel, ConfigDict, field_validator
from typing import Any, Optional
from datetime import datetime


class PayoutDetails(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_name: Optional[str] = Field(None, alias="accountName")
    account_number: Optional[str] = Field(None, alias="accountNumber")
    sort_code: Optional[str] = Field(None, alias="sortCode")


class CounterOfferEmbed(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    has_counter_offer: bool = Field(False, alias="hasCounterOffer")
    latest_offer_id: Optional[str] = Field(None, alias="latestOfferId")
    status: Optional[str] = None


class Order(Document):
    model_config = ConfigDict(populate_by_name=True)

    order_number: str = Field(..., alias="orderNumber")
    source: str
    status: str = "PENDING"
    customer_name: str = Field(..., alias="customerName")
    customer_phone: str = Field(..., alias="customerPhone")
    customer_email: Optional[str] = Field(None, alias="customerEmail")
    customer_address: str = Field(..., alias="customerAddress")
    postcode: Optional[str] = None
    device_id: Optional[str] = Field(None, alias="deviceId")
    device_name: str = Field(..., alias="deviceName")
    network: str
    device_grade: str = Field(..., alias="deviceGrade")
    storage: str
    offered_price: float = Field(..., alias="offeredPrice")
    final_price: Optional[float] = Field(None, alias="finalPrice")
    counter_offer: CounterOfferEmbed = Field(default_factory=CounterOfferEmbed, alias="counterOffer")
    postage_method: str = Field(..., alias="postageMethod")
    tracking_number: Optional[str] = Field(None, alias="trackingNumber")
    payment_method: str = Field("bank", alias="paymentMethod")
    payment_status: str = Field("PENDING", alias="paymentStatus")
    payout_details: Optional[PayoutDetails] = Field(None, alias="payoutDetails")
    transaction_id: Optional[str] = Field(None, alias="transactionId")
    partner_name: Optional[str] = Field(None, alias="partnerName")
    notes: Optional[str] = None
    admin_notes: Optional[str] = Field(None, alias="adminNotes")
    price_revision_reason: Optional[str] = Field(None, alias="priceRevisionReason")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    @field_validator("device_id", mode="before")
    @classmethod
    def coerce_device_id(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)

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
