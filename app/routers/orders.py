from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional
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
    limit: Optional[int] = Query(None, ge=1),
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sortBy: Optional[str] = None,
    sort_order: str = "desc",
    sortOrder: Optional[str] = None,
):
    try:
        filters = []
        if status:
            filters.append({"status": status})
        if source:
            filters.append({"source": source})

        query = {"$and": filters} if filters else {}
        collection = Order.get_motor_collection()
        docs = await collection.find(query).to_list(length=None)

        if search:
            import re
            pattern = re.compile(search, re.IGNORECASE)
            docs = [o for o in docs if any(pattern.search(str(_raw_value(o, *fields) or ""))
                    for fields in [
                        ("order_number", "orderNumber"),
                        ("customer_name", "customerName"),
                        ("customer_email", "customerEmail"),
                        ("customer_phone", "customerPhone"),
                        ("device_name", "deviceName"),
                    ])]

        requested_sort = sortBy or sort_by or "createdAt"
        reverse = (sortOrder or sort_order) == "desc"
        docs.sort(key=lambda doc: _sort_value(doc, requested_sort), reverse=reverse)

        total = len(docs)
        if limit is None:
            return success_response([_serialize_raw(o) for o in docs])

        skip = (page - 1) * limit
        paged_docs = docs[skip:skip + limit]

        return paginated_response([_serialize_raw(o) for o in paged_docs], page, limit, total)
    except Exception as e:
        logger.exception(f"Failed to get orders list: {e}")
        raise HTTPException(status_code=500, detail="Failed to load orders")


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

    if body.status is not None:
        order.status = body.status
    if body.final_price is not None:
        order.final_price = body.final_price
    if body.price_revision_reason is not None:
        order.price_revision_reason = body.price_revision_reason
    if body.tracking_number is not None:
        order.tracking_number = body.tracking_number
    if body.payment_status is not None:
        order.payment_status = body.payment_status
    if body.payout_details is not None:
        order.payout_details = body.payout_details
    if body.transaction_id is not None:
        order.transaction_id = body.transaction_id
    if body.admin_notes is not None:
        order.admin_notes = body.admin_notes
    if body.notes is not None:
        order.notes = body.notes

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


def _to_json_safe(value: Any) -> Any:
    """Recursively convert any MongoDB-specific or non-JSON-serializable type."""
    from bson import ObjectId as BsonObjectId
    if isinstance(value, BsonObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(i) for i in value]
    return value


def _raw_value(doc: dict, *keys: str):
    for key in keys:
        if key in doc and doc[key] is not None:
            return doc[key]
    return None


