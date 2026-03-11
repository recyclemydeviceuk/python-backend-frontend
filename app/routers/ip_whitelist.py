from fastapi import APIRouter, Depends, HTTPException
from app.models.ip_whitelist import IpWhitelist
from app.middleware.auth import get_current_admin
from app.utils.response import success_response, created_response
from app.utils.logger import logger


router = APIRouter(prefix="/ip-whitelist", tags=["IP Whitelist"])


@router.get("", summary="Get all whitelisted IPs", dependencies=[Depends(get_current_admin)])
async def get_all():
    entries = await IpWhitelist.find().sort(-IpWhitelist.created_at).to_list()
    return success_response({"entries": [_serialize(e) for e in entries]})


@router.post("", summary="Add IP to whitelist", dependencies=[Depends(get_current_admin)])
async def add_ip(ip_address: str, label: str = None):
    existing = await IpWhitelist.find_one(IpWhitelist.ip_address == ip_address)
    if existing:
        raise HTTPException(status_code=409, detail="IP address already whitelisted")
    entry = IpWhitelist(ip_address=ip_address, label=label)
    await entry.insert()
    logger.info(f"IP whitelisted: {ip_address}")
    return created_response({"entry": _serialize(entry)}, "IP added to whitelist")


@router.patch("/{entry_id}/toggle", summary="Toggle IP active status", dependencies=[Depends(get_current_admin)])
async def toggle_ip(entry_id: str):
    entry = await IpWhitelist.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="IP entry not found")
    entry.is_active = not entry.is_active
    await entry.save()
    return success_response({"entry": _serialize(entry)}, "IP status toggled")


@router.delete("/{entry_id}", summary="Remove IP from whitelist", dependencies=[Depends(get_current_admin)])
async def delete_ip(entry_id: str):
    entry = await IpWhitelist.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="IP entry not found")
    await entry.delete()
    logger.info(f"IP removed from whitelist: {entry.ip_address}")
    return success_response({"message": "IP removed from whitelist"})


def _serialize(e: IpWhitelist) -> dict:
    return {
        "id": str(e.id),
        "ip_address": e.ip_address,
        "label": e.label,
        "is_active": e.is_active,
        "created_at": e.created_at.isoformat(),
    }
