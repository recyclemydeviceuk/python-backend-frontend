from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
import secrets
from app.models.counter_offer import CounterOffer
from app.models.order import Order
from app.schemas.counter_offer import CreateCounterOfferSchema, RespondCounterOfferSchema
from app.middleware.auth import get_current_admin
from app.services.email_service import send_counter_offer_email, send_counter_offer_accepted_email, send_counter_offer_declined_email
from app.config.constants import CounterOfferStatus, PaymentStatus
from app.utils.response import success_response, created_response
from app.utils.logger import logger

router = APIRouter(prefix="/counter-offers", tags=["Counter Offers"])


@router.post("", summary="Create counter offer", dependencies=[Depends(get_current_admin)])
async def create_counter_offer(body: CreateCounterOfferSchema):
    order = await Order.get(body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    offer = CounterOffer(
        order_id=str(order.id),
        order_number=order.order_number,
        device_name=order.device_name,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        original_price=order.offered_price,
        counter_price=body.counter_price,
        reason=body.reason,
        token=token,
        expires_at=expires_at,
    )
    await offer.insert()

    # Update order
    order.counter_offer.has_counter_offer = True
    order.counter_offer.latest_offer_id = str(offer.id)
    order.counter_offer.status = CounterOfferStatus.PENDING
    await order.save()

    if order.customer_email:
        await send_counter_offer_email(order, offer)

    logger.info(f"Counter offer created for order {order.order_number}")
    return created_response({"counter_offer": _serialize(offer)}, "Counter offer created and email sent")


@router.get("/token/{token}", summary="Get counter offer by token (public)")
async def get_by_token(token: str):
    offer = await CounterOffer.find_one(CounterOffer.token == token)
    if not offer:
        raise HTTPException(status_code=404, detail="Counter offer not found")
    order = await Order.get(offer.order_id)
    return success_response({"counter_offer": _serialize(offer), "order": _serialize_order(order) if order else None})


@router.post("/token/{token}/accept", summary="Accept counter offer (public)")
async def accept_offer(token: str):
    offer = await CounterOffer.find_one(CounterOffer.token == token)
    if not offer:
        raise HTTPException(status_code=404, detail="Counter offer not found")
    if offer.status != CounterOfferStatus.PENDING:
        raise HTTPException(status_code=400, detail="This offer has already been responded to")

    now = datetime.now(timezone.utc)
    if offer.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=400, detail="This offer has expired")

    offer.status = CounterOfferStatus.ACCEPTED
    offer.responded_at = now
    await offer.save()

    order = await Order.get(offer.order_id)
    if order:
        order.final_price = offer.counter_price
        order.counter_offer.status = CounterOfferStatus.ACCEPTED
        order.payment_status = PaymentStatus.PENDING
        await order.save()
        await send_counter_offer_accepted_email(order, offer)

    logger.info(f"Counter offer accepted: {offer.order_number}")
    return success_response({"message": "Counter offer accepted", "counter_offer": _serialize(offer)})


@router.post("/token/{token}/reject", summary="Reject counter offer (public)")
async def reject_offer(token: str):
    offer = await CounterOffer.find_one(CounterOffer.token == token)
    if not offer:
        raise HTTPException(status_code=404, detail="Counter offer not found")
    if offer.status != CounterOfferStatus.PENDING:
        raise HTTPException(status_code=400, detail="This offer has already been responded to")

    now = datetime.now(timezone.utc)
    if offer.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=400, detail="This offer has expired")

    offer.status = CounterOfferStatus.DECLINED
    offer.responded_at = now
    await offer.save()

    order = await Order.get(offer.order_id)
    if order:
        order.counter_offer.status = CounterOfferStatus.DECLINED
        await order.save()
        await send_counter_offer_declined_email(order, offer)

    logger.info(f"Counter offer rejected: {offer.order_number}")
    return success_response({"message": "Counter offer declined", "counter_offer": _serialize(offer)})


@router.get("", summary="Get all counter offers", dependencies=[Depends(get_current_admin)])
async def get_all(status: str = None):
    filters = []
    if status:
        filters.append(CounterOffer.status == status)
    offers = await CounterOffer.find(*filters).sort(-CounterOffer.created_at).to_list()
    return success_response({"counter_offers": [_serialize(o) for o in offers]})


@router.get("/order/{order_id}/all", summary="Get all counter offers for an order", dependencies=[Depends(get_current_admin)])
async def get_order_counter_offers(order_id: str):
    offers = await CounterOffer.find(CounterOffer.order_id == order_id).sort(-CounterOffer.created_at).to_list()
    return success_response({"counterOffers": [_serialize(o) for o in offers], "counter_offers": [_serialize(o) for o in offers]})


def _serialize(o: CounterOffer) -> dict:
    return {
        "id": str(o.id), "_id": str(o.id),
        "order_id": o.order_id, "orderId": o.order_id,
        "order_number": o.order_number, "orderNumber": o.order_number,
        "device_name": o.device_name, "deviceName": o.device_name,
        "customer_name": o.customer_name, "customerName": o.customer_name,
        "original_price": o.original_price, "originalPrice": o.original_price,
        "counter_price": o.counter_price, "counterPrice": o.counter_price,
        "reason": o.reason, "status": o.status,
        "token": o.token,
        "expires_at": o.expires_at.isoformat(), "expiresAt": o.expires_at.isoformat(),
        "responded_at": o.responded_at.isoformat() if o.responded_at else None,
        "respondedAt": o.responded_at.isoformat() if o.responded_at else None,
        "created_at": o.created_at.isoformat(), "createdAt": o.created_at.isoformat(),
    }


def _serialize_order(o: Order) -> dict:
    return {
        "id": str(o.id), "_id": str(o.id),
        "order_number": o.order_number, "orderNumber": o.order_number,
        "device_name": o.device_name, "deviceName": o.device_name,
        "customer_name": o.customer_name, "customerName": o.customer_name,
        "offered_price": o.offered_price, "offeredPrice": o.offered_price,
        "status": o.status,
    }
