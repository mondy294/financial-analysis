# .codebuddy/

quant_system 项目的**设计沉淀与工作 memory**。所有由 AI 助手（砚）产出的设计方案、决策记录和日常笔记都存这里，跟着代码一起版本管理。

## 目录结构

```
.codebuddy/
├── README.md                 你正在看的这份
├── memory/
│   └── YYYY-MM-DD.md         每日工作日志（追加型，不覆盖）
└── design/
    ├── 00-index.md           设计索引（每完成一个阶段更新）
    ├── 01-architecture.md    整体架构（分层 / 依赖流向 / 扩展点）
    ├── 02-database-v1.md     数据库设计 v1（22 张表初版）
    ├── 03-database-v2.md     数据库设计 v2（含 signal_type / backtest_task 等修订）
    ├── 04-skeleton.md        项目骨架 + 依赖 + 配置
    ├── 05-data-layer.md      数据层：Provider / Repository / DataUpdate / DI
    └── 06-feature-quality.md 特征计算 + 数据质量 + 板块过滤
```

## 使用约定

1. **每个阶段完成后**，把当轮的关键决策沉淀成 `design/NN-xxx.md`，避免下次翻聊天记录。
2. **日常笔记**追加到 `memory/YYYY-MM-DD.md`，简短、可长期查阅。
3. **跨项目的稳定偏好**（如个人编码风格、通用工具喜好）仍写到全局 `~/WorkBuddy/.../MEMORY.md`；本项目专属的东西全在这里。
4. 这个目录会跟着 git 提交，**不要放密钥、token 或敏感数据**。

## 快速跳转

- 想看整体设计逻辑 → [design/01-architecture.md](./design/01-architecture.md)
- 想看数据库为什么长这样 → [design/03-database-v2.md](./design/03-database-v2.md)
- 想看今天做了什么 → [memory/](./memory/) 里最新一份
