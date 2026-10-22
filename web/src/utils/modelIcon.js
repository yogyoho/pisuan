const ICON_BASE = '/providers-logo' /* [pisuan-custom] 工程内置 logo，见 web/public/providers-logo */
const WHITE_ICON_FILTER = 'brightness(0) invert(1)'

const avatar = (icon, background, scale = 0.75, filter = WHITE_ICON_FILTER) => ({
  icon: `${ICON_BASE}/${icon}.svg`,
  background,
  scale,
  filter
})

export const modelAvatars = {
  default: avatar('default', 'var(--gray-100)', 0.72, 'none'),
  alibaba: avatar('alibaba', '#ff6003', 0.8), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'alibaba-cn': avatar('bailian-color', '#fff', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'alibaba-coding-plan': avatar('alibabacloud', '#ff6a00', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'alibaba-coding-plan-cn': avatar('alibabacloud', '#ff6a00', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  anthropic: avatar('anthropic', '#f1f0e8', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  ark: avatar('volcengine-color', '#fff', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  dashscope: avatar('bailian-color', '#fff', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  deepseek: avatar('deepseek', '#4d6bfe'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  fluxionai: {
    icon: '/providers-logo/fluxionai.jpeg',
    background: '#fff', /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
    scale: 1,
    filter: 'none'
  },
  google: avatar('google-color', '#fff', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  minimax: avatar('minimax', 'linear-gradient(to right, #e2167e, #fe603c)'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'minimax-cn': avatar('minimax', 'linear-gradient(to right, #e2167e, #fe603c)'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  modelscope: avatar('modelscope', '#624aff'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  moonshotai: avatar('moonshot', '#16191e'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'moonshotai-cn': avatar('moonshot', '#16191e'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  opencode: avatar('opencode', '#000'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'opencode-go': avatar('opencode', '#000'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  openai: avatar('openai-completions', '#000'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  ollama: avatar('ollama', '#000', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  openrouter: avatar(
    'openrouter',
    '#000', /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
    0.75,
    'brightness(0) saturate(100%) invert(94%) sepia(94%) saturate(1636%) hue-rotate(24deg) brightness(105%) contrast(106%)'
  ),
  siliconflow: avatar('siliconcloud', '#6e29f6', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'siliconflow-cn': avatar('siliconcloud', '#6e29f6', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  together: avatar('together', '#fff', 0.75, 'none'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'kimi-for-coding': avatar('moonshot', '#16191e'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  xiaomi: avatar('xiaomimimo', '#000', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'xiaomi-token-plan-cn': avatar('xiaomimimo', '#000', 0.7), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  zai: avatar('zai', '#000', 0.6), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'zai-coding-plan': avatar('zai', '#000', 0.6), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  zhipu: avatar('zhipu-code-plan', '#3859ff'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  zhipuai: avatar('zhipu-code-plan', '#3859ff'), /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
  'zhipuai-coding-plan': avatar('zhipu-code-plan', '#3859ff') /* [pisuan-custom] 青云素雅：品牌色，不随主题 */
}
