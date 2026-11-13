#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""读取西沙1测井解释报告样本"""

import win32com.client
import os

word_file = '西沙1测井解释报告.doc'

if not os.path.exists(word_file):
    print(f"文件不存在: {word_file}")
    exit(1)

print(f"正在读取: {word_file}")
print("=" * 80)

try:
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    doc = word.Documents.Open(os.path.abspath(word_file))
    
    print(f"总段落数: {len(doc.Paragraphs)}")
    print()
    
    # 显示前50个段落
    count = min(50, len(doc.Paragraphs))
    for i in range(count):
        para = doc.Paragraphs(i + 1)  # COM 索引从1开始
        text = para.Range.Text.strip()
        if text:
            print(f"[{i+1:2d}] {text[:120]}")
    
    doc.Close()
    word.Quit()
    
    print("\n" + "=" * 80)
    print("读取完成!")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
