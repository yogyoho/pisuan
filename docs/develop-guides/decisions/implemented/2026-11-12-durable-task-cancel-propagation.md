# Durable Task 取消即时传播

状态：implemented
类型：bug-fix
Owner：backend/package/pisuan/services/task_service.py

## 问题

任务中心取消只向 PostgreSQL 写入 `cancel_requested`，worker 的 `process_task` 仅在 10 秒一次的心跳中读取该标记。知识工厂段落泛化 `generalize_paragraphs()` 不接收 `TaskContext`，一个批次内可以持续发起大量 LLM 调用；取消后请求继续到达本地 LLM，最终只能停止 worker 进程。

任务中心读取知识工厂状态时，用领域行状态无条件覆盖 durable 状态。领域行在 worker 中断后可能滞留 `GENERALIZING`，导致已取消任务继续显示为进行中；`cancel_requested` 也没有独立提示。

## 决策

### 实现方案

- `Tasker.cancel_task()` 在 PostgreSQL `request_cancel` 事务提交后，向 Redis 写 `task:cancel:{task_id}` 短期信号，TTL 1800 秒；Redis 失败只记录 WARNING，不改变 PG 取消结果。
- `process_task()` 在每次 attempt 启动独立 `cancel_watcher`，以 0.5 秒间隔读取该 key；命中后设置 `TaskContext.cancellation_reason=cancelled` 并取消 handler Task。PG 心跳继续保留，Redis 故障或信号丢失时由 10 秒心跳兜底。
- attempt 结束的 `finally` 取消 watcher 并删除 Redis key；终态仍由 PostgreSQL `finish_owned` / `release_interrupted_owner` 事务拥有。
- `DomainFactoryService._etl_pipeline_async()` 把 `TaskContext` 传入 `generalize_paragraphs()`；后者在段落入口和拿到 semaphore 后各检查一次取消，取消后不再发起新 LLM 调用，已发出的调用随 handler Task 一起取消。
- 任务中心 `/api/domain-factory/tasks-center` 不再用领域行覆盖 durable `cancelled` / `failed` 终态；durable 仍活跃但 `cancel_requested` 时显示“取消中，等待 worker 停止”；只有活跃 durable 任务才用领域行映射 ETL 进度。

## 替代方案

- 缩短心跳周期：仍受固定轮询延迟，且增加 PostgreSQL 写放大；无法让取消与 LLM 调用边界同步。
- 只依赖 ARQ abort job：ARQ 对已开始执行的协程没有可靠的 per-task 中断语义，且跨进程不能定位当前 handler。
- 取消意图只放 Redis：Redis 丢数据时取消不可审计，违反 PostgreSQL 拥有业务终态。
- 任务中心继续信任领域行：领域行是 ETL 阶段投影，worker 崩溃后会滞留执行态，不能证明任务仍在运行。
- 泛化层只检查一次取消：并发 semaphore 排队期间可能已取消，仍会发起一批新 LLM 调用。

## 后果

取消从“最多等一个心跳周期”变为亚秒级可见（Redis 正常时），Redis 故障时仍退化为心跳兜底。取消是协作式的：已经进入模型的单次请求无法撤回，但不会再发起后续请求；worker 进程仍需等 handler 退出后才释放 durable 槽位。API 与 worker 必须一起升级，旧 worker 不认识新 key，旧 API 也不会发布信号。

## 验证

- `test_cancel_watcher_interrupts_blocked_handler_and_marks_cancelled`：watcher 收到信号后阻塞 handler 立即退出，durable 终态为 `cancelled`；移除 watcher 时该用例超时或终态不符。
- `test_redis_cancel_signal_interrupts_running_durable_task`（真实 PostgreSQL + Redis）：取消请求提交后阻塞 handler 在 2 秒内退出，持久化状态为 `cancelled`；移除 Redis watcher 时只能等下一次心跳。
- `test_cancel_task_publishes_signal_after_postgres_cancel`：断言发布信号时 PG 已写入 `cancel_requested`。
- `test_task_cancel_wait_returns_on_redis_signal` / `test_task_cancel_publication_failure_keeps_redis_best_effort`：Redis 正常读取与故障 best-effort。
- `test_generalize_paragraphs_checks_cancellation_after_semaphore`：拿到并发槽位后检查取消，移除该检查会发起 LLM。
- `test_generalize_paragraphs_stops_before_next_llm_after_cancel`：首段返回后取消，后续段落不再调用 LLM。
- `test_durable_cancelled_not_overridden_by_domain_status` / `test_cancel_requested_keeps_durable_progress_and_marks_stopping` / `test_active_durable_task_uses_domain_progress`：任务中心状态优先级。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_tasker_behavior.py test/unit/services/test_domain_factory_p0.py test/unit/routers/test_domain_factory_task_center.py -q`：38 passed。
- `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_durable_task_repository.py::test_redis_cancel_signal_interrupts_running_durable_task -q`：1 passed。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m "not slow" -q`：3304 passed，9 failed，65 skipped。9 个失败均在本次未触及的 `test_ragflow_like_chunking`、`test_eia_lexicon_*`、`test_entity_meta_service`、`test_graph_builder_identity_aggregation`、`test_graph_query_service`，与取消链路无关。
- `python -m ruff check` 对本次新增/修改的 `task_queue_service.py`、`task_service.py`、`domain_factory_router.py` 与四个测试文件通过；`domain_factory_service.py` 仅报告该文件既有的 F841/E501/E741，未落在本次新增行。
- `git diff --check` 对本次文件通过。
