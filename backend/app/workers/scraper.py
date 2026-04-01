from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.process_record import ProcessRecord
from app.services.excel import export_process_records

LOGGER = logging.getLogger(__name__)
PROCESS_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
PROCESSOS_POR_PAGINA = 15
SELECTOR_LISTA_PROCESSOS = "table tr[onclick]"
SELECTOR_DETALHE_PROCESSO = "#span_proc_numero, .destaque-proc-numero, fieldset.VisualizaDados"
SELECTOR_TABELA_ADVOGADOS = "#tabListaAdvogadoParte tr"


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

    _log_sync(job_id, "🔐 Abrindo PROJUDI e autenticando...")
    with SB(browser="chrome", headless=True, test=False, locale_code="pt") as sb:
        _open_and_login(sb)
        _log_sync(job_id, "✅ Login no PROJUDI concluído.")
        job_params, job_type = _run_async(_get_job_snapshot(job_id))

        if job_type == JobType.PLANILHA.value:
            processos = job_params["processes"]
            _log_sync(job_id, f"📚 Busca por planilha iniciada com {len(processos)} processo(s).")
            for idx, process_number in enumerate(processos, start=1):
                if not _job_should_continue(job_id):
                    _log_sync(job_id, "🛑 Execução interrompida durante busca por planilha.")
                    return
                _log_sync(job_id, f"🔎 Consultando processo {idx}/{len(processos)}: {process_number}")
                batch = _search_process_by_number(sb, process_number=process_number, job_id=job_id)
                _run_async(_append_scraped_batch(job_id, batch))
            return

        pagina_inicial = int(job_params.get("pagina_inicial", 1) or 1)
        if job_type == JobType.SERVENTIA.value:
            _executar_serventia(sb, job_id, job_params, pagina_inicial)
        elif job_type == JobType.NOME.value:
            _executar_nome(sb, job_id, job_params, pagina_inicial)
        elif job_type == JobType.COMBINADA.value:
            _executar_combined(sb, job_id, job_params, pagina_inicial)
        else:
            raise ValueError(f"Unsupported job type: {job_type}")


def _executar_serventia(sb: Any, job_id: int, job_params: dict[str, Any], pagina_inicial: int) -> None:
    descricao = job_params.get("serventia_nome") or job_params.get("serventia_id")
    _log_sync(job_id, f"🏛️ Busca por serventia iniciada: {descricao} (página {pagina_inicial})")
    _prepare_search_form(
        sb,
        nome=None,
        cpf=None,
        serventia_id=job_params["serventia_id"],
        serventia_nome=job_params.get("serventia_nome"),
    )
    _executar_busca_paginada(
        sb,
        job_id=job_id,
        pagina_inicial=pagina_inicial,
        contexto_busca="serventia",
        nome_referencia=None,
        cpf_referencia=None,
        serventia_referencia=job_params.get("serventia_nome") or job_params["serventia_id"],
    )


def _executar_nome(sb: Any, job_id: int, job_params: dict[str, Any], pagina_inicial: int) -> None:
    _log_sync(job_id, f"👤 Busca por nome iniciada: {job_params['nome']} (página {pagina_inicial})")
    _prepare_search_form(
        sb,
        nome=job_params["nome"],
        cpf=job_params.get("cpf"),
        serventia_id=None,
        serventia_nome=None,
    )
    _executar_busca_paginada(
        sb,
        job_id=job_id,
        pagina_inicial=pagina_inicial,
        contexto_busca="nome",
        nome_referencia=job_params["nome"],
        cpf_referencia=job_params.get("cpf"),
        serventia_referencia=None,
    )


def _executar_combined(sb: Any, job_id: int, job_params: dict[str, Any], pagina_inicial: int) -> None:
    _log_sync(
        job_id,
        (
            "🧩 Busca combinada iniciada: "
            f"nome={job_params['nome']} | "
            f"serventia={job_params.get('serventia_nome') or job_params.get('serventia_id') or 'todas'} | "
            f"página {pagina_inicial}"
        ),
    )
    _prepare_search_form(
        sb,
        nome=job_params["nome"],
        cpf=job_params.get("cpf"),
        serventia_id=job_params.get("serventia_id"),
        serventia_nome=job_params.get("serventia_nome"),
    )
    _executar_busca_paginada(
        sb,
        job_id=job_id,
        pagina_inicial=pagina_inicial,
        contexto_busca="combinada",
        nome_referencia=job_params["nome"],
        cpf_referencia=job_params.get("cpf"),
        serventia_referencia=job_params.get("serventia_nome") or job_params.get("serventia_id"),
    )


