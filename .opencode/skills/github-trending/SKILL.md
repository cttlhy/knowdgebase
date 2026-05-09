---
name: github-trending
description: 抓取 GitHub Trending Top 50 并过滤 AI 相关项目，输出结构化 JSON。Use when user wants 采集/抓取 GitHub 热门/趋势/流行项目，看看 GitHub 今天/本周/本月什么火，或需要 AI/LLM/Agent 开源项目列表、报告或 JSON.
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 技能

## 使用场景

用于抓取 GitHub Trending 榜单并筛出 AI 相关项目。

## 执行步骤（7步）

1. **确定时间窗**  
   默认用 `weekly`。  
   用户说今天/本周/本月时，改为 `daily` / `weekly` / `monthly`。

2. **抓 Trending Top 50**  
   主来源用 GitHub Trending 页面。  
   只抓前 50 个仓库。  
   页面失败时，再用 Search API 兜底。

3. **提取字段**  
   提取 `owner/repo`、URL、描述、Star、语言、Topics。

4. **过滤 AI 相关**  
   用名称、描述、Topics 命中 `ai`、`llm`、`agent`、`ml`、`rag`、`copilot` 等关键词。

5. **排除弱相关结果**  
   排除 `awesome-*`、`papers`、`resources`、`tutorial`、`list` 等列表或资料型仓库。

6. **去重并写摘要**  
   按 `owner/repo` 去重。  
   用中文写一句摘要。  
   格式是“做什么 + 为什么值得关注”。

7. **输出 JSON**  
   默认直接输出 JSON。  
   仅在调用方明确要求时写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`。
   写入 `knowledge/articles` 时，必须使用统一知识条目 schema。

## 规则

- 返回全部命中项。不要默认裁成 Top 15。  
- 不爬非 GitHub 平台。  
- 不读 README 做深度判定。  
- 摘要必须是中文短句。  
- 结果必须可去重、可复现、可解释。
- `knowledge/articles` 顶层只放通用字段。
- GitHub 特有字段放入 `metadata`。

## 失败处理

- 始终返回合法 JSON。  
- `status` 只用 `ok`、`no_matches`、`fetch_failed`。  
- 失败时保留 `items: []`。  
- 失败时写明 `error`。  

## 输出格式

采集结果输出为 JSON。结构如下：

```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "YYYY-MM-DDTHH:mm:ssZ",
  "status": "ok | no_matches | fetch_failed",
  "error": null,
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "中文摘要",
      "stars": 12345,
      "language": "TypeScript",
      "topics": ["ai", "llm", "agent"]
    }
  ]
}
```

写入 `knowledge/articles` 时使用统一知识条目 schema：

```json
{
  "id": "github-trending-YYYYMMDD-001",
  "title": "owner/repo",
  "source": "github-trending",
  "source_url": "https://github.com/owner/repo",
  "summary": "中文摘要，至少 20 字",
  "tags": ["ai", "llm", "agent"],
  "status": "published",
  "score": 8,
  "audience": "intermediate",
  "metadata": {
    "stars": 12345,
    "language": "TypeScript",
    "topics": ["ai", "llm", "agent"]
  }
}
```
