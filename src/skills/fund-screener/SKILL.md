---
name: fund-screener
description: 本地整理版，中国公募基金量化筛选与单基金分析 skill
description_zh: 中国公募基金筛选与单基金分析
version: 1.0.0-local
source_origin: https://skills.sh/sososun/mutual-fund-skills/fund-screener
status: curated-reference
---

# fund-screener

## 作用
用于**中国公募基金**的量化筛选和单基金分析，适合从大基金池中快速筛出满足特定风险收益条件的候选。

## 适用场景
- 从全市场中筛选纯债基金、固收+、股票类基金
- 按夏普、索提诺、卡玛、最大回撤、年化收益进行过滤
- 对单只基金做风险指标、收益表现、资产配置、基金经理、持仓等分析
- 输出基金池结果供后续人工复核或进一步研究

## 推荐输入
- 基金代码 / 基金名称
- 筛选条件：最小夏普、最小卡玛、最大回撤、最小收益等
- 基金类别：纯债、固收+、股票类、股票 Alpha

## 典型输出
- 单基金分析摘要
- 基金筛选清单
- 风险收益指标对比表
- 可导出的结构化结果（如 CSV）

## 最适合
- 国内公募基金池筛选
- 做“先筛后看”的投研流程
- 想快速缩小候选范围

## 不适合
- 个股基本面研究
- 企业估值或财报分析
- ETF 短线择时

## 推荐搭配
- 与 `neodata-financial-search` 搭配，用来补充实时基金/宏观/市场数据
- 如要穿透到持仓公司，再搭配 `fundamental-report`

## 来源说明
- 来源：`sososun/mutual-fund-skills`
- 当前为本地整理版说明，不直接引入第三方执行脚本
