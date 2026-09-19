"""LLM Planner 验证：生成多组查询词。

用法：python scripts/verify_plan.py [主题]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.planner import build_plan  # noqa: E402


def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "vision-language knowledge distillation"
    print(f"=== LLM Planner 验证: {topic} ===")
    plan = build_plan(topic, max_papers=10)
    print(f"来源: {plan.get('notes')}")
    print(f"查询词 {len(plan.get('queries') or [])} 组:")
    for i, q in enumerate(plan.get("queries") or [], 1):
        print(f"  [{i}] {q}")


if __name__ == "__main__":
    main()
