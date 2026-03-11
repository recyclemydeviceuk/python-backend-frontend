import boto3
from app.config.settings import settings


def get_ses_client():
    """AWS SES client using general AWS credentials."""
    return boto3.client(
        "ses",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


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

# SES config
SES_FROM_EMAIL = settings.AWS_SES_FROM_EMAIL
SES_FROM_NAME = settings.AWS_SES_FROM_NAME
SES_FROM = f"{SES_FROM_NAME} <{SES_FROM_EMAIL}>"
SES_REPLY_TO = settings.AWS_SES_VERIFIED_EMAIL or "Support@cashmymobile.co.uk"
