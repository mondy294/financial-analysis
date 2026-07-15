# 02 · 数据库设计 v1（初版）

> 已被 [v2](./03-database-v2.md) 取代，本文件保留为演进记录。

## 数据规模估算（10 年，全 A 股）

| 表 | 行数 | 空间 |
|---|---|---|
| daily_kline | 1290 万 | 1.5 GB |
| daily_feature | 1290 万 | 5.2 GB |
| strategy_signal | 190 万 | 380 MB |
| financial_snapshot | 21 万 | 42 MB |
| **合计** | | **~9 GB** |

**结论**：SQLite（20-50 GB 舒适区）完全撑得住，无需分表分区，但需合理索引 + 宽表/窄表取舍。

## 18 张表分组（v1）

| 分组 | 表 |
|---|---|
| 基础域 | industry / stock_basic / stock_pool / stock_pool_member |
| 行情域 | daily_kline |
| 财务域 | financial_snapshot |
| 市场域 | index_daily / market_daily / market_feature_daily |
| 特征域 | daily_feature / feature_meta |
| 策略域 | strategy / strategy_signal / strategy_signal_feature / strategy_performance |
| 报告域 | daily_report / daily_report_item |
| 系统域 | job_run_log / data_sync_state |

## v1 关键决策

1. **联合主键 `(code, trade_date)`** 而不是自增 id：`WITHOUT ROWID` 后主键即聚簇索引，同股票数据物理相邻，时序扫描 IO 最优。
2. **复权数据**：只存原始价 + `adj_factor`，永不覆盖；读取层动态算复权。
3. **成分股按时间序列存**：`stock_pool_member(pool_code, code, in_date, out_date)`，回测时按 `as_of` 还原历史成分，防止未来函数。
4. **财务 `ann_date` 单独存**：回测严格用 `ann_date <= 当前日` 过滤，防止提前用到未公告财报。
5. **特征宽表 + JSON 扩展位**：稳定字段做列（可索引），实验因子先塞 `ext` JSON，稳定后再 alter。

## 常用索引（按查询模式反推）

| 查询 | 索引 |
|---|---|
| 单股时间序列 | PK `(code, trade_date)` |
| 全市场当日 | IDX `(trade_date, code)` |
| 突破股筛选 | IDX `(trade_date, break_high_20d)` |
| 估值筛选 | IDX `(trade_date, pe_ttm)` |
| 策略历史触发 | IDX `(strategy_code, trade_date)` |
| 日报 TopN | IDX `(trade_date, final_score DESC)` |

## v1 遗漏的问题（v2 修正）

- 缺 `signal_type`（只有 hit bool），无法记录 WATCH/NEAR_MISS/FILTERED
- 缺 backtest_task/result 表，无法保存回测实验元数据
- 缺 data_quality_check 表
- daily_feature 基本面字段无血缘（不知道 pe/roe 来自哪一期财报）
- 缺向量预留字段
