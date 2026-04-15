# financial 项目架构与交互说明

> 更新时间：2026-04-15  
> 适用范围：`/Users/lijiaao/Desktop/financial`

## 1. 项目定位

`financial` 是一个本地运行的基金管理台，目标不是做公开投研平台，而是做一个偏个人工作台的工具：

- **基金总览**：查某只基金的净值、估值、区间业绩、历史净值和技术指标
- **条件选基与排行榜**：按基金类型、板块、收益、回撤、波动率、费率等条件筛选候选池，并查看收益榜 / 低回撤榜 / 稳健底仓榜 / 高弹性进攻榜
- **基金对比**：把候选基金加入本地对比池，横向查看收益、回撤、波动率和透明评分
- **我的自选**：维护一个重点观察池，快速查看常看基金的近期表现
- **我的持有**：手动记录自己的持仓状态、收益率、成本净值、持仓金额和备注
- **本地持久化**：不接数据库，直接把自选、持有、对比池和筛选方案写入项目内 JSON 文件

---

## 2. 技术栈与运行方式

### 前端
- React 18
- TypeScript
- Vite 6
- React Router 6
- ECharts + echarts-for-react

### 后端
- Node.js
- Express 4
- TypeScript

### 数据来源
- 天天基金 / 东方财富公开页面接口
- 服务端负责抓取、聚合、清洗并转成前端可直接消费的结构

### 本地持久化
- `data/watchlist.json`
- `data/holdings.json`
- `data/compare-list.json`
- `data/fund-universe-cache.json`
- `data/screener-presets.json`

### 启动方式
```bash
npm install
npm run dev
```

默认端口：
- 前端：`http://localhost:4177`
- API：`http://localhost:4176`

---

## 3. 目录结构与模块职责

```text
financial/
├── data/                      # 自选 / 持有的 JSON 持久化文件
├── docs/
│   └── PROJECT_ARCHITECTURE.md
├── server/                    # Express API、基金聚合逻辑、JSON 仓储
├── src/
│   ├── api/                   # 前端请求层
│   ├── components/            # 查询组件、详情卡、图表组件
│   ├── pages/                 # 路由页面
│   ├── utils/                 # 格式化、指标计算、区间处理
│   ├── App.tsx                # 应用壳层、导航、路由、全局状态
│   ├── main.tsx               # React 入口
│   ├── styles.css             # 全局样式
│   └── types.ts               # 前端类型定义
├── index.html                 # Vite 入口
├── README.md
├── package.json
├── tsconfig.json
├── tsconfig.server.json
└── vite.config.ts
```

### 3.1 前端核心模块

#### `src/main.tsx`
职责：
- 创建 React 根节点
- 注入 `BrowserRouter`
- 挂载全局样式

#### `src/App.tsx`
职责：
- 整个管理台的**应用壳层**
- 左侧导航栏与主工作区布局
- 全局状态管理：
  - `spotlight`：当前聚焦基金详情
  - `watchlist`：自选列表
  - `holdings`：持有列表
  - `holdingDraft`：待编辑的持有表单草稿
  - `notice`：全局 toast 提示
- 负责路由分发：
  - `/overview`
  - `/screener`
  - `/watchlist`
  - `/compare`
  - `/holdings`
- 负责把页面动作连接到 API 层

#### `src/pages/OverviewPage.tsx`
职责：
- 总览页容器
- 如果还没有查询基金，显示引导卡片
- 如果已有聚焦基金，渲染 `FundSummaryCard`

#### `src/pages/WatchlistPage.tsx`
职责：
- 展示自选基金列表
- 每张卡片显示基金简要表现
- 支持：
  - 查看总览
  - 转入持有录入
  - 从自选移除

#### `src/pages/HoldingsPage.tsx`
职责：
- 左侧/上方为持有录入表单
- 下方/右侧为持有表格
- 支持新增、编辑、删除持有记录
- 点击基金名可回到总览页查看详细走势

#### `src/components/FundSearchPanel.tsx`
职责：
- 顶部基金查询入口
- 输入 6 位基金编号触发查询
- 内置常用快捷基金代码

#### `src/components/FundSummaryCard.tsx`
职责：
- 总览页基金详情主卡
- 展示基金关键信息：最新净值、累计净值、估值、费率、申赎状态
- 关联当前持有信息与自选状态
- 提供动作：
  - 添加 / 移除自选
  - 录入 / 更新持有
- 下挂图表组件 `ChartPanel`
- 下挂近期业绩卡片、最近 30 条净值表格

