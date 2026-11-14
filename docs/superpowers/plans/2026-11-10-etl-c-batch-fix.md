# 通用域知识工厂 ETL：C批行为修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 C批五项行为修复（C-3 enqueue 兜底 → C-2 FAILED_PROVIDER 前端可达 → C-5 小项+死残留组 → C-4 泛化输入结构化组装 → C-1 INGESTING 状态机+幂等），每项独立提交。

**Architecture:** 后端单文件 `domain_factory_service.py`（6843 行）+ `domain_factory_repository.py` + `task_registry.py` 做行为修复；前端 `DataSourceDashboard.vue` / `EtlWorkbench.vue` / `tasker.js` 三处小改。C-1 引入 `INGESTING` 中间态与合法迁移校验表，file_id 去随机成分实现幂等。设计文档：`docs/vibe/2026-11-10-etl-c-batch-fix-design.md`（定稿）。

**Tech Stack:** Python 3.13 / SQLAlchemy async / ARQ worker / Vue 3 + Pinia / pytest（容器内执行）。

---

## 全局约定（执行前必读）

- **工作树与挂载**：本计划在 `C:\workspace\pisuan-localized` 执行，该目录直通 docker 挂载（`backend/package → /app/package`，`backend/test → /app/test`），改后 pytest 容器内立即可见。
- **分支注意**：当前分支 `pisuan-localized`。按三分支策略语义改动应落 `pisuan-custom`；**每个提交步骤执行前向用户确认就地提交还是留待用户自行同步**（见各任务末尾 commit 步骤）。
- **测试命令**（容器内，宿主缺依赖）：
  ```bash
  docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q
  docker exec pisuan-localized-api-1 pytest /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
  ```
  **Git Bash 注意**：含 `/app/...` 路径的 docker exec 命令会被 MSYS 路径转换改写，需加前缀 `MSYS_NO_PATHCONV=1`（2026-11-11 Task 3 实测）。**失败形态是静默的 `collected 0 items`**（session 正常启动、无 ERROR），不是报错——见 0 items 先怀疑路径改写，或改用 PowerShell 工具执行。
- **语法速检**（宿主）：`python -c "import ast; ast.parse(open('backend/package/pisuan/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"`
- **前端 lint**（容器内）：`docker exec pisuan-localized-web-1 sh -c "cd /app && pnpm exec eslint src/components/domain-factory/DataSourceDashboard.vue src/components/domain-factory/EtlWorkbench.vue src/stores/tasker.js"`
- **行号基准**：2026-11-10 工作树。执行时以 Edit 的 old_str 精确匹配为准，行号漂移不影响。
- 所有锚点缩进均为源码真实缩进（服务层方法体 4 空格起步，`_etl_pipeline_async` 内层 8-12 空格）。

---

### Task 1: C-3 enqueue 兜底（两处）

**Files:**
- Modify: `backend/package/pisuan/services/domain_factory_service.py`（create_task ~:605-606；retry_task ~:5757-5789）

- [ ] **Step 1.1: create_task catch 分支落 FAILED**

Edit old_str（唯一匹配）:
```python
        except Exception as e:
            logger.warning(f"注册任务中心失败，将继续执行: {e}")

        return DomainTaskDTO(
```
new_str:
```python
        except Exception as e:
            logger.warning(f"注册任务中心失败: {e}")
            # C-3 兜底：入队失败不再静默继续，任务落 FAILED 终态，用户可见可重试
            await self.repo.update_task(
                task_id,
                {"status": "FAILED", "error_message": f"任务中心注册失败: {e}"},
            )
            task.status = "FAILED"

        return DomainTaskDTO(
```
（`task.status = "FAILED"` 同步内存对象，保证下方 DTO 返回的 status 不再是过期的 UPLOADED。）

- [ ] **Step 1.2: retry_task 捕获原状态并入队失败恢复**

Edit old_str:
```python
        # P0-3 断点续跑：仅 provider 熔断任务且已有解析产物时，只补泛化失败段
        resume = task.status == "FAILED_PROVIDER" and bool(task.source_paragraphs)

        updated_task = await self.repo.update_task(task_id, {"status": "UPLOADED", "error_message": None})
```
new_str:
```python
        # P0-3 断点续跑：仅 provider 熔断任务且已有解析产物时，只补泛化失败段
        resume = task.status == "FAILED_PROVIDER" and bool(task.source_paragraphs)
        original_status = task.status  # C-3：入队失败时恢复原状态（保住 FAILED_PROVIDER 续跑资格）

        updated_task = await self.repo.update_task(task_id, {"status": "UPLOADED", "error_message": None})
```

- [ ] **Step 1.3: retry_task except 分支恢复原状态**

Edit old_str:
```python
        except Exception as e:
            logger.warning(f"重试任务注册 Tasker 失败: {e}")

        return updated_task.to_summary_dict()
```
new_str:
```python
        except Exception as e:
            logger.warning(f"重试任务注册 Tasker 失败: {e}")
            # C-3 兜底：任务已置 UPLOADED 但无人执行，恢复重试前状态原值；
            # 不得落 FAILED——否则 FAILED_PROVIDER 的 resume 判定丢失，退化为全卷重跑
            restored = await self.repo.update_task(
                task_id,
                {"status": original_status, "error_message": f"任务队列注册失败，请重试: {e}"},
            )
            if restored is not None:
                updated_task = restored
            return updated_task.to_summary_dict()

        return updated_task.to_summary_dict()
```

- [ ] **Step 1.4: 语法验证**

Run: `python -c "import ast; ast.parse(open('backend/package/pisuan/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 1.5: 容器内 import 冒烟**

Run: `docker exec pisuan-localized-api-1 python -c "from pisuan.services.domain_factory_service import DomainFactoryService; print('IMPORT_OK')"`
Expected: `IMPORT_OK`

- [ ] **Step 1.6: Commit**

```bash
git add backend/package/pisuan/services/domain_factory_service.py
git commit -m "fix(factory): C-3 enqueue 失败兜底——create_task 落 FAILED 终态、retry_task 恢复原状态保住续跑资格"
```

---

### Task 2: C-2 FAILED_PROVIDER 前端可达（纯前端）

**Files:**
- Modify: `web/src/components/domain-factory/DataSourceDashboard.vue`（statusMap :64-80；重试按钮 :511）

- [ ] **Step 2.1: statusMap 补条目**

Edit old_str:
```python
```
（注意：以下是 Vue 文件，old_str 用 JS 源码）
```js
  COMMIT_PARTIAL: { color: 'var(--color-warning-500)', text: '部分入库' },
  FAILED: { color: 'var(--color-error-500)', text: '失败' }
}
```
new_str:
```js
  COMMIT_PARTIAL: { color: 'var(--color-warning-500)', text: '部分入库' },
  FAILED: { color: 'var(--color-error-500)', text: '失败' },
  FAILED_PROVIDER: { color: 'var(--color-error-500)', text: '服务商中断' }
}
```

- [ ] **Step 2.2: 重试按钮条件扩展**

Edit old_str:
```html
                <a-tooltip v-if="record.status === 'FAILED'" title="重新提取">
