from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.pricing import Pricing
from app.schemas.pricing import CreatePricingSchema, UpdatePricingSchema, BulkUpsertPricingSchema
from app.middleware.auth import get_current_admin
from app.services.pricing_service import upsert_pricing
from app.utils.response import success_response, created_response
from app.utils.logger import logger

router = APIRouter(prefix="/pricing", tags=["Pricing"])


@router.get("", summary="Get all pricing (public)")
async def get_all_pricing(device_id: Optional[str] = None, network: Optional[str] = None, storage: Optional[str] = None):
    filters = []
    if device_id:
        filters.append(Pricing.device_id == device_id)
    if network:
        filters.append(Pricing.network == network)
    if storage:
        filters.append(Pricing.storage == storage)
    pricing = await Pricing.find(*filters).to_list()
    return success_response({"pricing": [_serialize(p) for p in pricing]})


@router.get("/device/{device_id}", summary="Get pricing for a device (public)")
async def get_pricing_by_device(device_id: str):
    # Convert string to ObjectId for query since MongoDB stores it as ObjectId
    try:
        device_oid = ObjectId(device_id)
    except:
        device_oid = device_id
    pricing = await Pricing.get_motor_collection().find({"deviceId": device_oid}).to_list(length=None)
    pricing_objs = [Pricing.model_validate(p) for p in pricing]
    return success_response({"pricing": [_serialize(p) for p in pricing_objs]})


@router.get("/quote", summary="Get quote for device configuration (public)")
async def get_quote(
    device_id: Optional[str] = None,
    network: Optional[str] = None,
    storage: Optional[str] = None,
    grade: Optional[str] = None,
):
    query = {}
    if device_id:
        try:
            query["deviceId"] = ObjectId(device_id)
        except:
            query["deviceId"] = device_id
    if network:
        query["network"] = network
    if storage:
        query["storage"] = storage

    pricing_doc = await Pricing.get_motor_collection().find_one(query) if query else None
    pricing = Pricing.model_validate(pricing_doc) if pricing_doc else None

    if not pricing:
        from app.utils.response import error_response
        return error_response("No pricing found for the given configuration", 404)

    grade_map = {
        "NEW": pricing.grade_new,
        "GOOD": pricing.grade_good,
        "BROKEN": pricing.grade_broken,
    }
    price = grade_map.get((grade or "").upper())
    return success_response({
        "pricing": _serialize(pricing),
        "quote": price,
        "grade": (grade or "").upper(),
    })


@router.post("", summary="Create pricing entry", dependencies=[Depends(get_current_admin)])
async def create_pricing(body: CreatePricingSchema):
    existing = await Pricing.find_one(
        Pricing.device_id == body.device_id,
        Pricing.network == body.network,
        Pricing.storage == body.storage,
    )
    if existing:
        raise HTTPException(status_code=409, detail="Pricing entry already exists for this device/network/storage combination")

    pricing = Pricing(**body.dict())
    await pricing.insert()
    return created_response({"pricing": _serialize(pricing)}, "Pricing created successfully")


@router.put("/{pricing_id}", summary="Update pricing entry", dependencies=[Depends(get_current_admin)])
async def update_pricing(pricing_id: str, body: UpdatePricingSchema):
    pricing = await Pricing.get(pricing_id)
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing entry not found")

    update_data = body.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(pricing, k, v)
    pricing.updated_at = datetime.utcnow()
    await pricing.save()
    return success_response({"pricing": _serialize(pricing)}, "Pricing updated successfully")


@router.delete("/{pricing_id}", summary="Delete pricing entry", dependencies=[Depends(get_current_admin)])
async def delete_pricing(pricing_id: str):
    pricing = await Pricing.get(pricing_id)
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing entry not found")
    await pricing.delete()
    return success_response({"message": "Pricing deleted successfully"})


@router.post("/bulk-upsert", summary="Bulk upsert pricing for a device", dependencies=[Depends(get_current_admin)])
async def bulk_upsert(body: BulkUpsertPricingSchema):
    results = []
    for entry in body.entries:
        p = await upsert_pricing(
            device_id=body.device_id,
            device_name=body.device_name,
            network=entry.network,
            storage=entry.storage,
            grade_new=entry.grade_new,
            grade_good=entry.grade_good,
            grade_broken=entry.grade_broken,
        )
        results.append(_serialize(p))
    return success_response({"pricing": results, "count": len(results)}, "Bulk upsert complete")


def _serialize(p: Pricing) -> dict:
    return {
        "id": str(p.id), "_id": str(p.id),
        "device_id": p.device_id or "", "deviceId": p.device_id or "",
        "device_name": p.device_name or "", "deviceName": p.device_name or "",
        "network": p.network, "storage": p.storage,
        "grade_new": p.grade_new, "gradeNew": p.grade_new,
        "grade_good": p.grade_good, "gradeGood": p.grade_good,
        "grade_broken": p.grade_broken, "gradeBroken": p.grade_broken,
        "created_at": p.created_at.isoformat(), "createdAt": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(), "updatedAt": p.updated_at.isoformat(),
    }
