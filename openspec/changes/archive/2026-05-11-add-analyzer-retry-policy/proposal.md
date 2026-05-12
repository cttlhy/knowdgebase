## Why

当前批量分析在运行中会遇到网络抖动、超时或上游限流，导致流程中断。  
中断后通常需要整批重跑，前面已消耗的 token 成本会被放大，因此需要在 LLM 调用层引入有边界的重试与失败隔离策略。

## What Changes

- 在 `pipeline/model_client.py` 的 LLM 调用路径上明确重试边界，只重试明确的可恢复错误。  
- 固化重试参数：`max_retries=3`（含首次，最多 3 次总尝试）、指数退避 `1 -> 2 -> 4`、`max_delay=20s`、`jitter=1.0~1.5x`（只加不减）。  
- 对不可恢复错误（`4xx` 且非 `429`）、中断/取消类错误、以及响应格式错误（如非 JSON 或缺少必需字段）直接失败，不进入重试。  
- 单条 item 达到重试上限后记录失败并继续后续 item，不中断整个 pipeline。  
- 增强日志，记录 `item title/url`、attempt 次数、错误类型、等待时长、以及最终是否放弃该条。

## Capabilities

### New Capabilities

- `llm-retry-policy`: 为 OpenAI 兼容 provider 调用增加可配置且可观测的重试策略，并将失败影响限制在单条分析任务。

### Modified Capabilities

- 无

## Impact

- 受影响代码：
  - `pipeline/model_client.py`（错误分类、退避与 jitter、重试日志）
  - `pipeline/pipeline.py`（单条分析失败后的继续执行与放弃日志）
- 不影响范围：
  - `step_collect / step_organize / step_save` 的业务行为不变
  - 不引入 provider fallback、circuit breaker、async/并发机制
- 运行影响：
  - 在可恢复错误场景下整体成功率提升
  - 在不可恢复错误场景下减少无效重试与额外 token 浪费
