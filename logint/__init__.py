# -*- coding: utf-8 -*-
"""logint — 测井数据处理子模块（dlis_tool 等）"""

# ========== logknow 知识库简易封装（logint 包入口） ==========
# 【R80 修复】knowledge_api 里没有 get_stats，真实函数名是 get_kb_stats。
# 原写法导致 `from logint.dlis_tool import DlisTool` 抛 ImportError，
# DLIS 井加载被静默吞掉、退到"外部 Python 3.12 桥接"的死路 → DLIS 井加载不了。
from logknow.core.knowledge_api import (
    lookup_interp_method as _lookup_interp_method,
    match_methods as _match_methods,
    lookup_hierarchy as _lookup_hierarchy,
    get_kb_stats as _get_kb_stats
)


def logint_lookup_interp(country: str, basin: str = None, formation: str = None):
    return _lookup_interp_method(country, basin, formation)


def logint_match_interp(country: str, basin: str, formation: str, log_values: dict = None):
    return _match_methods(country, basin, formation, log_values)


def logint_get_geo_hierarchy(country: str):
    return _lookup_hierarchy(country)


def logint_kb_stat():
    return _get_kb_stats()


__all__ = [
    "logint_lookup_interp",
    "logint_match_interp",
    "logint_get_geo_hierarchy",
    "logint_kb_stat"
]
