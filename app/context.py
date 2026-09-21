from __future__ import annotations

from dataclasses import dataclass
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    user_id: str
    branch_id: str | None
    practitioner_id: str | None
    specialty_code: str | None


def get_context(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_branch_id: str | None = Header(default=None),
    x_practitioner_id: str | None = Header(default=None),
    x_specialty_code: str | None = Header(default=None),
) -> RequestContext:
    if not x_tenant_id or not x_user_id:
        raise HTTPException(401, "missing MIS context headers")
    return RequestContext(x_tenant_id, x_user_id, x_branch_id, x_practitioner_id, x_specialty_code)
