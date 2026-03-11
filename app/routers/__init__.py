from fastapi import APIRouter
from app.routers import (
    auth, devices, orders, pricing, utilities,
    dashboard, contact, upload, export,
    counter_offers, partners, api_logs, ip_whitelist, api_gateway,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(orders.router)
api_router.include_router(devices.router)
api_router.include_router(pricing.router)
api_router.include_router(utilities.router)
api_router.include_router(api_gateway.router)
api_router.include_router(api_logs.router)
api_router.include_router(dashboard.router)
api_router.include_router(contact.router)
api_router.include_router(upload.router)
api_router.include_router(export.router)
api_router.include_router(counter_offers.router)
api_router.include_router(partners.router)
api_router.include_router(ip_whitelist.router)
