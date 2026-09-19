"""任务规划模块：把用户主题拆成可执行计划（Agent 四大部件之一）。

职责：
- 生成 3-5 组搜索关键词（覆盖主题的不同子方向：核心方法/代表性术语/变体表述）；
- 设定过滤条件（年份、篇数上限）；
- 失败降级：LLM 规划失败 → 规则版（单查询）。

设计（面试亮点）：
- **LLM 规划优先 + 规则降级**：LLM 生成多查询（覆盖宽），失败/不稳定时
  退化为规则版（保底可用）——"智能优先、规则兜底"的经典模式；
- 多查询必要性有评测数据支撑（P16）：单查询 AND 语义召回不了新论文
  （召回率 0%），多查询才达标（84.6%）——Planner 的职责被评测验证。
"""

from __future__ import annotations

import json
import re
from typing import Any

import config
from client import make_openai_client

PLANNER_SYSTEM_PROMPT = (
    "你是学术文献检索规划助手。给定一个研究主题，生成 3-5 组论文搜索关键词。\n"
    "要求：\n"
    "1. 每组关键词覆盖主题的一个子方向（核心方法、代表性术语、变体表述、相邻领域）；\n"
    "2. 用英文，词与词之间空格分隔（如 'knowledge distillation vision transformer'）；\n"
    "3. 各组之间要有区分度，避免重复；\n"
    "4. 不要包含年份（由外层过滤处理）。\n"
    "只输出一个 JSON 对象，形如 {\"queries\": [\"query1\", \"query2\", \"query3\"]}，"
    "不要输出任何其他内容。"
)


def build_plan_rule_based(topic: str, max_papers: int = 50) -> dict[str, Any]:
    """规则版规划：单一查询词 + 默认过滤条件（降级保底）。"""
    return {
        "queries": [topic.strip()],
        "max_papers": max_papers,
        "year_from": None,
        "venue_whitelist": [],
        "notes": "规则版规划（LLM 规划失败时的降级）",
    }


def _parse_queries(raw: str) -> list[str]:
    """宽松解析 LLM 规划输出：JSON 优先，正则兜底。"""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    # 1. JSON 解析
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            queries = obj.get("queries")
            if isinstance(queries, list):
                clean = [str(q).strip() for q in queries if str(q).strip()]
                return clean[:6]
    except json.JSONDecodeError:
        pass
    # 2. 正则兜底：提取引号字符串
    quoted = re.findall(r'"([^"]{3,120})"', s)
    if quoted:
        return quoted[:6]
    return []


def build_plan_llm(
    topic: str, client: Any | None = None, max_retries: int = 2
) -> dict[str, Any]:
    """LLM 版规划：生成多组查询词（3-5 组），失败返回空 queries（调用方降级）。"""
    if client is None:
        client = make_openai_client()

    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=config.settings.model,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": f"研究主题：{topic}"},
                ],
                max_tokens=512,
                timeout=120,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = f"API 错误: {e}"
            continue

        queries = _parse_queries(raw)
        if queries:
            return {"queries": queries, "source": "llm", "notes": "LLM 规划（多查询）"}
        last_err = f"解析失败 (attempt {attempt})"

    print(f"[planner] LLM 规划失败（{max_retries} 次重试）: {last_err}")
    return {"queries": [], "source": "llm_failed", "notes": "LLM 规划失败"}


def build_plan(
    topic: str,
    seed_papers: list[str] | None = None,
    max_papers: int = 50,
    year_from: int | None = None,
) -> dict[str, Any]:
    """统一入口：LLM 规划优先，失败/种子论文时降级规则版。"""
    plan = build_plan_llm(topic)
    if not plan.get("queries"):
        plan = build_plan_rule_based(topic, max_papers)
    plan["max_papers"] = max_papers
    plan["year_from"] = year_from
    plan["venue_whitelist"] = plan.get("venue_whitelist", [])
    return plan
