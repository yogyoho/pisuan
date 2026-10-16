<template>
  <div class="ewp meta-panel">
    <!-- 页头（原型 s10：网格图标，同左侧导航 LayoutGrid + 待办 pill + 导出物化；导入存量为真实运营件，s10 无对应物） -->
    <div class="page-head">
      <div class="ph-icon">
        <LayoutGrid :size="18" />
      </div>
      <div>
        <h2>语料元数据标注</h2>
        <div class="ph-sub">
          corpus_meta · {{ counts.total }} 份样本语料的报告级元数据（年份 / 规模 · DB 标注层）
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="todoCount" class="pill pill-orange"
          ><span class="dot dot-warn"></span>{{ todoCount }} 项待标注</span
        >
        <template v-if="userStore.isAdmin">
          <button class="btn btn-sec btn-sm" :disabled="importing" @click="onImport">
            <RefreshCw :size="14" />{{ importing ? '导入中…' : '导入存量' }}
          </button>
          <button class="btn btn-pri btn-sm" :disabled="exporting" @click="onExport">
            <Download :size="14" />{{ exporting ? '导出中…' : '导出物化' }}
          </button>
        </template>
      </div>
    </div>

    <!-- 初始化骨架：指标带 4 格 + 工具条 + 表 7 列按真实布局占位（通用 .sk recipe 见 factory-ui），
         与词表页骨架同节奏——整页骨架→数据原子切换，防加载后版面跳动 -->
    <div v-if="loading && !items.length" class="meta-skeleton" aria-hidden="true">
      <div class="metric-strip">
        <div v-for="i in 4" :key="i" class="metric-cell">
          <span class="sk sk-line w-25"></span>
          <span class="sk sk-line value w-10"></span>
        </div>
      </div>
      <div class="card">
        <div class="toolbar">
          <span v-for="i in 6" :key="i" class="sk sk-chip"></span>
          <span style="flex: 1"></span>
          <span class="sk sk-inp"></span>
          <span class="sk sk-seg"></span>
        </div>
        <div v-for="i in 10" :key="i" class="sk-tbl-row" :class="{ hd: i === 1 }">
          <span
            v-for="j in 7"
            :key="j"
            class="sk sk-line"
            :class="['w-10', 'w-10', 'w-10', 'w-10', 'w-25', 'w-10', 'w-25'][j - 1]"
          ></span>
        </div>
      </div>
    </div>
    <template v-else-if="items.length || isFiltered">
      <!-- 指标带（原型 s10 四格：总数 / 已标注 / 待标注 / 覆盖省份；省份由标注聚合，缺失计入未标识） -->
      <div class="metric-strip">
        <div class="metric-cell">
          <span class="metric-label">样本总数</span>
          <span class="metric-value">{{ counts.total }}<small>份</small></span>
        </div>
        <div class="metric-cell">
          <span class="metric-label"><span class="dot dot-ok"></span>已标注</span>
          <span class="metric-value">{{ counts.annotated }}</span>
        </div>
        <div class="metric-cell" :class="{ warn: todoCount > 0 }">
          <span class="metric-label"><span class="dot dot-warn"></span>待标注</span>
          <span class="metric-value">{{ todoCount }}</span>
        </div>
        <div class="metric-cell accent">
          <span class="metric-label">覆盖省份</span>
          <span class="metric-value">{{ provinceCount }}</span>
        </div>
      </div>

      <div class="card">
        <!-- 工具条：阶段 chips + 搜索 + 标注态分段器 -->
        <div class="toolbar">
          <button
            v-for="c in stageChips"
            :key="c.key"
            class="stage-chip"
            :class="{ on: filters.stage === c.key }"
            @click="setStage(c.key)"
          >
            {{ c.label }} <span class="cnt">{{ c.count }}</span>
          </button>
          <span style="flex: 1"></span>
          <input
            v-model="filters.q"
            class="inp"
            style="width: 200px"
            placeholder="搜索 rid / 省份…"
          />
          <div class="seg">
            <button :class="{ on: filters.state === '' }" @click="setState('')">全部</button>
            <button :class="{ on: filters.state === 'annotated' }" @click="setState('annotated')">
              已标注
            </button>
            <button :class="{ on: filters.state === 'todo' }" @click="setState('todo')">
              待标注
            </button>
          </div>
        </div>

        <!-- 自绘表（rid/省份/阶段/年份/规模/标注状态/操作） -->
        <table class="tbl" :style="loading && items.length ? 'opacity: .55' : ''">
          <thead>
            <tr>
              <th style="width: 15%">rid</th>
              <th style="width: 8%">省份</th>
              <th style="width: 14%">阶段</th>
              <th style="width: 9%">年份</th>
              <th style="width: 20%">规模（Mt/a）</th>
              <th style="width: 13%">标注状态</th>
              <th class="r" style="width: 21%; padding-right: 20px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in filteredItems" :key="record.report_id">
              <td class="mono">{{ record.report_id }}</td>
              <td>
                <template v-if="record.province">{{ record.province }}</template>
                <span v-else class="miss" title="省份未标识（标注缺失计入未标识）">未标识</span>
              </td>
              <td>
                <span class="pill pill-gray pill-sm">{{ stageLabel(record.stage) }}</span>
              </td>
              <td class="num">
                <span
                  v-if="effYear(record) != null"
                  :title="
                    record.annotation.year_hint != null ? '人工标注（覆盖自动抽取）' : '自动抽取'
                  "
                  >{{ effYear(record) }}</span
                >
                <span v-else class="miss">缺年份</span>
              </td>
              <td>
                <template v-if="effScale(record) != null">
                  <span class="mono" style="font-size: 12px" :title="candidatesTitle(record)">{{
                    effScale(record)
                  }}</span>
                  <span
                    v-if="record.scale_basis === 'needs_review'"
                    class="dot dot-warn"
                    style="margin-left: 6px"
                    title="规模依据待复核（needs_review）"
                  ></span>
                </template>
                <span v-else class="miss">缺规模</span>
              </td>
              <td>
                <span
                  v-if="hasAnnotation(record)"
                  class="pill pill-ok"
                  :title="annotatedTitle(record)"
                  >已标注</span
                >
                <span v-else class="pill pill-warn">待标注</span>
              </td>
              <td class="r" style="padding-right: 20px">
                <button class="btn btn-txt btn-sm" @click="openAnnotate(record)">
                  {{ hasAnnotation(record) ? '查看' : '标注' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="tbl-foot">
          共 {{ counts.total }} 份 · 待标注 {{ todoCount }} · 标注写入 DB 覆盖层，导出物化重写
          corpus_meta_annotations.json 人工层（全量、rid 序）
        </div>
      </div>
    </template>

    <!-- 空态：库空意味着语料未导入运行栈（非筛选问题给出清除出口） -->
    <div v-else class="card">
      <div class="empty-state">
        <a-empty :description="emptyDesc">
          <button v-if="isFiltered" class="btn btn-sec btn-sm" @click="clearFilters">
            清除筛选
          </button>
        </a-empty>
      </div>
    </div>

    <div class="note-bar">
      <Info :size="14" />
      <span
        >标注（年份 / 规模）供写手取值与总览省份聚合；规模候选供 PPS
        项目参数对账，二者缺失都会在质量体检点名。</span
      >
    </div>

    <!-- 标注对话框（原型 metaModal：rid + 阶段 pill，frm 行式表单；可标注字段仅年份/规模/备注） -->
    <a-modal :open="dlg.open" :width="560" :footer="null" @cancel="dlg.open = false">
      <template #title>
        <span class="modal-title">标注 · {{ dlg.record?.report_id }}</span>
        <span v-if="dlg.record" class="pill pill-gray pill-sm" style="margin-left: 8px">{{
          stageLabel(dlg.record.stage)
        }}</span>
      </template>
      <div v-if="dlg.record" class="modal-bd">
        <p class="dlg-line">
          {{ dlg.record.province || '未标识' }} · 自动年份 {{ dlg.record.auto_year_hint ?? '—' }} ·
          自动规模
          {{ dlg.record.auto_scale_mt_a ?? '—' }}
          <template v-if="dlg.record.scale_basis === 'manual'">（规模已核实）</template>
          <template v-else-if="dlg.record.scale_basis === 'needs_review'"
            >（规模依据待复核）</template
          >
        </p>
        <div v-if="dlg.record.scale_candidates.length" class="cand-box">
          <span class="cand-title">规模候选簇（自动抽取，点击快填）：</span>
          <button
            v-for="(c, i) in dlg.record.scale_candidates"
            :key="i"
            class="cand-tag"
            @click="dlg.form.scale_mt_a = c.value"
          >
            {{ c.label }} {{ c.value }}
          </button>
        </div>
        <div class="frm-row">
          <label>年份 year_hint<span class="must">*</span></label>
          <input
            v-model.number="dlg.form.year_hint"
            class="inp mono"
            type="number"
            min="2000"
            max="2100"
            step="1"
          />
          <div class="frm-help">写手取值来源，2000–2100 整数；留空表示清除该项标注</div>
        </div>
        <div class="frm-row">
          <label>规模标注（万吨/年）</label>
          <input
            v-model.number="dlg.form.scale_mt_a"
            class="inp mono"
            type="number"
            min="0.1"
            max="10000"
            step="0.1"
          />
          <div class="frm-help">供 PPS 项目参数对账；(0, 10000]，留空表示清除该项标注</div>
        </div>
        <div class="frm-row" style="margin-bottom: 0">
          <label>备注（可选）</label>
          <textarea
            v-model="dlg.form.note"
            class="inp"
            rows="2"
            placeholder="裁决依据，如「来自第 3 章建设规模」"
          ></textarea>
        </div>
      </div>
      <div class="modal-ft">
        <button class="btn btn-sec" @click="dlg.open = false">取消</button>
        <button class="btn btn-pri" :disabled="dlg.submitting" @click="onSubmit">
          {{ dlg.submitting ? '保存中…' : '保存标注' }}
        </button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { Download, Info, LayoutGrid, RefreshCw } from '@lucide/vue'
import { eiaMetaApi } from '@/apis/eia_meta_api'
import { useUserStore } from '@/stores/user'

const STAGES = [
  { key: 'planning_eia', label: '规划环评' },
  { key: 'post_eia', label: '事后环评' },
  { key: 'project_eia_openpit', label: '项目环评·露天' },
  { key: 'project_eia_underground', label: '项目环评·井工' },
  { key: 'tracking_eia', label: '跟踪评价' }
]
const STAGE_LABELS = Object.fromEntries(STAGES.map((s) => [s.key, s.label]))

const userStore = useUserStore()
const route = useRoute()
const loading = ref(false)
const importing = ref(false)
const exporting = ref(false)
const items = ref([])
const counts = reactive({
  total: 0,
  annotated: 0,
  year_missing: 0,
  scale_missing: 0,
  scale_needs_review: 0
})
const filters = reactive({ state: '', stage: '', q: '' })
// 深链入口：/eia-data/meta?state=todo|annotated 直落对应筛选（总览页 chip 分流）
const deepState = String(route.query.state ?? '')
if (deepState === 'todo' || deepState === 'annotated') {
  filters.state = deepState
}

const stageLabel = (k) => STAGE_LABELS[k] || k
const hasAnnotation = (r) =>
  r.annotation && (r.annotation.year_hint != null || r.annotation.scale_mt_a != null)
const candidatesText = (r) => r.scale_candidates.map((c) => `${c.label} ${c.value}`).join('；')
const candidatesTitle = (r) => (r.scale_candidates.length ? `候选簇：${candidatesText(r)}` : '')
const annotatedTitle = (r) =>
  r.annotation.decided_by
    ? `由 ${r.annotation.decided_by} 标注${r.annotation.decided_at ? ` · ${r.annotation.decided_at}` : ''}`
    : ''
// 生效值 = 人工标注覆盖自动抽取（二者缺席才显示「缺」）
const effYear = (r) => r.annotation.year_hint ?? r.auto_year_hint
const effScale = (r) => r.annotation.scale_mt_a ?? r.auto_scale_mt_a

const todoCount = computed(() => counts.total - counts.annotated)
const provinceCount = computed(
  () => new Set(items.value.map((r) => r.province).filter(Boolean)).size
)

const stageChips = computed(() => [
  { key: '', label: '全部', count: counts.total },
  ...STAGES.map((s) => ({
    key: s.key,
    label: s.label,
    count: items.value.filter((r) => r.stage === s.key).length
  }))
])

const isFiltered = computed(() => Boolean(filters.state || filters.stage || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配报告' : '语料元数据为空'))

const filteredItems = computed(() => {
  let list = items.value
  if (filters.state === 'annotated') list = list.filter((r) => hasAnnotation(r))
  if (filters.state === 'todo') list = list.filter((r) => !hasAnnotation(r))
  if (filters.stage) list = list.filter((r) => r.stage === filters.stage)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    list = list.filter(
      (r) => r.report_id.toLowerCase().includes(q) || (r.province || '').toLowerCase().includes(q)
    )
  }
  return list
})

const setStage = (key) => {
  filters.stage = key
}
const setState = (state) => {
  filters.state = state
}
const clearFilters = () => {
  filters.state = ''
  filters.stage = ''
  filters.q = ''
}

const fetchList = async () => {
  loading.value = true
  try {
    const data = await eiaMetaApi.listReports()
    items.value = data.items
    Object.assign(counts, data.counts)
  } catch (e) {
    message.error(e?.message || '元数据加载失败')
  } finally {
    loading.value = false
  }
}

const onImport = async () => {
  importing.value = true
  try {
    const r = await eiaMetaApi.importAnnotations()
    if (r.skipped_unknown > 0) {
      message.warning(
        `导入完成：新增 ${r.added} 条；${r.skipped_unknown} 条 rid 不在语料清单，已跳过（请核对人工层文件）`
      )
    } else {
      message.success(`导入完成：文件 ${r.scanned} 条，新增 ${r.added} 条`)
    }
    await fetchList()
  } catch (e) {
    message.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const onExport = async () => {
  exporting.value = true
  message.loading({ content: '正在物化…', key: 'meta-export', duration: 0 })
  try {
    const r = await eiaMetaApi.exportAnnotations()
    message.success({
      content: `已重写人工层文件（${r.materialized} 条；落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'meta-export'
    })
  } catch (e) {
    message.error({ content: e?.message || '导出失败', key: 'meta-export' })
  } finally {
    exporting.value = false
  }
}

// ── 标注对话框 ──────────────────────────────────────────

const dlg = reactive({
  open: false,
  submitting: false,
  record: null,
  form: { year_hint: null, scale_mt_a: null, note: '' }
})

const openAnnotate = (record) => {
  dlg.record = record
  dlg.form.year_hint = record.annotation?.year_hint ?? null
  dlg.form.scale_mt_a = record.annotation?.scale_mt_a ?? null
  dlg.form.note = record.annotation?.note || ''
  dlg.open = true
}

const onSubmit = async () => {
  // number input 清空后是 ''，归一成 null 再走「留空清除」语义
  const norm = (v) => (v === '' || v == null ? null : v)
  const year_hint = norm(dlg.form.year_hint)
  const scale_mt_a = norm(dlg.form.scale_mt_a)
  const note = dlg.form.note || null
  if (year_hint == null && scale_mt_a == null && !hasAnnotation(dlg.record)) {
    message.warning('年份与规模至少标注一项（或留空保存以清除标注）')
    return
  }
  dlg.submitting = true
  try {
    await eiaMetaApi.setAnnotation(dlg.record.report_id, {
      annotations: Object.fromEntries(
        [
          ['year_hint', year_hint],
          ['scale_mt_a', scale_mt_a]
        ].filter(([, v]) => v != null)
      ),
      note
    })
    message.success(`「${dlg.record.report_id}」标注已保存`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '标注保存失败')
  } finally {
    dlg.submitting = false
  }
}

onMounted(fetchList)
</script>

<style lang="less" scoped>
/* 语料元数据字段长度可控（rid/省份/数值），但 % 列宽需固定布局才生效——同 s9 结论 */
.meta-panel .tbl {
  table-layout: fixed;

  td {
    overflow-wrap: break-word;
  }
}

.miss {
  color: var(--second-600);
  font-size: 12px;
}

.empty-state {
  padding: 48px 0;
  text-align: center;
}

/* ── 标注对话框（原型 frm 行式表单，仅本页使用故 scoped 自绘） ── */
.modal-title {
  font-size: 15px;
  font-weight: 600;
}

.modal-bd {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dlg-line {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.cand-box {
  padding: 8px 10px;
  margin-bottom: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-50);

  .cand-title {
    display: block;
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--color-text-tertiary);
  }

  .cand-tag {
    margin: 0 6px 4px 0;
    padding: 2px 8px;
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    background: var(--gray-0);
    font-size: 12px;
    font-family: ui-monospace, 'Cascadia Code', Consolas, 'Courier New', monospace;
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      color: var(--main-600);
      border-color: var(--main-400);
      background: var(--main-50);
    }
  }
}

.frm-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 12px;

  label {
    font-size: 13px;
    font-weight: 500;
    color: var(--color-text);
  }

  .must {
    margin-left: 2px;
    color: var(--color-error-500);
  }

  .inp {
    width: 100%;
  }

  textarea.inp {
    height: auto;
    padding: 6px 10px;
    resize: vertical;
    line-height: 1.5;
  }
}

.frm-help {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.modal-ft {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

/* 初始化骨架：本页形状（通用 .sk/.sk-line recipe 在 factory-ui；.sk-tbl-row 同词表页配方） */
.sk-inp {
  width: 200px;
  height: 30px;
  border-radius: 6px;
}

.sk-chip {
  width: 72px;
  height: 24px;
  border-radius: 999px;
}

.sk-seg {
  width: 140px;
  height: 24px;
  border-radius: 6px;
}

.sk-tbl-row {
  display: flex;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid var(--gray-100);

  &.hd .sk-line {
    height: 11px;
  }
}
</style>

<style lang="less" src="./factory-ui.less"></style>
