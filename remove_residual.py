# 读取文件
with open(r'f:\360\Pythonwork\project\src\logInt.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# 找到开始删除的行（logger.error("无处理数据可可视化")）
start_line = None
for i, line in enumerate(lines):
    if 'logger.error("无处理数据可可视化")' in line:
        start_line = i
        break

# 找到结束删除的行（# 5. 生成报告）
end_line = None
for i, line in enumerate(lines):
    if '# 5. 生成报告' in line:
        end_line = i
        break

if start_line is not None and end_line is not None:
    # 删除从start_line+1到end_line-1的所有行
    new_lines = lines[:start_line+1] + lines[end_line:]
    
    # 保存文件
    with open(r'f:\360\Pythonwork\project\src\logInt.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f'Successfully removed lines from {start_line+1} to {end_line-1}')
else:
    print(f'Start line: {start_line}, End line: {end_line}')
    print('Patterns not found')