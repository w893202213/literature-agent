"""LLM API 最小请求诊断：测中科大 API 响应延迟。

用法：python scripts/diag_llm.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from client import make_openai_client  # noqa: E402


def main() -> None:
    print(f"model = {config.settings.model}")
    print(f"base_url = {config.settings.openai_base_url}")
    client = make_openai_client()
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=config.settings.model,
            messages=[{"role": "user", "content": "say hi in one word"}],
            max_tokens=10,
            temperature=0.0,
        )
        print(f"✅ 耗时 {time.time() - t0:.1f}s, 回复: {resp.choices[0].message.content!r}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ 耗时 {time.time() - t0:.1f}s, 失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
