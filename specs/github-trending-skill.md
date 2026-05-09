# skill: github-trending · Spec

## description（关键字段）

目标：覆盖用户所有可能的表达方式，让 agent 能精准判断何时激活此技能。

```
Collect GitHub Trending Top 50 repositories, filter AI-related projects, and output structured JSON. Use when user wants to: 采集/抓取/爬取 GitHub 热门/趋势/流行项目或仓库; 看看 GitHub 上最近什么火/值得关注; 获取 GitHub Trending / 排行榜 / 热门推荐; 收集/整理 AI / LLM / Agent / ML / RAG / Copilot 相关开源项目或工具; 搜索 GitHub 上特定领域的热门仓库或开源方案; 输出 GitHub 热点项目清单用于分析报告或周报; 批量获取 GitHub 项目元数据（Star、语言、Topics、描述）。 Default window is weekly. Override with daily or monthly when user says 今天/本周/本月 or today/this week/this month.
```

### 触发词矩阵

| 类别 | 中文表达 | English |
|------|---------|---------|
| 动词 | 采集, 抓取, 爬取, 收集, 获取, 查询, 搜索, 找, 看, 看看, 了解, 整理 | collect, scrape, fetch, get, search, find, look up, check |
| 时间 | 今天, 本周, 本月, 最近, 近期, 近 30 天 | today, this week, this month, recent |
| 平台 | GitHub | GitHub |
| 修饰 | 热门, 趋势, 流行, 火, 活跃, Star 多, Star 增长快, 值得关注, 最多 Star, 最火 | trending, popular, hot, top, most starred, fastest-growing |
| 对象 | 项目, 仓库, 开源项目, 开源工具, 开源方案 | projects, repos, repositories, open-source |
| 领域 | AI, LLM, Agent, ML, RAG, Copilot, 人工智能, 大模型, 机器学习, 智能体 | AI, LLM, Agent, ML, RAG, Copilot, artificial intelligence, machine learning |
| 输出 | 排行榜, 清单, 列表, 报告, JSON | ranking, list, report, JSON |

### 典型用户查询示例

```
"采集 GitHub 热门项目"
"看看 GitHub 上最近什么火"
"GitHub Trending 今天有哪些项目"
"找 AI 领域的热门开源项目"
"GitHub 本周 Star 增长最快的项目"
"爬取 GitHub 热门仓库"
"GitHub 开源项目排行榜"
"最近 GitHub 上有什么值得关注的项目"
"GitHub 趋势项目分析"
"抓取 GitHub Trending 数据"
"GitHub 热门开源项目推荐"
"看看本周 GitHub 上 AI 相关的热门项目"
"GitHub Trending 本月有哪些 AI 项目"
"收集 Agent 相关的 GitHub 热门项目"
"GitHub 上有什么好用的 AI 开源工具"
"获取 GitHub 热点项目清单"
"查一下 GitHub 最近流行的开源方案"
"GitHub 开源替代品有哪些"
"GitHub trending for AI this month"
"check GitHub trending this week"
"find top AI projects on GitHub"
"scrape GitHub popular repos"
```

## 要做什么

- 主数据源使用 GitHub Trending 页面，抓取 Trending Top 50
- 页面失败时，才使用 GitHub Search API 兜底
- 默认时间窗为 `weekly`，用户可指定 `daily` 或 `monthly`
- 按 AI / LLM / Agent / ML / RAG / Copilot 等关键词做第一阶段过滤
- 排除 `awesome-*`、`papers`、`resources`、`tutorial`、`list` 等列表或资料类仓库
- 按 owner/repo 去重
- 生成中文摘要：项目名 + 做什么 + 为什么值得关注
- 返回全部命中项，不默认裁成 Top 15
- 输出 JSON，只有调用方明确要求时才写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`

## 不做什么

- 不爬非 GitHub 平台
- 不存数据库（由 caller 决定）
- 不做深度代码分析（只做项目级元数据采集）
- 不读取 README 做深度判定

## 边界 & 验收

- 单次执行 < 30s
- 失败时仍返回合法 JSON，不抛异常
- JSON 输出必须通过 schema 验证
- 排除 Awesome 列表类仓库
- 摘要必须为中文
- 默认抓取 `weekly` Trending Top 50

## 输出 schema

采集结果 schema：

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

## 验证方法

- 运行 `skill-invoke github-trending`，检查采集结果是 JSON 且字段完整
- 写入 `knowledge/articles` 后运行 `hooks/validate_json.py`
- 检查默认时间窗：未指定时应使用 `weekly`
- 检查数据源：优先来自 Trending 榜单，而不是普通搜索结果
- 检查排除逻辑：确认 `awesome-*` 不在结果中
- 检查去重逻辑：确认无重复 owner/repo
- 检查摘要：确认全部为中文
- 检查失败语义：抓取失败时 `status` 为 `fetch_failed`，且仍返回合法 JSON
