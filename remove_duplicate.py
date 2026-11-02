import re

with open('f:/360/Pythonwork/project/src/logInt.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 删除主工作流中的重复8道综合图代码（保留visualize_composite_log函数中的代码）
# 找到从 "# 创建8道的综合测井曲线" 开始的第二个出现位置
pattern = r'\n                # 创建8道的综合测井曲线.*?(?=\n            # 5\. 生成报告)'
new_content = re.sub(pattern, '\n            ', content, flags=re.DOTALL)

# 写入文件
with open('f:/360/Pythonwork/project/src/logInt.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("删除重复代码完成")
