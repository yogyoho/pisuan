<template>
  <div class="main-content">
    <!-- 左侧: 章节列表 -->
    <div class="left-panel">
      <div class="scope-bar">
        <a-select
          v-model:value="selectedDomain"
          placeholder="业务领域"
          style="flex: 1"
          @change="onDomainChange"
        >
          <a-select-option v-for="d in domains" :key="d.code" :value="d.code">{{ d.name }}</a-select-option>
        </a-select>
        <a-select
          v-model:value="selectedReportType"
          placeholder="报告类型"
          style="flex: 1"
          :disabled="!reportTypeOptions.length"
          @change="loadList"
        >
          <a-select-option v-for="rt in reportTypeOptions" :key="rt.code" :value="rt.code">{{ rt.name }}</a-select-option>
        </a-select>
        <a-tooltip title="为标准章节生成提取正则">
          <a-button :loading="generatingRegex" @click="handleGenerateRegex">
            <template #icon><ToolOutlined /></template>
          </a-button>
        </a-tooltip>
      </div>
      <div class="panel-header">
        <a-input
          v-model:value="searchKeyword"
          placeholder="搜索章节..."
          allow-clear
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
      </div>
      <div class="chapter-list">
        <a-spin :spinning="loadingList">
          <div v-if="visibleNodes.length" class="chapter-tree">
            <div
              v-for="node in visibleNodes"
              :key="node.key"
              class="tree-node"
              :class="{ active: node.key === selectedKey }"
              :style="{ paddingLeft: 8 + node._level * 16 + 'px' }"
              @click="selectChapter(node.key)"
            >
              <span
                v-if="node.children && node.children.length"
                class="node-toggle"
                @click.stop="toggleExpand(node.key)"
              >
                <DownOutlined v-if="isExpanded(node.key)" />
                <RightOutlined v-else />
              </span>
              <span v-else class="node-toggle node-toggle-leaf"></span>
              <span v-if="node._level === 0 && node.order" class="node-order">{{ node.order }}</span>
              <span class="node-title">{{ node.title }}</span>
              <span v-if="node.content_contract_summary?.total_reports" class="cc-badge">
                {{ node.content_contract_summary.total_reports }}报告
              </span>
            </div>
          </div>
          <a-empty v-if="!loadingList && visibleNodes.length === 0" description="无匹配章节">
            <a-button
              v-if="!searchKeyword && chapterTree.length === 0"
              type="primary"
              :loading="seeding"
              @click="handleSeed"
            >
              <template #icon><ThunderboltOutlined /></template>
              初始化标准 13 章结构
            </a-button>
          </a-empty>
        </a-spin>
      </div>
    </div>

    <!-- 右侧: 章节详情编辑器 -->
    <div class="right-panel">
      <div class="panel-title">大纲Schema</div>
      <div class="panel-body">
        <div v-if="loadingDetail" class="empty-state">
          <a-spin />
        </div>
        <div v-else-if="!detail" class="empty-state">
          <a-empty description="请从左侧选择章节进行编辑" />
        </div>

        <div v-else class="schema-editor">
        <!-- 基础信息 -->
        <a-card title="基础信息" size="small" class="editor-section">
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
        <a-card v-if="detail.content_contract" title="内容契约" size="small" class="editor-section">
          <div class="contract-box">
            <div class="contract-row">
              <span class="contract-label">必写要素 ({{ requiredElements.length }}):</span>
              <a-tag v-for="el in requiredElements" :key="el" color="green">{{ el }}</a-tag>
            </div>
            <div class="contract-row">
              <span class="contract-label">可选要素 ({{ optionalElements.length }}):</span>
              <a-tag v-for="el in optionalElements" :key="el" color="orange">{{ el }}</a-tag>
            </div>
            <div class="contract-row">
              <span class="contract-label">贡献报告数:</span>
              <span>{{ detail.content_contract.total_reports || 0 }}</span>
            </div>
          </div>
        </a-card>

        <!-- 编写提示 -->
        <a-card title="编写提示" size="small" class="editor-section">
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
        <a-card v-if="detail.child_chapters && detail.child_chapters.length" title="子章节结构" size="small" class="editor-section">
          <div class="children-list">
            <div v-for="child in detail.child_chapters" :key="child.key" class="child-item">
              <span class="child-title">{{ child.title }}</span>
              <span class="child-key">{{ child.key }}</span>
            </div>
          </div>
        </a-card>

        <!-- 操作按钮 -->
        <div class="editor-actions">
          <a-space>
            <a-button type="primary" @click="handleSave" :loading="saving" :disabled="!selectedKey">
              <template #icon><SaveOutlined /></template>
              保存
            </a-button>
            <a-button @click="loadList" :loading="loadingList">
              <template #icon><ReloadOutlined /></template>
              刷新
            </a-button>
          </a-space>
        </div>
        </div>
      </div>
    </div>

    <!-- 大纲提取预览弹窗 -->
    <a-modal
      v-model:open="extractModalVisible"
      title="大纲提取预览"
      width="780px"
      :confirm-loading="confirming"
      ok-text="确认入库"
      cancel-text="取消"
      @ok="handleConfirmOutline"
    >
      <p v-if="extractedChapters.length" class="extract-tip">
        从「{{ extractFileName }}」提取到 {{ extractedChapters.length }} 个章节，可编辑规范名和编写目的后确认入库：
      </p>
      <a-empty v-else description="未提取到章节" />
      <div class="extract-list">
        <div v-for="(ch, idx) in extractedChapters" :key="idx" class="extract-chapter">
          <div class="extract-chapter-head">
            <span class="extract-orig-title">{{ ch.chapter_title }}</span>
            <span class="extract-para-count">{{ ch.paragraph_count }} 段</span>
          </div>
          <a-input v-model:value="ch.canonical_chapter_key" size="small" placeholder="规范章节名" />
          <a-textarea v-model:value="ch.purpose" :rows="2" size="small" placeholder="编写目的" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SaveOutlined, SearchOutlined, ThunderboltOutlined, ToolOutlined, DownOutlined, RightOutlined } from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const loadingList = ref(false)
