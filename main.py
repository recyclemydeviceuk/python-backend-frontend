import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.config.database import connect_db, close_db
from app.routers import api_router
from app.utils.logger import logger


# ── Ensure required directories exist ─────────────────────────────────────────
for d in ["logs", "uploads", "uploads/images", "uploads/csv", "exports"]:
    Path(d).mkdir(parents=True, exist_ok=True)


async def _seed_workflow_statuses():
    """Ensure the OrderStatus and PaymentStatus utility collections always
    contain the canonical workflow values that backend code (order emails,
    payment auto-flip, etc.) actually uses. The admin panel reads from these
    collections to render the 'Update Order Status' modal — if they're empty
    or contain unrelated entries, admins cannot move orders through the
    workflow.

    Idempotent: only inserts when a row with the same `value` is missing.
    Existing custom rows are left untouched (admins can deactivate them via
    the Utilities page if they want a clean list)."""
    from app.models.order_status import OrderStatus
    from app.models.payment_status import PaymentStatus

    canonical_order_statuses = [
        ("Received",            "RECEIVED",            "bg-blue-100 text-blue-700",       1),
        ("Pack Sent",           "PACK_SENT",           "bg-indigo-100 text-indigo-700",   2),
        ("Device Received",     "DEVICE_RECEIVED",     "bg-purple-100 text-purple-700",   3),
        ("Inspection Passed",   "INSPECTION_PASSED",   "bg-emerald-100 text-emerald-700", 4),
        ("Inspection Failed",   "INSPECTION_FAILED",   "bg-rose-100 text-rose-700",       5),
        ("Price Revised",       "PRICE_REVISED",       "bg-amber-100 text-amber-700",     6),
        ("Payout Ready",        "PAYOUT_READY",        "bg-teal-100 text-teal-700",       7),
        ("Paid",                "PAID",                "bg-green-100 text-green-700",     8),
        ("Closed",              "CLOSED",              "bg-gray-100 text-gray-700",       9),
        ("Cancelled",           "CANCELLED",           "bg-red-100 text-red-700",        10),
    ]
    for name, value, color, sort_order in canonical_order_statuses:
        existing = await OrderStatus.find_one(OrderStatus.value == value)
        if not existing:
            await OrderStatus(
                name=name, value=value, color=color,
                sort_order=sort_order, is_active=True,
            ).insert()
            logger.info(f"[Status seed] Created OrderStatus: {value}")

    canonical_payment_statuses = [
        ("Pending", "PENDING", "bg-amber-100 text-amber-700", 1),
        ("Paid",    "PAID",    "bg-green-100 text-green-700", 2),
    ]
    for name, value, color, sort_order in canonical_payment_statuses:
        existing = await PaymentStatus.find_one(PaymentStatus.value == value)
        if not existing:
            await PaymentStatus(
                name=name, value=value, color=color,
                sort_order=sort_order, is_active=True,
            ).insert()
            logger.info(f"[Status seed] Created PaymentStatus: {value}")


async def _seed_admins():
    from app.models.admin import Admin
    from app.config.constants import AdminRole
    # Hardcoded admin emails
    emails = ["sellyourfone@gmail.com", "thekhushnoor@gmail.com", "Hameeduk1@yahoo.co.uk"]
    for email in emails:
        exists = await Admin.find_one(Admin.email == email)
        if not exists:
            username = email.split("@")[0]
            await Admin(email=email, username=username, role=AdminRole.ADMIN, is_active=True).insert()
            logger.info(f"[Admin seed] Created admin: {email}")
        else:
            # Ensure existing admin is active
            if not exists.is_active or exists.role != AdminRole.ADMIN:
                exists.is_active = True
                exists.role = AdminRole.ADMIN
                await exists.save()
                logger.info(f"[Admin seed] Updated admin to active: {email}")
            else:
                logger.info(f"[Admin seed] Already exists: {email}")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=================================")
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"  Environment : {settings.ENVIRONMENT}")
    logger.info(f"  Port        : {settings.PORT}")
    logger.info("=================================")
    await connect_db()
    await _seed_admins()
    await _seed_workflow_statuses()
    yield
    await close_db()
    logger.info("Server shut down gracefully.")


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="CashMyMobile REST API — FastAPI / Python backend",
    docs_url="/docs" if settings.NODE_ENV != "production" else None,
    redoc_url="/redoc" if settings.NODE_ENV != "production" else None,
    lifespan=lifespan,
)

