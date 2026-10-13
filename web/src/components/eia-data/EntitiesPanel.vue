<template>
  <div class="ewp entities-panel">
    <!-- 页头（原型 s6：Package + 添加实体 + 导出物化） -->
    <div class="page-head">
      <button class="back-btn" aria-label="返回数据工厂总览" @click="goOverview">
        <ArrowLeft :size="16" />
      </button>
      <div class="ph-icon">
        <Package :size="18" />
      </div>
      <div>
        <h2>样例实体注册表</h2>
        <div class="ph-sub">
          sample_entities · 写手实体泄漏检测的禁用词库（{{ samples.length }} 份样本语料提取）
        </div>
      </div>
      <div class="ph-actions">
        <button class="btn btn-pri btn-sm" @click="openAddModal">
          <Plus :size="14" />添加实体
        </button>
        <button
          v-if="userStore.isAdmin"
          class="btn btn-sec btn-sm"
          :disabled="!pendingCount"
          @click="onExport"
        >
          <Download :size="14" />{{ exporting ? '导出中…' : '导出物化' }}
        </button>
      </div>
    </div>

    <!-- 指标条（写作期命中拦截无数据，不虚构） -->
    <div v-if="registry" class="metric-strip">
      <div class="metric-cell">
        <span class="metric-label">注册实体</span>
        <span class="metric-value">{{ entityTotal }}</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">实体类型</span>
        <span class="metric-value">{{ presentTypes }}<small>类</small></span>
      </div>
      <div class="metric-cell" :class="{ warn: pendingCount > 0 }">
        <span class="metric-label"><span class="dot dot-warn"></span>本批新增待导出</span>
        <span class="metric-value">{{ pendingCount }}</span>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <a-select
          v-model:value="activeSlug"
          style="width: 200px"
          :disabled="loading"
          @change="fetchRegistry"
        >
          <a-select-option v-for="s in samples" :key="s.slug" :value="s.slug">
            {{ s.slug }}
          </a-select-option>
          <a-select-option v-for="s in skipped" :key="s.slug" :value="s.slug" disabled>
            {{ s.slug }}（不可补充）
          </a-select-option>
        </a-select>
        <input v-model="query" class="inp" style="width: 220px" placeholder="搜索实体名 / rid…" />
        <div class="seg">
          <button :class="{ on: etypeFilter === 'all' }" @click="etypeFilter = 'all'">全部</button>
          <button
            v-for="t in ENTITY_TYPES"
            :key="t.key"
            :class="{ on: etypeFilter === t.key }"
            @click="etypeFilter = t.key"
          >
            {{ t.label }}
          </button>
        </div>
      </div>

      <table v-if="registry" class="tbl">
        <thead>
          <tr>
            <th>实体名</th>
            <th style="width: 110px">类型</th>
            <th style="width: 140px">来源样本 rid</th>
            <th style="width: 170px">添加人</th>
            <th style="width: 120px">状态</th>
            <th class="r" style="padding-right: 20px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in flatEntities" :key="`${e.etype}-${e.name}`">
            <td :title="pendingTitle(e)">{{ e.name }}</td>
            <td>
              <span class="pill pill-gray pill-sm">{{ e.etypeLabel }}</span>
            </td>
            <td class="mono">{{ e.rid || registry.sample_slug }}</td>
            <td>{{ e.decided_by || (e.id == null ? '语料提取' : '—') }}</td>
            <td>
              <span v-if="e.pending" class="pill pill-warn">新增 · 未导出</span>
              <span v-else class="pill pill-ok">在册</span>
            </td>
            <td class="r" style="padding-right: 20px">
              <button
                v-if="e.pending && e.id != null"
                class="btn btn-txt btn-sm withdraw-btn"
                @click="onWithdraw(e)"
              >
                撤回
              </button>
            </td>
          </tr>
          <tr v-if="!flatEntities.length">
            <td
              colspan="6"
              style="text-align: center; padding: 24px 0; color: var(--color-text-tertiary)"
            >
              该样例暂无匹配实体
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state"><a-spin v-if="loading" /></div>

      <div v-if="registry" class="tbl-foot">
        禁删既有条目——删除等于放行实体泄漏；确需移除走工程侧评审并附泄漏复扫报告（仅可撤回本人未导出的新增行）
      </div>
    </div>

    <!-- 补充实体弹窗 -->
    <a-modal
      v-model:open="addModal.open"
      title="添加实体"
      :confirm-loading="addModal.saving"
      @ok="submitAdd"
    >
      <div class="frm">
        <div class="frm-row">
          <label>实体类型（etype）</label>
          <a-select v-model:value="addModal.etype" style="width: 100%">
            <a-select-option v-for="t in ENTITY_TYPES" :key="t.key" :value="t.key">
              {{ t.label }}
            </a-select-option>
          </a-select>
        </div>
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
import { ArrowLeft, Download, Package, Plus } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { eiaEntityApi } from '@/apis/eia_entity_api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()

const goOverview = () => router.push('/domain-factory/eia-data')

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
const activeSlug = ref('')
const registry = ref(null)
const exporting = ref(false)
const query = ref('')
const etypeFilter = ref('all')

const pendingCount = computed(() =>
  Object.values(registry.value?.entities ?? {}).reduce(
    (acc, items) => acc + items.filter((e) => e.pending).length,
    0
  )
)

const entityTotal = computed(() =>
  Object.values(registry.value?.entities ?? {}).reduce((acc, items) => acc + items.length, 0)
)

const presentTypes = computed(
  () => Object.values(registry.value?.entities ?? {}).filter((items) => items.length).length
)

// 注册表按类型分组的条目平铺成表行（原型 s6 FLAT），待导出排前
const flatEntities = computed(() => {
  if (!registry.value) return []
  const q = query.value.trim().toLowerCase()
  const rows = []
  for (const t of ENTITY_TYPES) {
    if (etypeFilter.value !== 'all' && etypeFilter.value !== t.key) continue
    for (const e of registry.value.entities[t.key] ?? []) {
      if (q && !e.name.toLowerCase().includes(q) && !(e.rid ?? '').toLowerCase().includes(q)) {
        continue
      }
      rows.push({ ...e, etype: t.key, etypeLabel: t.label })
    }
  }
  return rows.sort((a, b) => Number(b.pending) - Number(a.pending))
})

const pendingTitle = (e) =>
  e.pending ? `待导出补充（${e.rid ? `rid ${e.rid}` : ''}${e.note ? ` · ${e.note}` : ''}）` : e.name

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
  if (!activeSlug.value) return
  registry.value = null
  try {
    registry.value = await eiaEntityApi.getRegistry(activeSlug.value)
  } catch (e) {
    message.error(`获取实体注册表失败: ${e.message}`)
  }
}

// ── 补充实体 ──
const addModal = reactive({
  open: false,
  saving: false,
  etype: ENTITY_TYPES[0].key,
  name: '',
  rid: '',
  note: ''
})

const openAddModal = () => {
  addModal.etype = ENTITY_TYPES[0].key
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
.withdraw-btn {
  color: var(--second-600);

  &:hover {
    background: var(--second-50);
  }
}

/* ── 添加实体弹窗 ── */
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
