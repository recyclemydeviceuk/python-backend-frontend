import time
from fastapi import APIRouter, Request, Query
from fastapi.responses import Response
from typing import Optional
from datetime import datetime
from app.services.feed_service import generate_pricing_feed_csv
from app.models.feed_log import FeedLog
from app.utils.logger import logger

router = APIRouter(prefix="/feed", tags=["Feed"])


@router.get("/pricing", summary="Live Pricing Feed (CSV)")
async def pricing_feed(
    request: Request,
    brand: Optional[str] = Query(None, description="Filter by brand (e.g., 'apple', 'samsung')"),
    active_only: bool = Query(True, description="Only include active devices"),
    category: Optional[str] = Query(None, description="Filter by category (e.g., 'Phone', 'Tablet')"),
):
    start_time = time.time()
    
    csv_content, row_count = await generate_pricing_feed_csv(
        brand=brand,
        active_only=active_only,
        category=category
    )
    
    response_time_ms = int((time.time() - start_time) * 1000)
    
    source_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    
    query_params_str = ""
    if brand:
        query_params_str += f"brand={brand}&"
    if not active_only:
        query_params_str += "active_only=false&"
    if category:
        query_params_str += f"category={category}&"
    query_params_str = query_params_str.rstrip("&")
    
    try:
        log = FeedLog(
            endpoint="/api/feed/pricing",
            source_ip=source_ip,
            user_agent=user_agent,
            partner_name=None,
            rows_returned=row_count,
            query_params=query_params_str or None,
            response_time_ms=response_time_ms
        )
        await log.insert()
    except Exception as e:
        logger.error(f"Failed to log feed access: {e}")
    
    filename = f"pricing_feed_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    logger.info(f"Pricing feed accessed from {source_ip} - {row_count} rows returned in {response_time_ms}ms")
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/pricing/json", summary="Live Pricing Feed (JSON)")
async def pricing_feed_json(
    request: Request,
    brand: Optional[str] = Query(None, description="Filter by brand"),
    active_only: bool = Query(True, description="Only include active devices"),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    from app.models.device import Device
    from app.models.pricing import Pricing

    start_time = time.time()

    device_col = Device.get_motor_collection()
    pricing_col = Pricing.get_motor_collection()

    conditions: list = []
    if active_only:
        conditions.append({"$or": [{"isActive": True}, {"is_active": True}]})
    if brand:
        conditions.append({"brand": {"$regex": f"^{brand}$", "$options": "i"}})
    if category:
        conditions.append({"category": {"$regex": f"^{category}$", "$options": "i"}})
    device_match: dict = {"$and": conditions} if conditions else {}

    devices_raw = await device_col.find(device_match).to_list(length=None)
    pricing_raw = await pricing_col.find({}).to_list(length=None)

    pricing_map: dict[str, list] = {}
    for p in pricing_raw:
        raw_did = p.get("deviceId") or p.get("device_id")
        if raw_did is None:
            continue
        pricing_map.setdefault(str(raw_did), []).append(p)

    result = []
    for device in devices_raw:
        device_id = str(device["_id"])
        name_val = device.get("name") or ""
        full_name_val = device.get("fullName") or device.get("full_name") or name_val
        brand_val = (device.get("brand") or "").title()
        category_val = device.get("category") or ""
        image_url_val = device.get("imageUrl") or device.get("image_url") or ""
        is_active_val = device.get("isActive", device.get("is_active", True))
        device_updated_raw = device.get("updatedAt") or device.get("updated_at")
        device_updated = device_updated_raw.isoformat() if device_updated_raw else datetime.utcnow().isoformat()

        for p in pricing_map.get(device_id, []):
            updated_raw = p.get("updatedAt") or p.get("updated_at")
            storage_val = p.get("storage") or ""
            full_name_with_storage = f"{full_name_val} {storage_val}".strip() if storage_val else full_name_val
            
            result.append({
                "device_id": device_id,
                "brand": brand_val,
                "device_name": name_val,
                "full_name": full_name_with_storage,
                "category": category_val,
                "storage": storage_val,
                "network": p.get("network") or "",
                "price_new": float(p.get("gradeNew") or p.get("grade_new") or 0),
                "price_good": float(p.get("gradeGood") or p.get("grade_good") or 0),
                "price_broken": float(p.get("gradeBroken") or p.get("grade_broken") or 0),
                "image_url": image_url_val,
                "active": is_active_val,
                "last_updated": updated_raw.isoformat() if updated_raw else device_updated,
            })

    response_time_ms = int((time.time() - start_time) * 1000)
    source_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    query_params_str = "&".join(
        filter(None, [
            f"brand={brand}" if brand else "",
            "active_only=false" if not active_only else "",
            f"category={category}" if category else "",
        ])
    )

    try:
        log = FeedLog(
            endpoint="/api/feed/pricing/json",
            source_ip=source_ip,
            user_agent=user_agent,
            partner_name=None,
            rows_returned=len(result),
            query_params=query_params_str or None,
            response_time_ms=response_time_ms,
        )
        await log.insert()
    except Exception as e:
        logger.error(f"Failed to log feed access: {e}")

    logger.info(f"Pricing feed (JSON) from {source_ip} — {len(result)} rows in {response_time_ms}ms")

    return {
        "success": True,
        "count": len(result),
        "data": result,
        "timestamp": datetime.utcnow().isoformat(),
    }
