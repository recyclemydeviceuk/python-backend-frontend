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
    orders = await Order.find().sort(-Order.created_at).limit(limit).to_list()
    data = [
        {
            "id": str(o.id), "_id": str(o.id),
            "orderNumber": o.order_number, "order_number": o.order_number,
            "status": o.status,
            "source": o.source,
            "customerName": o.customer_name, "customer_name": o.customer_name,
            "deviceName": o.device_name, "device_name": o.device_name,
            "offeredPrice": o.offered_price, "offered_price": o.offered_price,
            "finalPrice": o.final_price, "final_price": o.final_price,
            "createdAt": o.created_at.isoformat(), "created_at": o.created_at.isoformat(),
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
