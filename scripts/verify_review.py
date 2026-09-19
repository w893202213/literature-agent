"""综述初稿验证：用已落盘论文生成综述 + 引用核验。

用法：python scripts/verify_review.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.review import generate_review, verify_references  # noqa: E402


def load_extracted() -> dict[str, dict]:
    extracted: dict[str, dict] = {}
    for f in sorted(glob.glob("data/papers/*.json")):
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        extracted[data["arxiv_id"]] = data.get("paper", {})
    return extracted


def main() -> None:
    extracted = load_extracted()
    print(f"已加载 {len(extracted)} 篇\n")
    text, meta = generate_review("Knowledge Distillation 综述测试", extracted)
    print(f"attempts={meta['attempts']}, tokens={meta['tokens']}, "
          f"invalid={meta['invalid_refs']}")
    if text:
        v = verify_references(text, len(extracted))
        print(f"最终核验: citations={v['citations']}, ok={v['ok']}\n")
        print("--- 综述初稿（前 1200 字符）---")
        print(text[:1200])


if __name__ == "__main__":
    main()
