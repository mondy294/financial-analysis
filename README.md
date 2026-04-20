# financial

一个支持本地运行、也可部署到 Vercel 的基金管理台，支持基金查询、总览分析、自选列表和手动维护持有信息。

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
- 数据来源：天天基金 / 东方财富公开页面接口（含基金详情、主题板块、全球财经快讯）
- 持久化：项目内 JSON 文件（`data/watchlist.json`、`data/holdings.json`）

## 项目结构

```text
financial/
├── api/
│   └── [...path].ts       # Vercel Function 入口，转发所有 /api/* 请求
├── data/                  # 本地默认 JSON 数据与缓存种子
├── server/
│   ├── mcp/               # Koa + MCP 股票工具暴露层
│   ├── app.ts             # 可复用的 Express API 应用
│   ├── data-store.ts      # 本地 / Vercel 数据目录适配
│   ├── fund-service.ts    # 基金详情聚合服务
│   ├── screener-service.ts# 基金筛选与主题板块服务
│   ├── stock-service.ts   # 股票实时行情与基金持仓股服务
│   └── index.ts           # 本地 Node 主入口，同时拉起 MCP 服务
├── src/
│   ├── api/               # 前端 API 请求封装
│   ├── components/        # 查询卡片、走势组件、基金详情卡等
│   ├── pages/             # 总览 / 我的自选 / 我的持有 路由页面
│   ├── skills/            # 项目内技能与提示词资产
│   ├── utils/             # 格式化与区间筛选工具
│   ├── App.tsx            # 管理台壳层、导航和路由
│   └── main.tsx           # React 入口
├── vercel.json            # Vercel 构建与 SPA 路由回退配置
├── index.html             # Vite 入口页
├── package.json
├── tsconfig.json
├── tsconfig.server.json
└── vite.config.ts
```

## 本地启动

```bash
npm install
npm run dev
```

- 前端管理台：`http://localhost:4177`
- API 服务：`http://localhost:7070`
- Financial MCP 服务：`http://127.0.0.1:9090/mcp`
- MCP 健康检查：`http://127.0.0.1:9090/health`

## 部署到 Vercel

### 1. 构建输出

项目已经适配为：

- 前端由 `Vite` 构建到 `dist/`
- 后端通过 `api/[...path].ts` 作为 `Vercel Function` 提供 `/api/*`
- 前端继续使用相对路径 `/api/...` 调接口，无需额外改动
- React Router 通过 `vercel.json` 做 SPA 回退

### 2. 需要配置的环境变量

如果你要使用基金分析 Agent，建议至少在 Vercel 项目里配置：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`（可选，不配则走默认值）
- `DEEPSEEK_MODEL`（可选）

### 3. 数据持久化说明

为了兼容 Vercel 的只读部署文件系统，服务端在 `Vercel` 环境下会把可写数据目录切到 `/tmp/financial-data`，并在首次访问时从仓库里的 `data/` 拷贝初始 JSON 文件。

这意味着：

- 页面和 API **可以正常运行**
- 自选、持有、筛选缓存、模型设置等写操作 **只保证当前运行实例内可用**
- 这些数据 **不是长期持久化存储**，实例回收、扩缩容或重新部署后可能丢失

如果你希望 Vercel 上的数据长期保存，下一步建议把这部分从 `JSON 文件` 迁移到真正的数据库或对象存储。

### MCP 已暴露工具

- `get_realtime_stock_quotes`：批量查询股票最新价、涨跌额、涨跌幅
- `get_fund_holding_stocks`：查询基金最新披露持仓股，并补齐实时涨跌
- `get_fund_analysis`：按基金编号获取净值、区间走势、5/10/20/60 日均线、阶段收益、波动回撤、重仓股和本地持仓
- `get_my_fund_holding`：按基金编号查询我的当前本地持仓，并补充净值、估值和盈亏测算
- `list_my_fund_holdings`：列出本地全部基金持仓和组合汇总
- `get_fund_screener_options`：获取基金筛选器选项、主题、行业概念和排行榜定义
- `query_fund_universe`：按收益、回撤、波动、费率、主题等条件筛选基金池
- `get_fund_sectors`：获取基金池中有数据的行业、概念和标签统计
- `get_sector_funds`：查看某个行业/概念/标签下的基金列表
- `get_fund_market_news`：按时间段查询可能影响基金的国内外市场新闻，覆盖焦点、基金、股市、商品、外汇、债券、地区、央行和经济数据快讯
- `refresh_fund_universe_cache`：主动刷新基金池和行业概念缓存


## 数据说明

- 基金详情来自公开页面接口，不是官方稳定开放 API
- 非交易日估值和净值可能不同步
- 如果接口字段未来变化，基金详情页可能需要跟着调整解析逻辑
