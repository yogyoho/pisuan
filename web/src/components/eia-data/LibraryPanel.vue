<template>
  <div class="ewp lib-panel">
    <!-- 页头（原型 2026-10-17-eia-library-ui：FolderOpen 图标 + 进料区副题） -->
    <div class="page-head">
      <div class="ph-icon">
        <FolderOpen :size="18" />
      </div>
      <div>
        <h2>环评文件库</h2>
        <div class="ph-sub">环评报告样例统一进料 · sha1 全库唯一登记 · 文件夹即阶段分类</div>
      </div>
      <div class="ph-actions">
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".docx,.pdf"
          hidden
          @change="onPickFiles"
        />
        <button class="btn btn-pri btn-sm" :disabled="uploading" @click="fileInput.click()">
          <Upload :size="14" />{{ uploading ? '上传中…' : '上传' }}
        </button>
      </div>
    </div>

    <div class="card">
      <!-- 工具条：面包屑 + 命中章 + 全库搜索 -->
      <div class="lib-toolbar">
        <div class="crumb">
          <span class="crumb-ic"><FolderOpen :size="14" /></span>
          <span v-if="q" class="crumb-q">搜索「{{ q }}」</span>
          <span v-else>{{ scopeLabel }}</span>
        </div>
        <span class="flex-sp"></span>
        <span v-if="q" class="stat-chip"
          >命中 <b class="num">{{ files.length }}</b></span
        >
        <input
          v-model="q"
          class="inp search-inp"
          type="search"
          placeholder="搜索文件名（全库）"
          aria-label="全库搜索文件名"
          @keyup.enter="reload"
          @search="reload"
        />
        <input ref="manifestInput" type="file" accept=".json" hidden @change="onPickManifest" />
        <button
          class="btn btn-sm"
          :title="corpusKbId ? `当前语料知识库：${corpusKbId}` : '推送/加工前须先绑定语料知识库'"
          @click="openBindDlg"
        >
          <Database :size="14" />{{ corpusKbId ? '语料库已绑定' : '绑定语料知识库' }}
        </button>
        <button
          class="btn btn-sm"
          :disabled="!pushable.length"
          :title="corpusKbId ? '' : '请先绑定语料知识库'"
          @click="pushRows(pushable)"
        >
          <CloudUpload :size="14" /> 推送本组（{{ pushable.length }}）
        </button>
        <button
          class="btn btn-sm"
          :disabled="!processable.length"
          @click="processRows(processable)"
        >
          <Cog :size="14" /> 加工本组（{{ processable.length }}）
        </button>
        <a-dropdown :trigger="['click']">
          <button class="btn btn-sm" title="更多库级操作" aria-label="更多库级操作">
            <Ellipsis :size="14" />
          </button>
          <template #overlay>
            <a-menu @click="({ key }) => onLibMenu(key)">
              <a-menu-item key="recompile-all"> <Layers :size="14" /> 全库加工重编译… </a-menu-item>
              <a-menu-item key="bootstrap"><FileUp :size="14" /> 引导导入 manifest…</a-menu-item>
              <a-menu-item key="migrate">
                <HardDriveDownload :size="14" /> 存量迁移 MinIO…
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>

      <!-- 左树 + 文件表 -->
      <div class="lib-split">
        <aside class="lib-tree">
          <div class="tree-label">文件库</div>
          <button
            class="tree-item"
            :class="{ on: folderId === ALL && !q }"
            @click="pickFolder(ALL)"
          >
            <Files :size="14" />
            <span>全部文件</span>
            <span class="cnt num">{{ totalCount }}</span>
          </button>
          <button
            class="tree-item"
            :class="{ on: folderId === null && !q }"
            @click="pickFolder(null)"
          >
            <Folder :size="14" />
            <span>未归类</span>
            <span class="cnt num">{{ rootCount }}</span>
          </button>
          <button
            v-for="f in folders"
            :key="f.id"
            class="tree-item"
            :class="{ on: folderId === f.id && !q }"
            @click="pickFolder(f.id)"
          >
            <Folder :size="14" />
            <span>{{ f.name }}</span>
            <span class="cnt num">{{ f.file_count }}</span>
          </button>
          <div class="tree-note">上传至哪个文件夹即完成阶段归类；根目录 = 未归类</div>
        </aside>

        <div class="lib-tbl">
          <table class="tbl">
            <thead>
              <tr>
                <th>文件名</th>
                <th style="width: 96px">状态</th>
                <th style="width: 128px">阶段</th>
                <th style="width: 96px">md</th>
                <th style="width: 96px">知识库</th>
                <th style="width: 70px">类型</th>
                <th class="r" style="width: 88px">大小</th>
                <th style="width: 104px">上传日期</th>
                <th class="r" style="width: 56px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in files" :key="f.id">
                <td>
                  <div class="fname-cell">
                    <span class="fic" :class="ext(f.original_filename) === 'PDF' ? 'pdf' : 'docx'">
                      <File :size="16" />
                    </span>
                    <span class="fn-wrap">
                      <span class="fn" :title="f.original_filename">{{ f.original_filename }}</span>
                      <span v-if="q || (folderId === ALL && f.folder_name)" class="floc">位于〈{{ f.folder_name || '未归类' }}〉</span>
                    </span>
                  </div>
                </td>
                <td>
                  <span class="pill"><span class="dot dot-ok"></span>已入库</span>
                </td>
                <td>
                  <select
                    v-if="ext(f.original_filename) === 'DOCX'"
                    class="inp stage-sel"
                    :value="f.stage || ''"
                    :aria-label="`阶段：${f.original_filename}`"
                    @change="onStageChange(f, $event)"
                  >
                    <option value="">—</option>
                    <option v-for="(label, key) in STAGE_LABELS" :key="key" :value="key">
                      {{ label }}
                    </option>
                  </select>
                  <span v-else class="cell-dim">—</span>
                </td>
                <td>
                  <span
                    class="pill"
                    :class="mdPillClass(f)"
                    :title="f.md_status === 'failed' ? f.md_failed_reason || 'md 产出失败' : ''"
                  >
                    <span class="dot" :class="mdDotClass(f)"></span>{{ mdLabel(f) }}
                  </span>
                </td>
                <td>
                  <span
                    class="pill"
                    :class="kbPillClass(f)"
                    :title="f.kb_status === 'failed' ? f.push_error || '推送失败' : ''"
                  >
                    <span class="dot" :class="kbDotClass(f)"></span>{{ kbLabel(f) }}
                  </span>
                </td>
                <td>
                  <span class="pill pill-gray">{{ ext(f.original_filename) }}</span>
                </td>
                <td class="r num">{{ fmtSize(f.size_bytes) }}</td>
                <td class="num">{{ fmtDate(f.created_at) }}</td>
                <td class="r">
                  <a-dropdown :trigger="['click']">
                    <button class="more-btn" title="更多操作" aria-label="更多操作">
                      <Ellipsis :size="15" />
                    </button>
                    <template #overlay>
                      <a-menu @click="({ key }) => onRowMenu(key, f)">
                        <a-menu-item key="view-md" :disabled="f.md_status !== 'ready'">
                          <FileText :size="14" /> 查看 md
                        </a-menu-item>
                        <a-menu-item key="push" :disabled="f.md_status !== 'ready'">
                          <CloudUpload :size="14" />
                          {{ f.kb_status === 'indexed' ? '重推知识库' : '推送知识库' }}
                        </a-menu-item>
                        <a-menu-item key="process" :disabled="f.md_status !== 'ready' || !f.stage">
                          <Cog :size="14" /> 加工
                        </a-menu-item>
                        <a-menu-item v-if="f.md_status === 'failed'" key="regen-md">
                          <RefreshCw :size="14" /> 重产 md
                        </a-menu-item>
                        <a-menu-divider />
                        <a-menu-item key="download"><Download :size="14" /> 下载</a-menu-item>
                        <a-menu-item key="move"><FolderInput :size="14" /> 移动到…</a-menu-item>
                        <a-menu-item key="delete" class="menu-danger">
                          <Trash2 :size="14" /> 删除
                        </a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </td>
              </tr>
              <tr v-if="!files.length">
                <td colspan="9" class="empty-cell">
                  <div class="empty-ic"><Inbox :size="26" /></div>
                  <template v-if="q">未检索到匹配文件 — 搜索范围为全库文件名</template>
                  <template v-else
                    >暂无文件 — 点右上「上传」导入环评报告样例（docx / pdf）</template
                  >
                </td>
              </tr>
            </tbody>
          </table>
          <div class="tbl-foot">
            <span>
              共 {{ files.length }}（{{ q ? '全库' : scopeLabel }}）· 已登记
              {{ totalCount }}（全库）
            </span>
            <span class="flex-sp"></span>
            <span class="mono foot-note">
              登记键 content_sha1 全库唯一 · 同文件重复上传将被拒收
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- P2 语义说明（原型 note-bar） -->
    <div class="note-bar">
      <Info :size="14" />
      <span>
        P2：docx 上传即秒级产出 canonical md；推送知识库 /
        加工为后台任务，进度见任务中心；「全库加工重编译」以全库可编译报告重建技能语料衍生物（bank_index
        / 切片 / corpus_meta）。
      </span>
    </div>

    <!-- 移动到文件夹 弹窗 -->
    <a-modal
      v-model:open="moveDlg.open"
      title="移动到文件夹"
      ok-text="移动"
      cancel-text="取消"
      :confirm-loading="moveDlg.saving"
      @ok="doMove"
    >
      <a-select v-model:value="moveDlg.folderId" style="width: 100%" :options="moveOptions" />
      <div class="frm-help">移动后立即生效；文件夹即阶段归类（P2 管线按此读取）</div>
    </a-modal>

    <!-- 查看 canonical md -->
    <a-modal
      v-model:open="mdDlg.open"
      :title="`canonical md — ${mdDlg.name}`"
      :footer="null"
      width="720px"
    >
      <div v-if="mdDlg.loading" class="frm-help">加载中…</div>
      <pre v-else class="md-view">{{ mdDlg.content }}</pre>
    </a-modal>

    <!-- 绑定语料知识库 -->
    <a-modal
      v-model:open="bindDlg.open"
      title="绑定语料知识库"
      ok-text="绑定"
      cancel-text="取消"
      :confirm-loading="bindDlg.saving"
      @ok="doBind"
    >
      <a-input v-model:value="bindDlg.kbId" placeholder="知识库 ID" />
      <div class="frm-help">
        绑定后「推送知识库」把 canonical md 直通该知识库（登记 → 解析 →
        索引）；语料加工产物不依赖此绑定。
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  CloudUpload,
  Cog,
  Database,
  Download,
  Ellipsis,
  File,
  FileText,
  FileUp,
  Files,
  Folder,
  FolderInput,
  FolderOpen,
  HardDriveDownload,
  Inbox,
  Info,
  Layers,
  RefreshCw,
  Trash2,
  Upload
} from '@lucide/vue'
import { eiaDataApi } from '@/apis/eia_data_api'

