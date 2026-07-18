from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
import time
from typing import Any, Callable

from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from quant_system.config.settings import get_settings
from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.matcher import GenericPatternMatcher
from quant_system.patterns.result import PatternMatchResult, PatternRunResult

ProgressCb = Callable[[float, str], None]  # fraction in [0,1] relative to this run, message


@dataclass
class PatternRunner:
    matcher: GenericPatternMatcher | None = None
    keep_unmatched: bool = False
    show_progress: bool = True
    concurrency: int | None = None
    # API/Job 用：按完成比例回调（与 rich 终端条并行可选）
    progress_cb: ProgressCb | None = None

    def __post_init__(self) -> None:
        if self.matcher is None:
            self.matcher = GenericPatternMatcher()
        if self.concurrency is None:
            self.concurrency = max(1, int(get_settings().pattern.concurrency))

    def run(
        self,
        definition: PatternDefinition,
        trade_date: date,
        context: dict[str, Any],
    ) -> PatternRunResult:
        assert self.matcher is not None
        kline_by_code = context.get("kline_by_code") or {}
        stock_meta = context.get("stock_meta") or {}
        amount_by_code = context.get("amount_by_code") or {}
        name_map = {
            code: str((stock_meta.get(code) or {}).get("name") or "")
            for code in kline_by_code
        }

        codes = list(kline_by_code.keys())
        total = len(codes)
        workers = max(1, int(self.concurrency or 1))
        results: list[PatternMatchResult] = []
        matched_count = 0

        def _match_one(code: str) -> PatternMatchResult:
            assert self.matcher is not None
            return self.matcher.match(
                code,
                trade_date,
                kline_by_code[code],
                definition,
                meta=stock_meta.get(code, {}),
                last_amount=amount_by_code.get(code),
            )

        def _collect(result: PatternMatchResult) -> None:
            nonlocal matched_count
            if result.matched:
                matched_count += 1
            if result.matched or self.keep_unmatched:
                results.append(result)

        last_cb_at = 0.0
        last_cb_done = -1

        def _emit_cb(done: int) -> None:
            nonlocal last_cb_at, last_cb_done
            if self.progress_cb is None or total <= 0:
                return
            now = time.monotonic()
            # 节流：至少隔 200ms，或每 1%/50 只，或完成时
            frac = done / total
            if (
                done < total
                and done != total
                and done - last_cb_done < max(1, total // 100)
                and done - last_cb_done < 50
                and now - last_cb_at < 0.2
            ):
                return
            last_cb_at = now
            last_cb_done = done
            label = definition.display_name or definition.id
            self.progress_cb(
                frac,
                f"{label} {done}/{total} hit={matched_count}",
            )

        if self.show_progress and total > 0:
            label = definition.display_name or definition.id
            progress = Progress(
                TextColumn(f"[bold blue]{label}[/]"),
                BarColumn(bar_width=30),
                TextColumn("[bold]{task.fields[idx]:>4}/{task.total}[/]"),
                TextColumn("[cyan]{task.fields[cur]:<18}[/]"),
                TextColumn("[green]hit={task.fields[hit]}[/]"),
                TextColumn(f"[dim]x{workers}[/]"),
                TimeElapsedColumn(),
                TextColumn("<"),
                TimeRemainingColumn(),
                refresh_per_second=8,
                transient=False,
            )
            with progress:
                task_id = progress.add_task(
                    "scan",
                    total=total,
                    idx=0,
                    cur="-",
                    hit=0,
                )
                done = 0
                if workers <= 1:
                    for code in codes:
                        result = _match_one(code)
                        _collect(result)
                        done += 1
                        cur = f"{code} {name_map.get(code, '')}".strip()
                        progress.update(
                            task_id, completed=done, idx=done, cur=cur[:18], hit=matched_count,
                        )
                        _emit_cb(done)
                else:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = {pool.submit(_match_one, code): code for code in codes}
                        for fut in as_completed(futures):
                            code = futures[fut]
                            result = fut.result()
                            _collect(result)
                            done += 1
                            cur = f"{code} {name_map.get(code, '')}".strip()
                            progress.update(
                                task_id, completed=done, idx=done, cur=cur[:18], hit=matched_count,
                            )
                            _emit_cb(done)
        else:
            done = 0
            if workers <= 1:
                for code in codes:
                    _collect(_match_one(code))
                    done += 1
                    _emit_cb(done)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_match_one, code): code for code in codes}
                    for fut in as_completed(futures):
                        _collect(fut.result())
                        done += 1
                        _emit_cb(done)
            if total == 0 and self.progress_cb is not None:
                self.progress_cb(1.0, "宇宙为空，跳过匹配")

        results.sort(key=lambda r: (r.similarity, -r.distance), reverse=True)
        return PatternRunResult(
            pattern_id=definition.id,
            config_version=definition.version,
            trade_date=trade_date,
            results=results,
            stats={
                "matched_count": matched_count,
                "kept_count": len(results),
                "concurrency": workers,
            },
        )


def rank_records(results: list[PatternMatchResult]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for idx, result in enumerate(results, start=1):
        ranked.append(
            {
                "trade_date": result.trade_date,
                "code": result.code,
                "pattern_id": result.pattern_id,
                "scan_level": 1,
                "pattern_score": round(result.similarity, 2),
                "pattern_rank": idx,
                "global_rank": None,
                "reasons": result.reasons,
                "risk_flags": [],
                "score_components": {
                    "similarity": result.similarity,
                    "distance": result.distance,
                    "matched": result.matched,
                    "stage_similarity": result.stage_similarity,
                    "feature_similarity": result.feature_similarity,
                    "chosen_windows": result.chosen_windows,
                    "chosen_window_ranges": (result.metrics or {}).get("chosen_window_ranges"),
                    "metrics": result.metrics,
                },
                "inputs_snapshot": {
                    "chosen_windows": result.chosen_windows,
                    "chosen_window_ranges": (result.metrics or {}).get("chosen_window_ranges"),
                    "values": (result.metrics or {}).get("values"),
                },
            }
        )
    return ranked
