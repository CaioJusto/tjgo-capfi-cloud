import { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import CredentialsPage from './pages/CredentialsPage'
import DashboardPage from './pages/DashboardPage'
import { getMe, getCredentials } from './lib/api'

type Step = 'loading' | 'login' | 'credentials' | 'dashboard'

export default function App() {
  const [step, setStep] = useState<Step>('loading')
  const [user, setUser] = useState<any>(null)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setStep('login'); return }

    getMe()
      .then(async (u) => {
        setUser(u)
        // Verificar se já tem credenciais PROJUDI
        try {
          const creds = await getCredentials()
          setStep(creds.has_password ? 'dashboard' : 'credentials')
        } catch {
          setStep('credentials')
        }
      })
      .catch(() => {
        localStorage.removeItem('token')
        setStep('login')
      })
  }, [])

  const handleLogin = async (data: any) => {
    setUser(data.user || data)
    // Após login, verificar credenciais PROJUDI
    try {
      const creds = await getCredentials()
      setStep(creds.has_password ? 'dashboard' : 'credentials')
    } catch {
      setStep('credentials')
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setUser(null)
    setStep('login')
  }

  if (step === 'loading') return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
    </div>
  )

  if (step === 'login') return <LoginPage onLogin={handleLogin} />
  if (step === 'credentials') return <CredentialsPage onSaved={() => setStep('dashboard')} />
  return <DashboardPage user={user} onLogout={handleLogout} onEditCredentials={() => setStep('credentials')} />
}
