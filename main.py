import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.config.database import connect_db, close_db
from app.routers import api_router
from app.middleware.request_logger import RequestLoggerMiddleware
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.utils.logger import logger


# ── Ensure required directories exist ─────────────────────────────────────────
for d in ["logs", "uploads", "uploads/images", "uploads/csv", "exports"]:
    Path(d).mkdir(parents=True, exist_ok=True)


async def _seed_admins():
    from app.models.admin import Admin
    from app.config.constants import AdminRole
    emails = [e.strip() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
    for email in emails:
        exists = await Admin.find_one(Admin.email == email)
        if not exists:
            username = email.split("@")[0]
            await Admin(email=email, username=username, role=AdminRole.ADMIN, is_active=True).insert()
            logger.info(f"[Admin seed] Created admin: {email}")
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
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(RequestLoggerMiddleware)

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
    all_conds = await DeviceCondition.find(DeviceCondition.is_active == True).sort(DeviceCondition.sort_order).to_list()
    conditions = []
    for c in all_conds:
        grade_key = c.value.upper()
        price_map = {"NEW": price_row.get("gradeNew", 0), "GOOD": price_row.get("gradeGood", 0), "BROKEN": price_row.get("gradeBroken", 0)}
        price = price_map.get(grade_key, 0)
        if price > 0:
            conditions.append({"name": c.name, "value": c.value, "description": c.description or "", "price": price})
    if not conditions and price_row:
        grade_key_map = {"NEW": "gradeNew", "GOOD": "gradeGood", "BROKEN": "gradeBroken"}
        for grade_key, label, desc in [("NEW", "New / Excellent", "Perfect or near-perfect condition."), ("GOOD", "Good / Working", "Fully working with minor wear."), ("BROKEN", "Broken / Faulty", "Cracked screen or hardware faults.")]:
            price = price_row.get(grade_key_map[grade_key], 0) or 0
            if price > 0:
                conditions.append({"name": label, "value": grade_key, "description": desc, "price": price})
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
