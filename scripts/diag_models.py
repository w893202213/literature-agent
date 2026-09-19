"""模型延迟对比：测中科大 API 各可用模型的响应时间。

用法：python scripts/diag_models.py
在 API 高峰期很有用——找出当前最快的模型。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import make_openai_client  # noqa: E402

# 从 /v1/models 实测到的可用模型（按候选优先级排列）
MODELS = [
    "deepseek-v4-flash-ascend",
    "deepseek-flash",
    "glm-5.3-flash",
    "qwen3.5",
    "qwen3.6-chat",
    "qwen3.7-plus",
    "smart/default",
]


def main() -> None:
    client = make_openai_client()
    results: list[tuple[str, float, str]] = []
    for model in MODELS:
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "say hi in one word"}],
                max_tokens=10,
                temperature=0.0,
            )
            elapsed = time.time() - t0
            reply = resp.choices[0].message.content or ""
            print(f"  {model:<28} {elapsed:6.1f}s  回复: {reply!r}")
            results.append((model, elapsed, reply))
        except Exception as e:  # noqa: BLE001
            elapsed = time.time() - t0
            print(f"  {model:<28} {elapsed:6.1f}s  ❌ {type(e).__name__}")
            results.append((model, elapsed, f"FAIL {type(e).__name__}"))

    ok = [r for r in results if not r[2].startswith("FAIL")]
    if ok:
        best = min(ok, key=lambda r: r[1])
        print(f"\n最快可用模型: {best[0]} ({best[1]:.1f}s)")


if __name__ == "__main__":
    main()
