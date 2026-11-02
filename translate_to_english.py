# 读取文件内容
with open('logInt.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 定义需要替换的中文词汇及其对应的英文
replacements = {
    '数据加载成功': 'Data loaded successfully',
    '条记录': 'records',
    '加载的曲线': 'Loaded curves',
    '数据加载失败': 'Failed to load data',
    '数据未加载': 'Data not loaded',
    '数据质量检查': 'Data quality check',
    '总记录数': 'total_records',
    '缺失值': 'missing_values',
    '异常值': 'outliers',
    '数据类型': 'data_types',
    '缺失的必填列': 'missing_required_columns',
    '数据质量检查完成': 'Data quality check completed',
    '开始解释': 'START INTERPRETATION',
    '解释完成': 'Interpretation completed',
    '总': 'total',
    '开始多矿物分析': 'Starting multi-mineral analysis',
    '优化完成': 'Optimization completed',
    '成功率': 'success rate',
    '优化失败率较高': 'High optimization failure rate',
    '建议检查数据质量': 'Suggest checking data quality',
    '多矿物分析完成': 'Multi-mineral analysis completed',
    '开始岩性分析': 'Starting lithology analysis',
    '开始沉积相分析': 'Starting facies analysis',
    '开始测井资料处理工作流': 'Starting well log processing workflow',
    '创建处理器': 'Creating processor',
    '处理器创建成功': 'Processor created successfully',
    '从命令行获取文件路径': 'Getting file path from command line',
    '未提供文件路径，将打开文件选择对话框': 'No file path provided, will open file selection dialog',
    '加载数据文件': 'Loading data file',
    '工作流运行成功': 'Workflow ran successfully',
    '结果已保存至': 'Results saved to',
    '工作流运行失败': 'Workflow run failed',
    '运行工作流时出错': 'Error running workflow',
    '岩性': 'Lithology',
    '电阻率': 'Resistivity',
    '孔隙度': 'Porosity',
    '深度': 'Depth',
    '含水饱和度': 'Water Saturation',
    '沉积微相': 'Sedimentary Facies',
    '测井解释': 'Log Interpretation',
    '综合测井图': 'Composite Log',
    '尝试保存综合测井图到绝对路径': 'Attempting to save composite log to absolute path',
    '开始保存综合测井图': 'Starting to save composite log',
    '数据点数量': 'Number of data points',
    '图形大小': 'Figure size',
    '尝试保存综合测井图到': 'Attempting to save composite log to',
    '已保存综合测井图': 'Composite log saved',
    '综合测井图保存成功': 'Composite log saved successfully',
    '综合测井图保存失败': 'Failed to save composite log',
    '文件不存在': 'File does not exist',
    '保存综合测井图时出错': 'Error saving composite log',
    '尝试减少数据点数量后重新绘制': 'Attempting to redraw with reduced data points',
    '减少数据点后数量': 'Number of data points after reduction'
}

# 处理每一行，只替换非注释行中的中文
fixed_lines = []
for line in lines:
    # 检查是否是注释行
    if line.strip().startswith('#'):
        # 保留注释行不变
        fixed_lines.append(line)
    else:
        # 替换非注释行中的中文
        fixed_line = line
        for chinese, english in replacements.items():
            fixed_line = fixed_line.replace(chinese, english)
        fixed_lines.append(fixed_line)

# 写入修复后的内容
with open('logInt.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('已将除注释外的所有中文替换为英文')
