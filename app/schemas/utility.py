from pydantic import BaseModel
from typing import Optional, List


class CreateNetworkSchema(BaseModel):
    name: str
    value: str
    is_active: bool = True
    sort_order: int = 0


class UpdateNetworkSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateStorageOptionSchema(BaseModel):
    name: str
    value: str
    is_active: bool = True
    sort_order: int = 0


class UpdateStorageOptionSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateDeviceConditionSchema(BaseModel):
    name: str
    value: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class UpdateDeviceConditionSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateBrandSchema(BaseModel):
    name: str
    logo: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class UpdateBrandSchema(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CreateCategorySchema(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class UpdateCategorySchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CreateOrderStatusSchema(BaseModel):
    name: str
    value: str
    color: str = "bg-gray-100 text-gray-700"
    sort_order: int = 0
    is_active: bool = True


class UpdateOrderStatusSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CreatePaymentStatusSchema(BaseModel):
    name: str
    value: str
    color: str = "bg-gray-100 text-gray-700"
    sort_order: int = 0
    is_active: bool = True


class UpdatePaymentStatusSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ReorderItemSchema(BaseModel):
    id: str
    sort_order: Optional[int] = None


class ReorderSchema(BaseModel):
    items: List[ReorderItemSchema]
