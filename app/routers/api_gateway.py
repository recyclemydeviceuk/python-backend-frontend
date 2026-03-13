import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.order import Order
from app.models.api_log import ApiLog
from app.models.device import Device
from app.models.pricing import Pricing
from app.middleware.partner_auth import get_current_partner
from app.utils.order_number import generate_unique_order_number
from app.utils.response import success_response, created_response
from app.config.constants import OrderSource, PostageMethod, PaymentMethod, PaymentStatus
from app.utils.logger import logger
from app.services.email_service import send_order_confirmation

router = APIRouter(prefix="/gateway", tags=["API Gateway"])


class GatewayOrderSchema(BaseModel):
    model_config = {"populate_by_name": True}
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    customer_address: str
    postage_method: str                  # "label" or "postbag"
    device_name: str
    network: str
    device_grade: str                    # "NEW", "GOOD", "BROKEN"
    offered_price: float
    storage: Optional[str] = None
    bank_name: Optional[str] = Field(None, alias="payout_account_name")
    account_number: Optional[str] = Field(None, alias="payout_account_number")
    sort_code: Optional[str] = Field(None, alias="payout_sort_code")
    transaction_id: Optional[str] = None
    device_id: Optional[str] = None

    def __init__(self, **data):
        if "payout_account_name" in data and "bank_name" not in data:
            data["bank_name"] = data["payout_account_name"]
        if "payout_account_number" in data and "account_number" not in data:
            data["account_number"] = data["payout_account_number"]
        if "payout_sort_code" in data and "sort_code" not in data:
            data["sort_code"] = data["payout_sort_code"]
        super().__init__(**data)


async def _log_api_request(
    request: Request,
    status_code: int,
    success: bool,
    order_number: Optional[str],
    error: Optional[str],
    response_time_ms: int,
    partner_name: Optional[str] = None,
):
    """Log every API gateway request to ApiLog collection."""
    try:
        log = ApiLog(
            method=request.method,
            endpoint=str(request.url.path),
            status_code=status_code,
            source_ip=request.client.host if request.client else "unknown",
            payload=str({"order_number": order_number, "error": error, "partner_name": partner_name}),
            error=error,
            response_time=response_time_ms,
            success=success,
            order_number=order_number,
        )
        await log.insert()
    except Exception as e:
        logger.error(f"Failed to log API request: {e}")


