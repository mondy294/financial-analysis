"""常驻调度器入口。

用法：
    python -m quant_system.main
或（安装包后）：
    qs schedule

行为：
1. 加载配置 + 初始化日志；
2. 注册 APScheduler 任务（在 scheduler/jobs.py 定义）；
3. 前台阻塞运行；
4. Ctrl+C 优雅退出。
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
