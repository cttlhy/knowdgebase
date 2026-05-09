# AI 知识库 · 项目愿景 v1.0

## 目标

构建一个长期可积累的 AI 知识库。

系统每天从 GitHub Trending 抓取热门项目，筛选出 AI 相关项目，再用 Agent 做结构化分析。最终沉淀为可检索、可复用的 JSON 知识条目，并生成一份给个人阅读的 Markdown 日报。

核心目标不是做新闻摘要。核心目标是持续积累高质量 AI 开源项目信息，帮助后续复盘、检索和判断技术趋势。

## 要做什么

- 每天抓取 GitHub Trending Top 20。
- 用关键词和 Agent 语义判断筛选 AI 相关项目。
- 对筛选后的项目生成结构化分析。
- 输出 JSON 知识条目，作为知识库主资产。
- 输出 Markdown 日报，作为个人阅读入口。
- 记录被跳过的项目和跳过原因。
- 支持手动运行。
- 支持每天早上 8 点自动运行。

## AI 相关判定

先用关键词做初筛，再用 Agent 做语义判断。

关键词包括但不限于：

- LLM
- Agent
- RAG
- model
- diffusion
- embedding
- inference
- MCP

Agent 需要判断项目是否真的和 AI 开发、模型、应用或基础设施相关。只出现关键词但实际无关的项目，应跳过并记录原因。

## Agent 分析内容

每个入库项目至少包含以下分析：

- 项目摘要。
- 核心能力。
- 适用人群。
- 技术标签。
- 与已有项目或常见方案的差异点。
- 价值评分。
- 是否值得持续跟踪。

价值评分拆成 3 个维度。每项 1 到 5 分：

- 技术新颖性。
- 实用性。
- 持续跟踪价值。

系统还需要给出一个总评：高、中、低。

## 输出格式

JSON 是主格式。Markdown 是副产物。

JSON 用于长期沉淀、检索、去重和后续加工。Markdown 用于当天快速阅读。

## JSON 知识条目字段

每个知识条目包含：

- `repo`
- `url`
- `stars`
- `language`
- `summary`
- `core_capabilities`
- `target_users`
- `tags`
- `differentiation`
- `scores`
- `track_decision`
- `created_at`

`scores` 包含：

- `technical_novelty`
- `practicality`
- `tracking_value`
- `overall`

## 文件输出位置

每天生成以下文件：

- `data/entries/YYYY-MM-DD.json`
- `data/reports/YYYY-MM-DD.md`
- `data/skipped/YYYY-MM-DD.json`

跳过项只记录最小信息：

- `repo`
- `reason`

## 重复运行规则

同一天任务重复运行时，默认跳过已存在产物。

只有显式传入 `--force` 时，才允许覆盖当天文件。

这样可以避免调试时误删已有结果。

## 失败处理

关键步骤失败时，整批任务失败。

关键步骤包括：

- GitHub Trending 抓取失败。
- 无法创建当天输出目录。
- 无法写入最终产物。

单个项目分析失败时，不影响整批任务。系统应跳过该项目，并记录失败原因。

网络请求失败时，最多重试 2 次。

## 不做什么

初版明确不做：

- 不做 Web UI。
- 不做登录、多用户、权限。
- 不做向量搜索。
- 不做自动发布到公众号、博客或 X。
- 不抓取 GitHub 以外的数据源。
- 不做实时监控，只做每日批处理。
- 不自动 clone 仓库或运行项目代码。
- 不做复杂去重，只按 repo URL 去重。

## 边界 & 验收

一次每日任务完成后，必须满足流程、产物和质量 3 类验收。

流程验收：

- 能抓取 GitHub Trending Top 20。
- 能筛选 AI 相关项目。
- 能调用 Agent 生成分析。
- 能写入 JSON、Markdown 和跳过项文件。
- 失败时有明确错误信息。

产物验收：

- 生成 `data/entries/YYYY-MM-DD.json`。
- 生成 `data/reports/YYYY-MM-DD.md`。
- 生成 `data/skipped/YYYY-MM-DD.json`。
- JSON 条目字段完整。
- Markdown 日报可直接阅读。

质量验收：

- 人工抽查时，至少 80% 的入库项目确实和 AI 相关。
- 每个入库项目都有摘要、标签、评分和跟踪结论。
- 被跳过项目都有 repo 和原因。

## 怎么验证

用自动测试和真实数据共同验证。

自动测试：

- 使用 mock GitHub Trending 数据。
- 验证抓取、过滤、分析、写文件流程。
- 验证重复运行时默认不覆盖文件。
- 验证 `--force` 可以覆盖当天文件。
- 验证单个项目失败不会中断整批任务。

真实数据验证：

- 使用当天 GitHub Trending 跑通一次完整流程。
- 人工检查 JSON 字段是否完整。
- 人工检查 Markdown 日报是否可读。
- 人工抽查入库项目是否 AI 相关。
- 人工检查跳过项原因是否清楚。