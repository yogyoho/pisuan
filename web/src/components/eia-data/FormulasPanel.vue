<template>
  <div class="ewp formulas-panel">
    <!-- 页头（原型 s5：TrendingUp + 待导出 pill + 导出物化） -->
    <div class="page-head">
      <div class="ph-icon">
        <TrendingUp :size="18" />
      </div>
      <div>
        <h2>公式参数核对</h2>
        <div class="ph-sub">
          formulas.json · 写作时计算公式的专家核对参数（DB 覆盖层 → 导出物化）
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange"
          ><span class="dot dot-warn"></span>{{ pendingCount }} 项待导出</span
        >
        <button
          v-if="userStore.isAdmin"
          class="btn btn-pri btn-sm"
          :disabled="!pendingCount"
          @click="onExport"
        >
          <Download :size="14" />{{ exporting ? '导出中…' : '导出物化' }}
        </button>
      </div>
    </div>

    <a-spin v-if="loading" style="display: block; margin: 48px auto" />
    <template v-else-if="formulas.length">
      <div class="split">
        <!-- 左：公式列表 -->
        <div class="card fam-list">
          <div class="fam-search">
            <input v-model="famQuery" class="inp" placeholder="搜索公式…" />
          </div>
          <div
            v-for="f in filteredFormulas"
            :key="f.id"
            class="fam-item"
            :class="{ on: f.id === activeId }"
            @click="activeId = f.id"
          >
            <span v-if="f.inputs.some((i) => i.override?.pending)" class="mini-dot"></span>
            <span class="fam-name" :title="f.name">{{ f.name }}</span>
            <span class="fam-cnt mono">{{ f.inputs.length }} 参数</span>
          </div>
          <div v-if="!filteredFormulas.length" class="empty-state">
            <a-empty description="无匹配公式" />
          </div>
        </div>

        <!-- 右：表达式卡 + 输入参数表 -->
        <div>
          <div v-if="activeFormula" class="card" style="margin-bottom: 12px">
            <div class="card-hd">
              <h3>{{ activeFormula.name }}</h3>
              <code class="k">{{ activeFormula.id }}</code>
              <span class="hd-sub">用途：{{ activeFormula.chapter || '—' }}</span>
              <div class="hd-right">
                <span
                  class="pill"
                  :class="checkedCount === activeFormula.inputs.length ? 'pill-ok' : 'pill-gray'"
                  >{{ checkedCount }}/{{ activeFormula.inputs.length }} 已核对</span
                >
              </div>
            </div>
            <div style="padding: 14px 16px 10px">
              <div class="expr-block">
                <span class="ro-tag"><Lock :size="12" />表达式只读</span>
                <!-- eslint-disable-next-line vue/no-v-html -->
                <span v-html="tokenizedExpr"></span>
                <div v-if="activeFormula.outputs?.length" class="tok-cmt" style="margin-top: 4px">
                  // 输出 {{ activeFormula.outputs.map((o) => o.name).join('、') }}
                </div>
              </div>
              <div
                v-if="activeFormula.slots?.length"
                style="
                  display: flex;
                  gap: 8px;
                  margin-top: 10px;
                  align-items: center;
                  flex-wrap: wrap;
                "
              >
                <span style="font-size: 12px; color: var(--color-text-tertiary)">写入槽位：</span>
                <span v-for="s in activeFormula.slots" :key="s" class="slot-chip">{{
                  slotTag(s)
                }}</span>
              </div>
            </div>
          </div>

          <div v-if="activeFormula" class="card">
            <div class="card-hd">
              <h3>输入参数</h3>
              <span class="hd-sub">user_input 类型为专家核对对象 · derived 自动推导不可编辑</span>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th style="width: 60px">参数</th>
                  <th>说明</th>
                  <th style="width: 90px">类型</th>
                  <th class="r">参考值</th>
                  <th style="width: 150px">值来源</th>
                  <th style="width: 110px">核对状态</th>
                  <th class="r" style="padding-right: 20px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="inp in activeFormula.inputs"
                  :key="inp.name"
                  :style="inp.type === 'derived' ? 'opacity:.55' : ''"
                >
                  <td class="mono">{{ inp.name }}</td>
                  <td :title="inp.desc">{{ inp.desc || '—' }}</td>
                  <td>
                    <span
                      class="pill pill-sm"
                      :class="inp.type === 'user_input' ? 'pill-main' : 'pill-gray'"
                      >{{ inp.type }}</span
                    >
                  </td>
                  <td class="r val mono">
                    <template v-if="inp.override">{{ inp.override.value }}</template>
                    <template v-else>—</template>
                  </td>
                  <td>
                    <template v-if="inp.type === 'derived'">自动推导</template>
                    <template v-else-if="inp.override">
                      {{ inp.override.decided_by ? `DB · ${inp.override.decided_by}` : 'DB 覆盖' }}
                    </template>
                    <template v-else>—</template>
                  </td>
                  <td>
                    <span v-if="inp.type === 'derived'" class="pill pill-gray">—</span>
                    <span
                      v-else-if="inp.override && !inp.override.pending"
                      class="pill pill-ok"
                      :title="inp.override.note || ''"
                      >已核对</span
                    >
                    <span v-else class="pill pill-warn">待核对</span>
                  </td>
                  <td class="r" style="padding-right: 20px; white-space: nowrap">
                    <template v-if="inp.type === 'user_input'">
                      <button
                        class="btn btn-sm"
                        :class="inp.override ? 'btn-txt' : 'btn-pri'"
                        @click="openValueModal(activeFormula, inp)"
                      >
                        {{ inp.override ? '改值' : '核对' }}
                      </button>
                      <button
                        v-if="inp.override"
                        class="btn btn-txt btn-sm withdraw-btn"
                        @click="onWithdraw(activeFormula, inp)"
                      >
                        撤回
                      </button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="card">
            <div class="empty-state"><a-empty description="选择左侧公式查看参数" /></div>
          </div>

          <!-- 派生槽位：恒只读（expr 派生，无人工参数） -->
          <div v-if="derivedSlots.length" class="card" style="margin-top: 12px">
            <div class="card-hd">
              <h3>派生槽位</h3>
              <span class="hd-sub">{{ derivedSlots.length }} 个 · 由公式输出派生，恒只读</span>
            </div>
            <div v-for="d in derivedSlots" :key="d.slot" class="slot-line">
              <span class="slot-chip">{{ slotTag(d.slot) }}</span>
              <span class="sl-expr mono" :title="d.expr">{{ d.expr }}</span>
              <span class="pill pill-gray pill-sm">{{ d.chapter }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          导出物化仅改写 formulas.json 对应 input 的参考值字段，round-trip 校验 expr 与
          derived_slots 字节不变；expr / outputs / 结构恒只读。
        </span>
      </div>
    </template>
    <div v-else class="card">
      <div class="empty-state"><a-empty description="暂无公式数据" /></div>
    </div>

    <!-- 设值弹窗 -->
    <a-modal
      v-model:open="valueModal.open"
      :title="`参数参考值 · ${valueModal.inputName}`"
      :confirm-loading="valueModal.saving"
      @ok="submitValue"
    >
      <div class="frm">
        <div class="frm-row">
          <label>参考值（value）</label>
          <a-input v-model:value="valueModal.value" placeholder="数值或文本，如 0.65" />
        </div>
        <div class="frm-row">
          <label>裁决依据（note，选填）</label>
          <a-textarea
            v-model:value="valueModal.note"
            :rows="3"
            placeholder="取值来源/依据，仅运营侧留档"
          />
        </div>
        <div class="frm-help">
          落库为待导出覆盖，admin「导出物化」后行级写回 formulas.json 的
          {{ valueModal.formulaName }} inputs 生效
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Download, Info, Lock, TrendingUp } from '@lucide/vue'
import { eiaFormulaApi } from '@/apis/eia_formula_api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const loading = ref(true)
const formulas = ref([])
const derivedSlots = ref([])
const exporting = ref(false)
const activeId = ref('')
const famQuery = ref('')

