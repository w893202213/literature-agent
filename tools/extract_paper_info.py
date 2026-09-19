"""LLM 结构化提取工具（阶段 1）。

流程：全文截断 → few-shot 提示 → LLM 输出 → JSON 解析 → Schema 校验 →
失败重试（最多 config.settings.extract_max_retries 次，低温保证稳定）。

三重保险（对齐 PROJECT_PLAN 第 5 节）：JSON Schema + 低温 + few-shot + 校验重试。
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

import config
from tools.schemas import (
    EXTRACT_SYSTEM_PROMPT,
    PAPER_INFO_SCHEMA,
    validate_paper_info,
)


def _build_user_prompt(text: str) -> str:
    """构造提取 prompt：few-shot 示例 + 正文。"""
    parts: list[str] = []
    if config is not None:  # FEWSHOT_EXAMPLES 在阶段 1 填充
        from tools.schemas import FEWSHOT_EXAMPLES

        if FEWSHOT_EXAMPLES:
            parts.append("参考示例：\n" + json.dumps(FEWSHOT_EXAMPLES, ensure_ascii=False))
    parts.append("论文全文如下：\n" + text)
    parts.append("\n请输出符合上述 JSON Schema 的 JSON 对象。")
    return "\n\n".join(parts)


def _parse_json_loose(raw: str) -> dict[str, Any] | None:
    """宽松解析 LLM 输出：去掉代码块标记后 json.loads；失败返回 None。"""
    s = raw.strip()
    # 去掉 ```json ... ``` 包装
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def extract_paper_info(
    full_text: str,
    client: OpenAI | None = None,
    max_tokens: int = 1500,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """从论文全文提取结构化 PaperInfo。

    Returns:
        (paper_info, meta)，其中 paper_info 为合法 PaperInfo 或 None（全部重试失败）；
        meta 记录 {attempts, error, input_chars} 供日志/成本统计。
    """
    if client is None:
        from client import make_openai_client

        client = make_openai_client()

    from tools.parse_pdf import truncate_text

    text = truncate_text(full_text)
    meta: dict[str, Any] = {"attempts": 0, "error": "", "input_chars": len(text),
                            "tokens": 0}

    for attempt in range(1, config.settings.extract_max_retries + 1):
        meta["attempts"] = attempt
        try:
            resp = client.chat.completions.create(
                model=config.settings.model,
                temperature=config.settings.temperature,  # 低温保证 JSON 稳定
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(text)},
                ],
                max_tokens=max_tokens,
                timeout=180,  # 单次请求上限 3 分钟：超时快速失败走重试，避免挂死流水线
            )
            raw = resp.choices[0].message.content or ""
            if resp.usage:
                meta["tokens"] += int(resp.usage.total_tokens)  # 成本统计（落盘 meta）
        except Exception as e:  # noqa: BLE001 —— API 错误/超时重试
            meta["error"] = f"API 错误: {e}"
            continue

        obj = _parse_json_loose(raw)
        if obj is None:
            meta["error"] = f"JSON 解析失败 (attempt {attempt})"
            continue

        ok, err = validate_paper_info(obj)
        if ok:
            meta["error"] = ""
            return obj, meta
        meta["error"] = f"Schema 校验失败: {err} (attempt {attempt})"

    return None, meta


# TODO(阶段1): 若持续失败，可让 LLM 输出“修复说明”，第 2 次重试时带回原错误
#   信息（self-correct 循环），进一步提升成功率。
