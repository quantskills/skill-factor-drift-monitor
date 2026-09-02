# 因子漂移监控 Skill

[English](README.en.md) | 中文

检查 `(date, symbol)` 面板中的行情字段或因子是否出现缺失、重复、异常值、覆盖率变化和分布漂移。它是诊断工具，不生成因子、不回测、不修改原始数据。

原始贡献者：cuijie0317；QUANTSKILLS 发布维护：abgyjaguo。社区项目，未声明官方认证或推荐。

## 流程

```text
读取指定输入、合成样例或 .env 的 Parquet -> 校验契约 -> 按 symbol 升序/date 降序排序
-> 覆盖率与数值检查 -> 窗口统计/PSI/KS -> 分级报告
```

优先读取用户指定文件；本地演示可先运行 `tests/generate_synthetic_panel.py` 生成不含真实行情的确定性样例。没有明确输入时再使用 `.env` 的 `PARQUET_ROOT_PATH`。只读取指定字段和日期，避免扫描全库。

## 输入

至少需要 `date, symbol` 和待检查的数值列。常用字段为 `close, high, low, open, volume, amount`，也支持自定义因子。支持 CSV、Parquet。真实路径、数据和报告不要提交 Git。

加载后必须先按 `symbol` 升序、`date` 降序排序；计算收益等派生指标时，脚本内部另建时间升序副本，防止方向错误。

## 检查项

- 结构：空表、缺列、类型、重复 `(date, symbol)`。
- 覆盖：标的数、样本数、日期范围和缺失率。
- 数值：非有限值、非正价格、OHLC 关系和分布异常。
- 漂移：基准窗口与近期窗口的均值、标准差、标准差比率、PSI、KS。

小股票池的 PSI/KS 统计不稳定，必须注明低置信度，不可直接判定因子失效。

## 使用

```powershell
python tests/generate_synthetic_panel.py
python scripts/monitor_factor_drift.py --input tests/synthetic_panel.csv --output tests/synthetic_report
```

## 状态与输出

`normal` 表示无明显异常；`watch` 表示轻微变化或样本不足；`warning` 表示需要人工核查；`failed` 表示无法满足数据契约。报告必须含输入来源、字段、日期范围、样本量、指标、异常原因、影响范围和建议。`warning` 不等于删除数据，应先核对数据源、复权和公司行动。

详见 `SKILL.md`、`references/data-contract.md`、`references/output-contract.md` 和 `references/prompt_template.md`。

## 生产流水线

```mermaid
flowchart LR
 A[面板数据] --> B[安装/检查依赖]
 B --> C[读取 tests 或 Parquet]
 C --> D[主键与排序校验]
 D --> E[覆盖率/数值/分布检查]
 E --> F[异常分级报告]
```

## 这个 Skill 解决什么问题

在因子研究前及时发现数据缺失、重复、异常值、样本覆盖变化和因子分布漂移，避免把数据问题误判为策略或因子问题。

## 输入数据要求

必须有 `date`、`symbol` 和至少一个数值检查字段。支持 CSV、Parquet；可选 `close` 或收益列用于预测性漂移诊断。加载后先按 `symbol` 升序、`date` 降序。

## 生成出来的检查结构

```text
source -> normalized panel -> coverage/value checks
       -> baseline vs monitoring window -> status/reasons
```

## 快速开始

```powershell
python tests/generate_synthetic_panel.py
python scripts/monitor_factor_drift.py --input tests/synthetic_panel.csv --factors close,volume --output tests/synthetic_report
```

## 验证指标

缺失率、重复键、日期覆盖、样本数、均值变化（标准差单位）、标准差比率、PSI、KS；有收益列时增加 Rank IC 及 IC 保留率。小样本结论自动标低置信度。

## 安装到智能体环境

将本目录复制到 Agent skills 目录，在 Python 3.12 安装 `pandas`、`numpy` 及 Parquet 读取依赖，复制 `.env.example` 为 `.env` 并配置路径（如使用路径发现脚本）。

## 仓库内容

`SKILL.md`、中英文 README、`references/` 数据与输出契约、`scripts/monitor_factor_drift.py` 执行脚本、`tests/` 合成数据生成器、`agents/` 多运行时入口。

## License

GPL-3.0-only。监控结论仅供研究和数据治理，不构成投资建议。仓库不分发真实行情或私有数据集。

## PandaAI / QUANTSKILLS 社群

PandaAI / QUANTSKILLS 社群：<https://github.com/quantskills>。
