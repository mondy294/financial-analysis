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
- 避免把概率判断写成确定收益承诺

### 3. 新增 MCP 数据能力
新增工具：
- `get_fund_peer_benchmark`
  - 返回同类基金分位、可比基金列表
- `get_fund_holding_breadth`
  - 返回重仓股近期涨跌广度、集中度、最强/最弱持仓

Agent 仍会继续使用已有工具：
- `get_fund_analysis`
- `get_my_fund_holding`
- `query_fund_universe`
- `get_sector_funds`

### 4. 新增接口
- `POST /api/agent/fund-analysis`

请求体示例：
```json
{
  "fundCode": "161725",
  "horizon": "未来 1-3 个月",
  "userQuestion": "请分析未来走势并给出当下操作建议。"
}
```

返回结果核心字段：
- `fundCode`
- `fundName`
- `generatedAt`
- `model`
- `toolTrace`
- `report.outlook`
- `report.actionTag`
- `report.actionAdvice`
- `report.reasoning`
- `report.risks`
- `report.watchItems`

### 5. 前端入口
- 页面：基金详情页
- 组件：`src/components/FundSummaryCard.tsx`
- 按钮文案：`AI 分析未来走势`

点击后会在详情页直接展示：
- 趋势判断
- 操作标签
- 结论摘要
- 核心依据
- 风险点
- 后续观察指标
- 本次实际调用过的工具

## DeepSeek 配置
项目当前通过 `.env` 读取 Key。
兼容这些字段名：
- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`
- `api_key`

可选字段：
- `DEEPSEEK_BASE_URL`，默认 `https://api.deepseek.com`
- `DEEPSEEK_MODEL`，默认 `deepseek-chat`

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
3. 当前默认模型是 `deepseek-chat`，如果后续要加强推理，可以改成 `deepseek-reasoner` 继续试。
4. 输出属于研究辅助，不构成投资建议。
