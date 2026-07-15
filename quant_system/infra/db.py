"""数据库引擎与会话管理。

设计要点：
1. Engine 全局单例（一进程一个）；
2. sessionmaker 每次 begin() 出新 Session，事务边界清晰；
3. SQLite 的 PRAGMA 仅在 dialect=sqlite 时通过 connect 事件生效（数据库中立 R8）；
4. 不承担 ORM 定义（在 database/models.py）和读写逻辑（在 data/repository.py）。
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from quant_system.config.settings import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _configure_sqlite_pragmas(engine: Engine) -> None:
    """注册 connect 事件，SQLite 特化 PRAGMA。"""
    cfg = get_settings().database

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute(f"PRAGMA journal_mode = {cfg.sqlite_journal_mode}")
            cursor.execute(f"PRAGMA synchronous = {cfg.sqlite_synchronous}")
            cursor.execute(f"PRAGMA cache_size = -{cfg.sqlite_cache_size_kb}")
            cursor.execute(f"PRAGMA mmap_size = {cfg.sqlite_mmap_size_bytes}")
            cursor.execute("PRAGMA temp_store = MEMORY")
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite 文件路径的父目录自动创建。"""
    parsed = urlparse(url)
    if parsed.scheme.startswith("sqlite") and parsed.path:
        # sqlite:///./path/to.db → parsed.path 为 "/./path/to.db"，需去掉首字符
        raw = parsed.path.lstrip("/") if parsed.path.startswith("/./") else parsed.path
        db_path = Path(raw).resolve() if raw not in (":memory:", "") else None
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    """返回全局单例 Engine。"""
    global _engine, _SessionFactory
    if _engine is not None:
        return _engine

    cfg = get_settings().database
    _ensure_sqlite_dir(cfg.url)

    # SQLite 的 QueuePool 不适合多线程，用 default（NullPool）或 StaticPool
    connect_args: dict = {}
    engine_kwargs: dict = {"echo": cfg.echo_sql, "future": True}
    if cfg.url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
    else:
        engine_kwargs["pool_size"] = cfg.pool_size
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(cfg.url, **engine_kwargs)

    if engine.dialect.name == "sqlite":
        _configure_sqlite_pragmas(engine)

    _engine = engine
    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    logger.debug("db engine created: dialect={} url={}", engine.dialect.name, cfg.url)
    return engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        get_engine()  # 副作用：初始化 factory
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """事务作用域上下文管理器。

    用法：
        with session_scope() as session:
            session.add(obj)
            # 自动 commit；异常自动 rollback
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """关闭 engine（测试用 / 应用退出用）。"""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
