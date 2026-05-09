---
name: arxiv-papers
description: 检索并筛选 arXiv 最新论文，提取核心贡献并生成结构化 JSON 报告。Use when user wants 查看、抓取、采集、跟踪、监控、汇总 arXiv 最新论文、最新 paper、每日论文、论文雷达、论文日报、论文周报，或需要 AI、NLP、Agent、LLM、RAG、Retrieval 相关研究清单、去重后的论文 JSON、中文摘要、重点论文速览。
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# arXiv Papers 技能

## 使用场景

用于追踪 arXiv 最新论文。
用于产出论文清单、论文日报、论文 JSON。
重点关注 AI、NLP、Agent、LLM、RAG、Retrieval。

## 执行步骤（7步）

1. **抓最新论文**  
   用 arXiv API 抓取结果。  
   关键词匹配 `Agent`、`LLM`、`Retrieval`。  
   只保留 `cs.AI` 和 `cs.CL`。  
   按发布时间倒序。

2. **提取字段**  
   提取 `id`、`base_id`、`title`、`authors`、`published_at`、`summary_raw`、`url`、`pdf_url`、`categories`。  
   `base_id` 要去掉版本号。  
   例如 `2504.12345v2` 要转成 `2504.12345`。

3. **过滤结果**  
   排除 survey 和 review 类论文。  
   优先保留近 48 小时结果。  
   候选过多时，按标题命中 > 摘要命中排序。

4. **历史去重**  
   用 `Glob` 检查 `knowledge/raw/arxiv-papers-*.json`。  
   按 `base_id` 去重。  
   已存在就跳过。

5. **写中文摘要**  
   为每篇论文生成 `summary`。  
   格式是“核心方法 + 解决的问题或指标 + 工程启示”。  
   没有明确数据时，不写具体提升数字。

6. **排序精选**  
   按关键词匹配权重和时间戳排序。  
   只保留 Top 15。

7. **输出 JSON**  
   输出到 `knowledge/raw/arxiv-papers-YYYY-MM-DD.json`。  
   当天文件已存在时，按 `base_id` 增量合并。
   写入 `knowledge/articles` 时，必须使用统一知识条目 schema。

## 规则

- 只保留 `cs.AI` 和 `cs.CL`。
- 一律按 `base_id` 去重。
- 不编造指标、参数量或实验结论。
- `url` 和 `pdf_url` 必须是纯字符串。
- 多次运行时只做增量合并，不直接覆盖。
- `knowledge/articles` 顶层只放通用字段。
- arXiv 特有字段放入 `metadata`。

## 输出格式

采集结果输出为 JSON。结构如下：

```json
{
  "source": "arxiv",
  "skill": "arxiv-papers",
  "collected_at": "YYYY-MM-DDTHH:mm:ssZ",
  "items": [
    {
      "id": "2504.12345v2",
      "base_id": "2504.12345",
      "title": "Scaling Laws for Agentic Workflows",
      "url": "https://arxiv.org/abs/2504.12345",
      "pdf_url": "https://arxiv.org/pdf/2504.12345.pdf",
      "summary": "提出 Agent 工作流扩容规律，分析任务长度与协作规模的关系，并为多 Agent 系统的容量设计提供参考。"
    }
  ]
}
```

写入 `knowledge/articles` 时使用统一知识条目 schema：

```json
{
  "id": "arxiv-YYYYMMDD-001",
  "title": "Scaling Laws for Agentic Workflows",
  "source": "arxiv",
  "source_url": "https://arxiv.org/abs/2504.12345",
  "summary": "中文摘要，至少 20 字",
  "tags": ["llm", "agent", "research"],
  "status": "published",
  "score": 8,
  "audience": "advanced",
  "metadata": {
    "base_id": "2504.12345",
    "paper_id": "2504.12345v2",
    "pdf_url": "https://arxiv.org/pdf/2504.12345.pdf",
    "published_at": "YYYY-MM-DD",
    "categories": ["cs.AI", "cs.CL"]
  }
}
```