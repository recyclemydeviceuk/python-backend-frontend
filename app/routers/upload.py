from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.middleware.auth import get_current_admin
from app.services.s3_service import upload_file, delete_file
from app.utils.response import success_response
from app.config.constants import UPLOAD_LIMITS

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_IMAGE_TYPES = UPLOAD_LIMITS["IMAGE"]["ALLOWED_TYPES"]
MAX_IMAGE_SIZE = UPLOAD_LIMITS["IMAGE"]["MAX_SIZE_MB"] * 1024 * 1024


@router.post("/image", summary="Upload device image to S3", dependencies=[Depends(get_current_admin)])
async def upload_image(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

    url = await upload_file(content, file.filename, file.content_type, folder="device-images")
    if not url:
        raise HTTPException(status_code=500, detail="Failed to upload file")

    return success_response({"url": url}, "Image uploaded successfully")


@router.delete("/image", summary="Delete image from S3", dependencies=[Depends(get_current_admin)])
async def delete_image(url: str):
    deleted = await delete_file(url)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete file")
    return success_response({"message": "Image deleted successfully"})
