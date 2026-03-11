from botocore.exceptions import ClientError
from typing import Optional
import uuid
import os
from app.config.aws import get_s3_client, S3_BUCKET_NAME, S3_REGION, S3_FOLDERS
from app.utils.logger import logger


async def upload_file(file_bytes: bytes, filename: str, content_type: str, folder: str = "devices/") -> Optional[str]:
    """Upload file to S3 and return public URL."""
    try:
        ext = os.path.splitext(filename)[1]
        # Normalise folder — strip trailing slash for key building
        folder = folder.rstrip("/")
        key = f"{folder}/{uuid.uuid4().hex}{ext}"
        client = get_s3_client()
        client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        url = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{key}"
        logger.info(f"File uploaded to S3: {url}")
        return url
    except ClientError as e:
        logger.error(f"S3 upload error: {e}")
        return None


async def upload_device_image(file_bytes: bytes, filename: str, content_type: str) -> Optional[str]:
    """Upload a device image to the dedicated S3 folder."""
    return await upload_file(file_bytes, filename, content_type, folder=S3_FOLDERS["device_images"])


async def delete_file(url: str) -> bool:
    """Delete a file from S3 by its public URL."""
    try:
        key = url.split(".amazonaws.com/")[-1]
        client = get_s3_client()
        client.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
        logger.info(f"File deleted from S3: {key}")
        return True
    except ClientError as e:
        logger.error(f"S3 delete error: {e}")
        return False
