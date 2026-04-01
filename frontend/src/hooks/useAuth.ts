import { useState, useEffect } from 'react'
import { getMe } from '@/lib/api'

export function useAuth() {
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setLoading(false); return }
    getMe().then(setUser).catch(() => localStorage.removeItem('token')).finally(() => setLoading(false))
  }, [])

  const logout = () => { localStorage.removeItem('token'); setUser(null); window.location.href = '/login' }

  return { user, loading, setUser, logout }
}
