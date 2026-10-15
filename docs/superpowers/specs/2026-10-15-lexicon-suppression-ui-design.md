# 数值护栏词表 · 抑制名单 UI 设计（2026-10-15）

## 背景与动机

词表页（`/domain-factory/eia-data/lexicon`，`LexiconPanel.vue`）与原型（`2026-10-12-eia-p2-ui.html` s9 屏）UI 骨架已对齐，但原型中的**抑制名单卡**未实现：数据层齐备（表 `eia_lexicon_suppressions`、repo 写入路径、导入跳过逻辑均已上线），唯独没有查看/管理入口。当前抑制行只能由改名操作隐式登记，业务人员无法：

- 看到哪些旧指纹被抑制、因什么原因、由谁登记；
- 手工抑制某个扫描候选（不改名、仅屏蔽）；
- 撤回抑制（例如当初改名改错了，想恢复旧口径）。

本设计补齐这三件事，UI 位置与原型 s9 一致：词条表下方的第二张卡。

## 范围

**纳入**：
1. 抑制名单列表（全量，量级 ~20 行，无分页）
2. 撤回抑制（含两条后果的确认弹窗）
3. 手工添加抑制（数据源限定为扫描候选差集，可搜索下拉）

**排除（非目标）**：
- 不做抑制行的编辑（改理由 = 重新添加同一指纹，repo upsert 幂等刷新）
- 不做批量添加/批量撤回
- 不做词表页之外的其他差异项（手工添加词条、别名体系、待导出视角——已在差异对比中另行挂账）
- 无 schema 变更、无迁移

## 数据与既有链路（零迁移）

表 `eia_lexicon_suppressions`（`models_domain_factory.py::EiaLexiconSuppression`）：
- 唯一键 `(stage, caliber, unit)`（`uq_eia_lexicon_suppression_key`）
- 列：`stage` / `caliber`（旧断章指纹名）/ `unit` / `new_caliber`（改名目标，语境回落反查键）/ `reason`（Text）/ `created_by` / `created_at`
- v13 迁移已播种 7 条种子行；**导入判跳过只查 DB**（`suppressed_keys()`），删除行不会被自动补种

既有 repo 方法（复用，不动）：
- `add_suppression(...)`：`pg_insert ... on_conflict_do_update`，幂等刷新 new_caliber/reason/created_by/created_at
- `suppressed_keys()`：导入时跳过依据
- `find_fingerprint_suppression(stage, unit, new_caliber)`：改名条目语境回落反查

## 后端设计

### repository 新增 3 方法（`eia_lexicon_repository.py`）

| 方法 | 语义 |
|---|---|
| `list_suppressions()` | 全量列表，`created_at desc, id desc` |
| `get_suppression(sid)` | 单行，无则 `None` |
| `delete_suppression(sid)` | 硬删一行 |

### service 新增 4 方法（`eia_lexicon_service.py`）

| 方法 | 语义 |
|---|---|
| `list_suppressions()` | `{"items": [to_dict()...], "total": N}` |
| `scan_candidates()` | 扫描差集：`_scan_all()` − 已入库键 − 已抑制键，`{"items": [{stage, caliber, unit, ...}], "total": N}`，作为添加下拉数据源 |
| `add_suppression(payload, username)` | 见下方校验规则；成功后落库（手工行 `new_caliber=''`） |
| `withdraw_suppression(sid, username)` | 行不存在 → `ValueError`；存在 → 删除并返回被删行 to_dict（供 toast） |

**添加校验规则**（服务端强校验，杜绝静默无操作）：
- 指纹 `(stage, caliber, unit)` 必须在 `_scan_all()` 输出中 **且** 不在词条表现有键中，否则 `ValueError`（屏蔽语料中不存在的指纹永远不会生效，属用户误操作，应报错而非吞掉）
- 指纹已在抑制表中 → **允许**，走 repo upsert 幂等刷新（刷新理由/登记人），不算错误
- 手工行固定 `new_caliber=''`：语境回落反查 `WHERE new_caliber = X` 天然不命中，无改名目标即无回落，语义自洽

### router 新增 4 端点（`domain_factory_router.py`，lexicon 端点区）

| 端点 | 方法 |
|---|---|
| `/eia/lexicon/suppressions` | GET |
| `/eia/lexicon/suppressions` | POST，body `{stage, caliber, unit, reason}`（reason 可选） |
| `/eia/lexicon/suppressions/{sid}` | DELETE |
| `/eia/lexicon/scan-candidates` | GET |

- 沿用 lexicon 区既有惯例：`try/except` + `logger.error`+traceback，`ValueError → HTTPException(400)`，`current_user.username` 落 `created_by`
- **权限 = 业务人员**（不挂 admin guard）：与改名对称——改名会登记抑制行，若只有管理员能撤回，用户撤不了自己登记的行，不对称