#### `src/components/ChartPanel.tsx`
职责：
- 展示基金区间业绩图
- 支持时间范围切换：
  - `1M` / `3M` / `6M` / `1Y` / `YTD` / `ALL`
- 绘制多条技术指标线：
  - 单位净值
  - 成本线
  - MA5 / MA10 / MA20 / MA60
  - BOLL 上轨 / 下轨
- 图内交互：
  - 悬浮 tooltip 查看日期、净值、均线、布林带、成本偏离
  - 图层开关控制线条显隐
  - 图例同步控制显隐
  - 自动标记区间高点 / 低点
- 图下补充分析卡片：
  - 均线值
  - 相对成本线偏离
  - 相对 MA20 乖离率
  - 布林带宽
  - 20 日年化波动率
  - 区间最大回撤

#### `src/api/client.ts`
职责：
- 统一封装前端到服务端的请求
- 处理 JSON 解析与错误抛出
- 提供明确方法：
  - `getFundDetail`
  - `getWatchlist`
  - `addWatchlist`
  - `removeWatchlist`
  - `getHoldings`
  - `saveHolding`
  - `removeHolding`

#### `src/utils/fund.ts`
职责：
- 数值、净值、日期、涨跌幅格式化
- 曲线区间筛选
- 技术指标手动计算：
  - MA5 / MA10 / MA20 / MA60
  - 20 日布林带
  - 区间收益
  - 相对 MA20 / MA60 / 成本线偏离
  - 20 日年化波动率
  - 区间最大回撤

#### `src/types.ts`
职责：
- 统一前端业务类型
- 描述基金详情、趋势点、指标点、自选项、持有项、表单草稿等结构

---

### 3.2 服务端核心模块

#### `server/index.ts`
职责：
- 启动 Express 服务
- 提供基金查询、自选、持有相关 API
- 做请求校验与错误兜底
- 对自选 / 持有进行富化：把本地 JSON 中的 code 再补成完整基金详情
- 如果存在前端构建产物 `dist/`，同时支持静态托管

主要 API：
- `GET /api/health`
- `GET /api/funds/:code`
- `GET /api/watchlist`
- `POST /api/watchlist`
- `DELETE /api/watchlist/:code`
- `GET /api/compare`
- `POST /api/compare`
- `DELETE /api/compare/:code`
- `GET /api/holdings`
- `POST /api/holdings`
- `DELETE /api/holdings/:code`
- `GET /api/screener/options`
- `POST /api/screener/query`
- `GET /api/screener/sectors`
- `GET /api/screener/sectors/:sector/funds`
- `POST /api/screener/refresh`
- `GET /api/screener/presets`
- `POST /api/screener/presets`
- `DELETE /api/screener/presets/:id`

#### `server/fund-service.ts`
职责：
- 从公开页面接口抓取基金数据
- 清洗和聚合为统一响应结构
- 计算基础阶段收益：
  - 近 1 周
  - 近 1 月
  - 近 3 月
  - 近 6 月
  - 近 1 年
  - 年初至今
  - 成立以来
- 提供内存级缓存（TTL 2 分钟）减少重复请求

它负责聚合 3 类数据：
1. `pingzhongdata/{code}.js`：基金基础与净值趋势
2. `fundgz/{code}.js`：实时估值 JSONP
3. `f10/lsjz`：最近净值历史记录

#### `server/data-store.ts`
职责：
- 负责 `data/` 目录及 JSON 文件存在性检查
- 提供读写集合文件的方法
- 把 JSON 文件抽象成简易仓储层

#### `server/types.ts`
职责：
- 服务端类型定义
- 区分：
  - 基金详情结构
  - 原始持久化结构
  - 富化后的返回结构

---

## 4. 数据模型

### 4.1 自选数据
文件：`data/watchlist.json`

结构：
```json
{
  "items": [
    {
      "code": "270042",
      "addedAt": "2026-04-15T04:14:01.838Z"
    }
  ]
}
```

含义：
- `code`：基金编号
- `addedAt`：加入自选时间

服务端返回时会额外附加：
- `detail`：基金详情
- `error`：富化失败时的错误信息

### 4.2 持有数据
文件：`data/holdings.json`

结构：
```json
{
  "items": [
    {
      "code": "270042",
      "status": "持有中",
      "holdingReturnRate": 4.21,
      "positionAmount": 10297.2,
      "costNav": 7.0088,
      "note": "",
      "updatedAt": "2026-04-15T04:12:57.647Z"
    }
  ]
}
```

含义：
- `status`：持有状态，如持有中 / 观察仓 / 已止盈 / 已止损
- `holdingReturnRate`：手动填写的个人收益率
- `positionAmount`：持仓金额
- `costNav`：个人成本净值
- `note`：备注
- `updatedAt`：最近更新时间

