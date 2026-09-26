# 煤矿环评报告 13 章静态大纲

> 本目录包含煤矿建设项目环境影响评价报告的标准 13 章静态知识骨架。
> 依据 HJ/T 130-2019《建设项目环境影响报告表（书）编制技术导则》及横城矿区环评报告结构整理。

## 文件列表

| 文件 | 章节 | 负责 writer |
|------|------|-------------|
| ch01-总论.md | 第1章 总论 | regulation-writer |
| ch02-规划概况.md | 第2章 规划概况 | data-survey-writer |
| ch03-环境现状.md | 第3章 环境现状调查与评价 | data-survey-writer |
| ch04-回顾评价.md | 第4章 回顾性评价 | data-survey-writer |
| ch05-影响识别.md | 第5章 环境影响识别与评价因子筛选 | prediction-writer |
| ch06-影响预测.md | 第6章 环境影响预测与评价 | prediction-writer |
| ch07-承载力.md | 第7章 环境承载力分析 | prediction-writer |
| ch08-综合论证.md | 第8章 规划方案综合论证 | prediction-writer |
| ch09-减缓措施.md | 第9章 环境保护措施及可行性论证 | prediction-writer |
| ch10-环境管理.md | 第10章 环境管理与监测计划 | regulation-writer |
| ch11-清洁生产.md | 第11章 清洁生产与循环经济 | regulation-writer |
| ch12-公众参与.md | 第12章 公众参与 | regulation-writer |
| ch13-结论.md | 第13章 环境影响评价结论 | prediction-writer |

## 静态 vs 动态边界

- **MD 静态知识（本目录）**：13 章标准结构、法规清单、写作骨架、数据需求清单
- **图谱动态细化**：章节模板、段落模式、插槽（由 ETL 从样例报告抽取）

MD 只写到一级章节认知层面，不写细粒度子章节（如"3.1.1 地形地貌该怎么写"由图谱提供）。

## 加载顺序

```
1. 图谱查询（首选）→ ChapterTemplate + ParagraphTemplate + Slot
2. references/report_structure.md（图谱不可用时 fallback）
3. outlines/chXX.md（章节级静态骨架，writer 写作时按需 read_file）
```
