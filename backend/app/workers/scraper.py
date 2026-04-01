from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.process_record import ProcessRecord
from app.services.excel import export_process_records

LOGGER = logging.getLogger(__name__)
PROCESS_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def run_scraper_job_sync(job_id: int) -> None:
    asyncio.run(run_scraper_job(job_id))


async def run_scraper_job(job_id: int) -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            LOGGER.error("Job %s not found", job_id)
            return
        if job.status == JobStatus.CANCELED:
            return
        if job.status == JobStatus.PAUSED:
            return

        job.status = JobStatus.RUNNING
        job.error_message = None
        job.result_file_path = None
        job.logs = [*(job.logs or []), f"🚀 Iniciando job #{job_id} ({job.job_type.value})"]
        if job.processed_items == 0:
            if job.job_type != JobType.PLANILHA:
                job.total_items = 0
            await session.execute(delete(ProcessRecord).where(ProcessRecord.job_id == job_id))
        await session.commit()

    try:
        await asyncio.to_thread(_execute_scraping, job_id)
        await _persist_job_success(job_id, settings.result_dir)
    except Exception as exc:
        LOGGER.exception("Job %s failed", job_id)
        await _persist_job_failure(job_id, str(exc))


def _execute_scraping(job_id: int) -> None:
    from seleniumbase import SB

    asyncio.run(_append_job_log(job_id, "🔐 Abrindo PROJUDI e autenticando..."))
    with SB(browser="chrome", headless=True, test=False, locale_code="pt") as sb:
        _open_and_login(sb)
        asyncio.run(_append_job_log(job_id, "✅ Login no PROJUDI concluído."))
        job_params, job_type = asyncio.run(_get_job_snapshot(job_id))

        if job_type == JobType.PLANILHA.value:
            processos = job_params["processes"]
            asyncio.run(_append_job_log(job_id, f"📚 Busca por planilha iniciada com {len(processos)} processo(s)."))
            for idx, process_number in enumerate(processos, start=1):
                if not asyncio.run(_wait_if_paused_or_canceled(job_id)):
                    return
                asyncio.run(_append_job_log(job_id, f"🔎 Consultando processo {idx}/{len(processos)}: {process_number}"))
                batch = _search_process(sb, process_number=process_number)
                asyncio.run(_append_scraped_batch(job_id, batch))
        elif job_type == JobType.SERVENTIA.value:
            if not asyncio.run(_wait_if_paused_or_canceled(job_id)):
                return
            asyncio.run(_append_job_log(job_id, f"🏛️ Busca por serventia iniciada: {job_params.get('serventia_nome') or job_params.get('serventia_id')} (página {job_params.get('pagina_inicial', 1)})"))
            batch = _search_process(
                sb,
                serventia_id=job_params["serventia_id"],
                serventia_nome=job_params.get("serventia_nome"),
            )
            asyncio.run(_append_scraped_batch(job_id, batch))
        elif job_type == JobType.NOME.value:
            if not asyncio.run(_wait_if_paused_or_canceled(job_id)):
                return
            asyncio.run(_append_job_log(job_id, f"👤 Busca por nome iniciada: {job_params['nome']} (página {job_params.get('pagina_inicial', 1)})"))
            batch = _search_process(sb, nome=job_params["nome"], cpf=job_params.get("cpf"))
            asyncio.run(_append_scraped_batch(job_id, batch))
        elif job_type == JobType.COMBINADA.value:
            if not asyncio.run(_wait_if_paused_or_canceled(job_id)):
                return
            asyncio.run(_append_job_log(job_id, f"🧩 Busca combinada iniciada: nome={job_params['nome']} | serventia={job_params.get('serventia_nome') or job_params.get('serventia_id') or 'todas'} | página {job_params.get('pagina_inicial', 1)}"))
            batch = _search_process(
                sb,
                nome=job_params["nome"],
                cpf=job_params.get("cpf"),
                serventia_id=job_params.get("serventia_id"),
                serventia_nome=job_params.get("serventia_nome"),
            )
            asyncio.run(_append_scraped_batch(job_id, batch))
        else:
            raise ValueError(f"Unsupported job type: {job_type}")


