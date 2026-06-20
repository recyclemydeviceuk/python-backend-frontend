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

        # Fetch the most-recent counter offer per order in ONE batch so the
        # orders list can show the revised price + customer response inline.
        # Previously the admin only saw it on the detail page after acceptance.
        order_ids = [
            str(d.get("_id") or d.get("id"))
            for d in docs if d.get("_id") or d.get("id")
        ]
        latest_offers = await _fetch_latest_counter_offers(order_ids)

        if limit is None:
            return success_response([
                _serialize_raw(o, latest_offers.get(str(o.get("_id") or o.get("id"))))
                for o in docs
            ])

        skip = (page - 1) * limit
        paged_docs = docs[skip:skip + limit]

        return paginated_response(
            [
                _serialize_raw(o, latest_offers.get(str(o.get("_id") or o.get("id"))))
                for o in paged_docs
            ],
            page, limit, total,
        )
    except Exception as e:
        logger.exception(f"Failed to get orders list: {e}")
        raise HTTPException(status_code=500, detail="Failed to load orders")


async def _fetch_latest_counter_offers(order_ids: list) -> dict:
    """Return {order_id: latest counter offer dict} for the given ids.
    Looks up the offers collection directly (avoids round-trip per row).
    Best-effort: any failure returns an empty map and orders still render."""
    if not order_ids:
        return {}
    try:
        from app.models.counter_offer import CounterOffer
        coll = CounterOffer.get_motor_collection()
        cursor = coll.find(
            {"order_id": {"$in": order_ids}},
        ).sort("created_at", -1)
        rows = await cursor.to_list(length=None)
        latest: dict = {}
        for r in rows:
            oid = r.get("order_id")
            if oid and oid not in latest:
                latest[oid] = r
        return latest
    except Exception as e:
        logger.warning(f"Failed to fetch latest counter offers: {e}")
        return {}


@router.get("/{order_id}", summary="Get order by ID", dependencies=[Depends(get_current_admin)])
async def get_order(order_id: str):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    latest_offers = await _fetch_latest_counter_offers([str(order.id)])
    return success_response({
        "order": _serialize(order, latest_offers.get(str(order.id))),
    })


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

    normalized_new_status = None
    if body.status is not None:
        normalized_new_status = _normalize_status(str(body.status))
        order.status = normalized_new_status
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

    # Auto payment status — only override if the caller did NOT pass an
    # explicit payment_status. Use the normalized status so "Paid"/"paid"
    # both flip the payment column correctly.
    if normalized_new_status and body.payment_status is None:
        if normalized_new_status == "PAID":
            order.payment_status = PaymentStatus.PAID
        else:
            order.payment_status = PaymentStatus.PENDING

    order.updated_at = datetime.utcnow()
    await order.save()

    # Email notifications — mirror Node.js emailService
    if old_status != order.status:
        if order.status == "PAID":
            await send_order_completion_email(order)
            await send_payment_confirmation(order)
        elif order.status != "PRICE_REVISED":
            # Skip the generic status email for PRICE_REVISED — it quotes the
            # original full price. A genuine revision sends the dedicated
            # price-revision email below (with the correct revised amount).
            await send_order_status_update(order, old_status)
    if body.final_price and body.final_price != old_final_price and order.price_revision_reason:
        await send_price_revision_email(order, old_final_price, body.final_price, order.price_revision_reason)

    logger.info(f"Order updated: {order.order_number}")
    return success_response({"order": _serialize(order)}, "Order updated successfully")


_LEGACY_STATUS_ALIASES = {
    # Map legacy / human-readable names from older OrderStatus DB rows back to
    # the canonical workflow values backend code (emails, payment flip) checks.
    "pending":       "RECEIVED",
    "received":      "RECEIVED",
    "new":           "RECEIVED",
    "collected":     "DEVICE_RECEIVED",
    "received_device": "DEVICE_RECEIVED",
    "confirmed":     "INSPECTION_PASSED",
    "under review":  "INSPECTION_PASSED",
    "under_review":  "INSPECTION_PASSED",
    "reviewing":     "INSPECTION_PASSED",
    "completed":     "PAID",
    "paid":          "PAID",
    "complete":      "PAID",
    "cancelled":     "CANCELLED",
    "canceled":      "CANCELLED",
    "closed":        "CLOSED",
    "pack sent":     "PACK_SENT",
    "pack_sent":     "PACK_SENT",
    "payout ready":  "PAYOUT_READY",
    "payout_ready":  "PAYOUT_READY",
    "price revised": "PRICE_REVISED",
    "price_revised": "PRICE_REVISED",
    "inspection passed": "INSPECTION_PASSED",
    "inspection failed": "INSPECTION_FAILED",
}


