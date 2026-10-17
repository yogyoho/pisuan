# 环评文件库（P1）设计

> 状态：已评审通过（2026-10-17 头脑风暴定稿，三点决策用户确认）。P2 管线在线化、P3 入库另立 spec。

## 1. 背景与目标

语料元数据标注页的记录目前**无法溯源到环评报告样例源文件**：corpus_meta.json 无文件字段，原始 docx 散落在个人目录（`C:\项目管理\样例文件`），rid→file_name 映射只存在于本机 `.wolf/corpus-workdir/manifest.json`。

用户的运营闭环愿景分三步走：

1. **P1（本 spec）**：环评域管理员将环评报告上传到**环评文件库**，线上存储、可浏览、可下载；
2. **P2**：skill 语料提取管线在线化，消费库内文件（按管线需要提供格式）；
3. **P3**：加工产物入库（向量数据库、图谱）。

设计语义对齐参考原型（合同文件库截图）：**「上传即登记 · 加工需显式触发」** — P1 只做前半句，后半句是 P2。

## 2. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| D1 | **撤销 P0 溯源回填** | 在线化后溯源正源变为"上传即算 sha1 落库"；corpus_meta 的 `source_file`/`content_sha1` 字段改由 P2 管线产物**原生产出**，不做手工回填。现有 33 份待 P1/P2 就绪后重新上传走管线，自然获得溯源。字段契约归 P1（库表）与 P2（产物）spec，不单独成任务 |
| D2 | **方案 1 轻量自建**（新表+专属 volume+独立页面），不复用 KB 上传（上传即触发解析，与"存而未加工"冲突）、不扩展领域工厂（加工语义不同构，硬套扭曲） | P1 本质是"进料区"：文件安静存着、可溯源、可下载 |
| D3 | **格式门槛 (b)**：docx/pdf 都收，不做加工资格判断 | 库是库、加工是加工，库不替管线把门 |
| D4 | **文件夹 = 五阶段分类法**：规划环评 / 项目环评·井工 / 项目环评·露天 / 后评价 / 跟踪评价（即 samples_bank 现行 stage 分类 `planning_eia / project_eia_underground / project_eia_openpit / post_eia / tracking_eia`）；根目录为"未归类" | 把现管线"manifest stage 人工过目"工序变为**拖进哪个文件夹**这一动作，归类即标注；P2 管线直接读 folder→stage |
| D5 | **P1 隐藏全部加工入口**（解析队列/加入加工），不留禁用占位 | 不做投机性 UI 占位 |
| D6 | **docx 预览不做**（需转换基建），P1 行菜单仅：下载 / 移动到… / 删除 | 最小可用 |

## 3. 信息架构（前端）

### 3.1 页面结构（对照参考原型）

```
┌──────────────────────────────────────────────────────────────┐
│ [📁] 环评文件库  上传即登记 · 加工需显式触发（P2 上线）           │
├──────────────────────────────────────────────────────────────┤
│ 📂 未归类（当前面包屑）          [搜索文件名] [⬆ 上传]          │
├──────────────┬───────────────────────────────────────────────┤
│ ▾ 文件库      │ ☑ │ 文件名        │ 状态   │ 类型 │ 大小 │ 日期 │ │
│   📁 未归类   │   │ 📄 xxx.docx   │ 已入库 │ DOCX │ 18MB │ …  │⋯│
│   📁 规划环评 │   │               │        │      │      │    │ │
│   📁 项目·井工│   └────────── 行菜单：下载 / 移动到… / 删除 ───┘ │
│   📁 项目·露天│                                                 │
│   📁 后评价   │                                                 │
│   📁 跟踪评价 │                                                 │
├──────────────┴───────────────────────────────────────────────┤
│ 共 N（当前文件夹）· 已登记 M                                    │
└──────────────────────────────────────────────────────────────┘
```

