"""评测入口（阶段 3）：在冻结评测集上跑指标，输出评测报告。

用法：
    python main.py eval              # 生成"预测 vs 标准答案"对照表
    python main.py eval --verdict <文件>   # 读人工判定，算字段准确率

流程（半自动评测）：
1. 生成对照表（datasets 自动判，method/results 待人工）；
2. 人工在 verdict JSON 里把 PENDING 改成 ok / ng；
3. 脚本读 verdict 算字段准确率 + 汇总报告。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from eval.metrics import build_field_judgements, field_accuracy_from_verdicts


def load_dataset() -> list[dict[str, Any]]:
    """读取冻结评测集（eval/dataset/*.json），扁平化并带 topic。"""
    dataset_dir = Path(__file__).parent / "dataset"
    papers: list[dict[str, Any]] = []
    for f in sorted(dataset_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in data.get("papers", []):
            p = dict(p)
            p["_topic"] = data.get("topic", "")
            papers.append(p)
    return papers


def build_comparison() -> dict[str, Any]:
    """对评测集每篇：读落盘提取结果（或标记缺失）→ 对比 gold → 生成判定。"""
    dataset = load_dataset()
    rows: list[dict[str, Any]] = []
    for p in dataset:
        aid = p["arxiv_id"]
        paper_file = config.settings.papers_dir / f"{aid}.json"
        title = p.get("title", aid)
        if paper_file.exists():
            pred = json.loads(paper_file.read_text(encoding="utf-8"))["paper"]
            rows.append({
                "arxiv_id": aid,
                "title": title,
                "should_recall": p.get("should_recall", True),
                "status": "extracted",
                "judgements": build_field_judgements(pred, p["gold"]),
            })
        else:
            rows.append({
                "arxiv_id": aid,
                "title": title,
                "should_recall": p.get("should_recall", True),
                "status": "missing",
                "judgements": {},
            })
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "dataset_size": len(dataset),
        "extracted": sum(1 for r in rows if r["status"] == "extracted"),
        "missing": [r["arxiv_id"] for r in rows if r["status"] == "missing"],
        "rows": rows,
    }


def render_markdown(comp: dict[str, Any]) -> str:
    """生成人工核对对照表（Markdown）。"""
    lines = [
        f"# 评测对照表（{comp['date']}）",
        "",
        f"- 评测集规模: {comp['dataset_size']} 篇",
        f"- 已提取: {comp['extracted']} 篇 | 缺失(待跑): {len(comp['missing'])} 篇",
        "",
        "| 论文 | 字段 | 判定 | 模型预测 | 标准答案(gold) |",
        "|---|---|---|---|---|",
    ]
    for r in comp["rows"]:
        if r["status"] == "missing":
            lines.append(f"| {r['arxiv_id']} | - | ❌未提取 | - | - |")
            continue
        for f, j in r["judgements"].items():
            if j["judgement"] == "AUTO":
                mark = "✅" if j["ok"] else "❌"
                judge = f"{mark} 自动(重合{j['score']})"
            else:
                judge = "⏳待人工"
            pred_txt = str(j["pred"])[:80].replace("|", "\\|")
            gold_txt = str(j["gold"])[:80].replace("|", "\\|")
            lines.append(
                f"| {r['arxiv_id']} | {f} | {judge} | {pred_txt} | {gold_txt} |"
            )
    return "\n".join(lines)


def score_from_verdict(verdict_path: str) -> dict[str, Any]:
    """读人工判定文件（{"<arxiv_id>": {"method": "ok", "results": "ng", ...}}）算分。"""
    verdicts = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
    comp = build_comparison()
    # 把人工判定合并进 rows 的 judgements
    for row in comp["rows"]:
        v = verdicts.get(row["arxiv_id"], {})
        for f, j in row.get("judgements", {}).items():
            if f in v:
                j["judgement"] = v[f]  # ok / ng
    acc = field_accuracy_from_verdicts(comp["rows"])
    report = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "field_accuracy": acc,
        "rows": comp["rows"],
    }
    out = Path(__file__).parent / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"字段准确率: {acc:.1%}")
    print(f"评测报告已写入: {out}")
    return report


def _title_keywords(title: str, max_words: int = 2) -> str:
    """从标题提取搜索关键词：取前 max_words 个显著词（跳过停用词）。

    例："Qwen2.5-VL Technical Report" → "Qwen2.5-VL"
        "InternVL3: Exploring Advanced Training..." → "InternVL3 Exploring"
    词越少 AND 干扰越小；模型名/缩写词（含数字连字符）优先单用。
    """
    stopwords = {"a", "an", "the", "of", "for", "via", "and", "with", "from",
                 "on", "in", "to", "into", "towards", "toward", "novel", "new"}
    words: list[str] = []
    # 注意：不拆连字符——模型名/缩写（VLM-R1、CoME-VL、Vision-Language）以
    # 连字符为特征，拆开会丢失辨识度（P15 教训：VLM-R1 拆成 VLM,R1 后 R1 被跳过）
    for w in title.replace(":", " ").replace(",", " ").split():
        w = w.strip()
        if len(w) >= 4 and w.lower() not in stopwords:
            words.append(w)
        if len(words) >= max_words:
            break
    return " ".join(words) if words else title[:60]


def run_recall_eval(per_page: int = 20) -> dict[str, Any]:
    """召回率评测：逐篇用"标题关键词"召回（测检索能力，避免排序截断偏差）。

    口径（P15 修正）：
    - 宽泛主题查询 + 相关性排序会把特定新论文排到 100 名之外（排序截断），
      测的是排序而非检索能力；改用"每篇标题关键词查询"直接测能否召回该论文；
    - 召回率 = 命中正例 / 正例总数（should_recall=true，目标 ≥80%）；
    - 负例同样用标题关键词查询：若被召回（搜到标题相同论文）记为误召回；
    - 命中判定：arxiv_id 精确或归一化标题相等。

    Returns:
        {"topic", "recall", "hit_ids", "missed_ids", "false_recalls", "detail"}
    """
    from tools.dedupe import normalize_title
    from tools.search_openalex import search_openalex

    dataset = load_dataset()
    if not dataset:
        print("⚠️  评测集为空")
        return {"status": "empty"}

    topic = dataset[0].get("_topic", "")
    positives = [p for p in dataset if p.get("should_recall", True)]
    negatives = [p for p in dataset if not p.get("should_recall", True)]

    print(f"=== 召回率评测（标题关键词逐篇召回）: {topic} ===")
    detail: list[dict[str, Any]] = []

    def _hit(results, p) -> bool:
        ids = {r.paper_id for r in results}
        titles = {normalize_title(r.title) for r in results}
        return (p["arxiv_id"] in ids
                or normalize_title(p.get("title", "")) in titles)

    hit_ids: list[str] = []
    for p in positives:
        # 两级召回：先 2 词关键词（精准），未命中回退标题截断（宽召回）
        candidates = [_title_keywords(p.get("title", "")), p.get("title", "")[:45]]
        hit = False
        kw_used = candidates[0]
        for kw in candidates:
            results = search_openalex(kw, per_page=per_page, oa_only=False,
                                      year_from=2025)
            if _hit(results, p):
                hit = True
                break
        # 仍未命中：用完整标题检查 OpenAlex 是否收录该论文
        indexed = False
        if not hit:
            r_full = search_openalex(p.get("title", "")[:80], per_page=5,
                                     oa_only=False, year_from=2025)
            indexed = _hit(r_full, p)
        status = "✅" if hit else ("⚠️未收录" if indexed else "❌")
        detail.append({"arxiv_id": p["arxiv_id"], "keyword": kw_used,
                       "hit": hit, "indexed": indexed})
        print(f"  {status} {p['arxiv_id']} 关键词「{kw_used[:30]}」")
        if hit:
            hit_ids.append(p["arxiv_id"])

    # 负例用"宽泛主题查询"测试误召回（标题关键词必然命中自己，无意义）
    topic_queries = [topic, "knowledge distillation", "vision-language model"]
    topic_results = []
    for q in topic_queries:
        topic_results.extend(
            search_openalex(q, per_page=50, oa_only=False, year_from=2025)
        )
    topic_ids = {r.paper_id for r in topic_results}
    topic_titles = {normalize_title(r.title) for r in topic_results}
    false_recalls = [
        p["arxiv_id"] for p in negatives
        if p["arxiv_id"] in topic_ids
        or normalize_title(p.get("title", "")) in topic_titles
    ]

    recall_val = round(len(hit_ids) / len(positives), 3) if positives else 0.0
    missed_ids = [p["arxiv_id"] for p in positives if p["arxiv_id"] not in hit_ids]
    print(f"\n召回率: {len(hit_ids)}/{len(positives)} = {recall_val:.1%}")
    print(f"负例误召回: {len(false_recalls)}/{len(negatives)}")
    if missed_ids:
        print(f"未命中: {missed_ids}")
    return {
        "topic": topic,
        "recall": recall_val,
        "hit_ids": hit_ids,
        "missed_ids": missed_ids,
        "false_recalls": false_recalls,
        "detail": detail,
    }


def run_eval() -> dict[str, Any]:
    """主流程：生成对照表并落盘 Markdown。"""
    comp = build_comparison()
    if comp["dataset_size"] == 0:
        print("⚠️  评测集为空：请先在 eval/dataset/ 冻结论文（阶段 3）")
        return {"status": "empty"}

    md = render_markdown(comp)
    out_md = Path(__file__).parent / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"评测集 {comp['dataset_size']} 篇：已提取 {comp['extracted']}，缺失 {len(comp['missing'])}")
    print(f"对照表已写入: {out_md}")
    print("人工核对后：python main.py eval --verdict <判定文件>")
    return comp
