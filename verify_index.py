#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证知识库索引并输出统计信息"""

import sys
sys.path.insert(0, '.')
import os

from logIntKnowledge import WhooshIndexer, MarkdownLoader, BuiltInKnowledge

def main():
    # 创建输出文件
    output_file = 'index_verification_report.txt'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*60 + "\n")
        f.write("知识库索引验证报告\n")
        f.write("="*60 + "\n\n")
        
        # 1. 检查索引状态
        f.write("1. 索引状态检查\n")
        f.write("-"*40 + "\n")
        indexer = WhooshIndexer()
        count = indexer.get_document_count()
        f.write(f"索引文档总数: {count}\n\n")
        
        # 2. 检查本地文档数量
        f.write("2. 本地文档检查\n")
        f.write("-"*40 + "\n")
        loader = MarkdownLoader()
        docs = loader.load_all()
        f.write(f"本地Markdown文档数量: {len(docs)}\n")
        
        # 3. 检查内置知识数量
        f.write("\n3. 内置知识检查\n")
        f.write("-"*40 + "\n")
        builtin_knowledge = BuiltInKnowledge()
        builtin_docs = builtin_knowledge.get_all_knowledge()
        f.write(f"内置知识数量: {len(builtin_docs)}\n")
        
        # 4. 检查索引目录
        f.write("\n4. 索引目录检查\n")
        f.write("-"*40 + "\n")
        index_dir = "index"
        if os.path.exists(index_dir):
            files = os.listdir(index_dir)
            f.write(f"索引目录存在，包含 {len(files)} 个文件\n")
            for file in files:
                filepath = os.path.join(index_dir, file)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    f.write(f"  - {file}: {size} bytes\n")
                else:
                    f.write(f"  - {file}/ (目录)\n")
        else:
            f.write("索引目录不存在!\n")
        
        # 5. 测试搜索功能
        f.write("\n5. 搜索功能测试\n")
        f.write("-"*40 + "\n")
        test_query = "测井解释"
        results = indexer.search(test_query, top_n=5)
        f.write(f"搜索 '{test_query}' 找到 {len(results)} 条结果\n")
        for i, result in enumerate(results, 1):
            f.write(f"  {i}. {result.get('title', '无标题')} (评分: {result.get('score', 0):.3f})\n")
        
        f.write("\n" + "="*60 + "\n")
        f.write("验证完成\n")
    
    print(f"验证报告已保存到: {output_file}")

if __name__ == "__main__":
    main()
