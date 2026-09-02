# Agent 提示词模板

```text
参考 `skill-factor-drift-monitor`
请检查下面这个面板数据是否有异常漂移。
数据主键是 `(date, symbol)`。
检查字段包括 close、high、low、open、volume、amount。
请先按 symbol 升序、date 降序排序，再输出 normal、watch、warning 或 failed 的结论。
请实际运行 scripts/monitor_factor_drift.py 并返回指标，不要只复述检查方法。
如果只有自定义因子且没有 close，请跳过 IC，继续完成分布漂移检查。
```
