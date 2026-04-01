# TJGO CAPFI Cloud

Automação de busca e extração de processos judiciais do TJGO via PROJUDI, hospedada na nuvem.

## Stack
- **Backend:** FastAPI + PostgreSQL (Railway)
- **Scraping:** SeleniumBase headless (Chrome)
- **Frontend:** React + shadcn/ui (Railway/Vercel)
- **Auth:** JWT

## Funcionalidades
- Login com usuário/senha
- 4 modos de busca: Planilha, Serventia, Nome/CPF, Combinada
- Jobs de scraping em background (fila)
- Dashboard de status dos jobs em tempo real
- Download de resultados em Excel