# ── Custom Middleware ──────────────────────────────────────────────────────────
# ── CORS ───────────────────────────────────────────────────────────────────────
# Add CORS last so it runs FIRST (Starlette runs middleware in reverse order)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight for 24 hours
)

# ── Static Files ───────────────────────────────────────────────────────────────
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/exports", StaticFiles(directory="exports"), name="exports")

# ── Global validation-error handler ────────────────────────────────────────────
# Pydantic body validation failures normally return an opaque 422 — partners
# integrating against /api/gateway only see "UnprocessableEntity" and have no
# way to know which field was wrong. This handler always returns a parseable
# JSON body that names the offending field(s).
@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors() or []
    # Build a human-readable summary of what went wrong
    summary_parts = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body",))
        msg = err.get("msg", "invalid")
        summary_parts.append(f"{loc}: {msg}" if loc else msg)
    summary = "; ".join(summary_parts) or "Request validation failed."

    # Best-effort: log gateway validation failures into the API log so admins
    # can debug what partners are actually sending.
    if request.url.path.startswith("/api/gateway"):
        try:
            from app.models.api_log import ApiLog
            raw_body = ""
            try:
                raw_bytes = await request.body()
                raw_body = raw_bytes.decode("utf-8", errors="replace")[:4000]
            except Exception:
                pass
            await ApiLog(
                method=request.method,
                endpoint=str(request.url.path),
                status_code=422,
                source_ip=request.client.host if request.client else "unknown",
                payload=raw_body or json.dumps({"errors": errors}, default=str)[:4000],
                error=summary,
                response_time=0,
                success=False,
                order_number=None,
            ).insert()
        except Exception:
            pass

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": summary,
            "message": summary,
            "errors": [
                {
                    "field": ".".join(str(p) for p in e.get("loc", []) if p not in ("body",)),
                    "message": e.get("msg"),
                    "type": e.get("type"),
                }
                for e in errors
            ],
        },
    )


# ── API Routes ─────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api")

# ── Admin Panel SSR Routes ──────────────────────────────────────────────────────
from app.routers.admin_panel import router as admin_panel_router
app.include_router(admin_panel_router)

# ── Frontend Static Files ──────────────────────────────────────────────────────
_frontend_dir = Path(__file__).parent / "corefrontend"
_templates_dir = _frontend_dir / "templates"

if _frontend_dir.exists():
    _css_dir = _frontend_dir / "css"
    _js_dir = _frontend_dir / "js"
    if _css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(_css_dir)), name="frontend-css")
    if _js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(_js_dir)), name="frontend-js")
    app.mount("/static-frontend", StaticFiles(directory=str(_frontend_dir)), name="frontend-static")

templates = Jinja2Templates(directory=str(_templates_dir))

# Expose support contact details to every template so we can change them in
# one place (settings.SUPPORT_PHONE / SUPPORT_EMAIL) without hunting through
# the templates. Setting SUPPORT_PHONE to "" via env var hides every
# click-to-call CTA across the public site (contact, footer, counter-offer,
# complaint pages).
templates.env.globals["support_phone"] = settings.SUPPORT_PHONE or ""
templates.env.globals["support_email"] = settings.SUPPORT_EMAIL or "Support@cashmymobile.co.uk"


