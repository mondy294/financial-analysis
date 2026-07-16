"""股票关系层（Relationship Layer）。

L4 应用层：依赖 L1 repository + L0 infra，不被数据层反向依赖。

- returns_matrix：收益率宽表构建 + 停牌/上市对齐 + parquet 缓存
- calculator：纯函数关系算法（BaseCalculator + PearsonCalculator），无 DB/IO
- service：编排（宇宙解析 → 算 → 组装 → 写 + run 记录 + dry-run）
- queries：查询封装，供 report / ai / cli 复用
"""
