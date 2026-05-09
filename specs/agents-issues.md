# AI 知识库 · 三 Agent Pipeline · 任务拆解

> Parent: `specs/agents-prd.md` v0.1  
> 拆解日期: 2026-04-29  
> 共计: 6 个垂直切片 (全部 AFK)

---

## Issue 1 · Pipeline Orchestrator（核心编排）

**Type:** AFK  
**Blocked by:** None — 可立即开始

### What to build

创建 `scripts/run_pipeline.py` 作为整个流水线的入口：

- 按 collector → analyzer → organizer 顺序执行
- 通过 subprocess 调用 OpenCode agent（读取 `.opencode/agents/*.md` 定义）
- 确立文件传递协议：
  - collector 输出 → `knowledge/raw/{source}-{YYYYMMDD}.json`
  - analyzer 读取 `knowledge/raw/` → 标注后回传
  - organizer 读取标注结果 → 写入 `knowledge/articles/{YYYYMMDD}-{source}-{slug}.json`
- 支持 `--dry-run` 打印即将执行的步骤但不真正运行
- 支持 `--date YYYY-MM-DD` 指定运行日期（默认当天 UTC）

### Acceptance criteria

- [ ] 执行 `python scripts/run_pipeline.py` 能成功跑通完整的三 agent 流水线
- [ ] `knowledge/raw/` 中出现当天的 collector 输出文件
- [ ] `knowledge/articles/` 中出现当天标注后的条目文件
- [ ] 每个 agent 的 stdout/stderr 都被捕获并输出到终端
- [ ] `--dry-run` 只打印步骤不产生文件
- [ ] `--date 2026-04-28` 能对指定日期重跑

---

## Issue 2 · Error Propagation（失败传导）

**Type:** AFK  
**Blocked by:** Issue 1

### What to build

回答 PRD 问题 "上游失败下游怎么办？"：

- 任一 agent 返回非零退出码 → 标记当前步骤 `FAILED`
- 后续所有步骤自动标记 `SKIPPED`，不执行
- 将结构化错误信息写入 `knowledge/pipeline-runs/{YYYYMMDD}.json`：
  ```json
  {
    "run_id": "...",
    "date": "2026-04-29",
    "steps": [
      {"name": "collector", "status": "success", "duration_s": 12.3, "output": "..."},
      {"name": "analyzer",  "status": "failed",  "duration_s": 0.5,  "error": "..."},
      {"name": "organizer", "status": "skipped", "duration_s": 0}
    ]
  }
  ```
- 区分 stdout 正常退出 vs stderr 警告 vs 致命崩溃
- 流水线总体退出码 = 第一个失败步骤的退出码

### Acceptance criteria

- [ ] 模拟 collector 返回非零 → analyzer/organizer 不运行，日志记录 SKIPPED
- [ ] 模拟 analyzer 返回非零 → organizer 不运行，日志记录 SKIPPED
- [ ] 正常成功时，run 文件显示所有步骤为 `success`
- [ ] 错误信息包含 agent 名称、退出码、最后 20 行 stderr

---

## Issue 3 · Retry Strategy（重试策略）

**Type:** AFK  
**Blocked by:** Issue 1

### What to build

回答 PRD 问题 "重跑策略？"：

- 每个 agent 步骤支持自动重试，可配置：
  - `max_retries`：默认 3
  - `backoff_base_s`：初始等待秒数，默认 5s
  - `max_backoff_s`：最大等待秒数，默认 60s
  - 退避策略：指数退避 (5s → 10s → 20s → 40s → 60s)
- 区分错误类型：
  - **Retryable**：网络超时、API 限流 (HTTP 429, 503)、临时 I/O 错误
  - **Non-retryable**：配置错误、认证失败 (HTTP 401, 403)、数据格式错误
- 所有重试记录写入 run 日志
- `--no-retry` 标志禁用所有重试

### Acceptance criteria

- [ ] 模拟第 1 次失败(网络超时) → 重试 → 第 2 次成功 → 步骤标记 success
- [ ] 模拟连续 3 次都失败 → 步骤标记 failed，记录每次重试信息
- [ ] 模拟认证错误(401) → 0 次重试，立即标记 failed
- [ ] `--no-retry` 下任何失败都立即中止
- [ ] 重试日志记录每次尝试的时间戳和失败原因

---

## Issue 4 · Run History & Status（进度追踪）

