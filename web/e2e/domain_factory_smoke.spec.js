import { test, expect } from './fixtures/auth'

/**
 * 知识工厂冒烟测试：导航可达、tab 切换、页面无阻断性 console 错误。
 */
test.describe('知识工厂主页面', () => {
  test('导航到知识工厂 + tab 切换 + 无 console error', async ({ authedPage }) => {
    const page = authedPage
    const errors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.goto('/domain-factory')
    await expect(page.locator('text=知识工厂').first()).toBeVisible({ timeout: 15000 })

    // tab 切换：数据源管理 → ETL 清洗工作台
    const tabWorkbench = page.locator('.ant-tabs-tab:has-text("清洗工作台"), .ant-tabs-tab:has-text("ETL")').first()
    if (await tabWorkbench.count()) {
      await tabWorkbench.click()
      await page.waitForTimeout(500)
    }

    // 回到数据源 tab
    const tabData = page.locator('.ant-tabs-tab:has-text("数据源")').first()
    if (await tabData.count()) {
      await tabData.click()
      await page.waitForTimeout(500)
    }

    // 允许已知无关 error（如第三方扩展），但阻断性 error 应为 0
    const blocking = errors.filter((e) => !e.includes('favicon') && !e.includes('net::'))
    expect(blocking.length, `console errors: ${blocking.join(' | ')}`).toBe(0)
  })

  test('实体构建器页面可达', async ({ authedPage }) => {
    await authedPage.goto('/domain-factory/entity-builder')
    await expect(authedPage.locator('text=实体构建器, text=实体库').first()).toBeVisible({ timeout: 15000 })
  })

  test('大纲模板页面可达', async ({ authedPage }) => {
    await authedPage.goto('/domain-factory/outline-template')
    await expect(authedPage.locator('text=大纲').first()).toBeVisible({ timeout: 15000 })
  })
})
