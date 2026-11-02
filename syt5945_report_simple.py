#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化的 SY/T 5945-2016 报告生成入口
用于在 logInt.py 中调用
"""

def generate_report_from_csv(csv_path, output_dir):
    """
    从 processed.csv 生成完整报告
    
    Args:
        csv_path: CSV 文件路径
        output_dir: 输出目录
    
    Returns:
        str: 报告文件路径或 None
    """
    try:
        import pandas as pd
        import numpy as np
        import os
        from pathlib import Path
        from datetime import datetime
        
        # 加载数据
        data = pd.read_csv(csv_path)
        output_dir = Path(output_dir)
        
        # 设置井信息
        well_name = Path(csv_path).stem
        # 清洗井名: 去掉 _processed / -processed 等处理标记, 保留纯井名
        for _suf in ('_processed', '-processed', '_processed_data', '_clean', '_raw'):
            if well_name.lower().endswith(_suf):
                well_name = well_name[: -len(_suf)]
                break
        well_info = {
            'well_name': well_name,
            'well_type': '探井/评价井',
            'operation_date': datetime.now().strftime('%Y年%m月%d日'),
            'operator': '测井解释系统'
        }
        
        # 统计分析
        stats = {}
        
        if 'LITHOLOGY' in data.columns:
            lith_counts = data['LITHOLOGY'].value_counts()
            stats['lithology'] = {
                'counts': lith_counts.to_dict(),
                'percentages': ((lith_counts / len(data) * 100).round(2)).to_dict()
            }
        
        if 'PHI' in data.columns:
            phi_valid = data['PHI'].dropna()
            stats['porosity'] = {
                'mean': phi_valid.mean(),
                'std': phi_valid.std(),
                'min': phi_valid.min(),
                'max': phi_valid.max()
            }
        
        if 'Sw' in data.columns:
            sw_valid = data['Sw'].dropna()
            stats['saturation'] = {
                'mean': sw_valid.mean(),
                'std': sw_valid.std(),
                'min': sw_valid.min(),
                'max': sw_valid.max()
            }
        
        if 'INTERPRETATION' in data.columns:
            int_counts = data['INTERPRETATION'].value_counts()
            stats['interpretation'] = {
                'counts': int_counts.to_dict(),
                'percentages': ((int_counts / len(data) * 100).round(2)).to_dict()
            }
        
        if 'MD' in data.columns:
            stats['depth_range'] = {
                'start': data['MD'].min(),
                'end': data['MD'].max()
            }
        
        # 构建报告
        report = []
        report.append(generate_cover(well_info))
        report.append(generate_toc())
        report.append(generate_chapter_1(well_info, data, stats))
        report.append(generate_chapter_2(data))
        report.append(generate_chapter_3(stats, data))
        report.append(generate_chapter_4(stats))
        report.append(generate_chapter_5(stats, data))
        report.append(generate_chapter_6(well_info, data, stats))
        report.append(generate_chapter_7(well_info, data, stats))
        report.append(generate_appendix(stats))
        report.append(generate_end())
        
        # 保存中文报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename_cn = f"{well_name}井测井解释报告_{timestamp}.md"
        
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path_cn = output_dir / report_filename_cn
        
        with open(report_path_cn, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        
        # 生成英文报告
        report_en = []
        report_en.append(generate_cover_en(well_info))
        report_en.append(generate_toc_en())
        report_en.append(generate_chapter_1_en(well_info, data, stats))
        report_en.append(generate_chapter_2_en(data))
        report_en.append(generate_chapter_3_en(stats, data))
        report_en.append(generate_chapter_4_en(stats))
        report_en.append(generate_chapter_5_en(stats, data))
        report_en.append(generate_chapter_6_en(well_info, data, stats))
        report_en.append(generate_chapter_7_en(well_info, data, stats))
        report_en.append(generate_appendix_en(stats))
        report_en.append(generate_end_en())
        
        report_filename_en = f"{well_name}_Well_Log_Interpretation_Report_{timestamp}.md"
        report_path_en = output_dir / report_filename_en
        
        with open(report_path_en, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_en))
        
        print(f"\n[V] Chinese report generated: {report_path_cn}")
        print(f"[V] English report generated: {report_path_en}")
        
        return str(report_path_cn)
        
    except Exception as e:
        print(f"报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_cover(info):
    return f'''

================================================================================

                          {info.get('well_name', 'XXXX')}
                          测井解释报告

================================================================================

  编制单位: {info.get('operator', '测井解释系统')}
  编制日期: {info.get('operation_date', '')}
  报告人:   AI自动生成
  审核人:   {info.get('well_type', '专业人员')}
  技术负责人: {info.get('operator', '自动化系统')}

本标准依据 SY/T 5945-2016《测井解释报告编写规范》编制



'''

def generate_toc():
    return '''********************************************************************************
                                    目  次
********************************************************************************

一、钻井、地质概况 .................................................................................... 1
二、测井施工过程控制及测井资料质量评价 .................................................... 2
三、数据处理情况 .................................................................................... 4
四、储层划分及流体性质识别标准 ................................................................ 5
五、储层综合评价 .................................................................................... 7
六、地质分析与工程应用 .......................................................................... 9
七、测井解释结论与建议 .......................................................................... 11
附录 A  测井解释成果数据表 .................................................................. 13
附录 B  主要参数统计表 .......................................................................... 14




'''

def generate_chapter_1(info, data, stats):
    well_name = info.get('well_name', '未知井')
    result = f'''================================================================================
                        一、钻井、地质概况
================================================================================

1.1 基础数据
----------------------------------------
井号:       {well_name}
井别:       {info.get('well_type', '探井/评价井')}
地理位置:   暂无该信息
构造位置:   暂无该信息
地面海拔:   暂无该信息
磁偏角:     暂无该信息
开钻日期:   暂无该信息
完钻日期:   暂无该信息
完钻井深:   {f"{stats.get('depth_range', {}).get('end', 0):,.1f} m" if stats.get('depth_range') else "待确定"}
设计井深:   暂无该信息
目的层:     根据数据判断为主要目的层段
钻井目的:   油气勘探/开发


1.2 井身结构与钻井液性能
----------------------------------------
1.2.1 井身结构
    本井井身结构数据暂未获取。

1.2.2 钻井液性能
    钻井液性能数据暂未获取。

1.2.3 井身轨迹
'''
    
    if 'DEVI' in data.columns and data['DEVI'].notna().sum() > 0:
        result += f'''    井斜数据记录数: {len(data[data['DEVI'].notna()])} 条
    井斜范围: {data['DEVI'].min():.2f}° - {data['DEVI'].max():.2f}°
'''
    else:
        result += '    井斜数据: 暂无\n'
    
    result += '''

1.3 区域地质概况
----------------------------------------
1.3.1 构造特征
    该井所在的区域构造背景资料暂无。

1.3.2 沉积特征
'''
    
    if 'FACIES' in data.columns:
        result += generate_facies_text(data)
    else:
        result += '    暂无沉积相分析结果\n'
    
    result += '''

1.4 邻井钻探成果
----------------------------------------
    邻井资料暂无。

1.5 岩性及油气显示描述
----------------------------------------
    根据岩性识别结果统计：
'''
    
    if stats.get('lithology'):
        result += f'''    {"岩性类型":<15s} {"点数":>8s} {"占比(%)":>8s}
    -----------------------------------
'''
        for lith, count in stats.get('lithology', {}).get('counts', {}).items():
            pct = stats.get('lithology', {}).get('percentages', {}).get(lith, 0)
            if pct > 0:  # Only display lithology with percentage > 0%
                result += f'    {lith:<15s} {count:>8d} {pct:>7.2f}%\n'
        
        result += '\n    主要岩性类型（占比＞5%）：\n'
        _pcts = stats.get('lithology', {}).get('percentages', {})
        # 只统计有数据(>0%)且占比>=5%的岩性
        _major = sorted([(l, _pcts.get(l, 0)) for l in stats['lithology']['counts'] 
                         if _pcts.get(l, 0) > 0],
                        key=lambda x: -x[1])
        _major = [l for l, _p in _major if _p >= 5.0]
        if _major:
            for _l in _major:
                result += f'    - {_l}\n'
        else:
            result += '    （各岩性占比均低于5%，无明显主要岩性）\n'
    else:
        result += '    （暂无）\n'
    
    result += '''

1.6 气测录井概况
----------------------------------------
    气测数据如有采集，详见 Composite Log。

'''
    
    return result


def generate_chapter_2(data):
    return '''================================================================================
           二、测井施工过程控制及测井资料质量评价
================================================================================

2.1 测井仪器型号及刻度校验
----------------------------------------
    测井仪器型号：暂无该信息
    测前刻度：暂无该信息
    测后刻度：暂无该信息
    依据标准：GB/T 16523《测井作业技术规范》


2.2 测井项目与测量参数
----------------------------------------
    本次测井项目包括以下曲线：
''' + (
    f'''    可用曲线总数: {len(data.columns)} 条

    {"曲线代码":<12s} {"物理意义":<30s} {"有效数据":>10s}
    ------------------------------------------------------------
''' + '\n'.join([
        f'{col:<12s} {col:<30s} {data[col].notna().sum():>10d}'
        for col in data.columns[:15]
    ]) + '\n' if data is not None else ''
) + '''

2.3 测井施工过程控制
----------------------------------------
2.3.1 特殊测井项目
    待定。

2.3.2 测井环境评价
    需根据实际情况分析。


2.4 测井资料质量评价
----------------------------------------
2.4.1 评价标准
    执行标准：SY/T 5132-2012《测井原始资料质量要求》

2.4.2 逐曲线质量评分
''' + (
    f'''    {"曲线名称":<15s} {"完整率(%)":>10s} {"等级":<8s}
    -----------------------------------------------------------------------
''' + '\n'.join([
        f'{col:<15s} {data[col].notna().sum()/len(data)*100:>9.2f}% {"优秀" if data[col].notna().sum()/len(data) > 0.95 else "合格":<8s}'
        for col in ['GR', 'NPHI', 'RHOB', 'DT', 'LLD'] if col in data.columns
    ]) + '\n' if data is not None else ''
) + '''
2.4.3 总体质量评定
    （需根据实际曲线完整率进行评定）



'''

def generate_chapter_3(stats, data):
    return '''================================================================================
                         三、数据处理情况
================================================================================

3.1 测井资料标准化
----------------------------------------
    深度校正和环境校正已完成（如适用）。


3.2 测井解释模型选择
----------------------------------------
3.2.1 剖面类型判定
    根据实际数据进行矿物定量计算和交汇图分析来确定。

3.2.2 矿物定量计算模型
    采用合适的矿物分解模型。

3.2.3 孔隙度计算方法
    可采用多种方法并行计算孔隙度。
    孔隙度均值: {f"{stats.get('porosity', {}).get('mean', '待计算'):.4f}" if stats.get('porosity') else '待计算'}

3.2.4 含水饱和度计算方法
    采用 Arps 经验公式或其他合适的方法。


3.3 处理成果说明
----------------------------------------
3.3.1 岩性识别
''' + (
    f'''    识别岩性类型：{", ".join([l for l, p in sorted(stats.get("lithology", {}).get("counts", {}).items(), key=lambda x: -x[1]) if stats.get("lithology", {}).get("percentages", {}).get(l, 0) > 0 and stats.get("lithology", {}).get("percentages", {}).get(l, 0) >= 5.0])}
    砂岩占比: {stats.get("lithology", {}).get("percentages", {}).get("sandstone", 0):.1f}%
    页岩占比: {stats.get("lithology", {}).get("percentages", {}).get("shale", 0):.1f}%
''' if stats.get('lithology') else '    暂无岩性识别结果。\n'
) + '''



'''

def generate_chapter_4(stats):
    return '''================================================================================
               四、储层划分及流体性质识别标准
================================================================================

4.1 储层测井特征分析
----------------------------------------
4.1.1 物性特征
    有效孔隙度下限: PHI >= 0.05 (5%)
    本井平均孔隙度: {f"{stats.get('porosity', {}).get('mean', '待计算'):.4f}" if stats.get('porosity') else '待计算'}
    平均含水饱和度: {f"{stats.get('saturation', {}).get('mean', '待计算'):.4f}" if stats.get('saturation') else '待计算'}

4.1.2 电性特征
    油层: 中高电阻率，中等偏低含水饱和度
    气层: 高电阻率，低含水饱和度
    水层: 低电阻率，高含水饱和度 (Sw > 0.8)


4.2 有效储层判别标准
----------------------------------------
    ① PHI >= 0.05
    ② VALID_CURVES_COUNT >= 3
    ③ 非特殊岩性


4.3 油气水层判别方法及标准
----------------------------------------
    OIL (油层): Sw < 0.5 & Rt 中等偏高 & PHI >= 0.05    绿色
    GAS (气层): Sw < 0.4 & Rt 高    红色
    WATER (水层): Sw > 0.8 & Rt 低    蓝色
    DRY (干层): PHI < 0.05 或 Vsh 过高    棕色


4.4 储层分类
----------------------------------------
    - 碎屑岩储层：砂岩、粉砂岩
    - 碳酸盐岩储层：灰岩、白云岩
    - 特殊岩性储层：火山岩、蒸发岩



'''

def generate_chapter_5(stats, data):
    return '''================================================================================
                         五、储层综合评价
================================================================================

5.1 储层物性特征
----------------------------------------
    孔隙度统计参数：
''' + (
    f'''    - 平均值: {stats["porosity"]["mean"]:.4f}
    - 标准差: {stats["porosity"]["std"]:.4f}
    - 最大值: {stats["porosity"]["max"]:.4f}
    - 最小值: {stats["porosity"]["min"]:.4f}
''' if stats.get('porosity') else '    - 暂无统计数据\n'
) + '''

5.2 岩性及物性特征描述
----------------------------------------
''' + (
    '\n'.join([
        f'    {lith}: 分布占比 {pct:.1f}%'
        for lith, pct in sorted(stats.get('lithology', {}).get('percentages', {}).items(), key=lambda x: -x[1])
        if pct > 0
    ]) if stats.get('lithology') else '    暂无岩性统计信息\n'
) + '''

5.3 储层与非储层分布
----------------------------------------
    （根据实际解释结果统计）


5.4 流体性质分析
----------------------------------------
    流体性质统计：
''' + (
    f'''    - 油层 (OIL): {stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} 条
    - 气层 (GAS): {stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} 条
    - 水层 (WATER): {stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} 条
    - 干层 (DRY): {stats.get("interpretation", {}).get("counts", {}).get("DRY", 0)} 条
''' if stats.get('interpretation') else '    （暂无解释结果统计）\n'
) + '''



'''

def generate_chapter_6(info, data, stats):
    well_name = info.get('well_name', '未知井')
    return f'''================================================================================
                      六、地质分析与工程应用
================================================================================

6.1 地层对比与构造分析
----------------------------------------
    {well_name}井地层对比需结合区域地层格架进行。

6.2 沉积相分析及认识
----------------------------------------
''' + (generate_facies_text(data) if 'FACIES' in data.columns else '    暂无沉积相分析结果。\n') + '''

6.3 储层预测
----------------------------------------
    （需结合具体数据给出层位深度范围）

6.4 地层压力分析
----------------------------------------
    正常压力体系参考纯水层段。

6.5 裂缝分析
----------------------------------------
    如有成像测井资料可进行裂缝识别。

6.6 工程应用建议
----------------------------------------
6.6.1 完井方案建议
    - 优先对油气层段进行试油测试

6.6.2 钻井建议
    - 注意井眼稳定性



'''

def generate_chapter_7(info, data, stats):
    well_name = info.get('well_name', '未知井')
    return f'''================================================================================
                      七、测井解释结论与建议
================================================================================

7.1 主要结论
----------------------------------------
    1. 本井共测井深度范围及数据点数：
''' + (
    f'       从 {data["MD"].min():.1f} m 至 {data["MD"].max():.1f} m，共 {len(data)} 条记录。\n'
    if data is not None and 'MD' in data.columns else '       待确定\n'
) + f'''
    2. 识别有效油气水层数量：
''' + (
    f'''       - 油层 {stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} 个
       - 气层 {stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} 个
       - 水层 {stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} 个
''' if stats.get('interpretation') else '       暂无数据\n'
) + f'''
    3. 可能含油气层数量：
''' + (
    f'''       - 可能含油 {stats.get("interpretation", {}).get("counts", {}).get("OIL_POSSIBLE", 0)} 个
       - 可能含气 {stats.get("interpretation", {}).get("counts", {}).get("GAS_POSSIBLE", 0)} 个
''' if stats.get('interpretation') else '       暂无数据\n'
) + f'''
    4. 非储层数量及占比：
''' + (
    f'''       非储层 {stats.get("interpretation", {}).get("counts", {}).get("NonReservoir", 0)} 个，
       占总井段的 {stats.get("interpretation", {}).get("percentages", {}).get("NonReservoir", 0):.1f}%。
''' if stats.get('interpretation') else '       暂无统计信息。\n'
) + f'''
    5. 平均孔隙度 {f"{stats.get('porosity', {}).get('mean', '待计算'):.4f}" if stats.get('porosity') else '待计算'}，
       平均含水饱和度 {f"{stats.get('saturation', {}).get('mean', '待计算'):.4f}" if stats.get('saturation') else '待计算'}。


7.2 建议试油层位
----------------------------------------
    （需结合具体层位数据给出建议）


7.3 存在问题与建议
----------------------------------------
7.3.1 存在的问题
    1. 缺乏岩心实验数据对比验证
    2. 如未包含成像测井资料，裂缝识别能力有限

7.3.2 工作建议
    1. 建议补充取心作业，开展岩心实验分析
    2. 建议进行成像测井，精细识别裂缝
    3. 尽快安排试油作业，验证测井解释结论


7.4 认识及结论
----------------------------------------
    1. {well_name}井测井资料质量总体评价。
    2. 本井剖面类型及主要储层类型。
    3. 油气显示评价及勘探前景。
    4. 建议对主力油气层段进行试油测试，验证产能。


'''

def generate_appendix(stats):
    return '''================================================================================
                       附录 A  测井解释成果数据表（摘要）
================================================================================

    表A-1  孔隙度统计参数
    参数                             数值
    -----------------------------------
    平均值                        （待填入）
    标准差                        （待填入）
    最大值                        （待填入）
    最小值                        （待填入）

    表A-2  含水饱和度统计参数
    参数                             数值
    -----------------------------------
    平均值                        （待填入）
    标准差                        （待填入）
    最大值                        （待填入）
    最小值                        （待填入）

    表A-3  解释结论统计表
    解释类型                     点数    占比(%)
    --------------------------------------
    （待填入）


================================================================================
                       附录 B  测井曲线数据摘要
================================================================================

    表B-1  主要测井曲线基本信息
    （待填入）


'''

def generate_end():
    return '''********************************************************************************
                              报告结束
    编制单位: 测井解释系统
    编制日期: （自动生成日期）
    依据标准: SY/T 5945-2016《测井解释报告编写规范》
********************************************************************************

'''

def generate_facies_text(data):
    if data is None or 'FACIES' not in data.columns:
        return '    暂无沉积相分析结果\n'
    
    facies_counts = data['FACIES'].value_counts()
    result = '    根据沉积相分析结果：\n'
    for facies, count in facies_counts.items():
        pct = count / len(data) * 100
        result += f'    - {facies}: {count} 条 ({pct:.1f}%)\n'
    return result


# ==================== 英文版函数 ====================

def generate_cover_en(info):
    return f'''

================================================================================

                          {info.get('well_name', 'XXXX')} Well Log Interpretation Report

================================================================================

  Prepared by:   {info.get('operator', 'Well Log Interpretation System')}
  Date:          {info.get('operation_date', '')}
  Author:        AI Automated Generation
  Reviewer:      {info.get('well_type', 'Professional Staff')}
  Technical Lead: {info.get('operator', 'Automated System')}

This report is prepared in accordance with SY/T 5945-2016 specification


'''

def generate_toc_en():
    return '''********************************************************************************
                                    CONTENTS
********************************************************************************

1. Drilling and Geological Overview ................................................. 1
2. Logging Operation Control and Data Quality Evaluation ........................... 2
3. Data Processing ................................................................. 4
4. Reservoir Identification and Fluid Discrimination Criteria ....................... 5
5. Reservoir Comprehensive Evaluation ............................................... 7
6. Geological Analysis and Engineering Application .................................. 9
7. Interpretation Conclusions and Recommendations .................................. 11
Appendix A  Interpretation Results Data Table ....................................... 13
Appendix B  Curve Data Summary ...................................................... 14



'''

def generate_chapter_1_en(info, data, stats):
    well_name = info.get('well_name', 'Unknown Well')
    result = f'''================================================================================
                     1. DRILLING AND GEOLOGICAL OVERVIEW
================================================================================

1.1 Basic Information
----------------------------------------
Well Name:         {well_name}
Well Type:         {info.get('well_type', 'Exploration/Evaluation Well')}
Location:          Not available (coordinates required)
Structural Position: Not available
Elevation:         Not available
Magnetic Declination: Not available
Started Date:      Not available
Completed Date:    Not available
Total Depth:       {f"{stats.get('depth_range', {}).get('end', 0):,.1f} m" if stats.get('depth_range') else "TBD"}
Designed Depth:    Not available
Target Formation:  Main target formation based on data analysis
Drilling Purpose:  Oil and gas exploration/development


1.2 Wellbore Structure and Drilling Mud
----------------------------------------
1.2.1 Wellbore Structure
    Wellbore structure data not available (BS/CALS curve analysis required).

1.2.2 Drilling Mud Properties
    Drilling mud data not available.

1.2.3 Well Trajectory
'''
    
    # 添加轨迹数据
    if 'DEVI' in data.columns and data['DEVI'].notna().sum() > 0:
        result += f'''    Inclination measurements: {len(data[data['DEVI'].notna()])} records
    Inclination range: {data['DEVI'].min():.2f}° - {data['DEVI'].max():.2f}°
'''
    else:
        result += '    Inclination data: Not available\n'
    
    result += '''

1.3 Regional Geological Setting
----------------------------------------
1.3.1 Structural Features
    Regional tectonic background information not available.

1.3.2 Sedimentary Characteristics
'''
    
    if 'FACIES' in data.columns:
        result += generate_facies_text_en(data)
    else:
        result += '    Facies analysis data not available.\n\n'
    
    result += '''

1.4 Neighboring Wells
----------------------------------------
    Neighboring well data not available.

1.5 Lithology and Oil/Gas Shows
----------------------------------------
    Lithology statistics:
'''
    
    # 添加岩性统计表格
    lith_data = stats.get('lithology', {})
    if lith_data and lith_data.get('counts'):
        result += '    {:<15s} {:>8s} {:>12s}\n'.format('Lithology', 'Count', 'Percentage(%)')
        result += '    -------------------------------------------\n'
        for lith, count in lith_data['counts'].items():
            pct = lith_data['percentages'].get(lith, 0)
            if pct > 0:  # Only display lithology with percentage > 0%
                result += '    {:<15s} {:>8d} {:>11.2f}%\n'.format(lith, count, pct)
        result += '\n    Main lithology types (>0% and >=5%):\n'
        pcts = lith_data.get('percentages', {})
        # Only count lithology with percentage > 0%
        major = sorted([(l, pcts.get(l, 0)) for l in lith_data['counts'] 
                        if pcts.get(l, 0) > 0],
                       key=lambda x: -x[1])
        major = [l for l, _p in major if _p >= 5.0]
        if major:
            for l in major:
                result += '    - {}\n'.format(l)
        else:
            result += '    (No dominant lithology; all proportions below 5%)\n'
    else:
        result += '    (No lithology data available)\n'
    
    result += '''

1.6 Gas Logging Overview
----------------------------------------
    Gas logging data (if available), see Composite Log.

'''
    
    return result

def generate_chapter_2_en(data):
    return '''================================================================================
        2. LOGGING OPERATION CONTROL AND DATA QUALITY EVALUATION
================================================================================

2.1 Logging Tools and Calibration
----------------------------------------
    Tool models: Not available
    Pre-job calibration: Not available
    Post-job calibration: Not available
    Standard: GB/T 16523


2.2 Logging Parameters
----------------------------------------
    Curves acquired:
''' + (
    f'''    Total curves: {len(data.columns)}

    {"Curve Code":<12s} {"Physical Meaning":<30s} {"Valid Data":>10s}
    ------------------------------------------------------------
''' + '\n'.join([
        f'{col:<12s} {col:<30s} {data[col].notna().sum():>10d}'
        for col in data.columns[:15]
    ]) + '\n' if data is not None else ''
) + '''
2.3 Logging Operation Control
----------------------------------------
2.3.1 Special Logging
    To be determined.

2.3.2 Environmental Evaluation
    Hole enlargement and mud effects need actual data analysis.


2.4 Data Quality Evaluation
----------------------------------------
2.4.1 Evaluation Standard
    Standard: SY/T 5132-2012

2.4.2 Quality Assessment
''' + (
    f'''    {"Curve":<15s} {"Completeness(%)":>15s} {"Rating":<8s}
    -----------------------------------------------------------------------
''' + '\n'.join([
        f'{col:<15s} {data[col].notna().sum()/len(data)*100:>14.2f}% {"Excellent" if data[col].notna().sum()/len(data) > 0.95 else "Pass":<8s}'
        for col in ['GR', 'NPHI', 'RHOB', 'DT', 'LLD'] if col in data.columns
    ]) + '\n' if data is not None else ''
) + '''
2.4.3 Overall Quality Rating
    To be determined based on actual data completeness.

'''

def generate_chapter_3_en(stats, data):
    return '''================================================================================
                        3. DATA PROCESSING
================================================================================

3.1 Log Standardization
----------------------------------------
    Depth correction and environmental corrections completed (if applicable).

3.2 Interpretation Models
----------------------------------------
3.2.1 Profile Type
    Determined by mineral quantification and crossplot analysis.

3.2.2 Mineral Quantification Model
    Appropriate mineral decomposition model applied.

3.2.3 Porosity Calculation Method
    Multiple methods can be applied in parallel.
    Mean porosity: {f"{stats.get('porosity', {}).get('mean', 'TBD'):.4f}" if stats.get('porosity') else 'TBD'}

3.2.4 Water Saturation Calculation
    Arps empirical formula or other appropriate methods.


3.3 Processing Results
----------------------------------------
3.3.1 Lithology Identification
''' + (
    f'''    Identified lithologies: {", ".join([l for l, p in sorted(stats.get("lithology", {}).get("counts", {}).items(), key=lambda x: -x[1]) if stats.get("lithology", {}).get("percentages", {}).get(l, 0) > 0 and stats.get("lithology", {}).get("percentages", {}).get(l, 0) >= 5.0])}
    Sandstone percentage: {stats.get("lithology", {}).get("percentages", {}).get("sandstone", 0):.1f}%
    Shale percentage: {stats.get("lithology", {}).get("percentages", {}).get("shale", 0):.1f}%
''' if stats.get('lithology') else '    Lithology identification results not available.\n'
) + '''

'''

def generate_chapter_4_en(stats):
    return '''================================================================================
         4. RESERVOIR IDENTIFICATION AND FLUID DISCRIMINATION CRITERIA
================================================================================

4.1 Log Characteristics of Reservoirs
----------------------------------------
4.1.1 Physical Properties
    Effective porosity limit: PHI >= 0.05 (5%)
    Mean porosity: {f"{stats.get('porosity', {}).get('mean', 'TBD'):.4f}" if stats.get('porosity') else 'TBD'}
    Mean water saturation: {f"{stats.get('saturation', {}).get('mean', 'TBD'):.4f}" if stats.get('saturation') else 'TBD'}

4.1.2 Electrical Properties
    Oil zone: Medium-high resistivity, low-medium water saturation
    Gas zone: High resistivity, low water saturation
    Water zone: Low resistivity, high water saturation (Sw > 0.8)


4.2 Effective Reservoir Criteria
----------------------------------------
    ① PHI >= 0.05
    ② VALID_CURVES_COUNT >= 3
    ③ Non-special lithology


4.3 Oil/Gas/Water Discrimination Criteria
----------------------------------------
    OIL: Sw < 0.5 & medium-high Rt & PHI >= 0.05    Green
    GAS: Sw < 0.4 & high Rt                         Red
    WATER: Sw > 0.8 & low Rt                        Blue
    DRY: PHI < 0.05 or high Vsh                     Brown


4.4 Reservoir Classification
----------------------------------------
    - Clastic reservoirs: Sandstone, siltstone
    - Carbonate reservoirs: Limestone, dolomite
    - Special reservoirs: Volcanic, evaporite

'''

def generate_chapter_5_en(stats, data):
    return '''================================================================================
                      5. RESERVOIR COMPREHENSIVE EVALUATION
================================================================================

5.1 Reservoir Physical Properties
----------------------------------------
    Porosity statistics:
''' + (
    f'''    - Mean: {stats["porosity"]["mean"]:.4f}
    - Std Dev: {stats["porosity"]["std"]:.4f}
    - Maximum: {stats["porosity"]["max"]:.4f}
    - Minimum: {stats["porosity"]["min"]:.4f}
''' if stats.get('porosity') else '    No statistical data available.\n'
) + '''

5.2 Lithology and Property Description
----------------------------------------
''' + (
    '\n'.join([
        f'    {lith}: Distribution {pct:.1f}%'
        for lith, pct in sorted(stats.get('lithology', {}).get('percentages', {}).items(), key=lambda x: -x[1])
        if pct > 0
    ]) if stats.get('lithology') else '    No lithology statistics available.\n'
) + '''

5.3 Reservoir vs Non-reservoir Distribution
----------------------------------------
    (Based on actual interpretation results)

5.4 Fluid Properties Analysis
----------------------------------------
    Fluid statistics:
''' + (
    f'''    - Oil zones (OIL): {stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} intervals
    - Gas zones (GAS): {stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} intervals
    - Water zones (WATER): {stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} intervals
    - Dry zones (DRY): {stats.get("interpretation", {}).get("counts", {}).get("DRY", 0)} intervals
''' if stats.get('interpretation') else '    No interpretation results available.\n'
) + '''

'''

def generate_chapter_6_en(info, data, stats):
    well_name = info.get('well_name', 'Unknown Well')
    return f'''================================================================================
                   6. GEOLOGICAL ANALYSIS AND ENGINEERING APPLICATION
================================================================================

6.1 Correlation and Structural Analysis
----------------------------------------
    {well_name} correlation requires regional stratigraphic framework.

6.2 Sedimentary Analysis
----------------------------------------
''' + (generate_facies_text_en(data) if 'FACIES' in data.columns else '    No facies analysis data available.\n\n') + '''
6.3 Reservoir Prediction
----------------------------------------
    (Depths to be provided based on actual data)

6.4 Pressure Analysis
----------------------------------------
    Normal pressure reference from pure water zones.

6.5 Fracture Analysis
----------------------------------------
    Fracture identification requires imaging logs.

6.6 Engineering Recommendations
----------------------------------------
6.6.1 Completion Scheme
    - Prioritize oil/gas zones for testing

6.6.2 Drilling Recommendations
    - Pay attention to hole stability

'''

def generate_chapter_7_en(info, data, stats):
    well_name = info.get('well_name', 'Unknown Well')
    return f'''================================================================================
                    7. INTERPRETATION CONCLUSIONS AND RECOMMENDATIONS
================================================================================

7.1 Main Conclusions
----------------------------------------
    1. Well depth range and data points:
''' + (
    f'       From {data["MD"].min():.1f} m to {data["MD"].max():.1f} m, total {len(data)} records.\n'
    if data is not None and 'MD' in data.columns else '       TBD\n'
) + f'''    2. Identified oil/gas/water zones:
''' + (
    f'''       - Oil zones: {stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)}
       - Gas zones: {stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)}
       - Water zones: {stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)}
''' if stats.get('interpretation') else '       No data available.\n'
) + f'''    3. Possible oil/gas zones:
''' + (
    f'''       - Possible oil: {stats.get("interpretation", {}).get("counts", {}).get("OIL_POSSIBLE", 0)}
       - Possible gas: {stats.get("interpretation", {}).get("counts", {}).get("GAS_POSSIBLE", 0)}
''' if stats.get('interpretation') else '       No data available.\n'
) + f'''    4. Non-reservoir statistics:
''' + (
    f'''       Non-reservoir: {stats.get("interpretation", {}).get("counts", {}).get("NonReservoir", 0)} intervals,
       Accounting for {stats.get("interpretation", {}).get("percentages", {}).get("NonReservoir", 0):.1f}% of total.''' if stats.get('interpretation') else '       No statistical data.\n'
) + f'''    5. Mean porosity: {f"{stats.get('porosity', {}).get('mean', 'TBD'):.4f}" if stats.get('porosity') else 'TBD'},
       Mean water saturation: {f"{stats.get('saturation', {}).get('mean', 'TBD'):.4f}" if stats.get('saturation') else 'TBD'}.

7.2 Recommended Test Intervals
----------------------------------------
    (Specific intervals to be provided based on data)

7.3 Issues and Recommendations
----------------------------------------
7.3.1 Existing Issues
    1. Lack of core data for validation
    2. Limited fracture identification without imaging logs

7.3.2 Recommendations
    1. Conduct coring and core analysis
    2. Perform imaging logs for fracture identification
    3. Arrange testing operations to verify interpretation


7.4 Conclusions
----------------------------------------
    1. Overall quality evaluation of {well_name}.
    2. Profile type and main reservoir types.
    3. Oil/gas shows evaluation and exploration prospect.
    4. Recommend testing main oil/gas zones to verify productivity.


'''

def generate_appendix_en(stats):
    return '''================================================================================
                  APPENDIX A  INTERPRETATION RESULTS DATA TABLE
================================================================================

    Table A-1  Porosity Statistics
    Parameter                           Value
    -----------------------------------
    Mean                               (TBD)
    Std Dev                             (TBD)
    Maximum                            (TBD)
    Minimum                            (TBD)

    Table A-2  Water Saturation Statistics
    Parameter                           Value
    -----------------------------------
    Mean                               (TBD)
    Std Dev                             (TBD)
    Maximum                            (TBD)
    Minimum                            (TBD)

    Table A-3  Interpretation Results Statistics
    Interpretation Type               Count    Percentage(%)
    ----------------------------------------------------
    (TBD)


================================================================================
                 APPENDIX B  CURVE DATA SUMMARY
================================================================================

    Table B-1  Basic Curve Information
    (TBD)


'''

def generate_end_en():
    return '''********************************************************************************
                              END OF REPORT

  Prepared by: Well Log Interpretation System
  Date:        (Auto-generated date)
  Standard:    SY/T 5945-2016 - Well Log Interpretation Report Specification

********************************************************************************

'''

def generate_facies_text_en(data):
    if data is None or 'FACIES' not in data.columns:
        return '    Facies analysis data not available.\n'
    
    facies_counts = data['FACIES'].value_counts()
    result = '    Based on facies analysis:\n'
    for facies, count in facies_counts.items():
        pct = count / len(data) * 100
        result += f'    - {facies}: {count} intervals ({pct:.1f}%)\n'
    return result
