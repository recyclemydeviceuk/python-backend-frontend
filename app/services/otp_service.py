import random
import string
from datetime import datetime, timedelta, timezone
from app.models.otp import OTP
from app.models.admin import Admin
from app.config.settings import settings
from app.config.constants import OTP_CONFIG, ERROR_MESSAGES
from app.utils.logger import logger


def _generate_otp_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


async def create_and_send_otp(email: str) -> str:
    """Generate OTP, store in DB, return code for email sending."""
    # Invalidate any existing OTPs for this email
    await OTP.find(OTP.email == email, OTP.is_used == False).update({"$set": {"is_used": True}})

    code = _generate_otp_code(OTP_CONFIG["LENGTH"])
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    otp = OTP(email=email, code=code, expires_at=expires_at)
    await otp.insert()
    logger.info(f"OTP created for {email}")
    return code


async def verify_otp(email: str, code: str) -> bool:
    """Verify OTP code. Returns True if valid, raises on failure."""
    otp = await OTP.find_one(
        OTP.email == email,
        OTP.code == code,
        OTP.is_used == False,
    )

    if not otp:
        raise ValueError(ERROR_MESSAGES["INVALID_OTP"])

    now = datetime.now(timezone.utc)
    if otp.expires_at.replace(tzinfo=timezone.utc) < now:
        raise ValueError(ERROR_MESSAGES["INVALID_OTP"])

    if otp.attempts >= OTP_CONFIG["MAX_ATTEMPTS"]:
        raise ValueError("Maximum OTP attempts exceeded")

    # Mark as used
    otp.is_used = True
    otp.attempts += 1
    await otp.save()

    return True
