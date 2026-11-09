# logknow/bootstrap.py
# 入口包装：logknow 知识库（区域测井知识图谱）的实际实现见 bootstrap_knowledge。
# 本文件仅做再导出，保证 `from logknow.bootstrap import GraphStore, bootstrap` 等可用，
# 并作为 `python -m logknow.bootstrap` 的命令行入口。
from logknow.bootstrap_knowledge import (
    GraphStore,
    BENCHMARK_DATA,
    bootstrap,
    KnowledgeAPI,
    KnowledgeValidator,
    main,
)

__all__ = [
    "GraphStore",
    "BENCHMARK_DATA",
    "bootstrap",
    "KnowledgeAPI",
    "KnowledgeValidator",
    "main",
]

if __name__ == "__main__":
    main()
