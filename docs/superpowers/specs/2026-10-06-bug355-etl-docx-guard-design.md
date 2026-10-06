# ETL docx 入口防护设计（bug-355：WPS 病态 docx 诊断 + zip 手术自动修复重试）

> 日期：2026-10-06 ｜ 分支 pisuan-custom
> 状态：方案 B 已获用户批准（自动修复重试）；本 spec 待用户审阅
> 上游依据：roadmap v2 spec §7（缺陷前置修复表 bug-355 行）、gap-audit 排期 #2

---

## 1. 问题与证据

**三类病态 docx**（41 份语料普查实测，bug-355）：

| 病类 | 实例 | python-docx 表现 | 可救性 |
|---|---|---|---|
| 悬空关系项（WPS NULL-rels） | 九龙川 145MB：`Target="NULL"`；巴拉素 39MB：`Target` 解析到 `'word/NULL'` | `KeyError: "There is no item named 'NULL' in the archive"` 崩溃 | **可救**——zip 级剔除悬空条目后可正常解析（`.wolf/corpus-census/patched/` 两份手术副本实证，38 份完整章树含此二份） |
| WPS 私有格式（UniDocSa 头） | 塔然高勒（文件已不在盘上，buglog 记录） | `BadZipFile`（非标准 OOXML 容器） | 不可救——需精确报错指引（用户用 Word 另存） |
| 静默零值 | 解析"成功"但产物退化 | 无异常，`raw_markdown` 空 → 0 段落继续走完流水线 | 需空产物守卫 |

**现状缺口**：
- ETL 主解析（`domain_factory_service.py:577` → `ocr_service.parse_document`）失败时，驱动层（:1018）确实落 `status=FAILED + error_message`，但报错是裸 `KeyError`——不可诊断、无指引。
- 大纲提取（`_extract_headings_from_docx`，:5136 裸调 `Document(io.BytesIO(...))`）直接崩溃，同样不可诊断；0 heading 时只 warning 返回 `total:0`，用户不知原因。
- 解析产物为空（0 段落）无守卫，流水线空转到 WAITING_REVIEW。

## 2. 目标 / 非目标

**目标**：
1. ETL 主解析与大纲提取两个 docx 消费面：病态文件可诊断（报错带病类 + 可操作指引），可救类自动修复重试（机器能救的不用人）。
2. 空产物守卫：0 段落显式失败，不再静默空转。
3. 零 schema 变更，报错全走既有 `error_message` 通道。

**非目标**：
- 不改 `yuxi/knowledge/parser/unified.py`（全站 KB 上传共用面，爆炸半径大——方案 C 否决理由）。
- 不做 census 脚本转正（独立挂账项）。
- 不处理非 docx 类型的解析防护（PDF/图片等走既有链路）。

## 3. 设计

### 3.1 新模块 `backend/package/yuxi/services/docx_guard.py`（~100 行，纯 stdlib）

```python
@dataclass
class DocxDiagnosis:
    kind: str          # "ok" | "dangling_rels" | "unidocsa" | "corrupt"
    details: list[str] # 悬空条目清单等诊断细节（英文原文，供日志）

def diagnose_docx(data: bytes) -> DocxDiagnosis: ...
def repair_dangling_rels(data: bytes) -> bytes: ...
```

- `diagnose_docx`：
  - 头 8 字节非 `PK` 魔数：以 `UniDocSa` 开头 → `unidocsa`；否则 → `corrupt`
  - 是 zip：扫描全部 `*.rels` 条目，逐条解析 `Relationship`；**跳过 `TargetMode="External"`**；内部 Target 归一化（剥前导 `/`，相对 .rels 所在目录 resolve）后不在 zip namelist 中 → 记悬空。有悬空 → `dangling_rels`
- `repair_dangling_rels`：重写 zip——`.rels` 条目剔除悬空 Relationship 后重新序列化，其余条目**逐字节原样复制**（保留原 compress_type）。原文件永不改动，只产出内存副本。
  - 规则取「内部 Target 无法解析到实际部件即剔除」的一般形式（census 实测 `'NULL'` 与 `'word/NULL'` 两变体一并覆盖），不硬编码 "NULL" 字面量。

### 3.2 ETL 主解析接线（`_etl_parse_stage`，域 ：570-590）

该区域出自 pisuan-custom 提交 `484e5bf7`（ETL P0），非上游共享，可改。

```python
try:
    raw_markdown = await parse_document(file_path)
except Exception as e:
    raw_markdown = await self._retry_parse_with_docx_guard(file_path, e)
```

