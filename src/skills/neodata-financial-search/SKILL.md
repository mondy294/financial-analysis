---
name: neodata-financial-search
description: 本地整理版，金融数据查询底座，可查询基金、ETF、指数、板块、宏观等实时数据
description_zh: 基金/ETF/宏观/行情实时金融数据查询
version: 1.0.0-local
source_origin: local-marketplace:/Users/lijiaao/.workbuddy/skills-marketplace/skills/neodata-financial-search
status: curated-reference
---

# neodata-financial-search

## 作用
作为**金融分析的数据底座**，提供基金、ETF、指数、股票、板块、宏观、外汇、大宗商品等实时数据查询能力。

## 适用场景
- 查询基金产品信息、净值、基本资料
- 查询 ETF、指数、板块、个股、宏观数据
- 获取行情、财报、资金流向、研报、事件公告等实时信息
- 给其他分析 skill 提供数据补充和校验

## 推荐输入
- 自然语言查询，例如：
  - 某基金近一年表现如何
  - 某 ETF 最近走势如何
  - 某行业板块今天资金流向如何
  - 某基金经理管理产品表现如何

## 典型输出
- 实时金融数据摘要
- 基金/ETF/市场相关结构化信息
- 财经资讯或研报线索

## 最适合
- 做实时查询
- 给筛选结果补数据
- 作为基金/ETF 分析前的基础信息收集层

## 不适合
- 单独充当完整投研结论
- 替代基金筛选模型或基本面研究框架

## 推荐搭配
- 配合 `fund-screener` 做基金筛选后的二次验证
- 配合 `ai-investment-advisor-analyze` 做 ETF 数据补充
- 配合 `fundamental-report` 做持仓公司背景补充

## 来源说明
- 来源：本地 marketplace `neodata-financial-search`
- 当前保留为本地整理版说明，便于 agent 快速识别用途
