from numpy.core import einsumfunc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.neural_network import MLPClassifier
import seaborn as sns
from datetime import datetime
import logging
from pathlib import Path
import json
import warnings
import sys
import traceback
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics.pairwise import cosine_similarity

import os

warnings.filterwarnings('ignore')

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GasLoggingQC:
    """DATA QC"""

    def __init__(self, config_path=None):
        self.config = self._load_config(config_path)
        self.qc_report = {}

    def _load_config(self, config_path):
        """QC CONFIG LOADING"""
        default_config = {
            'depth_range': [0, 10000],  # 深度范围(m)
            'Total15_range': [0, 1000000],  # 全烃范围(ppm)
            'C1_range': [0, 1000000],  # C1范围(ppm)
            'C2_range': [0, 1000000],  # C2范围(ppm)
            'C3_range': [0, 1000000],  # C3范围(ppm)
            'IC4_range': [0, 1000000],  # IC4范围(ppm)
            'NC4_range': [0, 1000000],  # NC4范围(ppm)
            'IC5_range': [0, 1000000],  # IC4范围(ppm)
            'NC5_range': [0, 1000000],  # NC4范围(ppm)
            'rop_range': [0, 2000],  # 钻时范围(min/m)
            'missing_threshold': 0.3,  # 缺失值阈值
            'outlier_method': 'iqr',  # 异常值检测方法
            'smoothing_window': 5,  # 平滑窗口大小
            'duplicate_precision': 2  # 去重精度(小数位数)
        }
        return default_config

    def run_qc(self, df):
        """COMPLETE QC"""
        logger.info("STARTING QC...")

        # 1. 数据完整性检查
        df = self._check_completeness(df)

        # 2. 异常值检测
        df = self._detect_outliers(df)

        # 3. 数据平滑处理
        #df = self._smooth_data(df)

        # 4. 单位统一和格式标准化
        df = self._standardize_format(df)

        logger.info("QC COMPLETED")
        return df, self.qc_report

    def _check_completeness(self, df):
        """COMPUTING ADDING FIELD"""
        print("ADDING FIELDS...")

        # 1.总含量计算
        hc1 = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
        hc2 = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'BZ', 'C7', 'MCH', 'C8', 'TL']
        hc3 = ['C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
        hc4 = ['C1', 'C2', 'C3']
        hc5 = ['C1', 'C2', 'C3', 'IC4', 'NC4']
        hc7 = ['C7', 'MCH', 'TL']
        hc8 = ['C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'BZ', 'C7', 'MCH', 'C8', 'TL']
        hc9 = ['C1in', 'C2in', 'C3in', 'IC4in', 'NC4in', 'IC5in', 'NC5in', 'C6in', 'BZin', 'C7in', 'MCHin', 'C8in', 'TLin']

        # 总C4,C5
        df['C4'] = df['IC4'] + df['NC4']
        df['C5'] = df['IC5'] + df['NC5']
        # C1-3之和
        available_cols4 = [col for col in hc4 if col in df.columns]
        df['Total13'] = df[available_cols4].sum(axis=1)
        # C1-4之和
        available_cols5 = [col for col in hc5 if col in df.columns]
        df['Total14'] = df[available_cols5].sum(axis=1)
        # C1到C5之和
        available_cols1 = [col for col in hc1 if col in df.columns]
        df['Total15'] = df[available_cols1].sum(axis=1)
        # C1到C8之和
        available_cols2 = [col for col in hc2 if col in df.columns]
        df['Total18'] = df[available_cols2].sum(axis=1)
        # C2到C5之和
        available_cols3 = [col for col in hc3 if col in df.columns]
        df['Total25'] = df[available_cols3].sum(axis=1)
        # C2+之和
        available_cols3 = [col for col in hc8 if col in df.columns]
        df['Total28'] = df[available_cols3].sum(axis=1)
        # C7之和
        available_cols4 = [col for col in hc7 if col in df.columns]
        df['Total7'] = df[available_cols4].sum(axis=1)
        #总烃背景值Cbg
        available_cols4 = [col for col in hc9 if col in df.columns]
        df['Totalbg'] = df[available_cols4].sum(axis=1)
        # 总烃基线值Cbaseline,取前30个Total18的25%分布处的值(就是25%的数小于该数值)
        df['Totalbsl'] = df['Total18'].rolling(30, center=True, min_periods=1).quantile(0.25)
        # 2 气体比值计算
        # 2.1Pixel method ratio
        if all(col in df.columns for col in ['C1', 'C2']):
            df['C1C2'] = np.where(df['C2'] == 0, 0, round(df['C1'] / df['C2'], 2))

        if all(col in df.columns for col in ['C1', 'C3']):
            df['C1C3'] = np.where(df['C3'] == 0, 0, round(df['C1'] / df['C3'], 2))
        if all(col in df.columns for col in ['C2', 'C3']):
           df['C2C3'] = np.where(df['C3'] == 0, 0, round(df['C2'] / df['C3'], 2))

        if all(col in df.columns for col in ['C1', 'C4']):
            df['C1C4'] = np.where(df['C4'] == 0, 0, round(df['C1'] / df['C4'], 2))

        if all(col in df.columns for col in ['C1', 'C5']):
            df['C1C5'] = np.where(df['C5'] == 0, 0, round(df['C1'] / (df['C5']), 2))

        # 2.2 Ternary plot
        if all(col in df.columns for col in ['C1', 'Total18']):
            df['C1Ct'] = np.where(df['Total18'] == 0, 0, round(df['C1'] / df['Total18'], 2))  # C1比烃总和
        if all(col in df.columns for col in ['C2', 'Total18']):
            df['C2Ct'] = np.where(df['Total18'] == 0, 0, round(df['C2'] / df['Total18'], 2))  # C2比烃总和
        if all(col in df.columns for col in ['C3', 'Total18']):
            df['C3Ct'] = np.where(df['Total18'] == 0, 0, round(df['C3'] / df['Total18'], 2))  # C3比烃总和
        if all(col in df.columns for col in ['IC4', 'NC4', 'Total18']):
            df['C4Ct'] = np.where(df['Total18'] == 0, 0, round((df['IC4'] + df['NC4']) / df['Total18'], 2))  # C4比烃总和
        if all(col in df.columns for col in ['C1', 'Total14']):
            df['C1pt'] = np.where(df['Total14'] == 0, 0, round(df['C1'] / df['Total14'], 2))  # C1比C1-4总和
        if all(col in df.columns for col in ['C2', 'Total14']):
            df['C2pt'] = np.where(df['Total14'] == 0, 0, round(df['C2'] / df['Total14'], 2))  # C2比C1-4总和
        if all(col in df.columns for col in ['C3', 'Total14']):
            df['C3pt'] = np.where(df['Total14'] == 0, 0, round(df['C3'] / df['Total14'], 2))  # C3比C1-4总和
        if all(col in df.columns for col in ['NC4', 'Total14']):
            df['NC4pt'] = np.where(df['Total14'] == 0, 0, round(df['NC4'] / df['Total14'], 2))  # NC4比C1-4总和
        # 2.3 3H plot
        if all(col in df.columns for col in hc1):
            df['WH'] = np.where(df['Total15'] == 0, 0, round(df['Total25'] / df['Total15'], 2))
        if all(col in df.columns for col in hc1):
            df['BH'] = np.where((df['Total25'] - df['C2']) == 0, 0,
                                round((df['C1'] + df['C2']) / (df['Total25'] - df['C2']), 2))
        if all(col in df.columns for col in hc1):
            df['CH'] = np.where(df['C3'] == 0, 0, round((df['Total25'] - df['C2'] - df['C3']) / df['C3'], 2))
        # 2.4 radar plot
        if all(col in df.columns for col in ['Total18','Totalbsl']):
           df['TMUL'] = np.where(df['Totalbsl'] == 0, 0, round(df['Total18'] / df['Totalbsl'], 2)) #计算异常幅度
        if all(col in df.columns for col in ['C1Ct']):
           df['C2Ppt'] = round(1-df['C1Ct'], 2) #计算C2+占比
        if all(col in df.columns for col in ['Total7', 'MCH']):
           df['C7sMCH'] = np.where(df['MCH'] == 0, 0, round(df['Total7'] / df['MCH'], 2))
        if all(col in df.columns for col in ['Total7', 'TL']):
           df['TLC7s'] = np.where(df['Total7'] == 0, 0, round(df['TL'] / df['Total7'], 2))

        
        #if all(col in df.columns for col in hc1):

        # 2.4Fluid idex
        if all(col in df.columns for col in hc2):
            df['lg'] = np.where((df['Total18'] - df['Total13']) == 0, 0,
                                round(df['C1'] / (df['Total18'] - df['Total13']), 2))
            df['lo'] = np.where(df['Total13'] == 0, 0,
                                round((df['Total18'] - df['Total13'] - df['BZ'] - df['TL']) * 2 / df['Total13'], 2))
            df['lw'] = np.where((df['C6'] + df['C7']) == 0, 0, round((df['BZ'] + df['TL']) / (df['C6'] + df['C7']), 2))

        # 3. 干燥系数 (C1/总烃含量)
        # if all(col in df.columns for col in ['C1', 'Total15']):
        df['DRYNESS'] = np.where(df['Total15'] == 0, 0, round(df['C1'] / df['Total15'], 2))

        # 4. 气体湿度因子 (重烃/轻烃)
        light_hc = ['C1', 'C2']
        heavy_hc = ['C3', 'C4', 'C5', 'C6', 'C7', 'C8']

        light_cols = [col for col in light_hc if col in df.columns]
        heavy_cols = [col for col in heavy_hc if col in df.columns]

        df['LIGHT_HC'] = df[light_cols].sum(axis=1)
        df['HEAVY_HC'] = df[heavy_cols].sum(axis=1)

        df['GAS_HUMIDITY'] = np.where(df['LIGHT_HC'] == 0, 0,
                                             df['HEAVY_HC'] / df['LIGHT_HC'])
        df['LIGHT_HEAVY_RATIO'] = np.where(df['HEAVY_HC'] == 0, 0,
                                           df['LIGHT_HC'] / df['HEAVY_HC'])
        """DATA INTEGRITY CHECKING"""
        logger.info("INTEGRITY CHECKING...")

        # 检查必要字段
        countn=0
        required_cols = ['MD', 'C1', 'C2', 'C3', 'IC4', 'NC4','IC5', 'NC5','C6','MCH','TL','BZ','C7','C8','ROP','SPP']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.warning(f"REQUIRED FIELD MISSING: {missing_cols}")
            df['QC'] = 1
        else: 
             countn=((df[required_cols] <= 0) | df[required_cols].isna()).sum(axis=1)
             df['QC'] = round(countn/16,2)
              
        # 删除缺失值过多的列
        #cols_to_drop = missing_ratio[missing_ratio > self.config['missing_threshold']].index
        #if len(cols_to_drop) > 0:
            #logger.warning(f"删除缺失值过多的列: {list(cols_to_drop)}")
            #df = df.drop(columns=cols_to_drop)

        # 对关键字段进行插值
        for col in required_cols:
            if col in df.columns:
                df[col] = df[col].interpolate(method='linear')

        return df

    def _detect_outliers(self, df):
        required_cols = ['MD', 'Total15', 'C1', 'C2', 'C3', 'IC4', 'NC4','IC5', 'NC5','C6','MCH','TL','BZ','C7','C8','ROP','SPP']
        """OUTLIER DETECTION"""
        logger.info("OUTLIER DETECTING...")

        outlier_summary = {}

        if all(col in df.columns for col in required_cols):
           for col, (min_val, max_val) in [
               ('Total15', self.config['Total15_range']),
               ('C1', self.config['C1_range']),
               ('C2', self.config['C2_range']),
               ('C3', self.config['C3_range']),
               ('IC4', self.config['IC4_range']),
               ('NC4', self.config['NC4_range']),
               ('ROP', self.config['rop_range'])
               ]:

            if all(col in df.columns for col in required_cols):
                # 确保参数值是数值类型
                #outlier_ratio = len(df[col].isna())/len(df[col])
                #df['QC'] = np.where(df['QC']==1,1, outlier_ratio)
                df[col] = pd.to_numeric(df[col], errors='coerce')

                # 使用IQR方法
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR

                # 统计异常值
                outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound) |
                              (df[col] < min_val) | (df[col] > max_val)]
                outlier_summary[col] = len(outliers)

                # 处理异常值(设为NaN后插值)
                df.loc[(df[col] < lower_bound) | (df[col] > upper_bound) |
                       (df[col] < min_val) | (df[col] > max_val), col] = np.nan
                df[col] = df[col].interpolate()

        self.qc_report['outliers'] = outlier_summary
        logger.info(f"OUTLIER SUMMARY: {outlier_summary}")

        return df

    # 动态基线法

    def detect_high_segments(data, window_size=50, k=2, min_length=10):
        """DETECTING HIGH INTERVAL,DYNAMIC BASELINE METHOD"""
        # 1. 计算动态基线(中位数滤波)
        baseline = median_filter(data, size=window_size)

        # 2. 计算局部标准差
        half_window = window_size // 2
        local_std = np.zeros_like(data)
        for i in range(len(data)):
            start = max(0, i - half_window)
            end = min(len(data), i + half_window + 1)
            local_std[i] = np.std(data[start:end])

            # 3. 计算动态阈值
            threshold = baseline + k * local_std

            # 4. 标记高值点并合并为段
            high_points = data > threshold
            high_segments = []
            current_start = None
            for i in range(len(high_points)):
                if high_points[i] and current_start is None:
                    current_start = i
                elif not high_points[i] and current_start is not None:
                    if i - current_start >= min_length:
                        high_segments.append((current_start, i - 1))
                    current_start = None
            if current_start is not None and len(data) - current_start >= min_length:
                high_segments.append((current_start, len(data) - 1))

            return baseline, threshold, high_segments

            # 找总烃的高值段
            target_column = 'Total18'

            # 检查字段是否存在
            if target_column not in df.columns:
                raise ValueError(f"FIELDS {target_column}NOT FOUND in CSV FILE,PLS CHECK FIELD NAME")
            # 提取数值(排除空值)
            data = df[target_column].dropna().values  # 转换为numpy数组
            if len(data) == 0:
                raise ValueError(f"字FIELDS{target_column}HAS NOT VALID DATA,PLS CHECK DATA")

            # 2. 高值段识别参数(根据数据特点调整)
            window_size = 60  # 滑动窗口大小(基线变化慢则调大)
            k = 2.0  # 灵敏度(高值越显著,k可越大)
            min_length = 15  # 最小高值段长度(过滤短噪声)

            # 3. 执行高值段识别
            baseline, threshold, high_segments = detect_high_segments(
                data, window_size, k, min_length
            )

            # 5. 打印高值段信息(可结合原始索引对应到CSV中的行)

            # print(f"识别到的高值段({target_column})：")
            for i, (start, end) in enumerate(high_segments, 1):
                print(f"第{i}段：索引 {start} 至 {end}(长度：{end - start + 1})")
                high_itltxt = np.append(high_itltxt, ("第{i}段：索引 {start} 至 {end}(长度：{end - start + 1})"))

        # 6. 气体综合指数 (加权计算)
        df['GAS_COMPOSITE_INDEX'] = (0.4 * df['C1'] + 0.2 * df['C2'] + 0.15 * df['C3'] +
                                     0.1 * (df['IC4'] + df['NC4']) + 0.05 * (df['IC5'] + df['NC5']) +
                                     0.05 * (df['C6'] + df['C7']))

        # 7. 钻井效率指标 (如果有相关数据)
        if all(col in df.columns for col in ['ROP', 'WOB', 'RPM']):
            df['DRILLING_EFFICIENCY'] = np.where((df['WOB'] == 0) | (df['RPM'] == 0), 0,
                                                 (df['ROP'] * 100) / (df['WOB'] * df['RPM']))

        print(f"ADDING {len(df.columns) - len(available_cols1) - 2} FIELDS")
        return df

    def _smooth_data(self, df):
        """SNOOTHING DATA"""
        logger.info("SMOOTHING ...")

        smooth_cols = ['Total15', 'C1', 'C2', 'C3', 'IC4', 'NC4']
        window = self.config['smoothing_window']

        for col in smooth_cols:
            if col in df.columns:
                df[col] = df[col].rolling(window=window, center=True, min_periods=1).mean()

        return df

    def _standardize_format(self, df):
        """DATA FORMAT STANDARDARIZE"""
        logger.info("STANDARDARIZING...")

        # 确保深度递增
        df = df.sort_values('MD')

        # 删除重复深度点
        df = df.drop_duplicates(subset=['MD'], keep='first')

        # 重置索引
        df = df.reset_index(drop=True)

        return df


