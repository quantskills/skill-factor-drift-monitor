---
name: skill-factor-drift-monitor
description: 检查 `(date, symbol)` 面板数据的因子或字段是否异常漂移，优先本地样例和 parquet，先排序再检查。
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: quantskills/skill-factor-drift-monitor
  repository_url: https://github.com/quantskills/skill-factor-drift-monitor
  project_type: skill
  collection: factor-quality
  license: GPL-3.0-only
  creator: cuijie0317
  maintainer: abgyjaguo
  platforms: [claude-code, codex, cursor, hermes, openclaw]
---

# 因子漂移监控

## 目标

- 检查面板数据是否异常
- 识别因子漂移、缺失、重复、离群和分布变化
- 优先用本地样例数据快速完成检查
- 只读取指定股票、日期和字段；同一面板在一次任务中只加载一次并复用

## 必须遵守

- 先按 `symbol` 升序、`date` 降序整理，再做检查。
- 只检查 `(date, symbol)` 面板数据。
- 不要先假设数据正常。
- 不要把小样本误判成大漂移。
- 优先级固定为：用户明确指定的输入 -> `tests/` 本地生成的合成面板 -> `.env` 本地 Parquet；读取到非空且字段完整的数据后立即停止探测。

## 检查范围

- 默认检查 `close, high, low, open, volume, amount`；用户指定时只检查指定字段。
- 允许只有自定义因子、没有 `close`。此时只做结构、覆盖、数值和分布漂移，不计算 IC。
- 有 `close` 或用户明确提供收益列时，才增加 Rank IC 和 IC 保留率。

## 标准流程

1. 优先使用用户明确指定的输入；没有时查 `tests/` 本地生成的合成面板，再读取 `.env` 的 `PARQUET_ROOT_PATH`。
2. 按股票、日期和字段过滤，读取后报告行数、标的数和日期范围。
3. 面板按 `symbol` 升序、`date` 降序排序并复用，不重复读取。
4. 检查缺失、重复、非正价格、OHLC 关系、异常值和分布变化。
5. 运行 `scripts/monitor_factor_drift.py`，不得只描述流程；返回报告中的真实指标。
6. 输出正常、观察、警告或失败结论，并解释触发原因和置信度。

## 输出要求

- 检查对象
- 数据范围
- 发现的问题
- 异常等级
- 处理建议

## 结果判断

- `normal`：没有明显异常
- `watch`：有轻微波动，需要继续观察
- `warning`：有可疑异常，需要人工确认
- `failed`：数据结构或质量无法使用

`failed` 是任务级状态：空表、缺少主键、重复主键、缺少请求字段或基准/监控窗口为空时，停止计算并报告原始错误。少于 5 个标的或单窗口少于 100 行时，分布统计标记为低置信度，不能仅凭 PSI/KS 升级为 `warning`。

## 按需读取参考文件

- 普通检查读取 `references/data-contract.md` 和 `references/output-contract.md`。
- 用户需要生成检查命令时读取 `references/prompt_template.md`。
- 数据来源或权限问题读取 `references/source_boundary.md`。
- 脚本失败必须返回输入路径、阶段、原始异常和修复建议；小样本只能给低置信度结论。
