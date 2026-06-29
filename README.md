# AI 知识库系统

> 基于多 Agent 协作的 AI 技术知识库——自动采集、智能分析、定时推送

---

## 架构概览

系统采用四层架构，数据自下而上流动：Agent 层负责角色化任务执行，Pipeline 层编排采集→分析→整理流程，工程层提供质量门禁与运维保障，分发层将高价值内容推送到阅读渠道。

```
┌──────────────────────────────────────────────────────────────────┐
│                         分发层  Distribution                      │
│  飞书每日 Digest · Telegram 推送 · MCP 知识检索 · 人工 Review 队列  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                         工程层  Engineering                       │
│  Schema 校验 · CostGuard 成本预算 · Security Guard 安全审计       │
│  GitHub Actions 定时任务 · Hooks 质量门禁 · 重试与失败隔离策略      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                        Pipeline 层  Pipeline                      │
│  轻量流水线: 采集 → 分析 → 整理 → 落盘  (pipeline/pipeline.py)    │
│  完整工作流: Planner → Collect → Analyze → Review → Organize     │
│              → Save → Distribute  (workflows/graph.py)           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                          Agent 层  Agent                          │
│  Collector · Analyzer · Organizer · Reviewer · Reviser           │
│  OpenCode Agent 定义 (.opencode/agents/) · Supervisor/Router 模式  │
└──────────────────────────────────────────────────────────────────┘
```

**数据流：** 外部信息源 → `knowledge/raw/`（原始数据）→ LLM 分析 → `knowledge/articles/`（结构化 JSON）→ 校验 & 分发

---

## 快速开始

### 环境要求

- Python 3.11+
- 大模型 API Key（推荐 DeepSeek，亦支持 Qwen / OpenAI）

### 1. 克隆与安装

```bash
git clone <repo-url>
cd knowdeage

# 安装依赖（Windows 环境可通过 uv 启动 Python）
pip install -r requirements.txt

# 运行 LangGraph 完整工作流时，需额外安装
pip install langgraph
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

在 `.env` 中填入以下关键配置：

```bash
# 大模型（必填）
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxx

