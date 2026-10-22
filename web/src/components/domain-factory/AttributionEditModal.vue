<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 改判弹窗：region_label 必填 / region_key 可选（候选+可输入新建 slug）/ scope 三选
const props = defineProps({
  open: { type: Boolean, default: false },
  task: { type: Object, default: null },
  usedKeys: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'edited'])

// 与 backend/package/pisuan/services/domain_factory_region.py 的 REGION_VOCAB 同源（17 slug，人工同步）
const REGION_KEY_OPTIONS = [
  'hengcheng',
  'yining-beiqu',
  'wujianfang',
  'naomaohu',
  'shajingzi',
  'santanghu',
  'lingtai',
  'yimin',
  'shengli',
  'weizhou',
  'huating',
  'gaotouyao',
  'hegang',
  'nalinxili',
  'qitaihe',
  'yakeshi-wujiu',
  'dongsheng'
]
const SCOPE_OPTIONS = [
  { value: 'regional', label: 'regional（区域级：知识归入区域库，多项目共用）' },
  { value: 'project', label: 'project（项目级：知识仅归入单项目）' },
  { value: 'universal', label: 'universal（通用：跨区域跨项目复用）' }
]
const SLUG_RE = /^[a-z0-9-]+$/

const regionLabel = ref('')
const regionKey = ref('')
const scope = ref('regional')
const submitting = ref(false)

watch(
  () => props.open,
  (v) => {
    if (v && props.task) {
      regionLabel.value = props.task.region_label || ''
      regionKey.value = props.task.region_key || ''
      scope.value = props.task.scope || 'regional'
    }
  }
)

const keyOptions = computed(() => {
  const s = new Set([...REGION_KEY_OPTIONS, ...props.usedKeys])
  if (regionKey.value) s.add(regionKey.value)
  return [...s].map((k) => ({ value: k }))
})

const handleOk = async () => {
  if (!props.task) return
  if (!regionLabel.value.trim()) {
    message.warning('region_label 不能为空')
    return
  }
  const key = regionKey.value.trim()
  if (key && !SLUG_RE.test(key)) {
    message.warning('region_key 只允许小写字母/数字/连字符（slug 格式）')
    return
  }
  submitting.value = true
  try {
    const res = await domainFactoryApi.confirmRegion(props.task.id, {
      region_label: regionLabel.value.trim(),
      region_key: key || null,
      scope: scope.value
    })
    emit('edited', res)
  } catch (e) {
    message.error('归属确认失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="task && task.region_key ? `改判归属 · ${task.file_name}` : `归属确认 · ${task?.file_name || ''}`"
    :confirm-loading="submitting"
    :ok-text="task && task.region_key ? '确认改判' : '确认归属'"
    @ok="handleOk"
    @cancel="emit('close')"
  >
    <div class="edit-form">
      <div class="form-row">
        <span class="form-label">region_label *</span>
        <a-input v-model:value="regionLabel" placeholder="区域展示名（如：横城矿区）" />
      </div>
      <div class="form-row">
        <span class="form-label">region_key</span>
        <a-auto-complete
          v-model:value="regionKey"
          :options="keyOptions"
          placeholder="slug，可从候选选择或输入新建；留空则按 label 反查词表"
        />
      </div>
      <div class="form-row">
        <span class="form-label">scope *</span>
        <a-radio-group v-model:value="scope">
          <a-radio v-for="o in SCOPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</a-radio>
        </a-radio-group>
      </div>
      <a-alert
        type="warning"
        show-icon
        message="确认后将级联：该任务全部未退役事实覆盖回填 region 并 draft→confirmed；归因集内模板按 min-permissive 重算。"
      />
    </div>
  </a-modal>
</template>

<style lang="less" scoped>
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-label {
  display: inline-block;
  width: 100px;
  color: var(--gray-500, #64748b);
}
</style>
