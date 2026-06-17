<template>
  <div class="domain-entity-builder-view">
    <div class="page-header">
      <div>
        <div class="header-title-row">
          <a-button type="text" @click="handleBack" class="back-btn">
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <h2>领域实体构建器</h2>
        </div>
        <p class="subtitle">
          管理4大域层级分类体系和实体Schema定义，支持不同行业的实体隔离
        </p>
      </div>
      <div class="header-actions">
        <a-select
          v-model:value="currentDomain"
          placeholder="全部行业"
          style="width: 140px"
          :options="domainOptions"
          allow-clear
          @change="onDomainChange"
        />
        <a-button type="default" @click="handleExport">
          <template #icon><DownloadOutlined /></template>
          导出
        </a-button>
        <a-button type="default" @click="handleImport">
          <template #icon><UploadOutlined /></template>
          导入
        </a-button>
        <a-button type="primary" @click="handleCreateEntity">
          <template #icon><PlusOutlined /></template>
          新建实体
        </a-button>
        <a-button type="primary" @click="handleOpenExtract">
          <template #icon><RobotOutlined /></template>
          AI 提取
        </a-button>
      </div>
    </div>

    <a-alert
      v-if="error"
      type="error"
      show-icon
      class="alert"
      :message="error"
      closable
      @close="error = ''"
    />

    <div class="main-content">
      <!-- 左侧：分类导航树 -->
      <div class="left-panel">
        <div class="panel-header">
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索实体..."
            allow-clear
            @change="handleSearch"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </div>
        <div class="taxonomy-tree">
          <a-spin :spinning="loading">
            <a-tree
              v-if="treeData.length > 0"
              :tree-data="filteredTreeData"
              :selected-keys="selectedKeys"
              :expanded-keys="expandedKeys"
              :auto-expand-parent="autoExpandParent"
              @select="handleTreeSelect"
              @expand="handleTreeExpand"
            >
              <template #title="{ title, category, entity_id, isNew }">
                <div class="tree-node-row">
                  <span :class="['tree-node-title', { 'is-new': isNew }]">{{ title }}</span>
                  <span v-if="category" class="tree-node-count">
                    ({{ getEntityCountByCategory(category) }})
                  </span>
                  <a-popconfirm
                    v-if="entity_id && !isNew"
                    title="确定删除此实体？"
                    ok-text="删除"
                    cancel-text="取消"
                    placement="right"
                    @confirm.stop="handleTreeDelete(entity_id)"
                  >
                    <DeleteOutlined
                      class="tree-delete-icon"
                      @click.stop
                    />
                  </a-popconfirm>
                </div>
              </template>
            </a-tree>
            <a-empty v-else description="暂无分类数据" />
          </a-spin>
        </div>
      </div>

      <!-- 右侧：Schema编辑器 -->
      <div class="right-panel">
        <div v-if="!selectedEntity" class="empty-state">
          <a-empty description="请从左侧选择分类或实体进行编辑" />
        </div>

        <div v-else class="schema-editor">
          <!-- 实体基本信息 -->
          <a-card title="基础元数据" class="editor-section">
            <a-form :model="editingEntity" layout="vertical">
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="实体键 (entity_key)" required>
                    <a-input
                      v-model:value="editingEntity.entity_key"
                      placeholder="snake_case"
                      :disabled="!!editingEntity.entity_id"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="中文名称" required>
                    <a-input v-model:value="editingEntity.name_cn" placeholder="例如：设计生产能力" />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="分类" required>
                    <a-select
                      v-model:value="editingEntity.category"
                      placeholder="请选择分类"
                      :disabled="!!editingEntity.entity_id"
                      :options="categoryOptions"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="行业 (domain_code)" required>
                    <a-select
                      v-model:value="editingEntity.domain_code"
                      :disabled="!!editingEntity.entity_id"
                      :options="domainOptions"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="值类型">
                    <a-select v-model:value="editingEntity.value_type">
                      <a-select-option value="String">String</a-select-option>
                      <a-select-option value="Integer">Integer</a-select-option>
                      <a-select-option value="Float">Float</a-select-option>
                      <a-select-option value="Boolean">Boolean</a-select-option>
                      <a-select-option value="Enum">Enum</a-select-option>
                      <a-select-option value="Object">Object</a-select-option>
                      <a-select-option value="List">List</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="单位">
                    <a-input v-model:value="editingEntity.unit" placeholder="Mt/a、万吨/年" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <a-checkbox v-model:checked="editingEntity.is_list_type">
                      列表型实体（一份报告可能有多个）
                    </a-checkbox>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item label="描述">
                <a-textarea v-model:value="editingEntity.description" :rows="2" placeholder="描述该实体的用途和特点" />
              </a-form-item>

              <a-form-item label="同义词列表">
                <a-select
                  v-model:value="editingEntity.synonyms"
                  mode="tags"
                  placeholder="输入同义词，按回车添加"
                  :token-separators="[',']"
                  style="width: 100%"
                />
              </a-form-item>
            </a-form>
          </a-card>

          <!-- 属性定义 -->
          <a-card title="属性结构定义" class="editor-section">
            <a-table :columns="propertyColumns" :data-source="editingEntity.properties" :pagination="false" size="small">
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'actions'">
                  <a-space>
                    <a-button type="link" size="small" @click="handleEditProperty(index)">编辑</a-button>
                    <a-popconfirm title="删除此属性？" @confirm="handleDeleteProperty(index)">
                      <a-button type="link" size="small" danger>删除</a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
                <template v-else-if="column.key === 'value_type'">{{ record.value_type }}</template>
                <template v-else-if="column.key === 'required'">
                  <a-tag :color="record.required ? 'red' : 'default'">{{ record.required ? '必填' : '可选' }}</a-tag>
                </template>
                <template v-else-if="column.key === 'enum_options'">
                  <span v-if="record.enum_options && record.enum_options.length">{{ record.enum_options.join(', ') }}</span>
                  <span v-else>-</span>
                </template>
              </template>
            </a-table>
            <a-button type="dashed" block style="margin-top: 16px" @click="handleAddProperty">
              <template #icon><PlusOutlined /></template>
              添加属性
            </a-button>
          </a-card>

          <!-- 关系推理规则 -->
          <a-card title="图谱关系推理规则" class="editor-section">
            <div v-for="(rule, index) in editingEntity.relation_rules" :key="index" class="rule-item">
              <div class="rule-header">
                <strong>{{ rule.rule_name || `规则 ${index + 1}` }}</strong>
                <a-space>
                  <a-button type="link" size="small" @click="handleEditRule(index)">编辑</a-button>
                  <a-popconfirm title="删除此规则？" @confirm="handleDeleteRule(index)">
                    <a-button type="link" size="small" danger>删除</a-button>
                  </a-popconfirm>
                </a-space>
              </div>
              <div class="rule-content">
                <div class="rule-condition">
                  <strong>条件：</strong>
                  <code>{{ JSON.stringify(rule.condition, null, 2) }}</code>
                </div>
                <div class="rule-actions">
                  <strong>动作：</strong>
                  <code>{{ JSON.stringify(rule.actions, null, 2) }}</code>
                </div>
              </div>
            </div>
            <a-button type="dashed" block style="margin-top: 16px" @click="handleAddRule">
              <template #icon><PlusOutlined /></template>
              添加规则
            </a-button>
          </a-card>

          <!-- 操作按钮 -->
          <div class="editor-actions">
            <a-space>
              <a-button type="primary" @click="handleSave" :loading="saving">保存</a-button>
              <a-button @click="handleCancel">取消</a-button>
              <a-button v-if="editingEntity.entity_id" type="default" @click="handleClone">
                <template #icon><CopyOutlined /></template>
                克隆
              </a-button>
              <a-button v-if="editingEntity.entity_id" type="default" @click="handleViewJson">
                <template #icon><FileTextOutlined /></template>
                查看JSON
              </a-button>
              <a-popconfirm
                v-if="editingEntity.entity_id"
                title="确定删除此实体？此操作不可恢复。"
                ok-text="删除"
                cancel-text="取消"
                @confirm="handleDelete"
              >
                <a-button type="primary" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </div>
        </div>
      </div>
    </div>

    <!-- 属性编辑弹窗 -->
    <a-modal v-model:open="propertyModalVisible" title="属性定义" width="700px" @ok="handleSaveProperty">
      <a-form :model="editingProperty" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="属性键" required>
              <a-input v-model:value="editingProperty.key" placeholder="例如：name" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="中文名称" required>
              <a-input v-model:value="editingProperty.name_cn" placeholder="例如：村庄名称" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="数据类型" required>
              <a-select v-model:value="editingProperty.value_type">
                <a-select-option value="String">String</a-select-option>
                <a-select-option value="Integer">Integer</a-select-option>
                <a-select-option value="Float">Float</a-select-option>
                <a-select-option value="Boolean">Boolean</a-select-option>
                <a-select-option value="Enum">Enum</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="单位">
              <a-input v-model:value="editingProperty.unit" placeholder="例如：m、人" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item>
          <a-checkbox v-model:checked="editingProperty.required">必填</a-checkbox>
        </a-form-item>
        <a-form-item v-if="editingProperty.value_type === 'Enum'" label="枚举选项" required>
          <a-select v-model:value="editingProperty.enum_options" mode="tags" placeholder="输入枚举选项，按回车添加" :token-separators="[',']" style="width: 100%" />
        </a-form-item>
        <a-row :gutter="16" v-if="editingProperty.value_type === 'Integer' || editingProperty.value_type === 'Float'">
          <a-col :span="12">
            <a-form-item label="最小值">
              <a-input-number v-model:value="editingProperty.min_value" style="width: 100%" :precision="editingProperty.value_type === 'Float' ? 2 : 0" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="最大值">
              <a-input-number v-model:value="editingProperty.max_value" style="width: 100%" :precision="editingProperty.value_type === 'Float' ? 2 : 0" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-textarea v-model:value="editingProperty.description" :rows="2" placeholder="属性描述" />
        </a-form-item>
        <a-form-item label="提取提示词">
          <a-textarea v-model:value="editingProperty.extraction_hint" :rows="2" placeholder="用于指导LLM提取的提示词" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 规则编辑弹窗 -->
    <a-modal v-model:open="ruleModalVisible" title="关系推理规则" width="800px" @ok="handleSaveRule">
      <a-form :model="editingRule" layout="vertical">
        <a-form-item label="规则名称" required>
          <a-input v-model:value="editingRule.rule_name" placeholder="例如：错动线内不搬迁冲突检测" />
        </a-form-item>
        <a-form-item label="条件表达式 (JSON)" required>
          <a-textarea v-model:value="editingRule.condition_json" :rows="4" placeholder='{"location_relation": "错动线内", "protection_status": "留守"}' />
        </a-form-item>
        <a-form-item label="动作列表 (JSON)" required>
          <a-textarea v-model:value="editingRule.actions_json" :rows="6" placeholder='[{"type": "create_edge", "relation": "CONFLICT_WITH", "target": "Project_Entity"}]' />
        </a-form-item>
        <a-form-item label="规则描述">
          <a-textarea v-model:value="editingRule.description" :rows="2" placeholder="规则描述" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 导入配置弹窗 -->
    <a-modal v-model:open="importModalVisible" title="导入配置" @ok="handleConfirmImport">
      <a-upload-dragger v-model:fileList="importFileList" :before-upload="handleBeforeUpload" accept=".json" :max-count="1">
        <p class="ant-upload-drag-icon"><InboxOutlined /></p>
        <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p class="ant-upload-hint">支持 JSON 格式配置文件</p>
      </a-upload-dragger>
    </a-modal>

    <!-- 查看JSON弹窗 -->
    <a-modal v-model:open="jsonModalVisible" title="实体元数据JSON" width="900px" :footer="null">
      <div class="json-viewer">
        <div class="json-actions">
          <a-space>
            <a-button type="default" @click="handleCopyJson"><template #icon><CopyOutlined /></template>复制</a-button>
            <a-button type="default" @click="handleDownloadJson"><template #icon><DownloadOutlined /></template>下载</a-button>
          </a-space>
        </div>
        <pre class="json-content">{{ jsonContent }}</pre>
      </div>
    </a-modal>

    <!-- 克隆弹窗 -->
    <a-modal v-model:open="cloneModalVisible" title="克隆实体" @ok="handleConfirmClone">
      <a-form layout="vertical">
        <a-form-item label="新实体键 (entity_key)" required>
          <a-input v-model:value="cloneNewKey" placeholder="例如：sensitive_villages_v2" />
        </a-form-item>
        <a-form-item label="新中文名称" required>
          <a-input v-model:value="cloneNewName" placeholder="例如：敏感目标村庄（V2）" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- AI 实体提取弹窗 -->
    <a-modal v-model:open="showExtractModal" title="AI 实体提取" width="900px" :footer="null" @cancel="handleExtractCancel">
      <a-steps :current="extractStep" size="small" style="margin-bottom: 24px">
        <a-step title="上传文档" />
        <a-step title="提取结果" />
      </a-steps>

      <!-- Step 1: Upload -->
      <div v-if="extractStep === 0">
        <a-form layout="vertical">
          <a-form-item label="选择行业" required>
            <a-select v-model:value="extractDomain" :options="domainOptions" placeholder="选择行业" style="width: 100%" />
          </a-form-item>
          <a-form-item label="上传文档" required>
            <a-upload-dragger :before-upload="handleExtractUpload" :show-upload-list="false" accept=".txt,.md,.json">
              <p class="ant-upload-drag-icon"><InboxOutlined /></p>
              <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
              <p class="ant-upload-hint">支持 TXT、Markdown 格式文档，最大 5MB</p>
            </a-upload-dragger>
            <div v-if="extractFile" class="extract-file-info">
              <FileTextOutlined /> {{ extractFile.name }} ({{ formatFileSize(extractFile.size) }})
            </div>
          </a-form-item>
          <a-form-item>
            <a-button type="primary" :loading="extracting" :disabled="!extractFile || !extractDomain" @click="handleStartExtract" style="width: 100%">
              <template #icon><ThunderboltOutlined /></template>
              开始提取
            </a-button>
          </a-form-item>
        </a-form>
      </div>

      <!-- Step 2: Comparison & Import -->
      <div v-if="extractStep === 1">
        <div class="extract-results-header">
          <a-space>
            <a-tag color="blue">提取 {{ extractComparison.length }} 个实体</a-tag>
            <a-tag color="green">{{ extractComparison.filter(e => e._status === 'matched').length }} 匹配</a-tag>
            <a-tag color="orange">{{ extractComparison.filter(e => e._status === 'different').length }} 有变化</a-tag>
            <a-tag color="purple">{{ extractComparison.filter(e => e._status === 'new').length }} 新增</a-tag>
            <a-tag v-if="extractDomain">{{ domainLabel(extractDomain) }}</a-tag>
          </a-space>
          <a-space>
            <a-button size="small" @click="handleSelectAllNew" :disabled="importableCount === 0">全选可导入</a-button>
            <a-button size="small" @click="handleDeselectAll">取消全选</a-button>
            <a-button size="small" @click="handleExtractBack">重新上传</a-button>
            <a-button size="small" type="primary" @click="handleExtractRedo" :loading="extracting">重新提取</a-button>
          </a-space>
        </div>
        <div v-if="extractComparison.length === 0" class="extract-empty">
          <a-empty description="未提取到实体对象" />
        </div>
        <div v-else class="extract-results-list">
          <a-card v-for="(item, idx) in extractComparison" :key="idx" size="small"
            :class="['extract-result-card', 'extract-card-' + item._status]">
            <div class="extract-result-header">
              <a-checkbox v-if="item._status !== 'matched'" v-model:checked="extractSelected[idx]" class="extract-check" />
              <template v-else><span class="extract-check-placeholder" /></template>
              <span class="extract-result-name">{{ item.name_cn || item.schema_ref }}</span>
              <a-space size="4">
                <a-tag v-if="item._status === 'new'" color="purple">新增</a-tag>
                <a-tag v-if="item._status === 'matched'" color="green">已匹配</a-tag>
                <a-tag v-if="item._status === 'different'" color="orange">有变化</a-tag>
                <a-tag :color="item.confidence >= 0.8 ? 'green' : item.confidence >= 0.5 ? 'orange' : 'red'">
                  {{ (item.confidence * 100).toFixed(0) }}%
                </a-tag>
                <a-tag>{{ item.schema_ref }}</a-tag>
              </a-space>
            </div>

            <!-- 差异对比 -->
            <div v-if="item._diff && Object.keys(item._diff).length" class="extract-diff">
              <div class="diff-title">字段变更对比：</div>
              <div v-for="(diff, field) in item._diff" :key="field" class="diff-row">
                <span class="diff-field">{{ field }}</span>
                <span class="diff-old">{{ diff.existing ?? '(无)' }}</span>
                <span class="diff-arrow">→</span>
                <span class="diff-new">{{ diff.extracted ?? '(无)' }}</span>
              </div>
            </div>
            <div v-else-if="item._status === 'matched'" class="extract-matched-hint">
              与已有实体完全一致，无需导入
            </div>

            <div v-if="item.extracted_text" class="extract-result-text">
              <strong>原文：</strong>{{ item.extracted_text }}
            </div>
            <div v-if="item.values && Object.keys(item.values).length" class="extract-result-values">
              <a-descriptions size="small" :column="2" bordered>
                <a-descriptions-item v-for="(val, k) in item.values" :key="k" :label="k">
                  {{ typeof val === 'object' ? JSON.stringify(val) : val }}
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </a-card>
        </div>

        <!-- Import button -->
        <div v-if="importableCount > 0" class="extract-import-bar">
          <a-space>
            已选 <strong>{{ selectedCount }}</strong> 个实体
          </a-space>
          <a-button type="primary" :loading="importing" @click="handleImportExtracted">
            <template #icon><DownloadOutlined /></template>
            导入数据库（{{ selectedCount }}）
          </a-button>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, SearchOutlined,
  DownloadOutlined, UploadOutlined, InboxOutlined,
  FileTextOutlined, CopyOutlined, ArrowLeftOutlined,
  DeleteOutlined, RobotOutlined, ThunderboltOutlined
} from '@ant-design/icons-vue'
import { domainEntityBuilderApi } from '@/apis/domain_entity_builder_api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const taxonomy = ref(null)
const entitySchemas = ref([])
const selectedKeys = ref([])
const expandedKeys = ref([])
const autoExpandParent = ref(true)
const searchKeyword = ref('')
const selectedEntity = ref(null)
const editingEntity = ref(null)
const selectedCategoryPath = ref('')
const pendingEntityKey = ref(null)
const currentDomain = ref(null)

