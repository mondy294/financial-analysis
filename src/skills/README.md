# 金融分析 Skills 本地索引

这是一份给后续 agent 使用的本地技能目录，重点放在**基金分析、ETF 分析、基金穿透研究、金融数据查询**。

> 说明：当前目录以**本地整理版 skill 说明**为主，优先沉淀“适用场景、作用、边界、推荐搭配”。这样做更安全，也方便后续 agent 先选型再执行。

## 推荐选用顺序

### 1. 看中国公募基金
- 首选：`fund-screener`
- 搭配：`neodata-financial-search`
- 用途：基金池筛选、单基金分析、风险收益指标对比

### 2. 看 ETF / 行业主题轮动
- 首选：`ai-investment-advisor-analyze`
- 搭配：`neodata-financial-search`
- 用途：ETF 择时、板块强弱、交易型分析

### 3. 做基金持仓穿透
- 首选：`fundamental-report`
- 用途：分析基金重仓股的基本面、估值、风险和同业对比

### 4. 做企业财务/估值类补充分析
- 首选：`finance-skills`
- 用途：比率、DCF、预算差异、预测

## Skills 总览

| Skill | 主要作用 | 最适合的场景 | 不适合的场景 |
|---|---|---|---|
| `fund-screener` | 中国公募基金筛选与单基金分析 | 选基金、比较基金、做风险收益排序 | 个股基本面、企业估值 |
| `neodata-financial-search` | 实时金融数据查询底座 | 查基金/ETF/指数/宏观/行情/资讯 | 替代完整投研框架 |
| `ai-investment-advisor-analyze` | ETF/股票分析、择时和交易策略 | ETF 轮动、行业强弱、技术面判断 | 主动基金/债基长期配置分析 |
| `fundamental-report` | 上市公司基本面研报 | 基金持仓穿透、重仓股研究 | 直接分析基金本身 |
| `finance-skills` | 通用财务分析工具 | 企业财务分析、估值、预测 | 公募基金专门分析 |

## 组合建议

### 组合 A：基金筛选
1. `fund-screener` 初筛基金池
2. `neodata-financial-search` 补实时数据
3. 如需穿透持仓，再看 `fundamental-report`

### 组合 B：ETF 研究
1. `ai-investment-advisor-analyze` 做宏观/行业/技术面判断
2. `neodata-financial-search` 补指数、板块、资讯和资金数据

### 组合 C：持仓公司研究
1. 先拿基金重仓股名单
2. 用 `fundamental-report` 生成公司基本面研报
3. 必要时用 `finance-skills` 补估值或预测分析

## 给后续 agent 的建议
- 先读本文件，再进入对应 skill 目录。
- 先判断你要分析的是：**基金本身 / ETF / 基金持仓公司 / 企业财务**。
- 不要拿企业财务 skill 去硬套基金分析，也不要拿 ETF 技术分析去替代主动基金研究。
- 如果需要真正引入第三方源码版 skill，再单独做一次源码审查和落地。
