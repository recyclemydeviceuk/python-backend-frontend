from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from app.config.constants import OrderStatus, OrderSource, DeviceGrade, PostageMethod, PaymentMethod, PaymentStatus
from app.utils import customer_validation as cv


class PayoutDetailsSchema(BaseModel):
    account_name: Optional[str] = Field(None, alias="accountName")
    account_number: Optional[str] = Field(None, alias="accountNumber")
    sort_code: Optional[str] = Field(None, alias="sortCode")

    class Config:
        populate_by_name = True


class CreatePayoutDetailsSchema(PayoutDetailsSchema):
    """Strict payout details for public order creation: 8-digit account
    number, 6-digit sort code, real-looking account name."""

    @field_validator("account_name")
    @classmethod
    def _account_name(cls, v):
        return cv.validate_name(v, "Account name") if v not in (None, "") else v

    @field_validator("account_number")
    @classmethod
    def _account_number(cls, v):
        return cv.validate_account_number(v) if v not in (None, "") else v

    @field_validator("sort_code")
    @classmethod
    def _sort_code(cls, v):
        return cv.validate_sort_code(v) if v not in (None, "") else v


class CreateOrderSchema(BaseModel):
    customer_name: str = Field(..., alias="customerName", max_length=cv.MAX_NAME)
    customer_phone: str = Field(..., alias="customerPhone", max_length=cv.MAX_PHONE_RAW)
    customer_email: Optional[EmailStr] = Field(None, alias="customerEmail", max_length=cv.MAX_EMAIL)
    customer_address: str = Field(..., alias="customerAddress", max_length=cv.MAX_ADDRESS)
    city: Optional[str] = Field(None, max_length=cv.MAX_CITY)
    postcode: Optional[str] = Field(None, max_length=cv.MAX_POSTCODE + 2)
    device_id: Optional[str] = Field(None, alias="deviceId", max_length=64)
    device_name: str = Field(..., alias="deviceName", max_length=120)
    network: str = Field(..., max_length=60)
    device_grade: DeviceGrade = Field(..., alias="deviceGrade")
    storage: str = Field(..., max_length=30)
    offered_price: float = Field(..., alias="offeredPrice", ge=0, le=100000)
    postage_method: PostageMethod = Field(..., alias="postageMethod")
    payout_details: Optional[CreatePayoutDetailsSchema] = Field(None, alias="payoutDetails")
    notes: Optional[str] = Field(None, max_length=500)

    class Config:
        populate_by_name = True

    # Same rules as the website form (app/utils/customer_validation.py) so a
    # junk order can't come in through the JSON endpoint either.
    @field_validator("customer_name")
    @classmethod
    def _customer_name(cls, v):
        return cv.validate_name(v, "Name")

    @field_validator("customer_phone")
    @classmethod
    def _customer_phone(cls, v):
        return cv.validate_phone(v)

    @field_validator("customer_email")
    @classmethod
    def _customer_email(cls, v):
        return cv.validate_email(v, required=False) or None

    @field_validator("customer_address")
    @classmethod
    def _customer_address(cls, v):
        return cv.validate_address(v)

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        return cv.validate_city(v, required=False) or None

    @field_validator("postcode")
    @classmethod
    def _postcode(cls, v):
        return cv.validate_postcode(v, required=False) or None


class UpdateOrderSchema(BaseModel):
    model_config = {"populate_by_name": True}

    status: Optional[OrderStatus] = None
    final_price: Optional[float] = Field(None, alias="finalPrice")
    price_revision_reason: Optional[str] = Field(None, alias="priceRevisionReason")
    tracking_number: Optional[str] = Field(None, alias="trackingNumber")
    payment_status: Optional[PaymentStatus] = Field(None, alias="paymentStatus")
    payout_details: Optional[PayoutDetailsSchema] = Field(None, alias="payoutDetails")
    transaction_id: Optional[str] = Field(None, alias="transactionId")
    admin_notes: Optional[str] = Field(None, alias="adminNotes")
    notes: Optional[str] = None


class UpdateOrderStatusSchema(BaseModel):
    status: OrderStatus
    # Optional free-text note from staff that gets included in the customer's
    # status-update email (e.g. "Your pack is on its way, expect it in 2 days").
    # Empty/None → the standard templated email goes out unchanged.
    comment: Optional[str] = None


class BulkUpdateOrdersSchema(BaseModel):
    order_ids: list[str]
    updates: dict
