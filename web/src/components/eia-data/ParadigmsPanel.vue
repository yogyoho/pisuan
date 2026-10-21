<template>
  <div class="ewp paradigms-panel">
    <!-- 页头（原型 s12：NotebookPen + 待导出 pill + 导出物化） -->
    <div class="page-head">
      <div class="ph-icon"><NotebookPen :size="18" /></div>
      <div>
        <h2>写作范式</h2>
        <div class="ph-sub">
          paradigms/*.md · 四角色行文范式（适用 / 结构骨架 / 范文 / 节尾收束段 / 句式模式 /
          反模式）· 写手按节角色整文件注入
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange">
          <span class="dot dot-warn"></span>{{ pendingCount }} 文件待导出
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
      <a-empty description="范式层加载失败" />
    </div>
    <template v-else>
      <div class="split">
        <!-- 左：角色列表 -->
        <div class="card fam-list">
          <div class="fam-search">
            <input v-model="query" class="inp" placeholder="搜索角色…" />
          </div>
          <div
            v-for="p in filteredParadigms"
            :key="p.asset_id"
            class="fam-item"
            :class="{ on: p.asset_id === activeId }"
            @click="selectRole(p.asset_id)"
          >
            <span v-if="p.has_draft && !p.drift" class="mini-dot"></span>
            <span class="fam-name">{{ roleLabel(p.asset_id) }}</span>
            <span class="fam-cnt" style="margin-left: auto">{{
              p.has_draft ? '改·未导出' : '一致'
            }}</span>
            <span class="fam-cnt">{{ roleCounts[p.asset_id] ?? 0 }} 节</span>
          </div>
          <div class="tbl-foot">
            挂载节数取自 _roles.json（{{ rolesTotal }} 节全映射，查不到=拒派报错）
          </div>
        </div>

        <!-- 右：编辑器 + 角色对照 -->
        <div>
          <div class="card" style="margin-bottom: 12px">
            <div class="card-hd">
              <h3>{{ activeId }}.md</h3>
              <span class="hd-sub">挂载 {{ roleCounts[activeId] ?? 0 }} 节</span>
              <div class="hd-right">
                <div class="seg">
                  <button :class="{ on: mode === 'edit' }" @click="mode = 'edit'">编辑</button>
                  <button :class="{ on: mode === 'view' }" @click="mode = 'view'">预览</button>
                </div>
                <button v-if="draftContent !== null" class="btn btn-txt btn-sm" @click="onWithdraw">
                  丢弃草稿
                </button>
                <button class="btn btn-pri btn-sm" :disabled="!dirty || saving" @click="onSave">
                  {{ saving ? '保存中…' : '保存草稿' }}
                </button>
              </div>
            </div>
            <textarea
              v-show="mode === 'edit'"
              v-model="mdText"
              class="edt-area"
              spellcheck="false"
            ></textarea>
            <MarkdownPreview v-if="mode === 'view'" :content="mdText" bordered class="md-preview" />
            <div class="edt-meta">
              <span v-if="draftContent !== null" class="field-src db">
                草稿 · {{ draftMeta?.updated_by }} · {{ shortTime(draftMeta?.updated_at) }}
              </span>
              <span v-else class="field-src file">无草稿 · 编辑后保存落库</span>
              <span style="margin-left: auto" class="field-src file"
                >base_hash {{ shortHash(active?.file_hash) }}</span
              >
            </div>
          </div>

          <div class="card">
            <div class="card-hd">
              <h3>节角色对照</h3>
              <span class="hd-sub">_roles.json · {{ rolesTotal }} 节 · 只读</span>
              <div class="hd-right">
                <div class="seg">
                  <button
                    v-for="f in roleFilters"
                    :key="f"
                    :class="{ on: roleFilter === f }"
                    @click="roleFilter = f"
                  >
                    {{ f }}
                  </button>
                </div>
                <input
                  v-model="roleQuery"
                  class="inp"
                  style="width: 150px"
                  placeholder="搜索节 id…"
                />
              </div>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th style="width: 130px">节 id</th>
                  <th style="width: 110px">角色</th>
                  <th style="width: 110px">挂载范式</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="[sid, role] in filteredRoles" :key="sid">
                  <td class="mono">{{ sid }}</td>
                  <td>
                    <span class="pill pill-gray">{{ role }}</span>
                  </td>
                  <td>{{ roleLabel(role) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="tbl-foot">
              共 {{ rolesTotal }} 节 ·
              <span
                >角色错配 = 整节范式错注入；调整映射改 _roles.json 走 git 评审，不设 UI 编辑</span
              >
              <span v-if="filteredRoles.length === 20">
                · 仅显示前 20 条，可用筛选/搜索缩小范围</span
              >
            </div>
          </div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          范式 md
          的「反模式」表与交付门残留词表（RESIDUE_RE）人工同源：此处修改反模式表述不会自动更新门禁词表，
          导出确认时会提示同步修订。
        </span>
      </div>
    </template>

    <ParadigmExportModal v-model:open="exportOpen" @exported="fetchAll" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Info, NotebookPen } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'
import { useUserStore } from '@/stores/user'
import ParadigmExportModal from './ParadigmExportModal.vue'
import MarkdownPreview from '@/components/common/MarkdownPreview.vue'

const KIND = 'paradigm_md'
const ROLE_LABELS = {
  opener: 'opener · 章首定位',
  baseline: 'baseline · 现状盘点',
  analysis: 'analysis · 影响预测',
  measures: 'measures · 措施要求'
}

const userStore = useUserStore()
const loading = ref(true)
const overview = ref(null)
const activeId = ref('analysis')
const query = ref('')
const mode = ref('edit')
const mdText = ref('')
const draftContent = ref(null)
const draftMeta = ref(null)
const saving = ref(false)
const exportOpen = ref(false)
const roleFilter = ref('全部')
const roleQuery = ref('')
const fileText = ref('')

const roleFilters = ['全部', 'opener', 'baseline', 'analysis', 'measures']
const roleCounts = computed(() => overview.value?.role_counts ?? {})
const rolesMap = computed(() => overview.value?.roles_map ?? {})
const rolesTotal = computed(() => Object.keys(rolesMap.value).length)
const pendingCount = computed(
  () =>
    (overview.value?.paradigms ?? []).filter((p) => p.has_draft).length +
    (overview.value?.families ?? []).filter((f) => f.has_draft).length
)
const filteredParadigms = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (overview.value?.paradigms ?? []).filter((p) => !q || p.asset_id.includes(q))
})
const filteredRoles = computed(() =>
  Object.entries(rolesMap.value)
    .filter(
      ([sid, role]) =>
        (roleFilter.value === '全部' || role === roleFilter.value) &&
        sid.includes(roleQuery.value.trim())
    )
    .slice(0, 20)
)

const roleLabel = (r) => ROLE_LABELS[r] ?? r
const shortHash = (h) => (h ? `${h.slice(0, 4)}…${h.slice(-2)}` : '—')
const shortTime = (t) => (t ? String(t).slice(5, 16).replace('T', ' ') : '')

const active = computed(() =>
  (overview.value?.paradigms ?? []).find((p) => p.asset_id === activeId.value)
)
const dirty = computed(() => mdText.value !== (draftContent.value ?? fileText.value))

const selectRole = (id) => {
  if (id === activeId.value) return
  if (!dirty.value) {
    activeId.value = id
    return
  }
  Modal.confirm({
    title: '有未保存修改',
    content: '切换角色将丢弃当前编辑内容，是否继续？',
    okText: '继续（丢弃）',
    cancelText: '留在本页',
    onOk: () => {
      activeId.value = id
    }
  })
}

let loadSeq = 0

const loadAsset = async () => {
  const seq = ++loadSeq
  try {
    const out = await eiaParadigmApi.getAsset(KIND, activeId.value)
    if (seq !== loadSeq) return
    fileText.value = out.file_text
    draftContent.value = out.draft ? out.draft.content.md : null
    draftMeta.value = out.draft
    mdText.value = out.draft ? out.draft.content.md : out.file_text
  } catch (e) {
    if (seq !== loadSeq) return
    fileText.value = ''
    draftContent.value = null
    draftMeta.value = null
    mdText.value = ''
    message.error(e.message)
  }
}

const fetchAll = async () => {
  loading.value = true
  try {
    overview.value = await eiaParadigmApi.loadOverview()
    await loadAsset()
  } catch (e) {
    message.error(`获取范式层失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

watch(activeId, () => loadAsset())

const onSave = async () => {
  saving.value = true
  try {
    await eiaParadigmApi.saveDraft(KIND, activeId.value, { md: mdText.value })
    message.success('草稿已落库，待 admin 导出物化')
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

const onWithdraw = () => {
  Modal.confirm({
    title: '丢弃草稿',
    content: '将删除数据库草稿（文件锚点不受影响），编辑器恢复为文件内容。',
    okText: '丢弃',
    onOk: async () => {
      try {
        await eiaParadigmApi.withdrawDraft(KIND, activeId.value)
        message.success('已撤回草稿（文件锚点不受影响）')
        await fetchAll()
      } catch (e) {
        message.error(e.message)
      }
    }
  })
}

onMounted(fetchAll)
</script>

<style lang="less" scoped>
.paradigms-panel {
  --hairline: var(--gray-200);
}

/* 本页形状（原型 s12）：md 编辑区 / 预览 / 元信息行 —— 公共配方在 factory-ui.less */
.edt-area {
  display: block;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--hairline);
  background: transparent;
  color: var(--color-text);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.8;
  padding: 14px 16px;
  min-height: 320px;
  resize: vertical;
  outline: none;
}

/* 预览容器只管盒子（与 edt-area 同高，内部纵向滚动，编辑/预览切换不跳变），排版交 MarkdownPreview 自带 */
.md-preview {
  height: 320px;
  overflow-y: auto;
  border-top: 1px solid var(--hairline);
  padding: 16px 20px;
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
</style>

<style lang="less" src="./factory-ui.less"></style>
