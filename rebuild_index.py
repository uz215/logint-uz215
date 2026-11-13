#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专门用于重建知识库索引的脚本
"""

import os
import sys

# 添加当前目录到path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logknow import WhooshIndexer, MarkdownLoader, BuiltInKnowledge, generate_file_hash

def main():
    print("="*60)
    print("开始重建知识库索引")
    print("="*60)
    
    # 创建索引器
    indexer = WhooshIndexer()
    print("\n1. 创建/获取索引...")
    
    # 确保索引目录存在
    index_dir = "index"
    if not os.path.exists(index_dir):
        print(f"   创建索引目录: {index_dir}")
        os.makedirs(index_dir)
    
    # 创建新索引
    print("   创建新索引...")
    ix = indexer.create_index()
    print("   ✓ 索引创建成功")
    
    # 添加内置知识
    print("\n2. 添加内置知识...")
    builtin_knowledge = BuiltInKnowledge()
    builtin_docs = builtin_knowledge.get_all_knowledge()
    print(f"   加载了 {len(builtin_docs)} 条内置知识")
    
    for doc in builtin_docs:
        doc["source"] = f"builtin://{doc['title']}"
        doc["timestamp"] = __import__('datetime').datetime.now()
        doc["content_hash"] = generate_file_hash(doc["content"])
    
    if builtin_docs:
        added = indexer.add_documents(builtin_docs, skip_duplicates=False)
        print(f"   ✓ 已添加 {added} 条内置知识")
    
    # 添加本地文档
    print("\n3. 添加本地文档...")
    loader = MarkdownLoader()
    docs = loader.load_all()
    print(f"   加载了 {len(docs)} 个本地文档")
    
    if docs:
        # 分批添加，每批50个
        batch_size = 50
        total_added = 0
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i+batch_size]
            added = indexer.add_documents(batch, skip_duplicates=False)
            total_added += added
            print(f"   批次 {i//batch_size + 1}: 添加 {added} 个文档")
        
        print(f"   ✓ 已添加 {total_added} 个本地文档")
    
    # 检查最终索引数量
    final_count = indexer.get_document_count()
    print(f"\n4. 索引重建完成")
    print(f"   最终索引文档数: {final_count}")
    print("\n" + "="*60)
    
    # 验证索引目录
    if os.path.exists(index_dir):
        files = os.listdir(index_dir)
        print(f"   索引目录内容: {files}")
    else:
        print("   警告: 索引目录不存在!")

if __name__ == "__main__":
    main()
