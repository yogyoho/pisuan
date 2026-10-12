<template>
  <div class="formulas-panel">
    <div class="card toolbar-card">
      <div class="toolbar">
        <span class="toolbar-label">参数参考值裁决</span>
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

    <template v-if="!loading">
      <!-- 计算公式卡：inputs 参考值为唯一可编辑面 -->
      <div v-for="f in formulas" :key="f.id" class="card formula-card">
        <div class="card-hd">
          <h3>
            {{ f.name }} <code class="k">{{ f.id }}</code>
          </h3>
          <span class="src-chip">{{ f.chapter }}</span>
          <span class="hd-sub mono expr" :title="f.expr">{{ f.expr }}</span>
        </div>
        <a-table
          :data-source="f.inputs"
          :columns="inputColumns"
          :pagination="false"
          row-key="name"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <code class="k">{{ record.name }}</code>
            </template>
            <template v-else-if="column.key === 'value'">
              <template v-if="record.override">
                <span class="val mono">{{ record.override.value }}</span>
                <span v-if="record.override.pending" class="pending-tag" title="尚未导出物化">
                  <span class="dot"></span>待导出
                </span>
                <span
                  v-else-if="record.override.note"
                  class="note-hint"
                  :title="`${record.override.note}（${record.override.decided_by ?? ''}）`"
                >
                  <Info :size="13" />
                </span>
              </template>
              <span v-else class="unset">—</span>
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-space :size="6">
                <a-button size="small" @click="openValueModal(f, record)">
                  {{ record.override ? '改值' : '设值' }}
                </a-button>
                <a-button v-if="record.override" size="small" danger @click="onWithdraw(f, record)">
                  撤回
                </a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>

      <!-- 派生槽位：恒只读（expr 派生，无人工参数） -->
      <div class="card">
        <div class="card-hd">
          <h3>派生槽位</h3>
          <span class="hd-sub">{{ derivedSlots.length }} 个 · 由公式输出派生，恒只读</span>
        </div>
        <div v-for="d in derivedSlots" :key="d.slot" class="slot-line">
          <span class="sl-name mono">{{ d.slot }}</span>
          <span class="sl-expr mono" :title="d.expr">{{ d.expr }}</span>
          <span class="src-chip">{{ d.chapter }}</span>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          只读边界：expr / derived_slots / outputs / 结构恒只读——写手按 expr
          复算，覆盖结构会破坏冻结口径；参考值仅在导出物化回 formulas.json 后对写作生效。
        </span>
      </div>
    </template>
    <div v-else class="empty-state"><a-spin /></div>

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
import { Info } from '@lucide/vue'
import { eiaFormulaApi } from '@/apis/eia_formula_api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const loading = ref(true)
const formulas = ref([])
const derivedSlots = ref([])
const exporting = ref(false)

const inputColumns = [
  { title: '参数名', key: 'name', width: 150 },
  { title: '说明', dataIndex: 'desc', key: 'desc', ellipsis: true },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 90 },
  { title: '参考值', key: 'value', width: 220 },
  { title: '操作', key: 'actions', width: 150 }
]

const pendingCount = computed(() =>
  formulas.value.reduce((acc, f) => acc + f.inputs.filter((inp) => inp.override?.pending).length, 0)
)

const fetchFormulas = async () => {
  loading.value = true
  try {
    const out = await eiaFormulaApi.listFormulas()
    formulas.value = out.formulas
    derivedSlots.value = out.derived_slots
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
.formulas-panel {
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

.card-hd {
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
  }

  .expr {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: right;
    color: var(--gray-400);
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

.formula-card :deep(.ant-table) {
  border-radius: 0;
}

.val {
  color: var(--main-600);
  font-weight: 600;
}

.unset {
  color: var(--gray-300);
}

.pending-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  padding: 0 7px;
  height: 18px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--warn, #ad6800);
  background: var(--warn-0, #fff7e6);
  border: 1px solid var(--warn-2, #ffe58f);

  .dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--warn, #ad6800);
  }
}

.note-hint {
  display: inline-flex;
  margin-left: 6px;
  color: var(--gray-400);
  cursor: help;
}

.src-chip {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid var(--hairline);
  background: var(--gray-50);
  color: var(--gray-600);
  white-space: nowrap;
}

.slot-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 8px 16px;

  & + .slot-line {
    border-top: 1px dashed var(--gray-100);
  }

  .sl-name {
    flex: none;
    width: 260px;
    color: var(--gray-800);
  }

  .sl-expr {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--gray-500);
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