def _coerce_sort_datetime(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _sort_value(doc: dict, requested_sort: str):
    sort_field = {
        "created_at": ("created_at", "createdAt"),
        "createdAt": ("created_at", "createdAt"),
        "updated_at": ("updated_at", "updatedAt"),
        "updatedAt": ("updated_at", "updatedAt"),
        "order_number": ("order_number", "orderNumber"),
        "orderNumber": ("order_number", "orderNumber"),
        "customer_name": ("customer_name", "customerName"),
        "customerName": ("customer_name", "customerName"),
        "offered_price": ("offered_price", "offeredPrice"),
        "offeredPrice": ("offered_price", "offeredPrice"),
        "final_price": ("final_price", "finalPrice"),
        "finalPrice": ("final_price", "finalPrice"),
    }.get(requested_sort, (requested_sort,))

    raw = _raw_value(doc, *sort_field)
    if requested_sort in {"created_at", "createdAt", "updated_at", "updatedAt"}:
        return _coerce_sort_datetime(raw)
    if isinstance(raw, (int, float)):
        return raw
    if raw is None:
        return ""
    return str(raw).lower()


def _serialize_raw(doc: dict) -> dict:
    doc = _to_json_safe(doc)
    payout = _raw_value(doc, "payout_details", "payoutDetails") or {}
    counter = _raw_value(doc, "counter_offer", "counterOffer") or {}
    created_at = _raw_value(doc, "created_at", "createdAt")
    updated_at = _raw_value(doc, "updated_at", "updatedAt")
    return {
        "id": str(doc.get("_id") or doc.get("id")), "_id": str(doc.get("_id") or doc.get("id")),
        "order_number": _raw_value(doc, "order_number", "orderNumber") or "", "orderNumber": _raw_value(doc, "order_number", "orderNumber") or "",
        "source": _raw_value(doc, "source") or "WEBSITE",
        "customer_name": _raw_value(doc, "customer_name", "customerName") or "", "customerName": _raw_value(doc, "customer_name", "customerName") or "",
        "customer_phone": _raw_value(doc, "customer_phone", "customerPhone") or "", "customerPhone": _raw_value(doc, "customer_phone", "customerPhone") or "",
        "customer_email": _raw_value(doc, "customer_email", "customerEmail"), "customerEmail": _raw_value(doc, "customer_email", "customerEmail"),
        "customer_address": _raw_value(doc, "customer_address", "customerAddress") or "", "customerAddress": _raw_value(doc, "customer_address", "customerAddress") or "",
        "postcode": _raw_value(doc, "postcode"),
        "device_id": str(_raw_value(doc, "device_id", "deviceId")) if _raw_value(doc, "device_id", "deviceId") is not None else None, "deviceId": str(_raw_value(doc, "device_id", "deviceId")) if _raw_value(doc, "device_id", "deviceId") is not None else None,
        "device_name": _raw_value(doc, "device_name", "deviceName") or "", "deviceName": _raw_value(doc, "device_name", "deviceName") or "",
        "network": _raw_value(doc, "network") or "",
        "device_grade": _raw_value(doc, "device_grade", "deviceGrade") or "", "deviceGrade": _raw_value(doc, "device_grade", "deviceGrade") or "",
        "storage": _raw_value(doc, "storage") or "",
        "offered_price": _raw_value(doc, "offered_price", "offeredPrice") or 0, "offeredPrice": _raw_value(doc, "offered_price", "offeredPrice") or 0,
        "final_price": _raw_value(doc, "final_price", "finalPrice"), "finalPrice": _raw_value(doc, "final_price", "finalPrice"),
        "postage_method": _raw_value(doc, "postage_method", "postageMethod") or "", "postageMethod": _raw_value(doc, "postage_method", "postageMethod") or "",
        "status": _raw_value(doc, "status") or "PENDING",
        "payment_method": _raw_value(doc, "payment_method", "paymentMethod") or "bank", "paymentMethod": _raw_value(doc, "payment_method", "paymentMethod") or "bank",
        "payment_status": _raw_value(doc, "payment_status", "paymentStatus") or "PENDING", "paymentStatus": _raw_value(doc, "payment_status", "paymentStatus") or "PENDING",
        "payout_details": {
            "account_name": _raw_value(payout, "account_name", "accountName"), "accountName": _raw_value(payout, "account_name", "accountName"),
            "account_number": _raw_value(payout, "account_number", "accountNumber"), "accountNumber": _raw_value(payout, "account_number", "accountNumber"),
            "sort_code": _raw_value(payout, "sort_code", "sortCode"), "sortCode": _raw_value(payout, "sort_code", "sortCode"),
        } if payout else None,
        "counter_offer": {
            "has_counter_offer": _raw_value(counter, "has_counter_offer", "hasCounterOffer") or False, "hasCounterOffer": _raw_value(counter, "has_counter_offer", "hasCounterOffer") or False,
            "latest_offer_id": _raw_value(counter, "latest_offer_id", "latestOfferId"), "latestOfferId": _raw_value(counter, "latest_offer_id", "latestOfferId"),
            "status": _raw_value(counter, "status"),
        } if counter else None,
        "notes": _raw_value(doc, "notes"),
        "admin_notes": _raw_value(doc, "admin_notes", "adminNotes"), "adminNotes": _raw_value(doc, "admin_notes", "adminNotes"),
        "tracking_number": _raw_value(doc, "tracking_number", "trackingNumber"), "trackingNumber": _raw_value(doc, "tracking_number", "trackingNumber"),
        "transaction_id": _raw_value(doc, "transaction_id", "transactionId"), "transactionId": _raw_value(doc, "transaction_id", "transactionId"),
        "partner_name": _raw_value(doc, "partner_name", "partnerName"), "partnerName": _raw_value(doc, "partner_name", "partnerName"),
        "price_revision_reason": _raw_value(doc, "price_revision_reason", "priceRevisionReason"), "priceRevisionReason": _raw_value(doc, "price_revision_reason", "priceRevisionReason"),
        "created_at": created_at or datetime.utcnow().isoformat(), "createdAt": created_at or datetime.utcnow().isoformat(),
        "updated_at": updated_at or datetime.utcnow().isoformat(), "updatedAt": updated_at or datetime.utcnow().isoformat(),
    }


def _serialize(o: Order) -> dict:
    # Handle missing fields gracefully for old database records
    try:
        payout = getattr(o, "payout_details", None)
        payout_data = None
        if payout:
            payout_data = {
                "account_name": getattr(payout, "account_name", None), "accountName": getattr(payout, "account_name", None),
                "account_number": getattr(payout, "account_number", None), "accountNumber": getattr(payout, "account_number", None),
                "sort_code": getattr(payout, "sort_code", None), "sortCode": getattr(payout, "sort_code", None),
            }
        counter = getattr(o, "counter_offer", None)
        counter_data = None
        if counter:
            counter_data = {
                "has_counter_offer": getattr(counter, "has_counter_offer", False), "hasCounterOffer": getattr(counter, "has_counter_offer", False),
                "latest_offer_id": getattr(counter, "latest_offer_id", None), "latestOfferId": getattr(counter, "latest_offer_id", None),
                "status": getattr(counter, "status", None),
            }
        return {
            "id": str(o.id), "_id": str(o.id),
            "order_number": getattr(o, "order_number", ""), "orderNumber": getattr(o, "order_number", ""),
            "source": getattr(o, "source", "WEBSITE"),
            "customer_name": getattr(o, "customer_name", ""), "customerName": getattr(o, "customer_name", ""),
            "customer_phone": getattr(o, "customer_phone", ""), "customerPhone": getattr(o, "customer_phone", ""),
            "customer_email": getattr(o, "customer_email", None), "customerEmail": getattr(o, "customer_email", None),
            "customer_address": getattr(o, "customer_address", ""), "customerAddress": getattr(o, "customer_address", ""),
            "postcode": getattr(o, "postcode", None),
            "device_id": getattr(o, "device_id", None), "deviceId": getattr(o, "device_id", None),
            "device_name": getattr(o, "device_name", ""), "deviceName": getattr(o, "device_name", ""),
            "network": getattr(o, "network", ""),
            "device_grade": getattr(o, "device_grade", ""), "deviceGrade": getattr(o, "device_grade", ""),
            "storage": getattr(o, "storage", ""),
            "offered_price": getattr(o, "offered_price", 0), "offeredPrice": getattr(o, "offered_price", 0),
            "final_price": getattr(o, "final_price", None), "finalPrice": getattr(o, "final_price", None),
            "postage_method": getattr(o, "postage_method", ""), "postageMethod": getattr(o, "postage_method", ""),
            "status": getattr(o, "status", "PENDING"),
            "payment_method": getattr(o, "payment_method", "bank"), "paymentMethod": getattr(o, "payment_method", "bank"),
            "payment_status": getattr(o, "payment_status", "PENDING"), "paymentStatus": getattr(o, "payment_status", "PENDING"),
            "payout_details": payout_data, "payoutDetails": payout_data,
            "counter_offer": counter_data, "counterOffer": counter_data,
            "notes": getattr(o, "notes", None),
            "admin_notes": getattr(o, "admin_notes", None), "adminNotes": getattr(o, "admin_notes", None),
            "tracking_number": getattr(o, "tracking_number", None), "trackingNumber": getattr(o, "tracking_number", None),
            "created_at": getattr(o, "created_at", datetime.utcnow()).isoformat() if getattr(o, "created_at", None) else datetime.utcnow().isoformat(), "createdAt": getattr(o, "created_at", datetime.utcnow()).isoformat() if getattr(o, "created_at", None) else datetime.utcnow().isoformat(),
            "updated_at": getattr(o, "updated_at", datetime.utcnow()).isoformat() if getattr(o, "updated_at", None) else datetime.utcnow().isoformat(), "updatedAt": getattr(o, "updated_at", datetime.utcnow()).isoformat() if getattr(o, "updated_at", None) else datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error serializing order {getattr(o, 'id', 'unknown')}: {str(e)}")
        # Return minimal safe data
        return {
            "id": str(o.id), "_id": str(o.id),
            "order_number": "ERROR", "orderNumber": "ERROR",
            "source": "WEBSITE",
            "customer_name": "", "customerName": "",
            "customer_phone": "", "customerPhone": "",
            "customer_email": None, "customerEmail": None,
            "customer_address": "", "customerAddress": "",
            "device_name": "", "deviceName": "",
            "network": "", "device_grade": "", "deviceGrade": "",
            "storage": "", "offered_price": 0, "offeredPrice": 0,
            "postage_method": "", "postageMethod": "",
            "status": "PENDING", "payment_status": "PENDING", "paymentStatus": "PENDING",
            "created_at": datetime.utcnow().isoformat(), "createdAt": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(), "updatedAt": datetime.utcnow().isoformat(),
        }
