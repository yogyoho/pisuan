<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Download, FileText, Inbox, Zap } from '@lucide/vue'
import { domainEntityBuilderApi } from '@/apis/domain_entity_builder_api'

const emit = defineEmits(['imported'])

const open = defineModel('open', { type: Boolean, default: false })

const extractStep = ref(0)
const extracting = ref(false)
const importing = ref(false)
const extractFile = ref(null)
const extractComparison = ref([])
const extractSelected = ref({})
const extractCoverage = ref(null)
const extractConfidenceThreshold = ref(0.6)

const countByStatus = (status) =>
  extractComparison.value.filter((item) => item._status === status).length

const hasProposalProblems = (item) => Boolean(item._proposed_entity?.problems?.length)

// 可导入 = 非"已一致"、有原文证据、提案无校验问题
const isImportable = (item) =>
  item._status !== 'matched' && item.grounded === true && !hasProposalProblems(item)

const importableCount = computed(() => extractComparison.value.filter(isImportable).length)
const invalidCount = computed(
  () =>
    extractComparison.value.filter((item) => item._status !== 'matched' && !isImportable(item))
      .length
)
const selectedCount = computed(() => Object.values(extractSelected.value).filter(Boolean).length)

const resetState = () => {
  extractStep.value = 0
  extractFile.value = null
  extractComparison.value = []
  extractSelected.value = {}
  extractCoverage.value = null
}

watch(open, (visible) => {
  if (visible) resetState()
})

const handleExtractUpload = (file) => {
  if (file.size > 5 * 1024 * 1024) {
    message.error('文件大小不能超过 5MB')
    return false
  }
  extractFile.value = file
  return false
}

const handleStartExtract = async () => {
  if (!extractFile.value) return
  extracting.value = true
  try {
    const res = await domainEntityBuilderApi.extractEntities(extractFile.value, 'general')
    if (res.success) {
      const data = res.data || {}
      extractComparison.value = data.comparison || data.entities || []
      extractCoverage.value = data.coverage || null
      extractConfidenceThreshold.value = data.confidence_threshold ?? 0.6
      extractSelected.value = {}
      extractComparison.value.forEach((item, index) => {
        if (isImportable(item) && (item.confidence ?? 0) >= extractConfidenceThreshold.value) {
          extractSelected.value[index] = true
        }
      })
      extractStep.value = 1
      message.success(
        `提取完成：新建提案 ${countByStatus('new')}，可补属性 ${countByStatus('partial')}，已一致 ${countByStatus('matched')}`
      )
    }
  } catch (e) {
    console.error('实体提取失败', e)
    message.error('提取失败: ' + (e?.message || '未知错误'))
  } finally {
    extracting.value = false
  }
}

const handleSelectAllNew = () => {
  extractComparison.value.forEach((item, index) => {
    if (isImportable(item)) extractSelected.value[index] = true
  })
}

const handleDeselectAll = () => {
  extractSelected.value = {}
}

const handleExtractBack = () => {
  extractStep.value = 0
  extractComparison.value = []
  extractSelected.value = {}
}

const handleImportExtracted = async () => {
  const selected = extractComparison.value.filter((_, index) => extractSelected.value[index])
  if (!selected.length) {
    message.warning('请选择要导入的实体')
    return
  }
  importing.value = true
  try {
    const res = await domainEntityBuilderApi.importExtractedEntities(selected, 'general')
    if (res.success) {
      if (res.rejected?.length) {
        message.warning(`${res.message}；首条拒绝原因：${res.rejected[0].reason}`)
      } else {
        message.success(res.message || '导入完成')
      }
      open.value = false
      emit('imported')
    }
  } catch (e) {
    console.error('导入失败', e)
    message.error('导入失败: ' + (e?.message || '未知错误'))
  } finally {
    importing.value = false
  }
}

