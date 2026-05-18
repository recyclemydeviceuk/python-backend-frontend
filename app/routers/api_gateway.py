import time
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional, Any
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


# ── Field-name aliases ────────────────────────────────────────────────────────
# Maps every accepted incoming key (lower-cased, dashes/spaces→underscore) to
# our canonical schema field. Lets us absorb partner payloads that use slightly
# different field naming without rejecting the whole request.
_FIELD_ALIASES = {
    "customer_name":    ["customer_name", "customername", "name", "full_name", "fullname",
                         "customer", "first_name_last_name"],
    "customer_phone":   ["customer_phone", "customerphone", "phone", "phone_number",
                         "phonenumber", "mobile", "mobile_number", "mobilenumber",
                         "contact_number", "contact_phone", "tel", "telephone"],
    "customer_email":   ["customer_email", "customeremail", "email", "email_address",
                         "emailaddress", "contact_email"],
    "customer_address": ["customer_address", "customeraddress", "address", "full_address",
                         "fulladdress", "delivery_address", "deliveryaddress",
                         "shipping_address", "postal_address"],
    "postcode":         ["postcode", "post_code", "postal_code", "postalcode", "zip", "zipcode"],
    "postage_method":   ["postage_method", "postagemethod", "postage", "shipping_method",
                         "shippingmethod", "shipping", "delivery_method", "fulfilment_method"],
    "device_name":      ["device_name", "devicename", "device", "device_model", "devicemodel",
                         "model", "model_name", "modelname", "phone_model", "phone_name",
                         "product_name", "productname", "handset"],
    "network":          ["network", "carrier", "operator", "network_provider", "service_provider"],
    "device_grade":     ["device_grade", "devicegrade", "grade", "condition", "condition_grade",
                         "device_condition", "phone_condition", "handset_condition"],
    "offered_price":    ["offered_price", "offeredprice", "price", "amount", "value",
                         "offer", "offer_price", "offerprice", "quote", "quoted_price",
                         "payout", "payout_amount"],
    "storage":          ["storage", "storage_capacity", "storagecapacity", "capacity",
                         "memory", "memory_capacity", "rom"],
    "bank_name":        ["bank_name", "bankname", "bank", "payout_account_name",
                         "payoutaccountname", "account_holder", "account_holder_name",
                         "account_name", "accountname"],
    "account_number":   ["account_number", "accountnumber", "payout_account_number",
                         "payoutaccountnumber", "bank_account_number", "bankaccountnumber"],
    "sort_code":        ["sort_code", "sortcode", "payout_sort_code", "payoutsortcode",
                         "bank_sort_code", "banksortcode", "sort"],
    "transaction_id":   ["transaction_id", "transactionid", "txn_id", "txnid", "reference",
                         "ref", "partner_ref", "partnerref", "external_id", "externalid",
                         "order_ref", "orderref", "client_ref"],
    "device_id":        ["device_id", "deviceid", "product_id", "productid", "sku"],
}


def _normalize_key(key: str) -> str:
    """Lowercase, strip whitespace, normalize dashes/spaces to underscores."""
    if not isinstance(key, str):
        return ""
    return re.sub(r"[-\s]+", "_", key.strip()).lower()


def _coerce_price(value: Any) -> Optional[float]:
    """Accept price as number or string (with £/$/€, commas, whitespace)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[£$€,\s]", "", value.strip())
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return str(value).strip() or None


class GatewayOrderSchema(BaseModel):
    """Lenient schema — all fields Optional. Validation is enforced manually in
    the handler so we can return descriptive errors (rather than letting Pydantic
    return an opaque 422 that bypasses our request logging)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    postcode: Optional[str] = None
    postage_method: Optional[str] = None
    device_name: Optional[str] = None
    network: Optional[str] = None
    device_grade: Optional[str] = None
    offered_price: Optional[float] = None
    storage: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None
    transaction_id: Optional[str] = None
    device_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Build a lookup of normalized incoming keys → original value
        lookup: dict = {}
        for k, v in data.items():
            nk = _normalize_key(k)
            if nk and nk not in lookup:
                lookup[nk] = v
        out: dict = {}
        for canonical, variants in _FIELD_ALIASES.items():
            for v in variants:
                if v in lookup and lookup[v] not in (None, ""):
                    out[canonical] = lookup[v]
                    break
        # Coerce price up front so Pydantic's float type accepts it
        if "offered_price" in out:
            out["offered_price"] = _coerce_price(out["offered_price"])
        # Coerce phone / account-number / IDs that may arrive as int
        for key in ("customer_phone", "account_number", "sort_code", "device_id",
                    "transaction_id", "storage", "postcode"):
            if key in out and out[key] is not None and not isinstance(out[key], str):
                out[key] = str(out[key])
        return out


