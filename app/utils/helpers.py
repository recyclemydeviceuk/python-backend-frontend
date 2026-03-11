import re
from datetime import datetime, timezone
from typing import Optional
from app.config.constants import VALIDATION_PATTERNS


def is_valid_email(email: str) -> bool:
    return bool(VALIDATION_PATTERNS["EMAIL"].match(email))


def is_valid_uk_phone(phone: str) -> bool:
    return bool(VALIDATION_PATTERNS["PHONE_UK"].match(phone))


def is_valid_uk_postcode(postcode: str) -> bool:
    return bool(VALIDATION_PATTERNS["POSTCODE_UK"].match(postcode))


def is_valid_sort_code(sort_code: str) -> bool:
    return bool(VALIDATION_PATTERNS["SORT_CODE"].match(sort_code))


def is_valid_account_number(account_number: str) -> bool:
    return bool(VALIDATION_PATTERNS["ACCOUNT_NUMBER"].match(account_number))


def sanitize_string(value: str) -> str:
    return value.strip() if value else value


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def mask_sensitive(value: str, visible: int = 4) -> str:
    """Mask all but last N characters."""
    if not value or len(value) <= visible:
        return "*" * len(value) if value else ""
    return "*" * (len(value) - visible) + value[-visible:]


def parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    return value.lower() in ("true", "1", "yes")
