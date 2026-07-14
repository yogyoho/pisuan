<template>
  <div class="outline-template">
    <div class="ot-main-content">
      <!-- 左侧: 章节列表 -->
      <div class="ot-left-panel">
        <div class="ot-panel-header">
          <span class="ot-panel-title">章节列表</span>
          <a-button size="small" @click="loadList" :loading="loadingList">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </div>
        <div class="ot-chapter-list">
          <a-spin :spinning="loadingList">
            <div
              v-for="item in chapterList"
              :key="item.key"
              class="ot-chapter-item"
              :class="{ active: item.key === selectedKey }"
              @click="selectChapter(item.key)"
            >
              <span class="ot-chapter-order">{{ item.order }}</span>
              <span class="ot-chapter-title">{{ item.title }}</span>
              <span v-if="item.content_contract_summary" class="ot-cc-badge">
                {{ item.content_contract_summary.total_reports }}报告
              </span>
            </div>
          </a-spin>
        </div>
      </div>

      <!-- 右侧: 章节详情编辑器 -->
      <div class="ot-right-panel">
        <div v-if="!detail" class="ot-empty-state">
          <a-empty description="请从左侧选择章节进行编辑" />
        </div>

        <div v-else class="ot-editor">
          <!-- 基础信息 -->
          <a-card title="基础信息" size="small" class="ot-editor-section">
            <a-form :model="detail" layout="vertical">
              <a-form-item label="编写目的">
                <a-textarea
                  v-model:value="detail.purpose"
                  :rows="3"
                  placeholder="本章在环评报告中的作用与编写目的"
                />
              </a-form-item>

              <a-form-item label="提取关键字">
                <a-select
                  v-model:value="detail.key_points"
                  mode="tags"
                  style="width: 100%"
                  placeholder="输入关键字后回车"
                />
              </a-form-item>

              <a-form-item label="提取正则表达式">
                <a-input
                  v-model:value="detail.extraction_regex"
                  placeholder="用于从报告中提取该章节内容的正则表达式"
                />
              </a-form-item>
            </a-form>
          </a-card>

          <!-- 内容契约 -->
          <a-card v-if="detail.content_contract" title="内容契约" size="small" class="ot-editor-section">
            <div class="ot-contract">
              <div class="ot-contract-row">
                <span class="ot-contract-label">必写要素 ({{ requiredElements.length }}):</span>
                <a-tag v-for="el in requiredElements" :key="el" color="green">{{ el }}</a-tag>
              </div>
              <div class="ot-contract-row">
                <span class="ot-contract-label">可选要素 ({{ optionalElements.length }}):</span>
                <a-tag v-for="el in optionalElements" :key="el" color="orange">{{ el }}</a-tag>
              </div>
              <div class="ot-contract-row">
                <span class="ot-contract-label">贡献报告数:</span>
                <span>{{ detail.content_contract.total_reports || 0 }}</span>
              </div>
            </div>
          </a-card>

          <!-- 编写提示 -->
          <a-card title="编写提示" size="small" class="ot-editor-section">
            <a-form :model="detail" layout="vertical">
              <a-form-item label="编写提示词">
                <a-textarea
                  v-model:value="detail.writing_hints"
                  :rows="4"
                  placeholder="本章专属写作提示"
                />
              </a-form-item>

              <a-form-item label="法规标准引用">
                <a-select
                  v-model:value="detail.regulations"
                  mode="tags"
                  style="width: 100%"
                  placeholder="输入法规标准后回车"
                />
              </a-form-item>

              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="预期表格">
                    <a-select
                      v-model:value="detail.expected_tables"
                      mode="tags"
                      style="width: 100%"
                      placeholder="表格清单"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="预期图表">
                    <a-select
                      v-model:value="detail.expected_charts"
                      mode="tags"
                      style="width: 100%"
                      placeholder="图表清单"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="预期公式">
                    <a-select
                      v-model:value="detail.expected_formulas"
                      mode="tags"
                      style="width: 100%"
                      placeholder="公式清单"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-form>
          </a-card>

          <!-- 子章节结构 -->
          <a-card v-if="detail.child_chapters && detail.child_chapters.length" title="子章节结构" size="small" class="ot-editor-section">
            <div class="ot-children">
              <div v-for="child in detail.child_chapters" :key="child.key" class="ot-child-item">
                <span class="ot-child-title">{{ child.title }}</span>
                <span class="ot-child-key">{{ child.key }}</span>
              </div>
            </div>
          </a-card>

          <!-- 操作按钮 -->
          <div class="ot-editor-actions">
            <a-space>
              <a-button type="primary" @click="handleSave" :loading="saving" :disabled="!selectedKey">
                <template #icon><SaveOutlined /></template>
                保存
              </a-button>
            </a-space>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const loadingList = ref(false)
