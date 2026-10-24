import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import type { CharacterResponse, IdentityResponse, CharacterListItem } from '@/lib/api'

export function useCharacter() {
  const [characters, setCharacters] = useState<CharacterListItem[]>([])
  const [character, setCharacter] = useState<CharacterResponse | null>(null)
  const [identity, setIdentity] = useState<IdentityResponse | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    const list = await api.characters()
    setCharacters(list.characters)
    setActiveId(list.characters.find((c) => c.active)?.id ?? null)
    const [ch, idn] = await Promise.all([api.character(), api.identity()])
    setCharacter(ch)
    setIdentity(idn)
  }, [])

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const tick = () => {
      if (cancelled) return
      fetchAll().catch(() => {
        if (cancelled) return
        if (++attempts % 15 === 0)
          console.warn(`[useCharacter] бэкенд ещё не отвечает (${attempts} попыток) — жду`)
        setTimeout(tick, 2000)
      })
    }
    tick()
    return () => {
      cancelled = true
    }
  }, [fetchAll])

  const select = useCallback(
    async (id: string, secret?: string): Promise<'ok' | 'locked' | 'wrong' | 'error'> => {
      try {
        const r = await api.selectCharacter(id, secret)
        if (r?.locked) return 'locked'
        if (r?.wrong_password) return 'wrong'
        if (r?.error) {
          console.error('[useCharacter] select failed', r.error)
          return 'error'
        }
        await fetchAll()
        return 'ok'
      } catch (e) {
        console.error('[useCharacter] select failed', e)
        return 'error'
      }
    },
    [fetchAll],
  )

  const refreshActive = useCallback(async () => {
    try {
      const [ch, idn] = await Promise.all([api.character(), api.identity()])
      setCharacter(ch)
      setIdentity(idn)
    } catch (e) {
      console.error('[useCharacter] refreshActive failed', e)
    }
  }, [])

  return { characters, character, identity, activeId, select, refresh: fetchAll, refreshActive }
}
