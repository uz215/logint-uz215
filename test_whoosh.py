#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID

# 测试基本的Whoosh功能
print("测试基本的Whoosh功能...")

# 定义schema
schema = Schema(
    title=TEXT(stored=True),
    content=TEXT(stored=True),
    source=ID(stored=True, unique=True)
)

# 创建索引目录
index_dir = "test_index"
print(f"索引目录: {index_dir}")

try:
    # 删除旧目录
    if os.path.exists(index_dir):
        import shutil
        shutil.rmtree(index_dir)
        print("已删除旧索引目录")
    
    # 创建目录
    os.makedirs(index_dir)
    print("已创建索引目录")
    
    # 创建索引
    ix = create_in(index_dir, schema)
    print("已创建索引")
    
    # 添加文档
    writer = ix.writer()
    writer.add_document(
        title="测试文档1",
        content="这是一个测试文档的内容",
        source="test://doc1"
    )
    writer.commit()
    print("已添加测试文档")
    
    # 检查文档数
    with ix.searcher() as searcher:
        count = searcher.doc_count()
        print(f"索引中文档数: {count}")
    
    print("\n测试成功！")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
