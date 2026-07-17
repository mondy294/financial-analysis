# 16 · Series Transformation Pipeline（已收编为 v3 一章）

> 状态：⚠️ **v2 不再作为顶层叙事**  
> 正式文档请阅读：**[16-market-representation.md](./16-market-representation.md)**（Market Representation Framework v3）

v2 把 Pipeline + Common Factor Removal 抬了上来，但仍有偏差：

- Pipeline 被写成 Similarity 前置，而非全系统中台  
- CFR 仍偏 Selection+Regression  
- Catalog 偏 Factor，Exposure 偏 β  
- Graph 仍像唯一关系形态  

上述能力在 v3 中分别升格为：公共 Pipeline（DAG）、CommonComponentExtractor、DataCatalog、RepresentationBundle、Relationship + Fusion。  
细节以 v3 为准；本文件仅保留跳转。