def _normalize_status(raw: str) -> str:
    """Accept any of the historical status names and return the canonical
    workflow value backend code expects."""
    if not raw:
        return raw
    s = str(raw).strip()
    if s.upper() in {
        "RECEIVED", "PACK_SENT", "DEVICE_RECEIVED", "INSPECTION_PASSED",
        "INSPECTION_FAILED", "PRICE_REVISED", "PAYOUT_READY",
        "PAID", "CLOSED", "CANCELLED",
    }:
        return s.upper()
    return _LEGACY_STATUS_ALIASES.get(s.lower(), s)


@router.patch("/{order_id}/status", summary="Update order status", dependencies=[Depends(get_current_admin)])
async def update_status(order_id: str, body: UpdateOrderStatusSchema):
    order = await Order.get(order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"No order was found with id '{order_id}'.",
        )

    if not body.status or not str(body.status).strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "The field 'status' is required and cannot be empty. "
                "Please choose one of: Received, Pack Sent, Device Received, "
                "Inspection Passed, Inspection Failed, Price Revised, "
                "Payout Ready, Paid, Closed, Cancelled."
            ),
        )

    new_status = _normalize_status(body.status)
    old_status = order.status
    order.status = new_status
    order.payment_status = (
        PaymentStatus.PAID if new_status == "PAID" else PaymentStatus.PENDING
    )
    order.updated_at = datetime.utcnow()
    try:
        await order.save()
    except Exception as e:
        logger.exception(f"Failed to save status for order {order.order_number}: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to update the order. Please try again — if the problem "
                "persists, contact the developer."
            ),
        )

    # Emails are best-effort. Never fail the API just because SES is down.
    try:
        if new_status == "PAID":
            await send_order_completion_email(order)
            await send_payment_confirmation(order)
        elif new_status == "PRICE_REVISED":
            # "Price Revised" is driven by the Counter Offer flow, which sends
            # its own correct email (revised price + accept/decline links). The
            # generic status email here would quote the ORIGINAL full price, so
            # skip it to avoid confusing the customer with the wrong amount.
            pass
        elif old_status != new_status:
            await send_order_status_update(order, old_status, comment=body.comment)
    except Exception as e:
        logger.warning(f"Status email failed for {order.order_number}: {e}")

    logger.info(f"Order status: {order.order_number} {old_status} -> {new_status}")
    return success_response({"order": _serialize(order)}, "Order status updated successfully.")


@router.delete("/{order_id}", summary="Delete order", dependencies=[Depends(get_current_admin)])
async def delete_order(order_id: str):
    # Delete straight from the raw collection by _id. We deliberately do NOT load
    # the order through the Beanie/Pydantic model first (Order.get), because OLD
    # orders created by the previous backend are often missing fields the current
    # Order model marks as required (postage_method, customer_address,
    # device_grade, ...). Loading them raises a ValidationError, so the delete
    # 500'd and the row reappeared — admins could SEE these orders (the list uses
    # a raw motor query) but never delete them, while newer well-formed orders
    # deleted fine. Matching _id directly sidesteps model validation entirely.
    from bson import ObjectId as BsonObjectId

    collection = Order.get_motor_collection()

    # Build candidate _id matches: the raw string exactly as stored, plus its
    # ObjectId form when the id is a valid 24-hex string. Covers both ObjectId
    # _ids (the norm) and any legacy string _ids.
    candidates: list = [order_id]
    try:
        candidates.append(BsonObjectId(order_id))
    except Exception:
        pass

    # Cascade-delete any counter offers tied to this order so the collection
    # doesn't accumulate orphaned offer rows. Best-effort — never block the
    # order delete on it.
    try:
        from app.models.counter_offer import CounterOffer
        co = CounterOffer.get_motor_collection()
        await co.delete_many({"order_id": {"$in": [str(c) for c in candidates]}})
    except Exception as e:
        logger.warning(f"Failed to cascade-delete counter offers for {order_id}: {e}")

    try:
        result = await collection.delete_one({"_id": {"$in": candidates}})
    except Exception as e:
        logger.exception(f"Failed to delete order id={order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to delete the order. Please try again — if the "
                "problem continues, contact the developer."
            ),
        )

    if result.deleted_count == 0:
        # Idempotent: nothing matched (already deleted, or unknown id). The admin
        # panel optimistically drops the row, so report success either way.
        logger.info(f"Delete matched no order for id={order_id} (no-op)")
        return success_response({"message": "Order already removed"})

    logger.info(f"Order deleted: id={order_id}")
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


