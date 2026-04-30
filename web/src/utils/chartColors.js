/**
 * Chart Color Palette Utility
 * 统一的图表调色盘工具函数
 * 从 CSS 变量中动态获取颜色，确保与主题保持一致
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
      ['--main-500', '#40a9ff'],
      ['--color-success-500', '#52c41a'],
      ['--color-warning-500', '#faad14'],
      ['--color-error-500', '#ff4d4f'],
      ['--color-accent-500', '#13c2c2']
    ]

    // Extended palette colors - 从 know 项目导入
    const paletteVars = [
      ['--chart-palette-1', '#40a9ff'],
      ['--chart-palette-2', '#11cbe3'],
      ['--chart-palette-3', '#00b8a9'],
      ['--chart-palette-4', '#f2c94c'],
      ['--chart-palette-5', '#eb5757'],
      ['--chart-palette-6', '#2f80ed'],
      ['--chart-palette-7', '#9b51e0'],
      ['--chart-palette-8', '#56ccf2'],
      ['--chart-palette-9', '#6fcf97'],
      ['--chart-palette-10', '#333333']
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
    // Fallback palette - Ant Design 拂晓蓝
    colorPalette = [
      '#40a9ff',
      '#52c41a',
      '#faad14',
      '#ff4d4f',
      '#13c2c2',
      '#11cbe3',
      '#00b8a9',
      '#f2c94c',
      '#eb5757',
      '#2f80ed'
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