`_retry_parse_with_docx_guard`（service 方法）：
1. 取文件 bytes：`is_minio_url(file_path)` → `parse_minio_url` + `get_minio_client().adownload_file`（unified.py:137-139 同款 API）；否则本地读
2. `diagnose_docx`：
   - `ok` → **原样 re-raise 原异常**（文件本身无病，失败另有原因如网络/存储，守卫不得掩盖）
   - `unidocsa` → raise `ValueError("文件为 WPS 私有格式（UniDocSa），非标准 docx 容器，无法解析；请用 Word/WPS 打开后另存为标准 .docx 再上传")`
   - `corrupt` → raise `ValueError("文件损坏或非标准 docx 容器，无法解析")`（chain 原异常）
   - `dangling_rels` → `repair_dangling_rels` → 写临时 `.docx` → 重调 `parse_document(temp_path)` 一次 → `finally` 删临时文件
3. 重试成功 → `logger.warning(f"docx 悬空关系项已自动修复后解析成功: {file_path}, 悬空条目={details}")`，返回 markdown；重试仍败 → raise 链式错误（含病类诊断）

非 docx 后缀的解析失败直接走原异常（守卫只对 `.docx` 生效）。

### 3.3 大纲提取接线（`_extract_headings_from_docx`，域 :5126）

出自 pisuan-custom 提交 `02419f2f`，非上游共享，可改。`Document()` 前插三行：

```python
diag = diagnose_docx(file_bytes)
if diag.kind == "dangling_rels":
    file_bytes = repair_dangling_rels(file_bytes)
elif diag.kind != "ok":
    raise ValueError(病类中文指引)   # 与 3.2 同款报错文案
```

### 3.4 空产物守卫（`_etl_parse_stage`，段落切分后）

```python
paragraphs = self._parse_markdown_to_paragraphs(raw_markdown, html_content=raw_html)
if not paragraphs:
    raise ValueError(f"解析产物为空（0 段落）: {file_path}——文件可能为空壳或格式退化，请检查文件")
if len(raw_markdown) < 1000:
    logger.warning(f"解析产物疑似退化（Markdown 仅 {len(raw_markdown)} 字符）: {file_path}")  # 不阻断
```

稀疏产物只告警不阻断（正常简本文件可能就是小）。

### 3.5 错误文案归属

`docx_guard` 只返回结构化 `kind + details`（机械判定层）；中文用户文案在 service 接线处组装（用户面归 service）。报错经既有驱动层 except（:1018）落 `error_message`，前端现状即显示。

## 4. 数据流与不变量

- 原文件**永不修改**：修复只发生在内存副本 / 临时文件（ETL 重试副本 `finally` 清理）。
- 145MB 级文件一次 bytes 驻留：管理端一次性流，可接受；修复重写 zip 的 CPU/内存峰值同量级。
- 重试**恰一次**：修复后仍失败即最终失败，不循环。
- 守卫范围：仅 `.docx` 后缀 + 仅工厂 ETL / 大纲提取两个消费面；`unified.py`、`ocr_service` 零改动。

## 5. 测试计划

`backend/test/unit/test_docx_guard.py`（synthetic fixtures 全内存构造，不依赖外部文件）：
1. 正常 docx 结构 zip（document.xml + 合法 rels）→ `ok`；`repair` 不被调用
2. `Target="NULL"` 变体 → `dangling_rels`；repair 后条目消失、其余条目字节保持；`python-docx` 可打开修复副本
3. `Target="/word/NULL"` 变体 → 同上（覆盖第二实测变体）
4. `TargetMode="External"` 悬空链接（http://...）→ **不**判悬空（外部引用合法）
5. `b"UniDocSa..."` 头 → `unidocsa`；随机非 PK 字节 → `corrupt`
6. `_retry_parse_with_docx_guard`：monkeypatch `parse_document`——首败 + 可救诊断 → 修复重试成功路径 / 不可救 → 中文报错路径（fake bytes，不触真实解析器）

真实文件冒烟（本地手办，不入 CI）：`.wolf/corpus-census/patched/` 两份真实病态文件过 `diagnose → repair → python-docx 打开`。

**验收标准**：
- [ ] unit 测试在容器内全过（宿主 `--noconftest`；容器用 `pisuan-api:0.7.3` 临时容器——api-dev 不存在，运行栈勿碰）
- [ ] ETL 主解析 + 大纲提取两面的接线 diff 各 ≤ 15 行；`unified.py`/`ocr_service` 零 diff；零 schema 变更
- [ ] changelog 追加行 + buglog bug-355 更新（occurrences/last_seen/fix 补 ETL 落地）
- [ ] 禁碰清单零卷入

## 6. 关联

- buglog：bug-355（census 侧已修，本设计落 ETL 侧同型防护）
- 证据：`.wolf/corpus-census/{census.json（error 字段）, patched/}`、`.wolf/buglog.json` bug-355
- 上游：roadmap v2 spec §7、gap-audit §5 排期 #2
- 出处判定：两处改动区域分别出自 pisuan-custom `484e5bf7`、`02419f2f`（`git branch --contains` 验证不在 main）
