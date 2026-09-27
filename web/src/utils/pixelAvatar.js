const DICEBEAR_GLYPHS_AVATAR_BASE_URL = 'https://api.dicebear.com/10.x/glyphs/svg'
// [pisuan-custom] 智能体统一头像：thumbs 扁平图形套图（用户选定；上游仅 glyphs 一套），同步时保留
const DICEBEAR_AGENT_AVATAR_BASE_URL = 'https://api.dicebear.com/10.x/thumbs/svg'

export const AVATAR_BACKGROUND_TOKENS = [
  { background: 'linear-gradient(135deg, var(--main-600), var(--color-info-500))', color: '#fff' },
  {
    background: 'linear-gradient(135deg, var(--chart-palette-5), var(--chart-palette-9))',
    color: '#fff'
  },
  {
    background: 'linear-gradient(135deg, var(--chart-palette-7), var(--chart-palette-3))',
    color: '#fff'
  },
  {
    background: 'linear-gradient(135deg, var(--color-accent-500), var(--chart-palette-6))',
    color: '#fff'
  },
  {
    background: 'linear-gradient(135deg, var(--chart-palette-4), var(--color-error-500))',
    color: '#fff'
  }
]

const normalizeSeed = (id) => {
  if (id === null || id === undefined || String(id).trim() === '') {
    throw new Error('generatePixelAvatar requires an id')
  }
  return String(id).trim()
}

export const generatePixelAvatar = (id) => {
  const seed = normalizeSeed(id)
  return `${DICEBEAR_GLYPHS_AVATAR_BASE_URL}?seed=${encodeURIComponent(seed)}`
}

/** [pisuan-custom] 智能体统一使用 thumbs 套图，与用户头像（glyphs 符号）区分；上游无此函数。 */
export const generateAgentAvatar = (id) => {
  const seed = normalizeSeed(id)
  return `${DICEBEAR_AGENT_AVATAR_BASE_URL}?seed=${encodeURIComponent(seed)}`
}

export const getAvatarInitials = (name, kind = 'user') => {
  const fallback = kind === 'agent' ? '智能' : '用户'
  const normalizedName = String(name || '').trim()
  if (!normalizedName) return fallback
  return Array.from(normalizedName).slice(0, 2).join('')
}

export const getAvatarColorIndex = (seed) => {
  const normalizedSeed = String(seed || '').trim()
  const value = normalizedSeed || 'avatar'
  let hash = 0
  for (const char of value) {
    hash = (hash * 31 + char.codePointAt(0)) >>> 0
  }
  return hash % AVATAR_BACKGROUND_TOKENS.length
}

export const getAvatarFallbackStyle = (seed) => AVATAR_BACKGROUND_TOKENS[getAvatarColorIndex(seed)]
