# 读取文件内容
with open('logInt.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 处理每一行，统一修改 tick_params 中的 labelsize 和 pad 参数
fixed_lines = []
for line in lines:
    # 处理包含 tick_params 的行
    if 'tick_params' in line:
        # 替换 labelsize 参数为 8
        if 'labelsize=' in line:
            # 使用正则表达式替换 labelsize 值
            import re
            line = re.sub(r'labelsize=\d+', 'labelsize=8', line)
        # 确保添加 pad=10 参数
        if 'pad=' not in line:
            # 在行末添加 pad=10
            if ')' in line:
                # 在括号前添加 pad=10
                line = line.replace(')', ', pad=10)')
            else:
                # 如果没有括号，添加 pad=10
                line = line.rstrip() + ', pad=10\n'
    fixed_lines.append(line)

# 写入修复后的内容
with open('logInt.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('已统一修改所有刻度标签的字体大小为 8，边距为 10')