const loadingDetail = ref(false)
const saving = ref(false)
const seeding = ref(false)
const confirming = ref(false)
const generatingRegex = ref(false)
const extractModalVisible = ref(false)
const extractedChapters = ref([])
const extractFileName = ref('')
const selectedDomain = ref('coal')
const selectedReportType = ref('eia_report')
const domains = ref([])
const reportTypesByDomain = ref({})

const reportTypeOptions = computed(
  () => reportTypesByDomain.value[selectedDomain.value] || []
)
const chapterTree = ref([])
const selectedKey = ref('')
const detail = ref(null)
const searchKeyword = ref('')

const filterTree = (nodes, kw) => {
  if (!kw) return nodes
  const result = []
  for (const n of nodes) {
    const children = filterTree(n.children || [], kw)
    if ((n.title || '').toLowerCase().includes(kw) || (n.key || '').toLowerCase().includes(kw) || children.length) {
      result.push({ ...n, children })
    }
  }
  return result
}

const filteredChapterTree = computed(() =>
  filterTree(chapterTree.value, searchKeyword.value.toLowerCase())
)

const expandedKeys = ref(new Set())

const isExpanded = (key) => expandedKeys.value.has(key)

const toggleExpand = (key) => {
  const s = new Set(expandedKeys.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedKeys.value = s
}

const visibleNodes = computed(() => {
  const tree = filteredChapterTree.value
  const result = []
  // 搜索时全部展开（匹配路径都可见）；否则按 expandedKeys
  const expanded = searchKeyword.value ? null : expandedKeys.value
  const walk = (nodes, level) => {
    for (const n of nodes) {
      result.push({ ...n, _level: level })
      if (n.children && n.children.length && (!expanded || expanded.has(n.key))) {
        walk(n.children, level + 1)
      }
    }
  }
  walk(tree, 0)
  return result
})

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
  selectedKey.value = ''
  detail.value = null
  try {
    const res = await domainFactoryApi.getOutlineTemplates({
      domain: selectedDomain.value,
      report_type: selectedReportType.value,
    })
    chapterTree.value = res?.items || []
    expandedKeys.value = new Set()
    if (chapterTree.value.length) {
      selectChapter(chapterTree.value[0].key)
    }
  } catch {
    message.error('加载大纲模板列表失败')
  } finally {
    loadingList.value = false
  }
}

const loadContexts = async () => {
  try {
    const res = await domainFactoryApi.getContexts()
    domains.value = res?.domains || []
    reportTypesByDomain.value = res?.report_types || {}
    // 当前领域若无报告类型，回退到第一个有数据的领域
    if (!reportTypeOptions.value.length && domains.value.length) {
      selectedDomain.value = domains.value[0].code
    }
    if (!reportTypeOptions.value.some((rt) => rt.code === selectedReportType.value)) {
      selectedReportType.value = reportTypeOptions.value[0]?.code || ''
    }
  } catch {
    message.error('加载领域/报告类型失败')
  }
}

const onDomainChange = () => {
  selectedReportType.value = reportTypeOptions.value[0]?.code || ''
  loadList()
}

const handleSeed = async () => {
  seeding.value = true
  try {
    const res = await domainFactoryApi.seedOutlineTemplates()
    message.success(
      `标准结构初始化完成：${res.chapters} 章 / ${res.subchapters} 子章节 / ${res.content_chapters} 章内容`
    )
    await loadList()
  } catch {
    message.error('标准结构初始化失败')
  } finally {
    seeding.value = false
  }
}

