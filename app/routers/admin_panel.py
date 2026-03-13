"""
Admin Panel SSR Routes
All pages served as Jinja2 templates, session via signed cookie.
"""
import secrets
import hashlib
import random
import string
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Request, Form, Depends, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.utils.logger import logger

_templates_dir = Path(__file__).parent.parent.parent / "corefrontend" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter(prefix="/admin-panel", tags=["Admin Panel"])

# ── Session helpers ────────────────────────────────────────────────────────────
SESSION_COOKIE = "admin_session"
SESSION_SECRET = "cmm_admin_secret_2026"   # in production, load from env


def _sign(value: str) -> str:
    return hashlib.sha256(f"{SESSION_SECRET}:{value}".encode()).hexdigest()[:16]


def _set_session(response, email: str):
    token = f"{email}:{_sign(email)}"
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=86400 * 7)


def _get_session(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE, "")
    if ":" not in token:
        return None
    parts = token.rsplit(":", 1)
    if len(parts) != 2:
        return None
    email, sig = parts
    if _sign(email) == sig:
        return email
    return None


def _require_admin(request: Request):
    email = _get_session(request)
    if not email:
        return None
    return email


def _redirect_login(msg: str = ""):
    return RedirectResponse("/admin-panel/login", status_code=302)


async def _send_admin_otp(email: str, code: str) -> bool:
    try:
        from app.services.email_service import send_otp_email
        return await send_otp_email(email, code)
    except Exception as e:
        logger.warning(f"OTP email failed: {e}")
        return False


def _ctx(request: Request, active: str, email: str, **kwargs):
    return {"request": request, "active_page": active, "admin_email": email, **kwargs}


# ── Utility: generate OTP ──────────────────────────────────────────────────────
def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


# ── Safe order loader (skips malformed documents) ─────────────────────────────
async def _safe_orders(limit: int = 0):
    from app.models.order import Order
    query = Order.find(
        {"order_number": {"$exists": True}, "customer_name": {"$exists": True}}
    ).sort(-Order.created_at)
    if limit:
        query = query.limit(limit)
    return await query.to_list()


async def _safe_api_logs(limit: int = 50):
    from app.models.api_log import ApiLog
    return await ApiLog.find(
        {"source_ip": {"$exists": True}, "status_code": {"$exists": True}}
    ).sort(-ApiLog.created_at).limit(limit).to_list()


async def _safe_partners():
    from app.models.partner import Partner
    return await Partner.find(
        {"key_hash": {"$exists": True}, "key_prefix": {"$exists": True}}
    ).sort(-Partner.created_at).to_list()


# ── Shared data loaders ────────────────────────────────────────────────────────
async def _load_utilities():
    from app.models.storage_option import StorageOption
    from app.models.device_condition import DeviceCondition
    from app.models.network import Network
    from app.models.brand import Brand
    from app.models.category import Category
    from app.models.order_status import OrderStatus
    from app.models.payment_status import PaymentStatus

    storage = await StorageOption.find().sort(+StorageOption.sort_order).to_list()
    conditions = await DeviceCondition.find().to_list()
    networks = await Network.find().to_list()
    brands = await Brand.find().to_list()
    partners = await _safe_partners()
    categories = await Category.find().to_list()
    order_statuses = await OrderStatus.find().sort(+OrderStatus.sort_order).to_list()
    payment_statuses = await PaymentStatus.find().to_list()
    return storage, conditions, networks, brands, categories, order_statuses, payment_statuses


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/login")
async def admin_login_get(request: Request, error: str = ""):
    if _get_session(request):
        return RedirectResponse("/admin-panel", status_code=302)
    return templates.TemplateResponse("admin_login.html", {
        "request": request, "hide_sidebar": True,
        "step": "email", "error": error, "email": ""
    })


