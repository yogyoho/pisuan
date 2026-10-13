<template>
  <div class="ewp standards-panel">
    <!-- 页头（原型 s11：盾形图标 + 待导出 pill + 双通道导出） -->
    <div class="page-head">
      <div class="ph-icon">
        <ShieldCheck :size="18" />
      </div>
      <div>
        <h2>标准与限值库</h2>
        <div class="ph-sub">
          standards_index 核实闭环 + 限值查找表专家录入（写手引用合法性与取值的权威来源）
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="dbTableCount" class="pill pill-orange"
          ><span class="dot dot-warn"></span>{{ dbTableCount }} 表待导出</span
        >
        <template v-if="userStore.isAdmin">
          <button class="btn btn-sec btn-sm" :disabled="exporting" @click="onExport">
            {{ exporting ? '导出中…' : '导出核实结果' }}
          </button>
          <button
            class="btn btn-pri btn-sm"
            :disabled="exporting || !dbTableCount"
            @click="exportLimits"
          >
            {{ exporting ? '导出中…' : '导出限值行' }}
          </button>
        </template>
      </div>
    </div>

    <!-- 门 1 体检卡（P2-3 只读）：规则规格 + 注册表自检（code 对 allowed_patterns），不伪造违规明细 -->
    <div v-if="gate1" class="gate1-card">
      <div class="gate1-hd">
        <div class="gate1-badge"><ShieldCheck :size="16" /></div>
        <div>
          <h3>门 1 · 标准号体检</h3>
          <div class="hd-sub" :title="gate1.desc">
            gate1_code_checks · 写作前标准引用合法性规则与当前命中
          </div>
        </div>
        <div class="hd-right">
          <span v-if="gate1.registry_check.violations.length" class="pill-warn-tag">
            {{ gate1.registry_check.violations.length }} 项待修正
          </span>
          <span v-else class="pill-ok-tag">全部通过</span>
        </div>
      </div>
      <div class="gate1-metrics">
        <div class="gate1-m">
          <span class="v num">{{ gate1.registry_check.total }}</span>
          <span class="l">在册标准</span>
          <span class="h">standards[].code</span>
        </div>
        <div class="gate1-m">
          <span class="v num">{{ gate1.allowed_patterns.length }}</span>
          <span class="l">引用模式</span>
          <span class="h">allowed_patterns</span>
        </div>
        <div class="gate1-m">
          <span class="v num" :class="gate1.registry_check.violations.length ? 'hot' : 'zero'">
            {{ gate1.registry_check.violations.length }}
          </span>
          <span class="l">命不上模式</span>
          <span class="h">需人工核对登记</span>
        </div>
      </div>
      <div class="gate1-body">
        <div class="gate1-patterns">
          <span class="pl-label">引用模式</span>
          <code v-for="p in gate1.allowed_patterns" :key="p" class="k">{{ p }}</code>
        </div>
        <ol class="gate1-rules">
          <li v-for="(r, i) in gate1.rules" :key="i">{{ r }}</li>
        </ol>
        <template v-if="gate1.registry_check.violations.length">
          <div class="gate1-viol">
            <span class="pl-label">命不上模式的在册编号</span>
            <code v-for="c in gate1.registry_check.violations" :key="c" class="k viol">{{
              c
            }}</code>
          </div>
        </template>
      </div>
    </div>

    <a-spin v-if="loading && !items.length" style="display: block; margin: 48px auto" />
    <template v-else>
      <!-- 标准核实清单（原型 s11：card-hd 内 seg + 搜索，自绘表） -->
      <div class="card">
        <div class="card-hd">
          <h3>标准核实清单</h3>
          <span class="hd-sub"
            >{{ items.length }} 条 · 待核实 {{ todoCount }} · 已核实 {{ doneCount }}</span
          >
          <div class="hd-right">
            <div class="seg">
              <button :class="{ on: filters.state === '' }" @click="filters.state = ''">
                全部 {{ items.length }}
              </button>
              <button :class="{ on: filters.state === 'todo' }" @click="filters.state = 'todo'">
                待核实 {{ todoCount }}
              </button>
              <button :class="{ on: filters.state === 'done' }" @click="filters.state = 'done'">
                已核实 {{ doneCount }}
              </button>
            </div>
            <input
              v-model="filters.q"
              class="inp"
              style="width: 180px"
              placeholder="搜索标准号 / 名称…"
            />
          </div>
        </div>
        <table class="tbl" :style="loading && items.length ? 'opacity: .55' : ''">
          <thead>
            <tr>
              <th style="width: 17%">标准号</th>
              <th style="width: 30%">名称</th>
              <th style="width: 10%">分级</th>
              <th style="width: 11%">核实状态</th>
              <th style="width: 20%">核实人 / 备注</th>
              <th class="r" style="width: 12%; padding-right: 20px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in filteredItems" :key="record.code">
              <td class="mono">
                {{ record.code }}
                <span
                  v-if="record.review.action && record.needs_verification"
                  class="pill pill-orange pill-sm"
                  style="margin-left: 4px"
                  title="已裁决，导出物化后转「已核实」"
                  >待导出</span
                >
              </td>
              <td>
                <div class="title-cell">
                  <span
                    class="title-main"
                    :title="`章节：${record.chapters || '—'} · 语料引用 ${record.cited_count} 份`"
                    >{{ record.title }}</span
                  >
                  <span v-if="record.role" class="title-role" :title="record.role">{{
                    record.role
                  }}</span>
                </div>
              </td>
              <td>
                <span
                  class="tier"
                  :class="tierBadge(record.tier)"
                  :title="tierLabel(record.tier)"
                  >{{ tierLabel(record.tier) }}</span
                >
              </td>
              <td>
                <span v-if="!record.needs_verification" class="pill pill-ok">已核实</span>
                <span v-else-if="record.review.action" class="pill pill-orange">已裁决·待导出</span>
                <span v-else class="pill pill-warn">待核实</span>
              </td>
              <td>
                <div v-if="record.review.action" class="review-cell">
                  <span class="review-by">{{ record.review.decided_by }}</span>
                  <small
                    v-if="record.review.note"
                    class="review-note"
                    :title="record.review.note"
                    >{{ record.review.note }}</small
                  >
                </div>
                <span v-else class="muted">—</span>
              </td>
              <td class="r" style="padding-right: 20px">
                <button class="btn btn-txt btn-sm" @click="openReview(record)">
                  {{ record.needs_verification || !record.review.action ? '核实' : '查看' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!filteredItems.length" class="empty-state">
          <a-empty :description="emptyDesc">
            <button v-if="isFiltered" class="btn btn-sec btn-sm" @click="clearFilters">
              清除筛选
            </button>
          </a-empty>
        </div>
        <div class="tbl-foot">
          共 {{ filteredItems.length }} 条 · 核实 =
          已对照标准原文确认编号/年份/名称；导出物化翻转注册表两标志
        </div>
      </div>

      <!-- 限值查找表（原型 s11：表 chips + 单表视图 + 整表替换编辑） -->
      <div class="card">
        <div class="card-hd">
          <h3>限值查找表</h3>
          <span class="hd-sub"
            >{{ tableEntries.length }} 表 · schema 驱动 · 整表替换语义 ·
            档位未录入达标判定输出「需人工对照」</span
          >
        </div>
        <div class="toolbar">
          <button
            v-for="[name, t] in tableEntries"
            :key="name"
            class="stage-chip"
            :class="{ on: activeTable === name }"
            @click="activeTable = name"
          >
            {{ t.desc }} <span class="cnt">{{ (t.rows || []).length }} 行</span>
          </button>
          <span style="flex: 1"></span>
          <span
            v-if="activeMeta"
            class="pill"
            :class="activeMeta.source === 'db' ? 'pill-orange' : 'pill-gray'"
            :title="
              activeMeta.source === 'db'
                ? 'DB 录入为导出真源，导出物化后写手可见'
                : '文件锚点态，导出前请先录入核实'
            "
            >{{ activeMeta.source === 'db' ? 'DB · 待导出' : '文件态' }}</span
          >
          <button
            v-if="userStore.isAdmin"
            class="btn btn-sec btn-sm"
            :disabled="!activeTable"
            @click="openLimitEdit(activeTable, activeMeta)"
          >
            {{ (activeMeta?.rows || []).length ? '编辑限值行' : '添加限值行' }}
          </button>
        </div>
        <table v-if="activeRows.length" class="tbl limit-tbl">
          <thead>
            <tr>
              <th v-for="(spec, k) in activeSchema" :key="k" :class="{ r: spec.type === 'number' }">
                {{ spec.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in activeRows" :key="i">
              <td v-for="(spec, k) in activeSchema" :key="k" :class="{ r: spec.type === 'number' }">
                <span :class="spec.type === 'number' ? 'mono num' : ''">{{ row[k] }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="limit-empty">
          <a-empty :description="`「${activeMeta?.desc || ''}」暂无限值行，录入后写手方可取值`" />
        </div>
        <p v-if="activeMeta?.note" class="limit-note" :title="activeMeta.note">
          {{ activeMeta.note }}
        </p>
        <div class="tbl-foot">
          整表替换语义：保存即以 DB 为导出真源全量替换；导出以 (table_key, id) 全序重写 rows
          数组并翻转核验标记；空表拒绝导出
        </div>
      </div>
    </template>

    <div class="note-bar">
      <Info :size="14" />
      <span
        >体检命不上模式的编号经核实通道人工登记修正；限值行按表 schema
        分型校验（str/number、必填），写手按 (标准号, 参数) 取值。</span
      >
    </div>

    <!-- 核实对话框 -->
    <a-modal
      v-model:open="dlg.open"
      :title="`核实 · ${dlg.record?.code ?? ''}`"
      :confirm-loading="dlg.submitting"
      ok-text="确认核实无误"
      @ok="onSubmit"
    >
      <div v-if="dlg.record" class="dlg-meta">
        <p class="dlg-title">{{ dlg.record.title }}</p>
        <p class="dlg-line">
          {{ tierLabel(dlg.record.tier) }}
          <template v-if="dlg.record.chapters"> · 章节 {{ dlg.record.chapters }}</template>
          · 语料引用 {{ dlg.record.cited_count }} 份
        </p>
        <div class="redline-box">
          <span class="redline-title">核实语义（红线）</span>
          web_search
          结果不采信，仅当已对照<strong>标准原文</strong>确认编号、年份、名称无误时才可确认。
          导出物化后该条目转「已核实」，写作技能将按注册表引用规范书写；但<strong>限值数值断言仍以限值查找表数据在位为准</strong>——
          档位未录入前达标判定一律输出「需人工对照」。
        </div>
      </div>
      <a-form layout="vertical" class="dlg-form">
        <a-form-item label="备注（仅平台库留档，不进物化文件）">
          <a-textarea
            v-model:value="dlg.form.note"
            :rows="2"
            placeholder="核实依据，如「已对照生态环境部官网现行版本」"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 限值行编辑对话框（整表替换保存） -->
    <a-modal
      v-model:open="editDlg.open"
      :title="`限值录入 · ${editDlg.tableMeta?.desc ?? ''}`"
      :confirm-loading="editDlg.submitting"
      :width="720"
      ok-text="保存录入"
      @ok="onSaveRows"
    >
      <p class="rows-editor-sub">
        整表替换保存（DB 即导出真源）；数值字段对照标准原文录入纯数字，禁带区间或文字。
      </p>
      <table class="rows-edit-table">
        <thead>
          <tr>
            <th v-for="(spec, k) in editFields" :key="k">{{ spec.label }}</th>
            <th class="op-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in editDlg.rows" :key="i">
            <td v-for="(spec, k) in editFields" :key="k">
              <a-input-number
                v-if="spec.type === 'number'"
                v-model:value="row[k]"
                style="width: 100%"
              />
              <a-input v-else v-model:value="row[k]" />
            </td>
            <td class="op-col"><a class="danger" @click="editDlg.rows.splice(i, 1)">删除</a></td>
          </tr>
        </tbody>
      </table>
      <a-button size="small" @click="addBlankRow">＋ 添加一行</a-button>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info, ShieldCheck } from '@lucide/vue'
import { eiaStandardApi } from '@/apis/eia_standard_api'
import { useUserStore } from '@/stores/user'

const TIERS = [
  { key: 'framework', label: '框架标准' },
  { key: 'quality_limit', label: '质量标准' },
  { key: 'emission_limit', label: '排放标准' },
  { key: 'method_param', label: '方法与参数' },
  { key: 'pending', label: '档位待定' }
]
const TIER_LABELS = Object.fromEntries(TIERS.map((t) => [t.key, t.label]))

const userStore = useUserStore()
const loading = ref(false)
const exporting = ref(false)
const items = ref([])
const limitTables = ref({})
const schemas = ref({})
const gate1 = ref(null)
const filters = reactive({ state: '', q: '' })
// 限值表单表视图：chips 切换当前表（原型 s11 单表视图）
const activeTable = ref('')

const tierLabel = (k) => TIER_LABELS[k] || k
// 分级徽记按真实类别映射展示档位（非虚构 T1/T2 评级）：质量/排放为写手取值主力 → tier-1
const TIER_BADGES = {
  quality_limit: 'tier-1',
  emission_limit: 'tier-1',
  framework: 'tier-2',
  method_param: 'tier-3',
  pending: 'tier-3'
}
const tierBadge = (k) => TIER_BADGES[k] || 'tier-3'

// 限值行列头取服务端 schemas（字段顺序与中文标签权威）；schemas 缺席时回退首行键
const rowKeys = (name, t) => {
  const s = schemas.value[name]
  if (s) return Object.keys(s)
  return Object.keys(t.rows?.[0] || {}).filter((k) => k !== 'origin')
}

// seg/头标与过滤同源：待核实 = 文件标记且无裁决；已核实 = 其余（含免核实条目）。
// 不用服务端 counts.confirmed——它只数 DB 裁决，与表格过滤口径脱节（会显示 0 却过滤出 21 行）
const todoCount = computed(
  () => items.value.filter((r) => r.needs_verification && !r.review.action).length
)
const doneCount = computed(
  () => items.value.filter((r) => !r.needs_verification || r.review.action).length
)

const isFiltered = computed(() => Boolean(filters.state || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配标准' : '标准注册表为空'))

const filteredItems = computed(() => {
  let list = items.value
  if (filters.state === 'todo') list = list.filter((r) => r.needs_verification && !r.review.action)
  if (filters.state === 'done') list = list.filter((r) => !r.needs_verification || r.review.action)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    list = list.filter(
      (r) => r.code.toLowerCase().includes(q) || (r.title || '').toLowerCase().includes(q)
    )
  }
  return list
})

const clearFilters = () => {
  filters.state = ''
  filters.q = ''
}

// ── 限值表单表视图 ──────────────────────────────────────

const tableEntries = computed(() =>
  Object.entries(limitTables.value).filter(([, v]) => typeof v === 'object' && v !== null)
)
const activeMeta = computed(() => limitTables.value[activeTable.value] || null)
const activeSchema = computed(() => schemas.value[activeTable.value] || {})
const activeRows = computed(() => {
  const t = activeMeta.value
  if (!t) return []
  // schema 缺席时回退首行键投影（与 rowKeys 同一兜底）
  if (schemas.value[activeTable.value]) return t.rows || []
  const keys = rowKeys(activeTable.value, t)
  return (t.rows || []).map((r) => Object.fromEntries(keys.map((k) => [k, r[k]])))
})

const fetchList = async () => {
  loading.value = true
  try {
    const [data, limits, gate1Data] = await Promise.all([
      eiaStandardApi.listStandards(),
      eiaStandardApi.listLimits(),
      eiaStandardApi.getGate1().catch(() => null) // 体检卡独立降级：不阻塞标准表主链
    ])
    items.value = data.items
    schemas.value = limits.schemas || {}
    limitTables.value = Object.fromEntries(
      Object.entries(limits.limit_tables).filter(([, v]) => typeof v === 'object' && v !== null)
    )
    gate1.value = gate1Data
    // 首次装载缺省选中第一张表；刷新后当前选中表被裁剪则回落
    if (!limitTables.value[activeTable.value]) {
      activeTable.value = tableEntries.value[0]?.[0] ?? ''
    }
  } catch (e) {
    message.error(e?.message || '标准库加载失败')
  } finally {
    loading.value = false
  }
}

const onExport = async () => {
  exporting.value = true
  message.loading({ content: '正在物化…', key: 'std-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportReviews()
    message.success({
      content: `已翻转 ${r.materialized} 条裁决 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'std-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '导出失败', key: 'std-export' })
  } finally {
    exporting.value = false
  }
}

// ── 核实对话框 ──────────────────────────────────────────

const dlg = reactive({ open: false, submitting: false, record: null, form: { note: '' } })

const openReview = (record) => {
  dlg.record = record
  dlg.form.note = record.review?.note || ''
  dlg.open = true
}

const onSubmit = async () => {
  dlg.submitting = true
  try {
    await eiaStandardApi.setReview(dlg.record.code, {
      action: 'confirm',
      note: dlg.form.note || null
    })
    message.success(`「${dlg.record.code}」核实裁决已保存（导出物化后生效）`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '核实保存失败')
  } finally {
    dlg.submitting = false
  }
}

// ── 限值行编辑对话框（整表替换保存）──────────────────────

const dbTableCount = computed(
  () => Object.values(limitTables.value).filter((t) => t.source === 'db').length
)

const editDlg = reactive({
  open: false,
  submitting: false,
  tableKey: '',
  tableMeta: null,
  rows: []
})
const editFields = computed(() => schemas.value[editDlg.tableKey] || {})

const addBlankRow = () => {
  const blank = {}
  for (const [k, spec] of Object.entries(editFields.value))
    blank[k] = spec.type === 'number' ? null : ''
  editDlg.rows.push(blank)
}

const openLimitEdit = (name, t) => {
  editDlg.tableKey = name
  editDlg.tableMeta = t
  // 按 schema 投影装载：文件锚点行携带的 origin 等溯源字段不进编辑器（服务端校验拒收）
  const fields = schemas.value[name] || {}
  editDlg.rows = (t.rows || []).map((r) =>
    Object.fromEntries(
      Object.entries(fields).map(([k, spec]) => [k, r[k] ?? (spec.type === 'number' ? null : '')])
    )
  )
  if (!editDlg.rows.length) addBlankRow()
  editDlg.open = true
}

const onSaveRows = async () => {
  editDlg.submitting = true
  try {
    const r = await eiaStandardApi.saveLimitRows(editDlg.tableKey, editDlg.rows)
    message.success(
      `「${editDlg.tableMeta?.desc || editDlg.tableKey}」已保存 ${r.saved} 行（导出物化后生效）`
    )
    editDlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '限值行保存失败')
  } finally {
    editDlg.submitting = false
  }
}

const exportLimits = async () => {
  exporting.value = true
  message.loading({ content: '正在物化限值行…', key: 'limits-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportLimits()
    message.success({
      content: `已物化 ${r.materialized} 张限值表 ${r.rows} 行 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'limits-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '限值行导出失败', key: 'limits-export' })
  } finally {
    exporting.value = false
  }
}

onMounted(fetchList)
</script>

<style lang="less" scoped>
.standards-panel {
  --hairline: var(--gray-200);
}

/* 清单表列宽固定（标准名/备注为长文本），同 s9/s10 结论；限值表字段短改回自动 */
.standards-panel .tbl {
  table-layout: fixed;

  td {
    overflow-wrap: break-word;
  }
}

.limit-tbl {
  table-layout: auto;
}

.limit-empty {
  padding: 40px 0;
}

.limit-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--gray-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  .title-main {
    color: var(--gray-800);
  }

  .title-role {
    font-size: 11px;
    line-height: 1.5;
    color: var(--gray-400);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    white-space: normal;
    word-break: break-all;
  }
}

.muted {
  color: var(--gray-400);
}

.review-cell {
  display: flex;
  flex-direction: column;

  .review-by {
    font-size: 13px;
    font-weight: 600;
    color: var(--main-600);
  }

  .review-note {
    font-size: 11px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/* ── 空态 ───────────────────────────────────────────── */
.empty-state {
  padding: 48px 0;
  text-align: center;
}

/* ── 核实对话框 ─────────────────────────────────────── */
.dlg-meta {
  margin-bottom: 12px;
}

.dlg-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-800);
}

.dlg-line {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--gray-600);
}

.redline-box {
  padding: 10px 12px;
  border: 1px solid var(--second-600);
  border-radius: 6px;
  background: var(--main-0);
  font-size: 12px;
  line-height: 1.7;
  color: var(--gray-600);

  .redline-title {
    display: block;
    margin-bottom: 4px;
    font-weight: 600;
    color: var(--second-600);
  }

  strong {
    color: var(--gray-800);
  }
}

.dlg-form {
  margin-top: 4px;
}

/* ── 限值行编辑对话框 ───────────────────────────────── */
.rows-editor-sub {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.rows-edit-table {
  width: 100%;
  margin-bottom: 10px;
  border-collapse: collapse;

  th,
  td {
    padding: 4px 6px;
    border: 1px solid var(--hairline);
  }

  th {
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-600);
    background: var(--gray-50);
    text-align: left;
  }

  td {
    color: var(--gray-800);
  }

  .op-col {
    width: 48px;
    text-align: center;
  }

  a.danger {
    color: var(--second-600);
    font-size: 12px;
  }
}

/* ── 门 1 体检卡 ── */
.gate1-card {
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--gray-0);
  margin-bottom: 12px;
  overflow: hidden;
}

.gate1-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;

  h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
  }

  .hd-right {
    margin-left: auto;
  }
}

.gate1-badge {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--main-0);
  color: var(--main-600);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.pill-warn-tag,
.pill-ok-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
}

.pill-warn-tag {
  background: var(--second-50, var(--gray-100));
  color: var(--second-600);
}

.pill-ok-tag {
  background: var(--main-0);
  color: var(--main-600);
}

.gate1-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--hairline);
}

