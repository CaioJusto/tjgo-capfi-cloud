from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import Workbook

from app.models.process_record import ProcessRecord


def export_process_records(records: Iterable[ProcessRecord], output_path: Path) -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Resultados"
    worksheet.append(
        [
            "numero_processo",
            "nome_parte",
            "cpf_cnpj",
            "serventia",
            "advogados",
            "status_rpv",
            "movimentacoes",
        ]
    )

    for record in records:
        worksheet.append(
            [
                record.numero_processo,
                record.nome_parte,
                record.cpf_cnpj,
                record.serventia,
                str(record.advogados or []),
                record.status_rpv,
                str(record.movimentacoes or []),
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
