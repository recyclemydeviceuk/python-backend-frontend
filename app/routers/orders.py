from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
from app.models.order import Order
from app.schemas.order import CreateOrderSchema, UpdateOrderSchema, UpdateOrderStatusSchema, BulkUpdateOrdersSchema
from app.middleware.auth import get_current_admin
from app.services.email_service import (
    send_order_confirmation,
    send_order_completion_email,
    send_order_status_update,
    send_price_revision_email,
    send_payment_confirmation,
)
from app.utils.order_number import generate_unique_order_number
from app.utils.response import success_response, created_response, paginated_response
from app.config.constants import OrderSource, PaymentStatus
from app.utils.logger import logger

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", summary="Get all orders", dependencies=[Depends(get_current_admin)])
async def get_all_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    filters = []
    if status:
        filters.append(Order.status == status)
    if source:
        filters.append(Order.source == source)

    q = Order.find(*filters)
    total = await q.count()

    skip = (page - 1) * limit
    orders = await q.sort(-Order.created_at if sort_order == "desc" else Order.created_at).skip(skip).limit(limit).to_list()

    if search:
        import re
        pattern = re.compile(search, re.IGNORECASE)
        orders = [o for o in orders if any(pattern.search(str(getattr(o, f, "") or ""))
                  for f in ["order_number", "customer_name", "customer_email", "customer_phone", "device_name"])]

    return paginated_response([_serialize(o) for o in orders], page, limit, total)


@router.get("/{order_id}", summary="Get order by ID", dependencies=[Depends(get_current_admin)])
async def get_order(order_id: str):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return success_response({"order": _serialize(order)})


@router.post("", summary="Create order (public)")
async def create_order(body: CreateOrderSchema):
    order_number = await generate_unique_order_number()
    order = Order(
        order_number=order_number,
        source=OrderSource.WEBSITE,
        **body.dict(),
    )
    await order.insert()
    logger.info(f"Order created: {order.order_number}")

    if order.customer_email:
        await send_order_confirmation(order)

    return created_response({"order": _serialize(order)}, "Order created successfully")


@router.put("/{order_id}", summary="Update order", dependencies=[Depends(get_current_admin)])
async def update_order(order_id: str, body: UpdateOrderSchema):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    old_status = order.status
    old_final_price = order.final_price or order.offered_price

    update_data = body.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(order, k, v)

    # Auto payment status
    if body.status and body.status == "PAID":
        order.payment_status = PaymentStatus.PAID
    elif body.status:
        order.payment_status = PaymentStatus.PENDING

    order.updated_at = datetime.utcnow()
    await order.save()

    # Email notifications — mirror Node.js emailService
    if old_status != order.status:
        if order.status == "PAID":
            await send_order_completion_email(order)
            await send_payment_confirmation(order)
        else:
            await send_order_status_update(order, old_status)
    if body.final_price and body.final_price != old_final_price and order.price_revision_reason:
        await send_price_revision_email(order, old_final_price, body.final_price, order.price_revision_reason)

    logger.info(f"Order updated: {order.order_number}")
    return success_response({"order": _serialize(order)}, "Order updated successfully")


@router.patch("/{order_id}/status", summary="Update order status", dependencies=[Depends(get_current_admin)])
async def update_status(order_id: str, body: UpdateOrderStatusSchema):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    old_status = order.status
    order.status = body.status
    order.payment_status = PaymentStatus.PAID if body.status == "PAID" else PaymentStatus.PENDING
    order.updated_at = datetime.utcnow()
    await order.save()

    if body.status == "PAID":
        await send_order_completion_email(order)
        await send_payment_confirmation(order)
    else:
        await send_order_status_update(order, old_status)

    logger.info(f"Order status: {order.order_number} {old_status} -> {body.status}")
    return success_response({"order": _serialize(order)}, "Order status updated")


@router.delete("/{order_id}", summary="Delete order", dependencies=[Depends(get_current_admin)])
async def delete_order(order_id: str):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await order.delete()
    logger.info(f"Order deleted: {order.order_number}")
    return success_response({"message": "Order deleted successfully"})


@router.post("/bulk-update", summary="Bulk update orders", dependencies=[Depends(get_current_admin)])
async def bulk_update(body: BulkUpdateOrdersSchema):
    from beanie.operators import In
    result = await Order.find(In(Order.id, body.order_ids)).update({"$set": body.updates})
    return success_response({"message": f"Orders updated successfully", "modified_count": result.modified_count})


def _serialize(o: Order) -> dict:
    payout = o.payout_details
    payout_data = None
    if payout:
        payout_data = {
            "account_name": payout.account_name, "accountName": payout.account_name,
            "account_number": payout.account_number, "accountNumber": payout.account_number,
            "sort_code": payout.sort_code, "sortCode": payout.sort_code,
        }
    counter = o.counter_offer
    counter_data = None
    if counter:
        counter_data = {
            "has_counter_offer": counter.has_counter_offer, "hasCounterOffer": counter.has_counter_offer,
            "latest_offer_id": counter.latest_offer_id, "latestOfferId": counter.latest_offer_id,
            "status": counter.status,
        }
    return {
        "id": str(o.id), "_id": str(o.id),
        "order_number": o.order_number, "orderNumber": o.order_number,
        "source": o.source,
        "customer_name": o.customer_name, "customerName": o.customer_name,
        "customer_phone": o.customer_phone, "customerPhone": o.customer_phone,
        "customer_email": o.customer_email, "customerEmail": o.customer_email,
        "customer_address": o.customer_address, "customerAddress": o.customer_address,
        "postcode": o.postcode,
        "device_id": o.device_id, "deviceId": o.device_id,
        "device_name": o.device_name, "deviceName": o.device_name,
        "network": o.network,
        "device_grade": o.device_grade, "deviceGrade": o.device_grade,
        "storage": o.storage,
        "offered_price": o.offered_price, "offeredPrice": o.offered_price,
        "final_price": o.final_price, "finalPrice": o.final_price,
        "postage_method": o.postage_method, "postageMethod": o.postage_method,
        "status": o.status,
        "payment_status": o.payment_status, "paymentStatus": o.payment_status,
        "payout_details": payout_data, "payoutDetails": payout_data,
        "counter_offer": counter_data, "counterOffer": counter_data,
        "notes": o.notes,
        "admin_notes": o.admin_notes, "adminNotes": o.admin_notes,
        "tracking_number": o.tracking_number, "trackingNumber": o.tracking_number,
        "created_at": o.created_at.isoformat(), "createdAt": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(), "updatedAt": o.updated_at.isoformat(),
    }
