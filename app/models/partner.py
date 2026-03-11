from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime
import hashlib
import secrets


class Partner(Document):
    name: str
    key_hash: str
    key_prefix: str
    is_active: bool = True
    last_used_at: Optional[datetime] = None
    total_orders: int = 0
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def generate_key() -> dict:
        """Generate a cryptographically secure partner key.
        Format: cmm_pk_<32 random hex chars>
        Returns { plainKey, keyHash, keyPrefix }
        """
        random_hex = secrets.token_hex(32)
        plain_key = f"cmm_pk_{random_hex}"
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        key_prefix = f"cmm_pk_{random_hex[:8]}..."
        return {
            "plain_key": plain_key,
            "key_hash": key_hash,
            "key_prefix": key_prefix
        }

    @staticmethod
    def verify_key(plain_key: str, key_hash: str) -> bool:
        """Verify a raw key against a stored hash"""
        hash_check = hashlib.sha256(plain_key.encode()).hexdigest()
        return hash_check == key_hash

    class Settings:
        name = "partners"
        indexes = ["name", "key_hash", "is_active"]
