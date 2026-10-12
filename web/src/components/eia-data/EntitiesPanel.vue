<template>
  <div class="entities-panel">
    <div class="card toolbar-card">
      <div class="toolbar">
        <span class="toolbar-label">实体补充（仅添加）</span>
        <span style="flex: 1"></span>
        <span v-if="pendingCount" class="pill-warn-tag">
          <span class="dot"></span>{{ pendingCount }} 项待导出
        </span>
        <a-button
          v-if="userStore.isAdmin"
          type="primary"
          :disabled="!pendingCount"
          :loading="exporting"
          @click="onExport"
        >
          导出物化
        </a-button>
      </div>
    </div>

    <div class="split">
      <!-- 左：样例清单 -->
      <div class="card fam-list">
        <div class="fam-search">
          <a-input-search v-model:value="sampleQuery" placeholder="搜索样例…" allow-clear />
        </div>
        <div
          v-for="s in filteredSamples"
          :key="s.slug"
          class="fam-item"
          :class="{ on: s.slug === activeSlug }"
          @click="selectSample(s.slug)"
        >
          <span v-if="slugPending[s.slug]" class="mini-dot"></span>
          <span class="fam-name" :title="s.slug">{{ s.slug }}</span>
          <span class="fam-cnt">{{ totalOf(s.counts) }} 实体</span>
        </div>
        <div v-if="skipped.length" class="skipped-block">
          <div class="skipped-hd">skipped（不可补充）</div>
          <div v-for="s in skipped" :key="s.slug" class="skipped-item" :title="s.reason">
            {{ s.slug }}
          </div>
        </div>
        <div v-if="!filteredSamples.length && !loading" class="empty-state">
          <a-empty description="无匹配样例" />
        </div>
      </div>

      <!-- 右：实体注册表 -->
      <div class="card">
        <template v-if="registry">
          <div class="fam-hd">
            <h3>
              {{ registry.sample_slug }} <code class="k">{{ activeSlug }}</code>
            </h3>
            <span class="hd-sub">{{ entityTotal }} 实体 · 生成于 {{ registry.source }}</span>
          </div>

          <div v-for="t in ENTITY_TYPES" :key="t.key" class="etype-block">
            <div class="etype-hd">
              <span class="etype-name">{{ t.label }}</span>
              <code class="k">{{ t.key }}</code>
              <span class="etype-cnt">{{ registry.entities[t.key].length }}</span>
            </div>
            <div class="etype-items">
              <span
                v-for="e in registry.entities[t.key]"
                :key="`${t.key}-${e.name}`"
                class="ent-chip"
                :class="{ pending: e.pending }"
                :title="pendingTitle(e)"
              >
                {{ e.name }}
                <button
                  v-if="e.pending"
                  class="ent-x"
                  aria-label="撤回待导出补充"
                  @click="onWithdraw(e)"
                >
                  ×
                </button>
              </span>
              <span v-if="!registry.entities[t.key].length" class="unset">（空）</span>
              <a-button size="small" type="dashed" class="add-mini" @click="openAddModal(t)">
                <Plus :size="12" style="margin-right: 2px" />补充
              </a-button>
            </div>
          </div>

          <div v-if="registry.notes.length" class="notes-block">
            <div
              v-for="(n, i) in registry.notes"
              :key="i"
              class="note-line"
              v-html="mdLite(n)"
            ></div>
          </div>
        </template>
        <div v-else class="empty-state"><a-spin v-if="loading" /></div>
      </div>
    </div>

    <div class="note-bar">
      <Info :size="14" />
      <span>
        边界：仅添加（name/etype/rid
        溯源留档），文件锚点条目禁删禁改——生成时实体泄漏检测清单依赖其稳定； 导出物化追加至 registry
        数组尾并同步 _index 计数。
      </span>
    </div>

    <!-- 补充实体弹窗 -->
    <a-modal
      v-model:open="addModal.open"
      :title="`补充实体 · ${addModal.etypeLabel}`"
      :confirm-loading="addModal.saving"
      @ok="submitAdd"
    >
      <div class="frm">
        <div class="frm-row">
          <label>实体名称（name）</label>
          <a-input v-model:value="addModal.name" placeholder="实体全称，与报告原文一致" />
        </div>
        <div class="frm-row">
          <label>来源报告 rid（选填，溯源留档）</label>
          <a-input v-model:value="addModal.rid" placeholder="如 012-x" />
        </div>
        <div class="frm-row">
          <label>补充依据（note，选填）</label>
          <a-textarea v-model:value="addModal.note" :rows="3" placeholder="仅运营侧留档，不物化" />
        </div>
        <div class="frm-help">
          落库为待导出补充，admin「导出物化」后追加至 {{ activeSlug }} 注册表数组尾并更新 _index
          计数
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info, Plus } from '@lucide/vue'
import { eiaEntityApi } from '@/apis/eia_entity_api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const ENTITY_TYPES = [
  { key: 'projects', label: '项目' },
  { key: 'mines', label: '矿' },
  { key: 'orgs', label: '机构' },
  { key: 'places', label: '地名' },
  { key: 'sensitive', label: '敏感目标' }
]

