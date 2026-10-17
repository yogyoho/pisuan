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
      </div>

      <!-- 左树 + 文件表 -->
      <div class="lib-split">
        <aside class="lib-tree">
          <div class="tree-label">文件库</div>
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
                      <span v-if="q" class="floc">位于〈{{ f.folder_name || '未归类' }}〉</span>
                    </span>
                  </div>
                </td>
                <td>
                  <span class="pill"><span class="dot dot-ok"></span>已入库</span>
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
                <td colspan="6" class="empty-cell">
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

    <!-- P1 边界说明（原型 note-bar） -->
    <div class="note-bar">
      <Info :size="14" />
      <span>
        P1 仅登记与检索：下载 / 移动 / 删除。「加入解析 / 解析队列」等加工入口由 P2
        管线在线化时开放，本版不留占位。
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
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  Download,
  Ellipsis,
  File,
  Folder,
  FolderInput,
  FolderOpen,
  Inbox,
  Info,
  Trash2,
  Upload
} from '@lucide/vue'
import { eiaDataApi } from '@/apis/eia_data_api'

const folders = ref([])
const files = ref([])
const folderId = ref(null) // null = 未归类（根）
const q = ref('')
const totalCount = ref(0)
const uploading = ref(false)
const fileInput = ref(null)
const moveDlg = reactive({ open: false, fileId: null, folderId: null, saving: false })

const rootCount = computed(
  () => totalCount.value - folders.value.reduce((sum, f) => sum + (f.file_count || 0), 0)
)
const scopeLabel = computed(
  () => folders.value.find((f) => f.id === folderId.value)?.name || '未归类'
)
const moveOptions = computed(() => [
  { value: null, label: '未归类' },
  ...folders.value.map((f) => ({ value: f.id, label: f.name }))
])

const reload = async () => {
  // 搜索=全库；未归类（folderId null）走 uncategorized 参数，与全库语义区分
  const queryFolder = q.value ? null : folderId.value
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
        await eiaDataApi.uploadLibraryFile(file, folderId.value)
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
  if (key === 'download') doDownload(f)
  else if (key === 'move') {
    moveDlg.fileId = f.id
    moveDlg.folderId = f.folder_id
    moveDlg.open = true
  } else if (key === 'delete') confirmDelete(f)
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

onMounted(reload)
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