const folders = ref([])
const files = ref([])
const ALL = 'all' // 视图哨兵：'all'=全部文件 / null=未归类 / 数字=文件夹
const folderId = ref(ALL)
const q = ref('')
const totalCount = ref(0)
const uploading = ref(false)
const fileInput = ref(null)
const moveDlg = reactive({ open: false, fileId: null, folderId: null, saving: false })
const manifestInput = ref(null)
const corpusKbId = ref('')
const mdDlg = reactive({ open: false, name: '', content: '', loading: false })
const bindDlg = reactive({ open: false, kbId: '', saving: false })

const STAGE_LABELS = {
  planning_eia: '规划环评',
  post_eia: '事后环评',
  project_eia_openpit: '项目环评·露天',
  project_eia_underground: '项目环评·井工',
  tracking_eia: '跟踪评价'
}

const rootCount = computed(
  () => totalCount.value - folders.value.reduce((sum, f) => sum + (f.file_count || 0), 0)
)
const scopeLabel = computed(() => {
  if (folderId.value === ALL) return '全部文件'
  return folders.value.find((f) => f.id === folderId.value)?.name || '未归类'
})
const moveOptions = computed(() => [
  { value: null, label: '未归类' },
  ...folders.value.map((f) => ({ value: f.id, label: f.name }))
])
const pushable = computed(() => files.value.filter((f) => f.md_status === 'ready'))
const processable = computed(() => files.value.filter((f) => f.md_status === 'ready' && f.stage))

