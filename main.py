"""文献综述自动化 Agent —— CLI 入口。

用法：
    python main.py demo-weather     # 阶段 0：LLM 调用假工具的最小闭环 demo（手写 ReAct）
    python main.py demo-langgraph   # 阶段 0：同上，LangGraph 版（ToolNode + 状态图）
    python main.py search "vision-language knowledge distillation"   # 阶段 1：搜索论文
    python main.py run "研究主题"    # 阶段 2：端到端跑完整流程
    python main.py eval              # 阶段 3：跑评测

说明：各子命令按阶段逐步实现，未实现前打印 TODO 提示。
"""

from __future__ import annotations

import argparse
import sys

import config


def cmd_demo_weather(args: argparse.Namespace) -> int:
    """阶段 0 验收项：LLM 能调用一个本地假工具（如查合肥天气）。

    实际实现复用 scripts/react_demo.py 的手写 ReAct loop。
    """
    from scripts.react_demo import run_react_demo

    print(run_react_demo("查询合肥天气"))
    return 0


def cmd_demo_langgraph(args: argparse.Namespace) -> int:
    """阶段 0 验收项（LangGraph 版）：ToolNode + 状态图调用假工具。

    与 demo-weather（手写 ReAct）做对比，取舍结论见 README「阶段 0 结论」。
    """
    from agent.graph import run_demo_langgraph

    print(run_demo_langgraph("查询合肥天气"))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """阶段 1：按主题搜索→筛选→逐篇处理（下载→解析→提取→落盘）。"""
    from tools.pipeline import run_topic_pipeline

    summary = run_topic_pipeline(
        args.topic, max_papers=args.max, source=args.source,
        min_score=args.min_score, year_from=args.year_from,
    )
    print(f"结果: 筛选后 {summary['filtered']} 篇，成功 {summary['processed']} 篇，失败 {summary['failed']} 篇")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """阶段 2：LangGraph 图版端到端流水线（含 JSONL 日志）。"""
    from agent.graph import run_agent_pipeline

    result = run_agent_pipeline(
        args.topic, max_papers=args.max, source=args.source,
        min_score=args.min_score, year_from=args.year_from,
    )
    print(f"run_id: {result['run_id']}")
    print(f"搜索 {result['searched']} → 筛选 {result['filtered']} → 成功 {result['ok']} / 失败 {result['failed']}")
    print(f"各阶段耗时: {result['step_timings']}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """阶段 3：评测（对照表 / 人工判定算分 / 召回率）。"""
    from eval.run_eval import run_eval, run_recall_eval, score_from_verdict

    if args.recall:
        run_recall_eval(per_page=args.per_page)
    elif args.verdict:
        score_from_verdict(args.verdict)
    else:
        run_eval()
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """阶段 3：启动 Gradio Demo（本机 127.0.0.1:7860）。"""
    from app.demo import launch

    print("启动 Gradio Demo：http://127.0.0.1:7860 （Ctrl+C 退出）")
    launch()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="literature-agent",
        description="文献综述自动化 Agent：搜索 → 筛选 → 解析 → 提取 → 综述",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo-weather", help="阶段 0 最小闭环 demo（手写 ReAct）")
    p_demo.set_defaults(func=cmd_demo_weather)

    p_demo_lg = sub.add_parser("demo-langgraph", help="阶段 0 demo（LangGraph 版）")
    p_demo_lg.set_defaults(func=cmd_demo_langgraph)

    p_search = sub.add_parser("search", help="搜索论文并跑单篇流水线（阶段 1）")
    p_search.add_argument("topic", help="研究主题关键词")
    p_search.add_argument("--max", type=int, default=10, help="最多处理篇数（默认 10）")
    p_search.add_argument("--source", choices=["openalex", "arxiv"], default="openalex",
                          help="搜索源（默认 openalex，更稳）")
    p_search.add_argument("--min-score", type=int, default=3, choices=[1, 2, 3, 4, 5],
                          help="LLM 相关性打分阈值（默认 3）")
    p_search.add_argument("--year-from", type=int, default=None,
                          help="只保留该年份及以后的论文")
    p_search.set_defaults(func=cmd_search)

    p_run = sub.add_parser("run", help="阶段 2：LangGraph 图版端到端流水线")
    p_run.add_argument("topic", help="研究主题")
    p_run.add_argument("--max", type=int, default=10, help="搜索候选上限（默认 10）")
    p_run.add_argument("--source", choices=["openalex", "arxiv"], default="openalex")
    p_run.add_argument("--min-score", type=int, default=3, choices=[1, 2, 3, 4, 5])
    p_run.add_argument("--year-from", type=int, default=None)
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="阶段 3：评测")
    p_eval.add_argument("--verdict", default=None,
                        help="人工判定文件路径（读它算字段准确率）")
    p_eval.add_argument("--recall", action="store_true",
                        help="跑召回率评测（按评测集主题搜索）")
    p_eval.add_argument("--per-page", type=int, default=100,
                        help="召回率评测的搜索条数（默认 100）")
    p_eval.set_defaults(func=cmd_eval)

    p_demo = sub.add_parser("demo", help="阶段 3：启动 Gradio Demo")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)

    # 阶段 0 自检：环境与配置是否就绪
    if not config.settings.check_api_ready():
        print("⚠️  未检测到 .env 中的 API 配置，请先：")
        print("    1) copy .env.example .env")
        print("    2) 填入 OPENAI_API_KEY（中科大 API）")
        print("    demo 类命令仍需配置才能验证协议连通。")
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
