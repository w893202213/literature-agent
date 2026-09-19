"""相关性筛选（阶段 1）：LLM 打分 1-5 + 规则过滤。

筛选流程（对齐 PROJECT_PLAN 阶段 1 步骤 3）：
    年份过滤（规则，零成本）→ 标题去重（normalize_title）
    → LLM 批量打分（1-5）→ 阈值过滤

设计要点（面试亮点）：
- **批量打分**：一次 LLM 调用给多篇论文打分（省 token/时间），
  输出 JSON 校验 + 重试（复用四层防线思想）；
- 与 OpenAlex 内置 relevance_score 互补：引擎分数是"检索相关"，LLM 分数是
  "用户主题语义"的二次精筛；
- 打分缺项保守处理：LLM 漏打某篇 → 保留（宁可多处理，避免误杀）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from client import make_openai_client
from tools.dedupe import normalize_title
from tools.models import PaperCandidate

RANK_SYSTEM_PROMPT = (
    "你是学术文献相关性评审。给定一个研究主题和若干篇论文（含标题与摘要），"
    "请为每篇论文与该主题的**语义相关性**打分（1-5 整数）：\n"
    "1=完全无关  2=弱相关（仅关键词巧合、研究问题与主题不同）  "
    "3=相关  4=很相关  5=高度相关\n"
    "特别注意：论文摘要中只出现主题关键词、但研究问题完全不同方向的论文，"
    "打分不得超过 2（例如主题是模型蒸馏，论文却讨论攻击/安全/越狱）。\n"
    "只输出一个 JSON 对象，键为论文 id，值为分数，形如 "
    '{"paper_id_1": 3, "paper_id_2": 4}。不要输出任何其他内容。'
)

# 摘要截断长度（控 token 成本）
_MAX_ABSTRACT_CHARS = 400


def build_rank_input(topic: str, candidates: list[PaperCandidate]) -> str:
    """构造批量打分输入：主题 + 每篇的 id/标题/摘要（截断）。"""
    lines = [f"研究主题：{topic}", ""]
    for c in candidates:
        lines.append(f"[{c.paper_id}]")
        lines.append(f"标题: {c.title[:150]}")
        if c.summary:
            lines.append(f"摘要: {c.summary[:_MAX_ABSTRACT_CHARS]}")
        lines.append("")
    return "\n".join(lines)


def _parse_scores(raw: str) -> dict[str, int]:
    """宽松解析 LLM 打分输出：先 json.loads，失败则正则提取。"""
    # 1. 尝试 JSON 解析（去掉代码块包装）
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return {str(k): int(v) for k, v in obj.items() if str(v).isdigit()}
    except json.JSONDecodeError:
        pass
    # 2. 正则兜底：提取 "id": 1-5 形式的键值对
    scores: dict[str, int] = {}
    for k, v in re.findall(r'"([^"]+)":\s*([1-5])', s):
        scores[k] = int(v)
    return scores


def batch_rank(
    topic: str,
    candidates: list[PaperCandidate],
    client: Any | None = None,
    max_retries: int = 2,
) -> dict[str, int]:
    """对候选论文批量打分，返回 {paper_id: score}。

    打分失败/缺失的论文不在返回 dict 中（调用方按保守策略处理）。
    """
    if not candidates:
        return {}
    if client is None:
        client = make_openai_client()

    from config import settings

    user_input = build_rank_input(topic, candidates)
    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=settings.model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": RANK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                max_tokens=512,
                timeout=180,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = f"API 错误: {e}"
            continue

        scores = _parse_scores(raw)
        # 校验：分数必须在 1-5 且键在候选 id 集合内
        valid_ids = {c.paper_id for c in candidates}
        clean = {
            pid: s for pid, s in scores.items()
            if pid in valid_ids and 1 <= s <= 5
        }
        if clean:
            return clean
        last_err = f"打分解析失败 (attempt {attempt}): {raw[:100]!r}"

    print(f"[rank] 打分失败（{max_retries} 次重试）: {last_err}")
    return {}


def filter_candidates(
    topic: str,
    candidates: list[PaperCandidate],
    min_score: int = 3,
    year_from: int | None = None,
    use_llm: bool = True,
) -> tuple[list[PaperCandidate], dict[str, Any]]:
    """筛选候选：年份过滤 → 标题去重 → LLM 打分 → 阈值过滤。

    Returns:
        (筛选后的候选列表, 统计信息 {before, after_year, after_dedupe, scored, kept})
    """
    stats: dict[str, Any] = {"before": len(candidates)}

    # 1. 年份过滤（规则，零成本）
    if year_from:
        candidates = [c for c in candidates if (int(c.year or 0) >= year_from)]
    stats["after_year"] = len(candidates)

    # 2. 标题归一化去重（同一篇的不同版本合并）
    seen: set[str] = set()
    deduped: list[PaperCandidate] = []
    for c in candidates:
        key = normalize_title(c.title)
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    stats["after_dedupe"] = len(deduped)

    # 3. LLM 批量打分 + 阈值过滤
    if use_llm and deduped:
        scores = batch_rank(topic, deduped)
        stats["scored"] = len(scores)
        kept = [c for c in deduped if scores.get(c.paper_id, min_score) >= min_score]
        # 保守策略：LLM 漏打的论文按 min_score 保留（避免误杀）
    else:
        scores = {}
        stats["scored"] = 0
        kept = deduped
    stats["kept"] = len(kept)

    # 附上分数供调用方展示
    for c in kept:
        c.scores = {"relevance": scores.get(c.paper_id)}
    return kept, stats
