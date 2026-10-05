# bug-365 修复设计：存量任务 storage_path 一次性迁移

> 状态：已拍板（2026-10-05，用户裁决 D1/D2/D3 均按推荐）
> 前序：bug-363 Task 2/3 清查立案（W1 第三项）

## 1. 背景与事实底座（全部实测）

存储根从 `saves/`（旧 config.save_dir）迁移到 `YUXI_USER_DATA_DIR`（`/app/user-data`）后，存量任务行的 `storage_path` 未做数据迁移。ETL 解析入口 `_etl_parse_stage`（domain_factory_service.py:553）在 :566 直接透传 DB 值给 parse_document，伊宁重试时立即 `PackageNotFoundError`。

- **受影响面**：全库唯一 1 行——`domain_factory_tasks` f7b40b18（COMMITTED，伊宁 354 段完整，committed_at 2026-08-20）；其余 6 张候选路径表（knowledge_files/skills/projects/evaluation_benchmarks 等）零命中。
- **病灶值**：`saves/domain_factory/coal/c5451b85-...docx`；文件实体在 `/app/user-data/domain_factory/coal/`（13.9MB 在位，两容器可见）。
- **现行惯例**：2026-10 起 7 条新行全为绝对路径 `/app/user-data/...`。
- **上游 sanctioned 方向**：`config/__init__.py:18 get_legacy_storage_dir` 自述「仅供一次性迁移使用」——一次性数据迁移而非运行时回退。

## 2. 拍板决策（2026-10-05）

- **D1 修法 = 数据迁移**：1 行 UPDATE，`saves/` 前缀 → `/app/user-data/`，与现行惯例对齐。零代码改动。拒绝解析入口代码回退（违反「反防御性回退」原则；现行写入已正确，回退是教代码原谅死数据）。
- **D2 验证 = 轻验证**：UPDATE 后容器内 `Path.exists()` + python-docx open 冒烟（秒级）。不跑完整 ETL（40min OCR + 云 API 限流风险；横城 a44afc93 尚待续跑，不宜并发撞 quota；伊宁数据完整无重跑需求）。
- **D3 清淤备份去留 = 删除**：`.wolf/bug363-stale-coal_mining-backup/` 在迁移落地后删除（镜像 tip `github/pisuan-localized` git 对象仍可恢复，双保险之一即可）。

## 3. 方案

| # | 落点 | 改动 |
|---|------|------|
| 1 | `pisuan-localized-postgres-1`（运行栈 DB） | `UPDATE domain_factory_tasks SET storage_path = '/app/user-data/' || substring(storage_path from 7) WHERE id LIKE 'f7b40b18%' AND storage_path LIKE 'saves/%'`（双守卫：id + 前缀，防误伤） |
| 2 | 容器轻冒烟 | python-docx 打开迁移后路径（纯文件操作，不初始化 pg_manager，无池挂风险） |
| 3 | 附带核查 | `docker ps` 确认是否存在第二套 postgres 栈；有则同修或如实记录 |
| 4 | 台账 | buglog-365 fix 原位更新（实际动作 + 验证结果）；changelog 一行；备份目录删除 |

## 4. 验收标准

1. UPDATE 恰好命中 1 行（前后 SELECT 留痕）；迁移后路径容器内存在且 python-docx 可开（读出段落数 >0）。
2. 零代码 diff（本项不含任何 .py/.yml 改动）；台账三件（buglog/changelog/计划执行记录）落档。
3. 备份目录删除后 `git status` 无新增未跟踪残留。

## 5. Out of scope

ETL 重跑（伊宁/横城均不做）、其他表回填（零命中无需）、解析入口改造、`git clean` 防护机制。
