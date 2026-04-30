<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  ReloadOutlined,
  DownloadOutlined,
  UploadOutlined,
  SearchOutlined
} from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const router = useRouter()

// 状态
const loading = ref(false)
const saving = ref(false)
const codeList = ref([])
const showEditModal = ref(false)
const editingItem = ref(null)
const searchKeyword = ref('')
const selectedCategory = ref('')

// 表单数据
const codeForm = ref({
  standard_code: '',
  name: '',
  description: '',
  environmental_factor: '',
  business_stage: '',
  action_type: 'analyze',
  category: '',
  priority: 50,
  match_rules: {
    fallback_keywords: [],
    must_include: [],
    should_include_one_of: [],
    must_not_include: []
  },
  semantic_routing: {
    required_skills: [],
    optional_skills: [],
    agent_persona: '',
    planning_strategy: 'sequential'
  }
})

// 筛选后的列表
const filteredList = computed(() => {
  let result = codeList.value
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    result = result.filter(item =>
      item.standard_code?.toLowerCase().includes(kw) ||
      item.name?.toLowerCase().includes(kw) ||
      item.description?.toLowerCase().includes(kw)
    )
  }
  if (selectedCategory.value) {
    result = result.filter(item => item.category === selectedCategory.value)
  }
  return result
})

// 选项
const envFactors = [
  { value: 'GENERAL', label: '综合' },
  { value: 'AIR', label: '大气环境' },
  { value: 'WATER', label: '水环境' },
  { value: 'SOIL', label: '土壤环境' },
  { value: 'NOISE', label: '声环境' },
  { value: 'ECOLOGY', label: '生态环境' },
  { value: ' SOLID_WASTE', label: '固体废物' }
]

const businessStages = [
  { value: 'GENERAL', label: '通用' },
  { value: 'PLANNING', label: '规划阶段' },
  { value: 'STATUS', label: '现状评价' },
  { value: 'PREDICT', label: '影响预测' },
  { value: 'MEASURE', label: '治理措施' }
]

const actionTypes = [
  { value: 'analyze', label: '分析' },
  { value: 'predict', label: '预测' },
  { value: 'assess', label: '评估' },
  { value: 'measure', label: '措施' }
]

const categories = [
  { value: 'General_Information', label: '基础信息' },
  { value: 'Engineering_Analysis', label: '工程分析' },
  { value: 'Environmental_Status_Assessment', label: '环境现状调查与评价' },
  { value: 'Environmental_Impact_Prediction', label: '环境影响预测与评价' },
  { value: 'Environmental_Measures', label: '环境保护措施' },
  { value: 'Monitoring_Plan', label: '监测计划' }
]

// 获取 StandardCode 列表
const fetchCodeList = async () => {
  loading.value = true
  try {
    const res = await domainFactoryApi.getStandardCodeMapping()
    codeList.value = res?.items || []
  } catch (e) {
    console.error('获取 StandardCode 列表失败:', e)
    // 使用默认示例数据
    codeList.value = [
      {
        standard_code: 'GEN_GENERAL_PRINCIPLES',
        name: '总则',
        description: '环评报告总则章节',
        environmental_factor: 'GENERAL',
        business_stage: 'GENERAL',
        action_type: 'analyze',
        category: 'General_Information',
        priority: 100
      },
      {
        standard_code: 'WATER_STATUS',
        name: '水资源现状分析',
        description: '水环境现状调查与评价',
        environmental_factor: 'WATER',
        business_stage: 'STATUS',
        action_type: 'analyze',
        category: 'Environmental_Status_Assessment',
        priority: 80
      }
    ]
  } finally {
    loading.value = false
  }
}

