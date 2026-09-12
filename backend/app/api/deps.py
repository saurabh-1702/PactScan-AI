"""Auth dependencies (Phase 5) — used by every retrofitted endpoint from
Phases 1-4 to resolve the real tenant/role from a JWT instead of the
hardcoded DEMO_TENANT default those pipelines still accept.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: str
    tenant_id: str
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    return CurrentUser(
        user_id=payload["sub"], tenant_id=payload["tenant_id"], role=payload["role"]
    )


def require_role(allowed_roles: list[str]):
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role {user.role!r} is not permitted; requires one of {allowed_roles}.",
            )
        return user

    return _check
