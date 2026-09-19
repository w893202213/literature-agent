"""阶段 2 端到端验收：检查表格/综述/日志/token 统计。

用法：python scripts/verify_stage2.py <run_id>
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.logger import read_log, summarize_log  # noqa: E402


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else "20260918_144354_25f650"
    data = Path("data")

    print(f"=== 阶段 2 验收: run={run_id} ===\n")

    # 1. 对比表
    md = data / "outputs" / f"{run_id}_table.md"
    csv = data / "outputs" / f"{run_id}_table.csv"
    print(f"[表格] md={'✅' if md.exists() else '❌'} csv={'✅' if csv.exists() else '❌'}")
    if md.exists():
        lines = md.read_text(encoding="utf-8").splitlines()
        print(f"       表格 {len([l for l in lines if l.startswith('|') and '---' not in l]) - 1} 行")
        print("       " + lines[2][:90] + " ..." if len(lines) > 2 else "")

    # 2. 综述
    rv = data / "outputs" / f"{run_id}_review.md"
    print(f"[综述] {'✅ 已导出' if rv.exists() else '❌ 未导出'}")
    if rv.exists():
        print(f"       字数 {len(rv.read_text(encoding='utf-8'))}")

    # 3. 日志：哪步最慢
    summary = summarize_log(run_id)
    print(f"\n[日志] 共 {summary['entries']} 条事件")
    print(f"       总耗时 {summary['total_time_s']}s，最慢步骤: {summary['slowest_step']}")
    print(f"       状态分布: {summary['statuses']}")
    for step, t in summary["step_time_s"].items():
        print(f"         {step:<10} {t:>8.1f}s")

    # 4. token 统计（本次运行成功落盘的论文 meta.tokens + 日志里的 tokens）
    tokens = 0
    ok_files = []
    for f in glob.glob(str(data / "papers" / "*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        t = (d.get("meta") or {}).get("tokens", 0)
        if t:
            tokens += int(t)
            ok_files.append(Path(f).name)
    log_tokens = sum(
        int(e.get("tokens_review", 0) or 0) for e in read_log(run_id)
    )
    print(f"\n[token] 落盘论文提取 token: {tokens}（{len(ok_files)} 篇）")
    print(f"       本 run 日志记录 review token: {log_tokens}")


if __name__ == "__main__":
    main()
