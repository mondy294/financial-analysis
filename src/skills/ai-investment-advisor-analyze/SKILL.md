---
name: ai-investment-advisor-analyze
description: 本地整理版，适用于 ETF/股票的宏观、行业、技术面与交易策略分析
description_zh: ETF/股票择时与交易型分析
version: 1.0.0-local
source_origin: https://skills.sh/allenai2014/ai-investment-advisor/analyze
status: curated-reference
---

# ai-investment-advisor-analyze

## 作用
用于**ETF、行业主题产品、股票**的投资分析，重点在宏观环境、行业强弱、技术面和交易策略，而不是传统公募基金深度研究。

## 适用场景
- 分析行业/主题 ETF 是否适合介入
- 判断 ETF 所在赛道的强弱
- 做趋势、动能、量价、支撑压力分析
- 输出买点、止损、目标位等交易建议

## 推荐输入
- ETF 代码
- 股票代码
- 行业或主题关键词

## 典型输出
- 宏观环境判断
- 行业强弱判断
- 技术面评分
- 交易策略建议

## 最适合
- ETF 轮动分析
- 行业主题基金择时
- 交易型研究

## 不适合
- 主动基金经理风格研究
- 债券基金分析
- 货币基金分析
- 长周期基金配置研究

## 推荐搭配
- 配合 `neodata-financial-search` 获取板块、资金、资讯数据
- 如 ETF 重仓成分股需要深挖，再搭配 `fundamental-report`

## 来源说明
- 来源：`allenai2014/ai-investment-advisor`
- 当前为本地整理版说明，不直接引入第三方执行脚本
