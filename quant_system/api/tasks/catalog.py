"""可从前端触发的批处理任务目录。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParamType = Literal["date", "bool", "string", "int", "float", "codes"]


@dataclass(frozen=True)
class TaskParam:
    name: str
    type: ParamType
    label: str
    required: bool = False
    default: Any = None
    help: str = ""


@dataclass(frozen=True)
class TaskSpec:
    id: str
    group: str
    label: str
    description: str
    heavy: bool = True
    dangerous: bool = False
    params: tuple[TaskParam, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group": self.group,
            "label": self.label,
            "description": self.description,
            "heavy": self.heavy,
            "dangerous": self.dangerous,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "label": p.label,
                    "required": p.required,
                    "default": p.default,
                    "help": p.help,
                }
                for p in self.params
            ],
        }


_DATE = TaskParam("trade_date", "date", "交易日", help="默认最近交易日")
_FULL = TaskParam("full", "bool", "全量", default=False, help="从起始日全量拉取")
_POOL = TaskParam("pool", "string", "股票池", help="如 HS300 / ALL，空=配置默认")
_CODES = TaskParam("codes", "codes", "股票代码", help="逗号分隔，可选")
_FORCE = TaskParam("force", "bool", "强制", default=False)
_DRY = TaskParam("dry_run", "bool", "Dry-run", default=False)


TASK_CATALOG: dict[str, TaskSpec] = {
    # ---- 数据更新 ----
    "update.all": TaskSpec(
        id="update.all",
        group="data",
        label="更新全部数据",
        description="basic → pool → kline → financial → valuation → market",
        params=(_DATE, _FULL),
    ),
    "update.stock_basic": TaskSpec(
        id="update.stock_basic",
        group="data",
        label="更新股票基础信息",
        description="stock_basic",
        params=(_DATE, _FULL),
    ),
    "update.stock_pool": TaskSpec(
        id="update.stock_pool",
        group="data",
        label="更新股票池",
        description="股票池成分",
        params=(_DATE, _FULL, _POOL),
    ),
    "update.kline": TaskSpec(
        id="update.kline",
        group="data",
        label="更新日 K 线",
        description="daily_kline 增量/全量",
        params=(_DATE, _FULL, _POOL, _CODES, _DRY),
    ),
    "update.financial": TaskSpec(
        id="update.financial",
        group="data",
        label="更新财务快照",
        description="financial_snapshot",
        params=(_DATE, _FULL, _POOL, _CODES),
    ),
    "update.valuation": TaskSpec(
        id="update.valuation",
        group="data",
        label="更新日频估值",
        description="daily_valuation（PE/PB/市值）",
        params=(_DATE, _FULL, _POOL, _CODES),
    ),
    "update.market": TaskSpec(
        id="update.market",
        group="data",
        label="更新市场/指数",
        description="指数日线 + 市场情绪",
        params=(
            _DATE,
            _FULL,
            TaskParam("backfill", "bool", "回填历史", default=False),
        ),
    ),
    # ---- 分析流水线 ----
    "feature": TaskSpec(
        id="feature",
        group="pipeline",
        label="计算特征",
        description="重算 daily_feature",
        params=(_DATE, _POOL, _CODES),
    ),
    "quality": TaskSpec(
        id="quality",
        group="pipeline",
        label="数据质量检查",
        description="写入 data_quality_check",
        params=(_DATE,),
    ),
    "select": TaskSpec(
        id="select",
        group="pipeline",
        label="跑选股",
        description="策略评分 → strategy_signal",
        params=(
            _DATE,
            TaskParam("top_n", "int", "Top N", help="可选，覆盖默认"),
        ),
    ),
    "report": TaskSpec(
        id="report",
        group="pipeline",
        label="生成日报",
        description="若无 select 会先跑选股再出报告",
        params=(_DATE,),
    ),
    "pipeline": TaskSpec(
        id="pipeline",
        group="pipeline",
        label="端到端流水线",
        description="update → feature → quality → select → report",
        params=(
            _DATE,
            TaskParam("skip_update", "bool", "跳过更新", default=False),
        ),
    ),
    # ---- Pattern & 关系 ----
    "pattern.scan": TaskSpec(
        id="pattern.scan",
        group="analysis",
        label="Pattern 正式扫描",
        description="仅 published Definition；写入 abnormal_signal",
        params=(
            _DATE,
            TaskParam("pattern_ids", "codes", "Pattern IDs", help="逗号分隔，空=全部已发布"),
            _FORCE,
        ),
    ),
    "similarity.refresh": TaskSpec(
        id="similarity.refresh",
        group="analysis",
        label="刷新相似度+聚类",
        description="Pearson 边落库后默认对 W60/W250 聚类（一次完成）",
        params=(
            _DATE,
            TaskParam("windows", "string", "窗口", default="60,250", help="如 60,250"),
            _POOL,
            TaskParam("threshold", "float", "边阈值", default=0.3),
            TaskParam("min_sample", "int", "最小样本", default=120),
            TaskParam("max_neighbors", "int", "最大邻居", default=200),
            TaskParam("with_cluster", "bool", "同时聚类", default=True),
            TaskParam("cluster_w_min", "float", "聚类边权门槛", default=0.45),
            TaskParam("cluster_conf_min", "float", "聚类置信门槛", default=0.5),
            TaskParam(
                "pipeline_recipe",
                "string",
                "Pipeline 配方",
                default="return_cfr_auto_v1",
                help="return_cfr_auto_v1=残差相关；return_raw_v1=毛收益对照",
            ),
            _DRY,
            _FORCE,
        ),
    ),
    "relationship.build": TaskSpec(
        id="relationship.build",
        group="analysis",
        label="构建股票关系（兼容）",
        description="等价于 similarity.refresh（默认带聚类）",
        params=(
            _DATE,
            TaskParam("windows", "string", "窗口", default="60,250", help="如 60,250"),
            _POOL,
            TaskParam("threshold", "float", "阈值", default=0.3),
            TaskParam("min_sample", "int", "最小样本", default=120),
            TaskParam("max_neighbors", "int", "最大邻居", default=200),
            TaskParam("with_cluster", "bool", "同时聚类", default=True),
            _DRY,
            _FORCE,
        ),
    ),
    "cluster.build": TaskSpec(
        id="cluster.build",
        group="analysis",
        label="仅重建聚类",
        description="使用已有相似度边重新聚类（不重算边）",
        params=(
            TaskParam("profile_id", "string", "Profile", default="pearson_w60"),
            TaskParam("window", "string", "窗口", default="W60"),
            TaskParam("cluster_w_min", "float", "边权门槛", default=0.45),
            TaskParam("cluster_conf_min", "float", "置信门槛", default=0.5),
        ),
    ),
    # ---- 运维 ----
    "cache.clear": TaskSpec(
        id="cache.clear",
        group="ops",
        label="清空缓存",
        description="清空 diskcache；可指定 namespace",
        heavy=False,
        params=(TaskParam("namespace", "string", "Namespace", help="空=全部"),),
    ),
    "cache.rebuild": TaskSpec(
        id="cache.rebuild",
        group="ops",
        label="重建交易日历缓存",
        description="清空缓存并 refresh 交易日历",
        heavy=False,
    ),
    "init_db": TaskSpec(
        id="init_db",
        group="ops",
        label="初始化数据库",
        description="建表 + 种子数据；危险操作请确认",
        heavy=True,
        dangerous=True,
        params=(
            TaskParam(
                "drop_first",
                "bool",
                "先删表",
                default=False,
                help="会清空全部数据，默认关闭",
            ),
        ),
    ),
}

GROUP_ORDER = ("data", "pipeline", "analysis", "ops")
GROUP_LABELS = {
    "data": "数据更新",
    "pipeline": "分析流水线",
    "analysis": "Pattern / 关系",
    "ops": "运维",
}


def get_task(task_id: str) -> TaskSpec | None:
    return TASK_CATALOG.get(task_id)


def list_tasks() -> list[dict[str, Any]]:
    items = [TASK_CATALOG[k].to_dict() for k in TASK_CATALOG]
    items.sort(key=lambda x: (GROUP_ORDER.index(x["group"]) if x["group"] in GROUP_ORDER else 99, x["id"]))
    return items


def list_tasks_grouped() -> list[dict[str, Any]]:
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    for item in list_tasks():
        by_group.setdefault(item["group"], []).append(item)
    return [
        {"group": g, "label": GROUP_LABELS.get(g, g), "tasks": by_group.get(g, [])}
        for g in GROUP_ORDER
        if by_group.get(g)
    ]
