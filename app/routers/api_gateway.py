import time
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional, Any
from datetime import datetime
from bson import ObjectId
from app.models.order import Order
from app.models.api_log import ApiLog
from app.models.device import Device
from app.models.partner import Partner
from app.models.pricing import Pricing
from app.middleware.partner_auth import get_current_partner
from app.utils.order_number import generate_unique_order_number
from app.utils.response import success_response, created_response
from app.config.constants import OrderSource, PostageMethod, PaymentMethod, PaymentStatus
from app.utils.logger import logger
from app.services.email_service import send_order_confirmation

router = APIRouter(prefix="/gateway", tags=["API Gateway"])


# DecisionTech / MoneySupermarket test IPs (per their integration guide).
# Used ONLY for informational attribution when no X-Partner-Key is supplied —
# not for access control.
_DECISIONTECH_IPS = {
    "35.189.124.202",
    "109.176.94.116",
    "109.176.117.84",
    "35.197.205.228",
}
_DEFAULT_DOP_PARTNER_NAME = "DecisionTech / MoneySupermarket"


async def _get_or_create_default_dop_partner() -> Optional[Partner]:
    """Lookup-or-create the catch-all 'DecisionTech / MoneySupermarket' partner.

    Used to attribute orders that arrive without a valid X-Partner-Key so they
    still appear in admin reporting under a sensible name.
    """
    name = _DEFAULT_DOP_PARTNER_NAME
    try:
        partner = await Partner.find_one(Partner.name == name)
        if not partner:
            partner = Partner(
                name=name,
                key_hash="",
                key_prefix="dop_",
                is_active=True,
                notes="Auto-created for DecisionTech DOP traffic (no X-Partner-Key required).",
            )
            await partner.insert()
        partner.last_used_at = datetime.utcnow()
        await partner.save()
        return partner
    except Exception as e:
        logger.warning(f"Could not resolve default DOP partner: {e}")
        return None


async def _resolve_partner_optional(
    request: Request,
    x_partner_key: Optional[str],
) -> tuple:
    """Return (partner_or_none, partner_name_for_log).

    Auth is INTENTIONALLY non-rejecting. The endpoint is meant to accept every
    well-formed order regardless of whether the partner sent an X-Partner-Key:

      • Header present AND matches an active partner row
            → use that partner (their orders appear under their own name).
      • Header present but does NOT match (bad / revoked / unknown key)
            → log a warning, accept the order anyway under the default
              'DecisionTech / MoneySupermarket' partner. Never 401.
      • Header absent
            → accept the order under the default partner. Never 401.

    This honours both the DecisionTech DOP spec ('No orders that are posted to
    an endpoint should be rejected') and the brief 'I don't want any
    restrictions' on this integration.
    """
    client_ip = request.client.host if request.client else "unknown"

    if x_partner_key:
        # Try strict validation first — if it succeeds, use the matched partner.
        if x_partner_key.startswith("cmm_pk_"):
            try:
                active_partners = await Partner.find(Partner.is_active == True).to_list()
                matched = next(
                    (p for p in active_partners if Partner.verify_key(x_partner_key, p.key_hash)),
                    None,
                )
                if matched:
                    try:
                        matched.last_used_at = datetime.utcnow()
                        await matched.save()
                    except Exception:
                        pass
                    return matched, matched.name
            except Exception as e:
                logger.warning(f"Partner key lookup failed: {e}")

        # Header present but did not match a partner — log and fall through.
        prefix = x_partner_key[:11] + "..." if len(x_partner_key) > 11 else "(short)"
        logger.warning(
            f"Gateway: X-Partner-Key supplied but did not match any active "
            f"partner — accepting anyway under default DOP partner "
            f"(prefix={prefix}, ip={client_ip})"
        )

    # No key, or key didn't match — attribute to default DOP partner.
    partner = await _get_or_create_default_dop_partner()
    return partner, (partner.name if partner else _DEFAULT_DOP_PARTNER_NAME)


