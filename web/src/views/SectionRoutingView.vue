<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  UploadOutlined,
  DownloadOutlined,
  ReloadOutlined,
  FolderOutlined,
  CodeOutlined,
  SettingOutlined
} from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const router = useRouter()

// 状态
const loading = ref(false)
const saving = ref(false)
const selectedDomain = ref('')
const selectedReportType = ref('')
const sectionTree = ref([])
const selectedSection = ref(null)
const showSectionModal = ref(false)
const editingSection = ref(null)
const showRuleDrawer = ref(false)
const editingRule = ref({})

// 选项
const domains = ref([
  { value: 'coal', label: '煤炭采选业' },
  { value: 'chem', label: '石油化工业' },
  { value: 'transport', label: '交通运输业' }
])

const reportTypes = ref([
  { value: 'eia', label: '环境影响评价报告' },
  { value: 'feasibility', label: '可行性研究报告' }
])

// 表单数据
const sectionForm = ref({
  code: '',
  title: '',
  section_path: '',
  level: 1,
  standard_code: '',
  parent_id: null
})

// 获取章节树
const fetchSectionTree = async () => {
  if (!selectedDomain.value || !selectedReportType.value) {
    sectionTree.value = []
    return
  }

  loading.value = true
  try {
    const res = await domainFactoryApi.getSectionTree(selectedDomain.value, selectedReportType.value)
    sectionTree.value = res?.sections || []
  } catch (e) {
    console.error('获取章节树失败:', e)
    message.error('获取章节树失败')
  } finally {
    loading.value = false
  }
}