**Type:** AFK  
**Blocked by:** Issue 1, Issue 2

### What to build

回答 PRD 问题 "进度追踪？"：

- 每次运行在 `knowledge/pipeline-runs/` 下生成 JSON 日志：
  - `run_id` = `{date}-{seq}` 如 `20260429-001`
  - per-step 记录：状态、起止时间、耗时、重试次数、输出文件路径、错误信息
- CLI 子命令：
  - `python scripts/run_pipeline.py --status` → 显示今日运行状态：
    ```
    Pipeline Status for 2026-04-29 UTC
    ┌──────────┬─────────┬──────────┬────────┐
    │ Step     │ Status  │ Duration │ Retries│
    ├──────────┼─────────┼──────────┼────────┤
    │ collector│ success │ 12.3s    │ 0      │
    │ analyzer │ running │ ...      │ -      │
    │ organizer│ pending │ -        │ -      │
    └──────────┴─────────┴──────────┴────────┘
    ```
  - `--history 7` → 最近 7 天的运行摘要
- 支持 `--watch` 模式：持续轮询状态直到完成

### Acceptance criteria

- [ ] 运行流水线后，`knowledge/pipeline-runs/` 出现当日日志文件
- [ ] `--status` 显示最近一次运行的全部步骤状态和耗时
- [ ] `--history 7` 列出最近 7 天每天的成功/失败/跳过数量
- [ ] `--watch` 持续输出现状直到所有步骤终止
- [ ] 同一天多次运行生成 `-001`, `-002` 递增序列号

---

## Issue 5 · Validation Gates（校验门禁）

**Type:** AFK  
**Blocked by:** Issue 1

### What to build

在两两 agent 之间插入自动校验：

- collector 完成 → 运行 `hooks/validate_github.py`（或对应的 `validate_arxiv.py`）校验输出
- analyzer 完成 → 运行 `hooks/check_quality.py` 检查标注质量
- 校验失败 → 流水线中止（后续步骤 SKIPPED），失败详情写入 run 日志
- `--skip-validation` 标志跳过所有校验门禁
- 校验结果作为独立子步骤记录在 run 日志中

### Acceptance criteria

- [ ] collector 输出缺少必要字段 → 校验失败 → analyzer 被 SKIPPED
- [ ] analyzer 输出分数超出 1-10 范围 → 校验失败 → organizer 被 SKIPPED
- [ ] 正常数据通过所有校验 → 流水线完整运行
- [ ] `--skip-validation` 下，校验步骤标记为 `skipped` 而非 `failed`
- [ ] 校验日志清晰指出哪个字段/条目不符合规范

---

## Issue 6 · Idempotent Rerun（安全重跑）

**Type:** AFK  
**Blocked by:** Issue 1

### What to build

确保同一天多次运行不会产生副作用：

- 运行前检查 `knowledge/raw/{source}-{YYYYMMDD}.json` 是否已存在：
  - 存在 → 提示 "数据已存在"，跳过 collector
  - `--force` → 覆盖已有数据，重新采集
- organizer 写入前检查 `knowledge/articles/` 中是否存在相同 URL 的条目：
  - 存在 → 跳过该条目，打印 "skipped: duplicate"
- 重复运行不产生重复的 article 文件（通过 slug + 日期唯一性保证）
- `--force-all` 清除当日所有数据后从头开始

### Acceptance criteria

- [ ] 第一次运行正常采集 → 所有文件生成
- [ ] 第二次运行（同一天） → collector 被跳过，提示 "data exists, use --force"
- [ ] `--force` 覆盖 raw 数据，analyzer + organizer 重新处理
- [ ] 重复条目不会在 articles/ 中产生两份文件
- [ ] `--force-all` 删除当日 raw + articles 后重头运行

---

## 依赖关系图

```
Issue 1 (Orchestrator)
 ├── Issue 2 (Error Propagation)
 │    └── Issue 4 (Run History)  ← 依赖 #1 + #2
 ├── Issue 3 (Retry Strategy)
 ├── Issue 5 (Validation Gates)
 └── Issue 6 (Idempotent Rerun)
```

## 实施建议

1. **先做 #1** — 这是根基，让流水线可运行
2. **#3 #5 #6 可并行** — 互相独立，可在 #1 完成后同时开工
3. **#2 先于 #4** — #4 依赖 #2 的 run 日志结构
