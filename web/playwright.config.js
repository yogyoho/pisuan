import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置（知识工厂前端回归）。
 *
 * 注意：web-dev 容器是 Alpine（musl），Playwright 无法在其内运行浏览器。
 * 本套件在宿主机（Windows/Mac/Linux glibc）或 CI 上执行，指向运行中的 dev server。
 *
 * 运行前设置管理员凭据环境变量（不写入文件）：
 *   $env:ADMIN_USER="admin"; $env:ADMIN_PASS="<password>"
 *   pnpm test:e2e
 *
 * 知识工厂路由均为 requiresAdmin，auth fixture 负责登录并复用 storageState。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // 知识工厂有状态，串行更稳
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    locale: 'zh-CN',
    actionTimeout: 10000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
