"""PaperInfo 结构化提取的 JSON Schema 定义与校验。

设计要点（对齐 PROJECT_PLAN 第 5 节）：
- 结构化输出三重保险：JSON Schema + 低温 + few-shot + 校验重试
- 字段缺失时标 None/空，不中断流程
"""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

# 论文结构化信息的 JSON Schema（阶段 1 核心交付物）
PAPER_INFO_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PaperInfo",
    "description": "单篇论文的结构化信息，由 LLM 从 PDF 全文中提取",
    "type": "object",
    "required": [
        "title", "authors", "venue", "year",
        "method", "datasets", "results", "contribution", "limitations",
    ],
    "properties": {
        "title": {"type": "string", "description": "论文标题"},
        "authors": {
            "type": "array", "items": {"type": "string"},
            "description": "作者列表",
        },
        "venue": {"type": ["string", "null"], "description": "发表 venue（会议/期刊，未知则 null）"},
        "year": {"type": ["integer", "null"], "description": "发表年份"},
        "abstract": {"type": ["string", "null"], "description": "摘要（PDF 中缺失则 null）"},
        "method": {"type": "string", "description": "核心方法（如何解决，含模型架构/训练方式）"},
        "datasets": {
            "type": "array", "items": {"type": "string"},
            "description": "使用的数据集/基准列表",
        },
        "results": {
            "type": "string",
            "description": "关键实验结果与数字（如 'top-1 87.3% on ImageNet'）",
        },
        "contribution": {
            "type": "array", "items": {"type": "string"},
            "description": "主要贡献点列表",
        },
        "limitations": {
            "type": ["array", "null"], "items": {"type": "string"},
            "description": "局限性（未提及则 null）",
        },
    },
}

# 评测时人工核对的“关键字段”（对齐评测方案：字段准确率按这些字段算）
KEY_FIELDS = ["method", "datasets", "results"]

# 给 LLM 的 few-shot 示例（阶段 1 填充，示例应与目标领域相近）
# 来源：真实论文提取并通过 Schema 校验的结果（ACL 2022 VLKD 论文），
# 作为"输出格式示范"的第二道防线（对齐四层防线设计）。
FEWSHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "title": "Enabling Multimodal Generation on CLIP via Vision-Language Knowledge Distillation",
        "authors": ["Wenliang Dai", "Lu Hou", "Lifeng Shang", "Xin Jiang", "Qun Liu", "Pascale Fung"],
        "venue": "Findings of the Association for Computational Linguistics: ACL 2022",
        "year": 2022,
        "abstract": (
            "The recent large-scale vision-language pre-training (VLP) of dual-stream "
            "architectures (e.g., CLIP) with a tremendous amount of image-text pair data, "
            "has shown its superiority on various multimodal alignment tasks. Despite its "
            "success, the resulting models are not capable of multimodal generative tasks "
            "due to the weak text encoder. To tackle this problem, we propose to augment "
            "the dual-stream VLP model with a textual pre-trained language model (PLM) via "
            "vision-language knowledge distillation (VLKD), enabling the capability for "
            "multimodal generation."
        ),
        "method": (
            "The paper proposes Vision-Language Knowledge Distillation (VLKD) to enable "
            "CLIP to perform generative multimodal tasks. It aligns the BART encoder to "
            "CLIP's joint multimodal embedding space using three objectives: 1) Text-Text "
            "Distance Minimization (TTDM), 2) Image-Text Contrastive Learning (ITCL), and "
            "3) Image-Conditioned Text Infilling (ICTI). During training, CLIP's weights "
            "are frozen to preserve its multimodal space, while BART is trained to distill "
            "this knowledge."
        ),
        "datasets": ["VQAv2", "COCO image caption dataset"],
        "results": (
            "The model achieves 44.5% zero-shot accuracy on the VQAv2 dataset and 84.6 "
            "CIDEr on the COCO image caption dataset in a zero-shot manner. It surpasses "
            "the previous state-of-the-art zero-shot model with 7x fewer parameters."
        ),
        "contribution": [
            "Introduce an efficient approach to distill knowledge from CLIP to BART, enabling strong zero-shot performance on generative multimodal tasks.",
            "Exhaustively quantify these capabilities on six benchmarks under various settings.",
            "Conduct comprehensive analysis and ablation study to provide insights.",
        ],
        "limitations": None,
    },
]

# 提取 prompt 模板（占位，阶段 1 细化）
EXTRACT_SYSTEM_PROMPT = (
    "你是学术论文结构化提取助手。根据给定论文全文，严格按 JSON Schema 输出。\n"
    "要求：\n"
    "1. 只输出 JSON，不要任何解释或 Markdown 代码块标记；\n"
    "2. 所有字段必须来自论文原文，禁止编造；\n"
    "3. 论文中未出现的字段填 null 或空数组；\n"
    "4. results 字段保留具体数字指标。\n"
    "JSON Schema：\n" + json.dumps(PAPER_INFO_SCHEMA, ensure_ascii=False)
)


def validate_paper_info(obj: Any) -> tuple[bool, str]:
    """校验对象是否符合 PaperInfo Schema。

    返回 (是否通过, 错误信息)。通过时错误信息为空串。
    """
    validator = Draft202012Validator(PAPER_INFO_SCHEMA)
    try:
        validator.validate(obj)
        return True, ""
    except ValidationError as e:
        # 只报第一个错误即可，调用方负责重试
        return False, f"{e.json_path}: {e.message}"


def normalize_paper_info(obj: Any) -> dict[str, Any]:
    """把 LLM 输出清洗成合法 PaperInfo（缺字段补默认值，类型错误标 null）。"""
    defaults: dict[str, Any] = {
        "title": "", "authors": [], "venue": None, "year": None,
        "abstract": None, "method": "", "datasets": [], "results": "",
        "contribution": [], "limitations": None,
    }
    out = dict(defaults)
    if not isinstance(obj, dict):
        return out
    for key in defaults:
        val = obj.get(key, defaults[key])
        if val is None:
            out[key] = defaults[key]
        elif key in ("authors", "datasets", "contribution", "limitations"):
            out[key] = val if isinstance(val, list) else defaults[key]
        elif key == "year":
            out[key] = val if isinstance(val, int) else defaults[key]
        else:
            out[key] = str(val)
    return out
