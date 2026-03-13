from pydantic import BaseModel, Field
from typing import Optional, List


def _normalize(data: dict) -> dict:
    """Map camelCase keys to snake_case for all utility schemas."""
    if "isActive" in data and "is_active" not in data:
        data["is_active"] = data.pop("isActive")
    if "sortOrder" in data and "sort_order" not in data:
        data["sort_order"] = data.pop("sortOrder")
    return data


class CreateNetworkSchema(BaseModel):
    name: str
    value: str
    is_active: bool = True
    sort_order: int = 0


class UpdateNetworkSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    value: Optional[str] = None
    is_active: Optional[bool] = Field(None, alias="isActive")
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreateStorageOptionSchema(BaseModel):
    name: str
    value: str
    is_active: bool = True
    sort_order: int = 0


class UpdateStorageOptionSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    value: Optional[str] = None
    is_active: Optional[bool] = Field(None, alias="isActive")
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreateDeviceConditionSchema(BaseModel):
    name: str
    value: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class UpdateDeviceConditionSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = Field(None, alias="isActive")
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreateBrandSchema(BaseModel):
    name: str
    logo: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class UpdateBrandSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    logo: Optional[str] = None
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    is_active: Optional[bool] = Field(None, alias="isActive")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreateCategorySchema(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class UpdateCategorySchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    is_active: Optional[bool] = Field(None, alias="isActive")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreateOrderStatusSchema(BaseModel):
    name: str
    value: str
    color: str = "bg-gray-100 text-gray-700"
    sort_order: int = 0
    is_active: bool = True


class UpdateOrderStatusSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    value: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    is_active: Optional[bool] = Field(None, alias="isActive")
    def __init__(self, **data): super().__init__(**_normalize(data))


class CreatePaymentStatusSchema(BaseModel):
    name: str
    value: str
    color: str = "bg-gray-100 text-gray-700"
    sort_order: int = 0
    is_active: bool = True


class UpdatePaymentStatusSchema(BaseModel):
    model_config = {"populate_by_name": True}
    name: Optional[str] = None
    value: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    is_active: Optional[bool] = Field(None, alias="isActive")
    def __init__(self, **data): super().__init__(**_normalize(data))


class ReorderItemSchema(BaseModel):
    id: str
    sort_order: Optional[int] = None


class ReorderSchema(BaseModel):
    items: List[ReorderItemSchema]
