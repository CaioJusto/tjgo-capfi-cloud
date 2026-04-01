from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProcessRecord(Base):
    __tablename__ = "process_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    numero_processo: Mapped[str | None] = mapped_column(String(50), index=True)
    nome_parte: Mapped[str | None] = mapped_column(String(255), index=True)
    cpf_cnpj: Mapped[str | None] = mapped_column(String(30), index=True)
    serventia: Mapped[str | None] = mapped_column(String(255))
    advogados: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    status_rpv: Mapped[str | None] = mapped_column(String(255))
    movimentacoes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    job = relationship("Job", back_populates="records")