```
new_str:
```html
                <a-tooltip
                  v-if="record.status === 'FAILED' || record.status === 'FAILED_PROVIDER'"
                  title="重新提取"
                >
```
（后端 `retry_task:5765` 已内建 FAILED_PROVIDER 断点续跑，本步纯前端。）

- [ ] **Step 2.3: ESLint**

Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && pnpm exec eslint src/components/domain-factory/DataSourceDashboard.vue"`
Expected: 无输出（0 error）

- [ ] **Step 2.4: 补遗（质量审查追加，2026-11-10）**

1. Dashboard :200 注释更新为：`// 重试任务：FAILED → 重置为 UPLOADED 重跑整个 ETL；FAILED_PROVIDER → 断点续跑（仅补失败段）`（原注释因本任务改动而失实）
2. tasker.js `DOMAIN_FACTORY_STATUS_MAP`（:37-47）补 `FAILED_PROVIDER: { status: 'failed', progress: 100, message: '服务商中断，可续跑仅补失败段' }`（同类 C-2 缺口在任务中心界面的另一表现——无映射条目导致原码直显、failed 徽标少计）
3. 两文件 eslint 复跑
4. **提交由控制者执行**：两文件均带在途未提交改动（tasker.js :130-165 summary 去重统计修复），用 `git apply --cached` 部分暂存仅本任务 hunks，在途改动保持未暂存

- [ ] **Step 2.5: Commit（控制者执行）**

```bash
git add web/src/components/domain-factory/DataSourceDashboard.vue   # 仅注释 hunk（经 git apply --cached）
# tasker.js 仅状态映射 hunk（经 git apply --cached）
git commit -m "fix(web): C-2 补遗——任务中心状态映射补 FAILED_PROVIDER、重试注释对齐续跑语义"
```

---

### Task 3: C-5 小项组 + 死残留组（7 项）

**Files:**
- Modify: `backend/package/pisuan/services/domain_factory_service.py`（:858-861 双 set；:1589 中文数字；:867-872+:1026 空壳；:52 schema；:342-348 prompt；:2208 docstring）
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`（:45 rawSlots；:1920 计数；:1784-1823 死分支）
- Test: `backend/test/unit/test_c_batch_fixes.py`（新建）

- [ ] **Step 3.1: 先写失败测试（中文数字 + narrative 墓碑）**

Create `backend/test/unit/test_c_batch_fixes.py`:
```python
# C批修复单测（C-4/C-5 纯函数部分 + C-1 迁移表）。容器内执行：
# docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from pisuan.services.domain_factory_service import DomainFactoryService, GeneralizedTemplate


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class TestChineseToArabic:
    def test_eleven(self):
        assert make_svc()._chinese_to_arabic("十一") == "11"

    def test_twenty_three(self):
        assert make_svc()._chinese_to_arabic("二十三") == "23"

    def test_one_hundred_three(self):
        assert make_svc()._chinese_to_arabic("一百零三") == "103"

    def test_liang(self):
        assert make_svc()._chinese_to_arabic("两") == "2"

    def test_ten(self):
        assert make_svc()._chinese_to_arabic("十") == "10"

    def test_arabic_passthrough(self):
        assert make_svc()._chinese_to_arabic("1.2") == "1.2"

    def test_mixed_passthrough(self):
        assert make_svc()._chinese_to_arabic("第3章") == "第3章"


class TestNarrativeCleanupTombstones:
    def test_no_narrative_placeholders_field(self):
        assert "narrative_placeholders" not in GeneralizedTemplate.model_fields
```

- [ ] **Step 3.2: 运行确认失败**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q`
Expected: FAIL（`十一`→`101`；`narrative_placeholders` 仍在 model_fields）

- [ ] **Step 3.3: GENERALIZING 双 set 去一**

Edit old_str（service）:
```python
            await service.repo.update_task(task_id, {"status": "GENERALIZING"})

            # ========== 阶段3: 泛化 (GENERALIZING) ==========
            await service.repo.update_task(task_id, {"status": "GENERALIZING"})
```
new_str:
```python
            await service.repo.update_task(task_id, {"status": "GENERALIZING"})
```

- [ ] **Step 3.4: `_chinese_to_arabic` 正规进位解析**

Edit old_str（service :1589-1609，整函数替换）:
```python
    def _chinese_to_arabic(self, cn_num: str) -> str:
        """将中文数字转换为阿拉伯数字"""
        cn_map = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
            "百": "100",
            "千": "1000",
            "万": "10000",
        }
        result = cn_num
        for cn, num in cn_map.items():
            result = result.replace(cn, num)
        return result
```
new_str:
```python
    def _chinese_to_arabic(self, cn_num: str) -> str:
        """中文数字 → 阿拉伯数字（正规进位解析：十一→11、二十三→23、一百零三→103）。

        含非中文数字字符或无法解析时原样返回（调用方有位置编号兜底）。
        """
        digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        units = {"十": 10, "百": 100, "千": 1000}
        if not cn_num:
            return cn_num
        total = 0      # 万段以上累计
        section = 0    # 当前万段累计
        number = 0     # 待乘单位的悬挂数字
        parsed = False
        for ch in cn_num:
            if ch in digits:
                number = digits[ch]
                parsed = True
            elif ch in units:
                section += (number if number else 1) * units[ch]
                number = 0
                parsed = True
            elif ch == "万":
                section = (section + number) * 10000
                total += section
                section = 0
                number = 0
                parsed = True
            elif ch == "亿":
                total = (total + section + number) * 100000000
                section = 0
                number = 0
                parsed = True
            elif ch == "零":
                number = 0
            else:
                return cn_num
        if not parsed:
            return cn_num
        return str(total + section + number)
```

- [ ] **Step 3.5: 空 template_payload 壳不再构建/落库**