// md / kb 状态 → 徽标文案与配色（复用 factory-ui pill/dot；进行中用主色，err 点为面板补缺）
const mdLabel = (f) =>
  ({ ready: 'md 就绪', failed: 'md 失败', pending_backfill: '待迁移' })[f.md_status] || '—'
const mdPillClass = (f) =>
  ({ ready: 'pill-ok', failed: 'pill-err', pending_backfill: 'pill-orange' })[f.md_status] ||
  'pill-gray'
const mdDotClass = (f) =>
  ({ ready: 'dot-ok', failed: 'dot-err', pending_backfill: 'dot-warn' })[f.md_status] || 'dot-gray'
const kbLabel = (f) =>
  !f.kb_status ? '未推' : { indexed: '已入库', failed: '失败' }[f.kb_status] || '进行中'
const kbPillClass = (f) =>
  !f.kb_status
    ? 'pill-gray'
    : { indexed: 'pill-ok', failed: 'pill-err' }[f.kb_status] || 'pill-main'
const kbDotClass = (f) =>
  !f.kb_status ? 'dot-gray' : { indexed: 'dot-ok', failed: 'dot-err' }[f.kb_status] || 'dot-run'

const reload = async () => {
  // 搜索/全部=全库；未归类（folderId null）走 uncategorized 参数，与全库语义区分
  const queryFolder = q.value || folderId.value === ALL ? null : folderId.value
  const uncategorized = !q.value && folderId.value === null
  const [folderRes, fileRes] = await Promise.all([
    eiaDataApi.listLibraryFolders(),
    eiaDataApi.listLibraryFiles(queryFolder, q.value || undefined, uncategorized)
  ])
  folders.value = folderRes.folders
  totalCount.value = folderRes.total_files
  files.value = fileRes.files
}

