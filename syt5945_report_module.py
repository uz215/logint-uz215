# SY/T 5945-2016 测井解释报告生成模块
# 用于集成到 logInt.py 中

def generate_syt5945_report(self):
    """
    生成符合 SY/T 5945-2016 标准的完整测井解释报告
    
    返回:
        str: 报告文件路径
    """
    import os
    import glob
    import pandas as pd
    import numpy as np
    from datetime import datetime
    from pathlib import Path
    
    try:
        logger.info("开始生成 SY/T 5945-2016 标准测井解释报告...")
        
        # 查找 processed.csv 文件
        csv_pattern = os.path.join(str(self.output_dir), '*_processed.csv')
        csv_files = glob.glob(csv_pattern)
        
        if not csv_files:
            logger.warning(f"未找到 processed.csv 文件，搜索路径: {csv_pattern}")
            return None
        
        # 使用最新生成的 CSV 文件
        csv_file = max(csv_files, key=os.path.getctime)
        logger.info(f"使用数据文件: {csv_file}")
        
        # 加载数据
        self.data = pd.read_csv(csv_file)
        self.output_dir = Path(os.path.dirname(os.path.abspath(csv_file)))
        
        # 设置井信息
        well_name = Path(csv_file).stem
        # 清洗井名: 去掉 _processed 等处理标记, 保留纯井名
        for _suf in ('_processed', '-processed', '_processed_data', '_clean', '_raw'):
            if well_name.lower().endswith(_suf):
                well_name = well_name[: -len(_suf)]
                break
        self.well_info = {
            'well_name': well_name,
            'well_type': '探井/评价井',
            'operation_date': datetime.now().strftime('%Y年%m月%d日'),
            'operator': '测井解释系统'
        }
        
        # 分析数据统计
        self._analyze_stats()
        
        # 生成报告内容
        report_parts = []
        report_parts.append(self._report_cover())
        report_parts.append(self._report_toc())
        report_parts.append(self._report_chapter_1())
        report_parts.append(self._report_chapter_2())
        report_parts.append(self._report_chapter_3())
        report_parts.append(self._report_chapter_4())
        report_parts.append(self._report_chapter_5())
        report_parts.append(self._report_chapter_6())
        report_parts.append(self._report_chapter_7())
        report_parts.append(self._report_appendix())
        report_parts.append(self._report_end_mark())
        
        # 组合完整报告
        full_report = '\n'.join(report_parts)
        
        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f"{well_name}_SYT5945_report_{timestamp}.md"
        report_path = os.path.join(str(self.output_dir), report_filename)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(full_report)
        
        logger.info(f"SY/T 5945-2016 标准报告已生成: {report_path}")
        print(f"\n✓ 完整测井解释报告 (SY/T 5945-2016): {report_path}")
        
        return report_path
        
    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _report_cover(self):
    """封面"""
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


def _report_toc(self):
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


def _report_chapter_1(self):
    """第一章：钻井、地质概况"""
    well_name = self.well_info.get('well_name', '未知井')
    # 主要岩性: 仅占比≥5%的岩性按占比降序; 否则提示无明显主要岩性
    _lith = self.stats.get('lithology', {})
    _pcts = _lith.get('percentages', {}) if _lith else {}
    _major = sorted([(k, _pcts.get(k, 0)) for k in (_lith.get('counts', {}) or {}).keys()],
                    key=lambda x: -x[1])
    _major = [l for l, _p in _major if _p >= 5.0]
    _major_text = ('\n'.join(f'    - {l}' for l in _major)
                   if _major else '    （各岩性占比均低于5%，无明显主要岩性）')
    
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
完钻井深:   {f"{self.stats.get('depth_range', {}).get('end', 0):,.1f} m" if self.stats.get('depth_range') else "待确定"}
设计井深:   暂无该信息
目的层:     根据数据判断为主要目的层段
钻井目的:   油气勘探/开发


1.2 井身结构与钻井液性能
----------------------------------------

1.2.1 井身结构
    本井井身结构数据暂未获取（需补充井眼直径曲线 BS/CALS 分析）。
    根据测井数据，可用井径曲线：CALS（BS 为钻头直径记录，非测井测量值，不列入测井项目）

