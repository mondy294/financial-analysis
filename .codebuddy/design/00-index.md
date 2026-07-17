# 设计索引

按阶段顺序记录 quant_system 项目每一轮的设计决策。

| 阶段 | 文档 | 主题 | 状态 |
|---|---|---|---|
| 1 | [01-architecture.md](./01-architecture.md) | 整体架构（6 层 + 模块职责 + 扩展点） | ✅ 已交付 |
| 2 | [02-database-v1.md](./02-database-v1.md) | 数据库设计 v1（18 张表 ER + 索引 + ORM 草案） | ✅ 已交付 |
| 3 | [03-database-v2.md](./03-database-v2.md) | 数据库设计 v2（新增 backtest_task/result、data_quality_check，strategy_signal 加 signal_type） | ✅ 已交付 |
| 4 | [04-skeleton.md](./04-skeleton.md) | 项目骨架 + 依赖 + 配置 + CLI 入口 | ✅ 已交付 |
| 5 | [05-data-layer.md](./05-data-layer.md) | 数据层：Provider / Repository / DataUpdate 编排 / DI 契约 | ✅ 已交付 |
| 6 | [06-feature-quality.md](./06-feature-quality.md) | 手写指标 + 特征聚合 + 数据质量 + 板块过滤 | ✅ 已交付 |
| 7 | [07-strategy-scoring-report.md](./07-strategy-scoring-report.md) | 策略 + 评分 + 日报（端到端产出 HTML） | ✅ 已交付 |
| 8 | [08-strategy-v2-layered-selection.md](./08-strategy-v2-layered-selection.md) | 策略 v2：分层门控 + 多策略共振 + regime 感知（v1.2 定稿） | 🚧 阶段 A 待落地 |
| 9 | [09-stock-relationship-engine.md](./09-stock-relationship-engine.md) | Stock Relationship Layer：收益率 Pearson + 阈值落库 + Lead-Lag | 🚧 已部分落地 |
| 10 | [10-abnormal-detector.md](./10-abnormal-detector.md) | Pattern Template Matching v2：可变窗口 + RelationFeature + Extractor/Evaluator 分离 | 🚧 已部分落地（RANGE_BREAKOUT） |
| 11 | [11-web-console.md](./11-web-console.md) | Web Console：FastAPI + SPA，Pattern/股票详情/选股日报只读操作 | 📝 设计稿待评审 |
| 12 | *待交付* | 回测 + 调度 | 🕐 未开始 |

## 用户核心约束（贯穿所有阶段）

1. **优先跑通链路**：update → feature → strategy → score → report → backtest，架构美感让位于能真跑起来。
2. **不做未来才用的实现**：ML / 向量 / LLM 保留字段/接口预留即可，不写实体模块。
3. **依赖注入**：业务只依赖 Protocol，具体实现由工厂注入；未来切 QMT/tushare 不动业务代码。
4. **数据完整性 vs 使用侧过滤分层**：数据层留全，过滤（板块 / 数据质量）放到 selector 和 backtest。
5. **配置化优先**：股票池、板块、信号记录级别、数据质量过滤级别全走 `.env`，改配置不改代码。

## 用户偏好速查

- 分阶段交付，每步先设计后代码，不接受一次性堆代码
- Python 3.11，暂不升级（pandas-ta 兼容问题走"手写指标"路径而非升 py 版本）
- 数据库：SQLite（WAL），未来可切 PG，ORM 保持中立
- akshare 数据源，A 股主板为主
- CLI 简洁命名：`qs update / feature / select / report / pipeline / backtest / doctor / benchmark`
- 中文回复，工程化表达，无 AI 味