const pickFolder = (id) => {
  folderId.value = id
  q.value = ''
  reload()
}

const onPickFiles = async (e) => {
  const list = [...e.target.files]
  e.target.value = ''
  if (!list.length) return
  uploading.value = true
  try {
    for (const file of list) {
      try {
        await eiaDataApi.uploadLibraryFile(file, folderId.value === ALL ? null : folderId.value)
        message.success(`「${file.name}」已登记`)
      } catch (err) {
        if (err?.status === 409) {
          message.warning(`「${file.name}」与库中已有文件重复：${err.message}`)
        } else if (err?.status === 413) {
          message.warning(`「${file.name}」${err.message}`)
        } else {
          message.error(`「${file.name}」上传失败：${err?.message || '未知错误'}`)
        }
      }
    }
  } finally {
    uploading.value = false
    await reload()
  }
}

const onRowMenu = (key, f) => {
  if (key === 'view-md') viewMd(f)
  else if (key === 'push') pushRows([f])
  else if (key === 'process') processRows([f])
  else if (key === 'regen-md') regenMd(f)
  else if (key === 'download') doDownload(f)
  else if (key === 'move') {
    moveDlg.fileId = f.id
    moveDlg.folderId = f.folder_id
    moveDlg.open = true
  } else if (key === 'delete') confirmDelete(f)
}

const onStageChange = async (f, e) => {
  const stage = e.target.value
  try {
    Object.assign(f, await eiaDataApi.updateFileMeta(f.id, { stage }))
    message.success('阶段已更新')
  } catch (err) {
    message.error(err?.message || '阶段更新失败')
    e.target.value = f.stage || ''
  }
}

const viewMd = async (f) => {
  mdDlg.name = f.original_filename
  mdDlg.content = ''
  mdDlg.loading = true
  mdDlg.open = true
  try {
    mdDlg.content = await eiaDataApi.getFileMd(f.id)
  } catch (err) {
    mdDlg.open = false
    message.error(err?.message || 'md 读取失败')
  } finally {
    mdDlg.loading = false
  }
}

const regenMd = async (f) => {
  try {
    await eiaDataApi.regenerateMd(f.id)
    message.success(`「${f.original_filename}」md 已重产`)
    await reload()
  } catch (err) {
    message.error(err?.message || '重产失败')
  }
}

