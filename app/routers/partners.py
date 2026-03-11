import secrets
from fastapi import APIRouter, Depends, HTTPException
from app.models.partner import Partner
from app.schemas.partner import CreatePartnerSchema, UpdatePartnerSchema
from app.middleware.auth import get_current_admin
from app.utils.response import success_response, created_response
from app.utils.logger import logger
from datetime import datetime

router = APIRouter(prefix="/partners", tags=["Partners"])


def _make_raw_key() -> str:
    return f"cmm_pk_{secrets.token_hex(24)}"


@router.get("", summary="Get all partners", dependencies=[Depends(get_current_admin)])
async def get_partners():
    partners = await Partner.find().sort(-Partner.created_at).to_list()
    return success_response({"partners": [_serialize(p) for p in partners]})


@router.get("/{partner_id}", summary="Get partner by ID", dependencies=[Depends(get_current_admin)])
async def get_partner(partner_id: str):
    partner = await Partner.get(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return success_response({"partner": _serialize(partner)})


@router.post("", summary="Create partner", dependencies=[Depends(get_current_admin)])
async def create_partner(body: CreatePartnerSchema):
    raw_key = _make_raw_key()
    partner = Partner(
        name=body.name,
        key_hash=Partner.hash_key(raw_key),
        allowed_ips=body.allowed_ips,
        rate_limit=body.rate_limit,
        notes=body.notes,
    )
    await partner.insert()
    logger.info(f"Partner created: {partner.name}")
    data = _serialize(partner)
    data["api_key"] = raw_key  # return raw key ONCE at creation
    return created_response({"partner": data}, "Partner created successfully. Save the api_key — it will not be shown again.")


@router.put("/{partner_id}", summary="Update partner", dependencies=[Depends(get_current_admin)])
async def update_partner(partner_id: str, body: UpdatePartnerSchema):
    partner = await Partner.get(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(partner, k, v)
    partner.updated_at = datetime.utcnow()
    await partner.save()
    return success_response({"partner": _serialize(partner)}, "Partner updated")


@router.post("/{partner_id}/regenerate-key", summary="Regenerate API key", dependencies=[Depends(get_current_admin)])
async def regenerate_key(partner_id: str):
    partner = await Partner.get(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    raw_key = _make_raw_key()
    partner.key_hash = Partner.hash_key(raw_key)
    partner.updated_at = datetime.utcnow()
    await partner.save()
    return success_response({"api_key": raw_key}, "API key regenerated. Save it — it will not be shown again.")


@router.delete("/{partner_id}", summary="Delete partner", dependencies=[Depends(get_current_admin)])
async def delete_partner(partner_id: str):
    partner = await Partner.get(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    await partner.delete()
    return success_response({"message": "Partner deleted"})


def _serialize(p: Partner) -> dict:
    return {
        "id": str(p.id), "name": p.name,
        "is_active": p.is_active, "allowed_ips": p.allowed_ips,
        "rate_limit": p.rate_limit, "total_orders": p.total_orders,
        "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
        "notes": p.notes, "created_at": p.created_at.isoformat(),
    }
