"""落盘模块（阶段 1）：单篇论文结果 + 汇总索引。

- data/papers/<arxiv_id>.json   单篇结构化结果（PaperInfo + 元信息）
- data/index.json               汇总索引（arxiv_id → 文件路径 + 关键字段）

可靠性设计：
- 原子写：先写 .tmp 再改名，避免进程中断产生半截 JSON；
- 索引按 arxiv_id 去重更新（重复处理同一篇只保留最新）；
- 全部 UTF-8，中文安全。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def _atomic_write(path: Path, obj: dict[str, Any]) -> None:
    """原子写：写临时文件后改名替换，防止中断损坏。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_paper(
    arxiv_id: str,
    paper: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> Path:
    """保存单篇论文结构化结果，返回文件路径。

    Args:
        arxiv_id: arXiv 编号（文件名）。
        paper: PaperInfo 字典（已通过 Schema 校验或 normalize 兜底）。
        meta: 提取元信息（attempts/error/耗时等），供评测与日志。

    Returns:
        保存后的完整路径。
    """
    config.settings.ensure_dirs()
    record = {
        "arxiv_id": arxiv_id,
        "paper": paper,
        "meta": meta or {},
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = config.settings.papers_dir / f"{arxiv_id}.json"
    _atomic_write(path, record)
    return path


def load_index() -> dict[str, Any]:
    """读取汇总索引；文件不存在/损坏时返回空索引。"""
    default = {"schema_version": "0.1", "papers": []}
    if not config.settings.index_path.exists():
        return default
    try:
        data = json.loads(config.settings.index_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("papers"), list):
            return data
        return default
    except (json.JSONDecodeError, OSError):
        return default


def update_index(arxiv_id: str, path: str, info: dict[str, Any]) -> None:
    """更新汇总索引：按 arxiv_id 去重后插入最新记录。"""
    idx = load_index()
    idx["papers"] = [p for p in idx["papers"] if p.get("arxiv_id") != arxiv_id]
    idx["papers"].append(
        {
            "arxiv_id": arxiv_id,
            "path": path,
            "title": info.get("title", ""),
            "year": info.get("year"),
            "venue": info.get("venue"),
        }
    )
    config.settings.ensure_dirs()
    _atomic_write(config.settings.index_path, idx)


def run_id() -> str:
    """生成一次流水线运行的 ID（日志/统计用）。"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
