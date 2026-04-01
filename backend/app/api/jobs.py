from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job import Job, JobStatus
from app.models.process_record import ProcessRecord
from app.models.user import User
from app.schemas.job import (
    JobCreate,
    JobListResponse,
    JobRead,
    ProcessRecordListResponse,
    ProcessRecordRead,
)
from app.services.jobs import enqueue_job


router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _get_owned_job(job_id: int, user_id: int, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    params = payload.model_dump(mode="json")
    total_items = len(params.get("processes", [])) if payload.job_type == "planilha" else 0
    job = Job(
        user_id=current_user.id,
        job_type=payload.job_type,
        status=JobStatus.PENDING,
        params=params,
        total_items=total_items,
        processed_items=0,
        logs=["🆕 Job criado e aguardando execução."],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    enqueue_job(background_tasks, job.id)
    return JobRead.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobListResponse:
    total = await db.scalar(select(func.count(Job.id)).where(Job.user_id == current_user.id))
    result = await db.execute(
        select(Job)
        .where(Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    jobs = result.scalars().all()
    return JobListResponse(
        items=[JobRead.model_validate(item) for item in jobs],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    job = await _get_owned_job(job_id, current_user.id, db)
    return JobRead.model_validate(job)


@router.post("/{job_id}/pause", response_model=JobRead)
async def pause_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    job = await _get_owned_job(job_id, current_user.id, db)
    if job.status != JobStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only running jobs can be paused")
    job.status = JobStatus.PAUSED
    job.logs = [*(job.logs or []), "⏸️ Job pausado pelo usuário."]
    await db.commit()
    await db.refresh(job)
    return JobRead.model_validate(job)


@router.post("/{job_id}/resume", response_model=JobRead)
async def resume_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    job = await _get_owned_job(job_id, current_user.id, db)
    if job.status != JobStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only paused jobs can be resumed")
    job.status = JobStatus.RUNNING
    job.logs = [*(job.logs or []), "▶️ Job retomado pelo usuário."]
    await db.commit()
    await db.refresh(job)
    enqueue_job(background_tasks, job.id)
    return JobRead.model_validate(job)


@router.delete("/{job_id}", response_model=JobRead)
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    job = await _get_owned_job(job_id, current_user.id, db)
    if job.status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job can no longer be canceled")
    job.status = JobStatus.CANCELED
    job.logs = [*(job.logs or []), "🛑 Job cancelado pelo usuário."]
    await db.commit()
    await db.refresh(job)
    return JobRead.model_validate(job)


@router.get("/{job_id}/results", response_model=ProcessRecordListResponse)
async def list_job_results(
    job_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessRecordListResponse:
    await _get_owned_job(job_id, current_user.id, db)
    total = await db.scalar(select(func.count(ProcessRecord.id)).where(ProcessRecord.job_id == job_id))
    result = await db.execute(
        select(ProcessRecord)
        .where(ProcessRecord.job_id == job_id)
        .order_by(ProcessRecord.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = result.scalars().all()
    return ProcessRecordListResponse(
        items=[ProcessRecordRead.model_validate(item) for item in records],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}/download")
async def download_job_results(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    job = await _get_owned_job(job_id, current_user.id, db)
    if job.status != JobStatus.DONE or not job.result_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result file not available")

    file_path = Path(job.result_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result file missing on disk")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
