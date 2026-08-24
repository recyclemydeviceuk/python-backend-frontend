from fastapi import Request, HTTPException, status
from typing import Optional
from app.models.ip_whitelist import IpWhitelist
from app.utils.logger import logger


def get_client_ip(request: Request) -> Optional[str]:
    """Resolve the real originating IP, honouring the proxy in front of us.

    Vercel / load balancers terminate the TCP connection themselves, so
    `request.client.host` is the PROXY's address, not the partner's. The
    originating IP is the first entry of X-Forwarded-For.

    NOTE: X-Forwarded-For is client-supplied and therefore spoofable unless the
    app is only reachable through the trusted proxy. Do not treat this as a
    security boundary on its own — it is a second factor alongside the
    X-Partner-Key.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return request.client.host if request.client else None


async def is_ip_whitelisted(client_ip: Optional[str]) -> bool:
    """True if `client_ip` matches any active whitelist entry (IP or CIDR)."""
    if not client_ip:
        return False
    entries = await IpWhitelist.find(IpWhitelist.is_active == True).to_list()
    return any(e.matches(client_ip) for e in entries)


async def require_whitelisted_ip(request: Request):
    """Dependency: raises 403 if the client IP is not whitelisted."""
    client_ip = get_client_ip(request)

    if not await is_ip_whitelisted(client_ip):
        logger.warning(f"Blocked request from non-whitelisted IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP address not whitelisted",
        )