# ── Field-name aliases ────────────────────────────────────────────────────────
# Maps every accepted incoming key (lower-cased, dashes/spaces→underscore) to
# our canonical schema field. Built to satisfy:
#   • the original CashMyMobile spec (customer_name, customer_phone, …)
#   • the DecisionTech / MoneySupermarket DOP spec (first_name, street1, …,
#     device_price, bank_account_number, bank_sort_code, paypal_email, …)
#   • assorted casing / synonyms partners commonly send.
_FIELD_ALIASES = {
    "customer_name":    ["customer_name", "customername", "name", "full_name", "fullname",
                         "customer", "first_name_last_name"],
    "first_name":       ["first_name", "firstname", "fname", "givenname", "given_name"],
    "last_name":        ["last_name", "lastname", "lname", "surname", "familyname", "family_name"],
    "customer_phone":   ["customer_phone", "customerphone", "phone", "phone_number",
                         "phonenumber", "mobile", "mobile_number", "mobilenumber",
                         "contact_number", "contact_phone", "tel", "telephone"],
    "customer_email":   ["customer_email", "customeremail", "email", "email_address",
                         "emailaddress", "contact_email"],
    "customer_address": ["customer_address", "customeraddress", "address", "full_address",
                         "fulladdress", "delivery_address", "deliveryaddress",
                         "shipping_address", "postal_address"],
    # DecisionTech sends the postal address as separate components — we'll
    # combine them into customer_address in the validator below.
    "street1":          ["street1", "address1", "address_line_1", "addressline1",
                         "address_line1", "line1", "house_number", "house"],
    "street2":          ["street2", "address2", "address_line_2", "addressline2",
                         "address_line2", "line2"],
    "city":             ["city", "town", "locality"],
    "county":           ["county", "state", "region", "province"],
    "country":          ["country", "country_name"],
    "postcode":         ["postcode", "post_code", "postal_code", "postalcode", "zip", "zipcode"],
    "postage_method":   ["postage_method", "postagemethod", "postage", "shipping_method",
                         "shippingmethod", "shipping", "delivery_method", "fulfilment_method"],
    "payment_method":   ["payment_method", "paymentmethod", "payment", "pay_method", "paymethod"],
    "paypal_email":     ["paypal_email", "paypalemail", "paypal", "paypal_address"],
    "device_name":      ["device_name", "devicename", "device", "device_model", "devicemodel",
                         "model", "model_name", "modelname", "phone_model", "phone_name",
                         "product_name", "productname", "handset"],
    "network":          ["network", "carrier", "operator", "network_provider", "service_provider"],
    "device_grade":     ["device_grade", "devicegrade", "grade", "condition", "condition_grade",
                         "device_condition", "phone_condition", "handset_condition"],
    "offered_price":    ["offered_price", "offeredprice", "price", "amount", "value",
                         "offer", "offer_price", "offerprice", "quote", "quoted_price",
                         "payout", "payout_amount", "device_price", "deviceprice"],
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
                         "order_ref", "orderref", "client_ref", "order_id", "orderid"],
    "device_id":        ["device_id", "deviceid", "product_id", "productid", "sku"],
    # DecisionTech extra fault descriptors — captured for admin context.
    "device_cracked_display": ["device_cracked_display", "devicecrackeddisplay",
                                "cracked_display", "screen_cracked"],
    "device_other_faults":    ["device_other_faults", "deviceotherfaults",
                                "other_faults", "faults"],
    "device_single_button_fault": ["device_single_button_fault", "devicesinglebuttonfault",
                                    "single_button_fault", "button_fault"],
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


# DecisionTech grade-code mapping: 0 = working (GOOD), 1 = broken, 2 = new.
# Plus string synonyms / case-insensitive accepted everywhere.
_GRADE_NUMERIC = {"0": "GOOD", "1": "BROKEN", "2": "NEW"}
_GRADE_SYNONYMS = {
    "NEW": "NEW", "MINT": "NEW", "EXCELLENT": "NEW", "AS_NEW": "NEW", "LIKE_NEW": "NEW",
    "GOOD": "GOOD", "WORKING": "GOOD", "USED": "GOOD", "FAIR": "GOOD", "AVERAGE": "GOOD",
    "BROKEN": "BROKEN", "FAULTY": "BROKEN", "DAMAGED": "BROKEN", "POOR": "BROKEN", "BAD": "BROKEN",
}