服务端返回时同样会富化：
- `detail`
- `error`

---

## 5. 页面与交互逻辑

## 5.1 全局主线
整个管理台的主线其实很简单：

1. **查询一只基金**
2. **决定它进入自选还是持有**
3. **持续回看走势与自己的仓位信息**

这也是当前应用最核心的交互闭环。

---

## 5.2 基金查询流程
触发位置：顶部 `FundSearchPanel`

流程：
1. 用户输入 6 位基金编号
2. 触发 `onSearch`
3. `App.tsx` 调用 `getFundDetail(code)`
4. 请求 `GET /api/funds/:code`
5. 服务端聚合公开接口数据并返回标准结构
6. 前端将结果写入 `spotlight`
7. 自动跳转到 `/overview`
8. 总览页显示详情卡、走势图、业绩卡、净值表格

交互要点：
- 查询成功后自动切到总览页
- 查询失败时通过全局 toast 给出错误提示
- 当前聚焦基金名称和代码会同步显示在左侧侧栏

---

## 5.3 总览页逻辑
路由：`/overview`

### 空状态
- 当 `spotlight === null` 时
- 显示功能引导卡，而不是空白页

### 有基金数据时
展示内容：
- 基金主信息
- 估值 / 净值 / 费率 / 申赎状态
- 当前是否在自选
- 当前是否已有持有记录
- 区间走势图 + 技术指标
- 近期阶段收益
- 最近 30 条净值记录

### 总览页动作
- **添加到自选**
- **从自选移除**
- **录入到我的持有** 或 **更新持有信息**

如果当前基金已经存在于持有列表：
- 总览页会显示“我的持有”摘要区
- 图表会额外绘制该基金的**成本线**

---

## 5.4 我的自选页逻辑
路由：`/watchlist`

页面职责：
- 展示已加入观察池的基金
- 每条数据都尝试富化为带详情的卡片

单条卡片支持动作：
- **查看总览**：把该基金详情送回 `spotlight`，并跳转到 `/overview`
- **录入持有**：直接带 code 跳转到 `/holdings`，预填表单
- **移除**：删除本地 JSON 中对应记录

特殊逻辑：
- 如果服务端富化失败，不会整页报错
- 当前项会以 `detail = null` + `error` 的形式显示兜底文案

---

## 5.5 我的持有页逻辑
路由：`/holdings`

页面分成两块：

### A. 持有录入表单
支持维护字段：
- 基金编号
- 持有状态
- 手动收益率
- 持仓金额
- 成本净值
- 备注

表单逻辑：
- 点击总览页“录入到我的持有”时，会把 code 带进来
- 点击持有表格“编辑”时，会把当前记录回填到表单
- 提交后调用 `POST /api/holdings`
- 服务端按 code 去重后写入 JSON，并刷新列表
- 保存成功后表单清空

### B. 持有表格
展示字段：
- 基金名 / 编号
- 状态
- 手动收益率
- 持仓金额
- 成本净值
- 最新净值
- 近 1 月表现
- 备注
- 更新时间

操作：
- **点击基金名**：跳回总览页查看该基金详情
- **编辑**：回填表单
- **删除**：从 JSON 删除当前持有记录

---

## 6. 图表模块交互说明

图表是这个项目里最复杂、也最值钱的交互模块。

### 6.1 时间区间切换
支持：
- 近 1 月
- 近 3 月
- 近 6 月
- 近 1 年
- 年初至今
- 全部

切换逻辑：
1. 根据最新日期反推目标起点
2. 对完整趋势数据进行切片
3. 重新计算当前视图下的：
   - 区间收益
   - 均线值
   - 布林带
   - 波动率
   - 最大回撤
   - 高低点标记

也就是说，指标是**基于当前展示区间重新判断**，不是死拿全量结果。

### 6.2 图层开关
当前支持显隐控制：
- 单位净值
- 成本线
- MA5
- MA10
- MA20
- MA60
- BOLL 上轨
- BOLL 下轨

交互逻辑：
- 顶部开关按钮与图例选择状态联动
- 如果当前没有成本净值，则不显示“成本线”开关
- 成本净值一旦存在，会自动允许成本线展示

### 6.3 悬浮提示
tooltip 展示内容包括：
- 横轴：日期
- 纵轴：单位净值
- MA5 / MA10 / MA20 / MA60
- BOLL 上轨 / 下轨
- 成本线（若存在）
- 区间涨跌
- 相对 MA20
- 相对成本