# ── Logging helper ───────────────────────────────────────────────────────────
_REDACT_FIELDS = {"account_number", "sort_code", "bank_name"}


def _redact(payload: dict) -> dict:
    """Redact PII / banking fields before persisting payload to logs."""
    if not isinstance(payload, dict):
        return {}
    redacted = {}
    for k, v in payload.items():
        if _normalize_key(k) in _REDACT_FIELDS and v:
            sv = str(v)
            redacted[k] = f"***{sv[-2:]}" if len(sv) >= 2 else "***"
        else:
            redacted[k] = v
    return redacted


async def _log_api_request(
    request: Request,
    status_code: int,
    success: bool,
    order_number: Optional[str],
    error: Optional[str],
    response_time_ms: int,
    partner_name: Optional[str] = None,
    payload: Optional[dict] = None,
):
    """Log every API gateway request to ApiLog collection."""
    try:
        body_str = ""
        if payload is not None:
            try:
                body_str = json.dumps(_redact(payload), default=str)[:4000]
            except Exception:
                body_str = str(payload)[:4000]
        log = ApiLog(
            method=request.method,
            endpoint=str(request.url.path),
            status_code=status_code,
            source_ip=request.client.host if request.client else "unknown",
            payload=body_str or str({"order_number": order_number, "error": error, "partner_name": partner_name}),
            error=error,
            response_time=response_time_ms,
            success=success,
            order_number=order_number,
        )
        await log.insert()
    except Exception as e:
        logger.error(f"Failed to log API request: {e}")


def _ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def _err(status: int, message: str) -> JSONResponse:
    """Build an error response body partners can actually parse."""
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": message, "message": message},
    )


async def _read_raw_payload(request: Request) -> dict:
    """Read raw JSON body; tolerate empty or malformed payloads."""
    try:
        raw = await request.body()
        if not raw:
            return {}
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"__raw__": text[:2000]}
        if isinstance(data, dict):
            return data
        return {"__raw__": str(data)[:2000]}
    except Exception as e:
        logger.warning(f"Failed to read gateway payload: {e}")
        return {}


