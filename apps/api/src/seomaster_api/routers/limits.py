"""/api/v1/limits — plan limits and current usage (Semrush: /projects/api/limits)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from seomaster_api.deps import DB, CurrentOrg
from seomaster_api.services import limits
from seomaster_core.models import Envelope

router = APIRouter(prefix="/api/v1/limits", tags=["limits"])


class LimitOut(BaseModel):
    name: str
    used: int
    max: int
    period: Literal["day", "month", "total"]


class LimitsOut(BaseModel):
    plan_id: str
    limits: list[LimitOut]


@router.get("/me")
async def my_limits(db: DB, org: CurrentOrg) -> Envelope[LimitsOut]:
    rows = await limits.snapshot(db, org)
    return Envelope(
        data=LimitsOut(plan_id=org.plan_id, limits=[LimitOut.model_validate(r) for r in rows])
    )
