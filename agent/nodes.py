"""流程节点（阶段 2）：LangGraph 图中的每个节点对应一个阶段。

节点约定：
- 输入 state，输出 {字段: 新值} 字典（LangGraph 自动合并进状态）；
- **阶段内批量处理**：单篇失败在节点内部消化（复用 pipeline 的 skip 容错），
  图层面只管阶段间流转——状态粒度与图粒度分离；
- 每个节点写 JSONL 日志（tools.logger），满足"哪步最慢"的可观测验收；
- 节点内所有 LLM 调用走统一直连策略（client.py）。
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

import config
from agent.planner import build_plan
from agent.state import PipelineState
from tools.logger import log_event
from tools.models import PaperCandidate
from tools.pipeline import (
    arxiv_to_candidate,
    openalex_to_candidate,
    process_one_paper,
)
from tools.rank import filter_candidates
from tools.search_arxiv import build_arxiv_query, search_arxiv
from tools.search_openalex import search_openalex


def _to_dicts(cands: list[PaperCandidate]) -> list[dict[str, Any]]:
    return [asdict(c) for c in cands]


def _to_cands(items: list[dict[str, Any]]) -> list[PaperCandidate]:
    return [PaperCandidate(**d) for d in items]


def _timings(state: PipelineState) -> dict[str, float]:
    meta = dict(state.get("meta") or {})
    return dict(meta.get("step_timings") or {})


def _finish(state: PipelineState, step: str, t0: float,
            status: str = "ok", **extra: Any) -> dict[str, Any]:
    """统一收尾：更新 meta 计时 + 写日志（extra 一并进日志），返回节点增量。"""
    duration = time.perf_counter() - t0
    meta = dict(state.get("meta") or {})
    timings = _timings(state)
    timings[step] = round(timings.get(step, 0.0) + duration, 2)
    meta["step_timings"] = timings
    for k, v in extra.items():
        meta[k] = v
    log_event(state.get("run_id", "?"), step,
              duration_s=round(duration, 2), status=status, **extra)
    return {"meta": meta}


def node_planner(state: PipelineState) -> dict[str, Any]:
    """任务规划：LLM 生成多组查询词（失败降级规则版）。"""
    t0 = time.perf_counter()
    plan = build_plan(
        state.get("topic", ""),
        max_papers=state.get("max_papers", 10),
        year_from=state.get("year_from"),
    )
    plan["source"] = state.get("source", "openalex")
    plan["min_score"] = state.get("min_score", 3)
    out = _finish(state, "planner", t0, queries=len(plan.get("queries") or []),
                  planner=plan.get("notes"))
    out["plan"] = plan
    return out


def node_search(state: PipelineState) -> dict[str, Any]:
    """搜索：按 plan.queries 多查询合并（论文级去重），转统一候选。

    多查询必要性（P16）：单查询 AND 语义召回不了新论文，planner 生成的
    多组查询覆盖不同子方向，合并后候选更全。
    """
    t0 = time.perf_counter()
    plan = state.get("plan") or {}
    source = plan.get("source", "openalex")
    queries = plan.get("queries") or [state.get("topic", "")]
    n = plan.get("max_papers", 10)
    per_q = max(n // len(queries), 3)  # 每组分配条数（总数不超预算）

    cands: list[PaperCandidate] = []
    seen: set[str] = set()
    for q in queries:
        if source == "arxiv":
            results = search_arxiv(build_arxiv_query(q), max_results=per_q)
            for r in results:
                c = arxiv_to_candidate(r)
                if c.paper_id not in seen:
                    seen.add(c.paper_id)
                    cands.append(c)
        else:
            results = search_openalex(q, per_page=per_q,
                                      year_from=plan.get("year_from"))
            for r in results:
                c = openalex_to_candidate(r)
                if c.paper_id not in seen:
                    seen.add(c.paper_id)
                    cands.append(c)

    out = _finish(state, "search", t0, status="ok" if cands else "empty",
                  candidates=len(cands), queries=len(queries))
    out["papers"] = _to_dicts(cands)
    return out


def node_filter(state: PipelineState) -> dict[str, Any]:
    """筛选：年份过滤 → 标题去重 → LLM 打分 → 阈值过滤。"""
    t0 = time.perf_counter()
    plan = state.get("plan") or {}
    cands = _to_cands(state.get("papers") or [])

    kept, stats = filter_candidates(
        plan.get("queries", [""])[0], cands,
        min_score=plan.get("min_score", 3),
        year_from=plan.get("year_from"),
    )
    out = _finish(state, "filter", t0, filter_stats=stats, kept=len(kept))
    out["filtered"] = _to_dicts(kept)
    return out


def node_process(state: PipelineState) -> dict[str, Any]:
    """逐篇处理：下载→解析→提取→落盘（复用 pipeline 的 skip 容错）。

    单篇失败在节点内部消化，图层面不感知——这是"阶段内批量"设计。
    成功后从 data/papers/<id>.json 读回提取结果，供 summarize 使用。
    """
    t0 = time.perf_counter()
    run = state.get("run_id", "?")
    cands = _to_cands(state.get("filtered") or [])

    ok_ids: list[str] = []
    fail_ids: list[str] = []
    fail_reasons: dict[str, str] = {}
    extracted: dict[str, dict[str, Any]] = {}
    for c in cands:
        rec = process_one_paper(c, run)
        if rec["status"] == "ok":
            ok_ids.append(c.paper_id)
            # 读回落盘的提取结果（后续 summarize 用）
            paper_file = config.settings.papers_dir / f"{c.paper_id}.json"
            if paper_file.exists():
                import json

                extracted[c.paper_id] = json.loads(
                    paper_file.read_text(encoding="utf-8")
                ).get("paper", {})
        else:
            fail_ids.append(c.paper_id)
            fail_reasons[c.paper_id] = rec.get("error") or rec["status"]

    out = _finish(state, "process", t0, ok=len(ok_ids), failed=len(fail_ids))
    out["errors"] = list(state.get("errors") or []) + [
        ("process", pid, reason) for pid, reason in fail_reasons.items()
    ]
    out["extracted"] = extracted
    return out


def node_summarize(state: PipelineState) -> dict[str, Any]:
    """汇总：LLM 批量压缩方法 → 程序生成对比表（Markdown+CSV）→ 导出。"""
    t0 = time.perf_counter()
    extracted = state.get("extracted") or {}
    if not extracted:
        return _finish(state, "summarize", t0, status="empty", papers=0)

    from tools.summarize import summarize_papers

    result = summarize_papers(
        state.get("topic", ""), extracted, state.get("run_id", "?")
    )
    out = _finish(state, "summarize", t0, papers=len(extracted),
                  files=result["files"], summarized=result["summarized"])
    out["tables"] = result["tables"]
    print(f"[summarize] 已生成对比表，导出: {result['files']['markdown']}")
    return out


def node_review(state: PipelineState) -> dict[str, Any]:
    """综述初稿：LLM 生成（引用白名单）+ 程序核验（防幻觉），落盘 Markdown。"""
    t0 = time.perf_counter()
    extracted = state.get("extracted") or {}
    if not extracted:
        return _finish(state, "review", t0, status="empty", papers=0)

    from tools.review import generate_review

    text, meta = generate_review(state.get("topic", ""), extracted)
    verified = meta.get("verified") or {}
    out = _finish(state, "review", t0, papers=len(extracted),
                  citations=len(verified.get("citations", [])),
                  invalid=meta.get("invalid_refs") or [],
                  tokens_review=meta.get("tokens", 0))

    if text:
        out["review"] = text
        # 落盘综述初稿
        out_dir = config.settings.data_dir / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{state.get('run_id', '?')}_review.md"
        md_path.write_text(
            f"# {state.get('topic', '')} 综述初稿\n\n{text}\n", encoding="utf-8"
        )
        print(f"[review] 综述初稿已导出（引用 {len(verified.get('citations', []))} 条）: {md_path}")
    else:
        print(f"[review] 综述生成失败（幻觉引用重试耗尽）: {meta.get('error', '')[:80]}")
    return out


def node_output(state: PipelineState) -> dict[str, Any]:
    """输出：落盘运行汇总 + 最终统计。"""
    t0 = time.perf_counter()
    meta = dict(state.get("meta") or {})
    summary = {
        "run_id": state.get("run_id", "?"),
        "topic": state.get("topic", ""),
        "source": (state.get("plan") or {}).get("source"),
        "searched": len(state.get("papers") or []),
        "filtered": len(state.get("filtered") or []),
        "filter_stats": meta.get("filter_stats"),
        "errors": state.get("errors") or [],
        "step_timings": meta.get("step_timings", {}),
        "total_time_s": round(time.perf_counter() - t0, 2),
    }
    out = _finish(state, "output", t0, summary=summary)
    out["output"] = summary
    return out
