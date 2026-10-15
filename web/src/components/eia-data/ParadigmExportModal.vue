<template>
  <a-modal
    :open="open"
    title="导出物化 · 写前校验"
    :confirm-loading="exporting"
    :ok-text="'校验并写入（admin）'"
    :ok-button-props="{ disabled: !data?.all_ok || exporting }"
    @ok="onExport"
    @cancel="$emit('update:open', false)"
  >
    <a-spin v-if="loading" style="display: block; margin: 32px auto" />
    <template v-else-if="data">
      <div v-for="it in data.items" :key="it.kind + it.asset_id" style="margin-bottom: 14px">
        <div class="dif-hd">
          {{ label(it) }}
          <span v-if="it.drift" class="pill pill-warn">文件已漂移 · 以草稿为准恢复</span>
          <span v-else-if="it.ok" class="pill pill-ok">校验通过</span>
          <span v-else class="pill pill-err">校验未过</span>
        </div>
        <ul v-if="it.errors?.length" class="err-list">
          <li v-for="e in it.errors" :key="e">{{ e }}</li>
        </ul>
        <pre v-else class="dif-box">{{ it.diff || '（无字节变化）' }}</pre>
      </div>
      <div class="frm-help">
        写前校验：范式 md 锚点小节在位、专名扫描 0 命中、forms JSON 可解析；任一不过 →
        全批不写。round-trip：未改动的文件与键保持字节一致（不重排键序）。
      </div>
      <div class="residue-warn">
        <TriangleAlert :size="14" />
        <span
          >反模式表如有改动，需同步人工修订交付门残留词表（RESIDUE_RE）——先改门表，再同步范式，导出不联动。</span
        >
      </div>
    </template>
  </a-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { TriangleAlert } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['update:open', 'exported'])

const loading = ref(false)
const exporting = ref(false)
const data = ref(null)

const label = (it) =>
  it.kind === 'paradigm_md'
    ? `references/paradigms/${it.asset_id}.md · 草稿 → 文件`
    : `forms_catalog.json · ${it.asset_id} desc/templates 两键`

const load = async () => {
  loading.value = true
  try {
    data.value = await eiaParadigmApi.previewExport()
  } catch (e) {
    message.error(e.message)
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => v && load()
)

const onExport = async () => {
  exporting.value = true
  try {
    const out = await eiaParadigmApi.exportParadigms()
    message.success(
      `已写回 ${out.paths.join('、')}（落运行栈技能目录，需人工回流 pisuan-custom 走 git 评审）`,
      6
    )
    emit('update:open', false)
    emit('exported')
  } catch (e) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.dif-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.dif-box {
  max-height: 200px;
  overflow: auto;
  margin: 0 0 4px;
  padding: 10px 12px;
  background: var(--gray-50);
  border-radius: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.err-list {
  margin: 0 0 4px;
  padding-left: 18px;
  font-size: 12px;
  color: var(--color-error-700);
}

.frm-help {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.7;
}

.residue-warn {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  background: var(--color-warning-50);
  color: var(--color-warning-700);
  font-size: 12px;
  line-height: 1.6;
}
</style>
