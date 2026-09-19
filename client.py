"""OpenAI 客户端工厂：统一网络策略（解决 Windows 系统代理劫持问题）。

背景：Windows 上若系统代理（如 Clash Verge）已开启但代理链路不可用，
httpx 默认读取系统代理，导致对可直连 API 的 TLS 握手超时（本项目踩过坑）。
而本项目所用 API（中科大 / New API 网关）均支持直连，因此默认强制直连：
    trust_env=False  → 忽略系统代理与环境变量代理

若将来某 API 确实必须走代理，在 .env 设置 USE_PROXY=true 即可关闭直连。
"""

from __future__ import annotations

from typing import Any

import httpx2

import config


def make_openai_client(
    base_url: str | None = None,
    api_key: str | None = None,
) -> Any:
    """创建 OpenAI 兼容客户端，统一应用直连策略。

    Args:
        base_url: API base URL；默认取 config.settings.openai_base_url。
        api_key: API Key；默认取 config.settings.openai_api_key。

    Returns:
        openai.OpenAI 实例。
    """
    from openai import OpenAI

    base_url = base_url or config.settings.openai_base_url
    api_key = api_key or config.settings.openai_api_key

    kwargs: dict[str, Any] = {}
    if not config.settings.use_proxy:
        # trust_env=False：完全忽略系统代理/环境变量代理，强制直连
        kwargs["http_client"] = httpx2.Client(trust_env=False)

    return OpenAI(base_url=base_url, api_key=api_key, **kwargs)