const propertyModalVisible = ref(false)
const ruleModalVisible = ref(false)
const importModalVisible = ref(false)
const jsonModalVisible = ref(false)
const cloneModalVisible = ref(false)
const importFileList = ref([])
const editingPropertyIndex = ref(-1)
const editingRuleIndex = ref(-1)
const jsonContent = ref('')
const cloneNewKey = ref('')
const cloneNewName = ref('')

const showExtractModal = ref(false)
const extractStep = ref(0)
const extracting = ref(false)
const importing = ref(false)
const extractDomain = ref(null)
const extractFile = ref(null)
const extractComparison = ref([])
const extractSelected = ref({})

const importableCount = computed(() => {
  return extractComparison.value.filter(e => e._status !== 'matched').length
})
const selectedCount = computed(() => {
  return Object.values(extractSelected.value).filter(v => v).length
})

const domainOptions = ref([])

const editingProperty = ref({
  key: '', name_cn: '', value_type: 'String', unit: '',
  required: false, enum_options: [], min_value: null, max_value: null,
  description: '', extraction_hint: ''
})

const editingRule = ref({
  rule_id: '', rule_name: '', condition_json: '', actions_json: '', description: ''
})

const propertyColumns = [
  { title: '属性键', dataIndex: 'key', key: 'key' },
  { title: '中文名称', dataIndex: 'name_cn', key: 'name_cn' },
  { title: '类型', dataIndex: 'value_type', key: 'value_type' },
  { title: '单位', dataIndex: 'unit', key: 'unit' },
  { title: '必填', dataIndex: 'required', key: 'required' },
  { title: '枚举选项', dataIndex: 'enum_options', key: 'enum_options' },
  { title: '操作', key: 'actions', width: 120 }
]