const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<template>
  <a-modal
    v-model:open="open"
    title="AI 实体提取"
    width="900px"
    :footer="null"
    @cancel="resetState"
  >
    <a-steps :current="extractStep" size="small" style="margin-bottom: 24px">
      <a-step title="上传文档" />
      <a-step title="提取结果" />
    </a-steps>

    <!-- Step 1: Upload -->
    <div v-if="extractStep === 0">
      <a-form layout="vertical">
        <a-form-item label="上传文档" required>
          <a-upload-dragger
            :before-upload="handleExtractUpload"
            :show-upload-list="false"
            accept=".txt,.md,.json"
          >
            <p class="ant-upload-drag-icon"><Inbox :size="48" /></p>
            <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p class="ant-upload-hint">支持 TXT、Markdown 格式文档，最大 5MB</p>
          </a-upload-dragger>
          <div v-if="extractFile" class="extract-file-info">
            <FileText :size="13" /> {{ extractFile.name }} ({{ formatFileSize(extractFile.size) }})
          </div>
        </a-form-item>
        <a-form-item>
          <a-button
            type="primary"
            :loading="extracting"
            :disabled="!extractFile"
            style="width: 100%"
            @click="handleStartExtract"
          >
            <template #icon><Zap :size="14" /></template>
            开始提取
          </a-button>
        </a-form-item>
      </a-form>
    </div>

    <!-- Step 2: Comparison & Import -->
    <div v-if="extractStep === 1">
      <div class="extract-results-header">
        <a-space wrap>
          <a-tag color="blue">提取 {{ extractComparison.length }} 条</a-tag>
          <a-tag color="green">{{ countByStatus('matched') }} 已一致</a-tag>
          <a-tag color="orange">{{ countByStatus('partial') }} 可补属性</a-tag>
          <a-tag color="purple">{{ countByStatus('new') }} 新建提案</a-tag>
          <a-tag v-if="invalidCount" color="red">{{ invalidCount }} 不可导入</a-tag>
        </a-space>
        <a-space>
          <a-button size="small" :disabled="importableCount === 0" @click="handleSelectAllNew"
            >全选可导入</a-button
          >
          <a-button size="small" @click="handleDeselectAll">取消全选</a-button>
          <a-button size="small" @click="handleExtractBack">重新上传</a-button>
          <a-button size="small" type="primary" :loading="extracting" @click="handleExtractBack"
            >重新提取</a-button
          >
        </a-space>
      </div>

      <a-alert
        v-if="extractCoverage?.truncated"
        type="warning"
        show-icon
        class="extract-coverage"
        :message="`仅扫描前 ${extractCoverage.scanned_chars} 字符（全文 ${extractCoverage.content_chars} 字符），超出部分未参与提取`"
      />
      <a-alert
        type="info"
        show-icon
        class="extract-coverage"
        :message="`默认勾选：有原文证据、置信度 ≥ ${(extractConfidenceThreshold * 100).toFixed(0)}% 且通过校验的条目；提取结果只用于补全 Schema，实例值不入库`"
      />

      <div v-if="extractComparison.length === 0" class="extract-empty">
        <a-empty description="未提取到实体对象" />
      </div>
      <div v-else class="extract-results-list">
        <a-card
          v-for="(item, idx) in extractComparison"
          :key="idx"
          size="small"
          :class="['extract-result-card', 'extract-card-' + item._status]"
        >
          <div class="extract-result-header">
            <a-checkbox
              v-if="item._status !== 'matched'"
              v-model:checked="extractSelected[idx]"
              :disabled="!isImportable(item)"
              class="extract-check"
            />
            <template v-else><span class="extract-check-placeholder" /></template>
            <span class="extract-result-name">{{ item.name_cn || item.schema_ref }}</span>
            <a-space size="4" wrap>
              <a-tag v-if="item._status === 'new'" color="purple">新建提案</a-tag>
              <a-tag v-if="item._status === 'matched'" color="green">已一致</a-tag>
              <a-tag v-if="item._status === 'partial'" color="orange">
                补 {{ item._diff.add_properties.length }} 个属性
              </a-tag>
              <a-tag v-if="!item.grounded" color="red">原文未命中</a-tag>
              <a-tag
                :color="
                  item.confidence >= 0.8 ? 'green' : item.confidence >= 0.6 ? 'orange' : 'red'
                "
              >
                {{ ((item.confidence || 0) * 100).toFixed(0) }}%
              </a-tag>
              <a-tag>{{ item.schema_ref || '(提案)' }}</a-tag>
            </a-space>
          </div>

          <!-- 新建提案的问题说明 -->
          <div v-if="item._proposed_entity?.problems?.length" class="extract-problems">
            <div v-for="(problem, i) in item._proposed_entity.problems" :key="i">
              • {{ problem }}
            </div>
          </div>

          <!-- 建议补充的属性 -->
          <div v-if="item._diff?.add_properties?.length" class="extract-diff">
            <div class="diff-title">建议补充的属性定义：</div>
            <div v-for="prop in item._diff.add_properties" :key="prop.key" class="diff-row">
              <span class="diff-field">{{ prop.name_cn }} ({{ prop.key }})</span>
              <span class="diff-new">{{ prop.value_type }}</span>
              <span class="diff-old">示例：{{ prop.sample_value }}</span>
            </div>
          </div>

          <!-- 新建提案的实体信息 -->
          <div v-else-if="item._status === 'new'" class="extract-diff">
            <div class="diff-title">新建实体提案：</div>
            <div class="diff-row">
              <span class="diff-field">{{ item._proposed_entity?.entity_key }}</span>
              <span class="diff-new">{{ item._proposed_entity?.category }}</span>
              <span class="diff-old">
                {{ item._proposed_entity?.properties?.length || 0 }} 个属性
              </span>
            </div>
          </div>
          <div v-else-if="item._status === 'matched'" class="extract-matched-hint">
            属性已全部覆盖，无需写入
          </div>

          <div
            v-if="item.extracted_text"
            :class="['extract-result-text', { 'is-ungrounded': !item.grounded }]"
          >
            <strong>{{ item.grounded ? '原文' : '原文未命中（不可导入）' }}：</strong>
            {{ item.extracted_text }}
          </div>
          <div v-if="item.values && Object.keys(item.values).length" class="extract-result-values">
            <a-descriptions size="small" :column="2" bordered>
              <a-descriptions-item v-for="(val, key) in item.values" :key="key" :label="key">
                {{ typeof val === 'object' ? JSON.stringify(val) : val }}
              </a-descriptions-item>
            </a-descriptions>
          </div>
        </a-card>
      </div>

      <!-- Import button -->
      <div v-if="importableCount > 0" class="extract-import-bar">
        <a-space>
          已选 <strong>{{ selectedCount }}</strong> / 可导入 {{ importableCount }}
        </a-space>
        <a-button
          type="primary"
          :loading="importing"
          :disabled="selectedCount === 0"
          @click="handleImportExtracted"
        >
          <template #icon><Download :size="14" /></template>
          导入数据库（{{ selectedCount }}）
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.extract-file-info {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--gray-50);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.extract-results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--gray-200);
}

