"""全局配置模块：从 .env 加载所有敏感信息与模型参数，集中管理。

用法：`from config import OPENAI_BASE_URL, MODEL` 或 `from config import settings`。
所有工具/Agent 模块一律从这里取配置，不要散落硬编码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（本文件所在目录）
ROOT = Path(__file__).resolve().parent

# 加载 .env（不存在时静默跳过，保证测试环境也能 import）
load_dotenv(ROOT / ".env")


def _get_env(key: str, default: str = "") -> str:
    """读取环境变量并去除首尾空白。"""
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Settings:
    """集中管理全部配置项。"""

    # ---- LLM API ----
    openai_base_url: str = _get_env("OPENAI_BASE_URL", "https://api.llm.ustc.edu.cn/v1")
    openai_api_key: str = _get_env("OPENAI_API_KEY")
    model: str = _get_env("MODEL", "deepseek-v4-pro")

    # ---- 备用 API（限流/降级时切换）----
    fallback_base_url: str = _get_env("FALLBACK_BASE_URL")
    fallback_api_key: str = _get_env("FALLBACK_API_KEY")
    fallback_model: str = _get_env("FALLBACK_MODEL", "deepseek-v4-pro")

    # ---- Semantic Scholar ----
    s2_api_key: str = _get_env("S2_API_KEY")

    # ---- ArXiv（海外服务，受限出口易 429，可走本地代理）----
    arxiv_proxy: str = _get_env("ARXIV_PROXY")

    # ---- OpenAlex（mailto 进"礼貌池"，显著提升限流配额）----
    openalex_mailto: str = _get_env("OPENALEX_MAILTO")

    # ---- LLM 采样 ----
    temperature: float = float(_get_env("LLM_TEMPERATURE", "0.2"))

    # ---- 网络 ----
    use_proxy: bool = _get_env("USE_PROXY", "false").lower() in ("1", "true", "yes")

    # ---- 路径 ----
    data_dir: Path = ROOT / "data"
    papers_dir: Path = ROOT / "data" / "papers"
    cache_dir: Path = ROOT / "data" / "cache"
    index_path: Path = ROOT / "data" / "index.json"
    logs_dir: Path = ROOT / "logs"

    # ---- 运行参数 ----
    max_papers: int = 50            # 单主题论文数上限（成本护栏）
    extract_max_retries: int = 2    # 结构化提取失败重试次数
    dedupe_threshold: float = 0.9   # embedding 去重相似度阈值
    arxiv_request_interval: float = 3.0  # arXiv 请求最小间隔（秒），遵守速率限制

    def ensure_dirs(self) -> None:
        """确保运行时目录存在（幂等）。"""
        for d in (self.data_dir, self.papers_dir, self.cache_dir,
                  self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def check_api_ready(self) -> bool:
        """阶段 0 自检：主力 API 是否已配置。"""
        return bool(self.openai_api_key and self.openai_base_url)


settings = Settings()

# 常用常量别名（向后兼容的简便写法）
OPENAI_BASE_URL = settings.openai_base_url
OPENAI_API_KEY = settings.openai_api_key
MODEL = settings.model

# 各模块相对引用时用 ROOT 定位资源
__all__ = ["Settings", "settings", "ROOT", "OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL"]
