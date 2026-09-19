"""单篇论文流水线（阶段 1）：search → fetch → parse → extract → save。

编排逻辑：
    搜索源（openalex 主 / arxiv 备）→ 逐篇：
        fetch_pdf（失败跳过）→ parse_pdf（失败跳过）
        → extract_paper_info（失败跳过）→ save_paper + update_index

设计原则（对齐 PROJECT_PLAN 第 5 节）：
- 单篇失败不中断整体：每步失败记录到 summary["failed"]，继续下一篇；
- 搜索源可插拔：统一抽象为 PaperCandidate（id/title/pdf_url），
  换搜索源只改"搜索结果 → PaperCandidate"的转换，pipeline 主体不动；
- 所有 LLM 调用走 client.py 统一直连策略。
"""

from __future__ import annotations

import time
from typing import Any

import config
from tools.dedupe import normalize_title  # noqa: F401  # 供 rank 使用
from tools.extract_paper_info import extract_paper_info
from tools.fetch_pdf import fetch_pdf
from tools.io import run_id, save_paper, update_index
from tools.models import PaperCandidate
from tools.parse_pdf import parse_pdf
from tools.rank import filter_candidates
from tools.search_arxiv import SearchResult, build_arxiv_query, search_arxiv
from tools.search_openalex import OpenAlexResult, search_openalex


def arxiv_to_candidate(r: SearchResult) -> PaperCandidate:
    """ArXiv 搜索结果 → 统一候选。"""
    return PaperCandidate(
        paper_id=r.arxiv_id,
        title=r.title,
        pdf_url=r.pdf_url,
        authors=r.authors,
        summary=r.summary,
        year=r.published[:4],
        source="arxiv",
    )


def openalex_to_candidate(r: OpenAlexResult) -> PaperCandidate:
    """OpenAlex 搜索结果 → 统一候选。"""
    return PaperCandidate(
        paper_id=r.paper_id,
        title=r.title,
        pdf_url=r.pdf_url,
        authors=r.authors,
        summary=r.abstract,
        year=str(r.year),
        venue=r.venue,
        source="openalex",
    )


