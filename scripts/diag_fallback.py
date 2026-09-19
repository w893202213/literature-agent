"""LLM 通道快速诊断：测主备 API + 候选模型的响应延迟。

用法：python scripts/diag_fallback.py
带 45s 超时快速失败，避免高峰期挂起。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2  # noqa: E402
from openai import OpenAI  # noqa: E402

import config  # noqa: E402

TIMEOUT = 45


def test(base_url: str, api_key: str, model: str, label: str) -> None:
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=httpx2.Client(trust_env=False),
    )
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "say hi in one word"}],
            max_tokens=10,
            temperature=0.0,
            timeout=TIMEOUT,
        )
        print(f"  {label:<10} {model:<26} {time.time()-t0:6.1f}s ✅ {resp.choices[0].message.content!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label:<10} {model:<26} {time.time()-t0:6.1f}s ❌ {type(e).__name__}: {str(e)[:80]}")


def main() -> None:
    print("=== LLM 通道延迟诊断（45s 超时）===")
    # 备选网关（用户自部署 New API）
    if config.settings.fallback_api_key:
        test(config.settings.fallback_base_url, config.settings.fallback_api_key,
             config.settings.fallback_model, "FALLBACK")
    # 中科大 + 其他候选模型
    test(config.settings.openai_base_url, config.settings.openai_api_key,
         "glm-5.3-flash", "USTC")
    test(config.settings.openai_base_url, config.settings.openai_api_key,
         "qwen3.5", "USTC")


if __name__ == "__main__":
    main()