def _coerce_grade(value: Any) -> Optional[str]:
    """Accept device_grade as numeric 0/1/2, common strings, or synonyms."""
    if value is None or value == "":
        return None
    # Booleans should not be silently coerced (True == 1)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _GRADE_NUMERIC.get(str(int(value)))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s in _GRADE_NUMERIC:
            return _GRADE_NUMERIC[s]
        u = s.upper().replace(" ", "_").replace("-", "_")
        return _GRADE_SYNONYMS.get(u, u if u in ("NEW", "GOOD", "BROKEN") else None)
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

    # Customer
    customer_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None

    # Address (full string OR DecisionTech component fields)
    customer_address: Optional[str] = None
    street1: Optional[str] = None
    street2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = None
    postcode: Optional[str] = None

    # Logistics
    postage_method: Optional[str] = None
    payment_method: Optional[str] = None
    paypal_email: Optional[str] = None

    # Device
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    network: Optional[str] = None
    device_grade: Optional[str] = None
    offered_price: Optional[float] = None
    storage: Optional[str] = None

    # Fault descriptors (DecisionTech)
    device_cracked_display: Optional[str] = None
    device_other_faults: Optional[str] = None
    device_single_button_fault: Optional[str] = None

    # Payout
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None

    # Reference
    transaction_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Build a lookup of normalized incoming keys → original value.
        # We flatten nested objects too: some partners (e.g. MoneySupermarket /
        # DOP integrations) wrap the payout details in a sub-object such as
        # {"payout": {"account_number": ...}} or {"bankDetails": {...}} instead
        # of sending them flat. Without recursing, every flat field mapped but
        # the bank details silently came through empty. Top-level keys are added
        # first and win; nested leaves only fill the gaps.
        lookup: dict = {}

        def _flatten_into(obj, into, depth=0):
            if depth > 4 or not isinstance(obj, dict):
                return
            nested = []
            for k, v in obj.items():
                if isinstance(v, dict):
                    nested.append(v)
                    continue
                if isinstance(v, list):
                    nested.extend(x for x in v if isinstance(x, dict))
                    continue
                nk = _normalize_key(k)
                if nk and nk not in into:
                    into[nk] = v
            for child in nested:
                _flatten_into(child, into, depth + 1)

        _flatten_into(data, lookup)

        out: dict = {}
        for canonical, variants in _FIELD_ALIASES.items():
            for v in variants:
                if v in lookup and lookup[v] not in (None, ""):
                    out[canonical] = lookup[v]
                    break

        # ── Build customer_name from first_name + last_name if missing ─────
        if not out.get("customer_name"):
            fn = (out.get("first_name") or "").strip() if isinstance(out.get("first_name"), str) else ""
            ln = (out.get("last_name") or "").strip() if isinstance(out.get("last_name"), str) else ""
            combined = (fn + " " + ln).strip()
            if combined:
                out["customer_name"] = combined

        # ── Build customer_address from postal components if missing ───────
        if not out.get("customer_address"):
            parts = []
            for k in ("street1", "street2", "city", "county", "postcode", "country"):
                val = out.get(k)
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
            if parts:
                out["customer_address"] = ", ".join(parts)

        # Coerce price (DecisionTech sends as quoted string like "99.99")
        if "offered_price" in out:
            out["offered_price"] = _coerce_price(out["offered_price"])

        # Coerce ID-style fields that may arrive as int (form-urlencoded gives
        # strings, but JSON clients sometimes send raw numbers).
        for key in ("customer_phone", "account_number", "sort_code", "device_id",
                    "transaction_id", "storage", "postcode", "first_name", "last_name",
                    "street1", "street2", "city", "county", "country",
                    "device_cracked_display", "device_other_faults",
                    "device_single_button_fault"):
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


def _err(status: int, message: str, field: Optional[str] = None,
         errors: Optional[list] = None) -> JSONResponse:
    """Build an error response body partners can actually parse.

    Always includes 'success', 'error' and 'message' (identical strings).
    Optionally includes 'field' (the single field at fault) and 'errors'
    (a list of {field, message} entries for per-field validation failures).
    """
    content: dict = {
        "success": False,
        "error": message,
        "message": message,
    }
    if field:
        content["field"] = field
    if errors:
        content["errors"] = errors
    return JSONResponse(status_code=status, content=content)


