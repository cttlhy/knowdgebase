# AI 生成代码对比：有 Memory vs 无 Memory

本对比基于 `utils/github_api.py` 和 `utils/github_api_new.py` 两个文件。

| 维度 | 有 Memory | 无 Memory |
| --- | --- | --- |
| 命名风格 | 命名更贴近已有代码习惯。使用 `logger`、`resp`、`data`、`result` 等变量，让步骤更清楚。 | 命名较直接。保留 `resp`、`data`，但直接返回字典，过程更短。 |
| docstring | docstring 较完整。包含参数、返回值和异常说明，适合后续维护。 | docstring 也较完整。内容与有 Memory 版本基本一致。 |
| 日志方式 | 使用 `logging`。请求前记录目标仓库，请求成功后记录 stars 和 forks。失败时记录异常堆栈。 | 没有日志。调用失败时只依赖异常向上传递，缺少运行过程信息。 |
| 错误处理 | 使用 `try/except requests.RequestException`。先记录错误日志，再重新抛出异常。问题更容易定位。 | 只调用 `raise_for_status()`。代码更简单，但排查问题时上下文较少。 |
| 文件位置 | 放在 `utils/github_api.py`。更像是沿用已有工具模块的位置和命名。 | 放在 `utils/github_api_new.py`。更像是新建了一个相近文件，可能造成重复实现。 |

## 结论

有 Memory 时，AI 更容易延续项目里的已有习惯。代码会更关注日志、错误定位和文件组织。

无 Memory 时，AI 也能生成可运行的核心功能，但更偏向最小实现。它可能忽略项目已有约定，并产生重复文件或缺少排错信息。
