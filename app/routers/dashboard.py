from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.middleware.auth import get_current_admin
from app.models.order import Order
from app.models.device import Device
from app.services.analytics_service import get_dashboard_stats
from app.utils.response import success_response
from app.utils.logger import logger

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", summary="Get dashboard statistics", dependencies=[Depends(get_current_admin)])
async def get_dashboard_stats_route():
    stats = await get_dashboard_stats()
    return success_response({"stats": stats})


@router.get("", summary="Get dashboard statistics (alias)", dependencies=[Depends(get_current_admin)])
async def get_dashboard():
    stats = await get_dashboard_stats()
    return success_response({"stats": stats})


@router.get("/recent-orders", summary="Get recent orders", dependencies=[Depends(get_current_admin)])
async def get_recent_orders(limit: int = Query(10, ge=1, le=100)):
    orders = await Order.get_motor_collection().find({}).sort("createdAt", -1).limit(limit).to_list(length=limit)
    data = [
        {
            "id": str(o.get("_id") or o.get("id")), "_id": str(o.get("_id") or o.get("id")),
            "orderNumber": o.get("orderNumber") or o.get("order_number") or "", "order_number": o.get("orderNumber") or o.get("order_number") or "",
            "status": o.get("status") or "PENDING",
            "source": o.get("source") or "WEBSITE",
            "customerName": o.get("customerName") or o.get("customer_name") or "", "customer_name": o.get("customerName") or o.get("customer_name") or "",
            "deviceName": o.get("deviceName") or o.get("device_name") or "", "device_name": o.get("deviceName") or o.get("device_name") or "",
            "offeredPrice": o.get("offeredPrice", o.get("offered_price", 0)), "offered_price": o.get("offeredPrice", o.get("offered_price", 0)),
            "finalPrice": o.get("finalPrice", o.get("final_price")), "final_price": o.get("finalPrice", o.get("final_price")),
            "createdAt": (o.get("createdAt") or o.get("created_at") or datetime.utcnow()).isoformat() if isinstance(o.get("createdAt") or o.get("created_at"), datetime) else str(o.get("createdAt") or o.get("created_at") or datetime.utcnow().isoformat()), "created_at": (o.get("createdAt") or o.get("created_at") or datetime.utcnow()).isoformat() if isinstance(o.get("createdAt") or o.get("created_at"), datetime) else str(o.get("createdAt") or o.get("created_at") or datetime.utcnow().isoformat()),
        }
        for o in orders
    ]
    return success_response({"orders": data})


@router.get("/status-breakdown", summary="Get order status breakdown", dependencies=[Depends(get_current_admin)])
async def get_status_breakdown():
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    breakdown = await Order.aggregate(pipeline).to_list()
    total = await Order.count()
    result = [
        {
            "status": item["_id"],
            "count": item["count"],
            "percentage": round((item["count"] / total) * 100, 2) if total > 0 else 0,
        }
        for item in breakdown
    ]
    return success_response({"breakdown": result, "total": total})


@router.get("/revenue", summary="Get revenue analytics", dependencies=[Depends(get_current_admin)])
async def get_revenue_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    match_filter = {"status": {"$in": ["COMPLETED", "PAID"]}}
    all_filter = {}
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        match_filter["created_at"] = date_filter
        all_filter["created_at"] = date_filter

    revenue_pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$final_price", "$offered_price"]}}}},
    ]
    avg_pipeline = [
        {"$match": all_filter},
        {"$group": {"_id": None, "avg": {"$avg": {"$ifNull": ["$final_price", "$offered_price"]}}}},
    ]

    revenue_result = await Order.aggregate(revenue_pipeline).to_list()
    avg_result = await Order.aggregate(avg_pipeline).to_list()
    paid_count = await Order.find(Order.status.in_(["COMPLETED", "PAID"])).count()

    return success_response({
        "totalRevenue": revenue_result[0]["total"] if revenue_result else 0,
        "paidOrders": paid_count,
        "avgOrderValue": round(avg_result[0]["avg"], 2) if avg_result and avg_result[0].get("avg") else 0,
    })


@router.get("/orders-over-time", summary="Get orders over time chart data", dependencies=[Depends(get_current_admin)])
async def get_orders_over_time(period: str = Query("30days")):
    days_map = {"7days": 7, "30days": 30, "90days": 90, "1year": 365}
    days_back = days_map.get(period, 30)
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    if period == "1year":
        group_by = {"$month": "$created_at"}
    else:
        group_by = {"$dayOfYear": "$created_at"}

    pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {
            "$group": {
                "_id": group_by,
                "count": {"$sum": 1},
                "date": {"$first": "$created_at"},
            }
        },
        {"$sort": {"date": 1}},
    ]
    data = await Order.aggregate(pipeline).to_list()
    return success_response({"period": period, "data": data})


@router.get("/top-devices", summary="Get top devices by order count", dependencies=[Depends(get_current_admin)])
async def get_top_devices(limit: int = Query(10, ge=1, le=50)):
    pipeline = [
        {
            "$group": {
                "_id": "$device_name",
                "count": {"$sum": 1},
                "totalValue": {"$sum": {"$ifNull": ["$final_price", "$offered_price"]}},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    top_devices = await Order.aggregate(pipeline).to_list()
    return success_response({"topDevices": top_devices})
