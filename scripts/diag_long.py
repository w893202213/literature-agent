"""长输入请求耗时诊断：测 qwen3.5 处理 12k 字符输入的速度。

用法：python scripts/diag_long.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2  # noqa: E402
from openai import OpenAI  # noqa: E402

import config  # noqa: E402

# 模拟 12k 字符论文正文
LONG_TEXT = (
    "This is a research paper about knowledge distillation. "
    "The student model learns from the teacher model's soft outputs. "
    "We evaluate on ImageNet and CIFAR-100. "
) * 300  # ≈ 11k+ 字符


def main() -> None:
    print(f"输入长度: {len(LONG_TEXT)} 字符")
    client = OpenAI(
        base_url=config.settings.openai_base_url,
        api_key=config.settings.openai_api_key,
        http_client=httpx2.Client(trust_env=False),
    )
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=config.settings.model,
            messages=[
                {"role": "system", "content": "提取论文信息，只输出 JSON。"},
                {"role": "user", "content": LONG_TEXT},
            ],
            max_tokens=1500,
            temperature=0.2,
            timeout=240,
        )
        elapsed = time.time() - t0
        content = resp.choices[0].message.content or ""
        print(f"✅ 耗时 {elapsed:.1f}s, 输出 {len(content)} 字符")
        print(f"开头: {content[:100]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ 耗时 {time.time()-t0:.1f}s, {type(e).__name__}: {str(e)[:120]}")


if __name__ == "__main__":
    main()
