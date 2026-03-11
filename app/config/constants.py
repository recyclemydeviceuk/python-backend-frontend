from enum import Enum


class OrderStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PACK_SENT = "PACK_SENT"
    DEVICE_RECEIVED = "DEVICE_RECEIVED"
    INSPECTION_PASSED = "INSPECTION_PASSED"
    INSPECTION_FAILED = "INSPECTION_FAILED"
    PRICE_REVISED = "PRICE_REVISED"
    PAYOUT_READY = "PAYOUT_READY"
    PAID = "PAID"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


ORDER_STATUS_LABELS = {
    "RECEIVED": "Received",
    "PACK_SENT": "Pack Sent",
    "DEVICE_RECEIVED": "Device Received",
    "INSPECTION_PASSED": "Inspection Passed",
    "INSPECTION_FAILED": "Inspection Failed",
    "PRICE_REVISED": "Price Revised",
    "PAYOUT_READY": "Payout Ready",
    "PAID": "Paid",
    "CLOSED": "Closed",
    "CANCELLED": "Cancelled",
}

ORDER_STATUS_WORKFLOW = [
    "RECEIVED",
    "PACK_SENT",
    "DEVICE_RECEIVED",
    "INSPECTION_PASSED",
    "PAYOUT_READY",
    "PAID",
    "CLOSED",
]


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"


class PaymentMethod(str, Enum):
    BANK = "bank"


class PostageMethod(str, Enum):
    LABEL = "label"
    POSTBAG = "postbag"


class DeviceGrade(str, Enum):
    NEW = "NEW"
    GOOD = "GOOD"
    BROKEN = "BROKEN"


DEVICE_GRADE_LABELS = {
    "NEW": "New / Mint",
    "GOOD": "Good",
    "BROKEN": "Broken / Faulty",
}


class OrderSource(str, Enum):
    WEBSITE = "WEBSITE"
    API = "API"


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    VIEWER = "viewer"


class CounterOfferStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


OTP_CONFIG = {
    "LENGTH": 6,
    "MAX_ATTEMPTS": 5,
}

PAGINATION = {
    "DEFAULT_PAGE": 1,
    "DEFAULT_LIMIT": 20,
    "MAX_LIMIT": 100,
}

UPLOAD_LIMITS = {
    "IMAGE": {
        "MAX_SIZE_MB": 5,
        "ALLOWED_TYPES": ["image/jpeg", "image/jpg", "image/png", "image/webp"],
    },
    "CSV": {
        "MAX_SIZE_MB": 10,
        "ALLOWED_TYPES": ["text/csv", "application/vnd.ms-excel"],
    },
}

import re

VALIDATION_PATTERNS = {
    "EMAIL": re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$"),
    "PHONE_UK": re.compile(r"^(\+44|0)[1-9]\d{9}$"),
    "POSTCODE_UK": re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$", re.IGNORECASE),
    "SORT_CODE": re.compile(r"^\d{2}-\d{2}-\d{2}$"),
    "ACCOUNT_NUMBER": re.compile(r"^\d{8}$"),
    "ORDER_NUMBER": re.compile(r"^[A-Z0-9]{6}$"),
    "IP_ADDRESS": re.compile(r"^(\d{1,3}\.){3}\d{1,3}$"),
}

ERROR_MESSAGES = {
    "UNAUTHORIZED": "Authentication required",
    "FORBIDDEN": "Access forbidden",
    "NOT_FOUND": "Resource not found",
    "VALIDATION_ERROR": "Validation failed",
    "INTERNAL_ERROR": "Internal server error",
    "INVALID_OTP": "Invalid or expired OTP",
    "INVALID_CREDENTIALS": "Invalid credentials",
    "EMAIL_NOT_AUTHORIZED": "Email not authorized for admin access",
    "IP_NOT_WHITELISTED": "IP address not whitelisted",
    "RATE_LIMIT_EXCEEDED": "Too many requests, please try again later",
    "FILE_TOO_LARGE": "File size exceeds limit",
    "INVALID_FILE_TYPE": "Invalid file type",
    "ORDER_NOT_FOUND": "Order not found",
    "DEVICE_NOT_FOUND": "Device not found",
    "DUPLICATE_ENTRY": "Duplicate entry",
}
