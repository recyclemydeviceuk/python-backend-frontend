import boto3
from app.config.settings import settings


def get_s3_client():
    """AWS S3 client using dedicated S3 credentials (fallback to general)."""
    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION,
        aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID or settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY or settings.AWS_SECRET_ACCESS_KEY,
    )


# S3 config
S3_BUCKET_NAME = settings.AWS_S3_BUCKET_NAME
S3_REGION = settings.AWS_S3_REGION
S3_FOLDERS = {
    "device_images": "devices/",
    "csv_imports": "csv/",
    "exports": "exports/",
}


# ── Brevo (transactional email) ───────────────────────────────────────────────
# Email delivery moved from AWS SES to Brevo. The constants below mirror the
# old SES_* names so the rest of the codebase keeps working with a one-line
# import change. The reply-to falls back to the support inbox so customer
# replies don't bounce.
BREVO_FROM_EMAIL = settings.FROM_EMAIL_Brevo
BREVO_FROM_NAME = settings.FROM_NAME_Brevo
BREVO_REPLY_TO = settings.SUPPORT_EMAIL or BREVO_FROM_EMAIL
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
