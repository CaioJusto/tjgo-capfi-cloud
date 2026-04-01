from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.projudi_credentials import ProjudiCredentials
from app.models.user import User

router = APIRouter(prefix="/credentials", tags=["credentials"])


class CredentialsIn(BaseModel):
    projudi_username: str
    projudi_password: str


class CredentialsOut(BaseModel):
    projudi_username: str
    has_password: bool


@router.get("", response_model=CredentialsOut)
async def get_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialsOut:
    result = await db.execute(
        select(ProjudiCredentials).where(ProjudiCredentials.user_id == current_user.id)
    )
    creds = result.scalar_one_or_none()
    if not creds:
        return CredentialsOut(projudi_username="", has_password=False)
    return CredentialsOut(projudi_username=creds.projudi_username, has_password=True)


@router.post("", response_model=CredentialsOut, status_code=status.HTTP_200_OK)
async def save_credentials(
    payload: CredentialsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialsOut:
    result = await db.execute(
        select(ProjudiCredentials).where(ProjudiCredentials.user_id == current_user.id)
    )
    creds = result.scalar_one_or_none()

    if creds:
        creds.projudi_username = payload.projudi_username
        creds.projudi_password = payload.projudi_password
    else:
        creds = ProjudiCredentials(
            user_id=current_user.id,
            projudi_username=payload.projudi_username,
            projudi_password=payload.projudi_password,
        )
        db.add(creds)

    await db.commit()
    return CredentialsOut(projudi_username=creds.projudi_username, has_password=True)