def _prepare_search_form(
    sb: Any,
    nome: str | None,
    cpf: str | None,
    serventia_id: str | None,
    serventia_nome: str | None,
) -> None:
    sb.wait_for_ready_state_complete()

    if _is_selector_present(sb, "#NomeParte"):
        sb.clear("#NomeParte")
        if nome:
            sb.type("#NomeParte", nome)

    if _is_selector_present(sb, "#CpfCnpjParte"):
        sb.clear("#CpfCnpjParte")
        if cpf:
            sb.type("#CpfCnpjParte", cpf)

    if _is_selector_present(sb, "#Serventia"):
        sb.clear("#Serventia")
        if serventia_nome:
            sb.type("#Serventia", serventia_nome)

    if serventia_id and _is_selector_present(sb, "#Id_Serventia"):
        sb.execute_script(
            "document.querySelector('#Id_Serventia').value = arguments[0];",
            serventia_id,
        )

    sb.execute_script(
        """
        var limpar = document.querySelector("[name='imaLimparProcessoStatus']");
        if (limpar) limpar.click();
        var paginaAtual = document.getElementById('PaginaAtual');
        if (paginaAtual) paginaAtual.value = '2';
        """
    )

    sb.execute_script(
        """
        var btn = document.getElementById('btnBuscar');
        if (btn) {
            btn.disabled = false;
            btn.click();
        }
        """
    )
    _esperar_contagem_elementos(sb, SELECTOR_LISTA_PROCESSOS, timeout=6)


