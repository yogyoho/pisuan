import { test as base, expect } from '@playwright/test'

/**
 * 登录 fixture：用 ADMIN_USER/ADMIN_PASS 环境变量登录，复用 storageState。
 * 凭据只从环境读取，不硬编码、不落盘。
 *
 * 用法：
 *   import { test, expect } from './fixtures/auth'
 *   test('xxx', async ({ authedPage }) => { ... })
 */
const ADMIN_USER = process.env.ADMIN_USER
const ADMIN_PASS = process.env.ADMIN_PASS

export const test = base.extend<{ authedPage: import('@playwright/test').Page }>({
  authedPage: async ({ page }, use) => {
    if (!ADMIN_USER || !ADMIN_PASS) {
      throw new Error('缺少 ADMIN_USER/ADMIN_PASS 环境变量，无法登录跑知识工厂 E2E')
    }
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"], input[id="username"]', ADMIN_USER)
    await page.fill('input[type="password"]', ADMIN_PASS)
    await page.click('button[type="submit"], button:has-text("登录")')
    await page.waitForURL(/(dashboard|domain-factory|agent|database)/, { timeout: 15000 })
    await use(page)
  },
})

export { expect }
