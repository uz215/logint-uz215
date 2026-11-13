#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成 SY/T 5945-2016 标准的完整测井解释报告
确保每个章节都存在，即使内容为空也保留结构
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('full_report_generator.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self):
        self.data = None
        self.well_info = {}
        self.stats = {}
        
    def load_data(self, csv_path):
        """加载处理后的数据"""
        logger.info(f"加载数据: {csv_path}")
        self.data = pd.read_csv(csv_path)
        self.output_dir = os.path.dirname(os.path.abspath(csv_path))
        
        # 设置基本信息
        well_name = Path(csv_path).stem
        self.well_info = {
            'well_name': well_name,
            'well_type': '探井/评价井',
            'field_name': '作业区',
            'operation_date': datetime.now().strftime('%Y年%m月%d日'),
            'operator': '测井解释小组'
        }
        
        # 分析数据统计
        self._analyze_stats()
        
        logger.info(f"数据加载完成: {len(self.data)} 条记录")
        
    def _analyze_stats(self):
        """统计分析数据"""
        if self.data is None:
            return
            
        # 岩性统计
        if 'LITHOLOGY' in self.data.columns:
            lith_counts = self.data['LITHOLOGY'].value_counts()
            self.stats['lithology'] = {
                'counts': lith_counts.to_dict(),
                'percentages': ((lith_counts / len(self.data) * 100).round(2)).to_dict()
            }
            
        # 孔隙度统计
        if 'PHI' in self.data.columns:
            phi_valid = self.data['PHI'].dropna()
            self.stats['porosity'] = {
                'mean': phi_valid.mean(),
                'std': phi_valid.std(),
                'min': phi_valid.min(),
                'max': phi_valid.max()
            }
            
        # 饱和度统计
        if 'Sw' in self.data.columns:
            sw_valid = self.data['Sw'].dropna()
            self.stats['saturation'] = {
                'mean': sw_valid.mean(),
                'std': sw_valid.std(),
                'min': sw_valid.min(),
                'max': sw_valid.max()
            }
            
        # 解释结果统计
        if 'INTERPRETATION' in self.data.columns:
            int_counts = self.data['INTERPRETATION'].value_counts()
            self.stats['interpretation'] = {
                'counts': int_counts.to_dict(),
                'percentages': ((int_counts / len(self.data) * 100).round(2)).to_dict()
            }
    
    def generate_report(self, output_dir=None):
        """生成完整报告"""
        if output_dir:
            self.output_dir = output_dir
            
        Path(self.output_dir).mkdir(exist_ok=True, parents=True)
        
        logger.info("开始生成报告...")
        
        # 构建报告各章节
        report_parts = [
            self._cover_page(),           # 封面
            self._toc(),                  # 目录
            self._chapter_1(),            # 第一章
            self._chapter_2(),            # 第二章
            self._chapter_3(),            # 第三章
            self._chapter_4(),            # 第四章
            self._chapter_5(),            # 第五章
            self._chapter_6(),            # 第六章
            self._chapter_7(),            # 第七章
            self._appendix(),             # 附录
            self._end_mark()              # 结束标记
        ]
        
        # 组合完整报告
        full_report = '\n'.join(report_parts)
        
        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        well_name = self.well_info.get('well_name', 'Unknown')
        report_filename = f"{well_name}_SYT5945_report_{timestamp}.md"
        report_path = Path(self.output_dir) / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(full_report)
        
        logger.info(f"报告已生成: {report_path}")
        return str(report_path)
    
    def _cover_page(self):
        """封面页"""
        well_name = self.well_info.get('well_name', 'XXXX')
        return f'''

================================================================================

                          {well_name}
                          测井解释报告

================================================================================

  编制单位: {self.well_info.get('operator', '测井解释系统')}

  编制日期: {self.well_info.get('operation_date', datetime.now().strftime('%Y年%m月%d日'))}

  报告人:   AI自动生成

  审核人:   {self.well_info.get('well_type', '专业人员')}

  技术负责人: {self.well_info.get('operator', '自动化系统')}


本标准依据 SY/T 5945-2016《测井解释报告编写规范》编制



'''

    def _toc(self):
        """目录"""
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

    def _chapter_1(self):
        """第一章：钻井、地质概况"""
        well_name = self.well_info.get('well_name', '未知井')
        
        return f'''================================================================================
                        一、钻井、地质概况
================================================================================

1.1 基础数据
----------------------------------------

井号:       {well_name}
井别:       {self.well_info.get('well_type', '探井/评价井')}
地理位置:   暂无该信息（需补充井位坐标）
构造位置:   暂无该信息（需提供构造单元）
地面海拔:   暂无该信息（需提供大地水准面）
磁偏角:     暂无该信息

开钻日期:   暂无该信息
完钻日期:   暂无该信息
完钻井深:   {f"{self.stats.get('depth_range', {}).get('end', 'N/A'):,.1f} m" if 'depth_range' in self.stats else "待确定"}
设计井深:   暂无该信息
目的层:     根据数据判断为主要目的层段
钻井目的:   油气勘探/开发


1.2 井身结构与钻井液性能
----------------------------------------

1.2.1 井身结构
    本井井身结构数据暂未获取（需补充井眼直径曲线 BS/CALS 分析）。
    根据测井数据，可用井径曲线：BS, CALS

1.2.2 钻井液性能
    钻井液性能数据暂未获取（需提供现场钻井液录井资料）。

1.2.3 井身轨迹
''' + (f'''    井斜数据记录数: {len(self.data[self.data['DEVI'].notna()])} 条（如有DEVI曲线）
    井斜范围: {self.data['DEVI'].min():.2f}° - {self.data['DEVI'].max():.2f}°（如有数据）
''' if 'DEVI' in self.data.columns else '    井斜数据: 暂无井斜测量数据\n') + '''


1.3 区域地质概况
----------------------------------------

1.3.1 构造特征
    该井所在的区域构造背景资料暂无。
    建议补充区域构造演化史、主断层分布、构造格架等信息。

1.3.2 沉积特征
''' + (self._get_facies_analysis() if 'FACIES' in self.data.columns else '    沉积相分析数据: 暂无沉积相分析结果\n') + '''


1.4 邻井钻探成果
----------------------------------------

    邻井资料暂无（建议补充周边井的钻探成效、测井解释成果及试油情况）。

1.5 岩性及油气显示描述
----------------------------------------

    根据岩性识别结果统计：

    岩性组成统计：
''' + (
    f'''    {"岩性类型":<15s} {"点数":>8s} {"占比(%)":>8s}
    -----------------------------------
''' + '\n'.join([
        f'    {lith:<15s} {count:>8d} {pct:>7.2f}%' 
        for lith, count in self.stats.get('lithology', {}).get('counts', {}).items()
        for pct in [self.stats.get('lithology', {}).get('percentages', {}).get(lith, 0)]
    ]) + f'''

    主要岩性类型：
''' + '\n'.join([f'    - {lith}' for lith in self.stats.get('lithology', {}).get('counts', {}).keys()]) or '    （暂无岩性统计信息）' or '' or '',
'' if 'LITHOLOGY' not in self.data.columns else '''

    暂无岩性识别结果（需进行岩性分类计算）。
'''
) + '''


1.6 气测录井概况
----------------------------------------

    气测数据（C1-C5+, 全烃等）如有采集，详见 Composite Log 第 gas track。
    气测异常层段需在后续综合解释中重点分析。

'''

    def _get_facies_analysis(self):
        """获取沉积相分析结果"""
        if self.data is None or 'FACIES' not in self.data.columns:
            return '    沉积相分析数据: 暂无沉积相分析结果\n'
        
        facies_counts = self.data['FACIES'].value_counts()
        result = '    根据沉积相分析结果：\n'
        for facies, count in facies_counts.items():
            pct = count / len(self.data) * 100
            result += f'    - {facies}: {count} 条 ({pct:.1f}%)\n'
        return result
    
    def _chapter_2(self):
        """第二章：测井施工过程控制及资料质量评价"""
        return '''================================================================================
           二、测井施工过程控制及测井资料质量评价
================================================================================

2.1 测井仪器型号及刻度校验
----------------------------------------

    测井仪器型号：暂无该信息（需提供测井服务公司的仪器清单）
    测前刻度：暂无该信息
    测后刻度：暂无该信息
    依据标准：GB/T 16523《测井作业技术规范》


2.2 测井项目与测量参数
----------------------------------------

    本次测井项目包括以下曲线：
''' + (
    f'''    可用曲线总数: {len(self.data.columns)} 条

    {"曲线代码":<12s} {"物理意义":<30s} {"有效数据":>10s}
    ------------------------------------------------------------
''' + '\n'.join([
        f'{col:<12s} {col:<30s} {self.data[col].notna().sum():>10d}'
        for col in self.data.columns[:15]
    ]) + '\n' if self.data is not None else ''
) + '''

2.3 测井施工过程控制
----------------------------------------

2.3.1 特殊测井项目
    本次测井是否有成像测井、核磁共振等特殊测井项目待定。

2.3.2 测井环境评价
    井眼扩大情况：根据井径曲线(BS/CALS)与钻头直径对比分析...
    泥浆环境影响：泥浆密度、滤液电阻率对电阻率测井的影响如有原始数据则已进行校正。


2.4 测井资料质量评价
----------------------------------------

2.4.1 评价标准
    执行标准：SY/T 5132-2012《测井原始资料质量要求》

2.4.2 逐曲线质量评分
''' + (
    f'''    {"曲线名称":<15s} {"完整率(%)":>10s} {"等级":<8s} {"备注"}
    -----------------------------------------------------------------------
''' + '\n'.join([
        f'{col:<15s} {self.data[col].notna().sum()/len(self.data)*100:>9.2f}% {"优秀" if self.data[col].notna().sum()/len(self.data) > 0.95 else "合格":<8s}'
        for col in ['GR', 'NPHI', 'RHOB', 'DT', 'LLD'] if col in self.data.columns
    ]) + '\n' if self.data is not None else ''
) + '''
2.4.3 总体质量评定
    （需根据实际曲线完整率进行评定）


'''

    def _chapter_3(self):
        """第三章：数据处理情况"""
        return '''================================================================================
                         三、数据处理情况
================================================================================

3.1 测井资料标准化
----------------------------------------

    深度校正：如进行了深度对齐，则已完成深度对齐，消除测速造成的深度偏差。
    环境校正：如有必要，已完成井眼、泥浆、温度等环境因素的影响校正。


3.2 测井解释模型选择
----------------------------------------

3.2.1 剖面类型判定
    根据实际数据进行矿物定量计算和交汇图分析来确定剖面类型。

3.2.2 矿物定量计算模型
    采用合适的矿物分解模型，输入相应的测井曲线。
    优化矿物组分：根据实际情况确定
    正则化系数：根据实际情况调整

3.2.3 孔隙度计算方法
    可采用多种方法并行计算孔隙度：
    - 密度法
    - 中子法
    - 声波法
    - 共振法
    主孔隙度来源根据实际情况确定
    孔隙度均值: {f"{self.stats.get('porosity', {}).get('mean', 'N/A'):.4f}" if 'porosity' in self.stats and self.stats['porosity'].get('mean') else '待计算'}
    孔隙度范围: [{f"{self.stats.get('porosity', {}).get('min', 'N/A'):.4f}" if 'porosity' in self.stats and self.stats['porosity'].get('min') else 'N/A'}, {f"{self.stats.get('porosity', {}).get('max', 'N/A'):.4f}" if 'porosity' in self.stats and self.stats['porosity'].get('max') else 'N/A'}]


3.2.4 含水饱和度计算方法
    采用 Arps 经验公式或其他合适的方法。
    视地层水电阻率 Rw 需从典型水层自动检测确定。
    电阻率选择：通常选用 LLD (深侧向电阻率)


3.3 处理成果说明
----------------------------------------

3.3.1 岩性识别
''' + (
    f'''    识别岩性类型：{", ".join(self.stats.get("lithology", {}).get("counts", {}).keys())}
    砂岩占比: {self.stats.get("lithology", {}).get("percentages", {}).get("sandstone", 0):.1f}%
    页岩占比: {self.stats.get("lithology", {}).get("percentages", {}).get("shale", 0):.1f}%
''' if self.stats.get('lithology') else '''    暂无岩性识别结果（需进行岩性分类计算）。
'''
) + '''
3.3.2 有效储层识别
    根据物性和流体性质综合判定有效储层。
    非储层识别：根据岩性、孔隙度、饱和度等多参数综合判断。



'''

    def _chapter_4(self):
        """第四章：储层划分及流体性质识别标准"""
        return '''================================================================================
               四、储层划分及流体性质识别标准
================================================================================

4.1 储层测井特征分析
----------------------------------------

4.1.1 物性特征
    有效孔隙度下限: PHI >= 0.05 (5%)（可根据实际调整）
    有效渗透率下限: K >= 1.0 mD（可根据实际调整）
    本井平均孔隙度: {f"{self.stats.get('porosity', {}).get('mean', '待计算'):.4f}" if 'porosity' in self.stats else '待计算'}
    平均含水饱和度: {f"{self.stats.get('saturation', {}).get('mean', '待计算'):.4f}" if 'saturation' in self.stats else '待计算'}

4.1.2 电性特征
    油层: 中高电阻率，中等偏低含水饱和度
    气层: 高电阻率，低含水饱和度，中子-密度交叉出现负异常
    水层: 低电阻率，高含水饱和度 (Sw > 0.8)


4.2 有效储层判别标准
----------------------------------------

    同时满足以下条件判定为有效储层：
    ① PHI >= 0.05 (孔隙度大于等于 5%)
    ② VALID_CURVES_COUNT >= 3 (至少 3 条有效曲线)
    ③ 非特殊岩性（非煤层、盐岩等）


4.3 油气水层判别方法及标准
----------------------------------------

4.3.1 判别流程
    基于多参数联合判别法：
    1. 含水饱和度 Sw 阈值法
    2. 电阻率 Rt 阈值法
    3. 泥质含量 Vsh 约束
    4. 孔隙度 PHI 有效性验证

4.3.2 判别标准

    {"解释结论":<18s} {"判别标准":<35s} {"显示颜色":<10s}
    '-'*68
    OIL (油层)           Sw < 0.5 & Rt 中等偏高 & PHI >= 0.05    绿色        
    GAS (气层)           Sw < 0.4 & Rt 高 & 中子密度负异常           红色        
    WATER (水层)         Sw > 0.8 & Rt 低                     蓝色        
    DRY (干层)           PHI < 0.05 或 Vsh 过高                 棕色        
    OIL_POSSIBLE (可能含油)  0.5 <= Sw < 0.7 且其他参数有利             浅绿色       
    GAS_POSSIBLE (可能含气)  0.4 <= Sw < 0.6 且电阻率偏高              浅珊瑚红      
    NonReservoir (非储层) 有效曲线不足或物性极差                         白色（不显示）   


4.4 储层分类
----------------------------------------

    根据矿物组分和物性特征，储层分为：
    - 碎屑岩储层：砂岩、粉砂岩
    - 碳酸盐岩储层：灰岩、白云岩（本井未识别时注明）
    - 特殊岩性储层：火山岩、蒸发岩（本井未识别时注明）



'''

    def _chapter_5(self):
        """第五章：储层综合评价"""
        return '''================================================================================
                         五、储层综合评价
================================================================================

5.1 储层物性特征
----------------------------------------

    孔隙度统计参数：
''' + (
    f'''    - 平均值: {self.stats.get("porosity", {}).get("mean", "无数据"):.4f}
    - 标准差: {self.stats.get("porosity", {}).get("std", "无数据"):.4f}
    - 最大值: {self.stats.get("porosity", {}).get("max", "无数据"):.4f}
    - 最小值: {self.stats.get("porosity", {}).get("min", "无数据"):.4f}
    - 有效点数: {(self.data["PHI"].notna().sum() if "PHI" in self.data.columns else 0)}
''' if 'porosity' in self.stats else '''    - 暂无孔隙度统计数据
'''
) + '''
    孔隙度频率分布：
    （需根据实际数据划分区间统计）

    含水饱和度统计参数：
''' + (
    f'''    - 平均值: {self.stats.get("saturation", {}).get("mean", "无数据"):.4f}
    - 标准差: {self.stats.get("saturation", {}).get("std", "无数据"):.4f}
    - 最大值: {self.stats.get("saturation", {}).get("max", "无数据"):.4f}
    - 最小值: {self.stats.get("saturation", {}).get("min", "无数据"):.4f}
''' if 'saturation' in self.stats else '''    - 暂无含水饱和度统计数据
'''
) + '''

5.2 岩性及物性特征描述
----------------------------------------

    根据岩性统计结果，对各岩性类型的物性进行分析：
''' + (
    '\n'.join([
        f'''    {lith}:
      分布占比: {pct:.1f}%
'''
        for lith, pct in self.stats.get('lithology', {}).get('percentages', {}).items()
    ]) if self.stats.get('lithology') else '    暂无岩性统计信息\n'
) + '''

5.3 储层与非储层分布
----------------------------------------

    有效解释总层段数量：（根据实际解释结果统计）
    - 油气水层数量及占比
    - 非储层数量及占比


5.4 流体性质分析
----------------------------------------

    流体性质统计：
''' + (
    f'''    - 油层 (OIL): {self.stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} 条 ({self.stats.get("interpretation", {}).get("percentages", {}).get("OIL", 0):.1f}%)
    - 气层 (GAS): {self.stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} 条 ({self.stats.get("interpretation", {}).get("percentages", {}).get("GAS", 0):.1f}%)
    - 水层 (WATER): {self.stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} 条 ({self.stats.get("interpretation", {}).get("percentages", {}).get("WATER", 0):.1f}%)
    - 干层 (DRY): {self.stats.get("interpretation", {}).get("counts", {}).get("DRY", 0)} 条 ({self.stats.get("interpretation", {}).get("percentages", {}).get("DRY", 0):.1f}%)
    - 可能含油 (OIL_POSSIBLE): {self.stats.get("interpretation", {}).get("counts", {}).get("OIL_POSSIBLE", 0)} 条
    - 可能含气 (GAS_POSSIBLE): {self.stats.get("interpretation", {}).get("counts", {}).get("GAS_POSSIBLE", 0)} 条
''' if 'interpretation' in self.stats else '''    （暂无解释结果统计）
'''
) + '''
    油气水分布规律：
    根据实际解释结果给出分析和评价。



'''

    def _chapter_6(self):
        """第六章：地质分析与工程应用"""
        well_name = self.well_info.get('well_name', '未知井')
        return f'''================================================================================
                      六、地质分析与工程应用
================================================================================

6.1 地层对比与构造分析
----------------------------------------

    {well_name}井地层对比需结合区域地层格架进行。
    建议补充标准层（如显著 GR 突变层）作为对比标志层。


6.2 沉积相分析及认识
----------------------------------------
''' + (
    f'''    根据沉积相分析结果：
    {self._get_facies_analysis()}

    沉积环境认识：
    需要结合区域沉积相图、岩心观察等进行综合分析。
''' if 'FACIES' in (self.data.columns if self.data is not None else []) else '''    暂无沉积相分析结果。

    沉积环境认识：
    建议补充沉积相研究。
'''
) + '''

6.3 储层预测
----------------------------------------

    根据测井解释结果，优质储层（PHI >= 0.2, Sw < 0.6）主要分布：
    （需结合具体数据给出层位深度范围）


6.4 地层压力分析
----------------------------------------

    正常压力体系：Sw ≈ 1.0 的纯水层段可作为静水压力的参考。
    异常高压：需结合 D指数、偏移量等方法进一步分析。


6.5 裂缝分析
----------------------------------------

    本次测井如有未包含成像测井资料，无法进行裂缝的精细识别。
    建议通过微电阻率成像或声波偶极各向异性进行裂缝预测。


6.6 工程应用建议
----------------------------------------

6.6.1 完井方案建议
    - 优先对油气层段进行试油测试
    - 建议试油层位见第七章

6.6.2 钻井建议
    - 注意井眼稳定性，特别是高温高压层段
    - 钻井液密度设计需考虑地层压力系数



'''

    def _chapter_7(self):
        """第七章：测井解释结论与建议"""
        well_name = self.well_info.get('well_name', '未知井')
        return f'''================================================================================
                      七、测井解释结论与建议
================================================================================

7.1 主要结论
----------------------------------------

    1. 本井共测井深度范围及数据点数：
''' + (
    f'       从 {self.data["MD"].min():.1f} m 至 {self.data["MD"].max():.1f} m，'
    f'共 {len(self.data)} 条记录。\n'
    if 'MD' in self.data.columns else '       待确定\n'
) + f'''
    2. 识别有效油气水层数量：
''' + (
    f'''       - 油层 {self.stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} 个
       - 气层 {self.stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} 个
       - 水层 {self.stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} 个
''' if 'interpretation' in self.stats else '''       - 油层：暂无
       - 气层：暂无
       - 水层：暂无
'''
) + f'''
    3. 可能含油气层数量：
''' + (
    f'''       - 可能含油 {self.stats.get("interpretation", {}).get("counts", {}).get("OIL_POSSIBLE", 0)} 个
       - 可能含气 {self.stats.get("interpretation", {}).get("counts", {}).get("GAS_POSSIBLE", 0)} 个
''' if 'interpretation' in self.stats else '''       - 可能含油：暂无
       - 可能含气：暂无
'''
) + f'''
    4. 非储层数量及占比：
''' + (
    f'''       非储层 {self.stats.get("interpretation", {}).get("counts", {}).get("NonReservoir", 0)} 个，
       占总井段的 {self.stats.get("interpretation", {}).get("percentages", {}).get("NonReservoir", 0):.1f}%。
''' if 'interpretation' in self.stats else '       暂无统计信息。\n'
) + f'''
    5. 平均孔隙度 {f"{self.stats.get('porosity', {}).get('mean', '待计算'):.4f}" if 'porosity' in self.stats and self.stats['porosity'].get('mean') else '待计算'}，
       平均含水饱和度 {f"{self.stats.get('saturation', {}).get('mean', '待计算'):.4f}" if 'saturation' in self.stats and self.stats['saturation'].get('mean') else '待计算'}。


7.2 建议试油层位
----------------------------------------

    根据解释结论，建议对以下层位进行测试：
''' + (
    f'''    {"序号":>4s} | {"解释类型":<15s} | {"顶深(m)":>8s} | {"底深(m)":>8s} | {"厚度(m)":>8s}
    ----------------------------------------------------------------------
    （需结合具体层位数据给出建议）
''' if 'interpretation' in self.stats else '''    （暂无解释结果，无法给出试油层位建议）
'''
) + '''

7.3 存在问题与建议
----------------------------------------

7.3.1 存在的问题
    1. PE曲线绝对值如有问题，仅趋势可用，影响矿物定量精度
    2. 缺乏岩心实验数据对比验证
    3. 如未包含成像测井资料，裂缝识别能力有限
    4. 气测录井数据需与测井解释综合对比

7.3.2 工作建议
    1. 建议补充取心作业，开展岩心实验分析
    2. 建议进行成像测井，精细识别裂缝
    3. 加强邻井资料对比，完善区域岩石物理模型
    4. 尽快安排试油作业，验证测井解释结论


7.4 认识及结论
----------------------------------------

    1. {well_name}井测井资料质量总体评价（根据实际质量评定填写）。
    2. 本井剖面类型及主要储层类型。
    3. 油气显示评价及勘探前景。
    4. 建议对主力油气层段进行试油测试，验证产能。


'''

    def _appendix(self):
        """附录"""
        return '''================================================================================
                       附录 A  测井解释成果数据表（摘要）
================================================================================


    以下为测井解释主要参数统计表：

    表A-1  孔隙度统计参数
    参数                             数值
    -----------------------------------
    平均值                        （待填入）
    标准差                        （待填入）
    最大值                        （待填入）
    最小值                        （待填入）
    中位数                        （待填入）

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

    {"曲线代码":<12s} {"均值":>10s} {"标准差":>10s} {"最小值":>10s} {"最大值":>10s}
    -------------------------------------------------------
    （待填入）


'''

    def _end_mark(self):
        """结束标记"""
        return '''********************************************************************************

                              报告结束

    编制单位: 测井解释系统

    编制日期: （自动生成日期）

    依据标准: SY/T 5945-2016《测井解释报告编写规范》

********************************************************************************

'''


def main():
    """主函数"""
    csv_path = r'output\XIMENIA-5\XIMENIA-5_processed.csv'
    
    if not os.path.exists(csv_path):
        print(f"文件不存在: {csv_path}")
        sys.exit(1)
    
    generator = ReportGenerator()
    
    # 加载数据
    generator.load_data(csv_path)
    
    # 生成报告
    report_path = generator.generate_report('output')
    
    print(f"\n完整报告已生成:")
    print(f"  Markdown 格式: {report_path}")
    print(f"\n报告符合 SY/T 5945-2016 标准")
    print(f"所有章节均已包含，部分暂时缺失的数据标注为'暂无'或'待补充'")


if __name__ == "__main__":
    main()