const normalizeValueType = (v) => {
  if (!v || typeof v !== 'string') return 'String'
  if (v.startsWith('List')) {
    if (v.includes('<Object>')) return 'Object'
    if (v.includes('<String>')) return 'String'
    if (v.includes('<Integer>')) return 'Integer'
    if (v.includes('<Float>')) return 'Float'
    return 'List'
  }
  const valid = ['String', 'Integer', 'Float', 'Boolean', 'Enum', 'Object', 'List']
  return valid.includes(v) ? v : 'String'
}

const categoryOptions = computed(() => {
  if (!taxonomy.value?.domains) return []
  const cats = []
  taxonomy.value.domains.forEach(d => {
    d.categories?.forEach(c => {
      if (c.category_name && !cats.find(x => x.value === c.category_name)) {
        cats.push({ label: c.category_name, value: c.category_name })
      }
    })
  })
  return cats
})

const treeData = computed(() => {
  if (!taxonomy.value?.domains) return []
  return taxonomy.value.domains
    .map(domain => {
      const category = domain.categories?.[0]
      if (!category) return null
      const categoryName = category.category_name
      const categoryEntities = entitySchemas.value.filter(e => (e.category || '') === categoryName)
      if (categoryEntities.length === 0) return null
      return {
        title: `${domain.domain_name} (${categoryEntities.length})`,
        key: domain.domain_id,
        category: categoryName,
        isLeaf: false,
        children: [
          ...categoryEntities.map(entity => ({
            title: entity.name_cn,
            key: `entity_${entity.entity_id}`,
            entity_id: entity.entity_id,
            entity_key: entity.entity_key,
            isLeaf: true
          })),
          {
            title: '+ 新建实体',
            key: `new_${domain.domain_id}`,
            category: categoryName,
            isLeaf: true,
            isNew: true
          }
        ]
      }
    })
    .filter(Boolean)
})

