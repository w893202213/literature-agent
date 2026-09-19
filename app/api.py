"""FastAPI 后端（可选加分项，阶段 3 时间充裕再做）。

规划：暴露 POST /run（提交主题，返回任务 id）与 GET /tasks/{id}（查询进度），
Gradio 前端走该后端，为部署到 4090 服务器做准备。
"""

from __future__ import annotations


def create_app():
    """构建 FastAPI 应用（阶段 3 可选）。"""
    raise NotImplementedError("阶段 3 可选：FastAPI 后端")
