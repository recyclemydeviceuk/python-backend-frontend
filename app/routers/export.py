from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from typing import Optional
from datetime import datetime
from app.middleware.auth import get_current_admin
from app.models.order import Order
from app.models.device import Device
from app.models.pricing import Pricing
from app.services.export_service import (
    export_orders_csv,
    export_devices_csv,
    export_pricing_csv,
    export_analytics_csv,
    export_all_zip,
)
from app.utils.logger import logger

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/orders", summary="Export orders as CSV", dependencies=[Depends(get_current_admin)])
async def export_orders(
    status: Optional[str] = None,
    source: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    filters = []
    if status:
        filters.append(Order.status == status)
    if source:
        filters.append(Order.source == source)
    orders = await Order.find(*filters).sort(-Order.created_at).to_list()

    if start_date or end_date:
        def in_range(o):
            if start_date and o.created_at < datetime.fromisoformat(start_date):
                return False
            if end_date and o.created_at > datetime.fromisoformat(end_date):
                return False
            return True
        orders = [o for o in orders if in_range(o)]

    csv_bytes = await export_orders_csv(orders)
    filename = f"orders_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    logger.info(f"Orders exported: {len(orders)} orders")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/devices", summary="Export devices as CSV", dependencies=[Depends(get_current_admin)])
async def export_devices_route(
    brand: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    filters = []
    if brand:
        filters.append(Device.brand == brand)
    if category:
        filters.append(Device.category == category)
    if is_active is not None:
        filters.append(Device.is_active == is_active)
    devices = await Device.find(*filters).sort(Device.brand).to_list()
    csv_bytes = await export_devices_csv(devices)
    filename = f"devices_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    logger.info(f"Devices exported: {len(devices)} devices")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/pricing", summary="Export pricing as CSV", dependencies=[Depends(get_current_admin)])
async def export_pricing_route(
    device_id: Optional[str] = None,
    network: Optional[str] = None,
    storage: Optional[str] = None,
):
    filters = []
    if device_id:
        filters.append(Pricing.device_id == device_id)
    if network:
        filters.append(Pricing.network == network)
    if storage:
        filters.append(Pricing.storage == storage)
    pricing = await Pricing.find(*filters).sort(Pricing.device_name).to_list()
    csv_bytes = await export_pricing_csv(pricing)
    filename = f"pricing_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    logger.info(f"Pricing exported: {len(pricing)} entries")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/all", summary="Export all data as ZIP", dependencies=[Depends(get_current_admin)])
async def export_all():
    orders = await Order.find().sort(-Order.created_at).to_list()
    devices = await Device.find().sort(Device.brand).to_list()
    pricing = await Pricing.find().sort(Pricing.device_name).to_list()

    orders_csv = await export_orders_csv(orders)
    devices_csv = await export_devices_csv(devices)
    pricing_csv = await export_pricing_csv(pricing)
    zip_bytes = await export_all_zip(orders_csv, devices_csv, pricing_csv)

    filename = f"cashmymobile_export_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    logger.info(f"All data exported: {len(orders)} orders, {len(devices)} devices, {len(pricing)} pricing")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/analytics", summary="Export analytics report as CSV", dependencies=[Depends(get_current_admin)])
async def export_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    match_filter = {}
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        match_filter["created_at"] = date_filter

    status_pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    device_pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$device_name", "count": {"$sum": 1}, "totalValue": {"$sum": {"$ifNull": ["$final_price", "$offered_price"]}}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    revenue_pipeline = [
        {"$match": {**match_filter, "status": "PAID"}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$final_price", "$offered_price"]}}, "count": {"$sum": 1}}},
    ]

    status_breakdown = await Order.aggregate(status_pipeline).to_list()
    top_devices = await Order.aggregate(device_pipeline).to_list()
    revenue_data = await Order.aggregate(revenue_pipeline).to_list()
    total_orders = await Order.count()

    revenue = revenue_data[0] if revenue_data else {}
    analytics = {
        "summary": {
            "totalOrders": total_orders,
            "totalRevenue": revenue.get("total", 0),
            "paidOrders": revenue.get("count", 0),
            "avgOrderValue": round(revenue["total"] / revenue["count"], 2) if revenue.get("count") else 0,
        },
        "statusBreakdown": status_breakdown,
        "topDevices": top_devices,
    }

    csv_bytes = await export_analytics_csv(analytics)
    filename = f"analytics_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    logger.info("Analytics exported")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
