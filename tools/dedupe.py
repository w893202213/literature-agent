"""论文去重工具（阶段 1）。

策略（对齐 PROJECT_PLAN 第 5 节）：
1. 标题归一化：小写 / 去空白 / 去 arXiv 版本号 / 去常见噪声词；
2. embedding 相似度阈值（默认 0.9）做语义去重。

阶段 1 先实现标题归一化（纯规则、零依赖）；
embedding 去重依赖可选安装的 sentence-transformers，作为 TODO。
"""

from __future__ import annotations

import re

import config

# arXiv 版本号：如 "2301.12345v3" -> "2301.12345"
_VERSION_RE = re.compile(r"(\d{4}\.\d{4,5})v\d+", re.IGNORECASE)
_NOISE = re.compile(r"[\W_]+", re.UNICODE)  # 非单词字符


def normalize_title(title: str) -> str:
    """标题归一化：小写、去空白、去 arXiv 版本号、去标点噪声。

    >>> normalize_title("Foo-Bar: A Study v2")
    'foobarastudyv2'
    """
    t = _VERSION_RE.sub(r"\1", title)
    t = t.lower()
    t = _NOISE.sub("", t)
    return t


def exact_duplicate(titles: list[str]) -> list[tuple[int, int]]:
    """基于归一化标题找出完全重复的 (原下标, 重复下标) 对。"""
    seen: dict[str, int] = {}
    dup_pairs: list[tuple[int, int]] = []
    for i, title in enumerate(titles):
        key = normalize_title(title)
        if key in seen:
            dup_pairs.append((seen[key], i))
        else:
            seen[key] = i
    return dup_pairs


# TODO(阶段2): embedding 语义去重
#   def semantic_duplicates(texts: list[str],
#                           threshold: float = config.settings.dedupe_threshold
#                           ) -> list[tuple[int, int, float]]:
#       """返回 (原下标, 重复下标, 相似度)。依赖 sentence-transformers + chroma。"""
