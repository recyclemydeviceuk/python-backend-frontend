from pydantic import BaseModel
from typing import Optional, List


class CreatePricingSchema(BaseModel):
    device_id: str
    device_name: str
    network: str
    storage: str
    grade_new: float = 0
    grade_good: float = 0
    grade_broken: float = 0


class UpdatePricingSchema(BaseModel):
    grade_new: Optional[float] = None
    grade_good: Optional[float] = None
    grade_broken: Optional[float] = None


class BulkUpsertPricingSchema(BaseModel):
    device_id: str
    device_name: str
    entries: List[CreatePricingSchema]
