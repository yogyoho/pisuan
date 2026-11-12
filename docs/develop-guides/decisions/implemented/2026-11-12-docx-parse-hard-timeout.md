# DOCX 解析硬超时与结构化兜底

状态：implemented
类型：bug-fix
Owner：backend/package/pisuan/knowledge/parser/unified.py

## 问题

知识工厂 ETL 的 DOCX 解析优先走 Docling。Docling 的 DOCX 后端会处理 VML/DrawingML 图片；遇到 WMF/EMF 时会回退到 LibreOffice 转换。生产日志已经出现 `VML image cannot be found` 与 `cannot find loader for this WMF file`，一次 DOCX 任务实际执行了 536 秒。

原实现有两个工程边界缺口：

- Docling 在 `asyncio.to_thread()` 中执行。取消 handler 只能取消等待协程，不能终止线程或它启动的 `soffice`；坏文档最坏可以占住 worker 到 Durable Task 的 6 小时超时。
- Docling 转换受进程级 `threading.Lock` 串行保护。一个卡住的 DOCX 会让同一 worker 内后续 Office 解析全部排队。

Docling 在表格、公式、图表和阅读顺序上优于裸 `python-docx`，因此不能简单替换；问题在缺少可杀死的执行边界和超时兜底。

## 决策

### 实现方案

- DOCX 仍以 Docling 为主解析器，但改在独立子进程中执行：`_convert_docx_with_timeout()` 通过 `asyncio.create_subprocess_exec()` 启动 `docx_docling_worker.py`，POSIX 下使用 `start_new_session=True` 建立独立进程组。
- 父进程按 `DOCLING_DOCX_TIMEOUT_SECONDS`（默认 900 秒）等待。超时或任务取消时用 `SIGKILL` 杀掉整个进程组，连同 Docling 启动的 `soffice`；等待子进程回收后再继续或抛出取消。
- 子进程把 Markdown 写入临时文件，父进程读取后返回；`stderr` 继承父进程，保留 Docling 的图片格式告警。只向子进程传 `image_bucket`、`image_prefix`，避免把无关参数或凭据带进命令。
- Docling 子进程失败或超时后，回退到 `_convert_docx_with_python_docx()`。兜底把 `Heading N` / `标题 N` 转为 Markdown `#`，并继续输出简单表格；它只用于失败路径，不替换正常 Docling 路径。
- 父进程继续持有现有 Office 转换锁，保持同一 worker 内 Office 解析串行；等待锁时使用非阻塞轮询，任务取消不会遗留已获取的锁。子进程只执行单个转换，不跨进程共享锁。
- 本次不把 DOCX 热路径切到 OCR/VLM。PDF/图片的既有 OCR 入口与 `figure` 段落的 VLM 提取保持不变，避免把本地模型资源竞争重新引入 ETL 主链路。

## 替代方案

- 只依赖 Durable Task 的 6 小时超时：worker 会被一个坏 DOCX 长时间占住，其他任务只能排队。
- 全部改用 `python-docx`：丢失表格合并、公式、图表、浮动对象和阅读顺序，解析质量下降。
- 用 `asyncio.timeout()` 包住 `to_thread()`：只能放弃等待，线程和 `soffice` 仍在后台运行，锁也不会释放。
- 整篇 DOCX 转 PDF 后走 OCR/VLM：对原生 DOCX 增加不必要的延迟和成本，并再次争抢本地模型显存。
- 只做图片格式转换、不加超时：可以改善 WMF/EMF 图片覆盖，但不能解决 LibreOffice 卡住和锁占用。

## 后果

- 正常 DOCX 仍由 Docling 解析；父进程在等待期间不阻塞事件循环，取消任务会终止解析子进程。
- DOCX 子进程启动会额外加载一次 Docling 相关模块，解析期间 worker 峰值内存上升；超时杀进程后内存释放。
- POSIX 下进程组确保 `soffice` 等后代进程一起退出；Windows 仅能杀死直接子进程，能力弱于生产 Linux。
- 硬超时过短会让复杂 DOCX 提前降级到 `python-docx`。默认 900 秒高于已知 536 秒案例，并允许通过环境变量调整。
- 兜底解析的表格、公式、浮动对象和阅读顺序弱于 Docling；标题层级和简单表格得到保留，避免 ETL 章节结构完全丢失。

## 验证

执行命令与结果：

```bash
docker compose exec -T api uv run --no-sync --group test pytest test/unit/knowledge/test_parser_facade.py -q
python -m ruff check package/pisuan/knowledge/parser/unified.py package/pisuan/knowledge/parser/docx_docling_worker.py test/unit/knowledge/test_parser_facade.py
python -m ruff format --check package/pisuan/knowledge/parser/unified.py package/pisuan/knowledge/parser/docx_docling_worker.py test/unit/knowledge/test_parser_facade.py
```

`pytest` 结果：47 passed、1 warning（容器内 pytest cache 目录无写权限，与本次改动无关）。Ruff check 与 format check 均通过。

真实链路：在 api 容器内对 `test/data/测试文档.docx` 调用 `_convert_docx_with_timeout(..., timeout_seconds=180)`，Docling 子进程约 3.2 秒完成，输出 2324 字符，包含 1 个图片链接和表格文本；证明 worker 模块导入、参数传递、临时输出文件和 MinIO 图片上传链路可用。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 | 负向案例 | 结果 |
|---|---|---|---|---|---|
| Docling DOCX 转换超时后子进程被杀死并回退 `python-docx` | 超时后子进程继续运行，worker 仍被占用 | `_convert_docx_with_timeout()` / `_run_process_with_timeout()` | `test_run_process_with_timeout_kills_child`、`test_parse_document_docx_falls_back_after_docling_timeout` | 恢复为直接 `asyncio.to_thread(_convert_with_docling)` 时，超时用例不会杀死子进程 | Passed |
| 任务取消会终止 DOCX 子进程 | 取消只停止协程，Docling 继续占用资源 | `_run_process_with_timeout()` | `test_run_process_with_timeout_kills_child_on_cancel` | 删除取消分支的进程组清理后，PID 仍可被信号探测 | Passed |
| 正常 DOCX 仍优先返回 Docling 结果 | 兜底逻辑替换了正常主路径 | `parse_resolved_document()` | `test_parse_document_docx_uses_docling_subprocess`、`test_slim_office_backends_convert_real_fixtures`、图片链接顺序用例 | 若跳过 Docling 直接走 `python-docx`，图片链接 fixture 用例变红 | Passed |
| Docling 失败/超时时兜底保留标题层级 | 兜底只剩纯文本，ETL 章节解析退化 | `_convert_docx_with_python_docx()` | `test_python_docx_fallback_preserves_heading_levels`、`test_markdown_heading_prefix_maps_word_styles` | 移除标题前缀后 `# 一级标题` 断言失败 | Passed |
| 原生 DOCX 不新增 OCR/VLM 调用 | 解析热路径重新引入模型资源竞争 | `parse_resolved_document()` | `test_parse_document_docx_does_not_call_ocr_models` | 若整篇走 OCR，OCR 入口替身会触发 `pytest.fail` | Passed |

未验证范围：未用生产环境触发 536 秒的原始 DOCX 复跑，也未在真实 worker/队列中验证取消到进程组退出的端到端时序；单测覆盖的是子进程超时、取消和兜底语义。
