"""Auth API (Phase 5).

POST /api/auth/register  -> create a user under an existing tenant
POST /api/auth/login     -> verify credentials, issue a JWT (user_id, tenant_id, role)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.api.deps import CurrentUser, get_current_user
from app.db.models import Tenant, User
from app.db.postgres_client import get_db
from app.models.auth import LoginRequest, RegisterRequest, TokenResponse
from app.models.contracts import MeOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=404, detail=f"tenant {body.tenant_id!r} not found")
    if db.query(User).filter(User.email == body.email).first() is not None:
        raise HTTPException(status_code=409, detail=f"email {body.email!r} is already registered")

    user = User(
        tenant_id=body.tenant_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.tenant_id, user.role)
    return TokenResponse(access_token=token, tenant_id=user.tenant_id, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(user.id, user.tenant_id, user.role)
    return TokenResponse(access_token=token, tenant_id=user.tenant_id, role=user.role)


@router.get("/me", response_model=MeOut)
def me(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> MeOut:
    user = db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    tenant = db.get(Tenant, user.tenant_id)
    return MeOut(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else user.tenant_id,
    )