# ── Shared helper ──────────────────────────────────────────────────────────
async def _get_devices_with_prices():
    from app.models.device import Device
    from app.models.pricing import Pricing
    devices = await Device.find(Device.is_active == True).sort(-Device.created_at).to_list()
    all_pricing = await Pricing.find().to_list()
    max_prices: dict = {}
    for p in all_pricing:
        did = str(p.device_id) if p.device_id else None
        if did:
            price = max(p.grade_new or 0, p.grade_good or 0, p.grade_broken or 0)
            if price > max_prices.get(did, 0):
                max_prices[did] = price
    devices_data = []
    for d in devices:
        did = str(d.id)
        devices_data.append({
            "id": did,
            "name": d.name,
            "full_name": d.full_name or d.name,
            "brand": d.brand.lower(),
            "image_url": d.image_url or "",
            "max_price": max_prices.get(did, 0),
        })
    return devices_data


# ── Root & Health ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root(request: Request):
    if not (_templates_dir.exists() and (_templates_dir / "index.html").exists()):
        return {
            "success": True,
            "message": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "endpoints": {"health": "/health", "api": "/api", "docs": "/docs"},
        }
    devices_data = await _get_devices_with_prices()
    apple_devices = [d for d in devices_data if d["brand"] == "apple"][:8]
    samsung_devices = [d for d in devices_data if d["brand"] == "samsung"][:8]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "active_page": "home",
        "apple_devices": apple_devices,
        "samsung_devices": samsung_devices,
    })


@app.get("/about", tags=["Frontend"])
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "active_page": "about"})


@app.get("/contact", tags=["Frontend"])
async def contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "active_page": "contact"})


@app.get("/complaint", tags=["Frontend"])
async def complaint_get(request: Request):
    return templates.TemplateResponse("complaint.html", {"request": request, "active_page": "complaint", "submitted": False})


@app.post("/complaint", tags=["Frontend"])
async def complaint_post(request: Request):
    return templates.TemplateResponse("complaint.html", {"request": request, "active_page": "complaint", "submitted": True})


@app.get("/faq", tags=["Frontend"])
async def faq(request: Request):
    return templates.TemplateResponse("faq.html", {"request": request, "active_page": "faq"})


@app.get("/how-it-works", tags=["Frontend"])
async def how_it_works(request: Request):
    return templates.TemplateResponse("how-it-works.html", {"request": request, "active_page": "how"})


@app.get("/sell", tags=["Frontend"])
async def sell(request: Request, brand: str = "all", q: str = ""):
    devices_data = await _get_devices_with_prices()
    q_lower = q.strip().lower()
    def match(d):
        if q_lower and q_lower not in d["full_name"].lower() and q_lower not in d["name"].lower():
            return False
        return True
    apple_devices = [d for d in devices_data if d["brand"] == "apple" and match(d)]
    samsung_devices = [d for d in devices_data if d["brand"] == "samsung" and match(d)]
    if brand == "apple":
        samsung_devices = []
    elif brand == "samsung":
        apple_devices = []
    return templates.TemplateResponse("sell.html", {
        "request": request,
        "active_page": "sell",
        "apple_devices": apple_devices,
        "samsung_devices": samsung_devices,
        "brand": brand,
        "q": q,
    })


# ── Multi-page sell flow (no-JS) ────────────────────────────────────────────────────
@app.get("/sell/storage", tags=["Frontend"])
async def sell_storage(request: Request, device_id: str, device_name: str):
    from app.models.pricing import Pricing
    from bson import ObjectId
    try:
        oid = ObjectId(device_id)
    except Exception:
        oid = device_id
    pricing_docs = await Pricing.get_motor_collection().find({"deviceId": oid}).to_list(length=None)
    storage_set = sorted(set(p["storage"] for p in pricing_docs if p.get("storage")),
                         key=lambda v: int("".join(filter(str.isdigit, v)) or "0") * (1024 if "tb" in v.lower() else 1))
    storage_max = {}
    for p in pricing_docs:
        s = p.get("storage", "")
        mx = max(p.get("gradeNew", 0), p.get("gradeGood", 0), p.get("gradeBroken", 0))
        if mx > storage_max.get(s, 0):
            storage_max[s] = mx
    storage_options = [{"value": s, "max_price": storage_max.get(s, 0)} for s in storage_set]
    return templates.TemplateResponse("sell_storage.html", {
        "request": request, "active_page": "sell",
        "device_id": device_id, "device_name": device_name,
        "storage_options": storage_options,
    })


