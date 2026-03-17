from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.schemas.auth import RequestOTPSchema, VerifyOTPSchema, TokenResponse
from app.models.admin import Admin
from app.services.otp_service import create_and_send_otp, verify_otp
from app.services.email_service import send_otp_email
from app.config.settings import settings
from app.config.constants import ERROR_MESSAGES
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["Auth"])

# Hardcoded admin emails
ALLOWED_ADMIN_EMAILS = ["sellyourfone@gmail.com", "thekhushnoor@gmail.com"]


@router.post("/request-otp", summary="Request OTP for admin login")
async def request_otp(body: RequestOTPSchema):
    email = body.email.lower()

    # Check if email is in allowed list
    if email not in ALLOWED_ADMIN_EMAILS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES["EMAIL_NOT_AUTHORIZED"])

    otp_code = await create_and_send_otp(email)
    sent = await send_otp_email(email, otp_code)

    if not sent:
        logger.warning(f"OTP email failed for {email}, code: {otp_code}")

    return {"success": True, "message": "OTP sent to your email address"}


@router.post("/verify-otp", response_model=TokenResponse, summary="Verify OTP and get JWT token")
async def verify_otp_endpoint(body: VerifyOTPSchema):
    email = body.email.lower()

    # Check if email is allowed
    if email not in ALLOWED_ADMIN_EMAILS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not authorized")

    try:
        await verify_otp(email, body.otp)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # Try to find admin in database, create if doesn't exist
    admin = await Admin.find_one(Admin.email == email)
    if not admin:
        username = email.split("@")[0]
        from app.config.constants import AdminRole
        admin = Admin(email=email, username=username, role=AdminRole.ADMIN, is_active=True)
        await admin.insert()
        logger.info(f"Created admin on-the-fly: {email}")

    # Update last login
    admin.last_login = datetime.now(timezone.utc)
    await admin.save()

    # Issue JWT
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    payload = {"id": str(admin.id), "email": admin.email, "exp": expire}
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": {"id": str(admin.id), "email": admin.email, "name": getattr(admin, "name", None) or admin.username, "role": admin.role},
    }


@router.get("/me", summary="Get current admin profile")
async def get_me(admin: Admin = None):
    from app.middleware.auth import get_current_admin
    from fastapi import Depends
    return {"success": True, "data": {"admin": {"id": str(admin.id), "email": admin.email, "name": getattr(admin, "name", None) or admin.username, "role": admin.role}}}
