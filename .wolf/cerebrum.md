# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-16

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Communication in Chinese for project discussion, English for code comments
- Large changes should have a requirements document in `docs/vibe/` with date prefix

## Key Learnings

- **ETL Pipeline stages:** PARSE → CLASSIFY → GENERALIZE → WAITING_REVIEW → COMMIT
- **Frontend tab alignment:** ETL workbench 4 tabs map to pipeline: parse → generalize → entities → commit
- **Data flow:** All frontend edits go through `source_paragraphs[].template`, never `form_schema`
- **Save endpoint:** `saveTaskStep(id, {step: 'structured', payload: {source_paragraphs, structured_blocks}})`
- **Commit endpoint:** `commitTask(id, {form, structured, source_paragraphs, knowledge_base_id})`
- **Ant Design Vue** is the UI framework for this project (a-card, a-tabs, a-tree, a-table, etc.)
- **Docker-based dev:** `docker exec web-dev` for pnpm commands, `docker logs web-dev` for compilation
- **Vite HMR:** edits auto-reload, check logs for compilation errors after changes
- **远程仓库布局：** `origin` = yogyoho/pisuan ≈ 上游 xerrors/Yuxi 的镜像；本地 `upstream/main` ref 可能过时，`git fetch upstream` 后 `origin/main` 与 `upstream/main` 通常同一 commit。同步走 `scripts/sync-upstream.ps1`（ff main → rebase pisuan-custom）。
- **deepagents 钉死 `<0.6.8`：** 0.6.10 移除了 `SubagentTransformer`，而 `yuxi/agents/middlewares/subagent_task.py` 仍 `from deepagents import SubagentTransformer`。上游已升 0.6.12（其代码已适配），pisuan 未适配 → 该约束必须保留；合并后必须 `uv lock` 让锁一致。
- **DB 迁移机制：** 无 Alembic，靠 `manager.py` 的 DDL 列表（`CREATE/ALTER ... IF NOT EXISTS`）每次启动跑。`create_all()` 只建不存在的表，不会给已存在的旧表补列/补默认值。

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-05-16] After full file rewrite, always run `pnpm run lint` before declaring done. Dead code accumulates quickly (unused imports, refs, functions). Catch blocks with unused `e` should use bare `catch {}`.
- [2026-05-17] When adding new template branches that call helper functions, ALWAYS define the function in the script section. An undefined function in a v-if/v-else-if chain causes a silent render failure for the entire branch — no error shown in UI, just blank content. This was the cause of "table paragraph click does nothing" bug (bug-108).
- [2026-05-16] Vue SFC must end with `</style>` not `</template>`. Stray closing tags cause `x-invalid-end-tag` parsing error.
- [2026-07-10] 上游大同步后，pisuan 的旧开发库可能缺合并后模型要求的列/默认值（如 `agent_runs.run_type`、`skills.is_builtin` 默认值），`create_all()` 不会补。同步后若 worker/api 崩在 `UndefinedColumn` / `NotNullViolation`，先 `docker exec postgres psql ... \d <table>` 比对模型，在 `manager.py` 补 `ALTER ... ADD COLUMN IF NOT EXISTS` 或 `ALTER COLUMN ... SET DEFAULT`。
- [2026-07-10] 合并中途 `uv.lock` 里残留冲突标记会让 worker/api 启动崩在 `Failed to parse uv.lock`（TOML 解析）。合并产生锁文件冲突时，先 `git checkout --theirs` 清标记再 `uv lock` 重生成，别让容器带着冲突标记重启。

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-05-16] ETL workbench tabs redesigned from 5 → 4 to align with pipeline stages (parse/generalize/entities/commit). Removed deprecated form_schema dependency. All edits now flow through source_paragraphs.
- [2026-07-10] 98 提交的大追赶同步用 **merge** 而非项目既定的 rebase：rebase 会把 16 个定制提交逐个重放、在 21 个冲突文件上反复解同一文件；merge 一次性摊开所有冲突（判定内容相同但工作量小得多）。合并提交完成后，以后小步同步仍回 rebase 流程。
