export const TOKEN_HEADER = 'X-MaidLink-Token'
const MEDIA_PARAM = 'mt'
const WS_PROTOCOL = 'maidlink'
const WS_TOKEN_PREFIX = 'maidlink-token.'

export const apiToken = (): string => window.maidlink?.apiToken || ''
export const mediaToken = (): string => window.maidlink?.mediaToken || ''

export function authHeaders(): Record<string, string> {
  const t = apiToken()
  return t ? { [TOKEN_HEADER]: t } : {}
}

export function wsProtocols(): string[] | undefined {
  const t = apiToken()
  return t ? [WS_PROTOCOL, WS_TOKEN_PREFIX + t] : undefined
}

export function withMediaToken(url: string): string {
  const t = mediaToken()
  if (!t || !url || /[?&]mt=/.test(url)) return url
  const hash = url.indexOf('#')
  const base = hash < 0 ? url : url.slice(0, hash)
  const tail = hash < 0 ? '' : url.slice(hash)
  return `${base}${base.includes('?') ? '&' : '?'}${MEDIA_PARAM}=${encodeURIComponent(t)}${tail}`
}