.gate1-m {
  padding: 11px 16px;
  display: flex;
  align-items: baseline;
  gap: 8px;

  & + & {
    border-left: 1px solid var(--hairline);
  }

  .v {
    font-size: 20px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;

    &.zero {
      color: var(--main-600);
    }

    &.hot {
      color: var(--second-600);
    }
  }

  .l {
    font-size: 12px;
    color: var(--gray-600);
  }

  .h {
    margin-left: auto;
    font-size: 11px;
    color: var(--gray-500);
  }
}

.gate1-body {
  border-top: 1px solid var(--hairline);
  padding: 10px 16px 12px;
}

.pl-label {
  display: inline-block;
  font-size: 12px;
  color: var(--gray-500);
  margin-right: 8px;
}

.gate1-patterns,
.gate1-viol {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

/* mono 栈对齐原型 var(--mono)（用户裁定，2026-10-13） */
code.k {
  font-family: ui-monospace, 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 12px;
  background: var(--gray-100);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--gray-700);

  &.viol {
    color: var(--second-600);
    background: var(--second-50, var(--gray-100));
  }
}

.gate1-rules {
  margin: 8px 0 0;
  padding-left: 30px;
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.9;

  li + li {
    margin-top: 2px;
  }
}

.gate1-viol {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--hairline);
}
</style>

<style lang="less" src="./factory-ui.less"></style>
