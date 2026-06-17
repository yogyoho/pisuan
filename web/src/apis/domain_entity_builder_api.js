import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'

const buildQuery = (params) => {
  const filtered = Object.entries(params).filter(([_, v]) => v != null && v !== '')
  if (filtered.length === 0) return ''
  return '?' + new URLSearchParams(filtered).toString()
}

export const domainEntityBuilderApi = {
  getTaxonomy: (domainCode = null) => {
    const query = buildQuery(domainCode ? { domain_code: domainCode } : {})
    return apiAdminGet('/api/domain-entity-builder/taxonomy' + query)
  },

  listDomains: () => {
    return apiAdminGet('/api/domain-entity-builder/domains')
  },

  listEntitySchemas: (category = null, domainCode = null) => {
    const params = {}
    if (category) params.category = category
    if (domainCode) params.domain_code = domainCode
    const query = buildQuery(params)
    return apiAdminGet('/api/domain-entity-builder/entities' + query)
  },

  getEntitySchema: (entityId) => {
    return apiAdminGet(`/api/domain-entity-builder/entities/${entityId}`)
  },

  createEntitySchema: (entityData) => {
    return apiAdminPost('/api/domain-entity-builder/entities', entityData)
  },

  updateEntitySchema: (entityId, entityData) => {
    return apiAdminPut(`/api/domain-entity-builder/entities/${entityId}`, entityData)
  },

  deleteEntitySchema: (entityId) => {
    return apiAdminDelete(`/api/domain-entity-builder/entities/${entityId}`)
  },

  batchDeleteEntities: (identifiers) => {
    return apiAdminPost('/api/domain-entity-builder/entities/batch-delete', { identifiers })
  },

  cloneEntity: (entityId, entityKey, nameCn) => {
    return apiAdminPost(`/api/domain-entity-builder/entities/${entityId}/clone`, {
      entity_key: entityKey,
      name_cn: nameCn
    })
  },

  exportConfig: (domainCode = null) => {
    const query = buildQuery(domainCode ? { domain_code: domainCode } : {})
    return apiAdminGet('/api/domain-entity-builder/export' + query)
  },

  importConfig: (configData) => {
    return apiAdminPost('/api/domain-entity-builder/import', configData)
  },

  extractEntities: (file, domainCode) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('domain_code', domainCode)
    return apiAdminPost('/api/domain-entity-builder/extract', formData, {})
  },

  importExtractedEntities: (entities, domainCode) => {
    return apiAdminPost('/api/domain-entity-builder/entities/import-extracted', {
      entities, domain_code: domainCode
    })
  }
}
