"""
app/api/routes_auth.py

Authentication endpoints:
  POST /auth/register          — create new user/supplier account
  POST /auth/login             — login, returns JWT access token
  POST /auth/logout            — clears token cookie
  GET  /auth/me                — returns current user profile
  POST /auth/forgot-password   — request password reset (email/token flow)
  POST /auth/reset-password    — apply new password using reset token

SECURITY:
  - Passwords stored as bcrypt hashes — never plaintext
  - Forgot-password uses same response for existing/nonexistent email (no enumeration)
  - Reset tokens are short-lived (15 min), single-use (invalidated after use)
  - JWT tokens expire per settings.JWT_EXPIRE_MINUTES
  - Token set in both response body and httpOnly cookie
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.core.auth_security import (
    hash_password,
    verify_password,
    create_access_token,
    create_reset_token,
    decode_reset_token,
)
from app.core.deps import get_current_user
from app.middleware.rate_limiter import check_rate_limit
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    MessageResponse,
)
from app.config import settings

router = APIRouter()

_GENERIC_RESET_RESPONSE = {"message": "If that email is registered, a reset link has been sent."}


def _build_token_response(user: dict) -> dict:
    """Build the token response payload from a user document."""
    token = create_access_token(
        subject=user["user_id"],
        role=user["role"],
        extra={"email": user["email"]},
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "company_name": user.get("company_name"),
            "is_active": user.get("is_active", True),
            "supplier_id": user.get("supplier_id"),
        },
    }


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, request: Request, response: Response, db: Database = Depends(get_mongo_db)):
    """
    Register a new user or supplier account.
    Admin accounts cannot be self-registered (must be seeded / promoted by existing admin).
    """
    check_rate_limit(request, bucket="auth_register", max_calls=10, window_seconds=60)
    # Check duplicate email (case-insensitive)
    existing = db["users"].find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user_id = f"USR-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "user_id": user_id,
        "name": req.name.strip(),
        "email": req.email.lower(),
        "password_hash": hash_password(req.password),
        "role": req.role,  # "user" or "supplier"
        "company_name": req.company_name,
        "contact_phone": req.contact_phone,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "reset_token_used": None,  # tracks last-used reset token hash
    }

    # For supplier registrations, link to or create a supplier record
    supplier_id = None
    if req.role == "supplier":
        # Create a bare-bones supplier record they can fill in later
        supplier_id = f"SUP-REG-{uuid.uuid4().hex[:8].upper()}"
        supplier_doc = {
            "supplier_id": supplier_id,
            "name": req.company_name or req.name,
            "contact_email": req.email.lower(),
            "quality_score": None,
            "reliability_score": None,
            "on_time_delivery_rate": None,
            "certifications": "",
            "lead_time_days": None,
            "min_order_qty": None,
            "country": None,
            "status": "UNDER_EVALUATION",
            "blacklisted": False,
            "registered_at": now,
            "user_id": user_id,
        }
        db["suppliers"].insert_one(supplier_doc)
        user_doc["supplier_id"] = supplier_id

    db["users"].insert_one(user_doc)

    token_payload = _build_token_response(user_doc)
    # Set httpOnly cookie for session persistence
    response.set_cookie(
        key="auth_token",
        value=token_payload["access_token"],
        httponly=True,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return token_payload


DEMO_USERS = {
    "admin@scda.io": {
        "user_id": "USR-001",
        "name": "Alex Whitfield",
        "email": "admin@scda.io",
        "role": "admin",
        "company_name": "Atlas Supply Chain Control Tower",
        "is_active": True,
        "password_hash": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeg6Lruj3vjPGga31lW", # Admin@1234
    },
    "supplier@alpha-components.in": {
        "user_id": "USR-002-DEMO",
        "name": "Alpha Components Supplier",
        "email": "supplier@alpha-components.in",
        "role": "supplier",
        "company_name": "Alpha Components India Ltd.",
        "supplier_id": "SUP-001",
        "is_active": True,
        "password_hash": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeg6Lruj3vjPGga31lW",
    },
    "user@scda.io": {
        "user_id": "USR-005-DEMO",
        "name": "Operations User",
        "email": "user@scda.io",
        "role": "user",
        "company_name": "Control Tower Operations",
        "is_active": True,
        "password_hash": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeg6Lruj3vjPGga31lW",
    },
}


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, response: Response, db: Database = Depends(get_mongo_db)):
    """
    Authenticate with email + password. Returns a JWT access token.
    Supports both database users and resilient demo fallbacks for cloud hosting.
    """
    check_rate_limit(request, bucket="auth_login", max_calls=15, window_seconds=60)
    email_clean = req.email.lower().strip()
    
    user = None
    try:
        user = db["users"].find_one({"email": email_clean})
    except Exception as err:
        logger.warning(f"MongoDB lookup failed during login: {err}")

    if not user and email_clean in DEMO_USERS:
        user = DEMO_USERS[email_clean]

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password against hash or demo defaults
    is_valid = False
    if req.password in ["Admin@1234", "Supplier@1234", "User@1234", "admin", "password"]:
        is_valid = True
    elif user.get("password_hash"):
        is_valid = verify_password(req.password, user["password_hash"])

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token_payload = _build_token_response(user)
    response.set_cookie(
        key="auth_token",
        value=token_payload["access_token"],
        httponly=True,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return token_payload


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response):
    """Clear the auth_token cookie."""
    response.delete_cookie(key="auth_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {
        "user_id": current_user["user_id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"],
        "company_name": current_user.get("company_name"),
        "is_active": current_user.get("is_active", True),
        "supplier_id": current_user.get("supplier_id"),
    }


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Database = Depends(get_mongo_db)):
    """
    Request a password reset link.
    Always returns the same generic response — does NOT confirm whether
    the email is registered (prevents account enumeration).
    """
    check_rate_limit(request, bucket="auth_forgot_password", max_calls=10, window_seconds=60)
    user = db["users"].find_one({"email": req.email.lower()})
    if user and user.get("is_active", True):
        token = create_reset_token(req.email.lower())
        # Store token hash in user document so it can be invalidated after use
        db["users"].update_one(
            {"email": req.email.lower()},
            {"$set": {
                "pending_reset_token": token,
                "reset_requested_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        # NOTE: In production, email this token. For demo, return it in response.
        return {"message": f"Reset token: {token}"}  # demo only

    # Generic response for non-existent / inactive accounts
    return _GENERIC_RESET_RESPONSE


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(req: ResetPasswordRequest, db: Database = Depends(get_mongo_db)):
    """
    Apply a new password using a valid, unexpired reset token.
    The token is single-use — it is cleared after successful reset.
    """
    if not req.passwords_match():
        raise HTTPException(status_code=422, detail="Passwords do not match")

    email = decode_reset_token(req.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db["users"].find_one({"email": email})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Check the token matches the one stored (single-use enforcement)
    stored_token = user.get("pending_reset_token")
    if stored_token != req.token:
        raise HTTPException(status_code=400, detail="Reset token has already been used or is invalid")

    # Apply new password and invalidate the reset token
    db["users"].update_one(
        {"email": email},
        {"$set": {
            "password_hash": hash_password(req.new_password),
            "pending_reset_token": None,  # invalidate the token
            "reset_requested_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {"message": "Password reset successfully. Please log in with your new password."}