class TraditionalInterpretation:
    """TRADITIONAL METHOD"""

    def __init__(self):
        self.interpretation_results = []

    def _pixler_interpretation(self, df):
        """PIXLER INTERPRETATION"""
        logger.info("PIXLER INTERPRETATION...")

        interpretations = []

        for idx,row in df.iterrows():
            c1_c2 = row['C1C2']
            c1_c3 = row['C1C3']
            c2_c3 = row['C2C3']

            # PIXLER判识标准
            if c1_c2 > 10 and c1_c3 > 30 and c2_c3 > 3:
                result = "GAS"
            elif 5 < c1_c2 <= 10 and 10 < c1_c3 <= 30 and 2 < c2_c3 <= 3:
                result = "OIL"
            elif c1_c2 <= 5 and c1_c3 <= 10 and c2_c3 <= 2:
                result = "DRY"
            else:
                result = "Undefined"

            interpretations.append({
                'MD': row['MD'],
                'C1/C2': c1_c2,
                'C1/C3': c1_c3,
                'C2/C3': c2_c3,
                'INTERPRETATION': result
            })

        return pd.DataFrame(interpretations)

    def _ternary_interpretation(self, df):
        """TERNARY(C1-C2-C3)"""
        logger.info("TERNARY INTERPRETATION...")

        interpretations = []

        for idx, row in df.iterrows():

            c1_pct = row['C1pt']
            c2_pct = row['C2pt']
            c3_pct = row['C3pt']
            NC4_pct = row['NC4pt']
            lr=(c2_pct+c3_pct+NC4_pct-0.17)/0.17
            # 简单的三角图版判识逻辑lr<0,内三角形为倒三角形,解释为油层3
            # lr>0,内三角形为正三角形,C1小于60%解释为油层,60-90为气层,90以上为气层2或水层0
            if lr>0 and c1_pct > 0.85:
                result = "GAS"
            elif lr > 0 and c1_pct < 0.6:
                result = "OIL"
            elif lr > 0 and c1_pct > 0.6:
                result = "GAS"
            elif lr<0 :
                result = "OIL"
            elif c1_pct < 0.50:
                result = "DRY"
            else:
                result = "undefined"

            interpretations.append({
                'MD': row['MD'],
                'C1_pct': c1_pct,
                'C2_pct': c2_pct,
                'C3_pct': c3_pct,
                'INTERPRETATION': result
            })

        return pd.DataFrame(interpretations)

    def _ht_interpretation(self, df):
        """3H INTERPRETATION(BH,WH,CH)"""
        logger.info("3H INTERPRETATION...") 

        interpretations = []
        result = []
        for idx, row in df.iterrows():
            WH_pct = row['WH']
            BH_pct = row['BH']
            CH_pct = row['CH']

            # 判识逻辑0.5＜WH＜17.5,BH＞WH,为可采气2
            # 0.5＜WH＜17.5,BH＜WH,CH＜0.5,为可采湿气或凝析气2.4
            # 0.5＜WH＜17.5,BH＜WH,CH＞0.5,为可采高气油比的油
            if 0.5 < WH_pct and WH_pct < 17.5 and BH_pct > WH_pct:
                result = "GAS"
            elif 0.5 < WH_pct and WH_pct <17.5 and BH_pct > WH_pct and CH_pct <0.5:
                result = "CONDENSATE"
            elif 0.5< WH_pct and WH_pct <17.5 and BH_pct < WH_pct and CH_pct>0.5:
                result = "OIL"
            else:
                result = "undefined"

            interpretations.append({
                'MD': row['MD'],
                'WH_pct': WH_pct,
                'BH_pct': BH_pct,
                'CH_pct': CH_pct,
                'INTERPRETATION': result
            })

        return pd.DataFrame(interpretations)

    def _star_interpretation(self, df):
        """STAR INTERPRETATION(7PARAMETERS)"""
        logger.info("STAR INTERPRETATION...")   

        interpretations = []
        similarity_threshold = 0.35
        """STAR INTERPRETATION SINGLE CORE POINTS"""
        core_params = ['C1Ct', 'C2Ppt', 'TMUL', 'C1C2', 'C2C3', 'C7sMCH', 'C4Ct']
        default_templates = {
            'GAS': [0.95, 0.04, 3.2, 12, 2.5, 4, 0.15], # 气层
            'OIL': [0.70, 0.16, 1, 4.85, 2.5, 2, 0], # 油层
            'WATER': [0.2, 0.1, 1, 3.2, 2, 3, 0], # 水层
            'DRY': [0.60, 0.19, 1.1, 3.3, 1.7, 8.5, 0.06] # 干层
        }
        #total_rows = len(df)
        #print(f"开始逐行解释{total_rows}个深度点...")
        templates = default_templates
        # ======================  模板标准化(仅执行一次,提升效率) ======================
        scaler = MinMaxScaler(feature_range=(0, 1))
        template_df = pd.DataFrame(templates).T
        template_df.columns = core_params
        scaled_templates = scaler.fit_transform(template_df)
        scaled_templates = pd.DataFrame(scaled_templates, index=template_df.index, columns=core_params)

        result = []
        for idx, row in df.iterrows():
            row1 = df.iloc[idx]
            
            #标准化目标深度点核心参数
            scaled_target = scaler.transform([row1[core_params].values])[0]

            similarity = {}
            for fluid_type, template in scaled_templates.iterrows():
                score = cosine_similarity([template.values], [scaled_target])[0][0]
                similarity[fluid_type] = round(score, 3)

                valid_types = {k: v for k, v in similarity.items() if v >= similarity_threshold}
                if valid_types:
                    result = max(valid_types.items(), key=lambda x: x[1])[0]
                    max_sim = max(valid_types.values())
                else:
                    result = "Undefined"
                    max_sim = max(similarity.values())  # 取所有相似度的最大值(即使低于阈值)


            interpretations.append({
                    'MD': row['MD'],
                    'MAX_SIM': max_sim,
                    'GAS_sim': similarity['GAS'],
                    'OIL_sim': similarity['OIL'],
                    'WATER_sim': similarity['WATER'],
                    'DRY_sim': similarity['DRY'],
                    'INTERPRETATION': result
            })

        return pd.DataFrame(interpretations)

    def run_interpretation(self, df):
        """TRADITIONAL INTERPRETATION"""
        logger.info("TRADITIONAL INTERPRETATION...")

        # PIXLER解释
        pixler_results = self._pixler_interpretation(df)

        # 三角图版解释
        ternary_results = self._ternary_interpretation(df)
        if ternary_results is not None:
           output_dir = Path('./output')          # 确保 output_dir 已定义
           output_dir.mkdir(parents=True, exist_ok=True)
           ternary_results.to_csv(output_dir / 'ternary_interpretation.csv', index=False)
         # 3H解释
        ht_results = self._ht_interpretation(df)
        if ht_results is not None:
           output_dir = Path('./output')          # 确保 output_dir 已定义
           output_dir.mkdir(parents=True, exist_ok=True)
           ht_results.to_csv(output_dir / 'ht_interpretation.csv', index=False)
        # 星形图解释
        star_results = self._star_interpretation(df)
        if star_results is not None:
           output_dir = Path('./output')          # 确保 output_dir 已定义
           output_dir.mkdir(parents=True, exist_ok=True)
           star_results.to_csv(output_dir / 'star_interpretation.csv', index=False)
        # 综合解释结果
        combined_results = self._combine_interpretations(pixler_results, ternary_results, ht_results, star_results)
        if combined_results is not None:
           output_dir = Path('./output')          # 确保 output_dir 已定义
           output_dir.mkdir(parents=True, exist_ok=True)
           combined_results.to_csv(output_dir / 'combined_interpretation.csv', index=False)

        return combined_results

    def _combine_interpretations(self, pixler, ternary, ht, star):
        """COMPOSITE INTERPRETATION"""
        logger.info("INTEGRATING...")

        # 合并结果
        combined1 = pd.merge(pixler[['MD', 'INTERPRETATION']],ternary[['MD', 'INTERPRETATION']], on='MD', how='outer', suffixes=('_pixler', '_ternary'))
        combined2 = pd.merge(combined1, ht[['MD', 'INTERPRETATION']], on='MD', how='outer', suffixes=('', '_ht'))
        combined = pd.merge(combined2, star[['MD', 'INTERPRETATION']], on='MD', how='outer', suffixes=('', '_star'))
        #combined = pd.merge(pixler[['MD', 'INTERPRETATION']],ternary[['MD', 'INTERPRETATION']],on='MD', how='outer', suffixes=('_pixler', '_ternary')).merge(ht[['MD', 'INTERPRETATION']], on='MD', how='outer', suffixes=('', '_ht')).merge(star[['MD', 'INTERPRETATION']], on='MD', how='outer', suffixes=('', '_star'))
        final_interp = []
        keyword = 'INTERPRETATION'
        #print(f"开始合并{combined.shape[0]}个深度点的解释结果...")
        for idx, row in combined.iterrows():
            p1 = row['INTERPRETATION_pixler']
            t1 = row['INTERPRETATION_ternary']
            h1 = row['INTERPRETATION']
            s1 = row['INTERPRETATION_star']
            votes = [p1, t1,h1,s1]
            # 取众数；若平票则按优先级 GAS>OIL>CONDENSATE>DRY>Undefined
            try:
                final = max(set(votes), key=lambda x: (votes.count(x), {'GAS': 5, 'OIL': 4, 'CONDENSATE': 3, 'DRY': 2, 'Undefined': 1}.get(x, 1)))
            except ValueError:
                final = 'Undefined'
            final_interp.append(final)

        combined['FINAL_INTERPRETATION'] = final_interp
        return combined
   