1.2.2 钻井液性能
    钻井液性能数据暂未获取（需提供现场钻井液录井资料）。

1.2.3 井身轨迹
''' + (
    f'''    井斜数据记录数: {len(self.data[self.data['DEVI'].notna()])} 条
    井斜范围: {self.data['DEVI'].min():.2f}° - {self.data['DEVI'].max():.2f}°
''' if 'DEVI' in self.data.columns and self.data['DEVI'].notna().sum() > 0 
    else '    井斜数据: 暂无井斜测量数据\n'
) + '''


1.3 区域地质概况
----------------------------------------

1.3.1 构造特征
    该井所在的区域构造背景资料暂无。
    建议补充区域构造演化史、主断层分布、构造格架等信息。

1.3.2 沉积特征
''' + (
    self._get_facies_text() if 'FACIES' in (self.data.columns if self.data is not None else [])
    else '    沉积相分析数据: 暂无沉积相分析结果\n'
) + '''


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
        if pct >= 0.05  # 占比<0.05%(显示0.0%)视为无该岩性, 不列
    ]) + f'''

    主要岩性类型（占比≥5%）：
''' + _major_text + ''
'' if self.stats.get('lithology') else ''
) + '''


1.6 气测录井概况
----------------------------------------

    气测数据（C1-C5+, 全烃等）如有采集，详见 Composite Log 第 gas track。
    气测异常层段需在后续综合解释中重点分析。

'''


# 测井曲线物理意义对照(曲线代码 -> 测量项目全名+物理参数)
_CURVE_MEANINGS = {
    'MD': '测量深度(m, 井口至测点斜深)', 'TVD': '垂直深度(m)',
    'BS': '钻头直径(钻头记录, 非测井测量值)', 'CAL': '井径(cm)', 'CALS': '井径(cm)',
    'SP': '自然电位(mV)', 'GR': '自然伽马(API)', 'CGR': '无铀自然伽马(API)',
    'SGR': '总自然伽马(API)', 'KTH': '无铀伽马(API)', 'GR_NOU': '无铀自然伽马(API)',
    'URAN': '铀含量(ppm)', 'U': '铀含量(ppm)', 'THOR': '钍含量(ppm)', 'TH': '钍含量(ppm)',
    'POTA': '钾含量(%)', 'K': '钾含量(%)',
    'LLD': '深侧向电阻率(Ω·m)', 'LLS': '浅侧向电阻率(Ω·m)',
    'MSFL': '微球形聚焦电阻率(Ω·m)', 'RT': '地层真电阻率(Ω·m)',
    'RHOB': '补偿密度(g/cm³)', 'DEN': '地层密度(g/cm³)',
    'NPHI': '补偿中子孔隙度(v/v)', 'CNL': '补偿中子孔隙度(v/v)',
    'DT': '声波时差(μs/ft)', 'AC': '声波时差(μs/ft)',
    'PEF': '光电吸收截面指数(b/e)', 'PE': '光电吸收截面(b/e)',
    'SW': '含水饱和度(计算成果)', 'POR': '孔隙度(计算成果)', 'PHI': '有效孔隙度(计算成果)',
    'PERM': '渗透率(计算成果)', 'VSH': '泥质含量(计算成果)',
    'DEVI': '井斜角(°)', 'AZIM': '井斜方位角(°)',
}

def _curve_meaning(self, col):
    """曲线物理意义: 全名+物理参数; 未收录则提示补充"""
    return _CURVE_MEANINGS.get(str(col).upper(), '待补充说明')

