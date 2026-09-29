/**
 * Chart Color Palette Utility
 * 统一的图表调色盘工具函数
 * 从 CSS 变量中动态获取颜色，确保与主题保持一致
 *
 * 主题承载常量：运行时颜色以 base.css 的 --chart-palette-* / --main-* /
 * --color-*-500 变量为准（换肤只需改 base.css）；下方文件内所有 hex 均为
 * 变量缺失时的 fallback 常量，换肤时须与 base.css 同步更新，请勿在页面样式中直接引用。
 */

let colorPalette = []
let isInitialized = false

/**
 * Build color palette from CSS variables in base.css
 * 从 base.css 中的 CSS 变量构建调色盘
 */
const buildColorPalette = () => {
  try {
    const root = document.documentElement
    const styles = getComputedStyle(root)

    const pick = (name, fallback) => {
      const v = styles.getPropertyValue(name)
      return v && v.trim() ? v.trim() : fallback
    }

    // Base chart colors - Ant Design 拂晓蓝主题
    const baseVars = [
      ['--main-500', '#6366f1'],
      ['--color-success-500', '#52c41a'],
      ['--color-warning-500', '#faad14'],
      ['--color-error-500', '#ff4d4f'],
      ['--color-accent-500', '#13c2c2']
    ]

    // Extended palette colors - 从 know 项目导入
    const paletteVars = [
      ['--chart-palette-1', '#4f46e5'],
      ['--chart-palette-2', '#0ea5e9'],
      ['--chart-palette-3', '#8b5cf6'],
      ['--chart-palette-4', '#14b8a6'],
      ['--chart-palette-5', '#f59e0b'],
      ['--chart-palette-6', '#f43f5e'],
      ['--chart-palette-7', '#06b6d4'],
      ['--chart-palette-8', '#10b981'],
      ['--chart-palette-9', '#d946ef'],
      ['--chart-palette-10', '#64748b']
    ]

    const baseColors = baseVars.map(([n, f]) => pick(n, f))
    const paletteColors = paletteVars.map(([n, f]) => pick(n, f))

    // Priority: palette first, then base colors
    const merged = [...paletteColors, ...baseColors]
      .filter(Boolean)
      .filter((c, idx, arr) => arr.indexOf(c) === idx) // Remove duplicates

    colorPalette = merged
    isInitialized = true
  } catch (e) {
    console.warn('Failed to build color palette from CSS variables, using fallback:', e)
    // Fallback palette - 青云靛蓝锚点环
    colorPalette = [
      '#4f46e5',
      '#52c41a',
      '#faad14',
      '#ff4d4f',
      '#13c2c2',
      '#0ea5e9',
      '#8b5cf6',
      '#14b8a6',
      '#f59e0b',
      '#f43f5e'
    ]
    isInitialized = true
  }
}

/**
 * Get color by index from the palette
 * 根据索引从调色盘中获取颜色
 * @param {number} index - Color index
 * @returns {string} Color value
 */
export const getColorByIndex = (index) => {
  if (!isInitialized || colorPalette.length === 0) {
    buildColorPalette()
  }
  return colorPalette[index % colorPalette.length]
}

/**
 * Get the entire color palette
 * 获取完整的调色盘
 * @returns {Array<string>} Color palette array
 */
export const getColorPalette = () => {
  if (!isInitialized || colorPalette.length === 0) {
    buildColorPalette()
  }
  return [...colorPalette] // Return a copy
}

/**
 * Truncate legend text for better display
 * 截断图例文本以便更好地显示
 * @param {string} name - Legend name
 * @param {number} maxLength - Maximum length (default: 20)
 * @returns {string} Truncated name
 */
export const truncateLegend = (name, maxLength = 20) => {
  if (!name) return ''
  return name.length > maxLength ? name.slice(0, maxLength) + '…' : name
}

/**
 * Initialize the color palette (call this when DOM is ready)
 * 初始化调色盘（在 DOM 准备好时调用）
 */
export const initColorPalette = () => {
  buildColorPalette()
}

// Auto-initialize when module is loaded
if (typeof window !== 'undefined' && document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initColorPalette)
} else if (typeof window !== 'undefined') {
  initColorPalette()
}