const loading = ref(true)
const samples = ref([])
const skipped = ref([])
const sampleQuery = ref('')
const activeSlug = ref('')
const registry = ref(null)
const exporting = ref(false)

const filteredSamples = computed(() => {
  const q = sampleQuery.value.trim().toLowerCase()
  if (!q) return samples.value
  return samples.value.filter((s) => s.slug.toLowerCase().includes(q))
})

const totalOf = (counts) => Object.values(counts ?? {}).reduce((a, b) => a + b, 0)

const slugPending = computed(() => {
  const map = {}
  for (const s of samples.value) map[s.slug] = 0
  // 待导出计数仅限当前已加载注册表（其余样例懒加载，不预取）
  if (registry.value) map[registry.value.sample_slug] = pendingCount.value
  return map
})

const pendingCount = computed(() =>
  Object.values(registry.value?.entities ?? {}).reduce(
    (acc, items) => acc + items.filter((e) => e.pending).length,
    0
  )
)

const entityTotal = computed(() =>
  Object.values(registry.value?.entities ?? {}).reduce((acc, items) => acc + items.length, 0)
)

const pendingTitle = (e) =>
  e.pending ? `待导出补充（${e.rid ? `rid ${e.rid}` : ''}${e.note ? ` · ${e.note}` : ''}）` : e.name

// notes 里的 **加粗** 轻量渲染（生成侧标注惯例）
const mdLite = (t) =>
  t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')