const filteredTreeData = computed(() => {
  if (!searchKeyword.value) return treeData.value
  const filter = (nodes) => nodes.map(node => {
    const match = node.title.toLowerCase().includes(searchKeyword.value.toLowerCase())
    const filtered = node.children ? filter(node.children) : []
    if (match || filtered.length) return { ...node, children: filtered.length ? filtered : node.children }
    return null
  }).filter(n => n !== null)
  return filter(treeData.value)
})

const getEntityCountByCategory = (cat) => {
  if (!cat) return 0
  return entitySchemas.value.filter(e => (e.category || '') === cat).length
}

const normalizeEntityForEditing = (entity) => {
  const copy = JSON.parse(JSON.stringify(entity))
  copy.value_type = normalizeValueType(copy.value_type)
  if (copy.properties?.length) {
    copy.properties = copy.properties.map(p => ({ ...p, value_type: normalizeValueType(p.value_type) }))
  }
  if (copy.relation_rules?.length) {
    copy.relation_rules = copy.relation_rules.map(rule => {
      const nr = {
        rule_id: rule.rule_id || `rule_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        rule_name: rule.rule_name || '未命名规则',
        condition: {}, actions: [],
        description: rule.description || ''
      }
      if (rule.condition) {
        if (typeof rule.condition === 'string') { try { nr.condition = JSON.parse(rule.condition) } catch { nr.condition = {} } }
        else if (typeof rule.condition === 'object' && rule.condition !== null && !Array.isArray(rule.condition)) nr.condition = rule.condition
      }
      if (rule.actions) {
        if (Array.isArray(rule.actions)) nr.actions = rule.actions
        else if (typeof rule.actions === 'string') { try { nr.actions = JSON.parse(rule.actions) } catch { nr.actions = [] } }
      }
      return nr
    })
  }
  copy.domain_code = copy.domain_code || currentDomain.value
  return copy
}

const selectEntityByKey = (entityKey) => {
  if (!entityKey) return false
  const entity = entitySchemas.value.find(e =>
    e.entity_key === entityKey || e.entity_id === entityKey ||
    e.entity_id === `${entityKey}_schema` || e.metadata?.legacy_id === entityKey
  )
  if (entity) {
    selectedKeys.value = [`entity_${entity.entity_id}`]
    selectedEntity.value = entity
    editingEntity.value = normalizeEntityForEditing(entity)
    if (entity.category && taxonomy.value?.domains) {
      for (const d of taxonomy.value.domains) {
        if (d.categories?.[0]?.category_name === entity.category) {
          if (!expandedKeys.value.includes(d.domain_id)) expandedKeys.value.push(d.domain_id)
          break
        }
      }
    }
    return true
  }
  return false
}

const loadData = async () => {
  loading.value = true
  error.value = ''
  try {
    const [taxRes, schemasRes] = await Promise.all([
      domainEntityBuilderApi.getTaxonomy(currentDomain.value),
      domainEntityBuilderApi.listEntitySchemas(null, currentDomain.value)
    ])
    if (taxRes.success) taxonomy.value = taxRes.data
    if (schemasRes.success) entitySchemas.value = schemasRes.data.entity_schemas || []
    if (taxonomy.value?.domains) {
      expandedKeys.value = treeData.value.map(d => d.key)
    }
    await nextTick()
    const ek = route.query.entity_key || pendingEntityKey.value
    if (ek) {
      if (selectEntityByKey(ek)) pendingEntityKey.value = null
    }
  } catch (e) {
    console.error('加载数据失败', e)
    error.value = e?.message || '加载数据失败'
    message.error(error.value)
  } finally {
    loading.value = false
  }
}

const loadDictionaries = async () => {
  try {
    const domainsRes = await domainEntityBuilderApi.listDomains()
    if (domainsRes.success && domainsRes.data?.length) {
      domainOptions.value = domainsRes.data.map(d => ({ label: d.name, value: d.code }))
    }
  } catch (e) {
    console.error('加载字典数据失败', e)
  }
}

const onDomainChange = () => {
  loadData()
}

const handleTreeSelect = (keys) => {
  if (!keys?.length) {
    selectedEntity.value = null; editingEntity.value = null; selectedKeys.value = []; return
  }
  const key = keys[0]
  selectedKeys.value = [key]
  if (key.startsWith('new_')) { handleCreateEntity(key.replace('new_', '')); return }
  if (key.startsWith('entity_')) {
    const eid = key.replace('entity_', '')
    const entity = entitySchemas.value.find(e => e.entity_id === eid)
    if (entity) { selectedEntity.value = entity; editingEntity.value = normalizeEntityForEditing(entity) }
  } else {
    selectedEntity.value = null; editingEntity.value = null; selectedCategoryPath.value = key
  }
}

const handleTreeExpand = (keys) => { expandedKeys.value = keys; autoExpandParent.value = false }
const handleSearch = () => { if (searchKeyword.value) autoExpandParent.value = true }

const handleTreeDelete = async (entityId) => {
  try {
    await domainEntityBuilderApi.deleteEntitySchema(entityId)
    message.success('实体已删除')
    if (selectedEntity.value?.entity_id === entityId) {
      selectedEntity.value = null; editingEntity.value = null; selectedKeys.value = []
    }
    await loadData()
  } catch (e) {
    console.error('删除失败', e)
    message.error(e?.message || '删除失败')
  }
}

const handleCreateEntity = (domainId = null) => {
  let defaultCategory = selectedCategoryPath.value
  if (domainId && taxonomy.value?.domains) {
    const domain = taxonomy.value.domains.find(d => d.domain_id === domainId)
    if (domain?.categories?.length) defaultCategory = domain.categories[0].category_name
  }
  if (!defaultCategory) defaultCategory = '基础工程实体'

  editingEntity.value = {
    entity_id: null, entity_key: '', name_cn: '',
    category: defaultCategory,
    domain_code: currentDomain.value,
    value_type: 'String', unit: '', is_list_type: false,
    description: '', synonyms: [], properties: [], relation_rules: [], metadata: {}
  }
  selectedEntity.value = editingEntity.value
}

const handleSave = async () => {
  try {
    if (!editingEntity.value.entity_key || !editingEntity.value.name_cn) {
      message.error('请填写实体键和中文名称'); return
    }
    if (!editingEntity.value.category) { message.error('请选择分类'); return }
    if (!editingEntity.value.domain_code) { message.error('请选择行业'); return }
    saving.value = true
    editingEntity.value.value_type = normalizeValueType(editingEntity.value.value_type)
    if (editingEntity.value.properties?.length) {
      editingEntity.value.properties = editingEntity.value.properties.map(p => ({ ...p, value_type: normalizeValueType(p.value_type) }))
    }
    if (editingEntity.value.entity_id) {
      await domainEntityBuilderApi.updateEntitySchema(editingEntity.value.entity_id, editingEntity.value)
      message.success('实体更新成功')
    } else {
      const res = await domainEntityBuilderApi.createEntitySchema(editingEntity.value)
      if (res.success) { editingEntity.value.entity_id = res.data.entity_id; message.success('实体创建成功') }
    }
    await loadData()
  } catch (e) {
    console.error('保存失败', e)
    message.error(e?.message || '保存失败')
  } finally { saving.value = false }
}

const handleCancel = () => {
  if (selectedEntity.value?.entity_id) editingEntity.value = normalizeEntityForEditing(selectedEntity.value)
  else { editingEntity.value = null; selectedEntity.value = null }
}

const handleDelete = async () => {
  if (!editingEntity.value.entity_id) return
  try {
    await domainEntityBuilderApi.deleteEntitySchema(editingEntity.value.entity_id)
    message.success('实体已删除')
    editingEntity.value = null; selectedEntity.value = null; selectedKeys.value = []
    await loadData()
  } catch (e) {
    console.error('删除失败', e)
    message.error(e?.message || '删除失败')
  }
}

const handleClone = () => {
  cloneNewKey.value = editingEntity.value.entity_key + '_copy'
  cloneNewName.value = editingEntity.value.name_cn + '（副本）'
  cloneModalVisible.value = true
}

const handleConfirmClone = async () => {
  if (!cloneNewKey.value || !cloneNewName.value) {
    message.error('请填写新实体键和名称'); return
  }
  try {
    const res = await domainEntityBuilderApi.cloneEntity(
      editingEntity.value.entity_id, cloneNewKey.value, cloneNewName.value
    )
    if (res.success) { message.success('实体克隆成功'); cloneModalVisible.value = false; await loadData() }
  } catch (e) {
    console.error('克隆失败', e)
    message.error(e?.message || '克隆失败')
  }
}

// --- Property handlers ---
const handleAddProperty = () => {
  editingPropertyIndex.value = -1
  editingProperty.value = {
    key: '', name_cn: '', value_type: 'String', unit: '', required: false,
    enum_options: [], min_value: null, max_value: null, description: '', extraction_hint: ''
  }
  propertyModalVisible.value = true
}
const handleEditProperty = (i) => {
  editingPropertyIndex.value = i
  editingProperty.value = JSON.parse(JSON.stringify(editingEntity.value.properties[i]))
  editingProperty.value.enum_options = editingProperty.value.enum_options || []
  propertyModalVisible.value = true
}
const handleDeleteProperty = (i) => { editingEntity.value.properties.splice(i, 1) }
const handleSaveProperty = () => {
  try {
    if (!editingProperty.value.key || !editingProperty.value.name_cn) { message.error('请填写属性键和中文名称'); return }
    if (editingProperty.value.value_type === 'Enum' && (!editingProperty.value.enum_options?.length)) { message.error('枚举类型必须提供枚举选项'); return }
    const data = {
      key: editingProperty.value.key, name_cn: editingProperty.value.name_cn,
      value_type: editingProperty.value.value_type, unit: editingProperty.value.unit || null,
      required: editingProperty.value.required, enum_options: editingProperty.value.enum_options || null,
      min_value: editingProperty.value.min_value || null, max_value: editingProperty.value.max_value || null,
      description: editingProperty.value.description || '', extraction_hint: editingProperty.value.extraction_hint || ''
    }
    if (editingPropertyIndex.value >= 0) editingEntity.value.properties[editingPropertyIndex.value] = data
    else editingEntity.value.properties.push(data)
    propertyModalVisible.value = false; message.success('属性保存成功')
  } catch (e) { console.error('保存属性失败', e); message.error('保存属性失败') }
}

// --- Rule handlers ---
const handleAddRule = () => {
  editingRuleIndex.value = -1
  editingRule.value = { rule_id: '', rule_name: '', condition_json: '{}', actions_json: '[]', description: '' }
  ruleModalVisible.value = true
}
const handleEditRule = (i) => {
  editingRuleIndex.value = i
  const rule = editingEntity.value.relation_rules[i]
  editingRule.value = {
    rule_id: rule.rule_id || '', rule_name: rule.rule_name || '',
    condition_json: JSON.stringify(rule.condition || {}, null, 2),
    actions_json: JSON.stringify(rule.actions || [], null, 2),
    description: rule.description || ''
  }
  ruleModalVisible.value = true
}
const handleDeleteRule = (i) => { editingEntity.value.relation_rules.splice(i, 1) }
const handleSaveRule = () => {
  try {
    let condition, actions
    try { condition = JSON.parse(editingRule.value.condition_json); actions = JSON.parse(editingRule.value.actions_json) }
    catch { message.error('JSON格式错误'); return }
    if (!editingRule.value.rule_name) { message.error('请填写规则名称'); return }
    if (!editingRule.value.rule_id) editingRule.value.rule_id = `rule_${Date.now()}`
    const data = { rule_id: editingRule.value.rule_id, rule_name: editingRule.value.rule_name, condition, actions, description: editingRule.value.description || '' }
    if (editingRuleIndex.value >= 0) editingEntity.value.relation_rules[editingRuleIndex.value] = data
    else editingEntity.value.relation_rules.push(data)
    ruleModalVisible.value = false; message.success('规则保存成功')
  } catch (e) { console.error('保存规则失败', e); message.error('保存规则失败') }
}

// --- Import / Export ---
const handleExport = async () => {
  try {
    const res = await domainEntityBuilderApi.exportConfig(currentDomain.value)
    if (res.success) {
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `domain_entity_${currentDomain.value}_${Date.now()}.json`
      link.click()
      URL.revokeObjectURL(link.href)
      message.success('配置导出成功')
    }
  } catch (e) { console.error('导出失败', e); message.error('导出失败') }
}
const handleImport = () => { importModalVisible.value = true; importFileList.value = [] }
const handleBeforeUpload = () => false
const handleConfirmImport = async () => {
  if (!importFileList.value.length) { message.error('请选择文件'); return }
  try {
    const text = await importFileList.value[0].originFileObj.text()
    await domainEntityBuilderApi.importConfig(JSON.parse(text))
    message.success('配置导入成功')
    importModalVisible.value = false
    await loadData()
  } catch (e) { console.error('导入失败', e); message.error('导入失败：' + (e?.message || '文件格式错误')) }
}

// --- JSON viewer ---
const handleViewJson = () => {
  if (!editingEntity.value) { message.warning('请先选择一个实体'); return }
  jsonContent.value = JSON.stringify(editingEntity.value, null, 2)
  jsonModalVisible.value = true
}
const handleCopyJson = async () => {
  try { await navigator.clipboard.writeText(jsonContent.value); message.success('已复制到剪贴板') }
  catch { message.error('复制失败') }
}
const handleDownloadJson = () => {
  const blob = new Blob([jsonContent.value], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${editingEntity.value?.entity_key || 'entity'}_${Date.now()}.json`
  link.click()
  URL.revokeObjectURL(link.href)
  message.success('JSON文件下载成功')
}

const handleBack = () => router.push({ name: 'DomainFactoryMain' })

onMounted(async () => {
  await loadDictionaries()
  if (route.query.entity_key) pendingEntityKey.value = route.query.entity_key
  loadData()
})

watch(() => route.query.entity_key, (nk) => {
  if (nk && entitySchemas.value.length) selectEntityByKey(nk)
  else if (nk) pendingEntityKey.value = nk
})

// ========== AI Extraction ==========

const handleOpenExtract = () => {
  extractDomain.value = currentDomain.value
  extractFile.value = null
  extractComparison.value = []
  extractSelected.value = {}
  extractStep.value = 0
  showExtractModal.value = true
}

const handleExtractUpload = (file) => {
  if (file.size > 5 * 1024 * 1024) {
    message.error('文件大小不能超过 5MB')
    return false
  }
  extractFile.value = file
  return false
}

const handleStartExtract = async () => {
  if (!extractFile.value || !extractDomain.value) return
  extracting.value = true
  try {
    const res = await domainEntityBuilderApi.extractEntities(
      extractFile.value, extractDomain.value
    )
    if (res.success) {
      extractComparison.value = res.data.comparison || res.data.entities || []
      extractSelected.value = {}
      extractStep.value = 1
      const newCount = extractComparison.value.filter(e => e._status === 'new').length
      const diffCount = extractComparison.value.filter(e => e._status === 'different').length
      const matchCount = extractComparison.value.filter(e => e._status === 'matched').length
      message.success(`提取完成：新增 ${newCount}，有变化 ${diffCount}，已匹配 ${matchCount}`)
    }
  } catch (e) {
    console.error('实体提取失败', e)
    message.error('提取失败: ' + (e?.message || '未知错误'))
  } finally {
    extracting.value = false
  }
}

const handleSelectAllNew = () => {
  extractComparison.value.forEach((item, idx) => {
    if (item._status !== 'matched') extractSelected.value[idx] = true
  })
}

const handleDeselectAll = () => {
  extractSelected.value = {}
}

const handleImportExtracted = async () => {
  const selected = extractComparison.value.filter((_, idx) => extractSelected.value[idx])
  if (!selected.length) {
    message.warning('请选择要导入的实体')
    return
  }
  importing.value = true
  try {
    const res = await domainEntityBuilderApi.importExtractedEntities(
      selected, extractDomain.value
    )
    if (res.success) {
      message.success(res.message || `导入完成`)
      showExtractModal.value = false
      await loadData()
    }
  } catch (e) {
    console.error('导入失败', e)
    message.error('导入失败: ' + (e?.message || '未知错误'))
  } finally {
    importing.value = false
  }
}

const handleExtractCancel = () => {
  showExtractModal.value = false
  extractFile.value = null
  extractComparison.value = []
  extractSelected.value = {}
  extractStep.value = 0
}

const handleExtractBack = () => {
  extractStep.value = 0
  extractComparison.value = []
  extractSelected.value = {}
}

const handleExtractRedo = () => {
  extractStep.value = 0
  extractComparison.value = []
  extractSelected.value = {}
}

const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const domainLabel = (code) => {
  const found = domainOptions.value.find(d => d.value === code)
  return found ? found.label : code
}

</script>

<style scoped lang="less">
.domain-entity-builder-view {
  padding: 24px;
  background: var(--gray-50);
  min-height: 100vh;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  background: var(--gray-0);
  padding: 20px 24px;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);

  .header-title-row {
    display: flex;
    align-items: center;
    gap: 12px;
    .back-btn {
      display: flex; align-items: center; gap: 4px;
      color: var(--gray-600); padding: 4px 8px; height: auto;
      &:hover { color: var(--main-color); background: var(--gray-50); }
    }
  }
  h2 { margin: 0; font-size: 20px; font-weight: 600; color: var(--gray-1000); }
  .subtitle { margin: 4px 0 0; font-size: 13px; color: var(--gray-600); }
  .header-actions { display: flex; gap: 8px; align-items: center; }
}

.alert { margin-bottom: 16px; }

.main-content { display: flex; gap: 16px; height: calc(100vh - 200px); }

.left-panel {
  width: 340px;
  background: var(--gray-0);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  overflow: hidden;
  display: flex;
  flex-direction: column;

  .panel-header { margin-bottom: 16px; }
  .taxonomy-tree {
    flex: 1; overflow-y: auto;
    .tree-node-row {
      display: flex; align-items: center; gap: 4px;
      .tree-node-title { font-weight: 500; &.is-new { color: var(--main-color); font-style: italic; } }
      .tree-node-count { color: var(--gray-600); font-size: 12px; }
      .tree-delete-icon {
        color: var(--gray-400); font-size: 12px; margin-left: auto; opacity: 0; transition: opacity 0.2s;
        &:hover { color: #ff4d4f; }
      }
      &:hover .tree-delete-icon { opacity: 1; }
    }
  }
}

.right-panel {
  flex: 1;
  background: var(--gray-0);
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  overflow-y: auto;

  .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; }
  .schema-editor {
    .editor-section { margin-bottom: 24px; }
    .relation-rules-list .rule-item {
      padding: 12px; border: 1px solid var(--gray-200); border-radius: 6px; margin-bottom: 12px;
      .rule-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
      .rule-content {
        font-size: 12px;
        .rule-condition, .rule-actions {
          margin-bottom: 8px;
          code { display: block; padding: 8px; background: var(--gray-100); border-radius: 4px; margin-top: 4px; font-family: 'Courier New', monospace; }
        }
      }
    }
    .editor-actions { margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--gray-200); }
  }
}

.json-viewer {
  .json-actions { margin-bottom: 16px; display: flex; justify-content: flex-end; }
  .json-content {
    background: var(--gray-50); border: 1px solid var(--gray-200); border-radius: 6px;
    padding: 16px; max-height: 600px; overflow: auto;
    font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.6;
    white-space: pre-wrap; word-wrap: break-word; color: var(--gray-1000);
  }

  .extract-file-info {
    margin-top: 12px; padding: 8px 12px;
    background: var(--gray-50); border-radius: 6px;
    display: flex; align-items: center; gap: 8px; font-size: 13px;
  }

  .extract-results-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px; padding-bottom: 12px;
    border-bottom: 1px solid var(--gray-200);
  }

  .extract-empty { padding: 40px 0; }

  .extract-results-list {
    max-height: 500px; overflow-y: auto;
    display: flex; flex-direction: column; gap: 12px;
  }

  .extract-result-card {
    .extract-result-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      margin-bottom: 8px;
      .extract-check, .extract-check-placeholder {
        flex-shrink: 0; width: 22px; margin-right: 4px;
      }
      .extract-result-name {
        font-weight: 600; font-size: 15px; color: var(--gray-900);
        flex: 1;
      }
      &:not(:last-child) { margin-bottom: 8px; }
    }
    .extract-result-text {
      font-size: 13px; color: var(--gray-600); padding: 8px;
      background: var(--gray-50); border-radius: 4px; margin-bottom: 8px;
    }
    .extract-result-values { margin-top: 4px; }

    .extract-diff {
      background: var(--gray-50); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;
      .diff-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: var(--gray-700); }
      .diff-row {
        display: flex; align-items: center; gap: 8px; font-size: 13px; margin: 3px 0;
        .diff-field { font-weight: 600; color: var(--gray-800); min-width: 120px; }
        .diff-old { color: var(--danger-color, #ff4d4f); text-decoration: line-through; background: #fff2f0; padding: 1px 6px; border-radius: 3px; }
        .diff-arrow { color: var(--gray-400); }
        .diff-new { color: var(--success-color, #52c41a); background: #f6ffed; padding: 1px 6px; border-radius: 3px; }
      }
    }

    .extract-matched-hint {
      font-size: 13px; color: var(--gray-500); padding: 6px 0; margin-bottom: 4px;
    }
  }

  .extract-card-new { border-left: 3px solid var(--purple-color, #722ed1); }
  .extract-card-matched { border-left: 3px solid var(--success-color, #52c41a); opacity: 0.75; }
  .extract-card-different { border-left: 3px solid var(--warning-color, #fa8c16); }

  .extract-import-bar {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 16px; padding: 12px 16px;
    background: var(--main-color); border-radius: 8px;
    color: #fff;
    a-button { margin-left: auto; }
  }
}
</style>