async def _get_job_snapshot(job_id: int) -> tuple[dict[str, Any], str]:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        return job.params, job.job_type.value


async def _append_job_log(job_id: int, message: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.logs = [*(job.logs or []), message][-200:]
        await session.commit()


async def _wait_if_paused_or_canceled(job_id: int) -> bool:
    while True:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return False
            if job.status == JobStatus.CANCELED:
                return False
            if job.status != JobStatus.PAUSED:
                return True
        await asyncio.sleep(2)


async def _append_scraped_batch(job_id: int, scraped_items: list[dict[str, Any]]) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
            return

        for item in scraped_items:
            session.add(ProcessRecord(job_id=job_id, **item))

        if scraped_items:
            job.processed_items += len(scraped_items)
            if job.total_items < job.processed_items:
                job.total_items = job.processed_items
            job.logs = [*(job.logs or []), f"📄 {len(scraped_items)} resultado(s) adicionados. Total processado: {job.processed_items}"][-200:]

        await session.commit()


def _open_and_login(sb: Any) -> None:
    settings = get_settings()
    sb.open(settings.projudi_base_url)

    if _is_selector_present(sb, 'iframe[name="userMainFrame"]'):
        sb.switch_to_frame('iframe[name="userMainFrame"]')

    if _is_selector_present(sb, settings.projudi_login_selector):
        sb.type(settings.projudi_login_selector, settings.projudi_user)
        sb.type(settings.projudi_password_selector, settings.projudi_password)
        sb.click(settings.projudi_submit_selector)
        sb.sleep(2)

    if _is_selector_present(sb, 'iframe[name="userMainFrame"]'):
        sb.switch_to_default_content()
        sb.switch_to_frame('iframe[name="userMainFrame"]')


def _search_process(
    sb: Any,
    process_number: str | None = None,
    nome: str | None = None,
    cpf: str | None = None,
    serventia_id: str | None = None,
    serventia_nome: str | None = None,
    pagina_inicial: int = 1,
) -> list[dict[str, Any]]:
    sb.wait_for_ready_state_complete()

    if _is_selector_present(sb, "#NomeParte"):
        sb.clear("#NomeParte")
        if nome:
            sb.type("#NomeParte", nome)

    if _is_selector_present(sb, "#CpfCnpjParte"):
        sb.clear("#CpfCnpjParte")
        if cpf:
            sb.type("#CpfCnpjParte", cpf)

    if serventia_id and _is_selector_present(sb, "#Id_Serventia"):
        sb.execute_script(
            "document.querySelector('#Id_Serventia').value = arguments[0];",
            serventia_id,
        )
    if serventia_nome and _is_selector_present(sb, "#Serventia"):
        sb.clear("#Serventia")
        sb.type("#Serventia", serventia_nome)

    if process_number:
        _fill_process_number_if_available(sb, process_number)

    sb.click("#btnBuscar")
    sb.sleep(2)

    # Busca por número de processo é pontual; demais modos podem ter múltiplas páginas
    if process_number:
        return _extract_results_from_page(sb, process_number, nome, cpf, serventia_nome)

    return _extract_paginated_results(sb, nome, cpf, serventia_nome, pagina_inicial)


def _fill_process_number_if_available(sb: Any, process_number: str) -> None:
    candidate_selectors = [
        "#NumeroProcesso",
        "#nrProcesso",
        'input[name="NumeroProcesso"]',
        'input[name="nrProcesso"]',
    ]
    for selector in candidate_selectors:
        if _is_selector_present(sb, selector):
            sb.clear(selector)
            sb.type(selector, process_number)
            return


def _extract_paginated_results(
    sb: Any,
    nome: str | None,
    cpf: str | None,
    serventia_nome: str | None,
    pagina_inicial: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    try:
        total_text = sb.execute_script("""
            return (function(){
                var match = document.body.textContent.match(/Total de:\\s*([\\d.]+)/);
                return match ? match[1] : '0';
            })()
        """)
        total_processos = int(str(total_text).replace('.', '') or '0')
    except Exception:
        total_processos = 0

    processos_por_pagina = 15
    total_paginas = max(1, (total_processos + processos_por_pagina - 1) // processos_por_pagina) if total_processos else 1

    if pagina_inicial > 1:
        try:
            sb.execute_script(f"""
                var input = document.querySelector('input[name="PosicaoPaginaAtual"]');
                if(input) input.value = '{pagina_inicial - 1}';
                var btns = document.querySelectorAll('.Paginacao input[value="Ir"]');
                if(btns.length > 0) btns[0].click();
            """)
            sb.sleep(2)
        except Exception:
            pass

    pagina_atual = max(1, pagina_inicial)
    while pagina_atual <= total_paginas:
        page_records = _extract_results_from_page(sb, None, nome, cpf, serventia_nome)
        if page_records:
            results.extend(page_records)

        if pagina_atual >= total_paginas:
            break

        try:
            sb.execute_script(f"""
                var input = document.querySelector('input[name="PosicaoPaginaAtual"]');
                if(input) input.value = '{pagina_atual}';
                var btns = document.querySelectorAll('.Paginacao input[value="Ir"]');
                if(btns.length > 0) btns[0].click();
            """)
            sb.sleep(2)
        except Exception:
            break

        pagina_atual += 1

    return results


def _extract_results_from_page(
    sb: Any,
    process_number: str | None,
    nome: str | None,
    cpf: str | None,
    serventia_nome: str | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_source = sb.get_page_source()

    table_rows = sb.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    for row in table_rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        texts = [cell.text.strip() for cell in cells if cell.text.strip()]
        if not texts:
            continue
        numero = next((item for item in texts if PROCESS_PATTERN.search(item)), process_number)
        records.append(
            {
                "numero_processo": numero,
                "nome_parte": nome or (texts[1] if len(texts) > 1 else None),
                "cpf_cnpj": cpf,
                "serventia": serventia_nome or (texts[2] if len(texts) > 2 else None),
                "advogados": [],
                "status_rpv": texts[3] if len(texts) > 3 else None,
                "movimentacoes": [],
                "raw_data": {"row": texts},
            }
        )

    if records:
        return records

    matched_processes = PROCESS_PATTERN.findall(page_source)
    if matched_processes:
        deduplicated = list(dict.fromkeys(matched_processes))
        return [
            {
                "numero_processo": number,
                "nome_parte": nome,
                "cpf_cnpj": cpf,
                "serventia": serventia_nome,
                "advogados": [],
                "status_rpv": None,
                "movimentacoes": [],
                "raw_data": {
                    "source": "page_source",
                    "snippet": page_source[:5000],
                },
            }
            for number in deduplicated
        ]

    return [
        {
            "numero_processo": process_number,
            "nome_parte": nome,
            "cpf_cnpj": cpf,
            "serventia": serventia_nome,
            "advogados": [],
            "status_rpv": None,
            "movimentacoes": [],
            "raw_data": {
                "source": "empty_result",
                "page_title": sb.get_title(),
                "snippet": page_source[:5000],
            },
        }
    ]


def _is_selector_present(sb: Any, selector: str) -> bool:
    try:
        return sb.is_element_present(selector)
    except (NoSuchElementException, TimeoutException):
        return False


async def _persist_job_success(job_id: int, result_dir: Path) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
            return

        result = await session.execute(
            select(ProcessRecord).where(ProcessRecord.job_id == job_id).order_by(ProcessRecord.id)
        )
        records = result.scalars().all()
        job.total_items = len(records)
        job.processed_items = len(records)
        file_path = export_process_records(records, result_dir / f"{job_id}.xlsx")
        job.result_file_path = str(file_path)
        job.status = JobStatus.DONE
        job.logs = [*(job.logs or []), f"✅ Job concluído. Planilha gerada com {len(records)} registro(s)."][-200:]
        await session.commit()


async def _persist_job_failure(job_id: int, error_message: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELED:
            return
        job.status = JobStatus.FAILED
        job.error_message = error_message[:2000]
        job.logs = [*(job.logs or []), f"❌ Falha no job: {error_message[:300]}"][-200:]
        await session.commit()