const handleExtract = async (file) => {
  try {
    const res = await domainFactoryApi.extractOutlinePreview(file, {
      domain: selectedDomain.value,
      report_type: selectedReportType.value,
    })
    extractedChapters.value = res?.chapters || []
    extractFileName.value = res?.file_name || file.name
    extractModalVisible.value = true
    message.success(`提取完成：${extractedChapters.value.length} 个章节`)
  } catch {
    message.error('大纲提取失败')
  }
  return false
}

defineExpose({ handleExtract })

const handleConfirmOutline = async () => {
  if (!extractedChapters.value.length) {
    extractModalVisible.value = false
    return
  }
  confirming.value = true
  try {
    const res = await domainFactoryApi.confirmOutlineExtract({
      domain: selectedDomain.value,
      report_type: selectedReportType.value,
      chapters: extractedChapters.value,
      file_name: extractFileName.value,
    })
    message.success(`入库完成：${res.saved} 章（图谱同步 ${res.graph_synced}）`)
    extractModalVisible.value = false
    extractedChapters.value = []
    await loadList()
  } catch {
    message.error('大纲入库失败')
  } finally {
    confirming.value = false
  }
}

const handleGenerateRegex = async () => {
  generatingRegex.value = true
  try {
    const res = await domainFactoryApi.generateExtractionRegex(
      selectedDomain.value,
      selectedReportType.value,
    )
    if (res?.generated) {
      message.success(`提取规则生成完成：${res.generated}/${res.total} 章`)
      if (selectedKey.value) await selectChapter(selectedKey.value)
    } else {
      message.warning(res?.reason || '未生成（可能无标准章节）')
    }
  } catch {
    message.error('提取规则生成失败')
  } finally {
    generatingRegex.value = false
  }
}

const selectChapter = async (key) => {
  selectedKey.value = key
  loadingDetail.value = true
  try {
    const res = await domainFactoryApi.getOutlineTemplate(key, {
      domain: selectedDomain.value,
      report_type: selectedReportType.value,
    })
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

onMounted(async () => {
  await loadContexts()
  await loadList()
})
</script>

<style scoped lang="less">
.main-content {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.left-panel {
  width: 340px;
  background: var(--gray-0);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  display: flex;
  flex-direction: column;

  .panel-header {
    margin-bottom: 16px;
  }

  .chapter-list {
    flex: 1;
    overflow-y: auto;
  }
}

.chapter-tree {
  .tree-node {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
      background: var(--gray-50);
    }

    &.active {
      background: rgba(24, 144, 255, 0.1);
    }

    .node-toggle {
      width: 16px;
      flex-shrink: 0;
      font-size: 11px;
      color: var(--gray-500);
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    .node-toggle-leaf {
      visibility: hidden;
    }

    .node-title {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
    }

    .node-order {
      flex-shrink: 0;
      min-width: 18px;
      font-size: 13px;
      font-weight: 600;
      color: var(--main-color, #1890ff);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
  }
}

.chapter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: var(--gray-50);
  }

  &.active {
    background: var(--main-color-light, #e6f7ff);
    color: var(--main-color, #1890ff);
    font-weight: 500;
  }
}

.chapter-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: var(--gray-100);
  font-size: 12px;
  flex-shrink: 0;
}

.chapter-item.active .chapter-order {
  background: var(--main-color, #1890ff);
  color: white;
}

.chapter-title {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cc-badge {
  font-size: 11px;
  color: var(--gray-600);
  flex-shrink: 0;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  overflow: hidden;

  .panel-title {
    flex-shrink: 0;
    padding: 14px 20px;
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-1000);
    border-bottom: 1px solid var(--gray-200);
  }

  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
  }

  .schema-editor {
    .editor-section {
      margin-bottom: 24px;
    }

    .contract-box {
      background: var(--gray-50);
      border-radius: 6px;
      padding: 12px;
    }

    .contract-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 4px;
      margin-bottom: 8px;

      &:last-child {
        margin-bottom: 0;
      }
    }

    .contract-label {
      font-weight: 500;
      margin-right: 4px;
    }

    .children-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .child-item {
      display: flex;
      justify-content: space-between;
      padding: 6px 12px;
      background: var(--gray-50);
      border-radius: 4px;
    }

    .child-title {
      font-size: 13px;
    }

    .child-key {
      font-size: 12px;
      color: var(--gray-600);
    }

    .editor-actions {
      margin-top: 24px;
      padding-top: 24px;
      border-top: 1px solid var(--gray-200);
    }
  }
}

.extract-tip {
  margin-bottom: 12px;
  color: var(--text-secondary, #666);
}

.scope-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.extract-list {
  max-height: 480px;
  overflow-y: auto;
}

.extract-chapter {
  padding: 10px;
  margin-bottom: 10px;
  background: var(--gray-50, #fafafa);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.extract-chapter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.extract-orig-title {
  font-weight: 500;
  font-size: 13px;
}

.extract-para-count {
  font-size: 12px;
  color: var(--text-secondary, #999);
}
</style>