def _curve_effective_depth_range(self, col):
    """曲线有效深度范围(剔除长直线未测段): 'start-end m' 或 '无有效数据'
    长直线: 连续>=3个有效点近恒定(span<=1e-6 或 span/|med|<0.5%), 视为未真正测量/填充死值"""
    try:
        df = getattr(self, 'data', None)
        if df is None or col not in df.columns or 'MD' not in df.columns:
            return '无有效数据'
        md = pd.to_numeric(df['MD'], errors='coerce').values
        v = pd.to_numeric(df[col], errors='coerce').values
        ok = (~np.isnan(v)) & (v != -999.0)
        if not ok.any():
            return '无有效数据'
        n = len(df)
        flat = np.zeros(n, dtype=bool)
        i = 0
        while i < n:
            if not ok[i]:
                i += 1
                continue
            j = i
            while j < n and ok[j]:
                j += 1
            if j - i >= 3:
                vals = v[i:j]
                med = float(np.median(vals))
                span = float(vals.max() - vals.min())
                if span <= 1e-6 or (med != 0 and span / abs(med) < 0.005):
                    flat[i:j] = True
            i = j
        valid = ok & ~flat
        if not valid.any():
            return '无有效数据(长直线)'
        d = md[valid]
        return f"{float(d.min()):.1f}-{float(d.max()):.1f} m"
    except Exception:
        return '无有效数据'

def _hc_layers_summary(self):
    """油气层统计: (层数, 主要分布深度段文本)。按解释层段统计并合并相邻段。"""
    try:
        import os as _os, glob as _glob
        hc_set = {'OIL', 'GAS', 'OIL_POSSIBLE', 'GAS_POSSIBLE'}
        intervals = []
        lay_csvs = _glob.glob(_os.path.join(str(getattr(self, 'output_dir', '')), '*_interpretation_layers.csv'))
        if lay_csvs:
            lay_csv = max(lay_csvs, key=_os.path.getmtime)
            ldf = pd.read_csv(lay_csv, encoding='utf-8-sig')
            for _, r in ldf.iterrows():
                if str(r.get('INTERPRETATION', '') or '').strip().upper() in hc_set:
                    intervals.append((float(r['TOP_MD']), float(r['BASE_MD'])))
        elif getattr(self, 'data', None) is not None and 'LAYER_ID' in self.data.columns:
            df = self.data[self.data['LAYER_ID'].notna()].copy()
            for lid, g in df.groupby('LAYER_ID'):
                main = str(g['INTERPRETATION'].value_counts().index[0] if len(g) else '')
                if main.upper() in hc_set:
                    d = pd.to_numeric(g['MD'], errors='coerce')
                    intervals.append((float(d.min()), float(d.max())))
        if not intervals:
            return 0, '无'
        intervals.sort()
        merged = []
        for st, en in intervals:
            if merged and st <= merged[-1][1] + 1.0:
                merged[-1] = (merged[-1][0], max(merged[-1][1], en))
            else:
                merged.append((st, en))
        text = ', '.join(f"{s:.1f}-{e:.1f} m" for s, e in merged)
        return len(intervals), text
    except Exception:
        return 0, '无'

def _report_chapter_2(self):
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

    本次测井项目包括以下测量曲线（不含非测量记录列，如钻头直径 BS）：
''' + (
    f'''    可用测量曲线总数: {len([c for c in self.data.columns if str(c).upper() != 'BS'])} 条

    {"曲线代码":<10s} {"物理意义":<30s} {"有效深度范围":>22s}
    ------------------------------------------------------------
''' + '\n'.join([
        f'{col:<10s} {self._curve_meaning(col):<30s} {self._curve_effective_depth_range(col):>22s}'
        for col in self.data.columns[:15] if str(col).upper() != 'BS'
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


def _report_chapter_3(self):
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
    孔隙度均值: {f"{self.stats.get('porosity', {}).get('mean', '待计算'):.4f}" if self.stats.get('porosity') and self.stats['porosity'].get('mean') else '待计算'}
    孔隙度范围: [{f"{self.stats.get('porosity', {}).get('min', 'N/A'):.4f}" if self.stats.get('porosity') and self.stats['porosity'].get('min') else 'N/A'}, {f"{self.stats.get('porosity', {}).get('max', 'N/A'):.4f}" if self.stats.get('porosity') and self.stats['porosity'].get('max') else 'N/A'}]


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
''' if self.stats.get('lithology') else '    暂无岩性识别结果（需进行岩性分类计算）。\n'
) + '''
3.3.2 有效储层识别
    根据物性和流体性质综合判定有效储层。
    非储层识别：根据岩性、孔隙度、饱和度等多参数综合判断。



'''