// 保存
const handleSave = async () => {
  saving.value = true
  try {
    await domainFactoryApi.updateStandardCodeMapping({ items: codeList.value })
    message.success('保存成功')
  } catch (e) {
    console.error('保存失败:', e)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 添加
const handleAdd = () => {
  editingItem.value = null
  codeForm.value = {
    standard_code: '',
    name: '',
    description: '',
    environmental_factor: '',
    business_stage: '',
    action_type: 'analyze',
    category: '',
    priority: 50,
    match_rules: {
      fallback_keywords: [],
      must_include: [],
      should_include_one_of: [],
      must_not_include: []
    },
    semantic_routing: {
      required_skills: [],
      optional_skills: [],
      agent_persona: '',
      planning_strategy: 'sequential'
    }
  }
  showEditModal.value = true
}

// 编辑
const handleEdit = (item) => {
  editingItem.value = item
  codeForm.value = JSON.parse(JSON.stringify(item))
  showEditModal.value = true
}

// 保存编辑
const handleSaveEdit = () => {
  if (!codeForm.value.standard_code) {
    message.warning('请输入 StandardCode')
    return
  }
  if (!codeForm.value.name) {
    message.warning('请输入名称')
    return
  }

  if (editingItem.value) {
    const idx = codeList.value.findIndex(i => i.standard_code === editingItem.value.standard_code)
    if (idx !== -1) {
      codeList.value[idx] = { ...codeForm.value }
    }
  } else {
    codeList.value.push({ ...codeForm.value })
  }

  showEditModal.value = false
}

// 删除
const handleDelete = (item) => {
  codeList.value = codeList.value.filter(i => i.standard_code !== item.standard_code)
}

// 导出
const handleExport = () => {
  const data = {
    version: '1.0.0',
    standard_codes: codeList.value,
    metadata: {
      exported_at: new Date().toISOString(),
      total_codes: codeList.value.length
    }
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `standard_codes_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  message.success('导出成功')
}

// 导入
const handleImport = (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result)
      const codes = data.standard_codes || data.items || []
      codes.forEach(code => {
        if (!codeList.value.find(i => i.standard_code === code.standard_code)) {
          codeList.value.push(code)
        }
      })
      message.success(`成功导入 ${codes.length} 条记录`)
    } catch (err) {
      message.error('导入失败：文件格式错误')
    }
  }
  reader.readAsText(file)
  event.target.value = ''
}

// 刷新
const handleRefresh = () => {
  fetchCodeList()
}

// 获取优先级颜色
const getPriorityColor = (priority) => {
  if (priority >= 80) return '#52c41a'
  if (priority >= 50) return '#faad14'
  return '#ff4d4f'
}

// 获取环境要素标签颜色
const getEnvFactorColor = (factor) => {
  const colors = {
    'GENERAL': 'default',
    'AIR': 'blue',
    'WATER': 'cyan',
    'SOIL': 'brown',
    'NOISE': 'purple',
    'ECOLOGY': 'green',
    'SOLID_WASTE': 'orange'
  }
  return colors[factor] || 'default'
}

onMounted(() => {
  fetchCodeList()
})
</script>

<template>
  <div class="standard-code-view">
    <!-- Header -->
    <div class="page-header">
      <div class="title-group">
        <div class="title-with-back">
          <a-button type="text" class="back-btn" @click="router.back()">
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <div>
            <h1>StandardCode 映射管理</h1>
            <p class="page-desc">管理标准章节代码映射表，用于规范化章节识别与路由</p>
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
        <a-button @click="handleAdd">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
        <a-button type="primary" @click="handleSave" :loading="saving">
          <template #icon><SaveOutlined /></template>
          保存配置
        </a-button>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <a-input-search
        v-model:value="searchKeyword"
        placeholder="搜索代码、名称、描述..."
        style="width: 280px"
        allow-clear
      />
      <a-select
        v-model:value="selectedCategory"
        placeholder="按分类筛选"
        style="width: 200px"
        allow-clear
      >
        <a-select-option v-for="cat in categories" :key="cat.value" :value="cat.value">
          {{ cat.label }}
        </a-select-option>
      </a-select>
      <div class="filter-stats">
        <span>共 {{ filteredList.length }} 条记录</span>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-area">
      <a-spin :spinning="loading">
        <a-table
          :dataSource="filteredList"
          :columns="columns"
          :pagination="{ pageSize: 15 }"
          row-key="standard_code"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'standard_code'">
              <code class="code-value">{{ record.standard_code }}</code>
            </template>
            <template v-else-if="column.key === 'name'">
              <span class="name-value">{{ record.name }}</span>
            </template>
            <template v-else-if="column.key === 'environmental_factor'">
              <a-tag :color="getEnvFactorColor(record.environmental_factor)">
                {{ record.environmental_factor || '-' }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'priority'">
              <a-badge
                :color="getPriorityColor(record.priority)"
                :text="`${record.priority || 0} 分`"
              />
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-space>
                <a-button size="small" type="link" @click="handleEdit(record)">
                  <EditOutlined />
                </a-button>
                <a-popconfirm
                  title="确定删除此映射吗？"
                  @confirm="handleDelete(record)"
                >
                  <a-button size="small" type="link" danger>
                    <DeleteOutlined />
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-spin>
    </div>

    <!-- Edit Modal -->
    <a-modal
      v-model:open="showEditModal"
      :title="editingItem ? '编辑 StandardCode' : '添加 StandardCode'"
      @ok="handleSaveEdit"
      ok-text="保存"
      width="700px"
    >
      <a-form :model="codeForm" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="StandardCode" required>
              <a-input v-model:value="codeForm.standard_code" placeholder="如: GEN_GENERAL_PRINCIPLES" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="名称" required>
              <a-input v-model:value="codeForm.name" placeholder="如: 总则" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="描述">
          <a-textarea v-model:value="codeForm.description" placeholder="描述此代码的用途" :rows="2" />
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="环境要素">
              <a-select v-model:value="codeForm.environmental_factor" placeholder="选择环境要素">
                <a-select-option v-for="ef in envFactors" :key="ef.value" :value="ef.value">
                  {{ ef.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="业务阶段">
              <a-select v-model:value="codeForm.business_stage" placeholder="选择业务阶段">
                <a-select-option v-for="bs in businessStages" :key="bs.value" :value="bs.value">
                  {{ bs.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="操作类型">
              <a-select v-model:value="codeForm.action_type" placeholder="选择操作类型">
                <a-select-option v-for="at in actionTypes" :key="at.value" :value="at.value">
                  {{ at.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="分类">
              <a-select v-model:value="codeForm.category" placeholder="选择分类">
                <a-select-option v-for="cat in categories" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="优先级">
              <a-input-number
                v-model:value="codeForm.priority"
                :min="1"
                :max="100"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script>
// Table columns definition
const columns = [
  {
    title: 'StandardCode',
    dataIndex: 'standard_code',
    key: 'standard_code',
    width: 200
  },
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    width: 150
  },
  {
    title: '环境要素',
    dataIndex: 'environmental_factor',
    key: 'environmental_factor',
    width: 120
  },
  {
    title: '业务阶段',
    dataIndex: 'business_stage',
    key: 'business_stage',
    width: 100
  },
  {
    title: '优先级',
    dataIndex: 'priority',
    key: 'priority',
    width: 100
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    fixed: 'right'
  }
]
</script>

<style lang="less" scoped>
.standard-code-view {
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

    .filter-stats {
      margin-left: auto;
      font-size: 13px;
      color: var(--gray-500);
    }
  }

  .content-area {
    background: #fff;
    border: 1px solid var(--gray-150);
    border-radius: 12px;
    overflow: hidden;
  }

  .code-value {
    font-size: 12px;
    color: var(--main-color);
    background: rgba(22, 119, 255, 0.1);
    padding: 2px 8px;
    border-radius: 4px;
  }

  .name-value {
    font-weight: 500;
  }
}

:deep(.ant-table) {
  .ant-table-thead > tr > th {
    background: var(--gray-50);
  }
}
</style>
