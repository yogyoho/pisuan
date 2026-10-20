/**
 * Regulation Library API
 * 标准与限值库权威指标（standard_indicators）核验 + 专家手工标准接口（W1 契约，admin）。
 *
 * 错误提示须透出后端业务 detail（FastAPI 字符串 detail，如「编号已存在」「检测到手工行，
 * 拒绝覆盖」）；apis/base.js 对非 422 响应会把 detail 折叠为公共文案，故本文件自行请求
 * 以保留 detail（仅本组端点，不扩散）。
 */
import { useUserStore, checkAdminPermission } from '@/stores/user'

async function regRequest(url, options = {}) {
  checkAdminPermission()
  const userStore = useUserStore()
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...userStore.getAuthHeaders(),
      ...options.headers
    }
  })
  if (!response.ok) {
    let detail = ''
    try {
      detail = (await response.json())?.detail ?? ''
    } catch {
      // 非 JSON 错误体：回退状态码文案
    }
    if (Array.isArray(detail)) detail = '请求参数验证失败'
    const error = new Error(detail || `请求失败: ${response.status}`)
    error.status = response.status
    throw error
  }
  return response.json()
}

const enc = encodeURIComponent

export const regulationLibraryApi = {
  /** 权威指标行全集（enrich + expert）：{ items: [...], total } */
  getIndicators: () => regRequest('/api/regulation-library/indicators'),

  /** 表单元核验：{doc_code, unit_no} → {updated} */
  verifyUnit: (docCode, unitNo) =>
    regRequest('/api/regulation-library/indicators/verify', {
      method: 'POST',
      body: JSON.stringify({ doc_code: docCode, unit_no: unitNo })
    }),

  /** 撤销核验（回退为待核验）：{doc_code, unit_no} → {updated} */
  unverifyUnit: (docCode, unitNo) =>
    regRequest('/api/regulation-library/indicators/unverify', {
      method: 'POST',
      body: JSON.stringify({ doc_code: docCode, unit_no: unitNo })
    }),

  /** 新建手工标准（保存即核验，unit_no='手录'）：409=编号已存在，400=行校验失败（行≤500） */
  createManualStandard: (payload) =>
    regRequest('/api/regulation-library/manual-standards', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  /** 整标准行替换（仅 source='expert' 行）：409=非 expert 行 */
  updateManualStandard: (docCode, payload) =>
    regRequest(`/api/regulation-library/manual-standards/${enc(docCode)}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  /** 删除手工标准全部行（仅 source='expert' 行）：409=非 expert 行 */
  deleteManualStandard: (docCode) =>
    regRequest(`/api/regulation-library/manual-standards/${enc(docCode)}`, {
      method: 'DELETE'
    })
}
