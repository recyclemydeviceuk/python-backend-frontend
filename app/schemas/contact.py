from pydantic import BaseModel, EmailStr
from typing import Optional


class CreateContactSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: str
