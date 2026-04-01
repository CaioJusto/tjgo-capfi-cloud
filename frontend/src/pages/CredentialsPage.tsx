import { useState, useEffect } from 'react'
import { getCredentials, saveCredentials } from '@/lib/api'
import { KeyRound, Eye, EyeOff, CheckCircle, ArrowRight } from 'lucide-react'

interface Props {
  onSaved: () => void
}

export default function CredentialsPage({ onSaved }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    getCredentials()
      .then((data) => {
        if (data.projudi_username) setUsername(data.projudi_username)
      })
      .catch(() => {})
      .finally(() => setChecking(false))
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('Preencha usuário e senha do PROJUDI')
      return
    }
    setLoading(true)
    setError('')
    try {
      await saveCredentials(username.trim(), password)
      setSuccess(true)
      setTimeout(() => onSaved(), 800)
    } catch {
      setError('Erro ao salvar credenciais. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  if (checking) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8">
          <div className="flex justify-center mb-6">
            <div className="w-14 h-14 bg-blue-50 rounded-full flex items-center justify-center">
              <KeyRound className="h-7 w-7 text-blue-600" />
            </div>
          </div>
          <div className="text-center mb-6">
            <h2 className="text-xl font-bold text-gray-900">Credenciais do PROJUDI</h2>
            <p className="text-gray-500 text-sm mt-1">
              Informe seu usuário e senha de acesso ao sistema PROJUDI do TJGO.<br />
              São as mesmas credenciais que você usa no aplicativo offline.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Usuário PROJUDI
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                placeholder="Seu usuário no PROJUDI"
                autoComplete="username"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Senha PROJUDI
              </label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  placeholder="Sua senha no PROJUDI"
                  autoComplete="current-password"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPass ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || success}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {success ? (
                <><CheckCircle className="h-4 w-4" /> Salvo!</>
              ) : loading ? (
                <><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" /> Salvando...</>
              ) : (
                <>Salvar e continuar <ArrowRight className="h-4 w-4" /></>
              )}
            </button>
          </form>

          <p className="text-xs text-gray-400 text-center mt-4">
            Suas credenciais ficam armazenadas de forma segura e são usadas apenas para acessar o PROJUDI nas buscas.
          </p>
        </div>
      </div>
    </div>
  )
}