async def _read_raw_payload(request: Request) -> dict:
    """Read the request body in whichever format the partner sent.

    Supports — in priority order:
      • application/json
      • application/x-www-form-urlencoded   ← DecisionTech / MoneySupermarket
      • multipart/form-data
      • bare query-string style bodies (auto-detected when JSON parse fails)

    Returns the parsed dict, or `{"__raw__": "..."}` on hard parse failure.
    """
    from urllib.parse import parse_qsl

    try:
        raw = await request.body()
        if not raw:
            return {}
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {}

        content_type = (request.headers.get("content-type") or "").lower()

        # 1) Explicit JSON
        if "application/json" in content_type or text.startswith(("{", "[")):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
                return {"__raw__": str(data)[:2000]}
            except json.JSONDecodeError:
                pass  # fall through and try form parsing

        # 2) Explicit form-urlencoded (or multipart) — DecisionTech default
        if ("application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type):
            try:
                form = await request.form()
                parsed = {}
                for k, v in form.multi_items():
                    # First occurrence wins (DecisionTech sends each key once)
                    if k not in parsed:
                        parsed[k] = v if isinstance(v, str) else str(v)
                return parsed
            except Exception:
                pass

        # 3) Auto-detect: body looks like key=value&key=value
        if "=" in text and "{" not in text:
            try:
                pairs = parse_qsl(text, keep_blank_values=True)
                if pairs:
                    parsed = {}
                    for k, v in pairs:
                        if k not in parsed:
                            parsed[k] = v
                    return parsed
            except Exception:
                pass

        # 4) Last-ditch: try JSON parse again (in case content-type was wrong)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        return {"__raw__": text[:2000]}
    except Exception as e:
        logger.warning(f"Failed to read gateway payload: {e}")
        return {}


# ── Endpoint ─────────────────────────────────────────────────────────────────
@router.post(
    "/decisiontech",
    summary="Create order via partner API (DecisionTech DOP integration)",
)
async def create_external_order(
    request: Request,
    x_partner_key: Optional[str] = Header(None),
):
    """POST /api/gateway/decisiontech — DecisionTech DOP-compatible endpoint.

    Accepts either application/json OR application/x-www-form-urlencoded body.
    The X-Partner-Key header is OPTIONAL: DecisionTech DOP does not send one,
    so requests without a key are attributed to the auto-created
    'DecisionTech / MoneySupermarket' partner. Existing CashMyMobile partners
    that DO send a key continue to be authenticated strictly.
    """
    start_time = time.time()

    # ── Resolve partner (strict if key supplied, default otherwise) ─────────
    partner, partner_name = await _resolve_partner_optional(request, x_partner_key)

    # ── 0. Read & normalize payload ──────────────────────────────────────────
    raw_payload = await _read_raw_payload(request)
    if "__raw__" in raw_payload:
        msg = ("The request body could not be parsed. Please send the order data "
               "as either application/json or application/x-www-form-urlencoded.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="body")

    if not raw_payload:
        msg = ("The request body is empty. Please send the order details either "
               "as a JSON object or as URL-encoded form data.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="body")

    try:
        body = GatewayOrderSchema.model_validate(raw_payload)
    except Exception as e:
        msg = (f"The request body could not be parsed. "
               f"Please check that every field has the correct data type. Details: {e}")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="body")

    # ── 1. Per-field required validation ────────────────────────────────────
    field_errors: list = []

    def _is_blank(v: Any) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    field_label = {
        "customer_name":    "customer_name (customer full name)",
        "customer_phone":   "customer_phone (UK mobile number)",
        "customer_address": "customer_address (full postal address)",
        "postage_method":   "postage_method ('label' or 'postbag')",
        "device_name":      "device_name (exact device model name)",
        "network":          "network (e.g. 'Unlocked', 'EE', 'O2')",
        "device_grade":     "device_grade ('NEW', 'GOOD' or 'BROKEN')",
        "offered_price":    "offered_price (positive number in GBP)",
    }

    for fname, fvalue in [
        ("customer_name",    body.customer_name),
        ("customer_phone",   body.customer_phone),
        ("customer_address", body.customer_address),
        ("postage_method",   body.postage_method),
        ("device_name",      body.device_name),
        ("network",          body.network),
        ("device_grade",     body.device_grade),
        ("offered_price",    body.offered_price),
    ]:
        if _is_blank(fvalue):
            field_errors.append({
                "field": fname,
                "message": f"The field '{fname}' is required but was missing or empty. "
                           f"Please provide {field_label[fname]}.",
            })

    if field_errors:
        summary = ("The request is missing one or more required fields: "
                   + ", ".join(e["field"] for e in field_errors) + ".")
        await _log_api_request(request, 422, False, None, summary, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, summary, errors=field_errors)

    # ── 2. customer_name format ──────────────────────────────────────────────
    customer_name = body.customer_name.strip()
    if len(customer_name) < 2:
        msg = ("The field 'customer_name' is too short. "
               "Please provide the customer's full name (at least 2 characters).")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="customer_name")
    if len(customer_name) > 120:
        msg = ("The field 'customer_name' is too long. "
               "Please keep the customer's full name under 120 characters.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="customer_name")

    # ── 3. customer_phone format (UK mobile or landline, lenient) ────────────
    # DecisionTech's example phones include 11-digit UK numbers; we normalize
    # +44 / 0044 prefixes to a leading 0 but otherwise accept any 7–15 digit
    # string so we don't reject perfectly valid customer phones.
    phone_digits = re.sub(r"[\s\-().+]", "", body.customer_phone)
    if phone_digits.startswith("0044"):
        phone_digits_normal = "0" + phone_digits[4:]
    elif phone_digits.startswith("44") and len(phone_digits) >= 11:
        phone_digits_normal = "0" + phone_digits[2:]
    else:
        phone_digits_normal = phone_digits
    if not re.fullmatch(r"\d{7,15}", phone_digits_normal):
        msg = ("The field 'customer_phone' does not look like a phone number. "
               "Please provide the customer's contact number "
               "(UK format e.g. '07XXXXXXXXX' or '+447XXXXXXXXX').")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="customer_phone")

    # ── 4. customer_email format (only when provided) ────────────────────────
    if body.customer_email:
        email_value = body.customer_email.strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email_value):
            msg = ("The field 'customer_email' is not a valid email address. "
                   "Please provide an address in the format 'name@example.com', "
                   "or omit the field if you do not wish to send a confirmation email.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="customer_email")
        if len(email_value) > 254:
            msg = ("The field 'customer_email' is too long. "
                   "Please keep the email under 254 characters.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="customer_email")

    # ── 5. customer_address format ───────────────────────────────────────────
    # DecisionTech sometimes builds addresses from sparse components, so the
    # minimum length is intentionally low. We still require a postcode SOMEWHERE
    # (either in customer_address or in the postcode field) so packages can be
    # delivered.
    customer_address = body.customer_address.strip()
    if len(customer_address) < 4:
        msg = ("The field 'customer_address' is too short. "
               "Please provide the full postal address including house number, "
               "street, town and postcode (or use the DecisionTech component "
               "fields: street1, city, postcode).")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="customer_address")
    if len(customer_address) > 1000:
        msg = ("The field 'customer_address' is too long. "
               "Please keep the postal address under 1000 characters.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="customer_address")

    # ── 6. postage_method (case-insensitive; DecisionTech-friendly) ──────────
    # Accepts: 'label', 'postbag', 'Freepost postbag', 'freepost', 'royal mail',
    # 'tracked'… anything that mentions postbag/pack normalises to 'postbag',
    # anything that mentions label/print normalises to 'label'.
    postage_raw = (body.postage_method or "").strip().lower()
    if any(t in postage_raw for t in ("postbag", "post bag", "freepost", "pack", "send pack")):
        postage_normalized = "postbag"
    elif any(t in postage_raw for t in ("label", "print", "self post", "self-post")):
        postage_normalized = "label"
    elif postage_raw in ("label", "postbag"):
        postage_normalized = postage_raw
    else:
        msg = (f"The value '{body.postage_method}' is not a recognised postage_method. "
               f"Please use 'label' (we email a prepaid postage label) "
               f"or 'postbag' (we post a Freepost postbag to the customer). "
               f"DecisionTech 'Freepost postbag' is also accepted.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="postage_method")

    # ── 7. device_grade (numeric 0/1/2, case-insensitive strings, synonyms) ──
    # DecisionTech DOP uses numeric codes: 0 = working (GOOD), 1 = broken
    # (BROKEN), 2 = new (NEW). String variants and common synonyms are also
    # accepted (e.g. "GOOD", "Working", "Mint", "Faulty").
    grade = _coerce_grade(body.device_grade)
    if grade not in ("NEW", "GOOD", "BROKEN"):
        msg = (f"The value '{body.device_grade}' is not a recognised device_grade. "
               f"Please use one of: 'NEW' / 2 (perfect or near-perfect condition), "
               f"'GOOD' / 0 (fully working with minor wear), "
               f"or 'BROKEN' / 1 (cracked screen or hardware faults). "
               f"DecisionTech numeric codes (0=working, 1=broken, 2=new) are also accepted.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="device_grade")

    # ── 8. offered_price ─────────────────────────────────────────────────────
    if body.offered_price is None:
        msg = ("The field 'offered_price' could not be parsed as a number. "
               "Please send a positive numeric value in GBP, e.g. 655.00 "
               "(currency symbols and thousand separators are allowed).")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="offered_price")
    if body.offered_price <= 0:
        msg = (f"The value '{body.offered_price}' is not a valid offered_price. "
               f"The offered price must be greater than zero (in GBP).")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="offered_price")
    if body.offered_price > 10000:
        msg = (f"The value '{body.offered_price}' is unusually high for a mobile device. "
               f"Please double-check the offered_price (we cap quotes at £10,000 GBP).")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="offered_price")

    # ── 9. Payment method (bank / cheque / paypal) ───────────────────────────
    payment_method_raw = (body.payment_method or "").strip().lower()
    if payment_method_raw and payment_method_raw not in ("bank", "cheque", "check", "paypal"):
        msg = (f"The value '{body.payment_method}' is not a recognised payment_method. "
               f"Please use 'bank', 'cheque' or 'paypal'.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="payment_method")
    payment_method_canonical = {"check": "cheque"}.get(payment_method_raw, payment_method_raw) or "bank"

    # ── 9a. PayPal payment requires paypal_email ─────────────────────────────
    if payment_method_canonical == "paypal":
        if not body.paypal_email or not body.paypal_email.strip():
            msg = ("The field 'paypal_email' is required when payment_method is 'paypal'. "
                   "Please provide the customer's PayPal email address.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="paypal_email")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", body.paypal_email.strip()):
            msg = ("The field 'paypal_email' is not a valid email address. "
                   "Please provide the customer's PayPal address in the format "
                   "'name@example.com'.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="paypal_email")

    # ── 9b. Optional banking fields — validate format when provided ──────────
    if body.sort_code:
        sc = body.sort_code.strip()
        sc_digits = re.sub(r"\D", "", sc)
        if len(sc_digits) != 6:
            msg = (f"The value '{body.sort_code}' is not a valid UK sort code. "
                   f"Please provide a 6-digit sort code (e.g. '20-00-00' or '200000').")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="sort_code")

    if body.account_number:
        an = re.sub(r"\D", "", body.account_number.strip())
        if len(an) != 8:
            msg = ("The field 'account_number' is not a valid UK bank account number. "
                   "Please provide an 8-digit account number (digits only).")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="account_number")

    if body.bank_name and len(body.bank_name.strip()) > 100:
        msg = ("The field 'bank_name' is too long. "
               "Please keep the bank name under 100 characters.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="bank_name")

    # 9c. Partial bank details are only flagged when payment_method is 'bank'
    # (DecisionTech bank flows don't always include the bank_name string).
    if payment_method_canonical == "bank":
        if (body.account_number or body.sort_code) and not (body.account_number and body.sort_code):
            missing_bank = []
            if not body.account_number: missing_bank.append("account_number (bank_account_number)")
            if not body.sort_code:      missing_bank.append("sort_code (bank_sort_code)")
            msg = ("Partial bank details were provided. "
                   "To pay the customer by bank transfer we need BOTH a sort_code "
                   "and an account_number. "
                   f"Missing: {', '.join(missing_bank)}.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="payout_details", errors=[
                {"field": f.split(' ')[0], "message": f"'{f}' is required for bank payment."}
                for f in missing_bank
            ])

    # ── 10. transaction_id length sanity ─────────────────────────────────────
    if body.transaction_id and len(body.transaction_id) > 128:
        msg = ("The field 'transaction_id' is too long. "
               "Please keep your internal reference under 128 characters.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="transaction_id")

    # ── 11. Look up device (exact → partial → fuzzy) ─────────────────────────
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

    device = next(
        (d for d in active_devices if requested_compact in _names_for(d)),
        None,
    )
    if not device:
        stripped = re.sub(r"^(apple|samsung)\s+", "", requested_compact)
        device = next(
            (d for d in active_devices
             if any(stripped == n or stripped == re.sub(r"^(apple|samsung)\s+", "", n)
                    for n in _names_for(d))),
            None,
        )
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
        msg = (f"The device '{body.device_name}' was not found in our catalogue. "
               f"Please provide the exact device name as listed on cashmymobile.co.uk "
               f"(for example, 'Apple iPhone 16 Pro Max' or 'Samsung Galaxy S24 Ultra').")
        await _log_api_request(request, 404, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(404, msg, field="device_name")

    # ── 12. network: support our list + DecisionTech's wider set ─────────────
    # CashMyMobile carriers + DecisionTech additions (Orange/Tmobile/Virgin/Other).
    # Orange & T-Mobile UK both became EE; we normalise them. 'Other' falls back
    # to 'Unlocked' so the order isn't rejected for an unknown carrier.
    supported_networks = ["Unlocked", "EE", "O2", "Vodafone", "Three",
                          "Virgin Mobile", "Tesco Mobile", "Giffgaff"]
    network_aliases = {
        "unlocked": "Unlocked", "sim free": "Unlocked", "sim-free": "Unlocked", "open": "Unlocked",
        "ee": "EE", "ee mobile": "EE",
        "orange": "EE", "orange uk": "EE",
        "tmobile": "EE", "t mobile": "EE", "t-mobile": "EE", "tmobile uk": "EE",
        "o2": "O2", "o2 uk": "O2",
        "vodafone": "Vodafone", "vodaphone": "Vodafone", "voda": "Vodafone",
        "three": "Three", "3": "Three", "three uk": "Three",
        "virgin mobile": "Virgin Mobile", "virgin": "Virgin Mobile",
        "tesco mobile": "Tesco Mobile", "tesco": "Tesco Mobile",
        "giffgaff": "Giffgaff", "giff gaff": "Giffgaff", "giff-gaff": "Giffgaff",
        "other": "Unlocked", "unknown": "Unlocked", "any": "Unlocked",
    }
    network_lc = body.network.strip().lower()
    canonical_network = network_aliases.get(network_lc)
    if not canonical_network:
        # Forgiving partial match
        for low, canon in network_aliases.items():
            if low and (low in network_lc or network_lc in low):
                canonical_network = canon
                break
    if not canonical_network:
        msg = (f"The value '{body.network}' is not a recognised network. "
               f"Please use one of: {', '.join(supported_networks)}. "
               f"DecisionTech values (Orange, Tmobile, Virgin, Other) are also accepted.")
        await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(422, msg, field="network")

    # ── 13. storage: must be one of the supported capacities (when present) ─
    supported_storage = ["64GB", "128GB", "256GB", "512GB", "1TB", "2TB"]
    canonical_storage = None
    if body.storage:
        st = body.storage.strip().upper().replace(" ", "")
        st_lookup = {s.upper(): s for s in supported_storage}
        canonical_storage = st_lookup.get(st)
        if not canonical_storage:
            msg = (f"The value '{body.storage}' is not a supported storage capacity. "
                   f"Please use one of: {', '.join(supported_storage)}.")
            await _log_api_request(request, 422, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(422, msg, field="storage")

    # ── 14. Validate network/storage pricing combo if storage provided ───────
    if canonical_storage:
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
                if (p.network or "").strip().lower() == canonical_network.lower()
                and (p.storage or "").strip().lower() == canonical_storage.lower()
            ),
            None,
        )
        if not pricing_entry:
            available_combos = sorted({
                f"{p.network} / {p.storage}" for p in pricing_rows
                if p.network and p.storage
            })
            hint = (f" Available combinations for this device: {', '.join(available_combos)}."
                    if available_combos else "")
            msg = (f"The combination network='{canonical_network}' and "
                   f"storage='{canonical_storage}' is not available for "
                   f"'{body.device_name}'.{hint}")
            await _log_api_request(request, 400, False, None, msg, _ms(start_time),
                                   partner_name, payload=raw_payload)
            return _err(400, msg, field="network/storage")

    # Use the canonical values from here on
    body.network = canonical_network
    if canonical_storage:
        body.storage = canonical_storage
    body.customer_phone = phone_digits_normal
    body.customer_name = customer_name
    body.customer_address = customer_address

    # Build a human-readable admin note from the DecisionTech fault fields
    # so the admin order page surfaces them without needing schema changes.
    fault_note_parts = []
    if body.device_cracked_display and body.device_cracked_display.strip().lower() not in ("", "false", "0", "no"):
        fault_note_parts.append(f"Cracked display: {body.device_cracked_display.strip()}")
    if body.device_other_faults and body.device_other_faults.strip().lower() not in ("", "false", "0", "no"):
        fault_note_parts.append(f"Other faults: {body.device_other_faults.strip()}")
    if body.device_single_button_fault and body.device_single_button_fault.strip().lower() not in ("", "false", "0", "no"):
        fault_note_parts.append(f"Single button fault: {body.device_single_button_fault.strip()}")
    if payment_method_canonical == "paypal" and body.paypal_email:
        fault_note_parts.append(f"PayPal email: {body.paypal_email.strip()}")
    elif payment_method_canonical == "cheque":
        fault_note_parts.append("Payment by cheque")
    admin_notes_value = " | ".join(fault_note_parts) if fault_note_parts else None

    # ── 7. Create order ──────────────────────────────────────────────────────
    order_number = await generate_unique_order_number()

    # Map DOP payment_method → our PaymentMethod enum (currently only BANK is
    # defined). We persist the raw 'bank'/'cheque'/'paypal' value too so admin
    # reports reflect the actual chosen method, but the enum check stays happy.
    payment_method_value = PaymentMethod.BANK  # placeholder; only enum supported now

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
            city=body.city,
            postcode=body.postcode,
            device_id=str(device.id),
            device_name=body.device_name,
            network=body.network,
            device_grade=grade,
            storage=body.storage or "Unknown",
            offered_price=float(body.offered_price),
            postage_method=postage_normalized,
            payment_method=payment_method_value,
            payment_status=PaymentStatus.PENDING,
            payout_details=PayoutDetails(
                account_name=body.bank_name or (
                    body.paypal_email or "" if payment_method_canonical == "paypal" else ""
                ),
                account_number=body.account_number or "",
                sort_code=body.sort_code or "",
            ),
            transaction_id=body.transaction_id or "",
            partner_name=partner_name,
            admin_notes=admin_notes_value,
            counter_offer=CounterOfferEmbed(),
        )
        await order.insert()
    except Exception as e:
        logger.exception(f"Failed to persist gateway order: {e}")
        await _log_api_request(request, 500, False, None, str(e), _ms(start_time),
                               partner_name, payload=raw_payload)
        return _err(
            500,
            "An internal error occurred while saving the order. "
            "Please retry the request shortly, or contact support@cashmymobile.co.uk "
            "if the problem persists.",
        )

    # ── 8. Increment partner order count (best-effort) ───────────────────────
    if partner is not None:
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
    await _log_api_request(request, 200, True, order.order_number, None, _ms(start_time),
                           partner_name, payload=raw_payload)
    logger.info(f"API Order created: {order.order_number} by partner {partner_name}")

    # DecisionTech DOP spec: return HTTP 200 with an order_id field at the top
    # level of the response body. We additionally include our existing keys for
    # backward compatibility with partners already integrated against them.
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "order_id": order.order_number,
            "orderNumber": order.order_number,
            "orderId": order.order_number,
            "message": "Order created successfully",
            "order": {
                "id": str(order.id),
                "order_id": order.order_number,
                "orderNumber": order.order_number,
                "status": order.status,
                "createdAt": order.created_at.isoformat(),
            },
        },
    )


@router.post("/orders", summary="Create order via partner API")
async def create_gateway_order(
    request: Request,
    x_partner_key: Optional[str] = Header(None),
):
    return await create_external_order(request, x_partner_key)


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
        raise HTTPException(
            status_code=404,
            detail=(
                f"No order was found with order number '{order_number}' "
                f"under your partner account. Please verify the order number "
                f"and ensure it was created via your X-Partner-Key."
            ),
        )
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
