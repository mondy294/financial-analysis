# financial

一个本地运行的基金管理台，支持基金查询、总览分析、自选列表和手动维护持有信息。

## 主要功能

- 左侧导航切换路由：基金总览 / 我的自选 / 我的持有
- 输入 6 位基金编号，查看最新净值、实时估值、近期阶段收益和最近净值记录
- 使用 ECharts 绘制区间业绩图，支持近 1 月 / 3 月 / 6 月 / 1 年 / 年初至今 / 全部切换
- 图表支持鼠标悬浮查看当前点的日期和净值坐标
- 管理“我的自选”：输入基金编号即可加入、移除、查看详情
- 管理“我的持有”：手动录入持有状态、持有收益率、持仓金额、成本净值、备注
- 自选和持有数据持久化写入项目内 `data/*.json`

## 技术栈

- 前端：React 18 + TypeScript + Vite + React Router + ECharts
- 服务端：Node.js + Express + Koa + TypeScript
- MCP：Koa + `@modelcontextprotocol/server` + `@modelcontextprotocol/node`
- 数据来源：天天基金 / 东方财富公开页面接口
- 持久化：项目内 JSON 文件（`data/watchlist.json`、`data/holdings.json`）

## 项目结构

```text
financial/
├── data/                  # 自选、持有、筛选缓存等 JSON 持久化数据
├── server/
│   ├── mcp/               # Koa + MCP 股票工具暴露层
│   ├── data-store.ts      # 本地 JSON 读写仓储
│   ├── fund-service.ts    # 基金详情聚合服务
│   ├── screener-service.ts# 基金筛选与主题板块服务
│   ├── stock-service.ts   # 股票实时行情与基金持仓股服务
│   └── index.ts           # Express API 主入口，同时拉起 MCP 服务
├── src/
│   ├── api/               # 前端 API 请求封装
│   ├── components/        # 查询卡片、走势组件、基金详情卡等
│   ├── pages/             # 总览 / 我的自选 / 我的持有 路由页面
│   ├── skills/            # 项目内技能与提示词资产
│   ├── utils/             # 格式化与区间筛选工具
│   ├── App.tsx            # 管理台壳层、导航和路由
│   └── main.tsx           # React 入口
├── index.html             # Vite 入口页
├── package.json
├── tsconfig.json
├── tsconfig.server.json
└── vite.config.ts
```

## 启动

```bash
npm install
npm run dev
```

- 前端管理台：`http://localhost:4177`
- API 服务：`http://localhost:4176`
- 股票 MCP 服务：`http://127.0.0.1:4178/mcp`
- MCP 健康检查：`http://127.0.0.1:4178/health`

### MCP 已暴露工具

- `get_realtime_stock_quotes`：批量查询股票最新价、涨跌额、涨跌幅
- `get_fund_holding_stocks`：查询基金最新披露持仓股，并补齐实时涨跌

## 数据说明

- 基金详情来自公开页面接口，不是官方稳定开放 API
- 非交易日估值和净值可能不同步
- 如果接口字段未来变化，基金详情页可能需要跟着调整解析逻辑
