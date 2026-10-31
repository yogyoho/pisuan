import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  AVATAR_BACKGROUND_TOKENS,
  generatePixelAvatar,
  getAvatarColorIndex,
  getAvatarFallbackStyle,
  getAvatarInitials
} from '../../src/utils/pixelAvatar.js'

const LOCAL_USER_AVATAR = '/user-avatar.svg'

test('user avatars resolve to the bundled local icon', () => {
  assert.equal(generatePixelAvatar('user-001'), LOCAL_USER_AVATAR)
  assert.equal(generatePixelAvatar('user-002'), LOCAL_USER_AVATAR)
  assert.equal(generatePixelAvatar(' user/中文 '), LOCAL_USER_AVATAR)
  assert.doesNotMatch(generatePixelAvatar('user-001'), /^https?:/i)
  assert.throws(() => generatePixelAvatar(''), /requires an id/)
  assert.throws(() => generatePixelAvatar(null), /requires an id/)

  assert.equal(getAvatarInitials('张三丰', 'user'), '张三')
  assert.equal(getAvatarInitials('Alice', 'user'), 'Al')
  assert.equal(getAvatarInitials('', 'user'), '用户')
  assert.equal(getAvatarInitials('', 'agent'), '智能')

  const first = getAvatarColorIndex('user-001')
  assert.equal(first, getAvatarColorIndex('user-001'))
  assert.notEqual(first, getAvatarColorIndex('user-002'))
  assert.ok(first >= 0 && first < AVATAR_BACKGROUND_TOKENS.length)

  const userStyle = getAvatarFallbackStyle('user-001', 'user')
  assert.equal(userStyle.background, 'var(--main-color)')
  assert.equal(userStyle.color, '#fff')
  assert.equal(getAvatarFallbackStyle('user-001').background, 'var(--main-color)')

  const agentStyle = getAvatarFallbackStyle('agent-001', 'agent')
  assert.match(agentStyle.background, /^linear-gradient\(/)
  assert.equal(typeof agentStyle.color, 'string')
})

test('bundled user avatar is served locally without remote references', async () => {
  const svg = await readFile(new URL(`../../public${LOCAL_USER_AVATAR}`, import.meta.url), 'utf8')
  assert.match(svg, /<svg[\s>]/)
  assert.doesNotMatch(svg, /(?:href|src)=["']https?:/i)
  assert.doesNotMatch(svg, /url\(\s*["']?https?:/i)
})
