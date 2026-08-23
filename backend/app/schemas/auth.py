"""
app/schemas/auth.py

Pydantic schemas for authentication endpoints.
These are the request and response models used by /auth/*.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
import re


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(user|supplier)$")  # admin registration blocked
    # Supplier-specific optional fields
    company_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone: Optional[str] = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    def passwords_match(self) -> bool:
        return self.new_password == self.confirm_password


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: "UserOut"


class UserOut(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    company_name: Optional[str] = None
    is_active: bool = True
    supplier_id: Optional[str] = None  # links supplier users to supplier records


TokenResponse.model_rebuild()


class MessageResponse(BaseModel):
    message: str