Edit old_str（service :867-872）:
```python
            # 全局模板不再单独生成 LLM 调用——前端从段落级 template 聚合
            template_payload = {
                "generalized": "",
                "slots": [],
                "metadata": {"chapter": "", "tags": []},
            }
```
new_str:
```python
            # 全局模板不再单独生成 LLM 调用——前端从段落级 template 聚合；
            # 空壳 payload 不落库（C-5），template_payload 列留 NULL，读取侧 `or {}` 兜底
```
Edit old_str（service :1023-1032 update dict）:
```python
                {
                    "template_payload": template_payload,
                    "base_info": form_data,
```
new_str:
```python
                {
                    "base_info": form_data,
```

- [ ] **Step 3.6: narrative_placeholders 摘除（schema + prompt）**

Edit old_str（service :52）:
```python
    slots: list[GeneralizedSlot] = Field(default_factory=list)
    narrative_placeholders: list[dict[str, Any]] = Field(default_factory=list)
    condition: str = ""
```
new_str:
```python
    slots: list[GeneralizedSlot] = Field(default_factory=list)
    condition: str = ""
```
Edit old_str（service :341-348 prompt 结构段）:
```python
            "  ],\n"
            '  "narrative_placeholders": [\n'
            "     {{\n"
            '       "mark": "叙述标记名称",\n'
            '       "role": "描述该叙述区的用途",\n'
            '       "sample": "原文中的参考文本"\n'
            "     }}\n"
            "  ],\n"
            '  "scope": "universal|regional|project（可选，不确定则省略）",\n'
```
new_str:
```python
            "  ],\n"
            '  "scope": "universal|regional|project（可选，不确定则省略）",\n'
```

- [ ] **Step 3.7: 法规 B 路 docstring 更正**

Edit old_str（service :2206-2209）:
```python
        """场景B：从正文段落中用 LLM 提取标准引用

        仅对 parameter/narrative 类型、且包含标准编号模式的段落调用。
        """
```
new_str:
```python
        """场景B：从正文段落中用 LLM 提取标准引用

        对全部散文段（排除 legal_reference/heading/table/figure/formula 结构类）、
        且包含标准编号模式的段落调用。
        """
```

- [ ] **Step 3.8: EtlWorkbench rawSlots 死代码 + 计数失真修复**

Edit old_str（Workbench :43-46）:
```js
// ========== 未识别实体相关 ==========
const unrecognizedEntities = ref([])
const rawSlots = ref([])
const groupedUnrecognizedEntities = ref({})
```
new_str:
```js
// ========== 未识别实体相关 ==========
const unrecognizedEntities = ref([])
const groupedUnrecognizedEntities = ref({})
```
Edit old_str（Workbench :1920）:
```html
              检测到 <strong>{{ rawSlots.length }}</strong> 个未识别插槽， 其中
```
new_str:
```html
              检测到 <strong>{{ unrecognizedEntities.length }}</strong> 个未识别插槽， 其中
```
（先 Grep 确认 `rawSlots` 全文件仅此两处：`Grep pattern=rawSlots path=web/src/components/domain-factory/EtlWorkbench.vue`）

- [ ] **Step 3.9: EtlWorkbench 叙述型摘要死分支删除（:1784-1823）**

先核实不可达：narrative ∈ PROSE_TYPES（:249），详情区 v-if 链在 :1647 `v-else-if="isProseType(...)"` 已接住 narrative，:1785 的 `v-if="... === 'narrative'"` 永假。

Edit old_str（整块）:
```html
                <!-- 叙述型摘要 -->
                <template
                  v-if="
                    selectedParagraph.classify_type === 'narrative' && selectedParagraph.template
                  "
                >
                  <a-divider style="margin: 8px 0" />
                  <div v-if="selectedParagraph.template.summary" class="detail-field">
                    <span class="detail-label">摘要</span>
                    <div class="detail-value" style="color: var(--gray-800); font-weight: 500">
                      {{ selectedParagraph.template.summary }}
                    </div>
                  </div>
                  <div
                    v-if="selectedParagraph.template.key_points?.length"
                    class="detail-field"
                    style="flex-direction: column; align-items: flex-start"
                  >
                    <span class="detail-label" style="margin-bottom: 4px">关键要点</span>
                    <ul
                      style="margin: 0; padding-left: 16px; font-size: 12px; color: var(--gray-700)"
                    >
                      <li v-for="point in selectedParagraph.template.key_points" :key="point">
                        {{ point }}
                      </li>
                    </ul>
                  </div>
                  <div v-if="selectedParagraph.template.entities?.length" class="detail-field">
                    <span class="detail-label">关键实体</span>
                    <div class="detail-value">
                      <a-tag
                        v-for="ent in selectedParagraph.template.entities"
                        :key="ent"
                        size="small"
                        style="margin: 2px"
                        >{{ ent }}</a-tag
                      >
                    </div>
                  </div>
                </template>

                <a-divider style="margin: 8px 0" />
```
new_str:
```html
                <a-divider style="margin: 8px 0" />
```
（保留其后 `原文` 展示块——属于 else 分支的 list/其他类型。）

- [ ] **Step 3.10: 运行测试确认通过**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q`
Expected: 全部 PASS

- [ ] **Step 3.11: ESLint**

Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && pnpm exec eslint src/components/domain-factory/EtlWorkbench.vue"`
Expected: 无输出

- [ ] **Step 3.12: Commit**

```bash
git add backend/package/pisuan/services/domain_factory_service.py backend/test/unit/test_c_batch_fixes.py web/src/components/domain-factory/EtlWorkbench.vue
git commit -m "fix(factory): C-5 小项组——中文数字正规解析、GENERALIZING 双 set、空壳 payload 不落库；清理叙述死分支/死槽位计数/narrative_placeholders"
```

---

### Task 4: C-4 泛化输入结构化组装

**Files:**
- Modify: `backend/package/pisuan/services/domain_factory_service.py`（新常量+新方法 ~:1589 附近或 generalize 区；:3425-3459 调用点；:3470-3493 文本 prompt；:3509-3517 表格 prompt）
- Test: `backend/test/unit/test_c_batch_fixes.py`（追加）

- [ ] **Step 4.1: 先写失败测试**

在 `test_c_batch_fixes.py` 追加:
```python
class TestGeneralizeInput:
    def test_table_whole_never_truncated(self):
        long_table = "| a | b |\n|---|---|\n" + "\n".join(f"| x{i} | y{i} |" for i in range(500))
        out, truncated = make_svc()._build_generalize_input(long_table, True, "3.2")
        assert truncated is False
        assert out == long_table

    def test_prose_under_budget_with_prefix(self):
        out, truncated = make_svc()._build_generalize_input("短段落。", False, "1.2")
        assert truncated is False
        assert out == "【章节】1.2\n短段落。"

    def test_prose_over_budget_drops_tail_at_boundary(self):
        body = "首句内容。" + "后续句子。" * 2000
        out, truncated = make_svc()._build_generalize_input(body, False, "")
        assert truncated is True
        assert len(out) <= make_svc().GENERALIZE_PROSE_BUDGET
        assert out.endswith("。")
        assert body.startswith(out)
        assert "【章节】" not in out

    def test_no_chapter_no_prefix(self):
        out, _ = make_svc()._build_generalize_input("内容", False, "")
        assert out == "内容"
```