- 路由：`/domain-factory/eia-data/library`（EiaDataLayout 子路由，`views/EiaLibraryView.vue` 薄壳 + `components/eia-data/LibraryPanel.vue`，配方同 MetaPanel）。
- 菜单：EiaDataLayout 导航数组**首位**加 `{ to: '/domain-factory/eia-data/library', label: '环评文件库', icon: FolderOpen }`（进料区先于加工产物区）。
- 左树固定两层（根 + 五夹），**P1 不提供文件夹管理**（YAGNI）；上传落在当前选中节点（根=未归类，`folder_id NULL`）。
- 「上传文件夹」P1 简化为**多选批量上传到当前文件夹**（`<input multiple>`）。
- 搜索：**全库范围**按文件名模糊匹配，结果显示"所在文件夹"列提示；清空恢复当前文件夹视图。
- 底栏：`共 N（当前文件夹）· 已登记 M（全库）`。
- 空态：引导文案「暂无文件 — 点右上「上传」导入环评报告样例（docx / pdf）」。
- 样式遵循 `base.css` 颜色变量与 lexicon-rename-redesign 原型配方；明暗两态 QA。

### 3.2 交互细节

- 上传中显示进度态（antd Upload 自带）；完成后列表刷新、新记录高亮不强制。
- 删除：确认框（含文件名与"同时删除磁盘文件"说明），成功后 toast。
- 移动：下拉选择目标文件夹（五夹互移 + 可移回未归类），保存后行内更新。
- 同 sha1 拒收：toast 提示「文件已存在于〈文件夹名〉」（幂等，不产生重复记录）。

## 4. 数据模型

`manager.py` 业务 schema **v18** 建两张表 + 种子数据；ORM 模型入 `models_domain_factory.py`。

```sql
CREATE TABLE eia_library_folders (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    stage_key  VARCHAR(50),              -- NULL = 自定义夹（P1 无）；五夹分别对应 stage 分类法
    sort       INT NOT NULL DEFAULT 0
);
INSERT INTO eia_library_folders (name, stage_key, sort) VALUES
    ('规划环评', 'planning_eia', 1),
    ('项目环评·井工', 'project_eia_underground', 2),
    ('项目环评·露天', 'project_eia_openpit', 3),
    ('后评价', 'post_eia', 4),
    ('跟踪评价', 'tracking_eia', 5)
ON CONFLICT DO NOTHING;  -- 幂等

CREATE TABLE eia_library_files (
    id                SERIAL PRIMARY KEY,
    folder_id         INT REFERENCES eia_library_folders(id),  -- NULL = 未归类
    original_filename VARCHAR(500) NOT NULL,
    stored_path       VARCHAR(1000) NOT NULL,   -- volume 内相对路径
    content_sha1      CHAR(40) NOT NULL UNIQUE, -- 全库去重键；P2 产物溯源外键
    size_bytes        BIGINT NOT NULL,
    content_type      VARCHAR(100),
    status            VARCHAR(20) NOT NULL DEFAULT 'stored',  -- P1 恒 'stored'；P2 扩待加工/加工中/已加工/失败
    uploaded_by       VARCHAR(100),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_eia_library_files_folder ON eia_library_files(folder_id);
```

## 5. 存储布局

- Docker volume（bind mount，与 threads 同模式）：`${YUXI_STATE_DIR:-./docker/volumes}/yuxi/eia-library` → api 容器 `/app/eia-library`；`docker-compose.yml` api 服务加一行 volumes（**需 `docker compose up -d api` 重建容器生效，非热重载**）。
- 落盘文件名：`<sha1 前 12 位>__<original_filename>`（sha1 防碰撞且天然去重，原名保可读）。
- 写盘复用 `yuxi/utils/upload_utils.py` 的 `write_upload_to_path` / `MAX_UPLOAD_SIZE_BYTES`（100MB 上限；census 实测最大样例 18MB，余量充足），超限报错文案明确。
- sha1 计算：上传流式读盘后对落盘文件计算，先写临时名再原子改名，避免半截文件。

## 6. API 契约

