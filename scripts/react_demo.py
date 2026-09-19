"""手写 ReAct loop demo（阶段 0）——理解原理，再对比 LangGraph。

目标：50-100 行内实现最简 ReAct：
1. 把工具描述写进 system prompt；
2. 循环：模型输出 Thought/Action/Action Input 或 Final Answer；
3. 解析输出 → 调用工具 → 把 Observation 追加回对话；
4. 直到模型给出 Final Answer 或达到最大步数。

本 demo 使用本地假工具“查天气”，不依赖真实 API 之外的东西。
与 LangGraph 版的对比结论（取舍）请记录到 README，面试时能讲清楚。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# 允许以脚本方式直接运行：把项目根加入 sys.path 以导入 config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402


def fake_weather_tool(city: str) -> str:
    """本地假工具：返回城市天气（用于验证 tool calling 链路）。"""
    fake_data = {"合肥": "晴 24°C", "北京": "多云 18°C", "上海": "小雨 22°C"}
    return fake_data.get(city, f"暂无{city}的天气数据")


# 工具描述（进入 prompt 的“说明书”）
TOOL_DESC = (
    "可用工具：\n"
    "- fake_weather_tool(city: str) -> str 查询指定城市天气，例如 fake_weather_tool('合肥')\n"
    "输出格式：\n"
    "Thought: <你的推理>\n"
    "Action: fake_weather_tool\n"
    "Action Input: 合肥\n"
    "（得到 Observation 后继续，直到给出）\n"
    "Final Answer: <最终答案>"
)

MAX_STEPS = 5


def run_react_demo(query: str = "查询合肥天气") -> str:
    """执行一次 ReAct 循环，返回最终答案。"""
    from client import make_openai_client

    client = make_openai_client()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "你是工具调用 Agent。\n" + TOOL_DESC},
        {"role": "user", "content": query},
    ]

    for step in range(MAX_STEPS):
        resp = client.chat.completions.create(
            model=config.settings.model,
            temperature=0.0,
            messages=messages,
        )
        text = resp.choices[0].message.content or ""
        print(f"--- step {step + 1} ---\n{text}\n")

        if "Final Answer" in text:
            return text.split("Final Answer", 1)[1].strip()

        # 解析 Action / Action Input
        action = re.search(r"Action:\s*(\w+)", text)
        action_input = re.search(r"Action Input:\s*([^\n]+)", text)
        if action and action_input:
            if action.group(1) == "fake_weather_tool":
                result = fake_weather_tool(action_input.group(1).strip().strip("\"'"))
            else:
                result = f"未知工具: {action.group(1)}"
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": f"Observation: {result}"})
        else:
            # 模型没按格式输出 → 提示后重试
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": "请按格式输出 Action 与 Action Input，或直接给出 Final Answer。",
            })

    return "(达到最大步数，未得到最终答案)"


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "查询合肥天气"
    print(run_react_demo(q))
