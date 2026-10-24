import { withMediaToken } from '@/lib/auth'

export const API_BASE = 'http://localhost:8001'

export const resolveUrl = (u?: string | null): string => {
  if (!u) return ''
  const abs = u.startsWith('http') ? u : `${API_BASE}${u}`
  return abs.startsWith(`${API_BASE}/`) ? withMediaToken(abs) : abs
}
