"""PDF 下载工具（阶段 1）。

ArXiv 开放获取直下；下载结果写入 data/cache 以便复用（省流量、防限流）。
"""

from __future__ import annotations

from pathlib import Path

import requests

import config

# 浏览器 UA：兼容更多 OA 源（ACM/IEEE 反爬严格，协会站点通常接受）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch_pdf(pdf_url: str, out_path: Path | None = None) -> Path | None:
    """下载 PDF 到本地，返回保存路径；失败返回 None（不抛异常，交由上层跳过）。

    Args:
        pdf_url: PDF 直链（通常来自 ArXiv 搜索结果）。
        out_path: 保存路径；为 None 时按 URL 哈希存到 data/cache/pdfs/。

    Returns:
        保存后的本地路径；下载失败返回 None。
    """
    if out_path is None:
        out_path = config.settings.cache_dir / "pdfs" / f"{_url_hash(pdf_url)}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = requests.get(pdf_url, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path
    except requests.RequestException as e:
        print(f"[fetch_pdf] 下载失败 {pdf_url}: {e}")
        return None


def _url_hash(url: str) -> str:
    """URL → 短哈希，用作缓存文件名（避免非法字符与超长文件名）。"""
    import hashlib

    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
