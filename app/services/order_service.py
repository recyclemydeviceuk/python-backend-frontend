from typing import Optional, List
from app.models.order import Order
from app.models.pricing import Pricing
from app.utils.logger import logger


async def get_price_for_order(device_id: str, network: str, storage: str, grade: str) -> Optional[float]:
    """Fetch the correct price from Pricing collection."""
    pricing = await Pricing.find_one(
        Pricing.device_id == device_id,
        Pricing.network == network,
        Pricing.storage == storage,
    )
    if not pricing:
        return None

    grade_map = {
        "NEW": pricing.grade_new,
        "GOOD": pricing.grade_good,
        "BROKEN": pricing.grade_broken,
    }
    return grade_map.get(grade.upper())


async def get_order_stats() -> dict:
    """Aggregate basic order statistics."""
    total = await Order.count()
    from app.config.constants import OrderStatus, PaymentStatus
    pending = await Order.find(Order.status == OrderStatus.RECEIVED).count()
    completed = await Order.find(Order.status == OrderStatus.PAID).count()
    cancelled = await Order.find(Order.status == OrderStatus.CANCELLED).count()

    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$offered_price"}}}]
    result = await Order.aggregate(pipeline).to_list()
    total_value = result[0]["total"] if result else 0

    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "cancelled": cancelled,
        "total_value": total_value,
    }