const pushRows = (rows) => {
  if (!rows.length) return
  if (!corpusKbId.value) {
    message.warning('请先绑定语料知识库')
    return
  }
  eiaDataApi
    .pushToKb(rows.map((f) => f.id))
    .then(() => message.success(`已提交推送任务（${rows.length} 个文件），进度见任务中心`))
    .catch((err) => message.error(err?.message || '推送任务提交失败'))
}

const processRows = (rows) => {
  if (!rows.length) return
  eiaDataApi
    .processCorpus({ file_ids: rows.map((f) => f.id) })
    .then(() => message.success(`已提交加工任务（${rows.length} 个文件），进度见任务中心`))
    .catch((err) => message.error(err?.message || '加工任务提交失败'))
}

const openBindDlg = () => {
  bindDlg.kbId = corpusKbId.value
  bindDlg.open = true
}

const doBind = async () => {
  const kbId = bindDlg.kbId.trim()
  if (!kbId) {
    message.warning('请输入知识库 ID')
    return
  }
  bindDlg.saving = true
  try {
    await eiaDataApi.bindCorpusKb(kbId)
    corpusKbId.value = kbId
    message.success('语料知识库已绑定')
    bindDlg.open = false
  } catch (err) {
    message.error(err?.message || '绑定失败')
  } finally {
    bindDlg.saving = false
  }
}

const onLibMenu = (key) => {
  if (key === 'recompile-all') confirmRecompileAll()
  else if (key === 'bootstrap') manifestInput.value.click()
  else if (key === 'migrate') confirmMigrate()
}

const confirmRecompileAll = () => {
  Modal.confirm({
    title: '全库加工重编译',
    content:
      '将物化全库可编译报告并重建技能语料衍生物（bank_index / 切片 / corpus_meta），耗时较长。继续？',
    okText: '重编译',
    cancelText: '取消',
    onOk: () =>
      eiaDataApi
        .processCorpus({ scope: 'all' })
        .then(() => message.success('已提交全库重编译任务，进度见任务中心'))
        .catch((err) => message.error(err?.message || '任务提交失败'))
  })
}

const confirmMigrate = () => {
  Modal.confirm({
    title: '存量迁移 MinIO',
    content:
      '将本地卷存量文件迁移至 MinIO 并逐份回填 canonical md（幂等，可重复执行直至全部完成）。继续？',
    okText: '开始迁移',
    cancelText: '取消',
    onOk: async () => {
      const hide = message.loading('迁移进行中，请勿关闭页面…', 0)
      try {
        const r = await eiaDataApi.migrateStorage()
        const failNote = r.failed?.length ? `，失败 ${r.failed.length} 个（可重跑续迁）` : ''
        message.success(`迁移完成：${r.migrated} 个成功，md 产出 ${r.md_ready} 个${failNote}`)
        await reload()
      } catch (err) {
        message.error(err?.message || '迁移失败')
      } finally {
        hide()
      }
    }
  })
}

const onPickManifest = async (e) => {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  try {
    const r = await eiaDataApi.bootstrapManifest(file)
    message.success(`引导完成：回填 ${r.matched} 个文件的 report_id / stage / mineral`)
    await reload()
  } catch (err) {
    message.error(err?.message || '引导导入失败')
  }
}

const doMove = async () => {
  moveDlg.saving = true
  try {
    await eiaDataApi.moveLibraryFile(moveDlg.fileId, moveDlg.folderId)
    message.success('已移动')
    moveDlg.open = false
    await reload()
  } catch (err) {
    message.error(err?.message || '移动失败')
  } finally {
    moveDlg.saving = false
  }
}

