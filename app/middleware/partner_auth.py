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
            detail="Missing X-Partner-Key header. Please include your partner API key.",
        )

    # Fetch all active partners and verify by bcrypt hash
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
            detail="Invalid or inactive partner API key.",
        )

    # Update last_used_at asynchronously (fire and forget)
    try:
        matched.last_used_at = datetime.utcnow()
        await matched.save()
    except Exception:
        pass

    return matched
