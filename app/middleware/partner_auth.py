from fastapi import Depends, HTTPException, status, Header, Request
from typing import Optional
from datetime import datetime
from app.models.partner import Partner
from app.utils.logger import logger


async def get_current_partner(
    request: Request,
    x_partner_key: Optional[str] = Header(None),
) -> Partner:
    """Validate X-Partner-Key header — matches Node.js partnerAuth middleware."""
    if not x_partner_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication failed: the 'X-Partner-Key' header is missing. "
                "Please include your partner API key on every request, e.g. "
                "'X-Partner-Key: cmm_pk_xxxxxxxx...'."
            ),
        )

    if not x_partner_key.startswith("cmm_pk_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication failed: the partner API key format is invalid. "
                "Keys must begin with 'cmm_pk_'. Please copy the key from the "
                "Partners page of the CashMyMobile admin panel."
            ),
        )

    active_partners = await Partner.find(Partner.is_active == True).to_list()
    matched = next(
        (p for p in active_partners if Partner.verify_key(x_partner_key, p.key_hash)),
        None,
    )

    if not matched:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Invalid or inactive partner key attempt from IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication failed: the partner API key is either invalid, "
                "revoked, or belongs to a disabled partner account. "
                "Please contact support@cashmymobile.co.uk if you believe this is in error."
            ),
        )

    # Update last_used_at asynchronously (fire and forget)
    try:
        matched.last_used_at = datetime.utcnow()
        await matched.save()
    except Exception:
        pass

    return matched
