"""综述初稿生成 + 引用核验（阶段 2，红线环节）。

红线（对齐 PROJECT_PLAN 第 5 节）：
- 综述里每条引用必须来自检索结果（论文清单），**禁止幻觉引用**；
- 引用格式 [编号]，编号对应论文清单；
- 生成后程序强制核验：所有引用编号必须在清单内，发现幻觉引用则带反馈重试。

设计（面试亮点）：
- **引用白名单机制**：把"检索到的论文"变成 prompt 里的引用白名单，
  LLM 只能引用清单内论文（白名单约束生成）+ 程序核验兜底（校验放行）
  = 双保险。Agent 类产品防幻觉引用的标准做法；
- 核验失败重试 1 次（把非法编号反馈给 LLM 修正），仍失败则返回 None 并记录。
"""

from __future__ import annotations

import re
from typing import Any

import config
from client import make_openai_client

REVIEW_SYSTEM_PROMPT = (
    "你是学术综述撰写助手。根据给定的研究主题和论文清单，撰写一篇结构完整的 related work 综述。\n"
    "结构要求：\n"
    "1. 开篇总起段：概述该领域的研究脉络与核心问题；\n"
    "2. 按方法流派分小节（用 ## 小节标题），每个小节综合多篇论文的异同与演进，不要逐篇罗列；\n"
    "3. 每篇被引论文至少展开 2-3 句：方法要点、关键发现、与同类工作的区别；\n"
    "4. 结尾小节总结领域现状与开放问题（可选）。\n"
    "篇幅要求：全文 1200-2000 字，内容充实有信息量，避免空泛套话。\n"
    "硬性要求：\n"
    "1. 只能引用论文清单中的论文，引用格式 [编号]，如 [1]、[2]；\n"
    "2. 禁止编造清单之外的任何文献（这是红线）；\n"
    "3. 输出 Markdown。\n"
)


def _link_for(paper_id: str) -> str:
    """根据论文 id 构造可溯源链接（arXiv 编号 / OpenAlex id）。"""
    if re.fullmatch(r"\d{4}\.\d{4,5}", paper_id):
        return f"https://arxiv.org/abs/{paper_id}"
    if paper_id.startswith("W"):
        return f"https://openalex.org/{paper_id}"
    return ""


def build_paper_list(extracted: dict[str, dict[str, Any]]) -> str:
    """构造论文清单（编号 + 标题 + 年份 + 方法摘要 + 链接）。"""
    lines: list[str] = []
    for i, pid in enumerate(sorted(extracted), 1):
        paper = extracted[pid]
        title = (paper.get("title") or "")[:120]
        year = paper.get("year") or ""
        method = (paper.get("method") or "")[:200]
        link = _link_for(pid)
        lines.append(f"[{i}] {title} ({year})")
        if method:
            lines.append(f"    方法: {method}")
        if link:
            lines.append(f"    链接: {link}")
        lines.append("")
    return "\n".join(lines)


def verify_references(text: str, n_papers: int) -> dict[str, Any]:
    """核验引用：文本中所有 [编号] 是否都在 1..n_papers 白名单内。

    Returns:
        {"citations": 去重排序的引用编号, "invalid": 非法编号, "ok": 是否全部合法}
    """
    cites = sorted({int(x) for x in re.findall(r"\[(\d+)\]", text)})
    invalid = [c for c in cites if not (1 <= c <= n_papers)]
    return {
        "citations": cites,
        "invalid": invalid,
        "ok": not invalid,
    }


def generate_review(
    topic: str,
    extracted: dict[str, dict[str, Any]],
    client: Any | None = None,
    max_retries: int = 2,
) -> tuple[str | None, dict[str, Any]]:
    """生成综述初稿（含引用核验与带反馈重试）。

    Returns:
        (综述 Markdown 文本, meta)。meta 含 attempts/invalid_refs/tokens/verified。
        全部重试仍产生幻觉引用时返回 (None, meta)——调用方记录失败不中断。
    """
    if not extracted:
        return None, {"error": "无论文可综述", "attempts": 0}
    if client is None:
        client = make_openai_client()

    paper_list = build_paper_list(extracted)
    user_msg = f"研究主题：{topic}\n\n论文清单（只可引用这些）：\n{paper_list}"
    meta: dict[str, Any] = {"attempts": 0, "invalid_refs": [], "tokens": 0, "error": ""}

    for attempt in range(1, max_retries + 1):
        meta["attempts"] = attempt
        try:
            resp = client.chat.completions.create(
                model=config.settings.model,
                temperature=0.3,  # 综述适度温度，避免过度模板化
                messages=[
                    {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=4000,  # 综述篇幅：1200-2000 字需要足够输出预算
                timeout=300,
            )
            text = resp.choices[0].message.content or ""
            if resp.usage:
                meta["tokens"] += int(resp.usage.total_tokens)
        except Exception as e:  # noqa: BLE001
            meta["error"] = f"API 错误: {e}"
            continue

        v = verify_references(text, len(extracted))
        if v["ok"]:
            meta["verified"] = v
            return text, meta

        # 幻觉引用：把非法编号反馈给 LLM，要求修正后重试
        meta["invalid_refs"] = v["invalid"]
        user_msg += (
            f"\n\n注意：上一版引用了白名单外的编号 {v['invalid']}，"
            "这是幻觉引用，禁止！请只引用清单内编号重新生成。"
        )

    meta["error"] = f"重试 {max_retries} 次仍存在幻觉引用: {meta.get('invalid_refs')}"
    return None, meta
