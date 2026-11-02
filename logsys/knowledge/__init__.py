# -*- coding: utf-8 -*-
"""logsys.knowledge —— 区域知识库（kb.db）

模块：
    db      模式/连接/统计
    ingest  md/docx → doc/chunk/FTS + 实体/事实
    query   检索与知识 API
    build   CLI（构建/统计/检索）
"""

from .db import connect, stats, SCHEMA_VERSION  # noqa: F401
from .ingest import ingest_markdown, ingest_file, ingest_directory, tokenize  # noqa: F401
from .query import search, get_cases, get_facts, get_entities, open_docs  # noqa: F401

__all__ = ['connect', 'stats', 'SCHEMA_VERSION', 'ingest_markdown', 'ingest_file',
           'ingest_directory', 'tokenize', 'search', 'get_cases', 'get_facts',
           'get_entities', 'open_docs']
