from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime
import ipaddress


class IpWhitelist(Document):
    # Either a single address ("91.102.184.10") or a CIDR range
    # ("91.102.184.0/24") — partners such as MONY Group supply ranges, not
    # individual IPs, so both forms must be storable and matchable.
    ip_address: str
    label: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def is_valid(value: str) -> bool:
        """True if `value` parses as a single IP or a CIDR network."""
        try:
            ipaddress.ip_network(value, strict=False)
            return True
        except ValueError:
            return False

    def matches(self, client_ip: str) -> bool:
        """True if `client_ip` falls inside this entry (exact IP or CIDR range)."""
        try:
            return ipaddress.ip_address(client_ip) in ipaddress.ip_network(
                self.ip_address, strict=False
            )
        except ValueError:
            return False

    class Settings:
        name = "ipwhitelists"
        indexes = ["ip_address", "is_active"]
