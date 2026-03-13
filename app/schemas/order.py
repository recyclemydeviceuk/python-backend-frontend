from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.config.constants import OrderStatus, OrderSource, DeviceGrade, PostageMethod, PaymentMethod, PaymentStatus


class PayoutDetailsSchema(BaseModel):
    account_name: Optional[str] = Field(None, alias="accountName")
    account_number: Optional[str] = Field(None, alias="accountNumber")
    sort_code: Optional[str] = Field(None, alias="sortCode")

    class Config:
        populate_by_name = True


class CreateOrderSchema(BaseModel):
    customer_name: str = Field(..., alias="customerName")
    customer_phone: str = Field(..., alias="customerPhone")
    customer_email: Optional[EmailStr] = Field(None, alias="customerEmail")
    customer_address: str = Field(..., alias="customerAddress")
    postcode: Optional[str] = None
    device_id: Optional[str] = Field(None, alias="deviceId")
    device_name: str = Field(..., alias="deviceName")
    network: str
    device_grade: DeviceGrade = Field(..., alias="deviceGrade")
    storage: str
    offered_price: float = Field(..., alias="offeredPrice")
    postage_method: PostageMethod = Field(..., alias="postageMethod")
    payout_details: Optional[PayoutDetailsSchema] = Field(None, alias="payoutDetails")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


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


class BulkUpdateOrdersSchema(BaseModel):
    order_ids: list[str]
    updates: dict
