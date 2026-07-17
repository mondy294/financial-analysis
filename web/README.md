# quant_system Web Console

## 开发（推荐：前后端热重载）

```bash
# 项目根目录
qs serve --dev
```

- 后端：`http://127.0.0.1:8000`（改 `quant_system/**/*.py` 自动重启）
- 前端：`http://127.0.0.1:5173`（Vite HMR，**开发请打开这个地址**）

等价拆分启动：

```bash
qs serve --reload --port 8000          # 终端 1
cd web && npm run dev                  # 终端 2
```

## 生产静态挂载

```bash
cd web && npm run build
qs serve --port 8000                   # 无 HMR，挂载 web/dist
```
