"""独立初始化脚本。等价于 `qs init-db`。"""
from __future__ import annotations

import sys


def main() -> None:
    from quant_system.database.migrations import (
        check_schema_integrity,
        init_db,
    )
    from quant_system.infra.logger import setup_logging

    setup_logging()

    drop_first = "--drop-first" in sys.argv
    init_db(drop_first=drop_first)

    ok, missing = check_schema_integrity()
    if not ok:
        print(f"缺失表: {missing}", file=sys.stderr)
        sys.exit(1)
    print("数据库初始化完成，22 张表齐全")


if __name__ == "__main__":
    main()