@app.get("/sell/network", tags=["Frontend"])
async def sell_network(request: Request, device_id: str, device_name: str, storage: str):
    from app.models.pricing import Pricing
    from bson import ObjectId
    try:
        oid = ObjectId(device_id)
    except Exception:
        oid = device_id
    pricing_docs = await Pricing.get_motor_collection().find({"deviceId": oid, "storage": storage}).to_list(length=None)
    network_set = sorted(set(p["network"] for p in pricing_docs if p.get("network")))
    network_max = {}
    for p in pricing_docs:
        n = p.get("network", "")
        mx = max(p.get("gradeNew", 0), p.get("gradeGood", 0), p.get("gradeBroken", 0))
        if mx > network_max.get(n, 0):
            network_max[n] = mx
    network_options = [{"value": n, "max_price": network_max.get(n, 0)} for n in network_set]
    return templates.TemplateResponse("sell_network.html", {
        "request": request, "active_page": "sell",
        "device_id": device_id, "device_name": device_name,
        "storage": storage, "network_options": network_options,
    })


@app.get("/sell/condition", tags=["Frontend"])
async def sell_condition(request: Request, device_id: str, device_name: str, storage: str, network: str):
    from app.models.pricing import Pricing
    from app.models.device_condition import DeviceCondition
    from bson import ObjectId
    try:
        oid = ObjectId(device_id)
    except Exception:
        oid = device_id
    pricing_docs = await Pricing.get_motor_collection().find(
        {"deviceId": oid, "storage": storage, "network": network}
    ).to_list(length=None)
    price_row = pricing_docs[0] if pricing_docs else {}

    # Read stored grade prices (support both camelCase aliases and snake_case)
    raw_new = float(price_row.get("gradeNew") or price_row.get("grade_new") or 0)
    raw_good = float(price_row.get("gradeGood") or price_row.get("grade_good") or 0)
    raw_broken = float(price_row.get("gradeBroken") or price_row.get("grade_broken") or 0)

    # Pick a "good-equivalent" anchor for derivation when grade columns are
    # missing or all duplicated (e.g. the CSV import populated all three with
    # the same value).
    if raw_good > 0:
        good_anchor = raw_good
    elif raw_new > 0:
        good_anchor = raw_new / 1.15
    elif raw_broken > 0:
        good_anchor = raw_broken / 0.4
    else:
        good_anchor = 0

    distinct_grades = {p for p in (raw_new, raw_good, raw_broken) if p > 0}
    if len(distinct_grades) >= 2:
        # DB has differentiated per-grade pricing — trust it, derive any missing
        derived = {
            "NEW":    raw_new    if raw_new    > 0 else round(good_anchor * 1.15),
            "GOOD":   raw_good   if raw_good   > 0 else round(good_anchor),
            "BROKEN": raw_broken if raw_broken > 0 else round(good_anchor * 0.4),
        }
    else:
        # All three are zero or all three are the same value → derive from anchor
        derived = {
            "NEW":    round(good_anchor * 1.15),
            "GOOD":   round(good_anchor),
            "BROKEN": round(good_anchor * 0.4),
        }

    # Always offer all three grades — use DeviceCondition entries only as
    # optional name/description overrides keyed by NEW/GOOD/BROKEN.
    default_grades = [
        ("NEW",    "New / Excellent",  "Perfect or near-perfect condition."),
        ("GOOD",   "Good / Working",   "Fully working with minor wear."),
        ("BROKEN", "Broken / Faulty",  "Cracked screen or hardware faults."),
    ]
    overrides: dict = {}
    try:
        all_conds = await DeviceCondition.find(
            DeviceCondition.is_active == True
        ).sort(DeviceCondition.sort_order).to_list()
        for c in all_conds:
            key = (c.value or "").strip().upper()
            if key in ("NEW", "GOOD", "BROKEN") and key not in overrides:
                overrides[key] = {"name": c.name, "description": c.description or ""}
    except Exception:
        pass

    conditions = []
    for grade_key, default_label, default_desc in default_grades:
        price = derived.get(grade_key, 0)
        if price > 0:
            override = overrides.get(grade_key) or {}
            conditions.append({
                "name": override.get("name") or default_label,
                "value": grade_key,
                "description": override.get("description") or default_desc,
                "price": price,
            })
    return templates.TemplateResponse("sell_condition.html", {
        "request": request, "active_page": "sell",
        "device_id": device_id, "device_name": device_name,
        "storage": storage, "network": network, "conditions": conditions,
    })