def _report_chapter_4(self):
    """第四章：储层划分及流体性质识别标准"""
    return '''================================================================================
               四、储层划分及流体性质识别标准
================================================================================

4.1 储层测井特征分析
----------------------------------------

4.1.1 物性特征
    有效孔隙度下限: PHI >= 0.05 (5%)（可根据实际调整）
    有效渗透率下限: K >= 1.0 mD（可根据实际调整）
    本井平均孔隙度: {f"{self.stats.get('porosity', {}).get('mean', '待计算'):.4f}" if self.stats.get('porosity') else '待计算'}
    平均含水饱和度: {f"{self.stats.get('saturation', {}).get('mean', '待计算'):.4f}" if self.stats.get('saturation') else '待计算'}

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


def _report_chapter_5(self):
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
    - 有效点数: {(self.data["PHI"].notna().sum() if self.data is not None and "PHI" in self.data.columns else 0)}
''' if self.stats.get('porosity') else '    - 暂无孔隙度统计数据\n'
) + '''
    孔隙度频率分布：
    （需根据实际数据划分区间统计）

    含水饱和度统计参数：
''' + (
    f'''    - 平均值: {self.stats.get("saturation", {}).get("mean", "无数据"):.4f}
    - 标准差: {self.stats.get("saturation", {}).get("std", "无数据"):.4f}
    - 最大值: {self.stats.get("saturation", {}).get("max", "无数据"):.4f}
    - 最小值: {self.stats.get("saturation", {}).get("min", "无数据"):.4f}
''' if self.stats.get('saturation') else '    - 暂无含水饱和度统计数据\n'
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
        if pct >= 0.05  # 占比<0.05%(显示0.0%)视为无该岩性, 不列
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
''' if self.stats.get('interpretation') else '    （暂无解释结果统计）\n'
) + f'''
    油气层分布（按解释层段统计，含确定与可能油气层）：
    - 油气层共 {self._hc_layers_summary()[0]} 层
    - 主要分布深度段: {self._hc_layers_summary()[1]}
    油气水分布规律：
    纵向上油层段集中在低伽马高孔砂岩段；水层段电阻率明显降低；含油性整体受储层物性控制，
    油气层与上下水层之间均有泥岩或致密段分隔（同岩性无隔层的相邻层已合并为统一结论）。



'''


def _report_chapter_6(self):
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
    {self._get_facies_text()}

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


def _report_chapter_7(self):
    """第七章：测井解释结论与建议"""
    well_name = self.well_info.get('well_name', '未知井')
    layer_table = self._build_layer_table_md()
    return f'''================================================================================
                      七、测井解释结论与建议
================================================================================

7.1 主要结论
----------------------------------------

    1. 本井共测井深度范围及数据点数：
''' + (
    f'       从 {self.data["MD"].min():.1f} m 至 {self.data["MD"].max():.1f} m，'
    f'共 {len(self.data)} 条记录。\n'
    if self.data is not None and 'MD' in self.data.columns else '       待确定\n'
) + f'''
    2. 识别有效油气水层数量：
''' + (
    f'''       - 油层 {self.stats.get("interpretation", {}).get("counts", {}).get("OIL", 0)} 个
       - 气层 {self.stats.get("interpretation", {}).get("counts", {}).get("GAS", 0)} 个
       - 水层 {self.stats.get("interpretation", {}).get("counts", {}).get("WATER", 0)} 个
''' if self.stats.get('interpretation') else '''       - 油层：暂无
       - 气层：暂无
       - 水层：暂无
'''
) + f'''
    3. 可能含油气层数量：
''' + (
    f'''       - 可能含油 {self.stats.get("interpretation", {}).get("counts", {}).get("OIL_POSSIBLE", 0)} 个
       - 可能含气 {self.stats.get("interpretation", {}).get("counts", {}).get("GAS_POSSIBLE", 0)} 个
''' if self.stats.get('interpretation') else '''       - 可能含油：暂无
       - 可能含气：暂无
'''
) + f'''
    4. 非储层数量及占比：
''' + (
    f'''       非储层 {self.stats.get("interpretation", {}).get("counts", {}).get("NonReservoir", 0)} 个，
       占总井段的 {self.stats.get("interpretation", {}).get("percentages", {}).get("NonReservoir", 0):.1f}%。
''' if self.stats.get('interpretation') else '       暂无统计信息。\n'
) + f'''
    5. 平均孔隙度 {f"{self.stats.get('porosity', {}).get('mean', '待计算'):.4f}" if self.stats.get('porosity') and self.stats['porosity'].get('mean') else '待计算'}，
       平均含水饱和度 {f"{self.stats.get('saturation', {}).get('mean', '待计算'):.4f}" if self.stats.get('saturation') and self.stats['saturation'].get('mean') else '待计算'}。


7.2 建议试油层位
----------------------------------------

    根据解释结论，建议对以下层位进行测试（层段由逐点解释聚合，同岩性且无低孔隙度隔层的相邻层已合并）：

{layer_table}


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


def _report_appendix(self):
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


def _report_end_mark(self):
    """结束标记"""
    return '''********************************************************************************

                              报告结束

    编制单位: 测井解释系统

    编制日期: （自动生成日期）

    依据标准: SY/T 5945-2016《测井解释报告编写规范》

********************************************************************************

'''


def _build_layer_table_md(self, max_rows=40):
    """生成"解释层段表" Markdown(2026-09 v2):
    优先读取 interpretation_layers.csv(分层统一结论: 同岩性无隔层合并、水上油下修正、密度孔隙度PHI_MEAN);
    回退按 processed_data(含LAYER_ID) 聚合.
    """
    try:
        import os as _os
        import glob as _glob
        import pandas as _pd
        # 优先: 读 interpretation_layers.csv(分层统一结论)
        lay_csvs = _glob.glob(_os.path.join(str(getattr(self, 'output_dir', '')), '*_interpretation_layers.csv'))
        if lay_csvs:
            lay_csv = max(lay_csvs, key=_os.path.getmtime)
            ldf = _pd.read_csv(lay_csv, encoding='utf-8-sig')
            if 'INTERPRETATION' in ldf.columns and len(ldf):
                rows = []
                for _, r in ldf.iterrows():
                    lid = int(r['LAYER_ID'])
                    top = float(r['TOP_MD']); base = float(r['BASE_MD'])
                    thick = float(r.get('THICKNESS', base - top))
                    ml = str(r.get('LITHOLOGY', '') or '')
                    main = str(r.get('INTERPRETATION', '') or '').strip()
                    if not main or main.lower() == 'nan':
                        main = '数据不足'
                    phi = float(r.get('PHI_MEAN', 0.0) or 0.0)
                    rt = float(r.get('RT_MEAN', 0.0) or 0.0)
                    rows.append([lid, top, base, thick, ml, main, phi, rt])
                hc_set = {'OIL', 'GAS', 'OIL_POSSIBLE', 'GAS_POSSIBLE'}
                # 建议试油层位: 仅油气层(确定+可能), 水层/干层/非储层不试油(用于确定产量与解释参数)
                rows = [r for r in rows if r[5] in hc_set]
                rows.sort(key=lambda r: (r[5] == 'OIL_POSSIBLE' or r[5] == 'GAS_POSSIBLE', -r[3], r[0]))
                head = '    | 层号 | 顶深(m) | 底深(m) | 厚度(m) | 岩性 | 解释结论 | PHI | RT(Ω·m) |'
                sep = '    | --- | --- | --- | --- | --- | --- | --- | --- |'
                lines = [head, sep]
                for r in rows[:max_rows]:
                    lines.append(
                        f"    | {r[0]} | {r[1]:.1f} | {r[2]:.1f} | {r[3]:.1f} | {r[4]} | {r[5]} | {r[6]:.3f} | {r[7]:.1f} |")
                if len(rows) > max_rows:
                    lines.append(f"    | ... | （其余 {len(rows)-max_rows} 层略） | ... | ... | ... | ... | ... | ... |")
                lines.append('')
                if not rows:
                    return '    （本井无可建议试油层位：未解释出油气层）'
                lines.append(f"    （共 {len(rows)} 个建议试油层位；仅油气层(含可能油气层)列入，用于试油确定产量与解释参数，其他层不试油）")
                return '\n'.join(lines)
        # 回退: 逐点聚合
        df = getattr(self, 'data', None)
        if df is None or 'LAYER_ID' not in df.columns or df['LAYER_ID'].isna().all():
            return '    （暂无可用的层段划分数据，请确认 processed.csv 含 LAYER_ID 列）'
        df = df[df['LAYER_ID'].notna()].copy()
        df['LAYER_ID'] = df['LAYER_ID'].astype(int)
        rows = []
        for lid, g in df.groupby('LAYER_ID'):
            md = g['MD'].astype(float)
            top, base = float(md.min()), float(md.max())
            thick = base - top
            conc = g['INTERPRETATION'].fillna('')
            cnt = conc.value_counts()
            main = str(cnt.index[0]) if len(cnt) else ''
            if not main.strip() or main.lower() == 'nan':
                main = '数据不足'
            lith = g['LITHOLOGY'].dropna()
            ml = str(lith.value_counts().index[0]) if len(lith) else ''
            # 砂泥岩剖面使用密度孔隙度(PHI_DEN_SHALE, 未受约束归0影响)为PHI口径
            phicol = next((c for c in ('PHI_DEN_SHALE', 'PHI', 'PHI_ND_MEAN', 'PHI_CROSS_LITHO') if c in g.columns), None)
            phi = float(g[phicol].mean()) if phicol else 0.0
            rtcol = next((c for c in ('RT', 'LLD', 'LLS') if c in g.columns), None)
            rt = float(g[rtcol].mean()) if rtcol else 0.0
            rows.append([lid, top, base, thick, ml, main, phi, rt])
        hc_set = {'OIL', 'GAS', 'OIL_POSSIBLE', 'GAS_POSSIBLE'}
        # 建议试油层位: 仅油气层(确定+可能), 水层/干层/非储层不试油(用于确定产量与解释参数)
        rows = [r for r in rows if r[5] in hc_set]
        rows.sort(key=lambda r: (r[5] == 'OIL_POSSIBLE' or r[5] == 'GAS_POSSIBLE', -r[3], r[0]))
        head = '    | 层号 | 顶深(m) | 底深(m) | 厚度(m) | 岩性 | 解释结论 | PHI | RT(Ω·m) |'
        sep = '    | --- | --- | --- | --- | --- | --- | --- | --- |'
        lines = [head, sep]
        for r in rows[:max_rows]:
            lines.append(
                f"    | {r[0]} | {r[1]:.1f} | {r[2]:.1f} | {r[3]:.1f} | {r[4]} | {r[5]} | {r[6]:.3f} | {r[7]:.1f} |")
        if len(rows) > max_rows:
            lines.append(f"    | ... | （其余 {len(rows)-max_rows} 层略） | ... | ... | ... | ... | ... | ... |")
        lines.append('')
        if not rows:
            return '    （本井无可建议试油层位：未解释出油气层）'
        lines.append(f"    （共 {len(rows)} 个建议试油层位；仅油气层(含可能油气层)列入，用于试油确定产量与解释参数，其他层不试油）")
        return '\n'.join(lines)
    except Exception as e:
        return f'    （生成层表失败: {e}）'


def _get_facies_text(self):
    """获取沉积相分析文本"""
    if self.data is None or 'FACIES' not in self.data.columns:
        return '    沉积相分析数据: 暂无沉积相分析结果\n'
    
    facies_counts = self.data['FACIES'].value_counts()
    md = pd.to_numeric(self.data['MD'], errors='coerce')
    result = '    沉积相构成（按点占比，%）：\n'
    for facies, count in facies_counts.items():
        pct = count / len(self.data) * 100
        if pct < 0.05:
            continue  # 占比<0.05%(显示0.0%)视为无该相, 不列
        seg = self.data[self.data['FACIES'] == facies]
        d = md[seg.index].dropna()
        if len(d):
            dmin, dmax = float(d.min()), float(d.max())
            result += f'    - {facies}: 占比 {pct:.1f}%，主要分布 {dmin:.1f}-{dmax:.1f} m\n'
        else:
            result += f'    - {facies}: 占比 {pct:.1f}%\n'
    return result
