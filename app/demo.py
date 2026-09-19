"""Gradio Demo（阶段 3）：输入主题 → 显示进度 → 对比表 + 综述。

设计：
- 长任务放后台队列（demo.queue + generator 逐步 yield），页面不转圈；
- 进度分阶段报告：搜索 → 筛选 → 逐篇处理(i/n) → 表格 → 综述；
- 复用 tools 层（_search/filter/process/summarize/review），不依赖图，
  以便逐步暴露进度；
- 所有输出（表格/综述）同时落盘到 data/outputs/。

启动：python -m app.demo  （或 python main.py demo）
访问：http://127.0.0.1:7860
"""

from __future__ import annotations

import json

import gradio as gr

import config


def _md_table_to_rows(md: str) -> list[list[str]]:
    """把 Markdown 表格解析成二维列表（供 gr.Dataframe 展示）。"""
    rows: list[list[str]] = []
    for line in (md or "").splitlines():
        line = line.strip()
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
    return rows


def _run_pipeline(topic: str, max_papers: int, min_score: int, year_from: int):
    """带进度的流水线（generator：yield (状态, 对比表rows, 综述md)）。"""
    from agent.planner import build_plan
    from tools.io import run_id
    from tools.pipeline import _search, process_one_paper
    from tools.rank import filter_candidates
    from tools.review import generate_review
    from tools.summarize import summarize_papers

    run = run_id()
    yield "🚀 开始：LLM 规划搜索词...", [], ""

    # LLM Planner 生成多组查询词（覆盖主题不同子方向，失败降级单查询）
    plan = build_plan(topic, max_papers=max_papers, year_from=year_from)
    queries = plan.get("queries") or [topic]
    candidates = _search(topic, "openalex", max_papers, year_from=year_from,
                         queries=queries)
    if not candidates:
        yield (
            "⚠️ 搜索到 0 篇候选。可能原因：\n"
            "1. **网络限流**：OpenAlex/arXiv 临时限流，等 1-2 分钟重试；\n"
            "2. **查询词过窄**：试试更宽泛的关键词（建议英文），或调低起始年份；\n"
            "3. 该主题确实没有符合年份范围的开放获取论文。",
            [],
            "",
        )
        return
    yield f"🔍 搜索到 {len(candidates)} 篇候选（{year_from} 年及以后），正在 LLM 相关性筛选...", [], ""
    kept, stats = filter_candidates(
        topic, candidates, min_score=min_score, year_from=year_from
    )
    yield f"🎯 筛选后保留 {len(kept)} 篇（打分 {stats.get('scored', 0)} 篇）", [], ""

    extracted: dict[str, dict] = {}
    total = len(kept)
    for i, c in enumerate(kept, 1):
        yield f"⚙️ 处理第 {i}/{total} 篇：{c.title[:45]}...", [], ""
        rec = process_one_paper(c, run)
        if rec["status"] == "ok":
            pf = config.settings.papers_dir / f"{c.paper_id}.json"
            if pf.exists():
                extracted[c.paper_id] = json.loads(
                    pf.read_text(encoding="utf-8")
                ).get("paper", {})

    if not extracted:
        yield "⚠️ 没有成功提取的论文（可能都是付费/无 OA PDF），请换主题或调参数。", [], ""
        return

    yield f"✅ 提取完成 {len(extracted)} 篇，生成对比表...", [], ""
    result = summarize_papers(topic, extracted, run)
    table_rows = _md_table_to_rows(result["tables"].get("markdown", ""))

    yield "✍️ 撰写综述初稿（引用白名单核验中）...", table_rows, ""
    text, rmeta = generate_review(topic, extracted)
    if text:
        rv = config.settings.data_dir / "outputs" / f"{run}_review.md"
        rv.write_text(f"# {topic} 综述初稿（run={run}）\n\n{text}\n", encoding="utf-8")
    review = text or "❌ 综述生成失败（幻觉引用重试耗尽）"

    yield (
        f"🎉 全部完成！run={run}｜表格: {result['files']['markdown']}",
        table_rows,
        review,
    )


# 页面美化（Gradio 6：theme/css 在 launch() 传入）
CSS = """
.gradio-container { max-width: 1100px !important; margin: auto !important; }
body, .gradio-container, .prose, .markdown, table, td, th, input, button, label {
    font-family: "Times New Roman", Times, serif !important;
}
#hero {
    text-align: center;
    padding: 28px 20px 10px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    color: white;
    margin-bottom: 14px;
}
#hero h1 { font-size: 2.1em; margin: 0 0 6px; font-family: "Times New Roman", serif !important; }
#hero p { opacity: 0.9; margin: 4px 0; }
.card {
    background: #f8f9fc;
    border: 1px solid #e4e7f0;
    border-radius: 12px;
    padding: 14px 18px;
}
#status-box {
    border-left: 4px solid #667eea;
    background: #f0f2ff;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 10px 0;
}
"""


def build_demo() -> gr.Blocks:
    """构建 Gradio 应用。"""
    with gr.Blocks(title="文献综述自动化 Agent") as demo:
        gr.HTML(
            "<div id='hero'><h1>📚 文献综述自动化 Agent</h1>"
            "<p>输入主题 → 自动搜索、筛选、提取 → 生成方法对比表与综述初稿</p></div>"
        )
        with gr.Row():
            topic = gr.Textbox(
                label="研究主题",
                placeholder="如：vision-language knowledge distillation",
                scale=3,
            )
            year_from = gr.Number(
                label="起始年份（含）", value=2023, minimum=2015, maximum=2026,
                precision=0, scale=1,
            )
        with gr.Row():
            max_papers = gr.Slider(3, 20, value=8, step=1, label="搜索候选上限", scale=1)
            min_score = gr.Dropdown([2, 3, 4], value=3, label="相关性阈值（1-5）", scale=1)
        btn = gr.Button("🚀 开始", variant="primary")
        status = gr.Markdown("就绪", elem_id="status-box")

        gr.Markdown("---")
        # 上下布局：对比表在上（Dataframe 列宽可控），综述在下
        with gr.Column(elem_classes="card"):
            gr.Markdown("### 📊 方法对比表")
            table_md = gr.Dataframe(
                headers=["论文", "年份", "一句话方法", "数据集", "关键结果", "亮点"],
                column_widths=[220, 60, 240, 180, 260, 240],
                label=None,
                interactive=False,
            )
            gr.Markdown("（同时保存为 Markdown/CSV，见运行日志）")
        with gr.Column(elem_classes="card"):
            gr.Markdown("### ✍️ 综述初稿")
            review_md = gr.Markdown("（运行后显示，同时保存为 Markdown）")

        btn.click(
            _run_pipeline,
            inputs=[topic, max_papers, min_score, year_from],
            outputs=[status, table_md, review_md],
        )

    demo.queue()  # 长任务后台队列，页面不转圈
    return demo


def launch() -> None:
    """本机启动 demo（验收标准：本机可访问）。"""
    app = build_demo()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=gr.themes.Soft(),
        css=CSS,
        show_error=True,
    )


if __name__ == "__main__":
    launch()