# ── Endpoint ─────────────────────────────────────────────────────────────────
@router.post("/decisiontech", summary="Create order via partner API (DecisionTech integration)")
async def create_external_order(
    request: Request,
    partner=Depends(get_current_partner),
):
    """POST /api/gateway/decisiontech — partner order creation."""
    start_time = time.time()

    # ── 0. Read & normalize payload ──────────────────────────────────────────
    raw_payload = await _read_raw_payload(request)
    if "__raw__" in raw_payload:
        msg = "Request body must be valid JSON."
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    try:
        body = GatewayOrderSchema.model_validate(raw_payload)
    except Exception as e:
        # Should rarely happen now that all fields are Optional, but be safe
        msg = f"Invalid request body: {e}"
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    # ── 1. Validate required fields ──────────────────────────────────────────
    required_pairs = [
        ("customer_name",    body.customer_name),
        ("customer_phone",   body.customer_phone),
        ("customer_address", body.customer_address),
        ("postage_method",   body.postage_method),
        ("device_name",      body.device_name),
        ("network",          body.network),
        ("device_grade",     body.device_grade),
        ("offered_price",    body.offered_price),
    ]
    missing = [name for name, val in required_pairs
               if val is None or (isinstance(val, str) and not val.strip())]
    if missing:
        msg = f"Missing required fields: {', '.join(missing)}"
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    # ── 2. Validate postage_method (case-insensitive) ────────────────────────
    postage_normalized = body.postage_method.strip().lower()
    if postage_normalized not in ("label", "postbag"):
        msg = f"Invalid postage_method '{body.postage_method}'. Must be 'label' or 'postbag'."
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    # ── 3. Validate device_grade (case-insensitive + common synonyms) ────────
    grade_raw = body.device_grade.strip().upper()
    grade_synonyms = {
        "NEW": "NEW", "MINT": "NEW", "EXCELLENT": "NEW", "AS_NEW": "NEW",
        "GOOD": "GOOD", "WORKING": "GOOD", "USED": "GOOD", "FAIR": "GOOD",
        "BROKEN": "BROKEN", "FAULTY": "BROKEN", "DAMAGED": "BROKEN", "POOR": "BROKEN",
    }
    grade = grade_synonyms.get(grade_raw, grade_raw)
    if grade not in ("NEW", "GOOD", "BROKEN"):
        msg = f"Invalid device_grade '{body.device_grade}'. Must be NEW, GOOD, or BROKEN."
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    # ── 4. Validate offered_price ────────────────────────────────────────────
    if body.offered_price is None or body.offered_price <= 0:
        msg = f"Invalid offered_price '{body.offered_price}'. Must be a positive number."
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(422, msg)

    # ── 5. Look up device (exact → partial → fuzzy) ──────────────────────────
    requested = body.device_name.strip()
    requested_lc = requested.lower()
    requested_compact = re.sub(r"\s+", " ", requested_lc)

    active_devices = await Device.find(Device.is_active == True).to_list()

    def _names_for(d: Device) -> list:
        candidates = []
        if d.full_name:
            candidates.append(d.full_name.strip().lower())
        if d.name:
            candidates.append(d.name.strip().lower())
            if d.brand:
                candidates.append(f"{d.brand} {d.name}".strip().lower())
        return [c for c in candidates if c]

    # 5a. Exact match
    device = next(
        (d for d in active_devices if requested_compact in _names_for(d)),
        None,
    )
    # 5b. Match ignoring brand prefix duplication ("apple apple iphone 11" etc.)
    if not device:
        stripped = re.sub(r"^(apple|samsung)\s+", "", requested_compact)
        device = next(
            (d for d in active_devices
             if any(stripped == n or stripped == re.sub(r"^(apple|samsung)\s+", "", n)
                    for n in _names_for(d))),
            None,
        )
    # 5c. Containment fallback — every catalog token present in the request
    if not device:
        for d in active_devices:
            for n in _names_for(d):
                tokens = [t for t in n.split() if t]
                if tokens and all(t in requested_compact for t in tokens):
                    device = d
                    break
            if device:
                break
    if not device:
        msg = f"Device not found: {body.device_name}. Please use a valid device from our catalog."
        await _log_api_request(request, 404, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(404, msg)

    # ── 6. Validate network/storage pricing combo if storage provided ────────
    if body.storage:
        requested_network = body.network.strip().lower()
        requested_storage = body.storage.strip().lower()
        pricing_collection = Pricing.get_motor_collection()
        pricing_query: dict = {
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
            msg = (f"Invalid configuration: {body.network} / {body.storage} is not available "
                   f"for {body.device_name}. Please check available options.")
            await _log_api_request(request, 400, False, None, msg, _ms(start_time),
                                   partner.name, payload=raw_payload)
            return _err(400, msg)

    # ── 7. Create order ──────────────────────────────────────────────────────
    order_number = await generate_unique_order_number()

    from app.models.order import PayoutDetails, CounterOfferEmbed
    try:
        order = Order(
            order_number=order_number,
            source=OrderSource.API,
            status="RECEIVED",
            customer_name=body.customer_name,
            customer_phone=body.customer_phone,
            customer_email=body.customer_email or "",
            customer_address=body.customer_address,
            postcode=body.postcode,
            device_id=str(device.id),
            device_name=body.device_name,
            network=body.network,
            device_grade=grade,
            storage=body.storage or "Unknown",
            offered_price=float(body.offered_price),
            postage_method=postage_normalized,
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
    except Exception as e:
        logger.exception(f"Failed to persist gateway order: {e}")
        msg = f"Failed to create order: {e}"
        await _log_api_request(request, 500, False, None, msg, _ms(start_time),
                               partner.name, payload=raw_payload)
        return _err(500, "Internal error while creating order. Please retry or contact support.")

    # ── 8. Increment partner order count ─────────────────────────────────────
    try:
        partner.total_orders += 1
        await partner.save()
    except Exception:
        pass

    # ── 9. Send confirmation email ───────────────────────────────────────────
    if body.customer_email:
        try:
            await send_order_confirmation(order)
        except Exception as e:
            logger.warning(f"Order confirmation email failed for {order.order_number}: {e}")

    # ── 10. Log successful request ───────────────────────────────────────────
    await _log_api_request(request, 201, True, order.order_number, None, _ms(start_time),
                           partner.name, payload=raw_payload)
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
    partner=Depends(get_current_partner),
):
    return await create_external_order(request, partner)


@router.get("/test", summary="Test API Gateway (GET)")
@router.post("/test", summary="Test API Gateway (POST)")
async def test_endpoint(request: Request):
    """GET/POST /api/gateway/test — connectivity check."""
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
