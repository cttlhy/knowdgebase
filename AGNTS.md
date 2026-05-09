# AGENTS.md

## 项目概述

本项目是一个 AI 知识库助手。系统自动从 GitHub Trending 和 Hacker News 采集 AI、LLM、Agent 领域的技术动态，交给 AI Agent 分析价值、提炼摘要、打标签，并以结构化 JSON 存入知识库，最后支持分发到 Telegram 和飞书等渠道。

## 技术栈

- Python 3.12
- OpenCode + 国产大模型
- LangGraph
- OpenClaw

## 编码规范

本项目遵循简洁、可读、可测试的编码原则。

- Python 使用 PEP 8。
- Python 命名使用 `snake_case`。
- 公开模块、类和函数使用 Google 风格 docstring。
- 禁止裸 `print()`，请使用 `logging`。
- 保持代码简单、清晰、模块化。
- 写代码或 review 代码时，必须参考 `specs/coding-standards.md`。

## 项目结构

```text
.opencode/
  agents/        # Agent 角色定义。每个 Agent 只负责一个清晰任务。
  skills/        # 可复用技能。用于采集、分析、整理和分发等步骤。

knowledge/
  raw/           # 原始采集数据。保留来源字段，便于回溯和重跑。
  articles/      # 分析后的知识条目。使用结构化 JSON 保存。
```

## 知识条目 JSON 格式

所有进入 `knowledge/articles/` 的知识条目必须使用稳定 JSON 结构。字段要清晰，方便搜索、分发和后续 RAG 使用。

```json
{
  "id": "github-trending-2026-04-29-owner-repo",
  "title": "项目或文章标题",
  "source": "github_trending",
  "source_url": "https://github.com/owner/repo",
  "collected_at": "2026-04-29T09:00:00+08:00",
  "summary": "用简短文字说明这个条目是什么，以及为什么值得关注。",
  "tags": ["llm", "agent", "open-source"],
  "status": "draft",
  "language": "Python",
  "score": 0.82,
  "reason": "说明入库原因。要写清楚技术价值、应用场景或趋势信号。",
  "distribution": {
    "telegram": false,
    "feishu": false
  },
  "metadata": {
    "stars": 1200,
    "comments": 18,
    "author": "owner"
  }
}
```

字段约定：

- `id`：全局唯一。建议由来源、日期和来源标识组合生成。
- `title`：原始标题或整理后的可读标题。
- `source`：信息源。可选值示例：`github_trending`、`hacker_news`。
- `source_url`：原始链接。必须保留。
- `collected_at`：采集时间。使用 ISO 8601 格式。
- `summary`：AI 生成摘要。应简洁、准确、可读。
- `tags`：标签列表。使用小写英文短词。
- `status`：处理状态。建议使用 `raw`、`analyzed`、`draft`、`published`、`archived`。
- `score`：价值评分。范围为 `0.0` 到 `1.0`。
- `reason`：入库理由。说明为什么值得保存或分发。
- `distribution`：分发状态。用于记录 Telegram 和飞书是否已发送。
- `metadata`：来源相关补充信息。不同来源可以有不同字段。

## Agent 角色概览

| 角色 | 主要职责 | 输入 | 输出 |
| --- | --- | --- | --- |
| 采集 Agent | 从 GitHub Trending 和 Hacker News 获取候选内容，并做基础去重和过滤。 | 信息源配置、采集时间窗口 | `knowledge/raw/` 下的原始 JSON |
| 分析 Agent | 判断内容是否属于 AI、LLM、Agent 领域，并生成摘要、标签、评分和入库理由。 | 原始 JSON | 带分析字段的结构化 JSON |
| 整理 Agent | 规范知识条目格式，补齐必要字段，并准备 Telegram、飞书分发内容。 | 分析后的 JSON | `knowledge/articles/` 下的最终 JSON |

## 红线

- 绝对禁止提交或硬编码 API Key、Token、Cookie、私钥和账号密码。
- 绝对禁止伪造来源、伪造评分、伪造采集时间或伪造引用链接。
- 绝对禁止在未保留 `source_url` 的情况下生成知识条目。
- 绝对禁止覆盖 `knowledge/raw/` 中的原始数据。需要修正时应生成新文件或新版本。
- 绝对禁止让 Agent 自动发布未经分析和整理的原始内容。
- 绝对禁止使用裸 `print()` 输出运行信息。
- 绝对禁止吞掉异常。必须记录错误原因、失败步骤和可重试信息。
- 绝对禁止引入复杂架构来解决简单问题。先保证最小可用闭环稳定运行。
