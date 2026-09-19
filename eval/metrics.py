"""评测指标计算（阶段 3）。

- recall：召回率（自动）
- datasets 重合率：列表字段自动判定（集合重合 ≥ 50% 视为正确）
- method / results：语义等价，生成对照表由人工判定（半自动评测）
- 成本/耗时：从落盘 meta.tokens 汇总

设计：评测是"半自动"的——机器能判的（datasets/召回）自动判，
需要语义判断的（method/results）生成对照表人工打勾，然后脚本算分。
"""

from __future__ import annotations

from typing import Any


def recall(retrieved: list[str], gold: list[str]) -> float:
    """召回率 = 评测集中被成功召回并提取的篇数 / 评测集总篇数。"""
    if not gold:
        return 0.0
    gold_set = set(gold)
    hit = sum(1 for pid in retrieved if pid in gold_set)
    return hit / len(gold)


def _norm(s: str) -> str:
    """数据集名归一化：小写 + 去标点/空白（消除 'Atari' vs 'Atari games'、
    引号字符差异等评测噪声——和标题归一化同一思想）。"""
    import re

    return re.sub(r"[\W_]+", "", str(s).lower())


def datasets_accuracy(pred: Any, gold: Any, threshold: float = 0.5) -> tuple[float, bool]:
    """datasets 字段判定：归一化后 |pred ∩ gold| / |gold|，重合率 ≥ threshold 视为正确。

    Returns:
        (重合率, 是否判定为正确)。
    """
    p = {_norm(x) for x in (pred or [])}
    g = {_norm(x) for x in (gold or [])}
    if not g:
        return (1.0, True) if not p else (0.0, False)
    score = len(p & g) / len(g)
    return (round(score, 2), score >= threshold)


def build_field_judgements(
    pred: dict[str, Any], gold: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """生成每篇论文的字段判定详情。

    - datasets：自动判定（重合率）；
    - method / results：语义任务，标记 PENDING 待人工核对。
    """
    return {
        "method": {
            "pred": str(pred.get("method") or "")[:150],
            "gold": str(gold.get("method") or "")[:150],
            "judgement": "PENDING",
        },
        "datasets": {
            "pred": list(pred.get("datasets") or []),
            "gold": list(gold.get("datasets") or []),
            "judgement": "AUTO",
            "score": datasets_accuracy(pred.get("datasets"), gold.get("datasets"))[0],
            "ok": datasets_accuracy(pred.get("datasets"), gold.get("datasets"))[1],
        },
        "results": {
            "pred": str(pred.get("results") or "")[:150],
            "gold": str(gold.get("results") or "")[:150],
            "judgement": "PENDING",
        },
    }


def field_accuracy_from_verdicts(
    rows: list[dict[str, Any]], key_fields: list[str] | None = None
) -> float:
    """根据已判定结果算字段准确率（method/results 由人工 verdict 标记 ok/ng）。

    Args:
        rows: build_comparison 的行，每行含 judgements（AUTO 自动 / PENDING 已由
              人工在 verdict 文件里改成 ok/ng）。

    Returns:
        0.0 ~ 1.0（参与判定的字段中正确的比例）。
    """
    fields = key_fields or ["method", "datasets", "results"]
    judged = 0
    correct = 0
    for row in rows:
        for f in fields:
            j = row.get("judgements", {}).get(f)
            if not j:
                continue
            if j.get("judgement") == "AUTO":
                judged += 1
                correct += 1 if j.get("ok") else 0
            elif j.get("judgement") in ("ok", "ng"):
                judged += 1
                correct += 1 if j["judgement"] == "ok" else 0
    return round(correct / judged, 3) if judged else 0.0