def _search(
    topic: str,
    source: str,
    max_results: int,
    year_from: int | None = None,
    queries: list[str] | None = None,
) -> list[PaperCandidate]:
    """按查询词列表搜索并统一转成 PaperCandidate（多查询合并 + 论文级去重）。"""
    queries = queries or [topic]
    per_q = max(max_results // len(queries), 3)
    cands: list[PaperCandidate] = []
    seen: set[str] = set()
    for q in queries:
        if source == "arxiv":
            query = build_arxiv_query(q)
            results = search_arxiv(query, max_results=per_q)
            for r in results:
                c = arxiv_to_candidate(r)
                if c.paper_id not in seen:
                    seen.add(c.paper_id)
                    cands.append(c)
        else:
            # 默认 openalex（更稳：无 key 限流宽松、有被引数排序）
            results = search_openalex(q, per_page=per_q, year_from=year_from)
            for r in results:
                c = openalex_to_candidate(r)
                if c.paper_id not in seen:
                    seen.add(c.paper_id)
                    cands.append(c)
    return cands


def process_one_paper(candidate: PaperCandidate, run: str) -> dict[str, Any]:
    """处理单篇论文（下载→解析→提取→落盘），返回结果记录。

    Returns:
        {"paper_id", "status": "ok"|"skip_fetch"|"skip_parse"|"skip_extract",
         "time_s", "error", "path"}
    """
    t0 = time.perf_counter()
    record: dict[str, Any] = {"paper_id": candidate.paper_id, "run": run}

    # 1. 下载 PDF（无直链或下载失败 → 跳过）
    if not candidate.pdf_url:
        record.update(status="skip_fetch", error="无 PDF 直链",
                      time_s=round(time.perf_counter() - t0, 1))
        print(f"[pipeline] {candidate.paper_id} 无 PDF 直链，跳过")
        return record
    pdf_path = config.settings.cache_dir / "pdfs" / f"{candidate.paper_id}.pdf"
    saved = fetch_pdf(candidate.pdf_url, out_path=pdf_path)
    if saved is None:
        record.update(status="skip_fetch", time_s=round(time.perf_counter() - t0, 1))
        print(f"[pipeline] {candidate.paper_id} 下载失败，跳过")
        return record

    # 2. 解析全文（失败跳过）
    text = parse_pdf(saved)
    if text is None:
        record.update(status="skip_parse", time_s=round(time.perf_counter() - t0, 1))
        print(f"[pipeline] {candidate.paper_id} 解析失败，跳过")
        return record

    # 3. 结构化提取（失败跳过）
    info, meta = extract_paper_info(text)
    if info is None:
        record.update(status="skip_extract", error=meta.get("error", ""),
                      time_s=round(time.perf_counter() - t0, 1))
        print(f"[pipeline] {candidate.paper_id} 提取失败: {meta.get('error', '')[:80]}")
        return record

    # 4. 落盘：单篇 JSON + 汇总索引
    path = save_paper(candidate.paper_id, {
        "title": candidate.title, "pdf": str(saved),
        "venue": candidate.venue, "source": candidate.source, **info,
    }, meta)
    update_index(candidate.paper_id, str(path), info)

    record.update(status="ok", path=str(path), time_s=round(time.perf_counter() - t0, 1))
    print(f"[pipeline] {candidate.paper_id} 完成 ({record['time_s']}s) → {path.name}")
    return record


def run_topic_pipeline(
    topic: str,
    max_papers: int = 10,
    source: str = "openalex",
    min_score: int = 3,
    year_from: int | None = None,
) -> dict[str, Any]:
    """按主题跑完整流水线（搜索 → 筛选 → 逐篇处理），返回汇总。

    Args:
        topic: 研究主题（自然语言）。
        max_papers: 搜索候选上限（成本护栏）。
        source: 搜索源，openalex（默认，更稳）或 arxiv。
        min_score: LLM 相关性打分阈值（1-5，低于则剔除，默认 3）。
        year_from: 只保留该年份及以后的论文（默认不限）。

    Returns:
        {"run_id", "topic", "source", "searched", "filtered", "processed",
         "failed", "ok_ids", "fail_ids", "filter_stats", "total_time_s"}
    """
    run = run_id()
    t0 = time.perf_counter()
    print(f"=== 流水线开始: {topic} (run={run}, 源={source}, 上限 {max_papers} 篇) ===")

    candidates = _search(topic, source, max_papers, year_from=year_from)
    print(f"搜索到 {len(candidates)} 篇候选")

    # 筛选：年份过滤 → 标题去重 → LLM 打分 → 阈值过滤
    filtered, filter_stats = filter_candidates(
        topic, candidates, min_score=min_score, year_from=year_from
    )
    print(
        f"筛选: {filter_stats['before']} → 年份后 {filter_stats['after_year']}"
        f" → 去重后 {filter_stats['after_dedupe']}"
        f" → LLM 打分 {filter_stats['scored']} 篇 → 保留 {filter_stats['kept']} 篇"
    )
    for c in filtered:
        sc = c.scores.get("relevance")
        print(f"  [相关度 {sc}/5] {c.paper_id} | {c.title[:50]}")

    ok_ids: list[str] = []
    fail_ids: list[str] = []
    for c in filtered:
        rec = process_one_paper(c, run)
        if rec["status"] == "ok":
            ok_ids.append(c.paper_id)
        else:
            fail_ids.append(c.paper_id)

    summary = {
        "run_id": run,
        "topic": topic,
        "source": source,
        "searched": len(candidates),
        "filtered": len(filtered),
        "processed": len(ok_ids),
        "failed": len(fail_ids),
        "ok_ids": ok_ids,
        "fail_ids": fail_ids,
        "filter_stats": filter_stats,
        "total_time_s": round(time.perf_counter() - t0, 1),
    }
    print(f"=== 完成: 成功 {len(ok_ids)} 篇 / 失败 {len(fail_ids)} 篇，总耗时 {summary['total_time_s']}s ===")
    return summary
