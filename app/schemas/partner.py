from pydantic import BaseModel
from typing import Optional, List


class CreatePartnerSchema(BaseModel):
    name: str
    allowed_ips: List[str] = []
    rate_limit: int = 100
    notes: Optional[str] = None


class UpdatePartnerSchema(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_ips: Optional[List[str]] = None
    rate_limit: Optional[int] = None
    notes: Optional[str] = None
