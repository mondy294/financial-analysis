"""代码目录指纹（用于回测复现）。

算法：
1. 递归遍历目标目录下匹配 glob_pattern 的所有文件；
2. 按相对路径升序排序；
3. 对每个文件：`{相对路径}:{文件内容 SHA256}\n` 拼接；
4. 对拼接结果再取一次 SHA256，取前 40 位作为最终指纹。

任何文件的任何字符变更都会导致最终 hash 变化。
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def hash_directory(target: Path, glob_pattern: str = "*.py") -> str:
    """通用目录 SHA256 指纹。返回 40 位 hex。"""
    target = Path(target)
    if not target.exists() or not target.is_dir():
        raise ValueError(f"目录不存在或不是目录: {target}")

    files = sorted(
        (p for p in target.rglob(glob_pattern) if p.is_file()),
        key=lambda p: str(p.relative_to(target)),
    )
    if not files:
        # 空目录也要给个稳定 hash，避免 None
        return hashlib.sha256(b"__empty__").hexdigest()[:40]

    aggregator = hashlib.sha256()
    for f in files:
        rel = str(f.relative_to(target)).replace("\\", "/")
        content = f.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        aggregator.update(f"{rel}:{file_hash}\n".encode("utf-8"))
    return aggregator.hexdigest()[:40]


def hash_strategy_dir(strategy_dir: Path | None = None) -> str:
    """策略目录指纹。默认使用 quant_system/strategy/。"""
    if strategy_dir is None:
        strategy_dir = Path(__file__).resolve().parent.parent / "strategy"
    return hash_directory(strategy_dir, "*.py")
