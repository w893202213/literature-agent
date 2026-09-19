"""评测集批量提取：按评测集的 arXiv ID 直接提取（跳过搜索）。

用法：python scripts/eval_extract.py [起始下标] [数量]
从评测集读 arxiv_id → 构造 PaperCandidate（arXiv PDF 直链）→ process_one_paper。
支持分批（如先跑 0-10，再 10-20），中断后可重跑（已落盘的跳过）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import load_dataset  # noqa: E402
from tools.io import run_id  # noqa: E402
from tools.models import PaperCandidate  # noqa: E402
from tools.pipeline import process_one_paper  # noqa: E402


def main() -> None:
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    dataset = load_dataset()
    batch = dataset[start : start + count]
    print(f"评测集 {len(dataset)} 篇，本批处理 [{start}, {start + len(batch)})")

    run = run_id()
    ok, fail = 0, 0
    for p in batch:
        aid = p["arxiv_id"]
        # 已落盘则跳过（可断点续跑）
        if (Path("data/papers") / f"{aid}.json").exists():
            print(f"[eval_extract] {aid} 已提取，跳过")
            ok += 1
            continue
        cand = PaperCandidate(
            paper_id=aid,
            title=p.get("title", aid),
            pdf_url=f"https://arxiv.org/pdf/{aid}.pdf",
            source="eval_dataset",
        )
        rec = process_one_paper(cand, run)
        if rec["status"] == "ok":
            ok += 1
        else:
            fail += 1
    print(f"\n=== 本批完成: 成功 {ok} / 失败 {fail} ===")


if __name__ == "__main__":
    main()
