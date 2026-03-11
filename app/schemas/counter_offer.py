from pydantic import BaseModel
from typing import Optional


class CreateCounterOfferSchema(BaseModel):
    order_id: str
    counter_price: float
    reason: Optional[str] = None


class RespondCounterOfferSchema(BaseModel):
    action: str  # "accept" or "decline"
