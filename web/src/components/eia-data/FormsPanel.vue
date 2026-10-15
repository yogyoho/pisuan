<template>
  <div class="ewp forms-panel">
    <!-- 页头（原型 s13：MessageSquareQuote + 待导出 pill + 导出物化） -->
    <div class="page-head">
      <div class="ph-icon"><MessageSquareQuote :size="18" /></div>
      <div>
        <h2>句式范式</h2>
        <div class="ph-sub">
          forms_catalog.json · 三族句式（口径消歧 / 数值引用 / 表题引导）· 写手按场景取 templates
          渲染
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange">
          <span class="dot dot-warn"></span>{{ pendingCount }} 行待导出
        </span>
        <button
          v-if="userStore.isAdmin"
          class="btn btn-pri btn-sm"
          :disabled="!pendingCount"
          @click="exportOpen = true"
        >
          导出物化
        </button>
      </div>
    </div>

    <a-spin v-if="loading" style="display: block; margin: 48px auto" />
    <div v-else-if="!overview" class="empty-state">
      <a-empty description="句式范式加载失败" />
    </div>
    <template v-else>
      <div class="family-grid">
        <div v-for="fam in families" :key="fam.asset_id" class="card">
          <div class="card-hd">
            <h3 class="mono">{{ fam.asset_id }}</h3>
            <span class="pill pill-gray" style="margin-left: auto">
              {{ displayValue(fam).templates.length }} 模板
            </span>
            <span v-if="fam.has_draft" class="pill pill-orange">
              <span class="dot dot-warn"></span>待导出
            </span>
          </div>
          <div class="fam-desc-row">
            <span>{{ displayValue(fam).desc }}</span>
            <button class="btn btn-txt btn-sm" @click="openDescEdit(fam)">改简介</button>
          </div>
          <div class="sub-h">templates · 写手消费（可编辑）</div>
          <div v-for="(t, i) in displayValue(fam).templates" :key="i" class="tpl-row">
            <span class="no">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="tx">{{ t }}</span>
            <button class="btn btn-txt btn-sm" @click="openTplEdit(fam, i)">改</button>
            <button class="btn btn-txt btn-sm" :disabled="deleting" @click="confirmDelete(fam, i)">
              删
            </button>
          </div>
          <div class="tpl-row">
            <span class="no">+</span>
            <button class="btn btn-txt btn-sm" @click="openTplEdit(fam, -1)">新增模板句式…</button>
          </div>
          <div class="sub-h">stats · 语料统计（只读）</div>
          <div class="stat-strip">
            <template v-if="Object.keys(statsOf(fam)).length">
              <span v-for="(v, k) in statsOf(fam)" :key="k" class="st" :class="{ hot: v >= 0.5 }"
                >{{ k }} {{ (v * 100).toFixed(1) }}%</span
              >
            </template>
            <span v-else class="st">31 份语料 · 该族无统计产出</span>
          </div>
          <div class="sub-h valve">导出安全阀</div>
          <div class="edt-meta">
            <span>仅写 desc / templates</span>
            <span class="field-src file" style="margin-left: auto">stats / examples 字节不动</span>
          </div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          bank_compile 重算会整文件重写 forms_catalog.json：草稿落库后若检测到 base_hash
          漂移（文件被语料脚本重算），导出预览会示警「文件已漂移」，确认导出即以草稿为准恢复。
        </span>
      </div>
    </template>

    <!-- 设值弹窗（desc / 模板句式共用） -->
    <a-modal
      v-model:open="editModal.open"
      :title="editModal.title"
      :confirm-loading="editModal.saving"
      @ok="submitEdit"
    >
      <div class="frm">
        <div class="frm-row">
          <label>{{ editModal.isDesc ? '族简介（desc）' : '模板句式' }}</label>
          <a-textarea v-model:value="editModal.value" :rows="3" />
        </div>
        <div class="frm-help">
          保存即写入该族草稿（desc / templates 两键），admin「导出物化」后回写 forms_catalog.json
        </div>
      </div>
    </a-modal>

    <ParadigmExportModal v-model:open="exportOpen" @exported="fetchAll" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Info, MessageSquareQuote } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'
import { useUserStore } from '@/stores/user'
import ParadigmExportModal from './ParadigmExportModal.vue'

const KIND = 'forms_catalog'
const FAMILY_LABELS = {
  caliber_disambiguation: '口径消歧',
  numeric_citation: '数值引用',
  table_lead: '表题引导'
}

const userStore = useUserStore()
const loading = ref(true)
const overview = ref(null)
const assets = ref({})
const exportOpen = ref(false)
const deleting = ref(false)
const editModal = reactive({
  open: false,
  saving: false,
  title: '',
  isDesc: false,
  family: '',
  index: -1,
  value: ''
})

const families = computed(() => overview.value?.families ?? [])
const pendingCount = computed(() => families.value.filter((f) => f.has_draft).length)