@router.post("/login")
async def admin_login_post(request: Request, email: str = Form(...)):
    from app.models.admin import Admin
    from app.models.otp import OTP

    admin = await Admin.find_one(Admin.email == email, Admin.is_active == True)
    if not admin:
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "hide_sidebar": True,
            "step": "email", "error": "Email not found or account inactive.", "email": email
        })

    code = _gen_otp()
    expires = datetime.utcnow() + timedelta(minutes=10)
    await OTP(email=email, code=code, expires_at=expires).insert()

    # Try to send email
    sent = await _send_admin_otp(email, code)
    if not sent:
        logger.info(f"[DEV OTP] {email} → {code}")

    return templates.TemplateResponse("admin_login.html", {
        "request": request, "hide_sidebar": True,
        "step": "otp", "error": "", "email": email
    })


@router.post("/login/verify")
async def admin_login_verify(request: Request, email: str = Form(...), otp: str = Form(...)):
    from app.models.otp import OTP
    from app.models.admin import Admin

    now = datetime.utcnow()
    record = await OTP.find_one(
        OTP.email == email,
        OTP.code == otp.strip(),
        OTP.is_used == False,
        OTP.expires_at > now
    )
    if not record:
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "hide_sidebar": True,
            "step": "otp", "error": "Invalid or expired OTP. Please try again.", "email": email
        })

    record.is_used = True
    await record.save()

    admin = await Admin.find_one(Admin.email == email)
    if admin:
        admin.last_login = now
        await admin.save()

    resp = RedirectResponse("/admin-panel", status_code=302)
    _set_session(resp, email)
    return resp


@router.get("/login/resend")
async def admin_login_resend(request: Request, email: str = ""):
    from app.models.otp import OTP
    from app.models.admin import Admin

    if not email:
        return RedirectResponse("/admin-panel/login", status_code=302)

    admin = await Admin.find_one(Admin.email == email, Admin.is_active == True)
    if not admin:
        return RedirectResponse("/admin-panel/login?error=Email+not+found", status_code=302)

    code = _gen_otp()
    expires = datetime.utcnow() + timedelta(minutes=10)
    await OTP(email=email, code=code, expires_at=expires).insert()

    sent = await _send_admin_otp(email, code)
    if not sent:
        logger.info(f"[DEV OTP resend] {email} → {code}")

    return templates.TemplateResponse("admin_login.html", {
        "request": request, "hide_sidebar": True,
        "step": "otp", "error": "", "email": email
    })


