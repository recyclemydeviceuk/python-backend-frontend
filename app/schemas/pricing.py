from pydantic import BaseModel, Field
from typing import Optional, List


class CreatePricingSchema(BaseModel):
    model_config = {"populate_by_name": True}

    device_id: str = Field(..., alias="deviceId")
    device_name: str = Field("", alias="deviceName")
    network: str
    storage: str
    grade_new: float = Field(0, alias="gradeNew")
    grade_good: float = Field(0, alias="gradeGood")
    grade_broken: float = Field(0, alias="gradeBroken")

    def __init__(self, **data):
        # Support both snake_case and camelCase
        if "device_id" in data and "deviceId" not in data:
            data["deviceId"] = data.pop("device_id")
        if "device_name" in data and "deviceName" not in data:
            data["deviceName"] = data.pop("device_name")
        if "grade_new" in data and "gradeNew" not in data:
            data["gradeNew"] = data.pop("grade_new")
        if "grade_good" in data and "gradeGood" not in data:
            data["gradeGood"] = data.pop("grade_good")
        if "grade_broken" in data and "gradeBroken" not in data:
            data["gradeBroken"] = data.pop("grade_broken")
        super().__init__(**data)


class UpdatePricingSchema(BaseModel):
    model_config = {"populate_by_name": True}

    grade_new: Optional[float] = Field(None, alias="gradeNew")
    grade_good: Optional[float] = Field(None, alias="gradeGood")
    grade_broken: Optional[float] = Field(None, alias="gradeBroken")

    def __init__(self, **data):
        if "grade_new" in data and "gradeNew" not in data:
            data["gradeNew"] = data.pop("grade_new")
        if "grade_good" in data and "gradeGood" not in data:
            data["gradeGood"] = data.pop("grade_good")
        if "grade_broken" in data and "gradeBroken" not in data:
            data["gradeBroken"] = data.pop("grade_broken")
        super().__init__(**data)


class BulkUpsertPricingSchema(BaseModel):
    model_config = {"populate_by_name": True}

    device_id: str = Field(..., alias="deviceId")
    device_name: str = Field("", alias="deviceName")
    entries: List[CreatePricingSchema] = []

    def __init__(self, **data):
        if "device_id" in data and "deviceId" not in data:
            data["deviceId"] = data.pop("device_id")
        if "device_name" in data and "deviceName" not in data:
            data["deviceName"] = data.pop("device_name")
        super().__init__(**data)