@app.get("/sell/details", tags=["Frontend"])
async def sell_details(request: Request, device_id: str, device_name: str, storage: str, network: str, condition: str, price: float):
    return templates.TemplateResponse("sell_details.html", {
        "request": request, "active_page": "sell",
        "device_id": device_id, "device_name": device_name,
        "storage": storage, "network": network,
        "condition": condition, "price": price,
    })


@app.post("/sell/submit", tags=["Frontend"])
async def sell_submit(
    request: Request,
    device_id: str = Form(...),
    device_name: str = Form(...),
    storage: str = Form(...),
    network: str = Form(...),
    condition: str = Form(...),
    price: float = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    postcode: str = Form(...),
    account_name: str = Form(...),
    sort_code: str = Form(...),
    account_number: str = Form(...),
    postage_method: str = Form("label"),
):
    from app.models.order import Order, PayoutDetails
    from app.utils.order_number import generate_unique_order_number
    from app.config.constants import OrderSource
    from app.services.email_service import send_order_confirmation
    order_number = await generate_unique_order_number()
    order = Order(
        order_number=order_number,
        source=OrderSource.WEBSITE,
        customer_name=full_name,
        customer_phone=phone,
        customer_email=email,
        customer_address=address,
        postcode=postcode,
        device_id=device_id,
        device_name=device_name,
        network=network,
        device_grade=condition,
        storage=storage,
        offered_price=price,
        postage_method=postage_method,
        payment_method="bank",
        payout_details=PayoutDetails(
            account_name=account_name,
            sort_code=sort_code,
            account_number=account_number,
        ),
    )
    await order.insert()
    if order.customer_email:
        await send_order_confirmation(order)
    return RedirectResponse(url=f"/sell/success?order_number={order.order_number}&device_name={device_name}&price={price}&postage_method={postage_method}", status_code=303)


@app.get("/sell/success", tags=["Frontend"])
async def sell_success(request: Request, order_number: str, device_name: str, price: float, postage_method: str = "label"):
    return templates.TemplateResponse("sell_success.html", {
        "request": request, "active_page": "sell",
        "order_number": order_number,
        "device_name": device_name,
        "price": price,
        "postage_method": postage_method,
    })


@app.get("/terms", tags=["Frontend"])
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request, "active_page": ""})


@app.get("/privacy", tags=["Frontend"])
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "active_page": ""})


@app.get("/counter-offer", tags=["Frontend"])
async def counter_offer(request: Request):
    return templates.TemplateResponse("counter-offer.html", {"request": request, "active_page": ""})


@app.get("/{page_name}.html", tags=["Frontend"])
async def serve_html_legacy(page_name: str, request: Request):
    from fastapi.responses import RedirectResponse
    redirects = {
        "index": "/", "about": "/about", "contact": "/contact",
        "faq": "/faq", "how-it-works": "/how-it-works", "sell": "/sell",
        "terms": "/terms", "privacy": "/privacy", "counter-offer": "/counter-offer",
    }
    if page_name in redirects:
        return RedirectResponse(url=redirects[page_name], status_code=301)
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/health", tags=["Root"])
async def health():
    import psutil, time
    return {
        "status": "OK",
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - psutil.boot_time()),
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    from fastapi.responses import FileResponse
    _svg = Path(__file__).parent / "corefrontend" / "favicon.svg"
    if _svg.exists():
        return FileResponse(str(_svg), media_type="image/svg+xml")
    from fastapi.responses import Response
    return Response(status_code=204)


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=os.environ.get("NODE_ENV", "production") == "development",
        log_level="info",
    )
