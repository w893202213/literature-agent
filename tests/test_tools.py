"""配置与工具链的单元测试（阶段 0/1 骨架，随实现逐步补充）。"""

from __future__ import annotations

from tools.dedupe import normalize_title
from tools.schemas import normalize_paper_info, validate_paper_info


def test_normalize_title():
    assert normalize_title("Foo-Bar: A Study v2") == normalize_title("foobar a study v2")
    assert normalize_title("2301.12345v3") == normalize_title("2301.12345")


def test_validate_paper_info_ok():
    info = {
        "title": "T", "authors": ["A"], "venue": "arXiv",
        "year": 2024, "method": "M", "datasets": ["D"],
        "results": "acc 90", "contribution": ["C"], "limitations": None,
    }
    ok, err = validate_paper_info(info)
    assert ok and err == ""


def test_validate_paper_info_missing_field():
    ok, _ = validate_paper_info({"title": "T"})
    assert not ok


def test_normalize_paper_info_fills_defaults():
    out = normalize_paper_info({"title": "T", "authors": "not-a-list"})
    assert out["authors"] == []
    assert out["method"] == ""
