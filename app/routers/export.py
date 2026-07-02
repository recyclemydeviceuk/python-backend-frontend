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
    orders_csv_from_rows,
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
    payment_status: Optional[str] = None,
    paymentStatus: Optional[str] = None,
    grade: Optional[str] = None,
    network: Optional[str] = None,
    postage_method: Optional[str] = None,
    postageMethod: Optional[str] = None,
    partner: Optional[str] = None,
    date_from: Optional[str] = None,
    dateFrom: Optional[str] = None,
    date_to: Optional[str] = None,
    dateTo: Optional[str] = None,
    min_price: Optional[float] = None,
    minPrice: Optional[float] = None,
    max_price: Optional[float] = None,
    maxPrice: Optional[float] = None,
    search: Optional[str] = None,
    # Legacy param names, kept so existing bookmarks/integrations don't break.
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    # Reuse the exact filter + serialization pipeline of GET /api/orders so
    # the CSV always matches what the admin sees in the panel.
    from app.routers.orders import _filter_docs, _serialize_raw, _coerce_sort_datetime, _raw_value

    collection = Order.get_motor_collection()
    docs = await collection.find({}).to_list(length=None)
    docs = _filter_docs(
        docs,
        status=status,
        source=source,
        payment_status=paymentStatus or payment_status,
        grade=grade,
        network=network,
        postage_method=postageMethod or postage_method,
        partner=partner,
        date_from=dateFrom or date_from or start_date,
        date_to=dateTo or date_to or end_date,
        min_price=minPrice if minPrice is not None else min_price,
        max_price=maxPrice if maxPrice is not None else max_price,
        search=search,
    )
    docs.sort(key=lambda d: _coerce_sort_datetime(_raw_value(d, "created_at", "createdAt")), reverse=True)

    rows = [_serialize_raw(d) for d in docs]
    csv_bytes = orders_csv_from_rows(rows)
    filename = f"orders_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    logger.info(f"Orders exported: {len(rows)} orders")
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
