from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class DeviceSpecsSchema(BaseModel):
    screen_size: Optional[str] = None
    processor: Optional[str] = None
    camera: Optional[str] = None
    battery: Optional[str] = None
    release_year: Optional[int] = None


class PricingEntrySchema(BaseModel):
    network: str
    storage: str
    grade_new: float = 0
    grade_good: float = 0
    grade_broken: float = 0


class CreateDeviceSchema(BaseModel):
    brand: str
    name: str
    full_name: str
    category: str
    image_url: Optional[str] = None
    is_active: bool = True
    specifications: Optional[DeviceSpecsSchema] = None
    default_pricing: Optional[List[PricingEntrySchema]] = None


class UpdateDeviceSchema(BaseModel):
    brand: Optional[str] = None
    name: Optional[str] = None
    full_name: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    specifications: Optional[DeviceSpecsSchema] = None
    default_pricing: Optional[List[PricingEntrySchema]] = None


class DeviceResponse(BaseModel):
    id: str
    brand: str
    name: str
    full_name: str
    category: str
    image_url: Optional[str] = None
    is_active: bool
    specifications: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
