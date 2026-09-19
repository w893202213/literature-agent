"""对比表格验证：用已落盘论文生成方法对比表。

用法：python scripts/verify_summarize.py
从 data/papers/*.json 读取提取结果 → summarize_papers → 打印表格。
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.summarize import summarize_papers  # noqa: E402


def load_extracted() -> dict[str, dict]:
    extracted: dict[str, dict] = {}
    for f in sorted(glob.glob("data/papers/*.json")):
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        extracted[data["arxiv_id"]] = data.get("paper", {})
    return extracted


def main() -> None:
    extracted = load_extracted()
    print(f"已加载 {len(extracted)} 篇提取结果\n")
    result = summarize_papers("Prompt Distillation 主题测试", extracted, "verify")
    print("--- Markdown 表格（前 15 行）---")
    print("\n".join(result["tables"]["markdown"].splitlines()[:15]))
    print("\n--- 导出的文件 ---")
    for k, v in result["files"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