// 保存章节树
const handleSave = async () => {
  if (!selectedDomain.value || !selectedReportType.value) {
    message.warning('请选择领域和报告类型')
    return
  }

  saving.value = true
  try {
    await domainFactoryApi.updateContextSections(
      selectedDomain.value,
      selectedReportType.value,
      sectionTree.value
    )
    message.success('保存成功')
  } catch (e) {
    console.error('保存失败:', e)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 添加章节
const handleAddSection = (parent = null, level = 1) => {
  editingSection.value = null
  sectionForm.value = {
    code: '',
    title: '',
    section_path: '',
    level: level,
    standard_code: '',
    parent_id: parent?.id || null
  }
  showSectionModal.value = true
}

// 编辑章节
const handleEditSection = (section) => {
  editingSection.value = section
  sectionForm.value = {
    code: section.code || '',
    title: section.title || '',
    section_path: section.section_path || '',
    level: section.level || 1,
    standard_code: section.standard_code || '',
    parent_id: section.parent_id || null
  }
  showSectionModal.value = true
}

// 保存章节
const handleSaveSection = () => {
  if (!sectionForm.value.title) {
    message.warning('请输入章节标题')
    return
  }

  const newSection = {
    code: sectionForm.value.code || `SEC_${Date.now()}`,
    title: sectionForm.value.title,
    section_path: sectionForm.value.section_path,
    level: sectionForm.value.level,
    standard_code: sectionForm.value.standard_code || null,
    children: []
  }

  if (editingSection.value) {
    // 更新现有章节
    const updateSection = (sections) => {
      for (let i = 0; i < sections.length; i++) {
        if (sections[i].code === editingSection.value.code) {
          sections[i] = { ...sections[i], ...newSection }
          return true
        }
        if (sections[i].children && updateSection(sections[i].children)) {
          return true
        }
      }
      return false
    }
    updateSection(sectionTree.value)
  } else {
    // 添加新章节
    sectionTree.value.push(newSection)
  }

  showSectionModal.value = false
}

// 删除章节
const handleDeleteSection = (section) => {
  const removeSection = (sections) => {
    const index = sections.findIndex(s => s.code === section.code)
    if (index !== -1) {
      sections.splice(index, 1)
      return true
    }
    for (const s of sections) {
      if (s.children && removeSection(s.children)) {
        return true
      }
    }
    return false
  }
  removeSection(sectionTree.value)
}

// 查看/编辑路由规则
const handleEditRule = (section) => {
  selectedSection.value = section
  editingRule.value = {
    inherit_mode: 'inherit',
    base_keywords: [],
    domain_keyword_groups: [],
    skill_id: null,
    schema_diff: {}
  }
  showRuleDrawer.value = true
}

// 刷新
const handleRefresh = () => {
  fetchSectionTree()
}

// 导出
const handleExport = async () => {
  if (!selectedDomain.value || !selectedReportType.value) {
    message.warning('请先选择领域和报告类型')
    return
  }
  try {
    const data = await domainFactoryApi.exportSections(selectedDomain.value, selectedReportType.value)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sections_${selectedDomain.value}_${selectedReportType.value}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch (e) {
    message.error('导出失败')
  }
}

// 统计信息
const stats = computed(() => {
  const countSections = (sections) => {
    let count = 0
    for (const s of sections) {
      count++
      if (s.children) {
        count += countSections(s.children)
      }
    }
    return count
  }
  return {
    total: countSections(sectionTree.value),
    level1: sectionTree.value.length
  }
})

// 监听选择变化
watch([selectedDomain, selectedReportType], () => {
  if (selectedDomain.value && selectedReportType.value) {
    fetchSectionTree()
  }
})

onMounted(() => {
  // 默认选中
  if (domains.value.length) {
    selectedDomain.value = domains.value[0].value
  }
  if (reportTypes.value.length) {
    selectedReportType.value = reportTypes.value[0].value
  }
})
</script>

<template>
  <div class="section-routing-view">
    <!-- Header -->
    <div class="page-header">
      <div class="title-group">
        <div class="title-with-back">
          <a-button type="text" class="back-btn" @click="router.back()">
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <div>
            <h1>章节路由配置</h1>
            <p class="page-desc">配置行业领域与报告类型的章节目录结构，以及路由规则</p>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <a-button @click="handleRefresh" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
        <a-button @click="handleExport">
          <template #icon><DownloadOutlined /></template>
          导出
        </a-button>
        <a-button type="primary" @click="handleSave" :loading="saving">
          <template #icon><SaveOutlined /></template>
          保存配置
        </a-button>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <div class="filter-item">
        <label>领域</label>
        <a-select
          v-model:value="selectedDomain"
          :options="domains"
          placeholder="选择领域"
          style="width: 160px"
        />
      </div>
      <div class="filter-item">
        <label>报告类型</label>
        <a-select
          v-model:value="selectedReportType"
          :options="reportTypes"
          placeholder="选择报告类型"
          style="width: 200px"
        />
      </div>
      <div class="filter-stats">
        <span>共 {{ stats.total }} 个章节，{{ stats.level1 }} 个一级章节</span>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-area">
      <a-spin :spinning="loading">
        <div class="section-tree-container">
          <div class="tree-header">
            <h3>章节结构</h3>
            <a-button type="link" @click="handleAddSection(null, 1)">
              <PlusOutlined /> 添加一级章节
            </a-button>
          </div>

          <div v-if="!sectionTree.length" class="empty-tree">
            <p>暂无章节配置，请添加或导入</p>
          </div>

          <div v-else class="section-list">
            <div v-for="section in sectionTree" :key="section.code" class="section-item level-1">
              <div class="section-row" :class="{ 'has-children': section.children?.length }">
                <div class="section-info">
                  <span class="section-path">{{ section.section_path || section.code }}</span>
                  <span class="section-title">{{ section.title }}</span>
                  <a-tag v-if="section.standard_code" color="blue" size="small">
                    {{ section.standard_code }}
                  </a-tag>
                </div>
                <div class="section-actions">
                  <a-button size="small" type="link" @click="handleAddSection(section, (section.level || 1) + 1)">
                    <PlusOutlined /> 子章节
                  </a-button>
                  <a-button size="small" type="link" @click="handleEditSection(section)">
                    <EditOutlined /> 编辑
                  </a-button>
                  <a-button size="small" type="link" @click="handleEditRule(section)">
                    <SettingOutlined /> 规则
                  </a-button>
                  <a-popconfirm
                    title="确定删除此章节吗？"
                    @confirm="handleDeleteSection(section)"
                  >
                    <a-button size="small" type="link" danger>
                      <DeleteOutlined />
                    </a-button>
                  </a-popconfirm>
                </div>
              </div>

              <!-- 子章节 -->
              <div v-if="section.children?.length" class="section-children">
                <div v-for="child in section.children" :key="child.code" class="section-item level-2">
                  <div class="section-row">
                    <div class="section-info">
                      <span class="section-path">{{ child.section_path }}</span>
                      <span class="section-title">{{ child.title }}</span>
                      <a-tag v-if="child.standard_code" color="purple" size="small">
                        {{ child.standard_code }}
                      </a-tag>
                    </div>
                    <div class="section-actions">
                      <a-button size="small" type="link" @click="handleEditSection(child)">
                        <EditOutlined /> 编辑
                      </a-button>
                      <a-button size="small" type="link" @click="handleEditRule(child)">
                        <SettingOutlined /> 规则
                      </a-button>
                      <a-popconfirm
                        title="确定删除此章节吗？"
                        @confirm="handleDeleteSection(child)"
                      >
                        <a-button size="small" type="link" danger>
                          <DeleteOutlined />
                        </a-button>
                      </a-popconfirm>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </a-spin>
    </div>

    <!-- Section Edit Modal -->
    <a-modal
      v-model:open="showSectionModal"
      :title="editingSection ? '编辑章节' : '添加章节'"
      @ok="handleSaveSection"
      ok-text="保存"
      width="500px"
    >
      <a-form :model="sectionForm" layout="vertical">
        <a-form-item label="章节标题" required>
          <a-input v-model:value="sectionForm.title" placeholder="请输入章节标题" />
        </a-form-item>
        <a-form-item label="章节代码">
          <a-input v-model:value="sectionForm.code" placeholder="自动生成" />
        </a-form-item>
        <a-form-item label="章节路径">
          <a-input v-model:value="sectionForm.section_path" placeholder="如: 1.1.2" />
        </a-form-item>
        <a-form-item label="章节层级">
          <a-input-number v-model:value="sectionForm.level" :min="1" :max="5" />
        </a-form-item>
        <a-form-item label="绑定 StandardCode">
          <a-input v-model:value="sectionForm.standard_code" placeholder="如: SEC_WATER_RESOURCE" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Rule Drawer -->
    <a-drawer
      v-model:open="showRuleDrawer"
      :title="`路由规则 - ${selectedSection?.title || ''}`"
      width="480"
    >
      <div class="rule-form">
        <a-form :model="editingRule" layout="vertical">
          <a-form-item label="继承模式">
            <a-select v-model:value="editingRule.inherit_mode">
              <a-select-option value="inherit">继承父章节</a-select-option>
              <a-select-option value="override">覆盖</a-select-option>
              <a-select-option value="none">无继承</a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="基础关键词">
            <a-select
              v-model:value="editingRule.base_keywords"
              mode="tags"
              placeholder="输入关键词后回车"
            />
          </a-form-item>

          <a-form-item label="领域关键词组">
            <div class="keyword-groups">
              <div v-for="(group, idx) in editingRule.domain_keyword_groups" :key="idx" class="keyword-group">
                <a-input :value="group" @change="(e) => editingRule.domain_keyword_groups[idx] = e.target.value" placeholder="关键词" />
              </div>
              <a-button type="link" @click="editingRule.domain_keyword_groups.push('')">
                <PlusOutlined /> 添加关键词组
              </a-button>
            </div>
          </a-form-item>

          <a-form-item label="关联 Skill">
            <a-select
              v-model:value="editingRule.skill_id"
              placeholder="选择关联的 Skill"
              allow-clear
            >
              <a-select-option value="skill_water_balance">水资源平衡计算</a-select-option>
              <a-select-option value="skill_air_emission">废气排放清单</a-select-option>
              <a-select-option value="skill_limit_validation">排放限值校验</a-select-option>
            </a-select>
          </a-form-item>
        </a-form>
      </div>
    </a-drawer>
  </div>
</template>

<style lang="less" scoped>
.section-routing-view {
  padding: 24px;
  background: #fff;
  min-height: 100vh;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--gray-150);

    .title-group {
      .title-with-back {
        display: flex;
        align-items: flex-start;
        gap: 8px;

        .back-btn {
          margin-top: 4px;
        }

        h1 {
          margin: 0;
          font-size: 20px;
          font-weight: 600;
        }

        .page-desc {
          margin: 4px 0 0;
          color: var(--gray-500);
          font-size: 13px;
        }
      }
    }

    .header-actions {
      display: flex;
      gap: 8px;
    }
  }

  .filter-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px;
    background: var(--gray-50);
    border-radius: 8px;
    margin-bottom: 16px;

    .filter-item {
      display: flex;
      align-items: center;
      gap: 8px;

      label {
        font-size: 13px;
        color: var(--gray-600);
        white-space: nowrap;
      }
    }

    .filter-stats {
      margin-left: auto;
      font-size: 13px;
      color: var(--gray-500);
    }
  }

  .content-area {
    .section-tree-container {
      background: #fff;
      border: 1px solid var(--gray-150);
      border-radius: 12px;
      overflow: hidden;

      .tree-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        border-bottom: 1px solid var(--gray-150);

        h3 {
          margin: 0;
          font-size: 15px;
        }
      }

      .empty-tree {
        padding: 60px;
        text-align: center;
        color: var(--gray-400);
      }

      .section-list {
        padding: 16px;
      }

      .section-item {
        &.level-1 {
          margin-bottom: 8px;
        }

        &.level-2 {
          margin-left: 24px;
          margin-top: 8px;
        }
      }

      .section-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        background: var(--gray-50);
        border-radius: 8px;
        border: 1px solid var(--gray-100);
        transition: all 0.2s;

        &:hover {
          border-color: var(--main-200);
          background: rgba(22, 119, 255, 0.04);
        }

        &.has-children {
          border-left: 3px solid var(--main-color);
        }
      }

      .section-info {
        display: flex;
        align-items: center;
        gap: 12px;

        .section-path {
          font-size: 12px;
          color: var(--gray-400);
          font-family: monospace;
          min-width: 40px;
        }

        .section-title {
          font-size: 14px;
          font-weight: 500;
        }
      }

      .section-actions {
        display: flex;
        gap: 4px;
      }

      .section-children {
        border-left: 2px dashed var(--gray-200);
        margin-left: 16px;
        padding-left: 8px;
      }
    }
  }

  .rule-form {
    padding: 8px 0;

    .keyword-groups {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
  }
}
</style>
