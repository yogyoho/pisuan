import { test, expect } from './fixtures/auth'

/**
 * ETL 清洗工作台 E2E：最复杂且零测试的页面。
 * 覆盖核心交互：段落选择、parameter 详情面板渲染、slot chip 展示、JSON 编辑模式。
 *
 * 依赖：至少一个 WAITING_REVIEW 任务存在（前置 upload）。无任务时 skip。
 */
test.describe('ETL 清洗工作台', () => {
  test.beforeEach(async ({ authedPage }) => {
    await authedPage.goto('/domain-factory')
    // 切到 ETL 清洗工作台 tab
    const tab = authedPage.locator('.ant-tabs-tab:has-text("清洗工作台"), .ant-tabs-tab:has-text("ETL")').first()
    await tab.waitFor({ state: 'visible', timeout: 10000 })
    await tab.click()
    await authedPage.waitForTimeout(800)
  })

  test('有任务时：选择段落 + parameter 详情面板渲染', async ({ authedPage }) => {
    const page = authedPage
    // 找一个可点击的段落项（class 含 paragraph）
    const firstPara = page.locator('.paragraph').first()
    if (!(await firstPara.count())) {
      test.skip(true, '无 WAITING_REVIEW 任务，跳过段落交互测试')
    }
    await firstPara.click()
    await page.waitForTimeout(400)

    // 详情面板应出现（结构化详情 或 JSON 模式）
    const detailPanel = page.locator('text=结构化详情').first()
    await expect(detailPanel).toBeVisible({ timeout: 5000 })
  })

  test('parameter 段落：slot chip 区域展示绑定状态', async ({ authedPage }) => {
    const page = authedPage
    // 筛选 parameter 类型
    const paramFilter = page.locator('.ant-radio-button-wrapper:has-text("参数"), .ant-radio-button-wrapper:has-text("parameter")').first()
    if (!(await paramFilter.count())) {
      test.skip(true, '无类型筛选，跳过')
    }
    await paramFilter.click()
    await page.waitForTimeout(400)

    const paramPara = page.locator('.paragraph').first()
    if (!(await paramPara.count())) {
      test.skip(true, '无 parameter 段落')
    }
    await paramPara.click()
    await page.waitForTimeout(400)

    // slot chip 区域或"未生成泛化模板"空状态二者必有其一
    const slotOrEmpty = page.locator('text=Slot, text=泛化模板, text=未生成泛化模板')
    await expect(slotOrEmpty.first()).toBeVisible({ timeout: 5000 })
  })

  test('JSON 编辑模式可切换', async ({ authedPage }) => {
    const page = authedPage
    const firstPara = page.locator('.paragraph').first()
    if (!(await firstPara.count())) {
      test.skip(true, '无段落')
    }
    await firstPara.click()
    await page.waitForTimeout(400)

    // 找 JSON 开关
    const jsonSwitch = page.locator('.ant-switch').first()
    if (!(await jsonSwitch.count())) {
      test.skip(true, '无 JSON 开关')
    }
    await jsonSwitch.click()
    await page.waitForTimeout(300)
    // 应出现 JSON 文本框
    await expect(page.locator('text=JSON, textarea').first()).toBeVisible({ timeout: 5000 })
  })
})
