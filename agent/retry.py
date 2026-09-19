"""统一重试与降级工具（基础设施，阶段 0 起可用）。

- 网络类调用统一加指数退避重试（tenacity）；
- LLM API 主通道失败时自动降级到备选通道（中科大 ↔ New API 网关）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential

import config

logger = logging.getLogger("lit-agent")
T = TypeVar("T")

# 常见的可重试异常类型（网络抖动/限流/5xx）
RETRYABLE_EXC = (ConnectionError, TimeoutError, IOError)

# 统一重试策略：最多 3 次，指数退避 1s → 2s → 4s，带 jitter 防雪崩
network_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=tenacity.retry_if_exception_type(RETRYABLE_EXC),
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
)


def with_retry(fn: Callable[..., T]) -> Callable[..., T]:
    """给网络/API 调用套统一重试装饰器。用法：`@with_retry`。"""
    return network_retry(fn)


class LLMClient:
    """LLM 客户端包装：主 API 失败自动降级到备用 API（New API 网关）。

    阶段 1 用于结构化提取等所有 LLM 调用；
    阶段 2 起记录 token/成本到日志。
    """

    def __init__(self) -> None:
        self._primary = self._make_client(
            config.settings.openai_base_url, config.settings.openai_api_key
        )
        self._fallback = self._make_client(
            config.settings.fallback_base_url, config.settings.fallback_api_key
        ) if config.settings.fallback_api_key else None

    @staticmethod
    def _make_client(base_url: str, api_key: str) -> Any:
        from client import make_openai_client

        return make_openai_client(base_url=base_url, api_key=api_key)

    @network_retry
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """调主 API；失败自动切备用 API，返回 assistant 文本内容。"""
        model = kwargs.pop("model", config.settings.model)
        try:
            return self._chat_with(self._primary, model, messages, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("主 API 失败(%s)，尝试备用 API…", e)
            if self._fallback is None:
                raise
            fallback_model = kwargs.pop(
                "fallback_model", config.settings.fallback_model
            )
            return self._chat_with(
                self._fallback, fallback_model, messages, **kwargs
            )

    @staticmethod
    def _chat_with(client: Any, model: str, messages: list[dict[str, str]],
                   **kwargs: Any) -> str:
        resp = client.chat.completions.create(
            model=model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""
