from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.job import JobStatus, JobType


class JobCreateBase(BaseModel):
    job_type: JobType


class JobCreatePlanilha(JobCreateBase):
    job_type: Literal[JobType.PLANILHA]
    processes: list[str] = Field(min_length=1)

    @field_validator("processes")
    @classmethod
    def validate_processes(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("At least one process number is required")
        return cleaned


class JobCreateServentia(JobCreateBase):
    job_type: Literal[JobType.SERVENTIA]
    serventia_id: str = Field(min_length=1)
    serventia_nome: str | None = None


class JobCreateNome(JobCreateBase):
    job_type: Literal[JobType.NOME]
    nome: str = Field(min_length=1)
    cpf: str | None = None


class JobCreateCombinada(JobCreateBase):
    job_type: Literal[JobType.COMBINADA]
    nome: str = Field(min_length=1)
    serventia_id: str = Field(min_length=1)
    cpf: str | None = None
    serventia_nome: str | None = None


JobCreate = Annotated[
    JobCreatePlanilha | JobCreateServentia | JobCreateNome | JobCreateCombinada,
    Field(discriminator="job_type"),
]


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_type: JobType
    status: JobStatus
    params: dict[str, Any]
    result_file_path: str | None
    total_items: int
    processed_items: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    page: int
    page_size: int


class ProcessRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    numero_processo: str | None
    nome_parte: str | None
    cpf_cnpj: str | None
    serventia: str | None
    advogados: list[dict[str, Any]] | None
    status_rpv: str | None
    movimentacoes: list[dict[str, Any]] | None
    raw_data: dict[str, Any] | None
    created_at: datetime


class ProcessRecordListResponse(BaseModel):
    items: list[ProcessRecordRead]
    total: int
    page: int
    page_size: int
