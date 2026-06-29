from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
from app.models.counter_offer import CounterOffer, DeviceImage
from app.models.order import Order
from app.schemas.counter_offer import CreateCounterOfferSchema, RespondCounterOfferSchema
from app.middleware.auth import get_current_admin
from app.services.email_service import (
    send_counter_offer_email,
    send_counter_offer_accepted_email,
    send_counter_offer_declined_email,
    send_admin_counter_offer_response,
)
from app.config.constants import CounterOfferStatus, PaymentStatus, OrderStatus
from app.utils.response import success_response, created_response
from app.utils.logger import logger

router = APIRouter(prefix="/counter-offers", tags=["Counter Offers"])


def _err(status: int, message: str, field: Optional[str] = None):
    """Consistent JSON error body the admin panel can parse."""
    detail = {"success": False, "error": message, "message": message}
    if field:
        detail["field"] = field
    raise HTTPException(status_code=status, detail=detail)


@router.post("", summary="Create counter offer", dependencies=[Depends(get_current_admin)])
async def create_counter_offer(body: CreateCounterOfferSchema):
    # ── Validate input ──────────────────────────────────────────────────
    if not body.order_id:
        _err(422,
             "The field 'order_id' is required to create a counter offer.",
             field="order_id")

    if body.revised_price is None:
        _err(422,
             "The field 'revised_price' is required and must be a positive number.",
             field="revised_price")

    if body.revised_price < 0:
        _err(422,
             "The 'revised_price' must be zero or greater.",
             field="revised_price")

    if not body.reason or not body.reason.strip():
        _err(422,
             "The field 'reason' is required — please explain why the price has been adjusted.",
             field="reason")

    if len(body.reason.strip()) < 20:
        _err(422,
             "The 'reason' must be at least 20 characters so the customer understands the adjustment.",
             field="reason")

    # ── Load order ──────────────────────────────────────────────────────
    try:
        order = await Order.get(body.order_id)
    except Exception:
        order = None
    if not order:
        _err(404,
             f"No order was found with id '{body.order_id}'. "
             f"Please verify the order ID and try again.",
             field="order_id")

    # ── Build counter offer using CORRECT model field names ─────────────
    review_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=48)

    device_image_objects = []
    if body.device_images:
        now = datetime.utcnow()
        for img in body.device_images:
            try:
                url = img.get("url") if isinstance(img, dict) else None
                key = img.get("key") if isinstance(img, dict) else None
                if url and key:
                    device_image_objects.append(DeviceImage(url=url, key=key, uploaded_at=now))
            except Exception:
                continue

    try:
        offer = CounterOffer(
            order_id=str(order.id),
            order_number=order.order_number,
            original_price=float(order.offered_price or 0),
            revised_price=float(body.revised_price),
            reason=body.reason.strip(),
            device_images=device_image_objects,
            status=CounterOfferStatus.PENDING,
            expires_at=expires_at,
            review_token=review_token,
        )
        await offer.insert()
    except Exception as e:
        logger.exception(f"Failed to persist counter offer for order {order.order_number}: {e}")
        _err(500,
             "An internal error occurred while saving the counter offer. "
             "Please retry — if the problem continues, contact the developer.")

    # ── Update parent order ─────────────────────────────────────────────
    try:
        if not order.counter_offer:
            from app.models.order import CounterOfferEmbed
            order.counter_offer = CounterOfferEmbed()
        order.counter_offer.has_counter_offer = True
        order.counter_offer.latest_offer_id = str(offer.id)
        order.counter_offer.status = CounterOfferStatus.PENDING
        # Surface the revision on the order itself the moment it's sent, so the
        # admin orders list/detail shows the revised price + reason immediately
        # — previously the revised amount was only visible after the customer
        # ACCEPTED (because accept_offer set final_price/status). Persist the
        # actual numbers on the embedded counter_offer so the backend never
        # has to rely on a live join to know what we offered the customer.
        order.counter_offer.revised_price = float(offer.revised_price)
        order.counter_offer.reason = offer.reason
        # Set final_price the moment the offer is SENT — not only when the
        # customer accepts. The admin UI (list + detail) falls back to
        # finalPrice to render the price, so without this the revised amount
        # stayed invisible until acceptance. This restores the behaviour of
        # the legacy admin_panel counter-offer flow, which set final_price
        # here too. Because create runs first, the value persists through a
        # later DECLINE, and ACCEPT re-sets the same number — so the revised
        # price shows in all three states (sent / accepted / declined).
        order.final_price = float(offer.revised_price)
        order.status = OrderStatus.PRICE_REVISED
        order.price_revision_reason = offer.reason
        order.updated_at = datetime.utcnow()
        await order.save()
    except Exception as e:
        logger.warning(f"Counter offer saved but parent order update failed: {e}")

    # ── Email customer (best-effort, never block the response) ──────────
    if order.customer_email:
        try:
            await send_counter_offer_email(order, offer)
        except Exception as e:
            logger.warning(f"Counter offer email failed for {order.order_number}: {e}")

    logger.info(f"Counter offer created for order {order.order_number}: £{offer.revised_price}")
    return created_response(
        {"counter_offer": _serialize(offer)},
        "Counter offer created successfully and customer email has been sent.",
    )


