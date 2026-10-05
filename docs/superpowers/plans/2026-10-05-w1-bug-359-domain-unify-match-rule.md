# bug-359 W1 首项实施计划：domain 词形统一 + 学习模板 match_rule 注入

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 bug-359（学习模板永远匹配不中）：domain 词形全栈统一到 `coal`（真实统一，删映射层），学习模板注入时按 `chapter` 生成 fallback match_rule，打通 `match_count` 数据通路。

**Architecture:** 三层改动：①词形原子翻转（静态模板 30 json + 目录改名 + 代码 5 处词形/硬编码，等价交换，全量回归守护）；②`add_templates_from_list` 注入生成 `fallback_keywords`（TDD，走 matcher 既有 fallback 路径，matcher 本身零改动）；③容器冒烟复验（W0 方法论：自匹配命中 > 0）+ 收尾。

**Tech Stack:** Python 3.12 / SQLAlchemy asyncio / pytest / ruff (uv run) / Docker Compose（pisuan-localized-* 运行栈）

**设计依据:** [2026-10-05-bug-359-domain-unify-match-rule-design.md](../specs/2026-10-05-bug-359-domain-unify-match-rule-design.md)

---

## 全局上下文（每个 implementer 必读）

- **运行栈容器是 `pisuan-localized-*`**（如 `pisuan-localized-api-1`）；`api-dev` 不存在。
- 任何容器验证前先同步运行栈：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1`（把 C:\workspace\pisuan 工作树同步到 localized 树并再生 yuxi→pisuan 改名层）。
- `docker exec` 一律加 `MSYS_NO_PATHCONV=1` 前缀（Git Bash MSYS 路径转换坑）。
- 容器内包名是 `pisuan`（直写 python -c 用 `pisuan.*` 导入）；**测试文件写 `yuxi.*` 是正确的**（sync 会改名）。
- 回归基线（bug-360 裁决口径，2026-10-05）：`pytest /app/test/unit` → **2676 passed / 0 failed / 61 skipped**；其中 unit/services 子套件 **1018 passed / 3 skipped / 0 failed**（3 skip = bug-357 test_formula_chunk，勿动）。**勿用 `pytest /app/test`**——unit 与 integration 存在同名单测文件（bug-360），全量收集 import file mismatch 报 3 errors。
- ruff：`cd backend && uv run ruff format <files> && uv run ruff check <files>`；**uv run 会改写 uv.lock，用完 `git checkout -- uv.lock` 还原**。host ruff 版本（0.15.12）与锁（0.16.4）不一致，勿用裸 ruff。
- **禁碰文件**（其他会话的未提交改动，严禁卷入提交）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`。
- 本次所有改动文件均 pisuan-owned（`git cat-file -e main:<path>` 验证过 templates/ 与三个 service 文件），**无需 `[pisuan-custom]` 标记**。
- 提交信息：中文 Conventional Commits，结尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 全量回归命令：`MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit -q --no-header 2>&1 | tail -3`

---