.extract-empty {
  padding: 40px 0;
}

.extract-results-list {
  max-height: 500px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.extract-result-card {
  .extract-result-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8px;
    .extract-check,
    .extract-check-placeholder {
      flex-shrink: 0;
      width: 22px;
      margin-right: 4px;
    }
    .extract-result-name {
      font-weight: 600;
      font-size: 15px;
      color: var(--gray-900);
      flex: 1;
    }
    &:not(:last-child) {
      margin-bottom: 8px;
    }
  }
  .extract-result-text {
    font-size: 13px;
    color: var(--gray-600);
    padding: 8px;
    background: var(--gray-50);
    border-radius: 4px;
    margin-bottom: 8px;
  }
  .extract-result-values {
    margin-top: 4px;
  }

  .extract-diff {
    background: var(--gray-50);
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 8px;
    .diff-title {
      font-weight: 600;
      font-size: 13px;
      margin-bottom: 6px;
      color: var(--gray-700);
    }
    .diff-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      margin: 3px 0;
      .diff-field {
        font-weight: 600;
        color: var(--gray-800);
        min-width: 120px;
      }
      .diff-old {
        color: var(--color-error-500);
        text-decoration: line-through;
        background: var(--color-error-50);
        padding: 1px 6px;
        border-radius: 3px;
      }
      .diff-arrow {
        color: var(--gray-400);
      }
      .diff-new {
        color: var(--color-success-500);
        background: var(--color-success-50);
        padding: 1px 6px;
        border-radius: 3px;
      }
    }
  }

  .extract-matched-hint {
    font-size: 13px;
    color: var(--gray-500);
    padding: 6px 0;
    margin-bottom: 4px;
  }
}

.extract-card-new {
  border-left: 3px solid var(--color-info-500);
}
.extract-card-matched {
  border-left: 3px solid var(--color-success-500);
  opacity: 0.75;
}
.extract-card-partial {
  border-left: 3px solid var(--color-warning-500);
}

.extract-import-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--main-color);
  border-radius: 8px;
  color: #fff; /* 中性白，不随主题 */
  a-button {
    margin-left: auto;
  }
}

.extract-coverage {
  margin-bottom: 12px;
}

.extract-problems {
  margin-bottom: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--color-error-50);
  color: var(--color-error-700);
  font-size: 13px;
}

.extract-result-text.is-ungrounded {
  background: var(--color-error-50);
  color: var(--color-error-700);
}
</style>
