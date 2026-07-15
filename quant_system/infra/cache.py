"""统一缓存层。

设计目标：
- **Provider 层禁止自行实现缓存**，所有 akshare / QMT / tushare 调用统一走这里；
- 分层策略：历史数据永久 / 近 30 日 TTL=1h / 当日快照不缓存；
- 支持 force_refresh 参数跳过缓存重新拉；
- 未来替换 Redis：只需实现同一套 CacheBackend Protocol。

使用方式（Provider 内部）：
    from quant_system.infra.cache import cached_call, CachePolicy

    def fetch_kline(code, start, end):
        return cached_call(
            key_parts=("akshare.kline", code, start, end),
            fn=lambda: _raw_ak_call(code, start, end),
            policy=CachePolicy.for_kline_range(end),
            force_refresh=False,
        )
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from diskcache import Cache
from loguru import logger

from quant_system.config.settings import get_settings

# ============================================================================
# Cache Backend Protocol（便于未来接 Redis / Memcached）
# ============================================================================

class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> bool: ...
    def clear(self) -> int: ...


class DiskCacheBackend:
    """基于 diskcache 的本地磁盘实现。"""

    def __init__(self, namespace: str) -> None:
        base = Path(get_settings().data.cache_dir)
        base.mkdir(parents=True, exist_ok=True)
        self._cache = Cache(directory=str(base / namespace))
        self._namespace = namespace

    def get(self, key: str) -> Any | None:
        return self._cache.get(key, default=None)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._cache.set(key, value, expire=ttl)

    def delete(self, key: str) -> bool:
        return bool(self._cache.delete(key))

    def clear(self) -> int:
        return int(self._cache.clear())

    def stats(self) -> dict[str, int]:
        return {"count": len(self._cache), "volume_bytes": self._cache.volume()}


_backends: dict[str, CacheBackend] = {}


def get_backend(namespace: str = "default") -> CacheBackend:
    if namespace not in _backends:
        _backends[namespace] = DiskCacheBackend(namespace)
    return _backends[namespace]


# ============================================================================
# 缓存策略（分层）
# ============================================================================

# 近 N 交易日以内的数据用短 TTL（数据源可能回溯修正）
RECENT_WINDOW_DAYS = 30
RECENT_TTL_SECONDS = 3600           # 1 小时
HISTORICAL_TTL_SECONDS: int | None = None  # 永久


@dataclass(frozen=True)
class CachePolicy:
    """缓存策略。ttl=None 表示永久；ttl=0 表示不缓存。"""
    ttl: int | None
    enabled: bool = True

    @classmethod
    def historical(cls) -> "CachePolicy":
        """历史数据：永久缓存。"""
        return cls(ttl=HISTORICAL_TTL_SECONDS, enabled=True)

    @classmethod
    def recent(cls) -> "CachePolicy":
        """近 30 交易日：短 TTL。"""
        return cls(ttl=RECENT_TTL_SECONDS, enabled=True)

    @classmethod
    def realtime(cls) -> "CachePolicy":
        """当日快照：不缓存。"""
        return cls(ttl=0, enabled=False)

    @classmethod
    def for_date(cls, target_date: date, today: date | None = None) -> "CachePolicy":
        """按日期自动选择策略。

        规则：
        - target_date == today → realtime（不缓存）
        - today - target_date < 30 → recent
        - 否则 → historical
        """
        today = today or date.today()
        if target_date >= today:
            return cls.realtime()
        if (today - target_date).days < RECENT_WINDOW_DAYS:
            return cls.recent()
        return cls.historical()

    @classmethod
    def for_kline_range(cls, end_date: date, today: date | None = None) -> "CachePolicy":
        """按 K 线区间的结束日期选择。区间末端近 30 日以内 → 短 TTL。"""
        return cls.for_date(end_date, today)


# ============================================================================
# 统一调用入口
# ============================================================================

def _make_key(key_parts: tuple[Any, ...]) -> str:
    """把任意参数拼成稳定的 hash key。"""
    payload = "|".join(str(p) for p in key_parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_call(
    key_parts: tuple[Any, ...],
    fn: Callable[[], Any],
    policy: CachePolicy | None = None,
    namespace: str = "akshare",
    force_refresh: bool = False,
) -> Any:
    """统一缓存调用入口。所有 Provider 都必须通过它访问外部数据源。

    Args:
        key_parts: 组成缓存 key 的元组，如 ("akshare.kline", "000001.SZ", "2015-01-01", "2026-07-15")。
        fn: 无参回调，真正执行数据拉取。
        policy: 缓存策略；None 时默认 historical。
        namespace: 缓存子目录（"akshare" / "tushare" / "qmt"）。
        force_refresh: True 时跳过缓存重新拉取，并覆盖缓存。
    """
    policy = policy or CachePolicy.historical()
    key = _make_key(key_parts)

    if not policy.enabled:
        # 实时数据：不查也不写缓存
        return fn()

    backend = get_backend(namespace)

    if not force_refresh:
        hit = backend.get(key)
        if hit is not None:
            logger.trace("cache HIT: {} key={}", key_parts[0] if key_parts else "?", key[:8])
            return hit

    logger.trace("cache MISS: {} key={}", key_parts[0] if key_parts else "?", key[:8])
    result = fn()
    if result is not None:
        backend.set(key, result, ttl=policy.ttl)
    return result


# ============================================================================
# 管理接口（CLI cache clear/rebuild 用）
# ============================================================================

def clear_namespace(namespace: str | None = None) -> dict[str, int]:
    """清空缓存。namespace=None 清全部已知 namespace。"""
    if namespace is None:
        stats: dict[str, int] = {}
        # 扫描 cache_dir 下所有子目录
        base = Path(get_settings().data.cache_dir)
        if base.exists():
            for sub in base.iterdir():
                if sub.is_dir():
                    stats[sub.name] = get_backend(sub.name).clear()
        return stats
    return {namespace: get_backend(namespace).clear()}


def cache_stats() -> dict[str, dict[str, int]]:
    """返回各 namespace 的缓存条数和体积。"""
    base = Path(get_settings().data.cache_dir)
    result: dict[str, dict[str, int]] = {}
    if base.exists():
        for sub in base.iterdir():
            if sub.is_dir():
                backend = get_backend(sub.name)
                if isinstance(backend, DiskCacheBackend):
                    result[sub.name] = backend.stats()
    return result


# ============================================================================
# 兼容旧接口（保留 disk_cache 装饰器给非 Provider 场景用，比如 trading_calendar）
# ============================================================================

import functools  # noqa: E402


def disk_cache(
    ttl: int | None = None,
    namespace: str = "default",
    enabled: bool = True,
) -> Callable:
    """简化装饰器版本。**不建议在 provider 里用**，provider 请用 cached_call。"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not enabled:
                return func(*args, **kwargs)
            return cached_call(
                key_parts=(func.__module__, func.__qualname__, args, tuple(sorted(kwargs.items()))),
                fn=lambda: func(*args, **kwargs),
                policy=CachePolicy(ttl=ttl, enabled=True),
                namespace=namespace,
            )
        return wrapper
    return decorator


def clear_cache(namespace: str | None = None) -> int:
    """兼容旧 API。"""
    stats = clear_namespace(namespace)
    return sum(stats.values())
