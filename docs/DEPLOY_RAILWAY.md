# Railway 部署说明

## 1. 部署方式

本项目按单服务部署：

- 前端：Vite 构建到 `dist`
- 后端：Node/Express 从 `dist-server/index.js` 启动

Railway 已通过 `railway.json` 配置：

- Build Command：`npm run build`
- Start Command：`npm run start`
- Health Check：`/api/health`

## 2. 必配环境变量

在 Railway 项目里至少配置：

- `DEEPSEEK_API_KEY`：默认模型接口 Key
- `DEEPSEEK_BASE_URL`：默认模型接口地址，可选，默认 `https://api.deepseek.com`
- `DEEPSEEK_MODEL`：默认模型名，可选，默认 `deepseek-reasoner`
- `DATA_DIR`：建议设置为 `/app/data`

可选：

- `ENABLE_MCP=false`
  - Railway 上建议默认关闭内置 MCP HTTP 服务
  - 若你确实需要容器内单独跑 MCP，再显式设为 `true`
- `MCP_HOST=127.0.0.1`
- `MCP_PORT=9090`

## 3. 持久化卷

本项目会把以下数据写入本地文件：

- 自选列表
- 持有列表
- 对比列表
- Agent 分析缓存
- Screener 缓存
- 模型设置页保存的 URL / API Key

所以必须在 Railway 给服务挂一个 Persistent Volume。

建议：

1. 新建 Volume
2. Mount Path 填：`/app/data`
3. 同时把环境变量 `DATA_DIR` 设置成：`/app/data`

这样服务重启或重新部署后，数据仍然保留。

## 4. 部署步骤

1. 把仓库推到 GitHub
2. 在 Railway 新建项目并连接仓库
3. 确认项目根目录是仓库根目录
4. 添加上面的环境变量
5. 创建并挂载 Persistent Volume 到 `/app/data`
6. 触发部署

## 5. 验证

部署完成后，先检查：

- `GET /api/health` 返回 `{ "ok": true }`
- 首页能正常打开
- “模型设置”页能保存接口 URL 和 API Key
- 自选/持有新增后，重新部署数据不丢
- 基金 AI 分析可以正常返回

## 6. 说明

- 生产环境下，前端静态资源由 Express 直接托管
- 若未设置 `ENABLE_MCP=true`，部署后不会额外启动 MCP HTTP 服务
- 模型设置页保存的自定义 URL / API Key 优先级高于 `.env` 默认值
