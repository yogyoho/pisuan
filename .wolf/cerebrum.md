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

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-05-16] After full file rewrite, always run `pnpm run lint` before declaring done. Dead code accumulates quickly (unused imports, refs, functions). Catch blocks with unused `e` should use bare `catch {}`.
- [2026-05-17] When adding new template branches that call helper functions, ALWAYS define the function in the script section. An undefined function in a v-if/v-else-if chain causes a silent render failure for the entire branch — no error shown in UI, just blank content. This was the cause of "table paragraph click does nothing" bug (bug-108).
- [2026-05-16] Vue SFC must end with `</style>` not `</template>`. Stray closing tags cause `x-invalid-end-tag` parsing error.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-05-16] ETL workbench tabs redesigned from 5 → 4 to align with pipeline stages (parse/generalize/entities/commit). Removed deprecated form_schema dependency. All edits now flow through source_paragraphs.
