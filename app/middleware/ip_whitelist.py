from fastapi import Request, HTTPException, status
from app.models.ip_whitelist import IpWhitelist
from app.utils.logger import logger


async def require_whitelisted_ip(request: Request):
    """Dependency: raises 403 if client IP is not in whitelist."""
    client_ip = request.client.host if request.client else None

    if not client_ip:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP address not whitelisted")

    entry = await IpWhitelist.find_one(
        IpWhitelist.ip_address == client_ip,
        IpWhitelist.is_active == True,
    )

    if not entry:
        logger.warning(f"Blocked request from non-whitelisted IP: {client_ip}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP address not whitelisted")
