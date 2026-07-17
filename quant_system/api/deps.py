from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from quant_system.data.repository import Repositories, build_repositories
from quant_system.infra.db import get_session_factory


def get_db_session() -> Generator[Session, None, None]:
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


def get_repos(session: Session = Depends(get_db_session)) -> Repositories:
    return build_repositories(session)
