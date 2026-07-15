# 项目工作约定

## 记录位置约定（由 Monody 在 2026-07-15 确认）

- **项目专属记录**全部写到 `~/Desktop/py/.codebuddy/`，跟着 git 提交
  - `memory/YYYY-MM-DD.md`：每日追加型工作日志
  - `design/NN-xxx.md`：每完成一个阶段后沉淀一份设计文档
  - `README.md` / `CONVENTIONS.md`：目录说明和工作约定
- **不再往**全局 `~/WorkBuddy/.../memory/` 写 quant_system 相关内容
- **跨项目稳定偏好**（编码风格、通用工具喜好）仍走全局 `MEMORY.md`

## 每次交付节奏

1. 先出设计和范围，等 Monody 确认再动手
2. 每完成一个阶段（第 N 步），回复固定四段：
   - 当前已经具备哪些能力
   - 可以执行哪些命令进行验证
   - 数据库增加了哪些表 / 表变化
   - 有没有可以直接查看的结果（SQL / CLI / md / html）
3. 阶段结束后把关键决策沉淀到 `design/NN-xxx.md`
4. 追加当日进展到 `memory/YYYY-MM-DD.md`

## 优先级

**跑通链路 > 架构美感**。update → feature → strategy → score → report → backtest 这条链路优先。

**不做未来才用的实现**：ML / 向量 / LLM 保留字段/接口预留即可。

## 技术栈锁定

- Python 3.11（不因兼容问题升级）
- 指标手写，不引 TA-Lib / pandas-ta
- SQLite + SQLAlchemy 2.0（ORM 数据库中立，可切 PG）
- akshare（A 股主板为主）