def _serialize_raw(doc: dict, latest_offer: Optional[dict] = None) -> dict:
    doc = _to_json_safe(doc)
    payout = _raw_value(doc, "payout_details", "payoutDetails") or {}
    counter = _raw_value(doc, "counter_offer", "counterOffer") or {}
    created_at = _raw_value(doc, "created_at", "createdAt")
    updated_at = _raw_value(doc, "updated_at", "updatedAt")

    # Surface the latest counter offer's revised price so the admin orders
    # list can show it next to the £ Offered column. Without this, the
    # main page only ever showed the original quote — admins had to open
    # each order to know the revised amount.
    offer_revised_price = None
    offer_status = None
    offer_responded_at = None
    offer_reason = None
    if latest_offer:
        offer_revised_price = latest_offer.get("revised_price")
        offer_status = latest_offer.get("status")
        offer_responded_at = latest_offer.get("responded_at")
        if isinstance(offer_responded_at, datetime):
            offer_responded_at = offer_responded_at.isoformat()
        offer_reason = latest_offer.get("reason")
    # Fall back to the values persisted on the order's embedded counter_offer.
    # These are written the moment a counter offer is SENT, so the revised
    # price is known even if the join to the counteroffers collection misses.
    if offer_revised_price is None:
        offer_revised_price = _raw_value(counter, "revised_price", "revisedPrice")
    if offer_status is None:
        offer_status = _raw_value(counter, "status")
    if offer_reason is None:
        offer_reason = _raw_value(counter, "reason")
    if offer_responded_at is None:
        offer_responded_at = _raw_value(counter, "responded_at", "respondedAt")
        if isinstance(offer_responded_at, datetime):
            offer_responded_at = offer_responded_at.isoformat()
    return {
        "id": str(doc.get("_id") or doc.get("id")), "_id": str(doc.get("_id") or doc.get("id")),
        "order_number": _raw_value(doc, "order_number", "orderNumber") or "", "orderNumber": _raw_value(doc, "order_number", "orderNumber") or "",
        "source": _raw_value(doc, "source") or "WEBSITE",
        "customer_name": _raw_value(doc, "customer_name", "customerName") or "", "customerName": _raw_value(doc, "customer_name", "customerName") or "",
        "customer_phone": _raw_value(doc, "customer_phone", "customerPhone") or "", "customerPhone": _raw_value(doc, "customer_phone", "customerPhone") or "",
        "customer_email": _raw_value(doc, "customer_email", "customerEmail"), "customerEmail": _raw_value(doc, "customer_email", "customerEmail"),
        "customer_address": _raw_value(doc, "customer_address", "customerAddress") or "", "customerAddress": _raw_value(doc, "customer_address", "customerAddress") or "",
        "city": _raw_value(doc, "city"),
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
            "has_counter_offer": (
                _raw_value(counter, "has_counter_offer", "hasCounterOffer")
                or bool(latest_offer) or False
            ),
            "hasCounterOffer": (
                _raw_value(counter, "has_counter_offer", "hasCounterOffer")
                or bool(latest_offer) or False
            ),
            "latest_offer_id": _raw_value(counter, "latest_offer_id", "latestOfferId"), "latestOfferId": _raw_value(counter, "latest_offer_id", "latestOfferId"),
            "status": offer_status or _raw_value(counter, "status"),
            "revised_price": offer_revised_price, "revisedPrice": offer_revised_price,
            "responded_at": offer_responded_at, "respondedAt": offer_responded_at,
            "reason": offer_reason,
        } if (counter or latest_offer) else None,
        "notes": _raw_value(doc, "notes"),
        "admin_notes": _raw_value(doc, "admin_notes", "adminNotes"), "adminNotes": _raw_value(doc, "admin_notes", "adminNotes"),
        "tracking_number": _raw_value(doc, "tracking_number", "trackingNumber"), "trackingNumber": _raw_value(doc, "tracking_number", "trackingNumber"),
        "transaction_id": _raw_value(doc, "transaction_id", "transactionId"), "transactionId": _raw_value(doc, "transaction_id", "transactionId"),
        "partner_name": _raw_value(doc, "partner_name", "partnerName"), "partnerName": _raw_value(doc, "partner_name", "partnerName"),
        "price_revision_reason": _raw_value(doc, "price_revision_reason", "priceRevisionReason"), "priceRevisionReason": _raw_value(doc, "price_revision_reason", "priceRevisionReason"),
        "created_at": created_at or datetime.utcnow().isoformat(), "createdAt": created_at or datetime.utcnow().isoformat(),
        "updated_at": updated_at or datetime.utcnow().isoformat(), "updatedAt": updated_at or datetime.utcnow().isoformat(),
    }