@router.post("/decisiontech", summary="Create order via partner API (DecisionTech integration)")
async def create_external_order(
    request: Request,
    body: GatewayOrderSchema,
    partner=Depends(get_current_partner),
):
    """POST /api/gateway/decisiontech — mirrors Node.js createExternalOrder."""
    start_time = time.time()

    # ── 1. Validate required fields ─────────────────────────────────────────
    required = {
        "customer_name": body.customer_name,
        "customer_phone": body.customer_phone,
        "customer_address": body.customer_address,
        "device_name": body.device_name,
        "network": body.network,
        "device_grade": body.device_grade,
        "offered_price": body.offered_price,
        "postage_method": body.postage_method,
    }
    missing = [k for k, v in required.items() if not v and v != 0]
    if missing:
        msg = f"Missing required fields: {', '.join(missing)}"
        await _log_api_request(request, 422, False, None, msg, _ms(start_time), partner.name)
        return JSONResponse(status_code=422, content={"error": msg})

    # ── 2. Validate postage_method ───────────────────────────────────────────
    if body.postage_method not in ("label", "postbag"):
        msg = "Invalid postage_method. Must be 'label' or 'postbag'"
        await _log_api_request(request, 422, False, None, msg, _ms(start_time), partner.name)
        return JSONResponse(status_code=422, content={"error": msg})

    # ── 3. Validate device_grade ─────────────────────────────────────────────
    grade = body.device_grade.upper()
    if grade not in ("NEW", "GOOD", "BROKEN"):
        msg = "Invalid device_grade. Must be NEW, GOOD, or BROKEN"
        await _log_api_request(request, 422, False, None, msg, _ms(start_time), partner.name)
        return JSONResponse(status_code=422, content={"error": msg})

    # ── 4. Look up device by fullName ────────────────────────────────────────
    requested_device_name = body.device_name.strip().lower()
    active_devices = await Device.find(Device.is_active == True).to_list()
    device = next(
        (
            d for d in active_devices
            if ((d.full_name or "").strip().lower() == requested_device_name)
            or ((d.name or "").strip().lower() == requested_device_name)
        ),
        None,
    )
    if not device:
        msg = f"Device not found: {body.device_name}. Please use a valid device from our catalog."
        await _log_api_request(request, 404, False, None, msg, _ms(start_time), partner.name)
        return JSONResponse(status_code=404, content={"error": msg})

    # ── 5. Validate network/storage pricing combo if storage provided ────────
    if body.storage:
        requested_network = body.network.strip().lower()
        requested_storage = body.storage.strip().lower()
        pricing_collection = Pricing.get_motor_collection()
        pricing_query = {
            "$or": [
                {"device_id": str(device.id)},
                {"deviceId": str(device.id)},
            ]
        }
        try:
            device_oid = ObjectId(str(device.id))
            pricing_query["$or"].extend([
                {"device_id": device_oid},
                {"deviceId": device_oid},
            ])
        except Exception:
            pass

        raw_pricing_rows = await pricing_collection.find(pricing_query).to_list(length=None)
        pricing_rows = []
        for row in raw_pricing_rows:
            try:
                pricing_rows.append(Pricing.model_validate(row))
            except Exception:
                continue

        pricing_entry = next(
            (
                p for p in pricing_rows
                if (p.network or "").strip().lower() == requested_network
                and (p.storage or "").strip().lower() == requested_storage
            ),
            None,
        )
        if not pricing_entry:
            msg = f"Invalid configuration: {body.network} / {body.storage} is not available for {body.device_name}. Please check available options."
            await _log_api_request(request, 400, False, None, msg, _ms(start_time), partner.name)
            return JSONResponse(status_code=400, content={"error": msg})

    # ── 6. Create order ──────────────────────────────────────────────────────
    order_number = await generate_unique_order_number()

    from app.models.order import PayoutDetails, CounterOfferEmbed
    order = Order(
        order_number=order_number,
        source=OrderSource.API,
        status="RECEIVED",
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        customer_email=body.customer_email or "",
        customer_address=body.customer_address,
        device_id=str(device.id),
        device_name=body.device_name,
        network=body.network,
        device_grade=grade,
        storage=body.storage or "Unknown",
        offered_price=float(body.offered_price),
        postage_method=body.postage_method,
        payment_method=PaymentMethod.BANK,
        payment_status=PaymentStatus.PENDING,
        payout_details=PayoutDetails(
            account_name=body.bank_name or "",
            account_number=body.account_number or "",
            sort_code=body.sort_code or "",
        ),
        transaction_id=body.transaction_id or "",
        partner_name=partner.name,
        counter_offer=CounterOfferEmbed(),
    )
    await order.insert()

    # ── 7. Increment partner order count ─────────────────────────────────────
    try:
        partner.total_orders += 1
        await partner.save()
    except Exception:
        pass

    # ── 8. Send confirmation email ───────────────────────────────────────────
    if body.customer_email:
        await send_order_confirmation(order)

    # ── 9. Log successful request ────────────────────────────────────────────
    await _log_api_request(request, 200, True, order.order_number, None, _ms(start_time), partner.name)
    logger.info(f"API Order created: {order.order_number} by partner {partner.name}")

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "orderNumber": order.order_number,
            "message": "Order created successfully",
            "order": {
                "id": str(order.id),
                "orderNumber": order.order_number,
                "status": order.status,
                "createdAt": order.created_at.isoformat(),
            },
        },
    )


@router.post("/orders", summary="Create order via partner API")
async def create_gateway_order(
    request: Request,
    body: GatewayOrderSchema,
    partner=Depends(get_current_partner),
):
    return await create_external_order(request, body, partner)


@router.get("/test", summary="Test API Gateway (GET)")
@router.post("/test", summary="Test API Gateway (POST)")
async def test_endpoint(request: Request):
    """GET/POST /api/gateway/test — mirrors Node.js testEndpoint."""
    client_ip = request.client.host if request.client else "unknown"
    return success_response({
        "success": True,
        "message": "API Gateway is working",
        "source_ip": client_ip,
        "timestamp": datetime.utcnow().isoformat(),
    })


@router.get("/orders", summary="Get partner orders")
async def gateway_get_orders(
    request: Request,
    partner=Depends(get_current_partner),
    page: int = 1,
    limit: int = 20,
):
    skip = (page - 1) * limit
    orders = await Order.find(Order.partner_name == partner.name).sort(-Order.created_at).skip(skip).limit(limit).to_list()
    total = await Order.find(Order.partner_name == partner.name).count()
    return success_response({
        "orders": [_serialize(o) for o in orders],
        "pagination": {"page": page, "limit": limit, "total": total},
    })


@router.get("/orders/{order_number}", summary="Get partner order by order number")
async def gateway_get_order(
    order_number: str,
    request: Request,
    partner=Depends(get_current_partner),
):
    order = await Order.find_one(
        Order.order_number == order_number.upper(),
        Order.partner_name == partner.name,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return success_response({"order": _serialize(order)})


def _ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def _serialize(o: Order) -> dict:
    return {
        "id": str(o.id),
        "order_number": o.order_number,
        "status": o.status,
        "device_name": o.device_name,
        "network": o.network,
        "storage": o.storage,
        "device_grade": o.device_grade,
        "offered_price": o.offered_price,
        "final_price": o.final_price,
        "postage_method": o.postage_method,
        "payment_status": o.payment_status,
        "created_at": o.created_at.isoformat(),
    }