### 6.4 自动标记
单位净值主线会自动标记：
- 区间高点
- 区间低点

### 6.5 指标卡片
图下方会展示一组摘要卡：
- 5 / 10 / 20 / 60 日均线
- 相对成本线偏离
- 相对 MA20 乖离率
- 20 日布林带宽
- 20 日年化波动率
- 区间最大回撤

---

## 7. 前后端数据流

## 7.1 查询基金详情的数据流
```text
用户输入基金编号
  -> FundSearchPanel
  -> App.handleSearch
  -> src/api/client.getFundDetail
  -> GET /api/funds/:code
  -> server/fund-service 聚合公开接口
  -> 返回 FundDetailResponse
  -> App.setSpotlight
  -> OverviewPage / FundSummaryCard / ChartPanel 渲染
```

## 7.2 自选数据流
```text
点击“添加到我的自选”
  -> App.handleAddWatchlist
  -> POST /api/watchlist
  -> server/index.ts 校验 code
  -> data-store 写入 data/watchlist.json
  -> App.reloadWatchlist
  -> GET /api/watchlist
  -> 服务端富化 detail
  -> WatchlistPage 列表更新
```

## 7.3 持有数据流
```text
点击“录入到我的持有”或在持有页提交表单
  -> App.prepareHolding / HoldingsPage.submit
  -> App.handleSaveHolding
  -> POST /api/holdings
  -> server/index.ts 归一化并按 code 去重写入
  -> data-store 写入 data/holdings.json
  -> App.reloadHoldings
  -> GET /api/holdings
  -> 服务端富化 detail
  -> HoldingsPage 表格更新
  -> OverviewPage 若当前聚焦同 code，则自动获得 holding 信息
  -> ChartPanel 绘制成本线
```

---

## 8. API 说明

### `GET /api/funds/:code`
用途：查询单只基金完整详情

返回核心字段：
- `fund`
- `performance`
- `navHistory`
- `trend`

### `GET /api/watchlist`
用途：获取自选列表（已富化）

### `POST /api/watchlist`
用途：新增自选

请求体：
```json
{ "code": "270042" }
```

### `DELETE /api/watchlist/:code`
用途：移除自选

### `GET /api/holdings`
用途：获取持有列表（已富化）

### `POST /api/holdings`
用途：新增或更新持有记录

请求体示例：
```json
{
  "code": "270042",
  "status": "持有中",
  "holdingReturnRate": 4.21,
  "positionAmount": 10297.2,
  "costNav": 7.0088,
  "note": "长期观察仓"
}
```

### `DELETE /api/holdings/:code`
用途：删除持有记录

---

## 9. 当前项目的设计取舍

### 9.1 为什么没有数据库
这是一个偏个人使用的本地工作台，当前阶段：
- 数据量小
- 部署目标简单
- 可迁移性高
- 调试成本低

所以 JSON 持久化比上数据库更划算。

### 9.2 为什么技术指标在前端计算
因为：
- 趋势数据已经在基金详情响应里返回
- 技术指标更多是展示层逻辑
- 区间切换需要即时重算
- 放前端能减少服务端复杂度

### 9.3 为什么自选和持有在服务端做富化
因为前端真正需要的是“可展示列表”，不是孤零零一个 code。
把富化放在服务端有两个好处：
- 前端不需要自己再串行请求多次
- 自选页、持有页能直接消费统一结构

---

## 10. 后续扩展建议

当前结构已经能继续迭代，比较自然的扩展方向有：

### 10.1 列表增强
- 我的自选 / 我的持有支持排序、筛选、搜索
- 标签系统（红利、医疗、白酒、定投等）

### 10.2 图表增强
- 成本线上下方区间着色
- 布林带中轨显式展示
- 更多指标：MACD、RSI、成交额相关代理指标（如果数据源可拿到）
- 多基金同图区间对比

### 10.3 持有分析增强
- 根据成本净值和持仓金额自动推导浮盈浮亏金额
- 统计总持仓、总收益、仓位分布

### 10.4 数据层增强
- 本地缓存基金详情快照
- 失败重试
- 后续如果记录量增大，再考虑 SQLite

---

## 11. 一句话总结

这个项目目前已经形成了比较清晰的三层结构：

- **前端负责页面、交互和技术指标展示**
- **服务端负责基金数据聚合、自选/持有 API 与本地持久化**
- **JSON 文件负责低成本保存个人数据**

主交互闭环也很明确：

> 查询基金 -> 看总览 -> 加入自选或录入持有 -> 持续回看走势和自己的仓位信息

这套结构对当前阶段是够用而且好改的，不花哨，但挺能打。