def _executar_busca_paginada(
    sb: Any,
    job_id: int,
    pagina_inicial: int,
    contexto_busca: str,
    nome_referencia: str | None,
    cpf_referencia: str | None,
    serventia_referencia: str | None,
) -> None:
    pagina_inicial = max(1, pagina_inicial)
    debug_info = _obter_debug_paginacao(sb)
    total_processos = debug_info["total_processos"]
    total_paginas = max(1, (total_processos + PROCESSOS_POR_PAGINA - 1) // PROCESSOS_POR_PAGINA) if total_processos else 1

    _run_async(_set_job_total_items(job_id, total_processos))
    _log_sync(
        job_id,
        (
            f"📊 Total identificado: {total_processos} processo(s) em {total_paginas} página(s). "
            f"paginação_input={debug_info['has_pagination_input']} | botao_ir={debug_info['has_pagination_ir']} | "
            f"title='{debug_info['title']}'"
        ),
    )
    if not debug_info["has_pagination_input"] or not debug_info["has_pagination_ir"]:
        _log_sync(
            job_id,
            (
                "⚠️ Paginação não localizada de forma completa; tentando continuar com a listagem atual. "
                f"Snippet='{debug_info['body_snippet'][:220]}'"
            ),
        )

    if total_processos == 0:
        _log_sync(
            job_id,
            f"ℹ️ Busca {contexto_busca} não retornou processos. Snippet='{debug_info['body_snippet'][:220]}'",
        )
        return

    if pagina_inicial > total_paginas:
        raise RuntimeError(
            f"Página inicial {pagina_inicial} é maior que o total de páginas {total_paginas} para a busca {contexto_busca}."
        )

    if pagina_inicial > 1:
        _log_sync(job_id, f"⏩ Pulando para a página inicial {pagina_inicial}.")
        if not _navegar_por_paginacao(sb, pagina_inicial - 1):
            raise RuntimeError(f"Não foi possível navegar para a página inicial {pagina_inicial}.")
        _esperar_contagem_elementos(sb, SELECTOR_LISTA_PROCESSOS, timeout=6)

    pagina_atual = pagina_inicial
    processo_global = (pagina_inicial - 1) * PROCESSOS_POR_PAGINA

    while pagina_atual <= total_paginas:
        if not _job_should_continue(job_id):
            _log_sync(job_id, f"🛑 Execução interrompida antes da página {pagina_atual}.")
            return

        process_ids = _coletar_ids_processos(sb)
        _log_sync(
            job_id,
            f"📄 Página {pagina_atual}/{total_paginas}: {len(process_ids)} processo(s) listado(s).",
        )

        if not process_ids:
            _log_sync(job_id, f"⚠️ Nenhum ID de processo encontrado na página {pagina_atual}.")
            break

        for indice_pagina, proc_id in enumerate(process_ids, start=1):
            if not _job_should_continue(job_id):
                _log_sync(job_id, f"🛑 Execução interrompida durante a página {pagina_atual}.")
                return

            processo_global += 1
            _log_sync(
                job_id,
                f"🔍 Abrindo processo {processo_global}/{total_processos} (pág {pagina_atual}, item {indice_pagina}/{len(process_ids)}): ID={proc_id}",
            )

            try:
                if not _abrir_processo_por_id(sb, proc_id, timeout=6):
                    _log_sync(job_id, f"⚠️ Não foi possível abrir os detalhes do processo ID={proc_id}.")
                    continue

                detalhes = _extrair_detalhes_processo(
                    sb,
                    proc_id=proc_id,
                    nome_referencia=nome_referencia,
                    cpf_referencia=cpf_referencia,
                    serventia_referencia=serventia_referencia,
                )
                if not detalhes:
                    _log_sync(job_id, f"⚠️ Extração vazia para o processo ID={proc_id}.")
                    continue

                _run_async(_append_scraped_batch(job_id, [detalhes]))
                _log_sync(
                    job_id,
                    (
                        f"✅ Processo extraído: {detalhes.get('numero_processo') or proc_id} | "
                        f"partes={len((detalhes.get('raw_data') or {}).get('polo_ativo', [])) + len((detalhes.get('raw_data') or {}).get('polo_passivo', []))} | "
                        f"movs={len(detalhes.get('movimentacoes') or [])}"
                    ),
                )
            except Exception as exc:
                _log_sync(job_id, f"❌ Falha ao extrair processo ID={proc_id} na página {pagina_atual}: {exc}")
            finally:
                is_last_on_page = indice_pagina == len(process_ids)
                next_page = pagina_atual + 1
                if is_last_on_page and next_page > total_paginas:
                    continue

                posicao_pagina = next_page - 1 if is_last_on_page else pagina_atual - 1
                if not _voltar_para_lista_processos(sb, posicao_pagina, timeout=6):
                    raise RuntimeError(
                        f"Não foi possível retornar para a lista após o processo ID={proc_id} "
                        f"(página {pagina_atual}, posicao {posicao_pagina})."
                    )

        pagina_atual += 1


def _search_process_by_number(sb: Any, process_number: str, job_id: int | None = None) -> list[dict[str, Any]]:
    sb.wait_for_ready_state_complete()
    _fill_process_number_if_available(sb, process_number)
    sb.execute_script(
        """
        var btn = document.getElementById('btnBuscar');
        if (btn) {
            btn.disabled = false;
            btn.click();
        }
        """
    )
    _esperar_contagem_elementos(sb, SELECTOR_LISTA_PROCESSOS, timeout=4)

    if _esperar_contagem_elementos(sb, SELECTOR_DETALHE_PROCESSO, timeout=2):
        return [
            _extrair_detalhes_processo(
                sb,
                proc_id=process_number,
                nome_referencia=None,
                cpf_referencia=None,
                serventia_referencia=None,
            )
        ]

    process_ids = _coletar_ids_processos(sb)
    if process_ids:
        if job_id is not None:
            _log_sync(job_id, f"🔍 Busca por número retornou listagem; abrindo ID real {process_ids[0]}.")
        if _abrir_processo_por_id(sb, process_ids[0], timeout=6):
            return [
                _extrair_detalhes_processo(
                    sb,
                    proc_id=process_ids[0],
                    nome_referencia=None,
                    cpf_referencia=None,
                    serventia_referencia=None,
                )
            ]

    page_source = sb.get_page_source()
    matched_processes = PROCESS_PATTERN.findall(page_source)
    if matched_processes:
        return [
            {
                "numero_processo": matched_processes[0],
                "nome_parte": None,
                "cpf_cnpj": None,
                "serventia": None,
                "advogados": [],
                "status_rpv": None,
                "movimentacoes": [],
                "raw_data": {"source": "page_source", "snippet": page_source[:5000]},
            }
        ]

    return [
        {
            "numero_processo": process_number,
            "nome_parte": None,
            "cpf_cnpj": None,
            "serventia": None,
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


def _obter_debug_paginacao(sb: Any) -> dict[str, Any]:
    debug_info = sb.execute_script(
        """
        return (function() {
            var body = document.body ? document.body.textContent : '';
            var totalMatch = body.match(/Total de:\\s*([\\d.]+)/);
            return {
                title: document.title || '',
                totalText: totalMatch ? totalMatch[1] : '0',
                hasPaginationInput: !!document.querySelector('input[name="PosicaoPaginaAtual"]'),
                hasPaginationIr: document.querySelectorAll('.Paginacao input[value="Ir"]').length > 0,
                tableRows: document.querySelectorAll('table tr[onclick]').length,
                bodySnippet: body.replace(/\\s+/g, ' ').slice(0, 500)
            };
        })();
        """
    ) or {}
    total_processos = int(str(debug_info.get("totalText", "0")).replace(".", "") or "0")
    return {
        "title": debug_info.get("title") or "",
        "total_processos": total_processos,
        "has_pagination_input": bool(debug_info.get("hasPaginationInput")),
        "has_pagination_ir": bool(debug_info.get("hasPaginationIr")),
        "table_rows": int(debug_info.get("tableRows") or 0),
        "body_snippet": debug_info.get("bodySnippet") or "",
    }


def _coletar_ids_processos(sb: Any) -> list[str]:
    process_ids = sb.execute_script(
        """
        return (function() {
            var rows = document.querySelectorAll('table tr[onclick]');
            var ids = [];
            rows.forEach(function(tr) {
                var onclick = tr.getAttribute('onclick') || '';
                var match = onclick.match(/submete\\('([^']+)'\\)/);
                if (match && match[1]) ids.push(match[1]);
            });
            return ids;
        })();
        """
    )
    if not process_ids:
        return []
    return [str(proc_id).strip() for proc_id in process_ids if str(proc_id).strip()]


def _esperar_contagem_elementos(
    sb: Any,
    selector: str,
    min_count: int = 1,
    timeout: float = 6,
    intervalo: float = 0.1,
) -> int:
    fim = time.monotonic() + timeout
    ultimo_total = 0
    while time.monotonic() < fim:
        total = _contar_elementos(sb, selector)
        if total >= min_count:
            return total
        ultimo_total = total
        sb.sleep(intervalo)
    return ultimo_total


def _contar_elementos(sb: Any, selector: str) -> int:
    try:
        total = sb.execute_script(f"return document.querySelectorAll({json.dumps(selector)}).length;")
        return int(total or 0)
    except Exception:
        return 0


def _abrir_processo_por_id(sb: Any, proc_id: str, timeout: float = 6) -> bool:
    sb.execute_script(
        f"""
        document.getElementById('PaginaAtual').value = '-1';
        var form = document.getElementById('Formulario');
        var hidden = document.getElementById('Id_Processo') || document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'Id_Processo';
        hidden.id = 'Id_Processo';
        hidden.value = {json.dumps(str(proc_id))};
        if (!document.getElementById('Id_Processo') && form) form.appendChild(hidden);
        if (form) form.submit();
        """
    )
    return _esperar_contagem_elementos(sb, SELECTOR_DETALHE_PROCESSO, timeout=timeout) > 0


def _navegar_para_lista_processos(sb: Any, posicao_pagina: int, timeout: float = 6) -> bool:
    sb.execute_script(
        f"""
        window.location.href = 'BuscaProcesso?PaginaAtual=2&Paginacao=true&PosicaoPaginaAtual={posicao_pagina}&PassoBusca=1';
        """
    )
    return _esperar_contagem_elementos(sb, SELECTOR_LISTA_PROCESSOS, timeout=timeout) > 0


def _voltar_para_lista_processos(sb: Any, posicao_pagina: int, timeout: float = 6) -> bool:
    for _ in range(2):
        try:
            sb.execute_script("history.back()")
        except Exception:
            break
        if _esperar_contagem_elementos(sb, SELECTOR_LISTA_PROCESSOS, timeout=1.5, intervalo=0.05):
            return True
    return _navegar_para_lista_processos(sb, posicao_pagina, timeout=timeout)


def _navegar_por_paginacao(sb: Any, posicao_pagina: int) -> bool:
    return bool(
        sb.execute_script(
            f"""
            return (function() {{
                var input = document.querySelector('input[name="PosicaoPaginaAtual"]');
                var btns = document.querySelectorAll('.Paginacao input[value="Ir"]');
                if (!input || !btns.length) return false;
                input.value = {json.dumps(str(posicao_pagina))};
                btns[0].click();
                return true;
            }})();
            """
        )
    )


def _extrair_detalhes_processo(
    sb: Any,
    proc_id: str,
    nome_referencia: str | None,
    cpf_referencia: str | None,
    serventia_referencia: str | None,
) -> dict[str, Any]:
    dados_js = sb.execute_script(
        """
        return (function() {
            var result = {};
            var allFS = document.querySelectorAll('fieldset');

            function getPartes(fs) {
                if (!fs) return [];
                var partes = [];
                var vizDatas = fs.querySelectorAll('fieldset.VisualizaDados');
                vizDatas.forEach(function(vd) {
                    var nome = '';
                    var cpf = '';
                    var span1 = vd.querySelector('span.destaque-nome');
                    if (span1) nome = span1.textContent.trim();
                    var span2 = vd.querySelector('span.span2');
                    if (span2) cpf = span2.textContent.trim();
                    if (nome) partes.push({ nome: nome, cpf_cnpj: cpf });
                });
                return partes;
            }

            function collectLabeledText(scope, labels) {
                if (!scope) return '';
                var divs = scope.querySelectorAll('div');
                for (var i = 0; i < divs.length; i++) {
                    var label = divs[i].textContent.replace(/\\s+/g, ' ').trim();
                    for (var j = 0; j < labels.length; j++) {
                        if (label.startsWith(labels[j])) {
                            var next = divs[i].nextElementSibling;
                            if (next && next.tagName === 'SPAN') return next.textContent.trim();
                            if (next) return next.textContent.replace(/\\s+/g, ' ').trim();
                        }
                    }
                }
                return '';
            }

            var poloAtivoFS = null;
            var poloPassivoFS = null;
            var outrasFS = null;
            for (var i = 0; i < allFS.length; i++) {
                var leg = allFS[i].querySelector('legend');
                if (!leg) continue;
                var txt = leg.textContent || '';
                if (txt.includes('Polo Ativo') || txt.includes('Exequente')) poloAtivoFS = allFS[i];
                if (txt.includes('Polo Passivo') || txt.includes('Executado')) poloPassivoFS = allFS[i];
                if (txt.includes('Outras')) outrasFS = allFS[i];
            }

            result.polo_ativo = getPartes(poloAtivoFS);
            result.polo_passivo = getPartes(poloPassivoFS);
            result.valor_causa = collectLabeledText(outrasFS, ['Valor da Causa']);
            result.classe = collectLabeledText(outrasFS, ['Classe']);
            result.assunto = collectLabeledText(outrasFS, ['Assunto']);
            result.serventia = collectLabeledText(outrasFS, ['Serventia', 'Serventia Atual']);
            result.processo_originario = '';
            var linkOrig = outrasFS ? outrasFS.querySelector('a[href*="ProcessoOutraServentia"]') : null;
            if (linkOrig) result.processo_originario = linkOrig.textContent.trim();
            if (!result.processo_originario) result.processo_originario = collectLabeledText(outrasFS, ['Processo Originário']);

            var numEl = document.querySelector('#span_proc_numero, .destaque-proc-numero');
            result.numero_processo = numEl ? numEl.textContent.trim() : '';
            if (!result.numero_processo) {
                var autos = document.querySelector('fieldset');
                if (autos) {
                    var match = autos.textContent.match(/(\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}|\\d+[-.]\\d+)/);
                    result.numero_processo = match ? match[0] : '';
                }
            }

            var movRows = document.querySelectorAll('#tabListaProcesso tr, #TabelaArquivos tbody tr');
            var movs = [];
            movRows.forEach(function(tr) {
                var txt = (tr.textContent || '').replace(/\\s+/g, ' ').trim();
                if (txt.length > 5) movs.push({ texto: txt });
            });
            result.movimentacoes = movs;
            return result;
        })();
        """
    ) or {}

    advogados = _obter_nomes_advogados(sb, timeout=2) or []
    partes = [
        *(dados_js.get("polo_ativo") or []),
        *(dados_js.get("polo_passivo") or []),
    ]
    nomes = [parte.get("nome", "").strip() for parte in partes if parte.get("nome")]
    cpfs = [parte.get("cpf_cnpj", "").strip() for parte in partes if parte.get("cpf_cnpj")]
    numero_processo = (dados_js.get("numero_processo") or "").strip() or proc_id
    serventia = (dados_js.get("serventia") or "").strip() or serventia_referencia

    return {
        "numero_processo": numero_processo,
        "nome_parte": " | ".join(dict.fromkeys(nomes)) or nome_referencia,
        "cpf_cnpj": " | ".join(dict.fromkeys(cpfs)) or cpf_referencia,
        "serventia": serventia,
        "advogados": [{"nome": nome} for nome in advogados],
        "status_rpv": None,
        "movimentacoes": dados_js.get("movimentacoes") or [],
        "raw_data": {
            "proc_id": proc_id,
            "numero_processo": numero_processo,
            "polo_ativo": dados_js.get("polo_ativo") or [],
            "polo_passivo": dados_js.get("polo_passivo") or [],
            "valor_causa": dados_js.get("valor_causa"),
            "classe": dados_js.get("classe"),
            "assunto": dados_js.get("assunto"),
            "processo_originario": dados_js.get("processo_originario"),
            "serventia": serventia,
            "advogados": advogados,
            "movimentacoes": dados_js.get("movimentacoes") or [],
        },
    }


def _obter_nomes_advogados(sb: Any, timeout: float = 3) -> list[str] | None:
    clicou = sb.execute_script(
        """
        return (function() {
            var links = document.querySelectorAll('a');
            for (var i = 0; i < links.length; i++) {
                if (links[i].href && links[i].href.indexOf('ProcessoParteAdvogado') !== -1) {
                    links[i].click();
                    return true;
                }
            }
            return false;
        })();
        """
    )
    if not clicou:
        return None

    _esperar_contagem_elementos(sb, SELECTOR_TABELA_ADVOGADOS, timeout=timeout)
    nomes = sb.execute_script(
        """
        return (function() {
            var rows = document.querySelectorAll('#tabListaAdvogadoParte tr');
            var nomes = [];
            rows.forEach(function(tr) {
                var tds = tr.querySelectorAll('td');
                if (tds.length >= 4) {
                    var nome = tds[3].textContent.trim();
                    if (nome && nome.length > 3) nomes.push(nome);
                }
            });
            return Array.from(new Set(nomes));
        })();
        """
    ) or []
    return [nome for nome in nomes if nome]


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


def _is_selector_present(sb: Any, selector: str) -> bool:
    try:
        return sb.is_element_present(selector)
    except (NoSuchElementException, TimeoutException):
        return False


def _job_should_continue(job_id: int) -> bool:
    return _run_async(_wait_if_paused_or_canceled(job_id))


def _log_sync(job_id: int, message: str) -> None:
    _run_async(_append_job_log(job_id, message))


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


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


async def _set_job_total_items(job_id: int, total_items: int) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if total_items > 0:
            job.total_items = total_items
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
            job.logs = [
                *(job.logs or []),
                f"📄 {len(scraped_items)} processo(s) persistido(s). Total processado: {job.processed_items}",
            ][-200:]

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


async def _persist_job_success(job_id: int, result_dir: Path) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
            return

        result = await session.execute(
            select(ProcessRecord).where(ProcessRecord.job_id == job_id).order_by(ProcessRecord.id)
        )
        records = result.scalars().all()
        job.total_items = max(job.total_items, len(records))
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