const confirmDelete = (f) => {
  Modal.confirm({
    title: '删除文件',
    content: `将删除「${f.original_filename}」及其磁盘文件，不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      await eiaDataApi.deleteLibraryFile(f.id)
      message.success('已删除')
      await reload()
    }
  })
}

const doDownload = async (f) => {
  try {
    const blob = await eiaDataApi.downloadLibraryFile(f.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = f.original_filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err?.message || '下载失败')
  }
}

const ext = (name) => (/\.pdf$/i.test(name) ? 'PDF' : /\.docx$/i.test(name) ? 'DOCX' : '其他')
const fmtSize = (n) =>
  n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`
const fmtDate = (s) => (s ? String(s).slice(0, 10).replaceAll('-', '/') : '')

const loadBinding = async () => {
  try {
    corpusKbId.value = (await eiaDataApi.getCorpusKbBinding()).kb_id || ''
  } catch {
    corpusKbId.value = ''
  }
}

onMounted(() => {
  reload()
  loadBinding()
})
</script>

<style lang="less" scoped>
/* 库页专属配方（原型 2026-10-17-eia-library-ui §屏内专属）；共享件（page-head/card/btn/pill/tbl/tbl-foot/note-bar/inp）在 factory-ui */
.flex-sp {
  flex: 1;
}

.lib-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--gray-200);
  flex-wrap: wrap;
}

.crumb {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);

  .crumb-ic {
    display: inline-flex;
    color: var(--main-600);
  }

  .crumb-q {
    font-weight: 500;
    color: var(--color-text-secondary);
  }
}

:root.dark .crumb .crumb-ic {
  color: var(--main-400);
}

.stat-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 9px;
  border: 1px solid var(--gray-200);
  border-radius: 999px;
  font-size: 12px;
  background: var(--gray-0);
  color: var(--color-text-secondary);

  b {
    font-size: 11px;
    color: var(--main-600);
  }
}

.search-inp {
  width: 220px;
}

.lib-split {
  display: grid;
  grid-template-columns: 208px 1fr;
  align-items: stretch;
}

.lib-tree {
  display: flex;
  flex-direction: column;
  padding: 8px;
  border-right: 1px solid var(--gray-200);
}

.tree-label {
  padding: 4px 8px 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
}

.tree-item {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-bottom: 2px;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: none;
  font-size: 13px;
  font-family: inherit;
  text-align: left;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;

  &:hover {
    background: var(--gray-50);
    color: var(--color-text);
  }

  &.on {
    background: var(--main-50);
    color: var(--main-600);
    font-weight: 600;
    box-shadow: inset 2px 0 0 var(--main-500);

    .cnt {
      color: var(--main-500);
    }
  }

  .cnt {
    margin-left: auto;
    font-size: 11px;
    color: var(--color-text-tertiary);
  }
}

:root.dark .tree-item.on {
  background: var(--main-100);
}

.tree-note {
  margin-top: auto;
  padding: 8px 10px 2px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.lib-tbl {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 文件名是长句，auto 布局下 nowrap 最小内容宽会撑爆表格（bug-4039）——固定布局 + 折行：
   文件名列吃剩余宽度，其余列保持表头固定宽（同 LexiconPanel 惯例） */
.lib-tbl .tbl {
  table-layout: fixed;
  width: 100%;

  td {
    overflow-wrap: break-word;
  }
}

.fname-cell {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;

  .fic {
    display: inline-flex;
    flex: none;
    color: var(--color-text-tertiary);

    &.docx {
      color: var(--main-500);
    }

    &.pdf {
      color: var(--second-600);
    }
  }

  .fn-wrap {
    min-width: 0;
  }

  .fn {
    display: block;
    font-weight: 500;
  }

  .floc {
    font-size: 11px;
    color: var(--color-text-tertiary);
  }
}

.more-btn {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--color-text-tertiary);
  cursor: pointer;

  &:hover {
    background: var(--gray-100);
    color: var(--color-text);
  }
}

.stage-sel {
  width: 112px;
  height: 26px;
  padding: 0 6px;
  font-size: 12px;
}

.cell-dim {
  color: var(--color-text-tertiary);
}

/* factory-ui dot 仅 ok/warn/gray：err 与进行中（主色）为面板补缺 */
.dot-err {
  background: var(--color-error-600);
}

.dot-run {
  background: var(--main-500);
}

.md-view {
  max-height: 60vh;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--gray-50);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.menu-danger {
  color: var(--color-error-600);
}

.empty-cell {
  padding: 44px 0 !important;
  text-align: center;
  color: var(--color-text-tertiary) !important;

  .empty-ic {
    margin-bottom: 6px;
    color: var(--gray-300);
  }
}

.foot-note {
  color: var(--color-text-tertiary);
}

.frm-help {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>

<style lang="less" src="./factory-ui.less"></style>
