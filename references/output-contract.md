# 输出契约

至少输出：

- 数据来源
- 检查对象
- 时间范围
- 异常项
- 异常等级
- 触发异常的指标和阈值
- 置信度（`low` 或 `standard`）
- 处理建议

## 结果等级

- `normal`
- `watch`
- `warning`
- `failed`

`failed` 用于无法执行的数据契约错误；可正常计算但样本少时用 `watch + low confidence`。每个字段至少报告窗口、行数、标的数、缺失率、均值偏移、标准差比率、PSI、KS、状态和原因；存在收益目标时再报告 Rank IC 与 IC 保留率。