// 模板里写字面 `}}` 会提前闭合插值，SLOT 记法只能走 script 方法；
// formulas.json 的 slots 已是 {{SLOT:...}} 全记法（derived_slots.slot 为裸名），避免二次包裹
const slotTag = (slot) => (slot.startsWith('{{SLOT:') ? slot : `{{SLOT:${slot}}}`)

const pendingCount = computed(() =>
  formulas.value.reduce((acc, f) => acc + f.inputs.filter((inp) => inp.override?.pending).length, 0)
)

const filteredFormulas = computed(() => {
  const q = famQuery.value.trim().toLowerCase()
  if (!q) return formulas.value
  return formulas.value.filter(
    (f) => f.name.toLowerCase().includes(q) || f.id.toLowerCase().includes(q)
  )
})

const activeFormula = computed(() => formulas.value.find((f) => f.id === activeId.value))

const checkedCount = computed(
  () =>
    activeFormula.value?.inputs.filter((inp) => inp.override && !inp.override.pending).length ?? 0
)

// expr 变量 token 着色：先整体 HTML 转义，再单趟把 input 名包 tok-var（长名优先，避免短名误匹配）
const tokenizedExpr = computed(() => {
  const f = activeFormula.value
  if (!f) return ''
  let html = f.expr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const names = [...new Set(f.inputs.map((i) => i.name).filter(Boolean))].sort(
    (a, b) => b.length - a.length
  )
  if (!names.length) return html
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(^|[^\\w])(${names.map(esc).join('|')})(?=[^\\w]|$)`, 'g')
  return html.replace(re, (_, pre, name) => `${pre}<span class="tok-var">${name}</span>`)
})

const fetchFormulas = async () => {
  loading.value = true
  try {
    const out = await eiaFormulaApi.listFormulas()
    formulas.value = out.formulas
    derivedSlots.value = out.derived_slots
    if (!formulas.value.some((f) => f.id === activeId.value)) {
      activeId.value = formulas.value[0]?.id ?? ''
    }
  } catch (e) {
    message.error(`获取公式参数失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

// ── 设值弹窗 ──
const valueModal = reactive({
  open: false,
  saving: false,
  formulaId: '',
  formulaName: '',
  inputName: '',
  value: '',
  note: ''
})

const openValueModal = (formula, input) => {
  valueModal.formulaId = formula.id
  valueModal.formulaName = formula.name
  valueModal.inputName = input.name
  valueModal.value = input.override?.value ?? ''
  valueModal.note = input.override?.note ?? ''
  valueModal.open = true
}

const submitValue = async () => {
  if (!valueModal.value.trim()) {
    message.warning('参考值不能为空')
    return
  }
  valueModal.saving = true
  try {
    await eiaFormulaApi.setInputValue(valueModal.formulaId, valueModal.inputName, {
      value: valueModal.value,
      note: valueModal.note.trim() || null
    })
    message.success('参考值已落库，待导出物化')
    valueModal.open = false
    await fetchFormulas()
  } catch (e) {
    message.error(e.message)
  } finally {
    valueModal.saving = false
  }
}

const onWithdraw = async (formula, input) => {
  try {
    await eiaFormulaApi.clearInputValue(formula.id, input.name)
    message.success('已撤回参数覆盖（文件锚点不受影响）')
    await fetchFormulas()
  } catch (e) {
    message.error(e.message)
  }
}

const onExport = async () => {
  exporting.value = true
  try {
    const out = await eiaFormulaApi.exportFormulas()
    const materialized = Object.values(out.results).reduce((acc, r) => acc + r.materialized, 0)
    const skipped = Object.values(out.results).reduce((acc, r) => acc + r.skipped, 0)
    message.success(
      `已写回 ${out.paths.join('、')}（物化 ${materialized} / 跳过已同值 ${skipped}）；落运行栈技能目录，需人工回流 pisuan-custom`,
      6
    )
    await fetchFormulas()
  } catch (e) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}

onMounted(fetchFormulas)
</script>

<style lang="less" scoped>
.withdraw-btn {
  color: var(--second-600);

  &:hover {
    background: var(--second-50);
  }
}

/* 派生槽位行（原型未给定版式，沿用 expr 卡同族语言） */
.slot-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;

  & + .slot-line {
    border-top: 1px dashed var(--gray-100);
  }

  .sl-expr {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text-tertiary);
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 12px;
  }
}

/* ── 设值弹窗 ── */
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