const fetchSamples = async () => {
  loading.value = true
  try {
    const out = await eiaEntityApi.listSamples()
    samples.value = out.samples
    skipped.value = out.skipped
    if (!samples.value.some((s) => s.slug === activeSlug.value)) {
      activeSlug.value = samples.value[0]?.slug ?? ''
    }
    if (activeSlug.value) await fetchRegistry()
  } catch (e) {
    message.error(`获取样例清单失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

const fetchRegistry = async () => {
  try {
    registry.value = await eiaEntityApi.getRegistry(activeSlug.value)
  } catch (e) {
    message.error(`获取实体注册表失败: ${e.message}`)
  }
}

const selectSample = async (slug) => {
  activeSlug.value = slug
  registry.value = null
  await fetchRegistry()
}

// ── 补充实体 ──
const addModal = reactive({
  open: false,
  saving: false,
  etype: '',
  etypeLabel: '',
  name: '',
  rid: '',
  note: ''
})

const openAddModal = (t) => {
  addModal.etype = t.key
  addModal.etypeLabel = t.label
  addModal.name = ''
  addModal.rid = ''
  addModal.note = ''
  addModal.open = true
}

const submitAdd = async () => {
  if (!addModal.name.trim()) {
    message.warning('实体名称不能为空')
    return
  }
  addModal.saving = true
  try {
    await eiaEntityApi.addEntity(activeSlug.value, {
      etype: addModal.etype,
      name: addModal.name.trim(),
      rid: addModal.rid.trim() || null,
      note: addModal.note.trim() || null
    })
    message.success('实体补充已落库，待导出物化')
    addModal.open = false
    await fetchRegistry()
  } catch (e) {
    message.error(e.message)
  } finally {
    addModal.saving = false
  }
}

const onWithdraw = async (e) => {
  try {
    await eiaEntityApi.withdrawEntity(e.id)
    message.success('已撤回待导出补充（文件锚点不受影响）')
    await fetchRegistry()
  } catch (err) {
    message.error(err.message)
  }
}

const onExport = async () => {
  exporting.value = true
  try {
    const out = await eiaEntityApi.exportEntities()
    const materialized = Object.values(out.results).reduce((acc, r) => acc + r.materialized, 0)
    const skippedN = Object.values(out.results).reduce((acc, r) => acc + r.skipped, 0)
    message.success(
      `已写回 ${out.paths.join('、')}（物化 ${materialized} / 跳过已物化 ${skippedN}）；落运行栈技能目录，需人工回流 pisuan-custom`,
      6
    )
    await fetchSamples()
  } catch (e) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}

onMounted(fetchSamples)
</script>

<style lang="less" scoped>
.entities-panel {
  --hairline: var(--gray-200);
}

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.card {
  background: var(--gray-0);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
}

.toolbar-label {
  font-size: 12px;
  color: var(--gray-500);
}

.split {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 12px;
  align-items: start;
}

.fam-list {
  padding-bottom: 6px;
}

.fam-search {
  padding: 10px 12px;
  border-bottom: 1px solid var(--hairline);
}

.fam-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  position: relative;

  &:hover {
    background: var(--gray-50);
  }

  &.on {
    background: var(--main-0);

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 2px;
      background: var(--main-600);
    }
  }

  .fam-name {
    flex: 1;
    font-size: 13px;
    color: var(--gray-800);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .fam-key {
    color: var(--gray-400);
  }

  .fam-cnt {
    font-size: 11px;
    color: var(--gray-500);
    font-variant-numeric: tabular-nums;
  }
}

.mini-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--warn, #ad6800);
  flex: none;
}

.skipped-block {
  margin: 8px 12px 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--gray-100);

  .skipped-hd {
    font-size: 11px;
    color: var(--gray-400);
    margin-bottom: 4px;
  }

  .skipped-item {
    font-size: 12px;
    color: var(--gray-400);
    text-decoration: line-through;
  }
}

.fam-hd {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);

  h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.k {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--gray-100);
  color: var(--gray-600);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
}

.etype-block {
  padding: 10px 16px;

  & + .etype-block {
    border-top: 1px dashed var(--gray-100);
  }
}

.etype-hd {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;

  .etype-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--gray-700);
  }

  .etype-cnt {
    font-size: 11px;
    color: var(--gray-500);
    font-variant-numeric: tabular-nums;
  }
}

.etype-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.ent-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--hairline);
  background: var(--gray-50);
  color: var(--gray-700);

  &.pending {
    border-color: var(--warn-2, #ffe58f);
    background: var(--warn-0, #fff7e6);
    color: var(--warn, #ad6800);
  }

  .ent-x {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    font-size: 12px;
    line-height: 1;
    cursor: pointer;

    &:hover {
      background: rgba(0, 0, 0, 0.08);
    }
  }
}

.add-mini {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}

.unset {
  font-size: 12px;
  color: var(--gray-300);
}

.notes-block {
  padding: 10px 16px;
  border-top: 1px solid var(--hairline);

  .note-line {
    font-size: 12px;
    color: var(--gray-500);
    line-height: 1.7;

    & + .note-line {
      margin-top: 2px;
    }
  }
}

.pill-warn-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--warn, #ad6800);
  background: var(--warn-0, #fff7e6);
  border: 1px solid var(--warn-2, #ffe58f);

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--warn, #ad6800);
  }
}

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
      color: var(--gray-600);
    }
  }

  .frm-help {
    font-size: 12px;
    color: var(--gray-500);
    line-height: 1.6;
  }
}

.empty-state {
  padding: 32px 0;
}

.note-bar {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: var(--main-0);
  border-radius: 6px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--gray-600);

  svg {
    margin-top: 2px;
    flex: none;
    color: var(--main-600);
  }
}
</style>
