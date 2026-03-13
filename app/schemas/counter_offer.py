from pydantic import BaseModel, Field
from typing import Optional, List


class CreateCounterOfferSchema(BaseModel):
    model_config = {"populate_by_name": True}

    order_id: str = Field(..., alias="orderId")
    counter_price: float = Field(..., alias="revisedPrice")
    reason: Optional[str] = None
    device_images: Optional[List[dict]] = Field(None, alias="deviceImages")

    def __init__(self, **data):
        if "order_id" in data and "orderId" not in data:
            data["orderId"] = data.pop("order_id")
        if "counter_price" in data and "revisedPrice" not in data:
            data["revisedPrice"] = data.pop("counter_price")
        if "device_images" in data and "deviceImages" not in data:
            data["deviceImages"] = data.pop("device_images")
        super().__init__(**data)


class RespondCounterOfferSchema(BaseModel):
    action: str  # "accept" or "decline"
