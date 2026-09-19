"""代理生效诊断：对比直连与代理的出口 IP。

用法：python scripts/diag_proxy.py
通过 https://api.ipify.org 查看出口 IP，确认 ARXIV_PROXY 是否真正生效。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import config  # noqa: E402


def _ip(proxies: dict | None) -> str:
    try:
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=15)
        return r.text.strip()
    except Exception as e:  # noqa: BLE001
        return f"FAIL: {e}"


def main() -> None:
    print(f"config.settings.arxiv_proxy = {config.settings.arxiv_proxy!r}")
    print(f"直连出口 IP: {_ip(None)}")
    if config.settings.arxiv_proxy:
        p = {"http": config.settings.arxiv_proxy, "https": config.settings.arxiv_proxy}
        print(f"代理出口 IP: {_ip(p)}")


if __name__ == "__main__":
    main()
