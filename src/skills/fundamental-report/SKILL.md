---
name: fundamental-report
description: 本地整理版，生成上市公司基本面研报，适合基金持仓穿透分析
description_zh: 上市公司基本面研究报告
version: 1.0.0-local
source_origin: https://skills.sh/tradeinsight-info/investment-analysis-skills/fundamental-report
status: curated-reference
---

# fundamental-report

## 作用
生成**上市公司基本面研究报告**，适合在基金分析中做“持仓穿透”，也就是继续研究基金重仓股背后的公司质量、估值和风险。

## 适用场景
- 分析基金重仓股的利润表、资产负债表、现金流
- 做估值、盈利能力、成长性、财务健康度分析
- 查看公司护城河、竞争地位、风险因素、分析师预期
- 对基金前十大持仓做逐个穿透研究

## 推荐输入
- 股票代码 / Ticker
- 公司名称
- 待穿透分析的基金持仓列表

## 典型输出
- 结构化基本面研报
- 关键财务指标总表
- 多空理由摘要
- 风险与同业对比结论

## 最适合
- 基金持仓公司研究
- 重仓股比较
- 做“基金为什么好/不好”的底层解释

## 不适合
- 直接分析基金本身
- ETF 技术面择时
- 纯宏观配置研究

## 推荐搭配
- 先用 `fund-screener` 或 `neodata-financial-search` 找到基金和持仓线索
- 再用本 skill 做公司层面的穿透分析

## 来源说明
- 来源：`tradeinsight-info/investment-analysis-skills`
- 当前为本地整理版说明，不直接引入第三方执行脚本
