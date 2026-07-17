<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { regulationApi } from './regulation_api'
import { databaseApi } from '@/apis/knowledge_api'

const visible = defineModel('open', { type: Boolean, default: false })

const kbList = ref([])
const fileList = ref([])
const form = ref({
  kb_id: '',
  file_id: '',
  doc_code: '',
  doc_name: '',
  doc_type: 'technical_standard'
})
const enriching = ref(false)
const result = ref(null)

const DOC_TYPES = [
  { value: 'technical_standard', label: '技术规范/标准' },
  { value: 'law', label: '法律' },
  { value: 'admin_regulation', label: '行政法规' },
  { value: 'ministry_rule', label: '部门规章' },
  { value: 'local_rule', label: '地方规章' },
  { value: 'national_plan', label: '国家规划' },
  { value: 'local_plan', label: '地方规划' },
  { value: 'project_material', label: '项目资料' }
]

const loadKbs = async () => {
  try {
    const res = await databaseApi.getDatabases()
    kbList.value = (res.databases || []).filter(
      (db) => db.kb_type === 'milvus' || db.type === 'milvus'
    )
  } catch {
    message.error('加载知识库失败')
  }
}

const loadFiles = async () => {
  form.value.file_id = ''
  fileList.value = []
  if (!form.value.kb_id) return
  try {
    const res = await databaseApi.getDatabaseInfo(form.value.kb_id)
    fileList.value = Object.values(res.files || {})
  } catch {
    message.error('加载文件列表失败')
  }
}

const runEnrich = async () => {
  const f = form.value
  if (!f.kb_id || !f.file_id || !f.doc_code) {
    message.warning('请选择知识库、文件并填写文档编号')
    return
  }
  enriching.value = true
  result.value = null
  try {
    const res = await regulationApi.enrichFile(f)
    result.value = res.result
    message.success(`加工完成: ${res.result.units} 个结构单元, ${res.result.indicators} 条指标`)
  } catch (e) {
    message.error('加工失败: ' + (e.message || e))
  } finally {
    enriching.value = false
  }
}
</script>

<template>
  <a-drawer
    v-model:open="visible"
    title="标准规范库加工"
    width="520"
    @after-open-change="(o) => o && loadKbs()"
  >
    <a-alert
      type="info"
      show-icon
      style="margin-bottom: 16px"
      message="先在知识库管理中上传规范文档并完成索引，再在此处执行结构化加工。"
    />
    <a-form layout="vertical">
      <a-form-item label="知识库" required>
        <a-select
          v-model:value="form.kb_id"
          placeholder="选择存放规范文档的知识库"
          @change="loadFiles"
        >
          <a-select-option v-for="kb in kbList" :key="kb.kb_id" :value="kb.kb_id">{{
            kb.name
          }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="文件" required>
        <a-select v-model:value="form.file_id" placeholder="选择已索引完成的规范文档">
          <a-select-option v-for="f in fileList" :key="f.file_id" :value="f.file_id">{{
            f.filename
          }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="文档编号" required>
        <a-input v-model:value="form.doc_code" placeholder="如 GB 3095-2012 / 水保[2013]188号" />
      </a-form-item>
      <a-form-item label="文档名称">
        <a-input v-model:value="form.doc_name" placeholder="如 环境空气质量标准" />
      </a-form-item>
      <a-form-item label="文档类型">
        <a-select v-model:value="form.doc_type">
          <a-select-option v-for="t in DOC_TYPES" :key="t.value" :value="t.value">{{
            t.label
          }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-button type="primary" block :loading="enriching" @click="runEnrich">开始加工</a-button>
    </a-form>

    <a-divider />
    <template v-if="result">
      <a-descriptions title="加工结果" :column="1" size="small">
        <a-descriptions-item label="结构单元">{{ result.units }}</a-descriptions-item>
        <a-descriptions-item label="限值表">{{ result.tables }}</a-descriptions-item>
        <a-descriptions-item label="提取指标">{{ result.indicators }}</a-descriptions-item>
        <a-descriptions-item label="图谱节点">{{ result.graph?.nodes || 0 }}</a-descriptions-item>
      </a-descriptions>
    </template>
  </a-drawer>
</template>