@router.get("/token/{token}", summary="Get counter offer by token (public)")
async def get_by_token(token: str):
    offer = await CounterOffer.find_one(CounterOffer.review_token == token)
    if not offer:
        _err(404,
             "This counter offer link is invalid or has expired. "
             "Please contact support if you believe this is in error.")
    order = await Order.get(offer.order_id)
    return success_response({
        "counter_offer": _serialize(offer),
        "order": _serialize_order(order) if order else None,
    })


@router.post("/token/{token}/accept", summary="Accept counter offer (public)")
async def accept_offer(token: str):
    offer = await CounterOffer.find_one(CounterOffer.review_token == token)
    if not offer:
        _err(404, "This counter offer link is invalid or has expired.")
    if offer.status != CounterOfferStatus.PENDING:
        _err(400,
             "This counter offer has already been responded to and cannot be changed.")
    if offer.is_expired():
        _err(400,
             "This counter offer has expired (offers are valid for 48 hours). "
             "Please contact support if you still wish to proceed.")

    now = datetime.utcnow()
    offer.status = CounterOfferStatus.ACCEPTED
    offer.customer_response = "ACCEPTED"
    offer.responded_at = now
    offer.updated_at = now
    await offer.save()

    order = await Order.get(offer.order_id)
    if order:
        order.final_price = offer.revised_price
        if order.counter_offer:
            order.counter_offer.status = CounterOfferStatus.ACCEPTED
            order.counter_offer.revised_price = float(offer.revised_price)
            order.counter_offer.reason = offer.reason
            order.counter_offer.responded_at = now
        # Move the order into PRICE_REVISED so the admin list shows the
        # change immediately — without this, accepted offers sat under
        # whatever status the order was in (e.g. DEVICE_RECEIVED) and the
        # revised price was effectively invisible on the main page.
        order.status = OrderStatus.PRICE_REVISED
        order.payment_status = PaymentStatus.PENDING
        order.price_revision_reason = offer.reason
        order.updated_at = now
        await order.save()
        try:
            await send_counter_offer_accepted_email(order, offer)
        except Exception as e:
            logger.warning(f"Counter offer accepted email failed: {e}")
        try:
            await send_admin_counter_offer_response(order, offer, accepted=True)
        except Exception as e:
            logger.warning(f"Admin counter offer accepted notification failed: {e}")

    logger.info(f"Counter offer accepted: {offer.order_number}")
    return success_response(
        {"counter_offer": _serialize(offer)},
        "Counter offer accepted successfully.",
    )


@router.post("/token/{token}/reject", summary="Decline counter offer (public)")
async def reject_offer(token: str, body: Optional[RespondCounterOfferSchema] = None):
    offer = await CounterOffer.find_one(CounterOffer.review_token == token)
    if not offer:
        _err(404, "This counter offer link is invalid or has expired.")
    if offer.status != CounterOfferStatus.PENDING:
        _err(400, "This counter offer has already been responded to.")
    if offer.is_expired():
        _err(400, "This counter offer has expired.")

    now = datetime.utcnow()
    offer.status = CounterOfferStatus.DECLINED
    offer.customer_response = "DECLINED"
    offer.responded_at = now
    offer.updated_at = now
    if body and body.feedback:
        offer.customer_feedback = body.feedback.strip()
    await offer.save()

    order = await Order.get(offer.order_id)
    if order:
        if order.counter_offer:
            order.counter_offer.status = CounterOfferStatus.DECLINED
            order.counter_offer.revised_price = float(offer.revised_price)
            order.counter_offer.reason = offer.reason
            order.counter_offer.responded_at = now
        # Keep final_price pinned to the revised amount on decline too, so the
        # order's price column keeps showing what we offered (the order stays
        # in PRICE_REVISED for manual WhatsApp follow-up). Mirrors accept_offer.
        order.final_price = float(offer.revised_price)
        # Do NOT auto-cancel. Keep the order visible on the admin back-end under
        # PRICE_REVISED with the revised price + reason and a "Declined" tag, so
        # staff can follow up (e.g. on WhatsApp) and choose the final status
        # themselves. Auto-cancelling here hid the revised price and slammed the
        # order to Cancelled before staff could act.
        order.status = OrderStatus.PRICE_REVISED
        order.price_revision_reason = offer.reason
        order.updated_at = now
        await order.save()
        # No automatic customer email on decline — declines are handled manually
        # (WhatsApp). Admins are still notified out-of-band below.
        try:
            await send_admin_counter_offer_response(order, offer, accepted=False)
        except Exception as e:
            logger.warning(f"Admin counter offer declined notification failed: {e}")

    logger.info(f"Counter offer declined: {offer.order_number}")
    return success_response(
        {"counter_offer": _serialize(offer)},
        "Counter offer declined.",
    )


