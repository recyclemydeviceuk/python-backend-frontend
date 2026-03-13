from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from typing import Optional
from app.models.device import Device
from app.models.pricing import Pricing
from app.schemas.device import CreateDeviceSchema, UpdateDeviceSchema
from app.middleware.auth import get_current_admin
from app.services.import_service import import_devices_from_csv
from app.utils.response import success_response, created_response, error_response
from app.utils.logger import logger
from datetime import datetime

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", summary="Get all devices (public)")
async def get_all_devices(
    brand: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    isActive: Optional[bool] = None,
    search: Optional[str] = None,
    limit: Optional[int] = Query(None, le=500),
    page: Optional[int] = Query(None, ge=1),
):
    active_filter = is_active if is_active is not None else isActive
    filters = []
    if brand:
        filters.append(Device.brand == brand)
    if category:
        filters.append(Device.category == category)
    if active_filter is not None:
        filters.append(Device.is_active == active_filter)

    q = Device.find(*filters).sort(-Device.created_at)
    total = await q.count()
    if search:
        import re
        pattern = re.compile(search, re.IGNORECASE)
        devices = await q.to_list()
        devices = [d for d in devices if pattern.search(d.name) or pattern.search(d.full_name or '') or pattern.search(d.brand)]
    elif page and limit:
        skip = (page - 1) * limit
        devices = await q.skip(skip).limit(limit).to_list()
        from app.utils.response import paginated_response
        return paginated_response([_serialize(d) for d in devices], page, limit, total)
    else:
        devices = await (q.limit(limit) if limit else q).to_list()

    return success_response({"devices": [_serialize(d) for d in devices]})


@router.get("/{device_id}", summary="Get single device with pricing")
async def get_device(device_id: str):
    device = await Device.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Try both string and ObjectId forms since pricing may have been saved either way
    from bson import ObjectId as BsonObjectId
    col = Pricing.get_motor_collection()
    try:
        oid = BsonObjectId(device_id)
        raw = await col.find({"$or": [{"deviceId": device_id}, {"deviceId": oid}, {"device_id": device_id}]}).to_list(length=None)
    except Exception:
        raw = await col.find({"$or": [{"deviceId": device_id}, {"device_id": device_id}]}).to_list(length=None)
    pricing_objs = []
    for doc in raw:
        try:
            pricing_objs.append(Pricing.model_validate(doc))
        except Exception:
            pass
    return success_response({"device": _serialize(device), "pricing": [_serialize_pricing(p) for p in pricing_objs]})


@router.post("", summary="Create device", dependencies=[Depends(get_current_admin)])
async def create_device(body: CreateDeviceSchema):
    device = Device(
        brand=body.brand, name=body.name, full_name=body.full_name,
        category=body.category, image_url=body.image_url, is_active=body.is_active,
        specifications=body.specifications,
    )
    await device.insert()

    if body.default_pricing:
        for p in body.default_pricing:
            pricing = Pricing(device_id=str(device.id), device_name=device.full_name,
                              network=p.network, storage=p.storage,
                              grade_new=p.grade_new, grade_good=p.grade_good, grade_broken=p.grade_broken)
            await pricing.insert()

    logger.info(f"Device created: {device.full_name}")
    return created_response({"device": _serialize(device)}, "Device created successfully")


@router.put("/{device_id}", summary="Update device", dependencies=[Depends(get_current_admin)])
async def update_device(device_id: str, body: UpdateDeviceSchema):
    device = await Device.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if body.brand is not None:
        device.brand = body.brand
    if body.name is not None:
        device.name = body.name
    if body.full_name is not None:
        device.full_name = body.full_name
    if body.category is not None:
        device.category = body.category
    if body.image_url is not None:
        device.image_url = body.image_url
    if body.is_active is not None:
        device.is_active = body.is_active
    if body.specifications is not None:
        device.specifications = body.specifications
    device.updated_at = datetime.utcnow()
    await device.save()

    if body.default_pricing is not None:
        await Pricing.find(Pricing.device_id == device_id).delete()
        for p in body.default_pricing:
            pricing = Pricing(device_id=device_id, device_name=device.full_name,
                              network=p.network, storage=p.storage,
                              grade_new=p.grade_new, grade_good=p.grade_good, grade_broken=p.grade_broken)
            await pricing.insert()

    logger.info(f"Device updated: {device.full_name}")
    return success_response({"device": _serialize(device)}, "Device updated successfully")


@router.patch("/{device_id}/toggle", summary="Toggle device active status", dependencies=[Depends(get_current_admin)])
async def toggle_device(device_id: str):
    device = await Device.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.is_active = not device.is_active
    device.updated_at = datetime.utcnow()
    await device.save()
    return success_response({"device": _serialize(device)}, "Device status updated")


@router.delete("/{device_id}", summary="Delete device", dependencies=[Depends(get_current_admin)])
async def delete_device(device_id: str):
    device = await Device.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await Pricing.find(Pricing.device_id == device_id).delete()
    await device.delete()
    logger.info(f"Device deleted: {device.full_name}")
    return success_response({"message": "Device deleted successfully"})


@router.post("/import", summary="Import devices from CSV", dependencies=[Depends(get_current_admin)])
async def import_devices(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    content = await file.read()
    imported, skipped, errors = await import_devices_from_csv(content)
    return success_response({"imported": imported, "skipped": skipped, "errors": errors}, "Import complete")


def _serialize(d: Device) -> dict:
    raw_full = d.full_name or d.name
    brand = (d.brand or "").strip()
    # Strip duplicate brand prefix (e.g. "Samsung Samsung Galaxy" → "Samsung Galaxy")
    if brand and raw_full.startswith(brand + " " + brand + " "):
        raw_full = raw_full[len(brand) + 1:]
    elif brand and raw_full.startswith(brand + " ") and raw_full.count(brand) > 1:
        raw_full = raw_full[len(brand) + 1:]
    full_name = raw_full
    return {
        "id": str(d.id), "_id": str(d.id),
        "brand": d.brand, "name": d.name,
        "full_name": full_name, "fullName": full_name,
        "category": d.category,
        "image_url": d.image_url, "imageUrl": d.image_url,
        "is_active": d.is_active, "isActive": d.is_active,
        "specifications": d.specifications,
        "created_at": d.created_at.isoformat(), "createdAt": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(), "updatedAt": d.updated_at.isoformat(),
    }


def _serialize_pricing(p: Pricing) -> dict:
    return {
        "id": str(p.id), "_id": str(p.id),
        "device_id": p.device_id, "deviceId": p.device_id,
        "network": p.network, "storage": p.storage,
        "grade_new": p.grade_new, "gradeNew": p.grade_new,
        "grade_good": p.grade_good, "gradeGood": p.grade_good,
        "grade_broken": p.grade_broken, "gradeBroken": p.grade_broken,
    }
