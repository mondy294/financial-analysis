# 基金 AI 分析接入说明

## 这次新增了什么

### 1. 后端 Agent
- 文件：`server/agent/fund-agent-service.ts`
- 能力：
  - 读取项目 `.env` 中的 DeepSeek Key
  - 使用 OpenAI SDK 兼容方式调用 DeepSeek
  - 复用项目内 MCP 工具做函数调用
  - 输出结构化的“未来走势 + 当前操作建议”结果

### 2. 新增 Skill 与 Reference
- Skill：`server/agent/skills/fund-trend-analyst/SKILL.md`
- Reference：`server/agent/references/fund-analysis-playbook.md`

设计目标：
- 先拿数据再下结论
- 强制区分趋势判断、操作建议、风险提示、待观察指标
- 让近期市场新闻与基金当前/历史数据一起进入分析流程
- 前端能直接看到近期影响因素，而不是只在工具轨迹里瞄一眼
- 避免把概率判断写成确定收益承诺
- 在分析结论之外补一组未来多情景预测，并给每条路径概率、解释和触发条件
- 预测结果与分析记录一起落到本地文件中，同一基金重复分析会覆盖旧预测

### 3. 新增 MCP 数据能力
新增工具：
- `get_fund_peer_benchmark`
  - 返回同类基金分位、可比基金列表
- `get_fund_holding_breadth`
  - 返回重仓股近期涨跌广度、集中度、最强/最弱持仓
- `get_fund_trade_plan`
  - 把均线位置、趋势结构、当前持仓金额、成本净值、组合占比整理成可执行计划
  - 返回试探加仓位、分批加仓位、减仓位、风控线和建议动作幅度
- `get_fund_market_news`
  - 按时间段查询可能影响基金的国内外市场新闻
  - 覆盖焦点、基金、全球股市、商品、外汇、债券、地区、央行和经济数据快讯
  - 现在会默认进入 Agent 分析链路，而不是只在用户主动问新闻时才补充

Agent 当前的默认分析链路：
1. 先预抓 `get_fund_analysis`（默认拉 1 年历史走势）
2. 再取 `get_fund_peer_benchmark`、`get_fund_trade_plan`
3. 如果有股票持仓，补 `get_fund_holding_breadth`
4. 默认补最近 21 天的 `get_fund_market_news`
5. 把“近期新闻 + 当前走势 + 中长期历史数据 + 同类位置 + 当前持仓”一起交给模型生成结论

这样做之后，输出结构保持不变，但近期和长远结论都会更依赖外部事件与历史趋势的联合验证。

另外做了两层输出质量优化：
1. 在系统提示、Skill 和 Reference 里明确要求数组字段直接输出干净要点，避免 `1）`、`2.`、`•` 这类编号残留
2. 在服务端最终归一化阶段增加清洗逻辑，即使模型偶尔写脏，也尽量落成前端可直接展示的干净数组

### 4. 新增接口
- `POST /api/agent/fund-analysis`
- `POST /api/agent/watchlist-analysis`

单基金请求体示例：
```json
{
  "fundCode": "161725",
  "horizon": "未来 1-3 个月",
  "userQuestion": "请分析未来走势并给出当下操作建议。"
}
```

批量自选请求体示例：
```json
{
  "horizon": "未来 1-3 个月"
}
```

其中 `POST /api/agent/watchlist-analysis` 会直接读取 `data/watchlist.json` 的当前自选列表，逐只复用同一条单基金 Agent 分析链路，并把每只基金的最新分析与未来预测覆盖写回现有缓存。

返回结果核心字段：
- `fundCode`
- `fundName`
- `generatedAt`
- `model`
- `toolTrace`
- `report.outlook`
- `report.actionTag`
- `report.actionAdvice`
- `report.holdingContext`
- `report.positionInstruction`
- `report.positionSizing`
- `report.planSummary`
- `report.executionRules`
- `report.planLevels`
- `report.reEvaluationTriggers`
- `report.reasoning`
- `report.risks`
- `report.watchItems`
- `forecast.baseDate`
- `forecast.baseNav`
- `forecast.scenarios[]`（每条包含 `label`、`probability`、`targetReturn`、`targetNav`、`summary`、`trigger`、`pathStyle`、`points[]`）
- `watchlist-analysis.total / succeeded / failed / durationMs / items[]`

### 5. 前端入口
- 页面：基金详情页、自选页
- 组件：`src/components/FundSummaryCard.tsx`、`src/pages/WatchlistPage.tsx`
- 按钮文案：`AI 分析未来走势`、`批量跑 Agent 分析`

### 6. 批量脚本与定时任务入口
- 批量脚本：`server/scripts/watchlist-agent-batch.ts`
- npm 命令：`npm run agent:watchlist`

这个脚本会读取当前 `data/watchlist.json`，逐只调用同一套 Agent 分析与落库逻辑，适合给每天固定时间的自动化任务直接调用。

点击后会在详情页直接展示：
- 趋势判断
- 操作标签
- 结论摘要
- 近期影响因素（新闻摘要 + 最近驱动 + 后续外部观察点）
- 当前持仓背景
- 现在该怎么做
- 关键净值位计划（加仓位 / 减仓位 / 风控线）
- 多情景未来路径预测（每条分支的概率、目标涨跌、说明和触发条件）
- 执行规则
- 重新评估条件
- 核心依据
- 风险点
- 后续观察指标
- 本次实际调用过的工具

业绩图 `src/components/ChartPanel.tsx` 现在会把预测分支直接接在历史曲线最右端：
- 用不同颜色的虚折线表示不同预测分支
- hover 未来日期时会像历史点一样展示净值，并额外展示该分支概率
- 同一基金只保留一份最新预测，重新分析后会覆盖 JSON 文件中的旧分支数据

持有抽屉 `src/components/FundAgentRecordDrawer.tsx` 也同步复用了同一块“近期影响因素”摘要，回看保存记录时不用再自己翻工具轨迹。

## DeepSeek 配置
项目当前通过 `.env` 读取 Key。
兼容这些字段名：
- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`
- `api_key`

可选字段：
- `DEEPSEEK_BASE_URL`，默认 `https://api.deepseek.com`
- `DEEPSEEK_MODEL`，默认 `deepseek-reasoner`


## 本地验证
### 类型检查
```bash
npm run typecheck
```

### 构建
```bash
npm run build
```

### 冒烟测试
```bash
npm run agent:smoke -- 161725
```

会生成：
- `examples/fund-agent-161725-input.json`
- `examples/fund-agent-161725-output.json`

## 当前实现边界
1. 这是同步分析接口，当前未做异步任务队列。
2. 同类对标依赖本地基金池缓存；若目标基金未进入缓存，会在结果里明确提示。
3. 当前默认模型是 `deepseek-reasoner`；如果需要更快响应或遇到兼容性问题，可以通过 `DEEPSEEK_MODEL=deepseek-chat` 回退。

4. 输出属于研究辅助，不构成投资建议。
