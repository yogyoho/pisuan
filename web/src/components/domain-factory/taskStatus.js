// 通用域数据加工任务状态语义（文案 + 状态点颜色）单一来源，供数据源列表与归属列表共用
export const statusMap = {
  UPLOADED: { color: 'var(--gray-400)', text: '已上传' },
  PARSING: { color: 'var(--main-color)', text: '解析中' },
  EXTRACTING: {
    color: '#722ed1',
    text: '提取中'
  } /* [pisuan-custom] 青云素雅：一次性装饰色（状态点缀），不随主题 */,
  GENERALIZING: {
    color: '#722ed1',
    text: '泛化中'
  } /* [pisuan-custom] 青云素雅：一次性装饰色（状态点缀），不随主题 */,
  WAITING_REVIEW: { color: 'var(--color-warning-500)', text: '待校验' },
  INGESTING: { color: 'var(--color-info-500)', text: '入库中' },
  COMMITTED: { color: 'var(--color-success-500)', text: '已入库' },
  COMMIT_FAILED: { color: 'var(--color-error-500)', text: '入库失败' },
  COMMIT_PARTIAL: { color: 'var(--color-warning-500)', text: '部分入库' },
  FAILED: { color: 'var(--color-error-500)', text: '失败' }
}

// EIA dot 配方：6px 圆点 + 3px 同色光环；灰色（无状态语义）不给光环
export const dotStyle = (status) => {
  const color = statusMap[status]?.color || 'var(--gray-400)'
  if (color === 'var(--gray-400)') return { backgroundColor: color }
  return {
    backgroundColor: color,
    boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 18%, transparent)`
  }
}