# 飞书推送（可选，不配置则跳过分发）
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=your_app_secret
FEISHU_RECEIVE_ID=
FEISHU_RECEIVE_ID_TYPE=chat_id
```

### 3. 运行流水线

**轻量四步流水线**（GitHub Actions 每日任务使用此入口）：

```bash
python pipeline/pipeline.py --sources github,rss --limit 20 --verbose
```

**LangGraph 完整工作流**（含 Planner 策略、Review/Revise 质量闭环、分发）：

```bash
python workflows/graph.py
```

**手动推送飞书日报**：

```bash
python scripts/distribute_daily_articles.py --limit 5
```

**启动 MCP 知识检索服务**：

```bash
pip install mcp
python mcp_knowledge_server.py
```

### 4. 运行测试

```bash
python -m unittest discover -s pipeline/tests -p "test_*.py"
python -m unittest discover -s workflows/tests -p "test_*.py"
python hooks/validate_json.py knowledge/articles/*.json
```

---

## 目录结构

| 目录 / 文件 | 说明 | 版本 |
|---|---|---|
| `.opencode/agents/` | Agent 角色定义（Collector / Analyzer / Organizer 等） | V2 |
| `.opencode/skills/` | 可复用 Agent 技能（采集、分析、整理） | V2 |
| `pipeline/` | 四步自动化流水线（采集→分析→整理→落盘）及 LLM 客户端 | V4 |
| `workflows/` | LangGraph 工作流引擎（Planner / Review / Distribute 等节点） | V3 |
| `knowledge/raw/` | 原始采集数据，按日期归档，便于回溯与重跑 | V1 |
| `knowledge/articles/` | 分析后的结构化 JSON 知识条目（主资产） | V1 |
| `scripts/` | 运维脚本（飞书日报分发、Receive ID 查询等） | V4 |
| `hooks/` | 数据质量校验 Hook（JSON Schema、质量评分、来源校验） | V3 |
| `human_flags/` | Review 未通过时的人工介入标记队列 | V3 |
| `patterns/` | Supervisor / Router 多 Agent 协作模式实验 | V4 |
| `lib/` | 公共工具库（GitHub API 封装等） | V2 |
| `specs/` | 需求文档、编码规范、Agent PRD | V1 |
| `openspec/` | OpenSpec 变更管理与规格归档 | V3 |
| `tests/` | 端到端评估与集成测试 | V3 |
| `mcp_knowledge_server.py` | MCP 本地知识库检索服务（关键词搜索、标签统计） | V4 |
| `.github/workflows/` | GitHub Actions 定时采集与飞书发现任务 | V4 |

---

## 技术栈

| 类别 | 技术 |
|---|---|
| 语言 | Python 3.11 / 3.12 |
| Agent 框架 | OpenCode + OpenClaw |
| 工作流编排 | LangGraph（StateGraph 状态机） |
| 大模型 | DeepSeek Chat / Qwen Plus / GPT-4o-mini（OpenAI 兼容 API） |
| 数据源 | GitHub API、RSS（HN / OpenAI Blog / HuggingFace 等） |
| 分发渠道 | 飞书 Bot、Telegram Bot |
| 知识接口 | MCP（Model Context Protocol）FastMCP |
| CI/CD | GitHub Actions（每日 UTC 08:00 自动采集） |
| 数据格式 | 结构化 JSON（主格式）+ Markdown 日报（副产物） |

---

## 版本历史

### V1 · 基础采集（2026-04）

- 每日抓取 GitHub Trending Top 20
- 关键词初筛 + Agent 语义判断，过滤 AI 相关项目
- 输出结构化 JSON 知识条目与 Markdown 日报
- 支持手动运行与 `--force` 重跑策略

### V2 · 三 Agent 流水线（2026-04 ~ 05）

- 引入 Collector → Analyzer → Organizer 三角色分工
- OpenCode Agent 定义（`.opencode/agents/`），职责边界清晰
- 确立文件传递协议：`knowledge/raw/` → `knowledge/articles/`
- Pipeline Orchestrator 编排与失败传导机制

### V3 · LangGraph 智能工作流（2026-05 ~ 06）

- LangGraph 状态图驱动完整工作流（Planner → Collect → Analyze → Review → Save）
- Review / Revise 质量闭环，未达标自动修订（最多 N 轮）
- Human Flag 人工介入队列，Review 超限后转人工审核
- CostGuard 成本预算、Security Guard 安全审计
- Hooks 质量门禁（Schema 校验、评分阈值、摘要长度检查）

### V4 · 多源分发与自动化（2026-06 当前）

- 多数据源：GitHub + RSS（OpenAI Blog、HuggingFace、HN 等）+ arXiv
- 飞书 / Telegram 定时推送每日 Digest
- GitHub Actions 全自动每日采集、校验、提交
- MCP 知识库检索服务，支持 IDE 内关键词搜索
- Supervisor / Router 多 Agent 协作模式探索
- 分析失败隔离（单条失败不中断整批）、LLM 重试与退避策略

---

## 月度成本估算

以下为**每日采集 20 条、DeepSeek Chat 为默认模型**的参考估算（实际费用因内容长度、Review 轮次而异）。

### 大模型 API

| 项目 | 假设 | 单价（DeepSeek） | 日成本 | 月成本 |
|---|---|---|---|---|
| 单条分析 | ~2,000 input + 800 output tokens | ¥1/M input · ¥2/M output | — | — |
| 每日 20 条（含 Review 约 2× 调用） | 40 次 LLM 调用 | — | ≈ ¥0.20 | ≈ ¥6 |
| LangGraph 完整工作流 | 含 Planner + Review + Revise | — | ≈ ¥0.50 | ≈ ¥15 |
| 预算上限（CostGuard 默认） | 单次运行 ¥1.0 封顶 | — | — | — |

> 切换至 Qwen Plus（¥4/M input · ¥12/M output）时，同等调用量月成本约 **¥60 ~ ¥180**；GPT-4o-mini 约 **¥200+**。

### 服务器 / 基础设施

| 方案 | 说明 | 月成本 |
|---|---|---|
| GitHub Actions（公开仓库） | 每日定时任务 ~5 min，2000 min/月免费额度内 | **¥0** |
| 轻量 VPS 自托管 | 1C2G 云主机跑定时任务 + MCP 服务 | **¥30 ~ ¥50** |
| 对象存储（可选） | 备份 `knowledge/` 目录 | **¥1 ~ ¥5** |

### 合计参考

| 场景 | 大模型 | 服务器 | 合计 |
|---|---|---|---|
| 最低配置（DeepSeek + GitHub Actions） | ≈ ¥6 ~ ¥15 | ¥0 | **≈ ¥6 ~ ¥15 / 月** |
| 标准配置（DeepSeek + VPS 自托管） | ≈ ¥15 | ≈ ¥40 | **≈ ¥55 / 月** |
| 高质量配置（Qwen Plus + VPS） | ≈ ¥100 | ≈ ¥40 | **≈ ¥140 / 月** |

> 详细 Token 消耗对比可记录至 [`cost_comparison.md`](cost_comparison.md)。

---

## License

MIT
