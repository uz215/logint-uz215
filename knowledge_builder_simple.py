# knowledge_builder_simple.py
import os
import json
from pathlib import Path

# 简化版知识库构建器，避免使用 torch 依赖
def build_simple_knowledgebase():
    """构建简化版知识库"""
    # 测井专业资料目录
    doc_path = r"F:/360/"
    
    all_docs = []
    
    # 1. 加载纯文本文件
    try:
        txt_files = list(Path(doc_path).rglob("*.txt"))
        for txt_file in txt_files:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                all_docs.append({
                    'file_path': str(txt_file),
                    'content': content[:1000]  # 只取前1000字符
                })
                print(f"加载了 TXT 文件: {txt_file}")
            except Exception as e:
                print(f"加载 TXT 文件失败 {txt_file}: {e}")
    except Exception as e:
        print(f"TXT文件加载失败: {e}")
    
    # 2. 保存文档信息到 JSON 文件
    output_dir = Path("C:/Vector_DB/Log_Chroma")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    output_file = output_dir / "knowledge_base.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)
    
    print(f"知识库构建完成！")
    print(f"共加载了 {len(all_docs)} 个文档")
    print(f"结果保存至: {output_file}")
    
    return all_docs

if __name__ == "__main__":
    # 构建简化版知识库
    docs = build_simple_knowledgebase()
    print("所有文档已成功添加到知识库！")