@router.post("/logout")
async def admin_logout(request: Request):
    resp = RedirectResponse("/admin-panel/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
@router.get("/")
async def admin_dashboard(request: Request):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.api_log import ApiLog

    orders = await _safe_orders()
    devices = await Device.find().to_list()
    api_logs = await _safe_api_logs()

    total = len(orders)
    active = sum(1 for o in orders if o.status not in ['COMPLETED', 'PAID', 'CLOSED', 'CANCELLED'])
    paid = sum(1 for o in orders if o.status in ['COMPLETED', 'PAID'])
    total_value = sum((o.final_price or o.offered_price) for o in orders if o.status in ['COMPLETED', 'PAID'])
    api_orders = sum(1 for o in orders if o.source == 'API')
    api_errors = sum(1 for l in api_logs if not l.success)
    active_devices = sum(1 for d in devices if d.is_active)

    status_map: dict = {}
    for o in orders:
        status_map[o.status] = status_map.get(o.status, 0) + 1
    status_breakdown = sorted(status_map.items(), key=lambda x: x[1], reverse=True)

    recent_orders = orders[:6]

    # Normalize api_logs for template
    api_logs_data = []
    for l in api_logs:
        ts = getattr(l, 'timestamp', None) or getattr(l, 'created_at', None)
        api_logs_data.append({
            "success": getattr(l, 'success', False),
            "order_number": getattr(l, 'order_number', None),
            "error": getattr(l, 'error', None),
            "source_ip": getattr(l, 'source_ip', ''),
            "status_code": getattr(l, 'status_code', 500),
            "created_at": ts,
        })

    return templates.TemplateResponse("admin_dashboard.html", _ctx(
        request, "dashboard", email,
        stats={
            "total_orders": total, "active_orders": active, "paid_orders": paid,
            "total_value": total_value, "api_orders": api_orders,
            "api_errors": api_errors, "active_devices": active_devices,
            "total_devices": len(devices),
        },
        recent_orders=recent_orders,
        status_breakdown=status_breakdown,
        api_logs=api_logs_data,
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/orders")
async def admin_orders(request: Request, q: str = "", status: str = "", page: int = 1, export: str = ""):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.order import Order
    from app.models.order_status import OrderStatus
    from app.models.payment_status import PaymentStatus

    all_orders = await _safe_orders()
    order_statuses = await OrderStatus.find().sort(+OrderStatus.sort_order).to_list()
    payment_statuses = await PaymentStatus.find().to_list()

    # Filter
    filtered = all_orders
    if status:
        filtered = [o for o in filtered if o.status == status]
    if q:
        ql = q.lower()
        filtered = [o for o in filtered if (
            ql in o.order_number.lower() or
            ql in o.customer_name.lower() or
            ql in (o.customer_email or "").lower() or
            ql in o.customer_phone or
            ql in o.device_name.lower()
        )]

    # Status counts
    status_counts = {}
    for o in all_orders:
        status_counts[o.status] = status_counts.get(o.status, 0) + 1

    # CSV export
    if export == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Order #', 'Customer', 'Email', 'Phone', 'Device', 'Network', 'Grade',
                         'Storage', '£ Offered', '£ Final', 'Status', 'Source', 'Payment', 'Postage', 'Date'])
        for o in filtered:
            writer.writerow([
                o.order_number, o.customer_name, o.customer_email or '', o.customer_phone,
                o.device_name, o.network, o.device_grade, o.storage,
                o.offered_price, o.final_price or '', o.status, o.source,
                o.payment_status, o.postage_method,
                o.created_at.strftime('%d/%m/%Y') if o.created_at else ''
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=orders.csv"}
        )

    # Paginate
    per_page = 20
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    paginated = filtered[(page - 1) * per_page: page * per_page]

    return templates.TemplateResponse("admin_orders.html", _ctx(
        request, "orders", email,
        orders=paginated, q=q, status_filter=status,
        order_statuses=order_statuses, payment_statuses=payment_statuses,
        total=total, total_all=len(all_orders), total_pages=total_pages,
        page=page, status_counts=status_counts,
    ))


@router.get("/orders/{order_id}")
async def admin_order_detail(request: Request, order_id: str, counter: str = ""):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.order import Order
    from app.models.order_status import OrderStatus
    from app.models.payment_status import PaymentStatus

    order = await Order.get(order_id)
    if not order:
        return RedirectResponse("/admin-panel/orders", status_code=302)

    order_statuses = await OrderStatus.find().sort(+OrderStatus.sort_order).to_list()
    payment_statuses = await PaymentStatus.find().to_list()

    status_flow = [s for s in order_statuses if s.is_active]
    current_status_idx = next(
        (i for i, s in enumerate(status_flow) if (s.value or s.name) == order.status), -1
    )

    # Extract payout_details fields for template
    payout_bank_name = order.payout_details.account_name if order.payout_details else None
    payout_account_number = order.payout_details.account_number if order.payout_details else None
    payout_sort_code = order.payout_details.sort_code if order.payout_details else None
    price_revision_reason = order.notes

    return templates.TemplateResponse("admin_order_detail.html", _ctx(
        request, "orders", email,
        order=order,
        order_statuses=order_statuses,
        payment_statuses=payment_statuses,
        status_flow=status_flow,
        current_status_idx=current_status_idx,
        show_counter_form=(counter == "1"),
        payout_bank_name=payout_bank_name,
        payout_account_number=payout_account_number,
        payout_sort_code=payout_sort_code,
        price_revision_reason=price_revision_reason,
    ))


@router.post("/orders/{order_id}/status")
async def admin_order_status(request: Request, order_id: str, status: str = Form(...)):
    email = _require_admin(request)
    if not email:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.models.order import Order
    from fastapi.responses import JSONResponse
    order = await Order.get(order_id)
    if order:
        order.status = status
        if status in ['COMPLETED', 'PAID']:
            order.payment_status = 'PAID'
        order.updated_at = datetime.utcnow()
        await order.save()

    # Support AJAX (fetch) calls from bulk update
    form_data = await request.form() if request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded') else {}
    if request.headers.get('accept', '') == 'application/json':
        return JSONResponse({"success": True})

    return RedirectResponse(f"/admin-panel/orders/{order_id}", status_code=302)


@router.post("/orders/{order_id}/delete")
async def admin_order_delete(request: Request, order_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.order import Order
    order = await Order.get(order_id)
    if order:
        await order.delete()

    return RedirectResponse("/admin-panel/orders", status_code=302)


@router.get("/orders/{order_id}/counter-offer")
async def admin_counter_offer_form(request: Request, order_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()
    return RedirectResponse(f"/admin-panel/orders/{order_id}?counter=1", status_code=302)


@router.post("/orders/{order_id}/counter-offer")
async def admin_counter_offer_post(request: Request, order_id: str,
                                   counter_price: float = Form(...), reason: str = Form(...)):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.order import Order
    order = await Order.get(order_id)
    if order:
        order.final_price = counter_price
        order.notes = reason
        order.status = "COUNTER_OFFERED"
        order.updated_at = datetime.utcnow()
        await order.save()

    return RedirectResponse(f"/admin-panel/orders/{order_id}", status_code=302)


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICE IMAGE UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/devices/upload-image")
async def admin_device_upload_image(request: Request, file: UploadFile = File(...)):
    email = _require_admin(request)
    if not email:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        from app.config.aws import get_s3_client, S3_BUCKET_NAME, S3_REGION
        import time
        import os

        ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
        allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        if ext not in allowed:
            return JSONResponse({"error": "Invalid file type. Use JPG, PNG, WebP or GIF."}, status_code=400)

        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:  # 5MB limit
            return JSONResponse({"error": "File too large. Max 5MB."}, status_code=400)

        key = f"devices/{int(time.time() * 1000)}-{file.filename.replace(' ', '-')}"
        s3 = get_s3_client()
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=contents,
            ContentType=file.content_type or "image/jpeg",
        )
        url = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{key}"
        return JSONResponse({"url": url})
    except Exception as e:
        logger.error(f"S3 upload error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/devices")
async def admin_devices(request: Request, q: str = "", brand: str = ""):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing

    all_devices = await Device.find().sort(-Device.created_at).to_list()
    all_pricing = await Pricing.find().to_list()

    # Build max_price map
    max_prices: dict = {}
    for p in all_pricing:
        did = str(p.device_id) if p.device_id else None
        if did:
            price = max(p.grade_new or 0, p.grade_good or 0, p.grade_broken or 0)
            if price > max_prices.get(did, 0):
                max_prices[did] = price

    devices = []
    for d in all_devices:
        did = str(d.id)
        devices.append({
            "id": did, "name": d.name, "full_name": d.full_name or d.name,
            "brand": d.brand, "category": d.category,
            "image_url": d.image_url, "is_active": d.is_active,
            "max_price": max_prices.get(did, 0),
        })

    brands = sorted(set(d["brand"] for d in devices))

    if brand:
        devices = [d for d in devices if d["brand"] == brand]
    if q:
        ql = q.lower()
        devices = [d for d in devices if ql in d["full_name"].lower() or ql in d["brand"].lower()]

    return templates.TemplateResponse("admin_devices.html", _ctx(
        request, "devices", email,
        devices=devices, brands=brands, q=q, brand_filter=brand,
    ))


@router.get("/devices/add")
async def admin_device_add_form(request: Request):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    storage, conditions, networks, brands, categories, _, _ = await _load_utilities()
    return templates.TemplateResponse("admin_device_form.html", _ctx(
        request, "devices", email,
        device=None, brands=brands, categories=categories,
        networks=networks, storage_options=storage, conditions=conditions,
        default_pricing=[],
        pricing_networks=[],
    ))


@router.post("/devices/add")
async def admin_device_add_post(request: Request):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing
    form = await request.form()

    brand = form.get("brand", "")
    name = form.get("name", "")
    full_name = form.get("full_name") or f"{brand.capitalize()} {name}"
    category = form.get("category", "")
    image_url = form.get("image_url") or None
    is_active = form.get("is_active") == "true"

    device = Device(brand=brand, name=name, full_name=full_name,
                    category=category, image_url=image_url, is_active=is_active)
    await device.insert()

    # Save pricing rows from form fields like "price_Unlocked_128GB_grade_new"
    await _save_device_pricing(str(device.id), name, form)

    return RedirectResponse("/admin-panel/devices", status_code=302)


@router.get("/devices/{device_id}/debug-pricing")
async def admin_device_debug_pricing(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from app.models.pricing import Pricing
    from app.models.device import Device
    col = Pricing.get_motor_collection()
    
    # Get all devices to see what device IDs exist
    all_devices = await Device.find().to_list(length=20)
    device_ids = [{"id": str(d.id), "name": d.name} for d in all_devices]
    
    # Get ALL pricing in the system (no filter)
    all_pricing = await col.find({}).to_list(length=50)
    for doc in all_pricing:
        doc["_id"] = str(doc["_id"])
    
    # Get pricing for this specific device
    device_pricing = await col.find(
        {"$or": [{"deviceId": device_id}, {"device_id": device_id}]}
    ).to_list(length=50)
    for doc in device_pricing:
        doc["_id"] = str(doc["_id"])
    
    return JSONResponse({
        "target_device_id": device_id,
        "all_devices": device_ids,
        "total_pricing_records": len(all_pricing),
        "pricing_for_device": device_pricing,
        "first_5_pricing": all_pricing[:5]
    })


@router.get("/devices/{device_id}/edit")
async def admin_device_edit_form(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing

    device = await Device.get(device_id)
    if not device:
        return RedirectResponse("/admin-panel/devices", status_code=302)

    pricing_rows = await Pricing.find(
        {"$or": [{"deviceId": device_id}, {"device_id": device_id}]}
    ).to_list()
    storage, conditions, networks, brands, categories, _, _ = await _load_utilities()

    logger.info(f"[PRICING DEBUG] device_id={device_id} rows={len(pricing_rows)}")
    for p in pricing_rows:
        logger.info(f"  row: device_id={p.device_id!r} network={p.network!r} storage={p.storage!r} new={p.grade_new} good={p.grade_good} broken={p.grade_broken}")
    logger.info(f"[UTILITIES DEBUG] networks={[(n.name, n.value) for n in networks]} storage={[(s.name, s.value) for s in storage]}")

    # Extract pricing data for template
    default_pricing = pricing_rows
    networks_used = list(set(p.network for p in pricing_rows))

    return templates.TemplateResponse("admin_device_form.html", _ctx(
        request, "devices", email,
        device=device, brands=brands, categories=categories,
        networks=networks, storage_options=storage, conditions=conditions,
        default_pricing=default_pricing,
        pricing_networks=networks_used,
    ))


@router.post("/devices/{device_id}/edit")
async def admin_device_edit_post(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    device = await Device.get(device_id)
    if not device:
        return RedirectResponse("/admin-panel/devices", status_code=302)

    form = await request.form()
    device.brand = form.get("brand", device.brand)
    device.name = form.get("name", device.name)
    device.full_name = form.get("full_name") or f"{device.brand.capitalize()} {device.name}"
    device.category = form.get("category", device.category)
    device.image_url = form.get("image_url") or device.image_url
    device.is_active = form.get("is_active") == "true"
    device.updated_at = datetime.utcnow()
    await device.save()

    await _save_device_pricing(device_id, device.name, form)

    return RedirectResponse("/admin-panel/devices", status_code=302)


@router.post("/devices/{device_id}/toggle")
async def admin_device_toggle(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    device = await Device.get(device_id)
    if device:
        device.is_active = not device.is_active
        device.updated_at = datetime.utcnow()
        await device.save()

    return RedirectResponse("/admin-panel/devices", status_code=302)


@router.post("/devices/{device_id}/delete")
async def admin_device_delete(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing
    device = await Device.get(device_id)
    if device:
        await Pricing.find({"$or": [{"deviceId": device_id}, {"device_id": device_id}]}).delete()
        await device.delete()

    return RedirectResponse("/admin-panel/devices", status_code=302)


async def _save_device_pricing(device_id: str, device_name: str, form):
    from app.models.pricing import Pricing
    # Delete existing — use raw query to match both deviceId (camelCase) and device_id fields
    await Pricing.find({"$or": [{"deviceId": device_id}, {"device_id": device_id}]}).delete()

    # Parse fields: price_{network}_{storage}_{gradeKey}
    # Field names embed network so we build: price_map[net][stor][gradeKey] = value
    price_map: dict = {}  # {net: {stor: {gradeKey: value}}}

    form_keys = list(form.keys())
    for key in form_keys:
        if not key.startswith("price_"):
            continue
        remainder = key[6:]  # strip "price_"
        # Find the grade key suffix (gradeNew, gradeGood, gradeBroken)
        grade_field = None
        for gk in ("gradeNew", "gradeGood", "gradeBroken"):
            if remainder.endswith("_" + gk):
                grade_field = gk
                net_stor = remainder[: -(len(gk) + 1)]  # strip "_gradeXxx"
                break
        if grade_field is None:
            continue
        # net_stor is like "Unlocked_128GB" or "EE_512GB"
        # Split on first "_" — but network names may contain no underscore, storage is last token
        # Storage options look like "64GB", "128GB", "512GB", "1TB" — no underscore
        # So split from the right: last token is storage, rest is network
        parts = net_stor.rsplit("_", 1)
        if len(parts) != 2:
            continue
        net, stor = parts
        if net not in price_map:
            price_map[net] = {}
        if stor not in price_map[net]:
            price_map[net][stor] = {}
        try:
            price_map[net][stor][grade_field] = float(form[key] or 0)
        except (ValueError, TypeError):
            price_map[net][stor][grade_field] = 0.0

    # Save one Pricing row per (network, storage) combination
    for net, stor_map in price_map.items():
        for stor, grades in stor_map.items():
            p = Pricing(
                device_id=device_id, device_name=device_name,
                network=net.lower(), storage=stor.lower(),
                grade_new=grades.get("gradeNew", 0),
                grade_good=grades.get("gradeGood", 0),
                grade_broken=grades.get("gradeBroken", 0),
            )
            await p.insert()


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/pricing")
async def admin_pricing(request: Request, q: str = ""):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing

    all_devices = await Device.find().sort(-Device.created_at).to_list()
    all_pricing = await Pricing.find().to_list()
    storage, conditions, networks, _, _, _, _ = await _load_utilities()

    if q:
        ql = q.lower()
        all_devices = [d for d in all_devices if ql in (d.full_name or d.name).lower()]

    # Attach pricing to each device
    devices_with_pricing = []
    for d in all_devices:
        did = str(d.id)
        pricing_rows = [p for p in all_pricing if str(p.device_id) == did]
        nets_used = list(set(p.network for p in pricing_rows))
        devices_with_pricing.append({
            "id": did, "name": d.name, "full_name": d.full_name or d.name,
            "brand": d.brand, "category": d.category,
            "image_url": d.image_url, "is_active": d.is_active,
            "pricing": pricing_rows, "pricing_networks": nets_used,
        })

    return templates.TemplateResponse("admin_pricing.html", _ctx(
        request, "pricing", email,
        devices=devices_with_pricing, q=q,
        networks=networks, storage_options=storage, conditions=conditions,
    ))


@router.post("/pricing/{device_id}")
async def admin_pricing_save(request: Request, device_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.device import Device
    from app.models.pricing import Pricing

    device = await Device.get(device_id)
    if not device:
        return RedirectResponse("/admin-panel/pricing", status_code=302)

    form = await request.form()
    networks_selected = form.getlist("networks")

    # Delete existing pricing for this device
    await Pricing.find({"$or": [{"deviceId": device_id}, {"device_id": device_id}]}).delete()

    # Parse fields: {storage}__{gradeKey}  e.g. 128GB__grade_new
    price_map: dict = {}
    for key in form.keys():
        if "__" in key and key != "networks":
            parts = key.split("__", 1)
            if len(parts) == 2:
                stor, grade_field = parts
                if stor not in price_map:
                    price_map[stor] = {}
                try:
                    price_map[stor][grade_field] = float(form[key] or 0)
                except (ValueError, TypeError):
                    price_map[stor][grade_field] = 0.0

    for net in (networks_selected or ["Unlocked"]):
        for stor, grades in price_map.items():
            any_price = any(v > 0 for v in grades.values())
            if any_price:
                p = Pricing(
                    device_id=device_id, device_name=device.name,
                    network=net, storage=stor,
                    grade_new=grades.get("grade_new", 0),
                    grade_good=grades.get("grade_good", 0),
                    grade_broken=grades.get("grade_broken", 0),
                )
                await p.insert()

    return RedirectResponse(f"/admin-panel/pricing?saved={device_id}", status_code=302)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

_UTILITY_MODEL_MAP = {
    "storage": ("app.models.storage_option", "StorageOption"),
    "conditions": ("app.models.device_condition", "DeviceCondition"),
    "networks": ("app.models.network", "Network"),
    "brands": ("app.models.brand", "Brand"),
    "categories": ("app.models.category", "Category"),
    "order_statuses": ("app.models.order_status", "OrderStatus"),
    "payment_statuses": ("app.models.payment_status", "PaymentStatus"),
}


async def _get_utility_model(tab: str):
    import importlib
    if tab not in _UTILITY_MODEL_MAP:
        return None
    mod_path, cls_name = _UTILITY_MODEL_MAP[tab]
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name, None)


@router.get("/utilities")
async def admin_utilities(request: Request, tab: str = "storage"):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    if tab not in _UTILITY_MODEL_MAP:
        tab = "storage"

    Model = await _get_utility_model(tab)
    items = []
    if Model:
        try:
            items = await Model.find().to_list()
            # Sort by sort_order if it exists
            items = sorted(items, key=lambda x: getattr(x, 'sort_order', 0))
        except Exception:
            items = await Model.find().to_list()

    # Normalize items to have consistent attributes for template
    normalized = []
    for item in items:
        normalized.append({
            "id": str(item.id),
            "name": item.name,
            "value": getattr(item, "value", None),
            "color": getattr(item, "color", None),
            "is_active": getattr(item, "is_active", True),
            "sort_order": getattr(item, "sort_order", 0),
        })

    return templates.TemplateResponse("admin_utilities.html", _ctx(
        request, "utilities", email,
        active_tab=tab, items=normalized,
    ))


@router.post("/utilities/{tab}/add")
async def admin_utility_add(request: Request, tab: str,
                             name: str = Form(...), value: str = Form(""), color: str = Form("")):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    Model = await _get_utility_model(tab)
    if Model:
        kwargs = {"name": name}
        if value:
            kwargs["value"] = value.upper()
        if color:
            kwargs["color"] = color
        try:
            await Model(**kwargs).insert()
        except Exception as e:
            logger.error(f"Utility add error: {e}")

    return RedirectResponse(f"/admin-panel/utilities?tab={tab}", status_code=302)


@router.post("/utilities/{tab}/{item_id}/update")
async def admin_utility_update(request: Request, tab: str, item_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    Model = await _get_utility_model(tab)
    if Model:
        item = await Model.get(item_id)
        if item:
            form = await request.form()
            item.name = form.get("name", item.name)
            if hasattr(item, "value") and form.get("value"):
                item.value = form.get("value", "").upper()
            if hasattr(item, "color"):
                item.color = form.get("color", "")
            if hasattr(item, "updated_at"):
                item.updated_at = datetime.utcnow()
            await item.save()

    return RedirectResponse(f"/admin-panel/utilities?tab={tab}", status_code=302)


@router.post("/utilities/{tab}/{item_id}/toggle")
async def admin_utility_toggle(request: Request, tab: str, item_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    Model = await _get_utility_model(tab)
    if Model:
        item = await Model.get(item_id)
        if item and hasattr(item, "is_active"):
            item.is_active = not item.is_active
            await item.save()

    return RedirectResponse(f"/admin-panel/utilities?tab={tab}", status_code=302)


@router.post("/utilities/{tab}/{item_id}/delete")
async def admin_utility_delete(request: Request, tab: str, item_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    Model = await _get_utility_model(tab)
    if Model:
        item = await Model.get(item_id)
        if item:
            await item.delete()

    return RedirectResponse(f"/admin-panel/utilities?tab={tab}", status_code=302)


# ═══════════════════════════════════════════════════════════════════════════════
# PARTNERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/partners")
async def admin_partners(request: Request, new_key: str = "", new_name: str = ""):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner
    partners = await _safe_partners()
    partners_data = []
    for p in partners:
        partners_data.append({
            "id": str(p.id), "name": p.name,
            "is_active": p.is_active,
            "total_orders": getattr(p, 'total_orders', 0),
            "created_at": getattr(p, 'created_at', None),
            "last_used_at": getattr(p, 'last_used_at', None),
            "api_key_preview": getattr(p, 'key_prefix', '••••••'),
        })

    return templates.TemplateResponse("admin_partners.html", _ctx(
        request, "partners", email,
        partners=partners_data,
        new_key=new_key if new_key else None,
        new_name=new_name if new_name else None,
    ))


@router.post("/partners/create")
async def admin_partner_create(request: Request, name: str = Form(...)):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner
    key_data = Partner.generate_key()
    partner = Partner(
        name=name.strip(),
        key_hash=key_data["key_hash"],
        key_prefix=key_data["key_prefix"],
        created_by=email,
    )
    await partner.insert()

    # Show the key via query param (one-time)
    pid = str(partner.id)
    plain = key_data["plain_key"]
    return RedirectResponse(f"/admin-panel/partners?new_key={plain}&new_name={name}", status_code=302)


@router.post("/partners/{partner_id}/toggle")
async def admin_partner_toggle(request: Request, partner_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner
    p = await Partner.get(partner_id)
    if p:
        p.is_active = not p.is_active
        p.updated_at = datetime.utcnow()
        await p.save()

    return RedirectResponse("/admin-panel/partners", status_code=302)


@router.post("/partners/{partner_id}/regenerate")
async def admin_partner_regenerate(request: Request, partner_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner
    p = await Partner.get(partner_id)
    if p:
        key_data = Partner.generate_key()
        p.key_hash = key_data["key_hash"]
        p.key_prefix = key_data["key_prefix"]
        p.updated_at = datetime.utcnow()
        await p.save()
        return RedirectResponse(
            f"/admin-panel/partners?new_key={key_data['plain_key']}&new_name={p.name}",
            status_code=302
        )

    return RedirectResponse("/admin-panel/partners", status_code=302)


@router.post("/partners/{partner_id}/delete")
async def admin_partner_delete(request: Request, partner_id: str):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner
    p = await Partner.get(partner_id)
    if p:
        await p.delete()

    return RedirectResponse("/admin-panel/partners", status_code=302)


# ═══════════════════════════════════════════════════════════════════════════════
# API GATEWAY
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api-gateway")
async def admin_api_gateway(request: Request):
    email = _require_admin(request)
    if not email:
        return _redirect_login()

    from app.models.partner import Partner

    try:
        logs_raw = await _safe_api_logs(100)
        partners = await Partner.find().to_list()
        partner_map = {p.name: p.name for p in partners}

        total = len(logs_raw)
        successful = sum(1 for l in logs_raw if getattr(l, 'success', False))
        failed = total - successful
        avg_response = int(sum(getattr(l, 'response_time', 0) or 0 for l in logs_raw) / total) if total else 0

        # Attach partner_name from partner lookup if not stored
        logs = []
        for l in logs_raw:
            ts = getattr(l, 'timestamp', None) or getattr(l, 'created_at', None) or datetime.utcnow()
            logs.append({
                "id": str(l.id),
                "success": getattr(l, 'success', False),
                "order_number": getattr(l, 'order_number', None),
                "error": getattr(l, 'error', None),
                "source_ip": getattr(l, 'source_ip', ''),
                "response_time": getattr(l, 'response_time', 0),
                "status_code": getattr(l, 'status_code', 500),
                "timestamp": ts,
                "created_at": ts,
                "payload": getattr(l, 'payload', None),
                "partner_name": None,
            })
    except Exception as e:
        logger.error(f"Error fetching API logs: {str(e)}")
        logs = []
        total = successful = failed = avg_response = 0

    return templates.TemplateResponse("admin_api_gateway.html", _ctx(
        request, "api-gateway", email,
        logs=logs,
        stats={
            "total": total, "successful": successful,
            "failed": failed, "avg_response": avg_response,
        }
    ))