## 前端设计

### API 封装（`eia_lexicon_api.js` 新增 4 函数）

`listSuppressions` / `addSuppression` / `withdrawSuppression`（DELETE 走 `apiRequest`）/ `getScanCandidates`

### 抑制名单卡（`LexiconPanel.vue`，词条表卡下方、原型 s9 同位）

```
┌ 抑制名单  N 条 · 命中不计入护栏统计，重扫导入跳过        [添加抑制] ┐
│ 被抑制指纹          │ 阶段 │ 改名目标 │ 理由 │ 登记人 · 时间 │ 操作   │
│ （mono 截断+tooltip）│      │ —=手工  │      │              │ 撤回抑制 │
└ 空态：暂无抑制行 — 改名词表口径时自动登记                              ┘
```

- 卡头：`card-hd`「抑制名单」+ `hd-sub`「N 条 · 命中不计入护栏统计，重扫导入跳过」+「添加抑制」`btn-sec`
- 列细节：
  - 被抑制指纹：mono、单行截断 + title tooltip（沿用词表口径列 bug-4025 的做法）
  - 阶段：`pill-stage` 样式（同抽屉 ident）
  - 改名目标：mono 截断；手工行（`new_caliber=''`）显示「—」
  - 理由：截断 + tooltip
  - 操作：「撤回抑制」`btn-txt`
- 样式全部复用既有 token/类（`base.css` 变量、亮暗自适应）

### 添加弹窗（a-modal）

- **指纹**：`a-select` `show-search`（`optionFilterProp`），选项来自 `getScanCandidates`，label 组装为「阶段 · 指纹 (单位)」；加载中禁用提交
- **理由**：`a-textarea`，可选（auto-size 2-6 行，对齐改名对话框备注的用户裁定）
- 提交：`message.success`「已登记抑制」→ 关闭 → 刷新列表
- 不做自由输入指纹：只能抑制扫描器真实会导入的候选

### 撤回确认（Modal.confirm）

文案必须含两条后果：

> 撤回后该旧指纹不再屏蔽：若仍在语料中，重扫将重新导入（A 类直接回已入选）；对应改名条目的语境回落也随之失效。确定撤回「{caliber}」？

- 后果 ①：重扫复活风险，且 `_IMPORT_STATUS` 预设使 measure 类直接回 `approved`
- 后果 ②：改名条目的语境回落依赖抑制行反查（`find_fingerprint_suppression`），删行即断

成功后 `message.success`「已撤回抑制」→ 刷新列表。

### 刷新时机

- `onMounted` 与词条列表**并行**拉取（不阻塞主表）
- 导入成功 / 改名成功（隐式登记）/ 添加 / 撤回后各刷新一次

## 测试策略

**单测** `backend/test/unit/test_eia_lexicon_suppression_ops.py`（FakeRepo + monkeypatch `eia_lexicon_service._scan_all`，**零真实 DB**）：

1. `add_suppression` 校验：指纹不在扫描结果 → `ValueError`；在扫描但已是词条 → `ValueError`
2. `add_suppression` 正常路径：合法候选 → repo 收到 `new_caliber=''` 与 username
3. 幂等刷新：指纹已抑制（在扫描差集外）→ 仍走 `add_suppression`，不报错
4. `withdraw_suppression`：存在 → 删除并返回行；不存在 → `ValueError`
5. `scan_candidates`：差集正确剔除已入库与已抑制
6. `list_suppressions`：to_dict 映射

容器内 `docker exec api-dev pytest /app/test/unit/test_eia_lexicon_suppression_ops.py` 通过。

**真实栈只读验证**：登录后 `GET /eia/lexicon/suppressions` 返回种子 7 条、页面抑制卡可见——只 GET，不写。

**前端链**：prettier → `sync-dev.ps1` → **容器 eslint（必须在 sync 之后跑）** → 真实数据亮/暗目检。

**红线**：绝不运行 `test/integration/services/test_eia_lexicon_service_flow.py`（清空 `eia_lexicon_entries` 表，DNR 已记录）。

## 验收标准

1. 词表页出现抑制名单卡（原型 s9 同位），种子 7 条可见，亮暗两态正常
2. 添加弹窗下拉只含扫描差集候选；提交后列表即时刷新
3. 撤回走确认弹窗且文案含两条后果；撤回后列表减一
4. 添加非候选指纹被服务端 400 拒绝（单测覆盖）
5. 单测 + prettier + 容器 eslint 全绿；更新 `docs/develop-guides/changelog.md`

## 实施注意事项

- 更新 `changelog.md`（v0.7.3 功能组）
- `docs/vibe` 为 gitignore 目录，如在其中新建文件需 `git add -f`
- 提交信息：中文 Conventional Commits，尾行 `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 不 push，除非用户明确指示