@router.get("", summary="Get all counter offers", dependencies=[Depends(get_current_admin)])
async def get_all(status: str = None):
    filters = []
    if status:
        filters.append(CounterOffer.status == status)
    offers = await CounterOffer.find(*filters).sort(-CounterOffer.created_at).to_list()
    return success_response({"counter_offers": [_serialize(o) for o in offers]})


@router.get("/order/{order_id}", summary="Get latest counter offer for order",
            dependencies=[Depends(get_current_admin)])
async def get_latest_for_order(order_id: str):
    """Used by the admin panel to display the current counter-offer status
    on an order detail page."""
    offer = await CounterOffer.find(
        CounterOffer.order_id == order_id
    ).sort(-CounterOffer.created_at).limit(1).to_list()
    return success_response({
        "counter_offer": _serialize(offer[0]) if offer else None,
    })


@router.get("/order/{order_id}/all", summary="Get all counter offers for an order",
            dependencies=[Depends(get_current_admin)])
async def get_order_counter_offers(order_id: str):
    offers = await CounterOffer.find(
        CounterOffer.order_id == order_id
    ).sort(-CounterOffer.created_at).to_list()
    return success_response({
        "counterOffers": [_serialize(o) for o in offers],
        "counter_offers": [_serialize(o) for o in offers],
    })


def _serialize(o: CounterOffer) -> dict:
    """Dual snake_case + camelCase shape so both the public web pages
    (JS) and the React admin panel (TS) can consume the same response."""
    return {
        "id": str(o.id), "_id": str(o.id),
        "order_id": o.order_id, "orderId": o.order_id,
        "order_number": o.order_number, "orderNumber": o.order_number,
        "original_price": o.original_price, "originalPrice": o.original_price,
        "revised_price": o.revised_price, "revisedPrice": o.revised_price,
        # Backwards-compat aliases for older clients that read counter_price/counterPrice:
        "counter_price": o.revised_price, "counterPrice": o.revised_price,
        "reason": o.reason,
        "status": o.status,
        "device_images": [
            {"url": img.url, "key": img.key,
             "uploaded_at": img.uploaded_at.isoformat(),
             "uploadedAt": img.uploaded_at.isoformat()}
            for img in (o.device_images or [])
        ],
        "deviceImages": [
            {"url": img.url, "key": img.key,
             "uploaded_at": img.uploaded_at.isoformat(),
             "uploadedAt": img.uploaded_at.isoformat()}
            for img in (o.device_images or [])
        ],
        "review_token": o.review_token, "reviewToken": o.review_token,
        "token": o.review_token,  # backwards-compat
        "customer_response": o.customer_response, "customerResponse": o.customer_response,
        "customer_feedback": o.customer_feedback, "customerFeedback": o.customer_feedback,
        "expires_at": o.expires_at.isoformat(), "expiresAt": o.expires_at.isoformat(),
        "responded_at": o.responded_at.isoformat() if o.responded_at else None,
        "respondedAt": o.responded_at.isoformat() if o.responded_at else None,
        "created_at": o.created_at.isoformat(), "createdAt": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(), "updatedAt": o.updated_at.isoformat(),
    }


def _serialize_order(o: Order) -> dict:
    return {
        "id": str(o.id), "_id": str(o.id),
        "order_number": o.order_number, "orderNumber": o.order_number,
        "device_name": o.device_name, "deviceName": o.device_name,
        "customer_name": o.customer_name, "customerName": o.customer_name,
        "customer_email": o.customer_email, "customerEmail": o.customer_email,
        "offered_price": o.offered_price, "offeredPrice": o.offered_price,
        "status": o.status,
    }
