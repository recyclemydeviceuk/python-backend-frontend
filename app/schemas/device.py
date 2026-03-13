from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class DeviceSpecsSchema(BaseModel):
    model_config = {"populate_by_name": True}
    screen_size: Optional[str] = Field(None, alias="screenSize")
    processor: Optional[str] = None
    camera: Optional[str] = None
    battery: Optional[str] = None
    release_year: Optional[int] = Field(None, alias="releaseYear")

    def __init__(self, **data):
        if "screen_size" in data and "screenSize" not in data:
            data["screenSize"] = data.pop("screen_size")
        if "release_year" in data and "releaseYear" not in data:
            data["releaseYear"] = data.pop("release_year")
        super().__init__(**data)


class PricingEntrySchema(BaseModel):
    model_config = {"populate_by_name": True}
    network: str
    storage: str
    grade_new: float = Field(0, alias="gradeNew")
    grade_good: float = Field(0, alias="gradeGood")
    grade_broken: float = Field(0, alias="gradeBroken")

    def __init__(self, **data):
        if "grade_new" in data and "gradeNew" not in data:
            data["gradeNew"] = data.pop("grade_new")
        if "grade_good" in data and "gradeGood" not in data:
            data["gradeGood"] = data.pop("grade_good")
        if "grade_broken" in data and "gradeBroken" not in data:
            data["gradeBroken"] = data.pop("grade_broken")
        super().__init__(**data)


class CreateDeviceSchema(BaseModel):
    model_config = {"populate_by_name": True}
    brand: str
    name: str
    full_name: str = Field(..., alias="fullName")
    category: str
    image_url: Optional[str] = Field(None, alias="imageUrl")
    is_active: bool = Field(True, alias="isActive")
    specifications: Optional[DeviceSpecsSchema] = None
    default_pricing: Optional[List[PricingEntrySchema]] = Field(None, alias="defaultPricing")

    def __init__(self, **data):
        if "full_name" in data and "fullName" not in data:
            data["fullName"] = data.pop("full_name")
        if "image_url" in data and "imageUrl" not in data:
            data["imageUrl"] = data.pop("image_url")
        if "is_active" in data and "isActive" not in data:
            data["isActive"] = data.pop("is_active")
        if "default_pricing" in data and "defaultPricing" not in data:
            data["defaultPricing"] = data.pop("default_pricing")
        super().__init__(**data)


class UpdateDeviceSchema(BaseModel):
    model_config = {"populate_by_name": True}
    brand: Optional[str] = None
    name: Optional[str] = None
    full_name: Optional[str] = Field(None, alias="fullName")
    category: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    is_active: Optional[bool] = Field(None, alias="isActive")
    specifications: Optional[DeviceSpecsSchema] = None
    default_pricing: Optional[List[PricingEntrySchema]] = Field(None, alias="defaultPricing")

    def __init__(self, **data):
        if "full_name" in data and "fullName" not in data:
            data["fullName"] = data.pop("full_name")
        if "image_url" in data and "imageUrl" not in data:
            data["imageUrl"] = data.pop("image_url")
        if "is_active" in data and "isActive" not in data:
            data["isActive"] = data.pop("is_active")
        if "default_pricing" in data and "defaultPricing" not in data:
            data["defaultPricing"] = data.pop("default_pricing")
        super().__init__(**data)


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
