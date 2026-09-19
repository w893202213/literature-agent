"""JSONL 运行日志（阶段 2 可观测）。

设计（对齐 PROJECT_PLAN 阶段 2 步骤 6）：
- 每步一条 JSON 记录：{ts, run, step, duration_s, status, ...}；
- 按 run_id 分文件：logs/<run_id>.jsonl；
- 后续接入 token/成本统计（usage 字段）。
- 用途：验收时能回答"这轮花了多少 token、哪步最慢"。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log_event(run: str, step: str, **fields: Any) -> None:
    """写一条事件日志（幂等：文件不存在则创建）。"""
    config.settings.ensure_dirs()
    entry: dict[str, Any] = {"ts": _now(), "run": run, "step": step}
    entry.update(fields)
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with open(config.settings.logs_dir / f"{run}.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_log(run: str) -> list[dict[str, Any]]:
    """读取一次运行的完整日志（供验收/复盘）。"""
    path = config.settings.logs_dir / f"{run}.jsonl"
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def summarize_log(run: str) -> dict[str, Any]:
    """日志摘要：每步耗时统计 + 总时长（验收用）。"""
    entries = read_log(run)
    step_times: dict[str, float] = {}
    statuses: dict[str, int] = {}
    for e in entries:
        step = e.get("step", "?")
        d = e.get("duration_s")
        if d is not None:
            step_times[step] = round(step_times.get(step, 0.0) + float(d), 1)
        st = e.get("status", "?")
        statuses[st] = statuses.get(st, 0) + 1
    total = sum(step_times.values())
    slowest = max(step_times.items(), key=lambda kv: kv[1]) if step_times else ("-", 0.0)
    return {
        "entries": len(entries),
        "statuses": statuses,
        "step_time_s": step_times,
        "total_time_s": round(total, 1),
        "slowest_step": slowest,
    }
