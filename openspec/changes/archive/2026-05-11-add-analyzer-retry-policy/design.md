## Context

当前 `pipeline` 的批量分析依赖 LLM 调用。  
在网络抖动、超时、限流时，单次失败可能中断整批处理，导致前序已消耗 token 的价值被放大损失。

现有目标是以最小改动方式增强鲁棒性，并保持系统简单：
- 只在 LLM 调用层处理重试；
- 不引入 provider fallback、circuit breaker、并发改造；
- 保持 `step_collect / step_organize / step_save` 的行为边界不变。

## Goals / Non-Goals

**Goals:**
- 为 LLM 调用建立明确、可审计的重试策略。
- 只重试可恢复错误，避免无意义重试。
- 单条分析失败时不中断整批运行。
- 通过结构化日志提升可观测性与排障效率。

**Non-Goals:**
- 不做跨 provider 自动切换。
- 不做全局熔断。
- 不引入异步或并发执行模型。
- 不改变采集、整理、保存阶段的业务规则。

## Decisions

### Decision 1: 重试边界按“可恢复错误”划分

实现仅对以下错误进行重试：
- 网络类错误（连接中断、临时网络不可达等）
- 超时错误
- HTTP `429`
- HTTP `5xx`

以下错误不重试并立即失败：
- HTTP `4xx`（除 `429`）
- 中断/取消类错误（用户或运行时主动中断）
- 响应格式错误（例如 JSON 解析失败或缺少解析必需字段）

**Rationale:**  
该划分能避免对确定性失败做重复请求，控制 token 与时间成本，并使行为可预测。

**Alternatives considered:**
- 对所有异常统一重试：实现简单，但会放大无效请求与成本。
- 仅按异常类型重试不看状态码：会误重试 `400/401/403` 等不可恢复错误。

### Decision 2: 固化退避参数，优先稳定和简单

重试参数固定为：
- `max_retries=3`（含首次；即最多 3 次总尝试）
- 指数退避基于 `base_delay=1s`，序列 `1 -> 2 -> 4`
- `max_delay=20s` 封顶
- 每次等待加入 `1.0~1.5x` jitter（只加不减）

**Rationale:**  
固定参数减少配置复杂度。正向 jitter 能降低雪崩重试风险，同时避免等待时间被压短。

**Alternatives considered:**
- 全部参数外置配置：灵活但引入额外配置管理成本。
- 对称 jitter（可能小于 1）：恢复更快但更易产生同步重试峰值。

### Decision 3: 失败隔离到 item 级别

当某条 item 在重试上限后仍失败，记录失败并继续处理后续 item。  
不会因为单条失败终止整条 pipeline。

**Rationale:**  
这直接降低“中途失败导致全量重跑”的概率，是当前阶段最直接的成本收益点。

**Alternatives considered:**
- fail-fast 全局中断：行为直接，但在批处理场景下浪费更大。

### Decision 4: 日志最小必需字段标准化

重试日志与最终失败日志必须包含：
- item 标识：`title`、`url`
- 重试信息：`attempt/current_total`、等待时长
- 错误信息：错误类型（必要时附状态码）
- 结果信息：最终是否放弃该条并继续

**Rationale:**  
保证定位问题时有足够上下文，不必复现才能判断根因归类。

## Risks / Trade-offs

- [Risk] 外部接口波动较大时，重试会拉长单条处理时间  
  → Mitigation: 重试次数上限固定为 3，且 delay 受 `max_delay` 封顶。

- [Risk] 单条失败继续执行可能降低最终成功条目比例  
  → Mitigation: 明确记录最终放弃日志，后续可基于日志做定向补跑。

- [Risk] 错误分类实现不严谨会导致误重试或漏重试  
  → Mitigation: 在 specs 中用场景明确状态码与错误类型判定规则。

- [Risk] 正向 jitter 增加平均等待时间  
  → Mitigation: 仅在重试路径生效，不影响成功首调用路径。