- [ ] **Step 4.2: 运行确认失败**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q -k TestGeneralizeInput`
Expected: FAIL（`_build_generalize_input` 不存在）

- [ ] **Step 4.3: 实现组装方法**

在 service `_chinese_to_arabic` 方法之后插入（Edit old_str 用 Step 3.4 新实现的函数尾部 + 下一个方法头锚定）:
```python
        if not parsed:
            return cn_num
        return str(total + section + number)

    def _compute_section_path(self, level: int, title: str, num_part: str | None = None) -> list[str]:
```
new_str:
```python
        if not parsed:
            return cn_num
        return str(total + section + number)

    GENERALIZE_PROSE_BUDGET: ClassVar[int] = 4000

    def _build_generalize_input(self, text: str, is_table: bool, chapter_hint: str) -> tuple[str, bool]:
        """组装泛化输入（C-4 结构化组装，替代 text[:1200]/[:1500] 中间截断）。

        - 表格段落整块传递、永不切碎（「表格整块不切碎」裁定），不设预算；
        - prose 段落超预算时按块（句号/分号/换行边界）丢尾，保留头部（环评语义密度前置）；
        - 章节路径非空时前置标题行。
        Returns: (组装后文本, 是否发生丢尾)
        """
        if is_table:
            return text, False
        truncated = False
        if len(text) > self.GENERALIZE_PROSE_BUDGET:
            head = text[: self.GENERALIZE_PROSE_BUDGET]
            cut = max(head.rfind("。"), head.rfind("；"), head.rfind("\n"))
            body = head[: cut + 1] if cut > 0 else head
            truncated = True
        else:
            body = text
        prefix = f"【章节】{chapter_hint}\n" if chapter_hint else ""
        return prefix + body, truncated

    def _compute_section_path(self, level: int, title: str, num_part: str | None = None) -> list[str]:
```

- [ ] **Step 4.4: 替换四个截断点**

Edit old_str（`_run_for_paragraph` prompt 构建段 :3425-3443）:
```python
            # 根据段落类型构建不同的 Prompt
            if is_table and table_format == "markdown":
                # Markdown 表格类型的段落
                prompt = self._build_table_generalize_prompt(
                    text,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
            else:
                # 普通文本段落
                prompt = self._build_text_generalize_prompt(
                    text,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
```
new_str:
```python
            # C-4 结构化组装：表格整块 / prose 块边界丢尾（替代 text[:1200] 中间截断）
            generalize_input, input_truncated = self._build_generalize_input(text, is_table, chapter_hint)
            if input_truncated:
                logger.info(f"泛化输入超长丢尾: 段落 {para_id} {len(text)}→{len(generalize_input)} 字符")
            # 根据段落类型构建不同的 Prompt
            if is_table and table_format == "markdown":
                # Markdown 表格类型的段落
                prompt = self._build_table_generalize_prompt(
                    generalize_input,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
            else:
                # 普通文本段落
                prompt = self._build_text_generalize_prompt(
                    generalize_input,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
```

Edit old_str（LLM 调用实参 :3451）:
```python
                resp, outcome = await self._generalize_text_tracked(text[:1200], chapter_hint, prompt=prompt)
                _record_outcome(outcome)
                progress["done"] += 1
```
new_str:
```python
                resp, outcome = await self._generalize_text_tracked(generalize_input, chapter_hint, prompt=prompt)
                _record_outcome(outcome)
                progress["done"] += 1
```

Edit old_str（结果回写 :3458-3459）:
```python
                if resp is not None:
                    results[para_id] = resp
```
new_str:
```python
                if resp is not None:
                    if input_truncated and isinstance(resp, dict):
                        meta = resp.get("metadata")
                        if not isinstance(meta, dict):
                            meta = {}
                            resp["metadata"] = meta
                        meta["truncated"] = True
                    results[para_id] = resp
```

Edit old_str（`_build_text_generalize_prompt` 两处 content，:3479-3493）:
```python
        if prompt_template:
            return self._render_prompt(
                prompt_template,
                content=text[:1200],
                schema_text=schema_text,
                chapter_hint=chapter_hint,
                domain_label=domain_label,
            )
        return self._render_prompt(
            self._PROMPT_DEFAULTS["template"],
            content=text[:1200],
            schema_text=schema_text,
            chapter_hint=chapter_hint,
            domain_label=domain_label,
        )
```
new_str:
```python
        # C-4：content 已由 _build_generalize_input 完成预算控制，此处不再中间截断
        if prompt_template:
            return self._render_prompt(
                prompt_template,
                content=text,
                schema_text=schema_text,
                chapter_hint=chapter_hint,
                domain_label=domain_label,
            )
        return self._render_prompt(
            self._PROMPT_DEFAULTS["template"],
            content=text,
            schema_text=schema_text,
            chapter_hint=chapter_hint,
            domain_label=domain_label,
        )
```

Edit old_str（表格 prompt :3517）:
```python
            f'"""\n{table_text[:1500]}\n"""\n\n'
```
new_str:
```python
            f'"""\n{table_text}\n"""\n\n'
```

- [ ] **Step 4.5: 运行测试**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q`
Expected: 全部 PASS

- [ ] **Step 4.6: Commit**

```bash
git add backend/package/pisuan/services/domain_factory_service.py backend/test/unit/test_c_batch_fixes.py
git commit -m "fix(factory): C-4 泛化输入结构化组装——表格整块永不切碎、prose 4000 字符块边界丢尾、截断 metadata 置位"
```

---

### Task 4b: bug-4227 markdown 表格泛化 kwarg 错配（追加项，2026-11-11 用户批准并入）

**背景**：Task 4 规格审查发现的潜伏 P1——`_run_for_paragraph` :3468 给 `_build_table_generalize_prompt`（签名仅 4 参，:3537-3543）传 `prompt_template=template_prompt`，markdown 表格段落（:1548 解析产线真实产出）进泛化即 TypeError，gather 无 return_exceptions 杀死整轮。docx/pdf 的 HTML 表走 `table_format=="html"` 的 :3423 跳过路径，故生产未爆。先于 C-4 存在。buglog 已记 bug-4227。

**Files:**
- Modify: `backend/package/pisuan/services/domain_factory_service.py`（:3468 一行）

- [ ] **Step 4b.1: 删除调用点 kwarg**

Edit old_str:
```python
                prompt = self._build_table_generalize_prompt(
                    generalize_input,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
```
new_str:
```python
                # bug-4227：表格泛化不套用域自定义模板（builder 文档语义：表格直接返回结构化信息）
                prompt = self._build_table_generalize_prompt(
                    generalize_input,
                    schema_text,
                    chapter_hint,
                    domain_label,
                )
```

- [ ] **Step 4b.2: 验证 + 独立提交**

Run: `MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q`（42 绿）
Run: Grep `_build_table_generalize_prompt` 全服务确认仅剩一个调用点且形参匹配
Commit:
```bash
git add backend/package/pisuan/services/domain_factory_service.py
git commit -m "fix(factory): bug-4227 表格泛化调用传入 builder 不存在的 prompt_template 形参，markdown 表格段落即崩"
```

### Task 5: C-1 INGESTING 状态机 + 入库幂等（最重项）

**Files:**
- Modify: `backend/package/pisuan/repositories/domain_factory_repository.py`（迁移表+校验器+begin_ingest+守卫）
- Modify: `backend/package/pisuan/services/domain_factory_service.py`（commit/reingest 管线、retry 守卫、fail handler）
- Modify: `backend/package/pisuan/services/task_registry.py`（failure_function 注册）
- Modify: `web/src/stores/tasker.js`、`web/src/components/domain-factory/DataSourceDashboard.vue`（INGESTING 条目）
- Test: `backend/test/unit/test_c_batch_fixes.py`（追加迁移表用例）

#### Task 5a: 迁移表 + 校验器（独立提交）

- [ ] **Step 5a.1: 先写失败测试**

在 `test_c_batch_fixes.py` 顶部 import 区追加:
```python
from pisuan.repositories.domain_factory_repository import (
    TASK_STATUS_EDGES,
    _validate_status_transition,
)
```
文件末尾追加:
```python
class TestStatusTransition:
    MAIN_CHAIN = [
        ("UPLOADED", "PARSING"),
        ("PARSING", "GENERALIZING"),
        ("GENERALIZING", "WAITING_REVIEW"),
        ("WAITING_REVIEW", "INGESTING"),
        ("INGESTING", "COMMITTED"),
        ("INGESTING", "COMMIT_PARTIAL"),
        ("INGESTING", "COMMIT_FAILED"),
    ]

    def test_main_chain_legal(self):
        for cur, nxt in self.MAIN_CHAIN:
            _validate_status_transition(cur, nxt)  # 不抛即合法

    def test_same_value_noop(self):
        _validate_status_transition("WAITING_REVIEW", "WAITING_REVIEW")
        _validate_status_transition("COMMITTED", "COMMITTED")

    def test_illegal_raises(self):
        with pytest.raises(ValueError):
            _validate_status_transition("COMMITTED", "PARSING")
        with pytest.raises(ValueError):
            _validate_status_transition("PARSING", "COMMITTED")
        with pytest.raises(ValueError):
            _validate_status_transition("INGESTING", "UPLOADED")

    def test_retry_and_resume_edges(self):
        # C-3 恢复边 + durable ETL 收敛边：UPLOADED→FAILED
        _validate_status_transition("UPLOADED", "FAILED")
        # 提交前校验中止边：WAITING_REVIEW→COMMIT_FAILED（既有行为）
        _validate_status_transition("WAITING_REVIEW", "COMMIT_FAILED")
        # 泛化失败收敛边
        _validate_status_transition("PARSING", "FAILED")
        _validate_status_transition("GENERALIZING", "FAILED")
        _validate_status_transition("GENERALIZING", "FAILED_PROVIDER")
        # resume：FAILED_PROVIDER→GENERALIZING（断点续跑）
        _validate_status_transition("FAILED_PROVIDER", "GENERALIZING")
        # retry（对齐 retry_task 守卫现状）：非运行态均可重置 UPLOADED
        for source in ("FAILED", "FAILED_PROVIDER", "WAITING_REVIEW",
                       "COMMIT_FAILED", "COMMIT_PARTIAL", "COMMITTED"):
            _validate_status_transition(source, "UPLOADED")

    def test_all_states_covered(self):
        for status in ("UPLOADED", "PARSING", "GENERALIZING", "WAITING_REVIEW", "INGESTING",
                       "FAILED", "FAILED_PROVIDER", "COMMITTED", "COMMIT_PARTIAL", "COMMIT_FAILED"):
            assert status in TASK_STATUS_EDGES
```

- [ ] **Step 5a.2: 运行确认失败**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q -k TestStatusTransition`
Expected: FAIL（ImportError: 无法导入 TASK_STATUS_EDGES）

- [ ] **Step 5a.3: repo 添加迁移表与校验器**

在 `domain_factory_repository.py` 模块常量区（`_DOMAIN_ALIASES` 等定义之后、第一个 class 之前）插入：
```python
# ---------------------------------------------------------------------------
# C-1 状态机：合法迁移表。键=当前状态，值=允许迁移到的目标集合。
# 同值重写不计为迁移；非法迁移 raise ValueError（fail-loud，不用静默兜底掩盖）。
# 已知写盘点普查（2026-11-10）：
#   service create_task/retry_task/_etl_pipeline_async(:858 GENERALIZING, 终态 WAITING_REVIEW/
#   FAILED/FAILED_PROVIDER)、commit 管线(:4493/:4510/:4583/:4666/:4721/:4744)、
#   reingest 管线(:5723/:5742)、repo.commit_task(:280)、fail_domain_factory_etl(:6803 直写)。
# ---------------------------------------------------------------------------
TASK_STATUS_EDGES: dict[str, set[str]] = {
    # UPLOADED→各终态/等待态：retry_task 入队失败恢复原状态（C-3）
    "UPLOADED": {"PARSING", "FAILED", "FAILED_PROVIDER", "WAITING_REVIEW",
                 "COMMITTED", "COMMIT_FAILED", "COMMIT_PARTIAL"},
    "PARSING": {"GENERALIZING", "FAILED"},
    "GENERALIZING": {"WAITING_REVIEW", "FAILED", "FAILED_PROVIDER"},
    # WAITING_REVIEW→COMMIT_FAILED：提交前校验中止（:4493 既有行为）
    "WAITING_REVIEW": {"INGESTING", "COMMIT_FAILED", "UPLOADED"},
    "INGESTING": {"COMMITTED", "COMMIT_PARTIAL", "COMMIT_FAILED"},
    "FAILED": {"UPLOADED"},
    "FAILED_PROVIDER": {"UPLOADED", "GENERALIZING"},
    # COMMITTED/PARTIAL/FAILED→UPLOADED：retry 现守卫允许；→INGESTING：reingest 入口
    "COMMITTED": {"UPLOADED", "INGESTING", "COMMITTED"},
    "COMMIT_PARTIAL": {"UPLOADED", "INGESTING", "COMMITTED"},
    "COMMIT_FAILED": {"UPLOADED", "INGESTING", "COMMITTED"},
}


def _validate_status_transition(current: str | None, target: str) -> None:
    """校验任务状态迁移合法性；同值重写放行，非法迁移 raise ValueError。"""
    if current == target:
        return
    allowed = TASK_STATUS_EDGES.get(current or "", set())
    if target not in allowed:
        raise ValueError(f"非法状态迁移: {current or '<None>'} → {target}")
```

- [ ] **Step 5a.4: update_task / commit_task 接守卫**

Edit old_str（repo update_task）:
```python
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            for key, value in data.items():
                if key not in ("id",):
                    setattr(task, key, value)
        return task

    async def commit_task(
```
new_str:
```python
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            target_status = data.get("status")
            if target_status is not None:
                _validate_status_transition(task.status, target_status)
            for key, value in data.items():
                if key not in ("id",):
                    setattr(task, key, value)
        return task

    async def commit_task(
```
Edit old_str（repo commit_task 状态写入前）:
```python
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
```
new_str:
```python
            _validate_status_transition(task.status, "COMMITTED")
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
```

- [ ] **Step 5a.5: repo 添加 begin_ingest**

在 `commit_task` 方法结束（`return task`）与 `async def delete_task` 之间插入：
```python
    async def begin_ingest(
        self, task_id: str, reviewer: str | None = None, ingest_task_id: str | None = None
    ) -> DomainFactoryTask | None:
        """C-1：入库链入口，落 INGESTING 中间态（归属字段早写，终态后置）。"""
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            _validate_status_transition(task.status, "INGESTING")
            task.status = "INGESTING"
            if reviewer:
                task.reviewer = reviewer
            if ingest_task_id:
                task.ingest_task_id = ingest_task_id
        return task
```

- [ ] **Step 5a.6: 运行迁移表测试**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q`
Expected: 全部 PASS

- [ ] **Step 5a.7: Commit（迁移校验单独提交，可独立 revert）**

```bash
git add backend/package/pisuan/repositories/domain_factory_repository.py backend/test/unit/test_c_batch_fixes.py
git commit -m "fix(factory): C-1a 任务状态合法迁移校验——TASK_STATUS_EDGES 迁移表 + update_task/commit_task 守卫 + begin_ingest"
```

#### Task 5b: 管线切换 + 幂等 + 前端映射

- [ ] **Step 5b.1: commit 管线——早落 INGESTING 替代早落 COMMITTED**

Edit old_str（service :4509-4510）:
```python
            # 更新任务状态为 COMMITTED
            await service.repo.commit_task(task_id, reviewer, ingest_task_id=ingest_task_id)
```
new_str:
```python
            # C-1 状态机收敛：先落 INGESTING（归属字段早写）；COMMITTED 只在入库成功后落
            await service.repo.begin_ingest(task_id, reviewer, ingest_task_id=ingest_task_id)
```

- [ ] **Step 5b.2: KB 入库失败改落 COMMIT_FAILED**

Edit old_str（service :4580-4586）:
```python
                    await service.repo.update_task(
                        task_id,
                        {
                            "status": "FAILED",
                            "error_message": f"知识库入库失败: {e}",
                        },
                    )
```
new_str:
```python
                    await service.repo.update_task(
                        task_id,
                        {
                            "status": "COMMIT_FAILED",
                            "error_message": f"知识库入库失败: {e}",
                        },
                    )
```

- [ ] **Step 5b.3: commit 管线外层 except 改落 COMMIT_FAILED**

（外层 try 从 begin_ingest 之后全部处于 INGESTING 态；begin_ingest 自身失败时任务仍 WAITING_REVIEW，WAITING_REVIEW→COMMIT_FAILED 亦合法）

Edit old_str（service :4742-4747）:
```python
        except Exception as e:
            logger.exception(f"入库流水线执行失败: {task_id}")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": str(e)})
            await context.set_progress(100.0, f"入库失败: {str(e)}")
            await context.set_message(f"入库失败: {str(e)}")
            return {"error": str(e)}

    def _build_ingest_markdown(self, task_detail: dict[str, Any]) -> str:
```
new_str:
```python
        except Exception as e:
            logger.exception(f"入库流水线执行失败: {task_id}")
            await service.repo.update_task(
                task_id,
                {"status": "COMMIT_FAILED", "error_message": f"入库流水线执行失败: {e}"},
            )
            await context.set_progress(100.0, f"入库失败: {str(e)}")
            await context.set_message(f"入库失败: {str(e)}")
            return {"error": str(e)}

    def _build_ingest_markdown(self, task_detail: dict[str, Any]) -> str:
```

- [ ] **Step 5b.4: commit file_id 确定化**

Edit old_str（service :4532）:
```python
                    file_id = f"df_{hashstr(task_id + str(uuid.uuid4()), 8)}"
```
new_str:
```python
                    file_id = f"df_{hashstr(task_id, 12)}"  # C-1 幂等：确定性 ID，同 task 重复入库同 key 覆盖
```

- [ ] **Step 5b.4b: 核实同 key 覆盖语义（设计 §5.2 实施核实项）**

Run: `grep -n "file_id" backend/package/pisuan/services/domain_factory_service.py`
定位 :4532（commit）/ :5647（reingest）附近 file_id 的下游消费调用（KB 上传/索引方法）。

Read 该调用点上下游 ~20 行，确认 KB 方法签名；再打开 `pisuan/knowledge` 对应实现（LightRAG 路径查 `apipeline_enqueue_documents`/`index_file` 的同 id 去重，Milvus 路径查 insert 是否按主键覆盖）。
判定规则：
- 该链路对同 file_id 是 **upsert / 先删后插** → 无需改动，Step 5b.4 的确定性 ID 即天然幂等；
- 该链路对同 file_id 是**盲目插入（产生重复文档）** → 在 ingest 调用前补一步按 file_id 删除旧文档（用对应 KB 管理器的既有 delete 接口，用法参考同类调用点），并在提交说明中注明。

Expected: 得出明确结论并按规则执行（结论写入提交说明）。

- [ ] **Step 5b.5: reingest 管线四处**

Edit old_str（reingest 入口 :5618-5620）:
```python
        try:
            await context.set_progress(10.0, "正在准备再入库...")
            await context.set_message("正在准备再入库...")
```
new_str:
```python
        try:
            # C-1：再入库同样走 INGESTING 中间态，durable 中断由 fail_domain_factory_ingest 收敛
            await service.repo.update_task(task_id, {"status": "INGESTING"})
            await context.set_progress(10.0, "正在准备再入库...")
            await context.set_message("正在准备再入库...")
```
Edit old_str（reingest file_id :5647）:
```python
                file_id = f"df_ri_{hashstr(task_id + str(uuid.uuid4()), 8)}"
```
new_str:
```python
                file_id = f"df_ri_{hashstr(task_id, 12)}"  # C-1 幂等：确定性 ID
```
Edit old_str（reingest ingest_task_id :5727）:
```python
                    "ingest_task_id": f"reingest_{task_id}_{uuid.uuid4().hex[:8]}",
```
new_str:
```python
                    "ingest_task_id": f"reingest_{task_id}",  # C-1 幂等：确定性标识
```
Edit old_str（reingest 外层 except :5741-5742）:
```python
            logger.exception(f"再入库流水线执行失败: {task_id}")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": str(e)})
```
new_str:
```python
            logger.exception(f"再入库流水线执行失败: {task_id}")
            await service.repo.update_task(
                task_id,
                {"status": "COMMIT_FAILED", "error_message": f"再入库流水线执行失败: {e}"},
            )
```

- [ ] **Step 5b.6: retry 守卫扩 INGESTING**

Edit old_str（service :5761-5763）:
```python
        # 运行中任务禁止重复重试（路由层捕获 ValueError 返回给前端）
        if task.status in ("PARSING", "GENERALIZING"):
            raise ValueError(f"任务正在执行中（{task.status}），请稍后再试")
```
new_str:
```python
        # 运行中/入库中任务禁止重复重试（路由层捕获 ValueError 返回给前端）
        if task.status in ("PARSING", "GENERALIZING", "INGESTING"):
            raise ValueError(f"任务正在执行中（{task.status}），请稍后再试")
```

- [ ] **Step 5b.7: 新增 fail_domain_factory_ingest 并注册**

在 `fail_domain_factory_etl` 函数之后（service :6807 之后）插入：
```python
async def fail_domain_factory_ingest(session, task_record, error: str) -> None:
    """任务失败收敛（C-1）：durable 层失败时把 INGESTING 残留的入库/再入库任务落为 COMMIT_FAILED。

    domain_factory_ingest / domain_factory_reingest 此前未注册 failure handler，
    worker lease 过期等异常终止会让任务滞留 INGESTING（或 COMMITTED 假象），用户不可见也无法重试。
    """
    from sqlalchemy import select

    from pisuan.storage.postgres.models_domain_factory import DomainFactoryTask

    task_id = (task_record.payload or {}).get("task_id")
    if not task_id:
        return
    task = await session.scalar(
        select(DomainFactoryTask).where(DomainFactoryTask.id == task_id).with_for_update()
    )
    if task is None or task.status != "INGESTING":
        return
    task.status = "COMMIT_FAILED"
    task.error_message = f"入库执行中断（durable 收敛）：{error}"
    logger.warning(f"入库任务 {task_id} INGESTING 残留，durable 收敛落为 COMMIT_FAILED: {error}")
```

Edit old_str（task_registry :97-106）:
```python
        TaskDefinition(
            "domain_factory_ingest",
            "pisuan.services.domain_factory_service",
            "run_domain_factory_ingest",
        ),
        TaskDefinition(
            "domain_factory_reingest",
            "pisuan.services.domain_factory_service",
            "run_domain_factory_reingest",
        ),
```
new_str:
```python
        TaskDefinition(
            "domain_factory_ingest",
            "pisuan.services.domain_factory_service",
            "run_domain_factory_ingest",
            failure_function="fail_domain_factory_ingest",
        ),
        TaskDefinition(
            "domain_factory_reingest",
            "pisuan.services.domain_factory_service",
            "run_domain_factory_reingest",
            failure_function="fail_domain_factory_ingest",
        ),
```

- [ ] **Step 5b.8: 前端 INGESTING 条目**

Edit old_str（tasker.js :42-43）:
```js
  WAITING_REVIEW: { status: 'running', progress: 95, message: '信息提取完成，等待人工审核...' },
  COMMITTED: { status: 'success', progress: 100, message: '报告已入库完成' },
```
new_str:
```js
  WAITING_REVIEW: { status: 'running', progress: 95, message: '信息提取完成，等待人工审核...' },
  INGESTING: { status: 'running', progress: 97, message: '报告入库中...' },
  COMMITTED: { status: 'success', progress: 100, message: '报告已入库完成' },
```
（设计文档原拟 WAITING_REVIEW 降 90，实施取 INGESTING=97：单调 95<97<100 且少改一处。）

Edit old_str（Dashboard :75-76）:
```js
  WAITING_REVIEW: { color: 'var(--color-warning-500)', text: '待校验' },
  COMMITTED: { color: 'var(--color-success-500)', text: '已入库' },
```
new_str:
```js
  WAITING_REVIEW: { color: 'var(--color-warning-500)', text: '待校验' },
  INGESTING: { color: 'var(--color-info-500)', text: '入库中' },
  COMMITTED: { color: 'var(--color-success-500)', text: '已入库' },
```

- [ ] **Step 5b.9: 状态写盘点普查（防迁移表遗漏）**

Run: `grep -n '"status": "' backend/package/pisuan/services/domain_factory_service.py | grep -v '#'`
逐行核对每个写盘目标状态对（当前态→目标态）均在上表内。已知全部写盘点：:858 GENERALIZING、WAITING_REVIEW 终态、FAILED/FAILED_PROVIDER 收敛、:4493/:4510/:4580/:4666/:4721/:4744 commit 链、:5618+/:5723/:5740 reingest 链、retry_task :5767、create_task C-3 FAILED。直写 `task.status =` 仅 repo.commit_task(:280)/begin_ingest（已接守卫）与 fail_domain_factory_etl(:6803)（自带状态白名单，语义即收敛，豁免）。
Expected: 无表外迁移边；若发现遗漏边 → 补 TASK_STATUS_EDGES 并加测试用例后重跑。

- [ ] **Step 5b.10: 全量单测 + ESLint**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q`
Expected: 全部 PASS
Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && pnpm exec eslint src/components/domain-factory/DataSourceDashboard.vue src/stores/tasker.js"`
Expected: 无输出

- [ ] **Step 5b.11: 容器内冒烟（worker 侧注册表加载）**

Run: `docker exec pisuan-localized-worker-1 python -c "from pisuan.services.task_registry import DEFAULT_TASK_DEFINITIONS; print('REGISTRY_OK')"`
Expected: `REGISTRY_OK`（若常量名不同，先 `grep -n "TaskDefinition(" backend/package/pisuan/services/task_registry.py | head -3` 找到宿主列表变量名再 import 对应符号）

- [ ] **Step 5b.12: Commit**

```bash
git add backend/package/pisuan/services/domain_factory_service.py backend/package/pisuan/services/task_registry.py web/src/stores/tasker.js web/src/components/domain-factory/DataSourceDashboard.vue
git commit -m "fix(factory): C-1b 入库状态机收敛——INGESTING 中间态、file_id/ingest_task_id 确定化幂等、ingest/reingest durable 收敛、retry 禁入库中"
```

---

### Task 6: 总验收 + changelog

**Files:**
- Modify: `docs/develop-guides/changelog.md`

- [ ] **Step 6.1: 后端全量单测**

Run: `docker exec pisuan-localized-api-1 pytest /app/test/unit --noconftest -q`
Expected: 全部 PASS（如存在与本批无关的既有失败，逐条比对确认非本批引入）

- [ ] **Step 6.2: 后端格式化**

Run: `make format`（宿主，ruff format + check + isort）
Expected: 无 diff 或格式化后语法检查 OK

- [ ] **Step 6.3: changelog 补记**

在 `docs/develop-guides/changelog.md` 最新版本段的「功能与修复」列表顶部插入一条：
```markdown
- fix(factory): ETL C批行为修复五项——① enqueue 失败兜底（create_task 落 FAILED、retry_task 恢复原状态保住断点续跑资格）；② FAILED_PROVIDER 前端可达（状态条目+重试入口）；③ 小项组（中文章节数字正规进位解析十一→11、GENERALIZING 双 set、空壳 template_payload 不落库、rawSlots 死代码、叙述摘要死分支、narrative_placeholders 摘除）；④ 泛化输入结构化组装（表格整块永不切碎、prose 4000 字符块边界丢尾、截断 metadata 置位）；⑤ 入库状态机收敛（WAITING_REVIEW→INGESTING→COMMITTED/COMMIT_PARTIAL/COMMIT_FAILED、合法迁移校验表、file_id/ingest_task_id 确定化幂等、ingest/reingest durable failure handler、retry 禁入库中）。设计：docs/vibe/2026-11-10-etl-c-batch-fix-design.md
```

- [ ] **Step 6.4: Commit**

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(changelog): ETL C批行为修复补记"
```

- [ ] **Step 6.5: E2E 人工验收清单（用户参与）**

1. 上传一份**含长表格**的样例报告 → 任务中心唯一卡片、状态流转 UPLOADED→PARSING→GENERALIZING→WAITING_REVIEW；泛化日志无「超长丢尾」误伤表格（表格不截断）
2. 审核通过 → 任务中心出现「报告入库中」(97%) → COMMITTED「已入库」；KB 文档列表中该文档 file_id 形如 `df_<12位hex>`
3. 再入库一次 → **不产生重复 KB 文档**（同 `df_ri_<12位hex>` 覆盖）
4. SQL 模拟熔断态后验证 C-2：`docker exec pisuan-localized-postgres-1 psql -U postgres -d <库名> -c "UPDATE domain_factory_tasks SET status='FAILED_PROVIDER' WHERE id='<task_id>'"` → **数据源列表**显示「服务商中断」+ 重试按钮，**且任务中心抽屉**对应行不再显示原码/空消息（DOMAIN_FACTORY_STATUS_MAP 映射生效、failed 徽标计数）→ 点击后日志 templated 只增不清零（resume 续跑）
5. （可选）断网 LLM 端点触发真熔断 → FAILED_PROVIDER 落库 → UI 同上

---

## Self-Review 记录

- **Spec 覆盖**：设计文档 §1(C-3)→Task1、§2(C-2)→Task2、§3(C-5 七项)→Task3、§4(C-4)→Task4、§5(C-1 全部四个子项+勘误后状态链，含 §5.2 覆盖语义核实步)→Task5a/5b、§6 提交切分→各任务 commit、§7 风险（迁移校验独立提交）→Task5a 单独 commit。✓
- **占位符**：无 TBD；Step 5b.4b（KB 覆盖语义）、5b.9（写盘点普查）、5b.11（常量名探测）均给出具体命令与判定规则。✓
- **类型一致性**：`_validate_status_transition`/`TASK_STATUS_EDGES`/`begin_ingest` 命名在 5a 定义与 5b 使用一致；`_build_generalize_input` 返回 `tuple[str, bool]` 与调用点解构一致；测试引用 `GENERALIZE_PROSE_BUDGET` 为 ClassVar；`fail_domain_factory_ingest(session, task_record, error)` 签名已对照 `fail_domain_factory_etl`（service:6790-6807 实测）完全对齐。✓
- **已知偏差**（设计→实施，均已注明理由）：
  1. WAITING_REVIEW progress 保持 95 不降、INGESTING 取 97（比设计的 90/90 单调且少改一处）；
  2. retry_task 恢复失败时内存对象同步（restored 回读）；
  3. `fail_domain_factory_reingest` 并入单一 `fail_domain_factory_ingest` 同时注册给两类任务——5b.5 已让 reingest 入口落 INGESTING，两类残留态相同，两份同义函数属复制；
  4. GENERALIZING 双 set 删除保留首个 set（:858，归位于「阶段2: 泛化」头注释下）、删除「阶段3」头注释+重复 set 整块——设计原文写「删 :858」，按其真实意图（注释归位、消除重复块）取保留连贯块的等价实现（实测 :853-861 确认结构）；
  5. retry 边含 `COMMIT_PARTIAL→UPLOADED`（设计 §5.3 清单漏列，但 retry 守卫现状允许，本批不扩权/不收权，对齐守卫现实）；
  6. **C-3 的 mock 单测未纳入计划**（设计 §1 验收项）：create_task/retry_task 全程依赖 DB-backed repo/tasker 协作者，项目单测惯例（test_w1 `__new__` 模式）只覆盖纯方法；改为由迁移表测试（UPLOADED→FAILED 边）+ 容器 import 冒烟 + E2E 演练覆盖，若用户要求补 mock 集成测试则按 testing-guidelines 放 `test/integration/` 另行补写。
