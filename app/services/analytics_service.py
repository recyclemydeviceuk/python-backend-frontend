from datetime import datetime, timedelta, timezone
from app.models.order import Order
from app.models.device import Device
from app.models.contact_submission import ContactSubmission
from app.utils.logger import logger


async def get_dashboard_stats() -> dict:
    """Aggregate stats for the admin dashboard."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    total_orders = await Order.count()
    orders_this_month = await Order.find(Order.created_at >= thirty_days_ago).count()
    orders_this_week = await Order.find(Order.created_at >= seven_days_ago).count()

    from app.config.constants import OrderStatus
    pending = await Order.find(Order.status == OrderStatus.RECEIVED).count()
    completed = await Order.find(Order.status == OrderStatus.PAID).count()
    cancelled = await Order.find(Order.status == OrderStatus.CANCELLED).count()

    # Revenue
    pipeline = [
        {"$match": {"status": "PAID"}},
        {"$group": {"_id": None, "total": {"$sum": "$final_price"}}},
    ]
    result = await Order.aggregate(pipeline).to_list()
    total_revenue = result[0]["total"] if result else 0

    total_devices = await Device.count()
    active_devices = await Device.find(Device.is_active == True).count()

    unread_contacts = await ContactSubmission.find(
        ContactSubmission.is_read == False
    ).count()

    # Orders by status
    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    status_breakdown = await Order.aggregate(status_pipeline).to_list()

    # Recent orders (last 7 days by day)
    daily_pipeline = [
        {"$match": {"created_at": {"$gte": seven_days_ago}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1},
                "revenue": {"$sum": "$offered_price"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    daily_stats = await Order.aggregate(daily_pipeline).to_list()

    return {
        "orders": {
            "total": total_orders,
            "this_month": orders_this_month,
            "this_week": orders_this_week,
            "pending": pending,
            "completed": completed,
            "cancelled": cancelled,
            "status_breakdown": status_breakdown,
        },
        "revenue": {
            "total": total_revenue,
        },
        "devices": {
            "total": total_devices,
            "active": active_devices,
        },
        "contacts": {
            "unread": unread_contacts,
        },
        "daily_stats": daily_stats,
    }