全部挂 `domain_factory_router.py` 现有 `/eia/...` 前缀下；鉴权：**读** `get_required_user`（与 `/eia/meta` 一致），**写** `get_admin_user`（环评域管理员统一管理）。Service 层 `EiaLibraryService`（单例 `get_eia_library_service()`，配方同 `EiaMetaService`），仓储层 `EiaLibraryRepository`。

| 方法 | 路径 | 说明 | 请求 → 响应 |
|---|---|---|---|
| GET | `/eia/library/folders` | 文件夹树（含各夹计数） | → `{folders: [{id, name, stage_key, file_count}]}` |
| POST | `/eia/library/files` | 上传（multipart；批量多选由前端逐个调用本端点，逐文件成败独立提示） | `file, folder_id?` → `201 {id, original_filename, content_sha1, size_bytes, …}`；sha1 重复 → `409 {detail, existing: {id, folder_name}}`；超限 → `413` |
| GET | `/eia/library/files` | 列表（`folder_id?` 缺省=全库；`q?` 文件名模糊） | → `{files: [{id, folder_id, folder_name, original_filename, content_sha1, size_bytes, content_type, status, uploaded_by, created_at}]}`；无分页（与 MetaPanel 同量级策略） |
| GET | `/eia/library/files/{id}/download` | 下载（`FileResponse`，filename=original_filename 恢复原名） | → 文件流；不存在 → `404` |
| PATCH | `/eia/library/files/{id}` | 移动文件夹 | `{folder_id: int\|null}` → `{…更新后记录}` |
| DELETE | `/eia/library/files/{id}` | 删除（DB 记录 + 磁盘文件同删） | → `{success: true}`；不存在 → `404` |

错误处理原则：磁盘文件缺失但 DB 有记录 → 列表照常返回并在 download 时 404（提示"文件已丢失，可删除后重新上传"）；不做自动修复假象。

## 7. 前端 API 层

`web/src/apis/eia_data_api.js` 的 `eiaDataApi` 对象内新增 library 方法组（`listLibraryFolders / uploadLibraryFiles / listLibraryFiles / downloadLibraryFile / moveLibraryFile / deleteLibraryFile`），组件不直接拼 URL。

## 8. 测试与验收

单测（`backend/test/unit/`，容器内跑）：
- repository CRUD + sha1 唯一约束触发 409 语义
- service：上传命名规则（sha1 前缀__原名）、重复 sha1 拒收、移动、删除（DB+盘同删）、文件夹计数
- 落盘文件缺失时列表/下载行为

浏览器 QA（isolatedContext，admin 登录）：
- AC1 上传 docx/pdf 单个+批量到指定文件夹，列表即时可见，明暗两态正常
- AC2 磁盘落盘 `<sha1 12>__<原名>`，DB 记录 sha1/size/uploader 正确
- AC3 同一文件重复上传被拒并提示既有位置
- AC4 全库搜索命中跨文件夹文件且显示所在文件夹
- AC5 下载得到原文件名原内容（sha1 校验一致）
- AC6 移动、删除（含磁盘文件消失）正常，删除有确认框
- AC7 底栏计数正确；空态文案正确
- AC8 页面上不出现任何加工入口（解析队列/加入加工）
- AC9 超限文件（>100MB）报 413 且文案明确

## 9. 部署与同步注意

- `docker-compose.yml` 变更经 sync-dev 链路到运行栈后需 `docker compose up -d api` 重建容器（volume 挂载不热生效）；在 pisuan-custom 提交，随官方链再生 pisuan-localized。
- 运行栈首次启动 v18 迁移自动建表 + 种子五夹。

## 10. 风险与开放问题

- **并发上传同名冲突**：stored_path 含 sha1，天然无碰撞；DB 唯一约束兜底。
- **volume 磁盘容量**：样例 18MB×几十份量级，无虞；P2 批量化后如增长再议配额。
- **Windows 主机 bind mount 的文件锁**：删除时若文件被占用（罕见）→ 返回明确错误，DB 记录保留，提示重试。
- 开放：未来是否允许自定义子文件夹/年份嵌套 — P1 固定两层，需要时另议（`stage_key NULL` 的自定义夹已留位）。
