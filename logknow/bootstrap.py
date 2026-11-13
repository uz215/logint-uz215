# logknow/bootstrap.py
# 入口包装：logknow 知识库（区域测井知识图谱）的实际实现见 bootstrap_knowledge。
# 本文件仅做再导出，保证 `from logknow.bootstrap import ...` 可用，
# 并作为 `python -m logknow.bootstrap` 的命令行入口。
#
# 2026-11-13 修复：bootstrap_knowledge 的实现已统一为 GeoKnowledgeLoader
# （SQLite entity/fact 图谱）+ scan_docs_in_path（原件归档 + 结构化抽取）。
# 旧版 GraphStore / BENCHMARK_DATA / KnowledgeValidator 不在该模块，
# 原再导出会 ImportError；此处改按真实 API 导出。
from logknow.bootstrap_knowledge import (
    GeoKnowledgeLoader,
    lookup_interp_method,
    get_removable_drives,
    auto_scan_removable_docs,
    scan_docs_in_path,
    simple_geo_extract,
    main,
)

__all__ = [
    "GeoKnowledgeLoader",
    "lookup_interp_method",
    "get_removable_drives",
    "auto_scan_removable_docs",
    "scan_docs_in_path",
    "simple_geo_extract",
    "main",
]

if __name__ == "__main__":
    main()
