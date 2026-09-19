"""对比表格生成（阶段 2）：从提取结果生成方法对比表（Markdown + CSV）。

设计（面试亮点）：
- **LLM 只做"语义压缩"，格式由程序保证**：LLM 负责把 method 压缩成
  "一句话方法概括 + 一句话亮点"（语义任务，它擅长）；Markdown/CSV 的语法
  由程序生成（稳定、零格式崩坏风险）。分工：LLM 加工内容，程序保证格式；
- 批量压缩：一次 LLM 调用处理多篇（复用 rank 的批量模式，省 token）；
- 论文量少（≤12）不聚类，直接一张总表（embedding 聚类留可选增强）；
- CSV 用 utf-8-sig 编码（Excel 打开中文不乱码）。
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import config
from client import make_openai_client

COLUMNS = ["论文", "年份", "一句话方法", "数据集", "关键结果", "亮点"]

TABLE_SYSTEM_PROMPT = (
    "你是学术综述助手。给定若干论文的标题和核心方法描述，请为每篇论文生成：\n"
    "1. method_short：一句话概括其核心方法（不超过 40 字）；\n"
    "2. highlight：一句话点出该工作最有辨识度的亮点（不超过 40 字）。\n"
    "只输出一个 JSON 对象，键为论文 id，值为 {method_short, highlight}，"
    '形如 {"id1": {"method_short": "...", "highlight": "..."}}。'
    "不要输出任何其他内容。"
)

_MAX_METHOD_CHARS = 500
_MAX_RESULT_CHARS = 200
_MAX_CONTRIBUTION_CHARS = 120
_MAX_HIGHLIGHT_CHARS = 80


def build_batch_input(extracted: dict[str, dict[str, Any]]) -> str:
    """构造批量压缩输入：每篇的 id/标题/方法描述（截断）。"""
    lines: list[str] = []
    for pid in sorted(extracted):
        paper = extracted[pid]
        lines.append(f"[{pid}]")
        lines.append(f"标题: {(paper.get('title') or '')[:120]}")
        method = paper.get("method") or ""
        if method:
            lines.append(f"方法: {method[:_MAX_METHOD_CHARS]}")
        lines.append("")
    return "\n".join(lines)


def _parse_summaries(raw: str) -> dict[str, dict[str, str]]:
    """宽松解析 LLM 压缩输出（JSON 优先，正则兜底）。"""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            out: dict[str, dict[str, str]] = {}
            for k, v in obj.items():
                if isinstance(v, dict):
                    out[str(k)] = {
                        "method_short": str(v.get("method_short") or "")[:80],
                        "highlight": str(v.get("highlight") or "")[:80],
                    }
            return out
    except json.JSONDecodeError:
        pass
    # 正则兜底：找 "id": {"method_short": "..", "highlight": ".."}
    out = {}
    for pid, ms, hl in re.findall(
        r'"([^"]+)":\s*\{[^}]*?"method_short"\s*:\s*"([^"]*)",?\s*"highlight"\s*:\s*"([^"]*)"',
        s,
    ):
        out[pid] = {"method_short": ms[:80], "highlight": hl[:80]}
    return out


def summarize_methods(
    extracted: dict[str, dict[str, Any]],
    client: Any | None = None,
    max_retries: int = 2,
) -> dict[str, dict[str, str]]:
    """LLM 批量压缩：{paper_id: {method_short, highlight}}（失败/缺失篇目返回空）。"""
    if not extracted:
        return {}
    if client is None:
        client = make_openai_client()

    user_input = build_batch_input(extracted)
    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=config.settings.model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": TABLE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                max_tokens=1024,
                timeout=180,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = f"API 错误: {e}"
            continue

        parsed = _parse_summaries(raw)
        # 只保留候选集合内的 id
        valid = {pid: v for pid, v in parsed.items() if pid in extracted}
        if valid:
            return valid
        last_err = f"解析失败 (attempt {attempt}): {raw[:100]!r}"

    print(f"[summarize] LLM 压缩失败（{max_retries} 次重试）: {last_err}")
    return {}


def _md_escape(s: str) -> str:
    """Markdown 表格单元转义：| 和换行。"""
    return s.replace("|", "\\|").replace("\n", " ").strip()


def build_table(
    extracted: dict[str, dict[str, Any]],
    short: dict[str, dict[str, str]],
) -> dict[str, str]:
    """程序拼装 Markdown + CSV（格式保证，LLM 只提供压缩内容）。"""
    rows: list[list[str]] = []
    for pid in sorted(extracted):
        paper = extracted[pid]
        s = short.get(pid, {})
        datasets = ", ".join(paper.get("datasets") or [])[:100] or "-"
        contribution = (paper.get("contribution") or ["-"])[0][:_MAX_CONTRIBUTION_CHARS]
        rows.append(
            [
                (paper.get("title") or pid)[:60],
                str(paper.get("year") or ""),
                s.get("method_short") or (paper.get("method") or "-")[:_MAX_HIGHLIGHT_CHARS],
                datasets,
                (paper.get("results") or "-")[:_MAX_RESULT_CHARS],
                s.get("highlight") or contribution,
            ]
        )

    # Markdown 表格
    header = "| " + " | ".join(COLUMNS) + " |"
    sep = "|" + "---|" * len(COLUMNS)
    lines = [header, sep]
    lines += ["| " + " | ".join(_md_escape(c) for c in r) + " |" for r in rows]
    md = "\n".join(lines)

    # CSV（csv 模块自动处理逗号/引号转义）
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return {"markdown": md, "csv": buf.getvalue()}


def save_outputs(topic: str, run_id: str, tables: dict[str, str]) -> dict[str, Path]:
    """导出 Markdown + CSV 到 data/outputs/（utf-8-sig：Excel 中文兼容）。"""
    out_dir = config.settings.data_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"{run_id}_table.md"
    md_path.write_text(
        f"# {topic} 方法对比表（run={run_id}）\n\n{tables['markdown']}\n",
        encoding="utf-8",
    )
    csv_path = out_dir / f"{run_id}_table.csv"
    csv_path.write_text(tables["csv"], encoding="utf-8-sig")
    return {"markdown": md_path, "csv": csv_path}


def summarize_papers(
    topic: str, extracted: dict[str, dict[str, Any]], run_id: str
) -> dict[str, Any]:
    """总入口：批量压缩 → 建表 → 导出，返回 {tables, files}。"""
    short = summarize_methods(extracted)
    tables = build_table(extracted, short)
    paths = save_outputs(topic, run_id, tables)
    return {
        "tables": tables,
        "files": {k: str(v) for k, v in paths.items()},
        "summarized": len(short),
    }
