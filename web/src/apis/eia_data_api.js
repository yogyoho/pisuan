/**
 * EIA Data Factory API
 * 环评域数据工厂（coal-eia-writer 技能数据加工与管理）相关接口
 */

import { apiDelete, apiGet, apiPatch, apiPost, apiRequest } from './base'

export const eiaDataApi = {
  /**
   * 技能数据集统计总览（只读聚合技能语料文件，无 DB 依赖）。
   * 后端按源文件 mtime 指纹缓存，语料未变时近似零开销。
   */
  getSkillStats: () => apiGet('/api/domain-factory/eia/stats'),

  /**
   * unmapped 池明细（只读）：per-stage 未归并量词短语，词表口径 label 扩充素材。
   * stage 缺省返回全部阶段。
   */
  getUnmapped: (stage) =>
    apiGet(
      `/api/domain-factory/eia/expectations/unmapped${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`
    ),

  /**
   * 节级明细只读视图（P2-2）：节键自然序展平（key/title/quantities）+ unmapped 附带。
   */
  getSections: (stage) =>
    apiGet(`/api/domain-factory/eia/expectations/sections?stage=${encodeURIComponent(stage)}`),

  /**
   * 备料清单只读视图（P2-4）：per_chapter 分章数据族 + source_hint 词表。
   */
  getDataExpectations: () => apiGet('/api/domain-factory/eia/expectations/data'),

  /**
   * 三数据集只读抽屉通道（P3-3）：key ∈ attachment_checklist / consistency_contracts / depth_targets。
   */
  getDatasetView: (key) =>
    apiGet(`/api/domain-factory/eia/datasets/${encodeURIComponent(key)}/view`),

  // ── 环评文件库（P1：上传即登记；加工属 P2 显式触发）──

  listLibraryFolders: () => apiGet('/api/domain-factory/eia/library/folders'),

  listLibraryFiles: (folderId, q, uncategorized) => {
    const params = new URLSearchParams()
    if (folderId != null) params.set('folder_id', String(folderId))
    if (uncategorized) params.set('uncategorized', '1')
    if (q) params.set('q', q)
    const qs = params.toString()
    return apiGet(`/api/domain-factory/eia/library/files${qs ? `?${qs}` : ''}`)
  },

  uploadLibraryFile: (file, folderId) => {
    const form = new FormData()
    form.append('file', file)
    if (folderId != null) form.append('folder_id', String(folderId))
    return apiPost('/api/domain-factory/eia/library/files', form)
  },

  downloadLibraryFile: (id) =>
    apiRequest(`/api/domain-factory/eia/library/files/${id}/download`, {}, true, 'blob'),

  moveLibraryFile: (id, folderId) =>
    apiPatch(`/api/domain-factory/eia/library/files/${id}`, { folder_id: folderId }),

  deleteLibraryFile: (id) => apiDelete(`/api/domain-factory/eia/library/files/${id}`),

  // —— P2 canonical md 正源（spec 2026-10-18 方案 B）——
  getCorpusKbBinding: () => apiGet('/api/domain-factory/eia/library/kb/binding'),
  bindCorpusKb: (kbId) => apiPost('/api/domain-factory/eia/library/kb/bind', { kb_id: kbId }),
  getFileMd: (id) =>
    apiRequest(`/api/domain-factory/eia/library/files/${id}/md`, { method: 'POST' }, true, 'text'),
  regenerateMd: (id) => apiPost(`/api/domain-factory/eia/library/files/${id}/regenerate-md`),
  updateFileMeta: (id, fields) =>
    apiPatch(`/api/domain-factory/eia/library/files/${id}/meta`, fields),
  pushToKb: (fileIds) => apiPost('/api/domain-factory/eia/library/push-kb', { file_ids: fileIds }),
  processCorpus: (payload) => apiPost('/api/domain-factory/eia/library/process', payload),
  bootstrapManifest: (file) => {
    const form = new FormData()
    form.append('file', file)
    return apiPost('/api/domain-factory/eia/library/admin/bootstrap-manifest', form)
  },
  migrateStorage: () => apiPost('/api/domain-factory/eia/library/admin/migrate-storage')
}
