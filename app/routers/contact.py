from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.models.contact_submission import ContactSubmission
from app.schemas.contact import CreateContactSchema
from app.middleware.auth import get_current_admin
from app.services.email_service import send_contact_confirmation
from app.utils.response import success_response, created_response
from app.utils.logger import logger
from datetime import datetime


class UpdateContactStatusSchema(BaseModel):
    status: str

router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("", summary="Submit contact form (public)")
async def submit_contact(body: CreateContactSchema):
    submission = ContactSubmission(**body.dict())
    await submission.insert()
    logger.info(f"Contact submission from {body.email}")
    await send_contact_confirmation(submission)
    return created_response({"message": "Message sent successfully"}, "Your message has been received")


@router.get("", summary="Get all contact submissions", dependencies=[Depends(get_current_admin)])
async def get_all_contacts(is_read: bool = None):
    filters = []
    if is_read is not None:
        filters.append(ContactSubmission.is_read == is_read)
    submissions = await ContactSubmission.find(*filters).sort(-ContactSubmission.created_at).to_list()
    return success_response({"submissions": [_serialize(s) for s in submissions]})


@router.get("/{submission_id}", summary="Get single submission", dependencies=[Depends(get_current_admin)])
async def get_contact(submission_id: str):
    s = await ContactSubmission.get(submission_id)
    if not s:
        raise HTTPException(status_code=404, detail="Submission not found")
    return success_response({"submission": _serialize(s)})


@router.patch("/{submission_id}/status", summary="Update submission status", dependencies=[Depends(get_current_admin)])
async def update_status(submission_id: str, body: UpdateContactStatusSchema):
    valid = ["new", "in_progress", "resolved", "closed"]
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")
    s = await ContactSubmission.get(submission_id)
    if not s:
        raise HTTPException(status_code=404, detail="Submission not found")
    s.status = body.status
    if body.status in ("resolved", "closed"):
        s.is_read = True
    await s.save()
    return success_response({"submission": _serialize(s)}, "Status updated")


@router.patch("/{submission_id}/read", summary="Mark as read", dependencies=[Depends(get_current_admin)])
async def mark_read(submission_id: str):
    s = await ContactSubmission.get(submission_id)
    if not s:
        raise HTTPException(status_code=404, detail="Submission not found")
    s.is_read = True
    await s.save()
    return success_response({"submission": _serialize(s)}, "Marked as read")


@router.delete("/{submission_id}", summary="Delete submission", dependencies=[Depends(get_current_admin)])
async def delete_contact(submission_id: str):
    s = await ContactSubmission.get(submission_id)
    if not s:
        raise HTTPException(status_code=404, detail="Submission not found")
    await s.delete()
    return success_response({"message": "Submission deleted"})


def _serialize(s: ContactSubmission) -> dict:
    return {
        "id": str(s.id), "_id": str(s.id),
        "name": s.name, "email": s.email,
        "phone": s.phone, "subject": s.subject, "message": s.message,
        "is_read": s.is_read, "isRead": s.is_read,
        "status": getattr(s, "status", "new"),
        "created_at": s.created_at.isoformat(), "createdAt": s.created_at.isoformat(),
    }