const loadingDetail = ref(false)
const saving = ref(false)
const chapterList = ref([])
const selectedKey = ref('')
const detail = ref(null)

const requiredElements = computed(() => {
  const cc = detail.value?.content_contract
  if (!cc) return []
  if (Array.isArray(cc)) return cc
  return cc.required_elements || []
})

const optionalElements = computed(() => {
  const cc = detail.value?.content_contract
  if (!cc || Array.isArray(cc)) return []
  return cc.optional_elements || []
})

const loadList = async () => {
  loadingList.value = true
  try {
    const res = await domainFactoryApi.getOutlineTemplates({ domain: 'coal', report_type: 'eia_report' })
    chapterList.value = res?.items || []
    if (chapterList.value.length && !selectedKey.value) {
      selectChapter(chapterList.value[0].key)
    }
  } catch {
    message.error('加载大纲模板列表失败')
  } finally {
    loadingList.value = false
  }
}

const selectChapter = async (key) => {
  selectedKey.value = key
  loadingDetail.value = true
  try {
    const res = await domainFactoryApi.getOutlineTemplate(key, { domain: 'coal', report_type: 'eia_report' })
    // 确保可编辑字段有默认值
    detail.value = {
      ...res,
      key_points: res.key_points || [],
      regulations: res.regulations || [],
      expected_tables: res.expected_tables || [],
      expected_charts: res.expected_charts || [],
      expected_formulas: res.expected_formulas || [],
      extraction_regex: res.extraction_regex || '',
    }
  } catch {
    message.error('加载章节详情失败')
    detail.value = null
  } finally {
    loadingDetail.value = false
  }
}

const handleSave = async () => {
  if (!selectedKey.value || !detail.value) return
  saving.value = true
  try {
    const payload = {
      purpose: detail.value.purpose || '',
      key_points: detail.value.key_points || [],
      writing_hints: detail.value.writing_hints || '',
      regulations: detail.value.regulations || [],
      extraction_regex: detail.value.extraction_regex || '',
      expected_tables: detail.value.expected_tables || [],
      expected_charts: detail.value.expected_charts || [],
      expected_formulas: detail.value.expected_formulas || [],
    }
    await domainFactoryApi.updateOutlineTemplate(selectedKey.value, payload)
    message.success('大纲模板保存成功')
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped lang="less">
.outline-template {
  height: 100%;
}

.ot-main-content {
  display: flex;
  gap: 16px;
  height: calc(100vh - 200px);
}

// ---- Left panel ----
.ot-left-panel {
  width: 280px;
  flex-shrink: 0;
  background: var(--gray-0);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .ot-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid var(--gray-100);
  }

  .ot-panel-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-900);
  }

  .ot-chapter-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
}

.ot-chapter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;

  &:hover {
    background: var(--gray-50);
  }

  &.active {
    background: var(--main-20);
    color: var(--main-color);
    font-weight: 500;

    .ot-chapter-order {
      background: var(--main-color);
      color: #fff;
    }
  }
}

.ot-chapter-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  border-radius: 4px;
  background: var(--gray-100);
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  color: var(--gray-600);
}

.ot-chapter-title {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gray-700);
}

.ot-chapter-item.active .ot-chapter-title {
  color: var(--main-color);
}

.ot-cc-badge {
  font-size: 11px;
  color: var(--gray-400);
  flex-shrink: 0;
}

// ---- Right panel ----
.ot-right-panel {
  flex: 1;
  background: var(--gray-0);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  overflow-y: auto;
  padding: 24px;

  .ot-empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
  }
}

.ot-editor {
  .ot-editor-section {
    margin-bottom: 20px;
  }

  .ot-editor-actions {
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid var(--gray-200);
  }
}

// ---- Content sections ----
.ot-contract {
  .ot-contract-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 8px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .ot-contract-label {
    font-weight: 500;
    font-size: 13px;
    color: var(--gray-600);
    margin-right: 4px;
  }
}

.ot-children {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ot-child-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--gray-50);
  border: 1px solid var(--gray-100);
  border-radius: 6px;

  .ot-child-title {
    font-size: 13px;
    color: var(--gray-700);
    font-weight: 500;
  }

  .ot-child-key {
    font-size: 12px;
    color: var(--gray-400);
    font-family: monospace;
  }
}
</style>
