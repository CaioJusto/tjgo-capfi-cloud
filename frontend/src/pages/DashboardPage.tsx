import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJobs, getJob, createJob, pauseJob, resumeJob, deleteJob, downloadResults, uploadPlanilha } from '@/lib/api'
import { LogOut, Plus, Download, Trash2, RefreshCw, Upload, Settings, Pause, Play, Activity, FileText } from 'lucide-react'

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  pending:  { label: 'Aguardando', color: 'bg-yellow-100 text-yellow-700' },
  running:  { label: 'Executando', color: 'bg-blue-100 text-blue-700' },
  paused:   { label: 'Pausado', color: 'bg-orange-100 text-orange-700' },
  done:     { label: 'Concluído', color: 'bg-green-100 text-green-700' },
  failed:   { label: 'Falhou', color: 'bg-red-100 text-red-700' },
  canceled: { label: 'Cancelado', color: 'bg-gray-100 text-gray-600' },
}

const JOB_TYPES = [
  { value: 'nome', label: 'Por Nome/CPF' },
  { value: 'serventia', label: 'Por Serventia' },
  { value: 'planilha', label: 'Por Planilha' },
  { value: 'combinada', label: 'Combinada' },
]

export default function DashboardPage({ user, onLogout, onEditCredentials }: { user: any; onLogout: () => void; onEditCredentials?: () => void }) {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [jobType, setJobType] = useState('nome')
  const [formData, setFormData] = useState<any>({ pagina_inicial: 1 })
  const [planilhaFile, setPlanilhaFile] = useState<File | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => getJobs(),
    refetchInterval: 4000,
  })

  useEffect(() => {
    if (!selectedJobId && jobs?.items?.length) setSelectedJobId(jobs.items[0].id)
  }, [jobs, selectedJobId])

  const { data: selectedJob } = useQuery({
    queryKey: ['job', selectedJobId],
    queryFn: () => getJob(selectedJobId as number),
    enabled: !!selectedJobId,
    refetchInterval: 2500,
  })

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['jobs'] })
    if (selectedJobId) qc.invalidateQueries({ queryKey: ['job', selectedJobId] })
  }

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ['jobs'] })
      setSelectedJobId(job.id)
      setShowForm(false)
      setFormData({ pagina_inicial: 1 })
      setPlanilhaFile(null)
    }
  })

  const pauseMutation = useMutation({ mutationFn: pauseJob, onSuccess: refreshAll })
  const resumeMutation = useMutation({ mutationFn: resumeJob, onSuccess: refreshAll })
  const cancelMutation = useMutation({ mutationFn: deleteJob, onSuccess: refreshAll })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    let params = { ...formData, job_type: jobType }
    if (jobType === 'planilha' && planilhaFile) {
      const up = await uploadPlanilha(planilhaFile)
      params = { ...params, processes: up.processes }
    }
    createMutation.mutate(params)
  }

  const handleDownload = async (id: number, type: string) => {
    const blob = await downloadResults(id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `resultados_${type}_${id}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }

  const selectedStatus = selectedJob ? (STATUS_LABEL[selectedJob.status] || STATUS_LABEL.pending) : null
  const progressPct = useMemo(() => {
    if (!selectedJob) return 0
    if (selectedJob.total_items <= 0) return selectedJob.status === 'done' ? 100 : 0
    return Math.round((selectedJob.processed_items / selectedJob.total_items) * 100)
  }, [selectedJob])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">TJGO CAPFI Cloud</h1>
          <p className="text-sm text-gray-500">Olá, {user?.username}</p>
        </div>
        <div className="flex items-center gap-3">
          {onEditCredentials && (
            <button onClick={onEditCredentials} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 border border-gray-200 rounded-lg px-3 py-1.5">
              <Settings className="h-4 w-4" /> Credenciais PROJUDI
            </button>
          )}
          <button onClick={onLogout} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
            <LogOut className="h-4 w-4" /> Sair
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-[1.2fr_.8fr] gap-6">
        <section className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-900">Buscas</h2>
            <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
              <Plus className="h-4 w-4" /> Nova Busca
            </button>
          </div>

          {showForm && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h3 className="font-semibold text-gray-900 mb-4">Nova Busca</h3>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de busca</label>
                  <select value={jobType} onChange={e => { setJobType(e.target.value); setFormData({ pagina_inicial: 1 }) }} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    {JOB_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>

                {(jobType === 'nome' || jobType === 'combinada') && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Nome da parte</label>
                    <input type="text" required value={formData.nome || ''} onChange={e => setFormData({ ...formData, nome: e.target.value })} placeholder="Nome completo" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                )}

                {(jobType === 'nome' || jobType === 'combinada') && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">CPF/CNPJ <span className="text-gray-400 font-normal">(opcional)</span></label>
                    <input type="text" value={formData.cpf || ''} onChange={e => setFormData({ ...formData, cpf: e.target.value })} placeholder="00000000000" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                )}

                {(jobType === 'serventia' || jobType === 'combinada') && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">ID da Serventia {jobType === 'combinada' && <span className="text-gray-400 font-normal">(opcional)</span>}</label>
                      <input type="text" required={jobType === 'serventia'} value={formData.serventia_id || ''} onChange={e => setFormData({ ...formData, serventia_id: e.target.value })} placeholder="Ex: 123" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Nome da Serventia <span className="text-gray-400 font-normal">(opcional)</span></label>
                      <input type="text" value={formData.serventia_nome || ''} onChange={e => setFormData({ ...formData, serventia_nome: e.target.value })} placeholder="Ex: 1ª Vara Civil" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                  </div>
                )}

                {jobType !== 'planilha' && (
                  <div className="w-40">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Página inicial <span className="text-gray-400 font-normal">(retomar)</span></label>
                    <input type="number" min={1} value={formData.pagina_inicial || 1} onChange={e => setFormData({ ...formData, pagina_inicial: Math.max(1, parseInt(e.target.value) || 1) })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                )}

                {jobType === 'planilha' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Arquivo Excel (.xlsx)</label>
                    <div className="flex items-center gap-2">
                      <input type="file" accept=".xlsx,.xls" onChange={e => setPlanilhaFile(e.target.files?.[0] || null)} className="text-sm text-gray-600 file:mr-3 file:px-3 file:py-1.5 file:border file:border-gray-300 file:rounded file:text-sm file:bg-white file:text-gray-700 hover:file:bg-gray-50" />
                      {planilhaFile && <Upload className="h-4 w-4 text-green-500" />}
                    </div>
                  </div>
                )}

                <div className="flex gap-3 pt-2">
                  <button type="submit" disabled={createMutation.isPending} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                    {createMutation.isPending ? 'Criando...' : 'Iniciar Busca'}
                  </button>
                  <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50">
                    Cancelar
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Histórico de buscas</span>
              <button onClick={refreshAll} className="text-gray-400 hover:text-gray-600"><RefreshCw className="h-4 w-4" /></button>
            </div>

            {isLoading ? (
              <div className="p-8 text-center text-gray-400 text-sm">Carregando...</div>
            ) : !jobs?.items?.length ? (
              <div className="p-8 text-center text-gray-400 text-sm">Nenhuma busca ainda. Clique em "Nova Busca" para começar.</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {jobs.items.map((job: any) => {
                  const st = STATUS_LABEL[job.status] || STATUS_LABEL.pending
                  const pct = job.total_items > 0 ? Math.round((job.processed_items / job.total_items) * 100) : 0
                  return (
                    <div key={job.id} className={`px-6 py-4 flex items-center justify-between gap-4 cursor-pointer ${selectedJobId === job.id ? 'bg-blue-50/50' : 'hover:bg-gray-50'}`} onClick={() => setSelectedJobId(job.id)}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-gray-900 text-sm">#{job.id} — {JOB_TYPES.find(t => t.value === job.job_type)?.label || job.job_type}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${st.color}`}>{st.label}</span>
                        </div>
                        {['running', 'paused'].includes(job.status) && (
                          <div className="mt-1.5">
                            <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                              <span>{job.processed_items}/{job.total_items || '?'} processos</span>
                              <span>{job.total_items > 0 ? pct : 0}%</span>
                            </div>
                            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${job.total_items > 0 ? pct : 8}%` }} />
                            </div>
                          </div>
                        )}
                        {job.error_message && <p className="text-xs text-red-500 mt-1 truncate">{job.error_message}</p>}
                        <p className="text-xs text-gray-400 mt-0.5">{new Date(job.created_at).toLocaleString('pt-BR')}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {job.status === 'running' && (
                          <button onClick={(e) => { e.stopPropagation(); pauseMutation.mutate(job.id) }} className="flex items-center gap-1 px-3 py-1.5 bg-yellow-50 text-yellow-700 border border-yellow-200 rounded-lg text-xs font-medium hover:bg-yellow-100">
                            <Pause className="h-3.5 w-3.5" /> Pausar
                          </button>
                        )}
                        {job.status === 'paused' && (
                          <button onClick={(e) => { e.stopPropagation(); resumeMutation.mutate(job.id) }} className="flex items-center gap-1 px-3 py-1.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg text-xs font-medium hover:bg-blue-100">
                            <Play className="h-3.5 w-3.5" /> Retomar
                          </button>
                        )}
                        {job.status === 'done' && (
                          <button onClick={(e) => { e.stopPropagation(); handleDownload(job.id, job.job_type) }} className="flex items-center gap-1 px-3 py-1.5 bg-green-50 text-green-700 border border-green-200 rounded-lg text-xs font-medium hover:bg-green-100">
                            <Download className="h-3.5 w-3.5" /> Planilha
                          </button>
                        )}
                        {!['done', 'failed', 'canceled'].includes(job.status) && (
                          <button onClick={(e) => { e.stopPropagation(); cancelMutation.mutate(job.id) }} className="flex items-center gap-1 px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg text-xs font-medium hover:bg-red-100">
                            <Trash2 className="h-3.5 w-3.5" /> Cancelar
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        <aside className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="h-4 w-4 text-blue-600" />
              <h3 className="font-semibold text-gray-900">Acompanhamento da execução</h3>
            </div>

            {!selectedJob ? (
              <p className="text-sm text-gray-400">Selecione um job para ver os detalhes.</p>
            ) : (
              <div className="space-y-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-sm font-medium text-gray-900">#{selectedJob.id}</span>
                    {selectedStatus && <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${selectedStatus.color}`}>{selectedStatus.label}</span>}
                  </div>
                  <p className="text-sm text-gray-500">{JOB_TYPES.find(t => t.value === selectedJob.job_type)?.label || selectedJob.job_type}</p>
                </div>

                <div>
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Progresso</span>
                    <span>{progressPct}%</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${Math.max(progressPct, selectedJob.status === 'running' ? 8 : 0)}%` }} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{selectedJob.processed_items} processado(s) / {selectedJob.total_items || 'a definir'}</p>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-400 text-xs">Criado em</p>
                    <p className="text-gray-800">{new Date(selectedJob.created_at).toLocaleString('pt-BR')}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-400 text-xs">Atualizado em</p>
                    <p className="text-gray-800">{new Date(selectedJob.updated_at).toLocaleString('pt-BR')}</p>
                  </div>
                </div>

                <div className="bg-gray-950 text-gray-100 rounded-xl p-4 h-[420px] overflow-y-auto">
                  <div className="flex items-center gap-2 mb-3 text-sm font-medium text-gray-200">
                    <FileText className="h-4 w-4" /> Logs em tempo real
                  </div>
                  <div className="space-y-2 text-xs font-mono">
                    {(selectedJob.logs?.length ? selectedJob.logs : ['Nenhum log ainda.']).map((line: string, idx: number) => (
                      <div key={idx} className="whitespace-pre-wrap break-words text-gray-300">{line}</div>
                    ))}
                  </div>
                </div>

                {selectedJob.status === 'done' && (
                  <button onClick={() => handleDownload(selectedJob.id, selectedJob.job_type)} className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
                    <Download className="h-4 w-4" /> Salvar planilha agora
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  )
}