const fetchAll = async () => {
  loading.value = true
  try {
    overview.value = await eiaParadigmApi.loadOverview()
    const results = await Promise.all(
      families.value.map((f) => eiaParadigmApi.getAsset(KIND, f.asset_id))
    )
    assets.value = Object.fromEntries(results.map((r) => [r.asset_id, r]))
  } catch (e) {
    message.error(`获取句式范式失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

// 有草稿时草稿即编辑真相（desc/templates 两键），否则回落文件值
const displayValue = (fam) => {
  const draft = assets.value[fam.asset_id]?.draft
  if (draft) return draft.content
  return { desc: fam.desc, templates: fam.templates }
}

// stats 只读，来自 getAsset 的 family 四键（overview 不含 stats）
const statsOf = (fam) => assets.value[fam.asset_id]?.family?.stats ?? {}

const openDescEdit = (fam) => {
  editModal.isDesc = true
  editModal.family = fam.asset_id
  editModal.index = -1
  editModal.title = `族简介 · ${FAMILY_LABELS[fam.asset_id] ?? fam.asset_id}`
  editModal.value = displayValue(fam).desc
  editModal.open = true
}

const openTplEdit = (fam, index) => {
  editModal.isDesc = false
  editModal.family = fam.asset_id
  editModal.index = index
  const label = FAMILY_LABELS[fam.asset_id] ?? fam.asset_id
  editModal.title =
    index < 0
      ? `新增模板 · ${label}`
      : `模板 ${String(index + 1).padStart(2, '0')} · ${fam.asset_id}`
  editModal.value = index < 0 ? '' : displayValue(fam).templates[index]
  editModal.open = true
}

const submitEdit = async () => {
  const value = editModal.value.trim()
  if (!value) {
    message.warning(editModal.isDesc ? '简介不能为空' : '模板句式不能为空')
    return
  }
  const fam = families.value.find((f) => f.asset_id === editModal.family)
  if (!fam) return
  const cur = displayValue(fam)
  let content
  if (editModal.isDesc) {
    content = { desc: value, templates: cur.templates }
  } else {
    const templates = [...cur.templates]
    if (editModal.index < 0) templates.push(value)
    else templates[editModal.index] = value
    content = { desc: cur.desc, templates }
  }
  editModal.saving = true
  try {
    await eiaParadigmApi.saveDraft(KIND, editModal.family, content)
    message.success('草稿已落库，待 admin 导出物化')
    editModal.open = false
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  } finally {
    editModal.saving = false
  }
}

const confirmDelete = (fam, index) => {
  Modal.confirm({
    title: '删除模板句式',
    content: '将从该族草稿中移除此行（未导出前可重新添加）。',
    okText: '删除',
    onOk: () => submitDelete(fam, index)
  })
}

const submitDelete = async (fam, index) => {
  if (deleting.value) return
  const cur = displayValue(fam)
  const content = { desc: cur.desc, templates: cur.templates.filter((_, j) => j !== index) }
  deleting.value = true
  try {
    await eiaParadigmApi.saveDraft(KIND, fam.asset_id, content)
    message.success('草稿已落库，待 admin 导出物化')
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  } finally {
    deleting.value = false
  }
}

onMounted(fetchAll)
</script>

<style lang="less" scoped>
.forms-panel {
  --hairline: var(--gray-200);
}

/* 本页形状（原型 s13）：三族卡片 grid / 模板行 / 统计条 —— 公共配方在 factory-ui.less */
.family-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  align-items: start;

  @media (max-width: 1280px) {
    grid-template-columns: 1fr;
  }

  .card-hd h3 {
    font-size: 13px;
  }
}

.fam-desc-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 2px 16px 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.7;

  span {
    flex: 1;
  }
}

.sub-h {
  padding: 10px 16px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--color-text-tertiary);
  border-top: 1px solid var(--hairline);
  margin-top: 6px;

  &.valve {
    border-bottom: 1px solid var(--hairline);
    margin-top: 0;
  }
}

.tpl-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 16px;

  & + .tpl-row {
    border-top: 1px dashed var(--hairline);
  }

  .no {
    width: 22px;
    flex: none;
    font-size: 11px;
    color: var(--color-text-tertiary);
    font-family: 'JetBrains Mono', Consolas, monospace;
    padding-top: 2px;
  }

  .tx {
    flex: 1;
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 13px;
    color: var(--color-text);
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
}

.stat-strip {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 2px 16px 12px;

  .st {
    font-size: 11px;
    font-family: 'JetBrains Mono', Consolas, monospace;
    color: var(--color-text-secondary);
    background: var(--gray-100);
    border-radius: 4px;
    padding: 2px 8px;

    &.hot {
      background: var(--main-50);
      color: var(--main-600);
    }
  }
}

.edt-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 16px;
  border-top: 1px solid var(--hairline);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* ── 编辑弹窗 ── */
.frm {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;

  .frm-row {
    display: flex;
    flex-direction: column;
    gap: 6px;

    label {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
  }

  .frm-help {
    font-size: 12px;
    color: var(--color-text-tertiary);
    line-height: 1.6;
  }
}
</style>

<style lang="less" src="./factory-ui.less"></style>
