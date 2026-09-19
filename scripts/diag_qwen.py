"""验证 qwen3.5 模型的实际输出内容。

用法：python scripts/diag_qwen.py
max_tokens 调大，打印完整响应结构，确认 content 是否为 None。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2  # noqa: E402
from openai import OpenAI  # noqa: E402

import config  # noqa: E402


def main() -> None:
    client = OpenAI(
        base_url=config.settings.openai_base_url,
        api_key=config.settings.openai_api_key,
        http_client=httpx2.Client(trust_env=False),
    )
    t0 = time.time()
    resp = client.chat.completions.create(
        model="qwen3.5",
        messages=[{"role": "user", "content": "用一句话介绍知识蒸馏。"}],
        max_tokens=200,
        temperature=0.2,
        timeout=90,
    )
    print(f"耗时 {time.time()-t0:.1f}s")
    msg = resp.choices[0].message
    print(f"content = {msg.content!r}")
    print(f"has tool_calls = {bool(msg.tool_calls)}")
    print(f"finish_reason = {resp.choices[0].finish_reason}")
    # 打印 message 全部字段（排查 content None 原因）
    print(f"message 字段: {msg.model_dump(exclude_none=False)}")


if __name__ == "__main__":
    main()
