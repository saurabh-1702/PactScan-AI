"""Pydantic schemas for auth (Phase 5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    tenant_id: str
    role: Literal["end_user", "reviewer", "admin"] = "end_user"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    role: str