### Task 1: domain 词形统一（原子翻转）

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:134,150,647,656`
- Modify: `backend/package/yuxi/services/template_generator.py:37`
- Modify: `backend/package/yuxi/services/template_matcher.py:36,38`（docstring）
- Rename: `backend/templates/coal_mining/` → `backend/templates/coal/`
- Modify: `backend/templates/coal/headers/*.json` ×30（sed）
- Modify: `backend/test/unit/services/test_template_system.py`（词形跟随）
- Modify: `docs/develop-guides/upstream-sync-guide.md:300`

这是等价交换型重构：翻转前后系统行为不变（coal 领域内），以既有全量回归套件为守护测试，不新增测试。

- [ ] **Step 1: 目录改名 + 静态 JSON 词形**

```bash
git mv backend/templates/coal_mining backend/templates/coal
sed -i 's/"domain": "coal_mining"/"domain": "coal"/g' backend/templates/coal/headers/*.json
grep -rn "coal_mining" backend/templates/ && echo "FAIL: 残留词形" || echo "OK: 静态模板词形清洁"
```

Expected: `OK: 静态模板词形清洁`（routing_config.json 本无 coal_mining，headers 30 个文件各 1 处）。

- [ ] **Step 2: service 三处词形（domain_factory_service.py）**

:134 默认参数：

```python
# before
    async def _get_template_matcher(self, domain: str = "coal_mining") -> Any:
# after
    async def _get_template_matcher(self, domain: str = "coal") -> Any:
```

:149-151 删除 replace 归一链（bug-359 的映射层）：

```python
# before
            # 从 DB 加载学习模板并注入
            try:
                domain_code = domain.replace("_mining", "").replace("_", "") or "coal"
                db_templates = await self.repo.list_learned_templates(domain_code=domain_code)
# after
            # 从 DB 加载学习模板并注入
            try:
                db_templates = await self.repo.list_learned_templates(domain_code=domain)
```

:647 与 :656（`_etl_parse_stage` 内，`domain_code` 是该方法既有参数）：

```python
# before
                matcher = await service._get_template_matcher()
# after
                matcher = await service._get_template_matcher(domain_code or "coal")
```

```python
# before
                    match_result = matcher.match(title, context={"domain": "coal_mining"})
# after
                    match_result = matcher.match(title, context={"domain": domain_code or "coal"})
```

- [ ] **Step 3: generator 缺省参 + matcher docstring**

template_generator.py:37：

```python
# before
        domain: str = "coal_mining",
# after
        domain: str = "coal",
```

template_matcher.py:36,38（类 docstring 用法示例）：

```python
# before
        library = TemplateLibrary("templates/coal_mining/headers")
        matcher = TemplateMatcher(library.get_all_templates())
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal_mining"})
# after
        library = TemplateLibrary("templates/coal/headers")
        matcher = TemplateMatcher(library.get_all_templates())
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal"})
```

- [ ] **Step 4: 测试词形跟随 + sync-guide 路径**

```bash
sed -i 's/coal_mining/coal/g' backend/test/unit/services/test_template_system.py
sed -i 's|backend/templates/coal_mining/|backend/templates/coal/|' docs/develop-guides/upstream-sync-guide.md
grep -rn "coal_mining" backend/test backend/package backend/templates docs/develop-guides/upstream-sync-guide.md && echo "FAIL: 有残留" || echo "OK: 全部清洁"
```

Expected: `OK: 全部清洁`（web/ 与 docs/vibe 历史文档中的 coal 不在本任务范围）。

- [ ] **Step 5: 容器全量回归（等价交换验证）**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test -q --no-header 2>&1 | tail -5
```

Expected: `≥1018 passed, 3 skipped, 0 failed`。任何失败都要先查明是否本任务引起（对照 main 基线），不是则停手上报。

- [ ] **Step 6: ruff + 提交**

```bash
cd backend && uv run ruff format package/yuxi/services/domain_factory_service.py package/yuxi/services/template_generator.py package/yuxi/services/template_matcher.py package/yuxi/services/template_library.py test/unit/services/test_template_system.py && uv run ruff check package/yuxi/services/domain_factory_service.py package/yuxi/services/template_generator.py package/yuxi/services/template_matcher.py package/yuxi/services/template_library.py test/unit/services/test_template_system.py; cd ..
git checkout -- backend/uv.lock
git add -A backend/templates backend/package/yuxi/services backend/test/unit/services/test_template_system.py docs/develop-guides/upstream-sync-guide.md
git commit -m "fix: bug-359 前置——domain 词形统一到 coal，删 replace 映射链与硬编码

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

Expected: 提交成功，`git status` 中无禁碰文件。

---

### Task 2: 学习模板 match_rule 注入（TDD）

**Files:**
- Test: `backend/test/unit/services/test_template_system.py`（文件尾部新增 5 测试）
- Modify: `backend/package/yuxi/services/template_library.py`（顶部 import + 注入逻辑）

matcher 本身零改动：`match_rule` 无 `strategy` 键 → `_try_match_template` 跳过 regex 块 → 走既有 fallback 分支（子串命中、置信度 0.6、不过阈值闸）。

- [ ] **Step 1: 写失败测试（test_template_system.py 尾部追加）**

```python
# ------------------------------------------------------------------
# bug-359: 学习模板 match_rule 注入与匹配
# ------------------------------------------------------------------


def _learned_row(overrides: dict | None = None) -> dict:
    """构造一条与 repo.list_learned_templates 返回形态一致的学习模板行"""
    row = {
        "id": 42,
        "chapter": "6.3.1.1 建设期水环境影响分析",
        "generalized": "受采动影响，{{数值}} 范围内…",
        "domain_code": "coal",
        "source_count": 3,
        "slots": [],
        "extra_meta": {},
    }
    if overrides:
        row.update(overrides)
    return row


def test_add_templates_from_list_generates_fallback_keywords(tmp_path):
    lib = TemplateLibrary(tmp_path / "none")
    lib.add_templates_from_list([_learned_row()])
    tpl = lib.templates["learned_42"]
    assert tpl["match_rule"]["fallback_keywords"] == ["建设期水环境影响分析"]


def test_add_templates_from_list_strips_numbering_variants(tmp_path):
    lib = TemplateLibrary(tmp_path / "none")
    lib.add_templates_from_list([
        _learned_row({"id": 1, "chapter": "1.2.2 法律、法规"}),
        _learned_row({"id": 2, "chapter": "5地表沉陷对建构筑物和水体影响预测评价"}),
    ])
    assert lib.templates["learned_1"]["match_rule"]["fallback_keywords"] == ["法律、法规"]
    assert lib.templates["learned_2"]["match_rule"]["fallback_keywords"] == [
        "地表沉陷对建构筑物和水体影响预测评价"
    ]


def test_add_templates_from_list_skips_empty_stripped_chapter(tmp_path):
    lib = TemplateLibrary(tmp_path / "none")
    lib.add_templates_from_list([
        _learned_row({"id": 3, "chapter": "1"}),
        _learned_row({"id": 4, "chapter": ""}),
    ])
    assert "match_rule" not in lib.templates["learned_3"]
    assert "match_rule" not in lib.templates["learned_4"]


def test_learned_template_matches_numbered_title(tmp_path):
    lib = TemplateLibrary(tmp_path / "none")
    lib.add_templates_from_list([_learned_row()])
    matcher = TemplateMatcher(lib.get_all_templates())
    result = matcher.match("5.1 建设期水环境影响分析", context={"domain": "coal"})
    assert result.matched
    assert result.template_id == "learned_42"


def test_learned_template_rejects_domain_mismatch_and_other_title(tmp_path):
    lib = TemplateLibrary(tmp_path / "none")
    lib.add_templates_from_list([_learned_row()])
    matcher = TemplateMatcher(lib.get_all_templates())
    assert not matcher.match("5.1 建设期水环境影响分析", context={"domain": "chem"}).matched
    assert not matcher.match("5.1 施工期噪声影响分析", context={"domain": "coal"}).matched
```

- [ ] **Step 2: 红字验证**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_template_system.py -q --no-header 2>&1 | tail -5
```

Expected: **3 failed / 2 passed**——失败的是 1/2/4（match_rule KeyError、matched False）；测试 3/5 是守卫型断言（无 match_rule 时反向断言空转通过），红字阶段通过属预期，绿字阶段才有判别力。其他失败形态（如 import error）说明环境问题，先停。

- [ ] **Step 3: 最小实现（template_library.py）**

顶部 import 块加 `import re`（排在 `import json` 后，isort 序）：

```python
import json
import re
from pathlib import Path
from typing import Any
```

`add_templates_from_list` 循环体、`converted` 字典之后追加（`self.templates[...]` 赋值之前）：

```python
            # bug-359: 按 chapter 生成 fallback 关键词（去编号全串），
            # 命中语义 = 新文档标题精确再现语料标题（容忍编号差异）
            chapter = tpl.get("chapter", "") or ""
            stripped = re.sub(r"^[\d.、\s]+", "", chapter).strip()
            if stripped:
                converted["match_rule"] = {"fallback_keywords": [stripped]}
```

- [ ] **Step 4: 绿字验证 + 全量回归**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_template_system.py -q --no-header 2>&1 | tail -3
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit -q --no-header 2>&1 | tail -3
```

Expected: 文件级全绿；unit 全量 `≥2681 passed, 0 failed, 61 skipped`（bug-360 口径，勿用 `/app/test`）。

- [ ] **Step 5: ruff + 提交**

```bash
cd backend && uv run ruff format package/yuxi/services/template_library.py test/unit/services/test_template_system.py && uv run ruff check package/yuxi/services/template_library.py test/unit/services/test_template_system.py; cd ..
git checkout -- backend/uv.lock
git add backend/package/yuxi/services/template_library.py backend/test/unit/services/test_template_system.py
git commit -m "fix: bug-359 学习模板注入生成 fallback match_rule（标题精确再现语义）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 冒烟复验 + 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`、`.wolf/buglog.json`、`.wolf/anatomy.md`、`.wolf/memory.md`（均无代码）

- [ ] **Step 1: 自匹配冒烟（W0 方法论，bug-359 失败判定翻转）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -c "
import asyncio
from pisuan.repositories.domain_factory_repository import DomainFactoryRepository
from pisuan.services.template_library import TemplateLibrary
from pisuan.services.template_matcher import TemplateMatcher

async def main():
    learned = await DomainFactoryRepository().list_learned_templates(domain_code='coal', limit=200)
    lib = TemplateLibrary()
    lib.add_templates_from_list(learned)
    matcher = TemplateMatcher(lib.get_all_templates())
    hits = sum(1 for t in learned if matcher.match(t['chapter'], context={'domain': 'coal'}).matched)
    print(f'templates total={len(matcher.templates)} (static+learned), learned={len(learned)}, self-match hits={hits}')
    assert hits > 0, '学习模板自匹配 0 命中 — bug-359 未修复'

asyncio.run(main())
"
```

Expected: `learned=200`（limit 封顶，全表 211），`hits > 0`（W0 冒烟为 0/5，判定翻转成立）。`templates total` 在容器栈 = 学习注入数——**静态模板在本栈从不加载**：`/app/templates` 在镜像层与 compose 挂载中均不存在（bug-363，既有部署缺陷，W1 后续候选），"静态共存"由 unit 套件承担验证。冒烟前确保已跑过一次 sync-dev（Task 2 Step 4 之后无代码改动则免）。

追加热核（质量评审 Minor 3，确认 DB 无遗留 coal_mining 词形）：

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -c "
import asyncio
from sqlalchemy import select
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import DomainFactoryDomain, DomainFactoryLearnedTemplate

async def main():
    async with pg_manager.get_async_session_context() as s:
        d = set((await s.execute(select(DomainFactoryDomain.code))).scalars().all())
        l = set((await s.execute(select(DomainFactoryLearnedTemplate.domain_code))).scalars().all())
        print(f'domains={d} learned_domain_codes={l}')
        assert 'coal_mining' not in d | l, '发现遗留 coal_mining 词形'

asyncio.run(main())
"
```

Expected: 两个集合均无 `coal_mining`（domains 应含 `coal`，可能含 chem 等）。

- [ ] **Step 2: changelog**

`docs/develop-guides/changelog.md` 的 `### pisuan 定制增量（2026-10-05）` 小节追加一条：

```markdown
- fix(bug-359): domain 词形全栈统一到 `coal`（删 `_get_template_matcher` replace 映射链、静态模板 30 json + 目录改名）；学习模板注入按 `chapter` 生成 fallback match_rule（标题精确再现语义），match_count 数据通路打通
```

- [ ] **Step 3: buglog（bug-359 修复回填）**

`.wolf/buglog.json` 的 bugs 数组追加（`last_seen` 用当天日期）：

```json
{
  "id": "bug-359",
  "timestamp": "2026-10-05",
  "error_message": "E2E 冒烟：学习模板自匹配 0 命中，match_count 恒 0（自增链接在不通电的线上）",
  "file": "backend/package/yuxi/services/template_library.py + domain_factory_service.py",
  "root_cause": "双缺陷：①词形分裂——DB 学习模板 domain='coal' vs matcher 硬编码 context 'coal_mining' 被领域过滤层全部跳过；②add_templates_from_list 不生成 match_rule，恒 matched=False",
  "fix": "词形统一到 coal（删 replace 映射链 + 静态 30 json + 目录改名 + ETL 块改传任务域）；注入时按 chapter 去编号全串生成 fallback_keywords，走 matcher 既有 fallback 路径",
  "tags": ["domain-factory", "template-matcher", "learned-templates", "match_count", "w1"],
  "related_bugs": ["bug-353", "bug-358"],
  "occurrences": 1,
  "last_seen": "2026-10-05"
}
```

（若 bug-359 已在 W0 期间登记过 entry，则原位更新 root_cause/fix，勿重复建条。冒烟执行中发现的脚本缺陷与部署缺陷另立新条：bug-362 冒烟脚本 pg_manager 导入路径、bug-363 容器栈 /app/templates 缺失静态模板从不加载。）

- [ ] **Step 4: anatomy + memory**

`.wolf/anatomy.md`：`## backend/templates/coal_mining/` 相关节标题与描述中的路径改为 `coal/`，并补一行说明"词形已统一到 coal（bug-359）"。`.wolf/memory.md` 追加一行任务记录。

- [ ] **Step 5: 终检 + 提交**

```bash
git status --short   # 确认只有预期文件，禁碰文件不在列
git add docs/develop-guides/changelog.md .wolf/buglog.json .wolf/anatomy.md .wolf/memory.md
git commit -m "docs: bug-359 收尾——changelog 与 buglog 回填

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成定义（DoD）

1. Task 1/2/3 全部 checkbox 勾完，三次提交落在 pisuan-custom 分支顶端。
2. 容器回归：unit/services 1023 passed / 0 failed；unit 全量 ≥2681 passed / 0 failed（bug-360 口径，见全局上下文）。
3. 冒烟 `hits > 0` 输出留档（贴入任务报告）。
4. `grep -rn "coal_mining" backend/package backend/test backend/templates backend/scripts` 0 命中（web/docs/vibe 历史层不要求）。