def _serialize(o: Order, latest_offer: Optional[dict] = None) -> dict:
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
        offer_revised_price = None
        offer_status = None
        offer_responded_at = None
        offer_reason = None
        if latest_offer:
            offer_revised_price = latest_offer.get("revised_price")
            offer_status = latest_offer.get("status")
            offer_responded_at = latest_offer.get("responded_at")
            if isinstance(offer_responded_at, datetime):
                offer_responded_at = offer_responded_at.isoformat()
            offer_reason = latest_offer.get("reason")
        # Fall back to the values persisted on the order's embedded
        # counter_offer (written the moment the offer is SENT).
        if counter is not None:
            if offer_revised_price is None:
                offer_revised_price = getattr(counter, "revised_price", None)
            if offer_status is None:
                offer_status = getattr(counter, "status", None)
            if offer_reason is None:
                offer_reason = getattr(counter, "reason", None)
            if offer_responded_at is None:
                _ra = getattr(counter, "responded_at", None)
                offer_responded_at = _ra.isoformat() if isinstance(_ra, datetime) else _ra
        counter_data = None
        if counter or latest_offer:
            counter_data = {
                "has_counter_offer": (
                    getattr(counter, "has_counter_offer", False)
                    or bool(latest_offer)
                ),
                "hasCounterOffer": (
                    getattr(counter, "has_counter_offer", False)
                    or bool(latest_offer)
                ),
                "latest_offer_id": getattr(counter, "latest_offer_id", None), "latestOfferId": getattr(counter, "latest_offer_id", None),
                "status": offer_status or getattr(counter, "status", None),
                "revised_price": offer_revised_price, "revisedPrice": offer_revised_price,
                "responded_at": offer_responded_at, "respondedAt": offer_responded_at,
                "reason": offer_reason,
            }
        return {
            "id": str(o.id), "_id": str(o.id),
            "order_number": getattr(o, "order_number", ""), "orderNumber": getattr(o, "order_number", ""),
            "source": getattr(o, "source", "WEBSITE"),
            "customer_name": getattr(o, "customer_name", ""), "customerName": getattr(o, "customer_name", ""),
            "customer_phone": getattr(o, "customer_phone", ""), "customerPhone": getattr(o, "customer_phone", ""),
            "customer_email": getattr(o, "customer_email", None), "customerEmail": getattr(o, "customer_email", None),
            "customer_address": getattr(o, "customer_address", ""), "customerAddress": getattr(o, "customer_address", ""),
            "city": getattr(o, "city", None),
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