class MLInterpretation:
    """ML INTERPRETATION"""

    def __init__(self, model_type='random_forest'):
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.feature_importance = None
        self.training_history = {}
        self.target_col_name = 'INTERPRETATION'

    def feature_engineering(self, df):
        """FEATURE ENGINEERING"""
        logger.info("FEATURE ENGINEERING...")
        # 滑动窗口大小(m),根据目标层厚度调整
        WIN_SIZES = [3, 5, 7, 10]  
        
        # 基础组分
        # 定义用于机器解释的7个核心参数
        COMPONENTS = ['C4Ct','TMUL','C1C2', 'Total18','C1Ct','C2Ct']

        # 纹层特征开关
        FEATURE_CONFIG = {
                'basic_ratio': True,      # 基础比值
                'rolling_stats': True,    # 滑动统计
                'trend': True,            # 趋势特征
                'texture': True,          # 纹理/波动特征
                'peak_shape': True,       # 形态特征
                'composite': True,        # 综合指数
        }

        features = [ 'TMUL', 'C1C2', 'C1C3', 'C1C4', 'C1C5', 'C1Ct', 'C2Ct']
        if 'ROP' in df.columns:
            features.append('ROP')

        df_feat = df[features].copy()
        win_features = {}
        """SLIDING WINDOW STATISTICS"""
        for win_m in WIN_SIZES:
            half = int(win_m / np.median(np.diff(df.MD)) / 2)
            for col in COMPONENTS:
                slopes = []
                # 均值、标准差、变异系数
                df[f'{col}_mean_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).mean()
                df[f'{col}_std_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).std()
                df[f'{col}_cv_{win_m}m']   = df[f'{col}_std_{win_m}m'] / (df[f'{col}_mean_{win_m}m'] + 1e-9)
                # 一阶差分(变化率)
                df[f'{col}_diff_{win_m}m'] = df[col].diff().abs().rolling(2*half+1, center=True, min_periods=1).mean()
                # 二阶差分(加速度)
                df[f'{col}_accel_{win_m}m'] = df[col].diff().diff().abs().rolling(2*half+1, center=True, min_periods=1).mean()
        
                # 中位数、极差
                df[f'{col}_median_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).median()
                df[f'{col}_range_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).max() - \
                                       df[col].rolling(2*half+1, center=True, min_periods=1).min()
                # 线性回归斜率
                for i in range(len(df)):
                    start = max(0, i-half)
                    end   = min(len(df), i+half+1)
                    y = df[col].iloc[start:end].values
                    x = np.arange(len(y))
                    if len(y) > 2:
                       from scipy import stats
                       slope, _, _, _, _ = stats.linregress(x, y)
                    else:
                         slope = 0
                    slopes.append(slope)
                df[f'{col}_slope_{win_m}m'] = np.array(slopes)
                #    """纹层结构：粗糙度、自相关系数、峰度、偏度"""
                # 粗糙度(一阶差分绝对和)
                df[f'{col}_roughness_{win_m}m'] = df[col].diff().abs().rolling(2*half+1, center=True, min_periods=1).sum()
                # 自相关系数(滞后1)
                autocorr = []
                for i in range(len(df)):
                    start = max(0, i-half)
                    end   = min(len(df), i+half+1)
                    sub = df[col].iloc[start:end]
                    if len(sub) > 2:
                       acf = sub.autocorr(lag=1)
                    else:
                         acf = np.nan
                autocorr.append(acf)
                #df[f'{col}_acf_{win_m}m'] = np.array(autocorr)
                # 峰度(Kurtosis)、偏度(Skewness)
                df[f'{col}_kurtosis_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).kurt()
                df[f'{col}_skewness_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).skew()
                # 滑动统计
                if FEATURE_CONFIG['rolling_stats']:
                   win_features[f'{col}_mean_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).mean()
                   win_features[f'{col}_std_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).std()
                   win_features[f'{col}_cv_{win_m}m']   = win_features[f'{col}_std_{win_m}m'] / (win_features[f'{col}_mean_{win_m}m'] + 1e-9)
                   win_features[f'{col}_median_{win_m}m'] = df[col].rolling(2*half+1, center=True, min_periods=1).median()
                   win_features[f'{col}_range_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).max() - \
                                                     df[col].rolling(2*half+1, center=True, min_periods=1).min()
                # 趋势特征
                if FEATURE_CONFIG['trend']:
                    win_features[f'{col}_diff_{win_m}m']  = df[col].diff().abs().rolling(2*half+1, center=True, min_periods=1).mean()
                    win_features[f'{col}_accel_{win_m}m'] = df[col].diff().diff().abs().rolling(2*half+1, center=True, min_periods=1).mean()
                # 纹理特征
                if FEATURE_CONFIG['texture']:
                   win_features[f'{col}_roughness_{win_m}m'] = df[col].diff().abs().rolling(2*half+1, center=True, min_periods=1).sum()
                   win_features[f'{col}_kurtosis_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).kurt()
                   win_features[f'{col}_skewness_{win_m}m']  = df[col].rolling(2*half+1, center=True, min_periods=1).skew()
            #"""峰宽、峰高、对称性、尖锐度"""
        from scipy.signal import find_peaks
        for win_m in WIN_SIZES:
            MD_step = np.median(np.diff(df.MD))
            half = int(win_m / MD_step / 2)
            for col in COMPONENTS:
                peaks, properties = find_peaks(df[col], distance=half, prominence=0.1)
        
                # 初始化
                df[f'{col}_peak_width_{win_m}m'] = 0
                df[f'{col}_peak_height_{win_m}m'] = 0
                df[f'{col}_peak_symmetry_{win_m}m'] = 0
        
                if len(peaks) > 0:
                   for pk in peaks:
                       # 峰宽(深度域)
                       left = properties['left_bases'][np.where(peaks==pk)[0][0]]
                       right = properties['right_bases'][np.where(peaks==pk)[0][0]]
                       width = (right - left) * MD_step
                       df.loc[pk, f'{col}_peak_width_{win_m}m'] = width
                
                       # 峰高(峰值-基线)
                       height = properties['prominences'][np.where(peaks==pk)[0][0]]
                       df.loc[pk, f'{col}_peak_height_{win_m}m'] = height
                
                       # 对称性：左右宽度比
                       left_width = (pk - left) * MD_step
                       right_width = (right - pk) * MD_step
                       symmetry = min(left_width, right_width) / (max(left_width, right_width) + 1e-9)
                       df.loc[pk, f'{col}_peak_symmetry_{win_m}m'] = symmetry
        
            
                    
        
        # 4. 一次性拼接所有特征
        feature_dfs = []
        if feature_dfs:
           df = pd.concat([df] + feature_dfs, axis=1)
    
        # 清理无穷值
        df = df.replace([np.inf, -np.inf], np.nan)
        if hasattr(self, 'output_dir') and self.output_dir:
           df.to_csv(self.output_dir /'featuresoutput.csv', index=False, encoding='utf-8-sig')
        exclude_cols = ['INTERPRETATION', '解释结果', '结论', 'RESULT', 'CLASS', 'test_result', 'PSEUDO_LABEL']
        # 只保留数值型特征和计算得到的特征
        feature_cols = [col for col in df.columns if col not in exclude_cols and col != 'MD']
        # 确保至少有一个特征列
        if not feature_cols:
           feature_cols = [col for col in df.columns if col != 'MD']
    
        return df[feature_cols]

    def prepare_training_data(self, df, target_col=None):
        """
        TRAINING DATA PREPARATION

        确保 LabelEncoder 接收到的数据 100% 是字符串类型,
        完全避免 'str' 和 'int' 混合导致的排序错误。
        """
        logger.info("TRAINING DATA PREPARING...")

        actual_target_col = target_col or self.target_col_name

        if actual_target_col not in df.columns:
            raise KeyError(f"TARGET COLUMNS NOT EXIT '{actual_target_col}' AVAILABLE COLUMNS: {list(df.columns)}")

        # 特征工程
        X = self.feature_engineering(df)

        # 获取原始目标列
        y_raw = df[actual_target_col]

        # ==================== 终极类型清理流程 ====================
        logger.info(f"STARTING COLUMNS CLEANING'{actual_target_col}'...")

        # 步骤1：填充缺失值
        y_filled = y_raw.fillna('UNDEFINED')

        # 步骤2：逐元素转换为字符串(最彻底的方式)
        # 使用列表推导式确保每个元素都被独立处理
        y_str_list = []
        for i, val in enumerate(y_filled):
            try:
                # 对于每个值,强制转换为字符串并清理
                str_val = str(val).strip()
                if str_val == '':
                    str_val = 'UNDEFINED'
                y_str_list.append(str_val)
            except Exception as e:
                logger.warning(f" {i}  '{val}' TRANSFORM FAILURE ({e}),replace with 'UNDEFINED' ")
                y_str_list.append('UNDEFINED')

        # 转换回 Series 以保持索引
        y_str = pd.Series(y_str_list, index=y_filled.index)

        # 步骤3：清理特殊字符和空白
        y_clean = y_str.str.replace(r'\s+', '', regex=True)  # 移除所有空白

        # 步骤4：标准化问题值
        problem_values = ['', 'nan', 'None', 'NULL', 'NoneType', 'NaN']
        y_standardized = y_clean.replace(problem_values, 'UNDEFINED')

        # 步骤5：最终验证 - 确保全部是字符串
        # 再次遍历检查(双重保险)
        final_values = []
        for val in y_standardized:
            if not isinstance(val, str):
                logger.warning(f"non-string values FOUND: {val} (TYPE: {type(val)})")
                final_values.append(str(val))
            else:
                final_values.append(val)

        y = pd.Series(final_values, index=y_standardized.index)

        # ==================== 类型验证 ====================
        # 验证所有值都是字符串
        unique_types = set(type(x).__name__ for x in y.unique())
        if len(unique_types) == 1 and 'str' in unique_types:
            logger.info(f"✅ TARGET CHECKING PASSED,ALL VALUES ARE STRING")
        else:
            logger.error(f"❌ MIXED TYPES FOUND: {unique_types}")
            # 最后的安全措施：强制全部转为字符串
            y = y.astype(str)

        logger.info(f"TARGET COLUMNS CLEANING COMPLETED - UNIQUE VALUES COUNT: {y.nunique()}")
        logger.info(f"TARGET COLUMNS CATEGORIES: {sorted(y.unique())[:20]}")

        # 现在可以安全地使用 LabelEncoder
        try:
            y_encoded = self.label_encoder.fit_transform(y)
            logger.info(
                f"✅ LABEL ENCODER SUCCESS,CLASS MAPPING: {dict(zip(self.label_encoder.classes_, range(len(self.label_encoder.classes_))))}")
        except Exception as e:
            logger.error(f"❌ LABEL ENCODER FAILURE: {e}")
            logger.error(f"TARGET COLUMNS dtype: {y.dtype}")
            logger.error(f"FIRST 10 VALUES: {y.head(10).tolist()}")
            logger.error(f"UNIQUE VALUES: {y.unique()[:10]}")
            raise

        return X, y_encoded

    def train_model(self, X, y, test_size=0.2, random_state=42):
        """MODEL TRAINING"""
        logger.info(f"TRAINING{self.model_type}MODEL...")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        X_train = X_train.apply(pd.to_numeric, errors='coerce')
        X_train = X_train.fillna(0)  # 填充NaN为0(或均值/中位数)
        X_test = X_test.apply(pd.to_numeric, errors='coerce')
        X_test = X_test.fillna(0)  # 填充NaN为0(或均值/中位数)
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        if self.model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=200, max_depth=10, random_state=random_state
            )
        elif self.model_type == 'gradient_boosting':
            self.model = GradientBoostingClassifier(
                n_estimators=200, max_depth=8, random_state=random_state
            )
        elif self.model_type == 'neural_network':
            self.model = MLPClassifier(
                hidden_layer_sizes=(100, 50), max_iter=500, random_state=random_state
            )
        else:
            raise ValueError(f"UNSUPPORTED MODEL TYPE: {self.model_type}")

        self.model.fit(X_train_scaled, y_train)

        y_pred = self.model.predict(X_test_scaled)
        y_pred_train = self.model.predict(X_train_scaled)

        train_acc = float(accuracy_score(y_train, y_pred_train))
        test_acc = float(accuracy_score(y_test, y_pred))

        logger.info(f"TRAINING ACCURACY: {train_acc:.3f}")
        logger.info(f"TEST ACCURACY: {test_acc:.3f}")

        self.training_history = {
            'train_accuracy': train_acc,
            'test_accuracy': test_acc,
            'classification_report': classification_report(y_test, y_pred, output_dict=True),
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist()
        }

        if hasattr(self.model, 'feature_importances_'):
            self.feature_importance = pd.DataFrame({
                'feature': X.columns,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)

        return self.training_history

    def predict(self, df):
        """PREDICTING NEW DATA"""
        logger.info("PREDICTING...")

        X = self.feature_engineering(df)
        X = X.apply(pd.to_numeric, errors='coerce')
        X = X.fillna(0)  # 填充NaN为0(或均值/中位数)
        X_scaled = self.scaler.transform(X)

        y_pred_encoded = self.model.predict(X_scaled)
        y_pred_proba = self.model.predict_proba(X_scaled)

        y_pred = self.label_encoder.inverse_transform(y_pred_encoded)

        results = df[['MD']].copy()
        results['PREDICTION'] = y_pred
        results['CONFIDENCE'] = np.max(y_pred_proba, axis=1)

        for i, class_name in enumerate(self.label_encoder.classes_):
            results[f'PROB_{class_name}'] = y_pred_proba[:, i]

        return results

    def cross_validate(self, X, y, cv=5):
        """CROSS VALIDATION"""
        logger.info(f"{cv}FIELDS CROSS VALIDATION...")

        X_scaled = self.scaler.fit_transform(X)

        scores = cross_val_score(self.model, X_scaled, y, cv=cv, scoring='accuracy')

        logger.info(f"{cv}FIELDS CROSS VALIDATION ACCURACY : {scores.mean():.3f} (+/- {scores.std() * 2:.3f})")

        return {
            'cv_scores': scores.tolist(),
            'mean_score': scores.mean(),
            'std_score': scores.std()
        }


class ValidationModule:
    """VALIDATION AND IMPROVEMENT MODULE"""

    def __init__(self):
        self.validation_results = {}
        self.improvement_suggestions = []

    def compare_with_test_results(self, ml_results, test_results, depth_tolerance=5, target_col=None):
        """
        COMPARE WITH TEST RESULTS

        Args:
            ml_results: 机器学习预测结果 (DataFrame,必须包含 MD 和 PREDICTION)
            test_results: 试油结果 (DataFrame,必须包含 MD 和解释列)
            depth_tolerance: 深度匹配容差(米)
            target_col: 试油结果中的解释列名(自动检测)
        """
        logger.info("COMPARE WITH TEST RESULTS...")

        # ==================== 关键修复：自动检测目标列 ====================
        if target_col is None:
            # 可能的列名列表
            possible_cols = ['INTERPRETATION', '解释结果', '结论', 'RESULT', 'CLASS', '试油结论','test_result']

            available_cols = list(test_results.columns)
            logger.info(f"AVAILABLE TEST RESULT COLUMNS: {available_cols}")

            # 自动匹配
            target_col = None
            for col in possible_cols:
                if col in available_cols:
                    target_col = col
                    logger.info(f"✅ AVAILABLE TEST RESULT COLUMNS: '{col}'")
                    break

            if target_col is None:
                logger.warning(f"⚠️ STARDARD INTERPRETATION COLUMNS NOT FOUND possible COLUMNS: {possible_cols}")
                logger.warning(f"⚠️ STARDARD INTERPRETATION COLUMNS NOT FOUND in TEST RESULTS,POSSIBLE COLUMNS ARE: {available_cols}")
                logger.warning("SKIPPING TEST VERIFICATION")
                self.validation_results['test_comparison'] = None
                return pd.DataFrame()  # 返回空DataFrame

        # 检查必需的 MD 列
        if 'MD' not in test_results.columns:
            logger.error("❌ MD FIELD SHOULD BE INCLUDED IN TEST RESULTS")
            logger.info(f"AVAILABLE TEST RESULT COLUMNS: {list(test_results.columns)}")
            self.validation_results['test_comparison'] = None
            return pd.DataFrame()

        logger.info(f"ML RESULTS SAMPLE: {ml_results[['MD', 'PREDICTION']].head(3).to_dict('records')}")

        logger.info(f"AVAILABLE TEST RESULT COLUMN: '{target_col}'(THE FIRST THREE VALUES: {test_results[target_col].head(3).tolist()})")

        # ==================== 标准化标签函数 ====================
        def standardize_label(label):
            """标准化解释标签，统一格式"""
            if pd.isna(label):
                return 'UNDEFINED'
            # 转换为字符串并去除空格
            label = str(label).strip().upper()
            # 标准化常见标签
            label_map = {
                'GAS': ['GAS', '气层', '天然气', '气'],
                'OIL': ['OIL', '油层', '原油', '油'],
                'WATER': ['WATER', '水层', '水'],
                'DRY': ['DRY', '干层', '干'],
                'CONDENSATE': ['CONDENSATE', '凝析气', '凝析油']
            }
            # 查找匹配的标准标签
            for std_label, variations in label_map.items():
                if label in variations:
                    return std_label
            return label

        # ==================== 执行匹配 ====================
        matches = []
        logger.info(f"TOTAL TEST POINTS: {len(test_results)}, ML RESULTS: {len(ml_results)}")
        
        for idx, row in test_results.iterrows():
            try:
                test_depth = float(row['MD'])
                test_interp = row[target_col]

                # 标准化试油结果标签
                test_interp_std = standardize_label(test_interp)

                # 找到最近的预测点
                if len(ml_results) == 0:
                    continue

                # 计算深度差并找到最近的点
                depth_diff = (ml_results['MD'] - test_depth).abs()
                closest_idx = depth_diff.idxmin()
                closest_depth = ml_results.loc[closest_idx, 'MD']
                depth_diff_value = depth_diff[closest_idx]

                logger.debug(f"TEST POINT {test_depth}m: CLOSEST ML POINT {closest_depth}m, DIFF {depth_diff_value}m")

                if depth_diff_value <= depth_tolerance:
                    ml_interp = ml_results.loc[closest_idx, 'PREDICTION']
                    confidence = ml_results.loc[closest_idx, 'CONFIDENCE']
                    
                    # 标准化机器学习预测标签
                    ml_interp_std = standardize_label(ml_interp)

                    # 判断是否匹配
                    is_match = bool(test_interp_std == ml_interp_std)
                    
                    matches.append({
                        'TEST_DEPTH': float(test_depth),
                        'ML_DEPTH': float(closest_depth),
                        'TEST_INTERP_RAW': str(test_interp),
                        'ML_INTERP_RAW': str(ml_interp),
                        'TEST_INTERP_STD': test_interp_std,
                        'ML_INTERP_STD': ml_interp_std,
                        'DEPTH_DIFF': float(depth_diff_value),
                        'CONFIDENCE': float(confidence),
                        'MATCH': is_match
                    })
                    logger.debug(f"MATCH RESULT: TEST={test_interp_std}, ML={ml_interp_std}, MATCH={is_match}")
            except Exception as e:
                logger.warning(f"处理试油结果第 {idx} 行时出错: {e}")
                # 打印详细错误信息，便于调试
                logger.warning(f"ERROR ROW: {row.to_dict()}")
                continue

        matches_df = pd.DataFrame(matches)
        logger.info(f"TOTAL MATCHES FOUND: {len(matches_df)}")

        if len(matches_df) > 0:
            accuracy = float(matches_df['MATCH'].mean())
            logger.info(f"✅ TEST MATCHING ACCURACY: {accuracy:.3f}")
            # 记录详细匹配结果统计
            logger.info(f"DETAILED MATCHING RESULTS: {matches_df[['TEST_INTERP_STD', 'ML_INTERP_STD', 'MATCH']].value_counts().to_dict()}")

            self.validation_results['test_comparison'] = {
                'accuracy': accuracy,
                'total_matches': int(len(matches_df)),
                'correct_matches': int(matches_df['MATCH'].sum()),
                'details': matches_df.to_dict('records')
            }
        else:
            logger.warning(" NO MATCHING TEST RESULTS FOUND")
            self.validation_results['test_comparison'] = None

        return matches_df

    def analyze_misclassifications(self, ml_results, true_labels):
        """MISCLASSIFICATION ANALYSIS"""
        logger.info("MISCLASSIFICATION ANALYZING...")

        # 合并数据
        merged = pd.merge(ml_results, true_labels, on='MD', how='inner')

        # 找出误分类
        misclassified = merged[merged['PREDICTION'] != merged['TRUE_LABEL']]

        if len(misclassified) > 0:
            logger.info(f"MISCLASSIFICATION POINTS: {len(misclassified)}")

            # 统计误分类类型
            error_types = misclassified.groupby(['PREDICTION', 'TRUE_LABEL']).size().reset_index(name='count')

            self.validation_results['misclassification_analysis'] = {
                'total_errors': int(len(misclassified)),
                'error_rate': float(len(misclassified) / len(merged)),
                'error_types': error_types.to_dict('records')
            }

            return misclassified, error_types
        else:
            logger.info("NO MISCLASSIFICATIONS")
            return None, None

    def generate_improvement_suggestions(self, training_history, validation_results):
        """IMPROVEMENT SUGGESTIONS"""
        logger.info("SUGGESTIONS GENERATING...")

        suggestions = []

        # 基于训练历史
        if training_history['train_accuracy'] - training_history['test_accuracy'] > 0.1:
            suggestions.append("模型存在过拟合,建议增加正则化或减少模型复杂度IMPROVEMENT SUGGESTION: OVERFIT MODEL, REGULARIZATION OR USE SIMPLIFY MODEL")

        if training_history['test_accuracy'] < 0.8:
            suggestions.append("模型准确率较低,建议增加更多特征或调整模型参数IMPROVEMENT SUGGESTION: MODEL ACCURY LOW,ADD MORE FEATURES OR TUNE MODEL PARAMETERS")  

        # 基于验证结果
        if validation_results.get('test_comparison'):
            if validation_results['test_comparison']['accuracy'] < 0.7:
                suggestions.append("与试油结果匹配度低,建议检查训练数据质量或增加试油样本IMPROVEMENT SUGGESTION: TEST MATCHING LOW, CHECK TRAINING DATA QUALITY OR INCREASE TEST SAMPLES")

        # 通用建议
        suggestions.extend([
            "尝试集成学习方法(如模型融合)IMPROVEMENT SUGGESTION: MODEL FUSION",
            "进行超参数调优(使用GridSearchCV或Bayesian优化)IMPROVEMENT SUGGESTION: HYPERPARAMETER TUNING",
            "收集更多标记样本,特别是边界情况IMPROVEMENT SUGGESTION: COLLECT MORE LABELED SAMPLES",
            "引入更多地质工程参数作为特征IMPROVEMENT SUGGESTION: INCLUDE MORE ENGINEERING FEATURES",
            "定期用新数据重新训练模型IMPROVEMENT SUGGESTION: RE-TRAIN WITH NEW DATA"    
        ])

        self.improvement_suggestions = suggestions
        return suggestions

    def run_continuous_evaluation(self, ml_model, data_stream, interval=100):
        """
        (模拟在线学习)continuous evaluation MODEL PERDFORMANCE (simulating machine learning online)
        ml_model: 训练好的模型trained model
        data_stream: 数据流生成器data stream generator
        interval: 评估间隔evaluation interval   
        """
        logger.info("STARING CONTINUOUS EVALUATION...")

        performance_log = []

        for i, batch_data in enumerate(data_stream):
            if i % interval == 0:
                # 评估当前模型
                predictions = ml_model.predict(batch_data)
                # 这里假设batch_data包含真实标签
                if 'TRUE_LABEL' in batch_data.columns:
                    accuracy = (predictions['PREDICTION'] == batch_data['TRUE_LABEL']).mean()
                    performance_log.append({
                        'batch': i,
                        'accuracy': accuracy,
                        'timestamp': datetime.now()
                    })

        self.validation_results['continuous_evaluation'] = performance_log
        return performance_log


class VisualizationModule:
    """可视化模块VISUALIZATION MODULE"""

    def __init__(self, output_dir='./output'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def plot_gas_curves(self, df, highlight_intervals=None, save_path=None):
        """GAS CURVES PLOT"""
        #fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 解决中文显示
        plt.rcParams['axes.unicode_minus'] = False    # 解决负号显示
        plt.rcParams['figure.dpi'] = 100              # 图表分辨率
        plt.rcParams['figure.figsize'] = (12, 10)      # 图表大小(宽,高)
        required_cols = ["MD","C1","C2","C3","IC4","NC4","IC5","NC5","C6","C7","C8","BZ","TL","MCH","ROP"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"COLUMNS MISSING IN EXCEL FILE: {col},PLS CHECK COLUMN NAMES")
            elif df[col].isna().any():
                 raise ValueError(f"COLUMNS MISSING IN EXCEL FILE: {col},PLS CHECK DATA INTEGRITY")
                 #检查数据类型是否为数值型
            if not pd.api.types.is_numeric_dtype(df[col]):
                # 尝试转换为数值型
                df[col] = pd.to_numeric(df[col], errors='coerce')
                #raise ValueError(f"Excel中{col}列数据类型不是数值型,请检查数据是否正确")
                # 去除空值行(避免绘图报错)
            df = df.dropna(subset=required_cols)

            # -------------------------- 3. 创建多分道图表(共享Y轴) --------------------------
            # 创建子图：nrows=1(一行),ncols=15(15列),共享Y轴
        fig, (ax1, ax2,ax3,ax4,ax5,ax6,ax7,ax8,ax9,ax10,ax11,ax12,ax13,ax14,ax15) = plt.subplots(nrows=1, ncols=15, sharey=True)
            # -------------------------- 4. 绘制第一个道：气测曲线 --------------------------
            # 绘制气测折线(深度为Y轴,气测为X轴)
        ax1.set_xscale('log')  # 设置x为对数刻度
        ax1.set_xlim(10, 1000000)
        # 设置气测轴标签
        ax1.set_xlabel("C1", fontsize=10, fontweight="bold")
        ax1.set_ylabel("MD (m)", fontsize=10, fontweight="bold")  # Y轴标签仅在第一个子图显示
        ax1.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax1.plot(df['C1'], df['MD'], 'r-', label='C1', linewidth=1)  # 红色实线
        ax1.legend(loc="upper right", fontsize=8)
        #2nd trackC2
        ax2.set_xscale('log')  # 设置x为对数刻度
        ax2.set_xlim(10, 1000000)
        ax2.set_xlabel("C2", fontsize=10, fontweight="bold")
        ax2.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax2.plot(df['C2'], df['MD'], 'g-', label='C2', linewidth=1)  # 绿色实线
        ax2.legend(loc="upper right", fontsize=8)
        #3rd trackC3
        ax3.set_xscale('log')  # 设置x为对数刻度
        ax3.set_xlim(10, 1000000)
        ax3.set_xlabel("C3", fontsize=10, fontweight="bold")
        ax3.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax3.plot(df['C3'], df['MD'],  'b-', label='C3', linewidth=1)  # 兰色实线
        ax3.legend(loc="upper right", fontsize=8)
        #4th trackIC4
        ax4.set_xscale('log')  # 设置x为对数刻度
        ax4.set_xlim(10, 1000000)
        ax4.set_xlabel("IC4", fontsize=10, fontweight="bold")
        ax4.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax4.plot(df['IC4'],df['MD'],  'y--', label='IC4', linewidth=1)#黄色虚线
        ax4.legend(loc="upper right", fontsize=8)
        #5th trackNC4
        ax5.set_xscale('log')  # 设置x为对数刻度
        ax5.set_xlim(10, 1000000)
        ax5.set_xlabel("NC4", fontsize=10, fontweight="bold")
        ax5.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax5.plot(df['NC4'],df['MD'],  'y--', label='NC4', linewidth=1)#青cyan色虚线
        ax5.legend(loc="upper right", fontsize=8)
        #6th trackIC5
        ax6.set_xscale('log')  # 设置x为对数刻度
        ax6.set_xlim(10, 1000000)
        ax6.set_xlabel("IC5", fontsize=10, fontweight="bold")
        ax6.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax6.plot(df['IC5'],df['MD'],  'm--', label='IC5', linewidth=1)  # 品红色magenta色虚线
        ax6.legend(loc="upper right", fontsize=8)
        #7th trackNC5
        ax7.set_xscale('log')  # 设置x为对数刻度
        ax7.set_xlim(10, 1000000)
        ax7.set_xlabel("NC5", fontsize=10, fontweight="bold")
        ax7.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax7.plot(df['NC5'],df['MD'],  'm--', label='NC5', linewidth=1)  # 品红色magenta色虚线
        ax7.legend(loc="upper right", fontsize=8)
        #8th trackC6
        ax8.set_xscale('log')  # 设置x为对数刻度
        ax8.set_xlim(10, 1000000)
        ax8.set_xlabel("C6", fontsize=10, fontweight="bold")
        ax8.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax8.plot(df['C6'],df['MD'],  'c--', label='C6', linewidth=1)  # 品红色magenta色虚线
        ax8.legend(loc="upper right", fontsize=8)
        #9th trackC7
        ax9.set_xscale('log')  # 设置x为对数刻度
        ax9.set_xlim(10, 1000000)
        ax9.set_xlabel("C7", fontsize=10, fontweight="bold")
        ax9.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax9.plot(df['C7'],df['MD'],  'm--', label='C7', linewidth=1)  # 品红色magenta色虚线
        ax9.legend(loc="upper right", fontsize=8)
        #10th trackC8
        ax10.set_xscale('log')  # 设置x为对数刻度
        ax10.set_xlim(10, 1000000)
        ax10.set_xlabel("C8", fontsize=10, fontweight="bold")
        ax10.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        # 确保 ax10 已定义(若前面未创建则补建)
        ax10.set_xscale('log')  # 设置x为对数刻度
        ax10.set_xlim(10, 1000000)
        ax10.set_xlabel("C8", fontsize=10, fontweight="bold")
        ax10.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax10.plot(df['C8'],df['MD'],  'm-', label='C8', linewidth=1)  # 品红色magenta色虚线
        ax10.legend(loc="upper right", fontsize=8)
        #11th trackBZ
        ax11.set_xscale('log')  # 设置x为对数刻度
        ax11.set_xlim(10, 1000000)
        ax11.set_xlabel("BZ", fontsize=10, fontweight="bold")
        ax11.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax11.plot(df['BZ'],df['MD'],  'm--', label='BZ', linewidth=1)  # 品红色magenta色虚线
        ax11.legend(loc="upper right", fontsize=8)
        #12th trackTL
        ax12.set_xscale('log')  # 设置x为对数刻度
        ax12.set_xlim(10, 1000000)
        ax12.set_xlabel("TL", fontsize=10, fontweight="bold")
        ax12.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax12.plot(df['TL'],df['MD'],  'm--', label='TL', linewidth=1)  # 品红色magenta色虚线
        ax12.legend(loc="upper right", fontsize=8)
        #13th trackMCH
        ax13.set_xscale('log')  # 设置x为对数刻度
        ax13.set_xlim(10, 1000000)
        ax13.set_xlabel("MCH", fontsize=10, fontweight="bold")
        ax13.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax13.plot(df['MCH'],df['MD'],  'm--', label='MCH', linewidth=1)  # 品红色magenta色虚线
        ax13.legend(loc="upper right", fontsize=8)
        # 自定义气测X轴刻度(可根据数据范围调整)
        #gas_min, gas_max = df[gas_col].min(), df[gas_col].max()
        #ax1.set_xlim(gas_min - 0.1*(gas_max-gas_min), gas_max + 0.1*(gas_max-gas_min))  # 刻度范围

        # -------------------------- 5. 绘制第14个道：钻时曲线 --------------------------
        # 绘制钻时折线(深度为Y轴,钻时为X轴)
        ax14.plot(df['ROP'], df['MD'], color="#2E86AB", linewidth=1.5, label="ROP")
        # 设置钻时轴标签
        ax14.set_xlabel("ROP (min/m)", fontsize=10, fontweight="bold")
        # 自定义钻时X轴刻度(独立刻度,与气测无关)
        drilling_min, drilling_max = df['ROP'].min(), df['ROP'].max()
        ax14.set_xlim(drilling_min - 0.1*(drilling_max-drilling_min), drilling_max + 0.1*(drilling_max-drilling_min))
        ax14.xaxis.set_major_locator(plt.MaxNLocator(3))
        # 网格线
        ax14.grid(True, alpha=0.3, linestyle="--")
        # 图例
        ax14.legend(loc="upper right", fontsize=8)
        #15thtrack QC
        #设置为颜色道,0为绿色,1为红色,中间根据数字大小颜色渐变
        ##ax15.set_xscale('log')  # 设置x为对数刻度
        ax15.set_xlim(0, 1)
        ax15.set_xlabel("QC", fontsize=10, fontweight="bold")
        ax15.xaxis.set_major_locator(plt.MaxNLocator(3))  # 刻度数量
        ax15.plot(df['QC'],df['MD'],  'r-', label='QC', linewidth=2)  # 品红色magenta色虚线
        ax15.legend(loc="upper right", fontsize=8)
        # 自定义颜色道刻度(0-100)
        #ax15.set_xticks([0, 0.25, 0.50, 0.75, 1.00])
        #ax15.set_xticklabels(['0', '0.25', '0.50', '0.75', '1.00'])

        # -------------------------- 6. 全局优化 --------------------------
        # 全局优化：调整子图间距,使X轴标签不遮挡
        plt.subplots_adjust(bottom=0.15)  # 底部留出空间
        # -------------------------- 8. 深度轴(Y轴)反转 --------------------------
        # 深度轴(Y轴)反转(深度越大,Y轴越向下,符合行业习惯)
        ax1.invert_yaxis()
            # 调整子图间距
        plt.subplots_adjust(wspace=0)  # 左右子图间距
        # 图表标题
        fig.suptitle("GAS CONTENT/ROP QC LOG", fontsize=12, fontweight="bold", y=0.95)
        # -------------------------- 7. 保存/显示图表 --------------------------

        if self.output_dir:
           plt.savefig(self.output_dir / f'gas_content_rop_qc_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png', dpi=300, bbox_inches='tight')

    def plot_interpretation_results(self, df, results, save_path=None):
        """PLOT INTERPRETATION RESULTS COMPARISON"""
        
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 解决中文显示
        plt.rcParams['axes.unicode_minus'] = False    # 解决负号显示
        plt.rcParams['figure.dpi'] = 100              # 图表分辨率
        plt.rcParams['figure.figsize'] = (12, 10)      # 图表大小(宽,高)
        required_cols = ["MD","C1","C2","C3","IC4","NC4","IC5","NC5","C6","C7","C8","BZ","TL","MCH","ROP","QC","C1C2","C1C3","C1C4","WH","CH","BH","C1pt","C2pt","C3pt","NC4pt"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"COLUMNS MISSING IN EXCEL FILE: {col},请检查列名是否正确PLS CHECK COLUMN NAMES")
            elif df[col].isna().any():
                 raise ValueError(f"COLUMNS MISSING IN EXCEL FILE: {col},请检查数据是否完整PLS CHECK DATA INTEGRITY")
                 #检查数据类型是否为数值型
            if not pd.api.types.is_numeric_dtype(df[col]):
                # 尝试转换为数值型
                df[col] = pd.to_numeric(df[col], errors='coerce')
                #raise ValueError(f"Excel中{col}列数据类型不是数值型,请检查数据是否正确")
                # 去除空值行(避免绘图报错)
            df = df.dropna(subset=required_cols)

            # -------------------------- 3. 创建多分道图表(共享Y轴) --------------------------
            # 创建子图：nrows=1(一行),ncols=15(15列),共享Y轴
        fig, (ax1, ax2,ax3,ax4,ax5,ax6,ax7) = plt.subplots(nrows=1, ncols=7, sharey=True)
            # -------------------------- 绘制第一个道3H --------------------------
            # 绘制3H解释(深度为Y轴,解释为X轴)
        #ax1.set_xscale('log')  # 设置x为对数刻度
        
        # 检查必需列是否存在
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"❌ 缺少必需列，无法绘制解释结果图: {missing_cols}")
            logger.error(f"✅ 请检查数据文件，确保包含所有必需列")
            return  # 直接退出，不绘制图表
        
        for col in required_cols:
            if df[col].isna().any():
                 logger.error(f"❌ {col}列存在缺失值，无法绘制解释结果图")
                 logger.error(f"✅ 请检查数据文件，确保数据完整")
                 return  # 直接退出，不绘制图表
                 #检查数据类型是否为数值型
            if not pd.api.types.is_numeric_dtype(df[col]):
                # 尝试转换为数值型
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 去除空值行(避免绘图报错)
        df = df.dropna(subset=required_cols)

            # -------------------------- 3. 创建多分道图表(共享Y轴) --------------------------
            # 创建子图：nrows=1(一行),ncols=15(15列),共享Y轴
        fig, (ax1, ax2,ax3,ax4,ax5,ax6,ax7) = plt.subplots(nrows=1, ncols=7, sharey=True)
        
            # -------------------------- 绘制第一个道3H --------------------------
            # 绘制3H解释(深度为Y轴,解释为X轴)
        #ax1.set_xscale('log')  # 设置x为对数刻度
        ax1.set_xlim(0, 100)
        # 设置3H解释轴标签
        ax1.set_xlabel("3H", fontsize=10, fontweight="bold")
        ax1.set_ylabel("MD (m)", fontsize=10, fontweight="bold")  # Y轴标签仅在第一个子图显示
        ax1.xaxis.set_major_locator(plt.MaxNLocator(3))  # 刻度数量
        ax1.plot(df['WH'], df['MD'], 'r-', label='WH', linewidth=1)  # 红色实线
        ax1.plot(df['CH'], df['MD'], 'g-', label='CH', linewidth=1)  # 绿色实线
        ax1.plot(df['BH'], df['MD'], 'b-', label='BH', linewidth=1)  # 兰色实线
        # 绘制单一数值随深度不变的直线,标出cutoff值
        ax1.axvline(x=0.5,  color='k', linestyle='-',label='cutoff0.5', linewidth=1)  # 黑色实线
        ax1.axvline(x=17.5,  color='k', linestyle='-',label='cutoff17.5',  linewidth=1)  # 黑色实线
        ax1.axvline(x=40,  color='k', linestyle='-', label='cutoff40', linewidth=1)  # 黑色实线
        ax1.legend(loc="upper right", fontsize=8)
        #2nd trackC2皮克斯勒解释
        ax2.set_xscale('log')  # 设置x为对数刻度
        ax2.set_xlim(10, 1000000)
        ax2.set_xlabel("PIXLER", fontsize=10, fontweight="bold")
        ax2.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax2.plot(df['C1C2'], df['MD'], 'r-', label='C1C2', linewidth=1)  # 绿色实线
        ax2.plot(df['C1C3'], df['MD'], 'g-', label='C1C3', linewidth=1)  # 兰色实线
        ax2.plot(df['C1C4'], df['MD'], 'b-', label='C1C4', linewidth=1)  # 黄色实线
        ax2.axvline(x=2, color='k', linestyle='-', label='cutoff2', linewidth=1)  # 黑色实线
        ax2.axvline(x=15, color='k', linestyle='-', label='cutoff15', linewidth=1)  # 黑色实线
        ax2.axvline(x=27, color='k', linestyle='-', label='cutoff27', linewidth=1)  # 黑色实线
        ax2.axvline(x=65, color='k', linestyle='-', label='cutoff65', linewidth=1)  # 黑色实线
        ax2.legend(loc="upper right", fontsize=8)
        #3rd trackC3三角形解释
        #ax3.set_xscale('log')  # 设置x为对数刻度
        ax3.set_xlim(0, 1)
        ax3.set_xlabel("TERNARY", fontsize=10, fontweight="bold")
        ax3.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax3.plot(df['C2pt'], df['MD'],  'r-', label='C2pt', linewidth=1)  # 红色实线
        ax3.plot(df['C3pt'], df['MD'],  'g-', label='C3pt', linewidth=1)  # 兰色实线
        ax3.plot(df['NC4pt'], df['MD'],  'b-', label='NC4pt', linewidth=1)  # 黄色实线
        ax3.legend(loc="upper right", fontsize=8)

        
        #6th track INTERPRETATION
               
        #7thtrack QC
        #设置为颜色道,0为绿色,1为红色,中间根据数字大小颜色渐变
        ##ax7.set_xscale('log')  # 设置x为对数刻度
        ax7.set_xlim(0, 1)
        ax7.set_xlabel("QC", fontsize=10, fontweight="bold")
        ax7.xaxis.set_major_locator(plt.MaxNLocator(3))  # 刻度数量
        ax7.plot(df['QC'],df['MD'],  'r-', label='QC', linewidth=2)  # 品红色magenta色虚线
        ax7.legend(loc="upper right", fontsize=8)
        # 自定义颜色道刻度(0-100)
        #ax7.set_xticks([0, 0.25, 0.50, 0.75, 1.00])
        #ax15.set_xticklabels(['0', '0.25', '0.50', '0.75', '1.00'])

        # -------------------------- 6. 全局优化 --------------------------
        # 全局优化：调整子图间距,使X轴标签不遮挡
        plt.subplots_adjust(bottom=0.15)  # 底部留出空间
        # -------------------------- 8. 深度轴(Y轴)反转 --------------------------
        # 深度轴(Y轴)反转(深度越大,Y轴越向下,符合行业习惯)
        ax1.invert_yaxis()
            # 调整子图间距
        plt.subplots_adjust(wspace=0)  # 左右子图间距
        # 图表标题
        fig.suptitle("GAS INTERPRETATION LOG", fontsize=12, fontweight="bold", y=0.95)
        # -------------------------- 7. 保存/显示图表 --------------------------

        if self.output_dir:
           plt.savefig(self.output_dir / f'GAS_INTERPRETATION_LOG_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png', dpi=300, bbox_inches='tight')
        
        ax1.set_xlim(0, 100)
        # 设置3H解释轴标签
        ax1.set_xlabel("3H", fontsize=10, fontweight="bold")
        ax1.set_ylabel("MD (m)", fontsize=10, fontweight="bold")  # Y轴标签仅在第一个子图显示
        ax1.xaxis.set_major_locator(plt.MaxNLocator(3))  # 刻度数量
        ax1.plot(df['WH'], df['MD'], 'r-', label='WH', linewidth=1)  # 红色实线
        ax1.plot(df['CH'], df['MD'], 'g-', label='CH', linewidth=1)  # 绿色实线
        ax1.plot(df['BH'], df['MD'], 'b-', label='BH', linewidth=1)  # 兰色实线
        # 绘制单一数值随深度不变的直线,标出cutoff值
        ax1.axvline(x=0.5,  color='k', linestyle='-',label='cutoff0.5', linewidth=1)  # 黑色实线
        ax1.axvline(x=17.5,  color='k', linestyle='-',label='cutoff17.5',  linewidth=1)  # 黑色实线
        ax1.axvline(x=40,  color='k', linestyle='-', label='cutoff40', linewidth=1)  # 黑色实线
        ax1.legend(loc="upper right", fontsize=8)
        #2nd trackC2皮克斯勒解释
        ax2.set_xscale('log')  # 设置x为对数刻度
        ax2.set_xlim(10, 1000000)
        ax2.set_xlabel("PIXLER", fontsize=10, fontweight="bold")
        ax2.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax2.plot(df['C1C2'], df['MD'], 'r-', label='C1C2', linewidth=1)  # 绿色实线
        ax2.plot(df['C1C3'], df['MD'], 'g-', label='C1C3', linewidth=1)  # 兰色实线
        ax2.plot(df['C1C4'], df['MD'], 'b-', label='C1C4', linewidth=1)  # 黄色实线
        ax2.axvline(x=2, color='k', linestyle='-', label='cutoff2', linewidth=1)  # 黑色实线
        ax2.axvline(x=15, color='k', linestyle='-', label='cutoff15', linewidth=1)  # 黑色实线
        ax2.axvline(x=27, color='k', linestyle='-', label='cutoff27', linewidth=1)  # 黑色实线
        ax2.axvline(x=65, color='k', linestyle='-', label='cutoff65', linewidth=1)  # 黑色实线
        ax2.legend(loc="upper right", fontsize=8)
        #3rd trackC3三角形解释
        #ax3.set_xscale('log')  # 设置x为对数刻度
        ax3.set_xlim(0, 1)
        ax3.set_xlabel("TERNARY", fontsize=10, fontweight="bold")
        ax3.xaxis.set_major_locator(plt.MaxNLocator(4))  # 刻度数量
        ax3.plot(df['C2pt'], df['MD'],  'r-', label='C2pt', linewidth=1)  # 红色实线
        ax3.plot(df['C3pt'], df['MD'],  'g-', label='C3pt', linewidth=1)  # 兰色实线
        ax3.plot(df['NC4pt'], df['MD'],  'b-', label='NC4pt', linewidth=1)  # 黄色实线
        ax3.legend(loc="upper right", fontsize=8)
        
        #6th track INTERPRETATION
               
        #7thtrack QC
        #设置为颜色道,0为绿色,1为红色,中间根据数字大小颜色渐变
        ##ax7.set_xscale('log')  # 设置x为对数刻度
        ax7.set_xlim(0, 1)
        ax7.set_xlabel("QC", fontsize=10, fontweight="bold")
        ax7.xaxis.set_major_locator(plt.MaxNLocator(3))  # 刻度数量
        ax7.plot(df['QC'],df['MD'],  'r-', label='QC', linewidth=2)  # 品红色magenta色虚线
        ax7.legend(loc="upper right", fontsize=8)
        # 自定义颜色道刻度(0-100)
        #ax7.set_xticks([0, 0.25, 0.50, 0.75, 1.00])
        #ax15.set_xticklabels(['0', '0.25', '0.50', '0.75', '1.00'])

        # -------------------------- 6. 全局优化 --------------------------
        # 全局优化：调整子图间距,使X轴标签不遮挡
        plt.subplots_adjust(bottom=0.15)  # 底部留出空间
        # -------------------------- 8. 深度轴(Y轴)反转 --------------------------
        # 深度轴(Y轴)反转(深度越大,Y轴越向下,符合行业习惯)
        ax1.invert_yaxis()
            # 调整子图间距
        plt.subplots_adjust(wspace=0)  # 左右子图间距
        # 图表标题
        fig.suptitle("GAS INTERPRETATION LOG", fontsize=12, fontweight="bold", y=0.95)
        # -------------------------- 7. 保存/显示图表 --------------------------

        if self.output_dir:
           plt.savefig(self.output_dir / f'GAS_INTERPRETATION_LOG_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png', dpi=300, bbox_inches='tight')

    def generate_report(self, qc_report, interpretation_results, training_history, validation_results):
        """生成解释报告GENERATE INTERPRETATION REPORT"""
        report_file = self.output_dir / f'interpretation_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'

        html_content = f"""
        <html>
        <head>
            <title>录井气测数据解释报告INTERPRETATION REPORT</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .warning {{ color: orange; }}
                .error {{ color: red; }}
                .success {{ color: green; }}
            </style>
        </head>
        <body>
            <h1>录井气测数据解释报告INTERPRETATION REPORT</h1>
            <p>生成时间TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

            <h2>1. 数据质量检查结果DATA QUALITY CHECK RESULTS</h2>
            <pre>{json.dumps(qc_report, indent=2)}</pre>

            <h2>2. 模型训练结果MODEL TRAINING RESULTS</h2>
            <p>训练准确率: {training_history.get('train_accuracy', 'N/A')}</p>
            <p>测试准确率: {training_history.get('test_accuracy', 'N/A')}</p>

            <h2>3. 验证结果VALIDATION RESULTS</h2>
            <pre>{json.dumps(validation_results, indent=2)}</pre>

            <h2>4. 建议IMPROVEMENT SUGGESTIONS</h2>
            <ul>
        """

        # 添加改进建议
        for suggestion in validation_results.get('improvement_suggestions', []):
            html_content += f"<li>{suggestion}</li>"

        html_content += """
            </ul>
        </body>
        </html>
        """

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"报告已保存REPORT SAVED: {report_file}")
        return report_file


class GasLoggingWorkflow:
    """COMPLETE GAS LOGGING INTERPRETATION WORKFLOW"""

    def __init__(self, config_path=None):
        self.qc_module = GasLoggingQC(config_path)
        self.trad_interp = TraditionalInterpretation()
        self.ml_interp = MLInterpretation()
        self.validation = ValidationModule()
        self.visualization = VisualizationModule()

        self.raw_data = None
        self.processed_data = None
        self.trad_results = None
        self.ml_results = None
        self.final_results = None

    def load_data(self, file_path):
        """LOAD DATA"""
        logger.info(f"DATA LOADING: {file_path}")

        if file_path.endswith('.csv'):
            self.raw_data = pd.read_csv(file_path)
        elif file_path.endswith('.xlsx'):
            self.raw_data = pd.read_excel(file_path)
        else:
            raise ValueError("DATA FORMAT NOT SUPPORTED")

        logger.info(f"DATA LOADING COMPLETED: {len(self.raw_data)} records")
        return self.raw_data

    def run_complete_workflow(self, data_path, target_col=None, ml_model_type='random_forest', test_result_path=None,
                              test_target_col=None, depth_tolerance=5):
        """FLAIR GAS LOGGING INTERPRETATION WORKFLOW
        Args:
        data_path: 数据文件路径DATA FILE PATH
        target_col: 训练目标列名(自动检测)TRAINING TARGET COLUMN (AUTO DETECTED)
        ml_model_type: 模型类型MODEL TYPE
        test_result_path: 试油结果文件路径(可选)TEST RESULT FILE PATH (OPTIONAL)
        test_target_col: 试油结果中的解释列名(自动检测)TEST TARGET COLUMN IN TEST RESULTS (AUTO DETECTED)
        """
        logger.info("=" * 50)  #
        logger.info("FLAIR GAS LOGGING INTERPRETATION WORKFLOW")
        logger.info("=" * 50)

        # 1. 加载数据
        self.load_data(data_path)

        # 2. 数据质量检查
        self.processed_data, qc_report = self.qc_module.run_qc(self.raw_data)
        #3.添加必要计算字段

        # 3. 传统方法解释
        self.trad_results = self.trad_interp.run_interpretation(self.processed_data)

        # 4. 机器学习方法
        possible_target_cols = ['INTERPRETATION', '解释结果', '结论', 'RESULT', 'CLASS','test_result']

        if target_col is None:
            for col in possible_target_cols:
                if col in self.processed_data.columns:
                    target_col = col
                    logger.info(f"✅ TRAINING TARGET COLUMNS AUTOMATICALLY DETECTED: '{col}'")
                    break

        if target_col is None or target_col not in self.processed_data.columns:
            logger.warning(f"⚠️ TRAINING TARGET COLUMNS NOT FOUND: '{target_col}'")
            logger.info("⚠️ PSEUDO LABELS FROM TRADITIONAL INTERPRETATION WILL BE USED")
            pseudo_labels = self.trad_results['FINAL_INTERPRETATION'].astype(str)
            self.processed_data['PSEUDO_LABEL'] = pseudo_labels
            target_col = 'PSEUDO_LABEL'

        # 设置模型类型
        self.ml_interp.model_type = ml_model_type

        # 准备训练数据
        X, y = self.ml_interp.prepare_training_data(self.processed_data, target_col)
        training_history = self.ml_interp.train_model(X, y)
        self.ml_results = self.ml_interp.predict(self.processed_data)

        # 5. 试油验证(可选)
        if test_result_path and Path(test_result_path).exists():
            logger.info(f"TEST RESULTS LOADING: {test_result_path}")
            test_results = pd.read_csv(test_result_path)

            # 执行验证
            self.validation.compare_with_test_results(
                self.ml_results,
                test_results,
                depth_tolerance=depth_tolerance,
                target_col=test_target_col
            )
        else:
            logger.info("TEST RESULTS NOT PROVIDED,TEST VERIFICATION SKIPPED")
            self.validation.validation_results['test_comparison'] = None

        # 生成改进建议
        improvement_suggestions = self.validation.generate_improvement_suggestions(
            training_history, self.validation.validation_results
        )

        # 6. 可视化
        # 绘制气测曲线
        self.visualization.plot_gas_curves(
            self.processed_data,
            highlight_intervals=self.ml_results,
            save_path=self.visualization.output_dir / 'gas_curves.png'
        )

        # 绘制解释结果
        self.visualization.plot_interpretation_results(
            self.processed_data,
            self.ml_results,
            save_path=self.visualization.output_dir / 'interpretation_results.png'
        )

        # 7. 生成报告
        report_file = self.visualization.generate_report(
            qc_report, self.trad_results, training_history,
            self.validation.validation_results
        )

        # 8. 保存结果
        self._save_results()

        logger.info("=" * 50)
        logger.info("FLAIR GAS LOGGING INTERPRETATION WORKFLOW")
        logger.info("=" * 50)

        return {
            'qc_report': qc_report,
            'traditional_results': self.trad_results,
            'ml_results': self.ml_results,
            'training_history': training_history,
            'validation_results': self.validation.validation_results,
            'improvement_suggestions': improvement_suggestions,
            'report_file': report_file
        }

    def _save_results(self):
        """SAVING RESULTS TO FILES"""
        output_dir = Path('./output')
        output_dir.mkdir(exist_ok=True)
        # 保存处理后的数据
        self.processed_data.to_csv(output_dir / 'processed_data.csv', index=False)

        # 保存解释结果
        if self.trad_results is not None:
          self.trad_results.to_csv(output_dir / 'traditional_interpretation.csv', index=False)
          #self.Ht_results.to_csv(output_dir / 'Ht_interpretation.csv', index=False)

        if self.ml_results is not None:
          self.ml_results.to_csv(output_dir / 'ml_interpretation.csv', index=False)

        logger.info(f"result files saved in {output_dir}")


# 使用示例和API设计
def main():
    """MAIN FUNCTION"""

    # 创建工作流实例
    workflow = GasLoggingWorkflow(config_path='./config.json')

    # 运行完整工作流
    results = workflow.run_complete_workflow(
        data_path='C:\\3.csv',        # 替换为实际数据路径,试油结果也放在这个目录
        target_col='INTERPRETATION',  # 如果数据包含真实解释结果
        ml_model_type='random_forest'
    )

    # 打印关键结果
    print("\n=== FLAIR GAS LOGGING INTERPRETATION WORKFLOW SUMMARY ===")
    print(f"DATA QC: {len(results['qc_report']['outliers'])} OUTLINERS")
    print(f"MODEL TRAINING ACCURACY: {results['training_history']['train_accuracy']:.3f}")
    print(f"MODEL TEST ACCURACY: {results['training_history']['test_accuracy']:.3f}")

    if results['validation_results'].get('test_comparison'):
        print(f"TEST COMPARISON ACCURACY: {results['validation_results']['test_comparison']['accuracy']:.3f}")

    print(f"\nIMPROVEMENT SUGGESTIONS:")
    for suggestion in results['improvement_suggestions'][:3]:
        print(f"  - {suggestion}")

    print(f"\nDETAILED REPORT: {results['report_file']}")

    return results


# 数据流生成器(用于连续评估)
def data_stream_generator(df, batch_size=50):
    """DATA STREAM GENERATOR"""
    for i in range(0, len(df), batch_size):
        yield df.iloc[i:i + batch_size]


# API接口设计
class GasLoggingAPI:
    """API接口类GAS LOGGING API"""

    def __init__(self, model_path=None):
        self.workflow = GasLoggingWorkflow()
        if model_path and Path(model_path).exists():
            self.load_model(model_path)

    def load_model(self, model_path):
        """TRAINING MODEL LOADING"""
        # 实现模型加载逻辑
        pass

    def predict_single_well(self, data_path):
        """API SINGLE WELL PREDICT """
        results = self.workflow.run_complete_workflow(data_path)
        return results['ml_results']

    def batch_predict(self, data_paths):
        """API BATCH PREDICT"""
        all_results = []
        for path in data_paths:
            results = self.predict_single_well(path)
            all_results.append(results)
        return all_results

    def retrain_model(self, new_data_path, validation_results):
        """API MODEL RETRAINING"""
        # 基于验证结果改进模型
        pass

    def get_model_performance(self):
        """GET MODEL PERFORMANCE"""
        return self.workflow.validation.validation_results


if __name__ == "__main__":
    # 运行示例
    results = main()