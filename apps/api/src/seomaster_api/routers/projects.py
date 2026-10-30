"""/api/v1/projects — CRUD scoped to the caller's org."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from seomaster_api.deps import DB, CurrentOrg
from seomaster_api.errors import AppError
from seomaster_api.services import limits
from seomaster_core.domains import InvalidDomainError, normalize_domain
from seomaster_core.markets import Market
from seomaster_core.models import Envelope
from seomaster_db.models import Project

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=3, max_length=255)
    market: Market = Market.IN


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    market: Market | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    market: Market
    created_at: datetime


def _out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id, name=p.name, domain=p.domain, market=Market(p.market), created_at=p.created_at
    )


def _domain(raw: str) -> str:
    try:
        return normalize_domain(raw)
    except InvalidDomainError as exc:
        raise AppError(422, "invalid_domain", str(exc)) from exc


async def _get(db: DB, org_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.org_id == org_id)
    )
    if project is None:  # 404 (not 403) so other orgs' ids aren't confirmed
        raise AppError(404, "not_found", "Project not found")
    return project


@router.get("")
async def list_projects(db: DB, org: CurrentOrg) -> Envelope[list[ProjectOut]]:
    rows = await db.scalars(
        select(Project).where(Project.org_id == org.id).order_by(Project.created_at)
    )
    return Envelope(data=[_out(p) for p in rows])


@router.post("", status_code=201)
async def create_project(body: ProjectIn, db: DB, org: CurrentOrg) -> Envelope[ProjectOut]:
    await limits.check_count(db, org, "projects")
    project = Project(
        org_id=org.id, name=body.name, domain=_domain(body.domain), market=body.market.value
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "project_exists", "Project for this domain and market exists") from exc
    await db.refresh(project)
    return Envelope(data=_out(project))


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, db: DB, org: CurrentOrg) -> Envelope[ProjectOut]:
    return Envelope(data=_out(await _get(db, org.id, project_id)))


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID, body: ProjectPatch, db: DB, org: CurrentOrg
) -> Envelope[ProjectOut]:
    project = await _get(db, org.id, project_id)
    if body.name is not None:
        project.name = body.name
    if body.market is not None:
        project.market = body.market.value
    await db.commit()
    return Envelope(data=_out(project))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: DB, org: CurrentOrg) -> None:
    await db.delete(await _get(db, org.id, project_id))
    await db.commit()
