// [pisuan-custom] 用户默认头像使用随前端包发布的本地图标，内网/离线部署不请求外网图源。
const LOCAL_USER_AVATAR = '/user-avatar.svg'
// [pisuan-custom] 用户头像底色统一取系统主体色（浅色 #4f46e5，深色主题由 token 映射）。
const USER_AVATAR_BACKGROUND = { background: 'var(--main-color)', color: '#fff' }
// [pisuan-custom] 智能体统一头像：thumbs 扁平图形套图（用户选定）。2026-11-07 交付改造：
// 原实现请求 api.dicebear.com 外网 API，客户无网环境全部裂图；现随前端包本地发布 12 张
// 固定套图（web/public/agent-avatars/，DiceBear thumbs 风格，CC0 1.0 公有领域，权利声明
// 已内嵌各 SVG metadata），按 seed 哈希取图，零外网请求。
const AGENT_AVATAR_COUNT = 12

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

/** [pisuan-custom] 用户头像统一为本地图标；保留入参校验，调用方仍以 uid 判断是否渲染默认头像。 */
export const generatePixelAvatar = (id) => {
  normalizeSeed(id)
  return LOCAL_USER_AVATAR
}

/** [pisuan-custom] 智能体统一使用本地 thumbs 套图（seed 哈希取图），与用户头像（本地人形图标）区分；上游无此函数。 */
export const generateAgentAvatar = (id) => {
  const seed = normalizeSeed(id)
  const index = (seedHash(seed) % AGENT_AVATAR_COUNT) + 1
  return `/agent-avatars/agent-avatar-${index}.svg`
}

export const getAvatarInitials = (name, kind = 'user') => {
  const fallback = kind === 'agent' ? '智能' : '用户'
  const normalizedName = String(name || '').trim()
  if (!normalizedName) return fallback
  return Array.from(normalizedName).slice(0, 2).join('')
}

const seedHash = (value) => {
  let hash = 0
  for (const char of value) {
    hash = (hash * 31 + char.codePointAt(0)) >>> 0
  }
  return hash
}

export const getAvatarColorIndex = (seed) => {
  const normalizedSeed = String(seed || '').trim()
  const value = normalizedSeed || 'avatar'
  return seedHash(value) % AVATAR_BACKGROUND_TOKENS.length
}

/** [pisuan-custom] 头像兜底底色：用户取系统主体色，智能体按种子取渐变色板。 */
export const getAvatarFallbackStyle = (seed, kind = 'user') =>
  kind === 'user' ? USER_AVATAR_BACKGROUND : AVATAR_BACKGROUND_TOKENS[getAvatarColorIndex(seed)]
