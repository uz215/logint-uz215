#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一气测解释系统 - 完整工作流程

该脚本实现了从数据加载到结果验证的完整气测解释工作流程，包括：
1. 数据加载和预处理
2. 数据质量检查（QC）
3. 传统解释方法（PIXLER、三角图版、3H、星形图）
4. 机器学习解释
5. 深度学习解释
6. 结果验证和对比
7. 可视化和报告生成

根据数据中是否包含C6字段自动选择处理模式：
- 如果数据包含C6字段，使用FLAIR模式（完整气测解释）
- 如果数据只有C1-C5字段，使用常规模式（基础气测解释）
"""

from numpy.core import einsumfunc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
from sklearn.neural_network import MLPClassifier
from sklearn.feature_selection import SelectKBest, f_classif, RFE, mutual_info_classif
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import VotingClassifier
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
import tkinter as tk
from tkinter import filedialog, messagebox

import os
import lasio
import dlisio

# 添加SHAP库导入
try:
    import shap
    shap_available = True
except ImportError:
    shap_available = False
    print("警告: SHAP库未安装，将使用特征重要性替代SHAP分析")


warnings.filterwarnings('ignore')

# 常量定义
DEPTH_COLUMN = 'MD'  # 深度列名
GAS_COLUMNS = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']  # 常规气测列名
FLAIR_COLUMNS = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'MCH', 'TL', 'BZ', 'C7', 'C8', 'ROP']  # FLAIR气测列名
TARGET_COLUMN = 'INTERPRETATION'  # 目标列名（大写，与数据集中的列名匹配）
minrng = 0.01  # 最小范围值
maxrng = 1000000  # 最大范围值
maxrop = 2000  # 最大ROP值
ml_model_type = 'random_forest'  # 机器学习模型类型（小写，与_train_single_model方法中的类型匹配）
model_type = 'ensemble'  # 机器学习模型类型
hc_threshold = 0.1  # 总烃阈值，过滤掉总烃含量低的样本

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 标签标准化函数
def standardize_label(label):
    """标准化解释标签"""
    label_map = {
        'OIL': 'OIL',
        'GAS': 'GAS',
        'WATER': 'WATER',
        'OIL-WATER': 'OIL-WATER',
        'GAS-WATER': 'GAS-WATER',
        'DRY': 'DRY'
    }
    if label is None:
        return 'DRY'
    if not isinstance(label, str):
        label = str(label)
    label_upper = label.upper().strip()
    # 尝试直接匹配
    if label_upper in label_map:
        return label_map[label_upper]
    # 尝试部分匹配
    for key in label_map:
        if key in label_upper:
            return label_map[key]
    # 如果都不匹配，返回DRY而不是UNKNOWN
    return 'DRY'

# 数据加载模块
class DataLoader:
    """数据加载和预处理模块"""
    
    def __init__(self, rawdata_path, testdata_path):
        self.rawdata_path = rawdata_path
        self.testdata_path = testdata_path
        self.data = None
        self.testdata = None
        self.data_mode = None  # 'FLAIR' 或 'REGULAR'
    
    def detect_data_mode(self):
        """检测数据模式(FLAIR或常规)"""
        if self.data is None:
            raise ValueError("数据未加载，无法检测数据模式")
        
        # 检查是否包含C6字段
        if 'C6' in self.data.columns:
            self.data_mode = 'FLAIR'
            logger.info("检测到FLAIR数据模式（包含C6字段）")
        else:
            self.data_mode = 'REGULAR'
            logger.info("检测到常规数据模式（只有C1-C5字段）")
        
        return self.data_mode
    
    def load_data(self):
        """加载数据"""
        try:
            logger.info(f"正在加载数据: {self.rawdata_path}")
            
            # 根据文件类型加载气测数据
            #文件名第一个空格前的字符定位井名
            well_name = os.path.basename(self.rawdata_path).split(' ')[0]
            logger.info(f"井名: {well_name}")
            if self.rawdata_path.endswith('.csv'):
                self.data = pd.read_csv(self.rawdata_path, encoding='utf-8')
                # 删除未命名列
                self.data = self.data.loc[:, ~self.data.columns.str.contains('^Unnamed:')]
            # 如果数据是Excel格式文件
            elif self.rawdata_path.endswith('.xlsx'):
                self.data = pd.read_excel(self.rawdata_path)
                # 删除未命名列
                self.data = self.data.loc[:, ~self.data.columns.str.contains('^Unnamed:')]
            # 如果数据是las格式文件
            elif self.rawdata_path.endswith('.las'):
                try:
                    las = lasio.read(self.rawdata_path)
                    self.data = las.df().reset_index()
                except ImportError:
                    logger.error("读取LAS文件需要安装lasio库: pip install lasio")
                    return None
            # 如果数据是dlis格式文件    
            elif self.rawdata_path.endswith('.dlis'):
                try:
                    self.data = pd.DataFrame()
                    with dlisio.load(self.rawdata_path) as f:
                        for channel in f.channels():
                            self.data[channel.name] = channel.data
                except ImportError:
                    logger.error("读取DLIS文件需要安装dlisio库: pip install dlisio")
                    return None
            else:
                logger.error(f"不支持的文件格式: {self.rawdata_path}")
                return None
            #如果深度不是MD，修改为MD
            if 'depth' in self.data.columns:
                self.data.rename(columns={'depth': 'MD'}, inplace=True)
            if 'DEPTH' in self.data.columns:
                self.data.rename(columns={'DEPTH': 'MD'}, inplace=True)
            if 'dep' in self.data.columns:
                self.data.rename(columns={'dep': 'MD'}, inplace=True)
            if 'DEP' in self.data.columns:
                self.data.rename(columns={'DEP': 'MD'}, inplace=True)

            logger.info(f"气测数据加载成功，共 {len(self.data)} 条记录")
            #logger.info(f"数据列名: {list(self.data.columns)}")
            
            # 计算T15（总烃）
            gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
            available_gas_cols = [col for col in gas_cols if col in self.data.columns]
            if available_gas_cols:
                self.data['T15'] = self.data[available_gas_cols].sum(axis=1)
                logger.info(f"已计算T15（总烃）列")
            else:
                logger.warning("缺少必要的气测列，无法计算T15")
                self.data['T15'] = 0
            
            # 检测数据模式
            self.detect_data_mode()
            
            # 根据文件类型加载试油数据
            try:
                if self.testdata_path is None:
                    logger.info("试油数据路径为None，跳过试油数据加载")
                    self.testdata = None
                else:
                    logger.info(f"正在加载试油数据: {self.testdata_path}")
                    # 标准化文件路径，处理扩展名大小写和可能的错误
                    testdata_path_lower = self.testdata_path.lower()
                    
                    # 如果数据是CSV格式文件
                    if testdata_path_lower.endswith('.csv'):
                        self.testdata = pd.read_csv(self.testdata_path, encoding='utf-8')
                    # 如果数据是Excel格式文件（处理各种可能的扩展名）
                    elif any(testdata_path_lower.endswith(ext) for ext in ['.xlsx', '.xls', '.xlsm']):
                        self.testdata = pd.read_excel(self.testdata_path)
                    else:
                        logger.warning(f"不支持的试油数据文件格式: {self.testdata_path}")
                        self.testdata = None
                
                if self.testdata is not None:
                    logger.info(f"试油数据加载成功，共 {len(self.testdata)} 条记录")
                    #logger.info(f"试油数据列名: {list(self.testdata.columns)}")
                    # 检查必要的列是否存在（支持不同的列名）
                    has_start_depth = any(col in self.testdata.columns for col in ['SDEP', 'sdep', 'SDEPTH', 'sdepth'])
                    has_end_depth = any(col in self.testdata.columns for col in ['EDEP', 'edep', 'EDEPTH', 'edepth'])
                    has_result = any(col in self.testdata.columns for col in ['result', 'RESULT', 'Test Result', 'test_result'])
                    
                    if not (has_start_depth and has_end_depth and has_result):
                        logger.error(f"试油数据缺少必要列: 开始深度({has_start_depth}), 结束深度({has_end_depth}), 结果({has_result})")
                        # 只有当原始数据中没有test_results列时，才添加默认值
                        if 'test_results' not in self.data.columns:
                            self.data['test_results'] = None
                    else:
                        # 如果试油数据不是连续深度而是深度段，进行深度转换，把试油数据添加到原始数据中
                        # 无论原始数据中是否有test_results列，都覆盖为None并从试油数据加载
                        self.data['test_results'] = None
                        updated_count = 0
                        
                        # 打印试油数据的前几行，了解数据格式
                        #logger.info(f"试油数据前5行: {self.testdata.head().to_dict('records')}")
                        #logger.info(f"试油数据列名: {list(self.testdata.columns)}")
                        
                        for idx, row in self.testdata.iterrows():
                            try:
                                # 尝试不同的列名
                                if 'SDEP' in self.testdata.columns:
                                    depth1 = row['SDEP']
                                elif 'sdep' in self.testdata.columns:
                                    depth1 = row['sdep']
                                elif 'SDEPTH' in self.testdata.columns:
                                    depth1 = row['SDEPTH']
                                elif 'sdepth' in self.testdata.columns:
                                    depth1 = row['sdepth']
                                else:
                                    depth1 = row.get('SDEP', None)
                                
                                if 'EDEP' in self.testdata.columns:
                                    depth2 = row['EDEP']
                                elif 'edep' in self.testdata.columns:
                                    depth2 = row['edep']
                                elif 'EDEPTH' in self.testdata.columns:
                                    depth2 = row['EDEPTH']
                                elif 'edepth' in self.testdata.columns:
                                    depth2 = row['edepth']
                                else:
                                    depth2 = row.get('EDEP', None)
                                
                                if 'result' in self.testdata.columns:
                                    result = row['result']
                                elif 'RESULT' in self.testdata.columns:
                                    result = row['RESULT']
                                elif 'Test Result' in self.testdata.columns:
                                    result = row['Test Result']
                                elif 'test_result' in self.testdata.columns:
                                    result = row['test_result']
                                else:
                                    result = row.get('result', None)
                                
                                # 检查深度值是否有效
                                if pd.isna(depth1) or pd.isna(depth2) or depth1 >= depth2:
                                    logger.warning(f"试油数据第{idx+1}行深度无效: {depth1}m - {depth2}m，跳过处理")
                                    continue
                                
                                mask = (self.data['MD'] >= depth1) & (self.data['MD'] <= depth2)
                                affected_rows = mask.sum()
                                
                                # 处理result为None的情况
                                if result is None:
                                    result = 'DRY'
                                else:
                                    # 标准化试油结果标签，确保与解释结果格式一致
                                    result = standardize_label(result)
                                
                                if affected_rows > 0:
                                    self.data.loc[mask, 'test_results'] = result
                                    updated_count += affected_rows
                                    logger.info(f"试油数据第{idx+1}行: {depth1}m - {depth2}m，结果: {result}，匹配 {affected_rows} 条记录")
                                else:
                                    logger.warning(f"试油数据第{idx+1}行深度段 {depth1}m - {depth2}m 在数据中无匹配记录")
                            
                            except Exception as e:
                                logger.error(f"处理试油数据第{idx+1}行时出错: {e}")
                                continue
                        
                        logger.info(f"试油数据匹配完成，共更新 {updated_count} 条记录")
                        logger.info(f"试油结果分布: {self.data['test_results'].value_counts().to_dict()}")
                        
                        # 确保test_results列被正确填充
                        if self.data['test_results'].isna().all():
                            logger.warning("所有试油结果都是NaN，可能是深度匹配问题")
                            # 尝试使用更宽松的深度匹配
                            for idx, row in self.testdata.iterrows():
                                try:
                                    # 尝试不同的列名
                                    if 'SDEP' in self.testdata.columns:
                                        depth1 = row['SDEP']
                                    elif 'sdep' in self.testdata.columns:
                                        depth1 = row['sdep']
                                    elif 'SDEPTH' in self.testdata.columns:
                                        depth1 = row['SDEPTH']
                                    elif 'sdepth' in self.testdata.columns:
                                        depth1 = row['sdepth']
                                    else:
                                        depth1 = row.get('SDEP', None)
                                    
                                    if 'EDEP' in self.testdata.columns:
                                        depth2 = row['EDEP']
                                    elif 'edep' in self.testdata.columns:
                                        depth2 = row['edep']
                                    elif 'EDEPTH' in self.testdata.columns:
                                        depth2 = row['EDEPTH']
                                    elif 'edepth' in self.testdata.columns:
                                        depth2 = row['edepth']
                                    else:
                                        depth2 = row.get('EDEP', None)
                                    
                                    if 'result' in self.testdata.columns:
                                        result = row['result']
                                    elif 'RESULT' in self.testdata.columns:
                                        result = row['RESULT']
                                    elif 'Test Result' in self.testdata.columns:
                                        result = row['Test Result']
                                    elif 'test_result' in self.testdata.columns:
                                        result = row['test_result']
                                    else:
                                        result = row.get('result', None)
                                    
                                    if pd.isna(depth1) or pd.isna(depth2) or depth1 >= depth2:
                                        continue
                                    
                                    # 找到最接近的深度点
                                    closest_idx = np.abs(self.data['MD'] - (depth1 + depth2) / 2).idxmin()
                                    closest_depth = self.data.loc[closest_idx, 'MD']
                                    
                                    if result is None:
                                        result = 'DRY'
                                    else:
                                        result = standardize_label(result)
                                    
                                    self.data.loc[closest_idx, 'test_results'] = result
                                    logger.info(f"使用最接近的深度点: {closest_depth}m，结果: {result}")
                                except Exception as e:
                                    logger.error(f"尝试宽松匹配时出错: {e}")
                                    continue
                        
                        logger.info(f"最终试油结果分布: {self.data['test_results'].value_counts().to_dict()}")
                else:
                    logger.warning("试油数据加载失败，将不进行试油结果对比")
                    # 只有当原始数据中没有test_results列时，才添加默认值
                    if 'test_results' not in self.data.columns:
                        self.data['test_results'] = None
            
            except Exception as e:
                logger.error(f"加载试油数据时出错: {e}")
                # 只有当原始数据中没有test_results列时，才添加默认值
                if 'test_results' not in self.data.columns:
                    self.data['test_results'] = None
            
            return self.data
        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            return None

# 数据质量检查模块
class QualityControlModule:
    """数据质量检查模块"""
    
    def __init__(self, data, data_mode):
        self.data = data
        self.data_mode = data_mode
        self.qc_report = None
    
    def run_qc(self):
        """运行质量检查"""
        try:
            logger.info("开始数据质量检查...")
            
            qc_report = {
                'total_records': len(self.data),
                'missing_values': {},
                'outliers': {},
                'data_types': {},
                'data_mode': self.data_mode,
                'quality_score': 0,
                'issues': []
            }
            
            # 检查缺失值
            missing_values = self.data.isnull().sum()
            for col in self.data.columns:
                if missing_values[col] > 0:
                    qc_report['missing_values'][col] = int(missing_values[col])
                    qc_report['issues'].append(f"列 '{col}' 存在 {missing_values[col]} 个缺失值")
            
            # 检查数据类型
            for col in self.data.columns:
                qc_report['data_types'][col] = str(self.data[col].dtype)
            
            # 检查异常值（仅对数值列）
            numeric_cols = self.data.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                if self.data[col].notnull().any():
                    Q1 = self.data[col].quantile(0.25)
                    Q3 = self.data[col].quantile(0.75)
                    IQR = Q3 - Q1
                    outliers = self.data[(self.data[col] < Q1 - 1.5*IQR) | (self.data[col] > Q3 + 1.5*IQR)]
                    outlier_count = len(outliers)
                    
                    if outlier_count > 0:
                        qc_report['outliers'][col] = outlier_count
                        if outlier_count / len(self.data) > 0.1:  # 超过10%的异常值
                            qc_report['issues'].append(f"列 '{col}' 存在较多异常值 ({outlier_count} 个，占比 {outlier_count/len(self.data)*100:.1f}%)")
            
            # 检查必要的列是否存在
            required_cols = ['MD', 'C1', 'C2', 'C3']
            missing_required = [col for col in required_cols if col not in self.data.columns]
            if missing_required:
                qc_report['issues'].append(f"缺少必要列: {', '.join(missing_required)}")
            
            # 检查深度数据
            if 'MD' in self.data.columns:
                if self.data['MD'].duplicated().any():
                    qc_report['issues'].append(f"存在重复的深度值")
                
                if not (self.data['MD'].diff() > 0).all():
                    qc_report['issues'].append(f"深度数据不是严格递增的")
            
            # 计算质量得分
            base_score = 100
            for issue in qc_report['issues']:
                base_score -= 10
            qc_report['quality_score'] = max(0, base_score)
            
            self.qc_report = qc_report
            
            logger.info(f"数据质量检查完成，质量得分: {qc_report['quality_score']}/100")
            if qc_report['issues']:
                logger.warning(f"发现 {len(qc_report['issues'])} 个问题:")
                for issue in qc_report['issues']:
                    logger.warning(f"  - {issue}")
            else:
                logger.info("数据质量检查通过，未发现问题")
            
            return qc_report
        except Exception as e:
            logger.error(f"数据质量检查失败: {e}")
            return None

# 传统解释模块
class TraditionalInterpretationModule:
    """传统解释方法模块"""
    
    def __init__(self, data, data_mode, output_dir, config_path=None):
        self.data = data
        self.data_mode = data_mode
        self.output_dir = output_dir
        self.results = None
        self.config = self.load_config(config_path)
    
    def load_config(self, config_path=None):
        """加载解释配置"""
        try:
            import json
            import os
            
            # 如果提供了配置文件路径，使用提供的路径
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"成功加载解释配置: {config_path}")
                return config
            else:
                # 如果没有提供配置文件路径或文件不存在，抛出异常
                if config_path:
                    logger.error(f"配置文件不存在: {config_path}")
                    raise FileNotFoundError(f"配置文件不存在: {config_path}")
                else:
                    logger.error("未提供配置文件路径")
                    raise ValueError("未提供配置文件路径")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            raise
    
    def pixler_interpretation(self, df):
        """PIXLER解释方法"""
        try:
            logger.info("执行PIXLER解释方法...")
            
            # 检查必要的基本列是否存在
            basic_required_cols = ['MD', 'C1', 'C2', 'C3', 'IC4', 'NC4']
            missing_basic_cols = [col for col in basic_required_cols if col not in df.columns]
            if missing_basic_cols:
                logger.warning(f"PIXLER解释缺少基本必要列: {missing_basic_cols}")
                return None
            
            # 计算PIXLER参数
            df['C1C2'] = np.where(df['C2'] == 0, 0, df['C1'] / df['C2'])
            df['C1C3'] = np.where(df['C3'] == 0, 0, df['C1'] / df['C3'])
            df['C1C4'] = np.where((df['IC4'] + df['NC4']) == 0, 0, df['C1'] / (df['IC4'] + df['NC4']))
            
            # 获取配置中的阈值（不设置默认值，完全使用配置文件数据）
            pixler_config = self.config['pixler']
            oil_config = pixler_config['oil']
            gas_config = pixler_config['gas']
            
            # PIXLER解释规则
            df['ITP_pixler'] = 'DRY'
            
            # 油层判断
            oil_mask = (df['C1C2'] >= oil_config['C1C2'][0]) & (df['C1C2'] <= oil_config['C1C2'][1]) & \
                      (df['C1C3'] >= oil_config['C1C3'][0]) & (df['C1C3'] <= oil_config['C1C3'][1]) & \
                      (df['C1C4'] >= oil_config['C1C4'][0]) & (df['C1C4'] <= oil_config['C1C4'][1])
            df.loc[oil_mask, 'ITP_pixler'] = 'OIL'
            
            # 气层判断
            gas_mask = (df['C1C2'] >= gas_config['C1C2'][0]) & (df['C1C2'] <= gas_config['C1C2'][1]) & \
                      (df['C1C3'] >= gas_config['C1C3'][0]) & (df['C1C3'] <= gas_config['C1C3'][1]) & \
                      (df['C1C4'] >= gas_config['C1C4'][0]) & (df['C1C4'] <= gas_config['C1C4'][1])
            df.loc[gas_mask, 'ITP_pixler'] = 'GAS'
            
            # 干层判断
            dry_mask = ~(oil_mask | gas_mask)
            df.loc[dry_mask, 'ITP_pixler'] = 'DRY'
            logger.info(f"PIXLER解释完成")
            logger.info(f"解释结果分布: {df['ITP_pixler'].value_counts().to_dict()}")
            
            return df
        except Exception as e:
            logger.error(f"PIXLER解释失败: {e}")
            return None
    
    def triangle_interpretation(self, df):
        """三角图版解释方法"""
        try:
            logger.info("执行三角图版解释方法...")
            
            # 计算三角图版参数
            df['T14']=df['C1']+df['C2']+df['C3']+df['IC4']+df['NC4']
            df['C1T14'] = np.where(df['T14'] == 0, 0, df['C1'] / df['T14'])
            df['C2T14'] = np.where(df['T14'] == 0, 0, df['C2'] / df['T14'])
            df['C3T14'] = np.where(df['T14'] == 0, 0, df['C3'] / df['T14'])
            df['NC4T14'] = np.where(df['T14'] == 0, 0, df['NC4'] / df['T14'])
           
            # 计算重烃含量
            df['heavy_hydrocarbon'] = df['C2T14'] + df['C3T14'] + df['NC4T14']
            
            # 获取配置（不设置默认值，完全使用配置文件数据）
            triangle_config = self.config['triangle']
            
            # 计算lr参数
            lr=(df['C2T14']+df['C3T14']+df['NC4T14']-triangle_config['lr_offset'])/triangle_config['lr_factor']
            
            # 三角图版解释规则
            df['ITP_triangle'] = 'DRY'
            
            # 油层判断：重烃含量较高，C1含量适中
            oil_mask = (lr<0)|(lr>0)&(df['T14'] > triangle_config['t14_threshold']) & (df['heavy_hydrocarbon'] > triangle_config['heavy_hydrocarbon_threshold']) & (df['C1T14'] >= triangle_config['c1t14_range']['min']) & (df['C1T14'] <= triangle_config['c1t14_range']['max'])
            df.loc[oil_mask, 'ITP_triangle'] = 'OIL'
            
            # 气层判断：C1含量较高
            gas_mask = (lr>0)&(df['T14'] > triangle_config['t14_threshold']) & (df['C1T14'] > triangle_config['c1t14_range']['max'])
            df.loc[gas_mask, 'ITP_triangle'] = 'GAS'
            
            logger.info(f"三角图版解释完成")
            logger.info(f"解释结果分布: {df['ITP_triangle'].value_counts().to_dict()}")
            
            return df
        except Exception as e:
            logger.error(f"三角图版解释失败: {e}")
            return None
    
    def three_h_interpretation(self, df):
        """3H解释方法"""
        try:
            logger.info("执行3H解释方法...")
            
            # 计算3H参数
            df['WH'] = np.where((df['C2']+df['C3']+df['IC4']+df['NC4']+df['IC5']+df['NC5']) == 0, 0, (df['C2']+df['C3']+df['IC4']+df['NC4']+df['IC5']+df['NC5']) / (df['C1']+df['C2']+df['C3']+df['IC4']+df['NC4']+df['IC5']+df['NC5']))
            df['CH'] = np.where(df['C3'] == 0, 0, (df['IC4']+df['NC4']+df['IC5']+df['NC5']) / df['C3'])
            df['BH'] = np.where((df['C3']+df['IC4']+df['NC4']+df['IC5']+df['NC5']) == 0, 0, (df['C1']+df['C2']) / (df['C3']+df['IC4']+df['NC4']+df['IC5']+df['NC5']))
            
            # 获取配置（不设置默认值，完全使用配置文件数据）
            three_h_config = self.config['three_h']
            oil_config = three_h_config['oil']
            gas_config = three_h_config['gas']
            
            # 3H解释规则
            df['ITP_3h'] = 'DRY'
            
            # 油层判断
            oil_mask = (df['WH'] >= oil_config['WH'][0]) & (df['WH'] <= oil_config['WH'][1]) & \
                      (df['CH'] >= oil_config['CH_min']) & \
                      (df['BH'] <= df['WH'] * oil_config['BH_max_ratio'])
            df.loc[oil_mask, 'ITP_3h'] = 'OIL'
            
            # 气层判断
            gas_mask = (df['WH'] >= gas_config['WH'][0]) & (df['WH'] <= gas_config['WH'][1]) & ~oil_mask
            df.loc[gas_mask, 'ITP_3h'] = 'GAS'
            
            logger.info(f"3H解释完成")
            logger.info(f"解释结果分布: {df['ITP_3h'].value_counts().to_dict()}")
            
            return df
        except Exception as e:
            logger.error(f"3H解释失败: {e}")
            return None
    
    def star_interpretation(self, df):
        """STAR解释方法（使用余弦相似法）"""
        try:
            logger.info("开始STAR解释...")
            
            # 检查输入数据
            if df is None:
                logger.error("输入数据为None")
                # 创建一个空数据框，添加必要的列
                df = pd.DataFrame()
                df['ITP_star'] = 'DRY'
                return df
            
            # 获取配置（不设置默认值，完全使用配置文件数据）
            star_config = self.config['star']
            
            # 计算STAR参数
            required_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'T15']
            if all(col in df.columns for col in required_cols):
                # 计算各组分比值
                df['C1T15'] = df['C1'] / df['T15']
                df['C2T15'] = df['C2'] / df['T15']
                df['C3T15'] = df['C3'] / df['T15']
                df['C4T15'] = (df['IC4'] + df['NC4']) / df['T15']
                
                # 计算C2/C3和C1/C2
                df['C2_C3'] = np.where(df['C3'] == 0, 0, df['C2'] / df['C3'])
                df['C1_C2'] = np.where(df['C2'] == 0, 0, df['C1'] / df['C2'])
                
                # 计算TMUL（异常倍数）
                #计算基值总烃基线值Cbaseline,取前30个Total18的25%分布处的值(就是25%的数小于该数值)
                df['Tbsl'] = df['T15'].rolling(star_config['rolling_window'], center=True, min_periods=1).quantile(star_config['quantile'])
                df['TMUL'] = np.where(df['Tbsl'] == 0, 0, round(df['T15'] / df['Tbsl'], 2)) #计算异常幅度
                
                # 定义核心参数和模板
                core_params = star_config['core_params']
                templates = star_config['templates']
                
                # 创建结果列
                df['ITP_star'] = ''
                similarity_threshold = star_config['similarity_threshold']
                
                # 批量处理：一次性提取所有核心参数值
                target_values = df[core_params].values
                
                # 计算相似度并确定结果
                for idx in range(len(df)):
                    target = target_values[idx]
                    
                    similarity = {}
                    for fluid_type, template in templates.items():
                        # 使用余弦相似法计算相似度
                        template_array = np.array(template)
                        norm_target = np.linalg.norm(target)
                        norm_template = np.linalg.norm(template_array)
                        
                        if norm_target > 0 and norm_template > 0:
                            cosine_sim = np.dot(target, template_array) / (norm_target * norm_template)
                        else:
                            cosine_sim = 0
                        
                        similarity[fluid_type] = cosine_sim
                    
                    # 确定结果
                    valid_types = {k: v for k, v in similarity.items() if v >= similarity_threshold}
                    if valid_types:
                        result = max(valid_types.items(), key=lambda x: x[1])[0]
                    else:
                        result = "DRY"
                    
                    # 将结果添加到数据框
                    df.at[idx, 'ITP_star'] = result
                
                logger.info(f"STAR解释完成")
                logger.info(f"解释结果分布: {df['ITP_star'].value_counts().to_dict()}")
            else:
                logger.warning(f"STAR解释所需列不全，缺少: {[col for col in required_cols if col not in df.columns]}")
                df['ITP_star'] = 'DRY'
            
            return df
        except Exception as e:
            logger.error(f"STAR解释失败: {e}")
            # 确保返回一个有效的数据框
            if df is None:
                df = pd.DataFrame()
            if 'ITP_star' not in df.columns:
                df['ITP_star'] = 'DRY'
            else:
                df['ITP_star'] = 'DRY'
            return df
    
    def optimize_config_from_test_results(self):
        """根据试油结果优化配置参数"""
        try:
            import json
            import os
            
            # 检查是否有试油结果
            if 'test_results' not in self.data.columns or self.data['test_results'].isna().all():
                logger.warning("没有有效的试油结果，无法优化配置")
                return self.config
            
            logger.info("根据试油结果优化配置参数...")
            
            # 获取有试油结果的数据
            test_data = self.data[self.data['test_results'].notna()].copy()
            
            # 优化Pixler参数
            if 'C1C2' in test_data.columns and 'C1C3' in test_data.columns and 'C1C4' in test_data.columns:
                # 油层数据
                oil_data = test_data[test_data['test_results'].str.upper() == 'OIL']
                if not oil_data.empty:
                    # 计算油层参数范围
                    self.config['pixler']['oil']['C1C2'] = [
                        max(0.1, oil_data['C1C2'].quantile(0.1)),
                        oil_data['C1C2'].quantile(0.9)
                    ]
                    self.config['pixler']['oil']['C1C3'] = [
                        max(0.1, oil_data['C1C3'].quantile(0.1)),
                        oil_data['C1C3'].quantile(0.9)
                    ]
                    self.config['pixler']['oil']['C1C4'] = [
                        max(0.1, oil_data['C1C4'].quantile(0.1)),
                        oil_data['C1C4'].quantile(0.9)
                    ]
                
                # 气层数据
                gas_data = test_data[test_data['test_results'].str.upper() == 'GAS']
                if not gas_data.empty:
                    # 计算气层参数范围
                    self.config['pixler']['gas']['C1C2'] = [
                        max(0.1, gas_data['C1C2'].quantile(0.1)),
                        gas_data['C1C2'].quantile(0.9)
                    ]
                    self.config['pixler']['gas']['C1C3'] = [
                        max(0.1, gas_data['C1C3'].quantile(0.1)),
                        gas_data['C1C3'].quantile(0.9)
                    ]
                    self.config['pixler']['gas']['C1C4'] = [
                        max(0.1, gas_data['C1C4'].quantile(0.1)),
                        gas_data['C1C4'].quantile(0.9)
                    ]
            
            # 优化Triangle参数
            if 'T14' in test_data.columns and 'heavy_hydrocarbon' in test_data.columns and 'C1T14' in test_data.columns:
                # 油层数据
                oil_data = test_data[test_data['test_results'].str.upper() == 'OIL']
                if not oil_data.empty:
                    self.config['triangle']['t14_threshold'] = max(0.01, oil_data['T14'].quantile(0.1))
                    self.config['triangle']['heavy_hydrocarbon_threshold'] = max(0.01, oil_data['heavy_hydrocarbon'].quantile(0.1))
                    self.config['triangle']['c1t14_range']['min'] = max(0.01, oil_data['C1T14'].quantile(0.1))
                    self.config['triangle']['c1t14_range']['max'] = oil_data['C1T14'].quantile(0.9)
                
                # 气层数据
                gas_data = test_data[test_data['test_results'].str.upper() == 'GAS']
                if not gas_data.empty:
                    self.config['triangle']['c1t14_range']['max'] = min(self.config['triangle']['c1t14_range']['max'], gas_data['C1T14'].quantile(0.1))
            
            # 优化3H参数
            if 'WH' in test_data.columns and 'CH' in test_data.columns and 'BH' in test_data.columns:
                # 油层数据
                oil_data = test_data[test_data['test_results'].str.upper() == 'OIL']
                if not oil_data.empty:
                    self.config['three_h']['oil']['WH'] = [
                        max(0.01, oil_data['WH'].quantile(0.1)),
                        oil_data['WH'].quantile(0.9)
                    ]
                    self.config['three_h']['oil']['CH_min'] = max(0.01, oil_data['CH'].quantile(0.1))
                    self.config['three_h']['oil']['BH_max_ratio'] = (oil_data['BH'] / oil_data['WH'].replace(0, np.nan)).quantile(0.9)
                
                # 气层数据
                gas_data = test_data[test_data['test_results'].str.upper() == 'GAS']
                if not gas_data.empty:
                    self.config['three_h']['gas']['WH'] = [
                        max(0.01, gas_data['WH'].quantile(0.1)),
                        gas_data['WH'].quantile(0.9)
                    ]
            
            # 优化STAR参数
            if 'C1T15' in test_data.columns and 'C2T15' in test_data.columns and 'TMUL' in test_data.columns and 'C1_C2' in test_data.columns and 'C2_C3' in test_data.columns and 'C3T15' in test_data.columns and 'C4T15' in test_data.columns:
                # 油层数据
                oil_data = test_data[test_data['test_results'].str.upper() == 'OIL']
                if not oil_data.empty:
                    self.config['star']['templates']['OIL'] = [
                        oil_data['C1T15'].mean(),
                        oil_data['C2T15'].mean(),
                        oil_data['TMUL'].mean(),
                        oil_data['C1_C2'].mean(),
                        oil_data['C2_C3'].mean(),
                        oil_data['C3T15'].mean(),
                        oil_data['C4T15'].mean()
                    ]
                
                # 气层数据
                gas_data = test_data[test_data['test_results'].str.upper() == 'GAS']
                if not gas_data.empty:
                    self.config['star']['templates']['GAS'] = [
                        gas_data['C1T15'].mean(),
                        gas_data['C2T15'].mean(),
                        gas_data['TMUL'].mean(),
                        gas_data['C1_C2'].mean(),
                        gas_data['C2_C3'].mean(),
                        gas_data['C3T15'].mean(),
                        gas_data['C4T15'].mean()
                    ]
            
            logger.info("配置参数优化完成")
            return self.config
        except Exception as e:
            logger.error(f"优化配置失败: {e}")
            return self.config
    
    def save_config_with_well_name(self, well_name):
        """保存配置文件，文件名包含井名"""
        try:
            import json
            import os
            
            # 创建配置保存目录
            config_save_dir = os.path.join(self.output_dir, 'config')
            os.makedirs(config_save_dir, exist_ok=True)
            
            # 保存路径
            config_path = os.path.join(config_save_dir, f'{well_name}_interpretation_config.json')
            
            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"配置文件保存成功: {config_path}")
            return config_path
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return None
    
    def run_interpretation(self, well_name='Unknown'):
        """运行所有传统解释方法"""
        try:
            logger.info("开始传统解释方法...")
            
            # 直接使用self.data，不创建副本
            #logger.info(f"初始self.data形状: {self.data.shape}")
            #logger.info(f"初始self.data列: {list(self.data.columns)}")
            
            # 执行各种传统解释方法，直接修改self.data
            logger.info("执行Pixler解释...")
            # 直接传递self.data，方法内部会修改它
            self.pixler_interpretation(self.data)
            #logger.info(f"Pixler解释后self.data形状: {self.data.shape}")
            #logger.info(f"Pixler解释后self.data列: {list(self.data.columns)}")
            
            logger.info("执行Triangle解释...")
            # 直接传递self.data，方法内部会修改它
            self.triangle_interpretation(self.data)
            #logger.info(f"Triangle解释后self.data形状: {self.data.shape}")
            #logger.info(f"Triangle解释后self.data列: {list(self.data.columns)}")
            
            logger.info("执行Three H解释...")
            # 直接传递self.data，方法内部会修改它
            self.three_h_interpretation(self.data)
            #logger.info(f"Three H解释后self.data形状: {self.data.shape}")
            #logger.info(f"Three H解释后self.data列: {list(self.data.columns)}")
            
            logger.info("执行STAR解释...")
            # 直接传递self.data，方法内部会修改它
            self.star_interpretation(self.data)
            #logger.info(f"STAR解释后self.data形状: {self.data.shape}")
            #logger.info(f"STAR解释后self.data列: {list(self.data.columns)}")
            
            # 综合解释结果（多数投票）
            interpretation_cols = ['ITP_pixler', 'ITP_triangle', 'ITP_3h', 'ITP_star']
            available_cols = [col for col in interpretation_cols if col in self.data.columns]
            logger.info(f"可用的解释列: {available_cols}")
            
            if available_cols:
                self.data['ITP_traditional'] = self.data[available_cols].mode(axis=1)[0]
                logger.info(f"传统解释综合结果分布: {self.data['ITP_traditional'].value_counts().to_dict()}")
            else:
                logger.warning("没有可用的传统解释结果列，跳过综合解释")
                self.data['ITP_traditional'] = 'DRY'
            
            # 确保所有解释列都存在
            for col in ['ITP_pixler', 'ITP_triangle', 'ITP_3h', 'ITP_star', 'ITP_traditional']:
                if col not in self.data.columns:
                    self.data[col] = 'DRY'
                    logger.info(f"添加默认列 {col}")
            
            # 根据试油结果优化配置
            self.optimize_config_from_test_results()
            
            # 保存带井名的配置文件
            self.save_config_with_well_name(well_name)
            
            self.results = self.data
            
            #logger.info(f"最终self.data形状: {self.data.shape}")
            #logger.info(f"最终self.data列: {list(self.data.columns)}")
            logger.info("传统解释方法完成")
            return True
        except Exception as e:
            logger.error(f"传统解释失败: {e}")
            # 确保所有解释列都存在
            for col in ['ITP_pixler', 'ITP_triangle', 'ITP_3h', 'ITP_star', 'ITP_traditional']:
                if col not in self.data.columns:
                    self.data[col] = 'DRY'
            self.results = self.data
            return False

# 机器学习解释模块
class MLInterpretationModule:
    """机器学习解释模块"""
    
    def __init__(self, data, data_mode, output_dir):
        self.data = data
        self.data_mode = data_mode
        self.output_dir = output_dir
        self.model = None
        self.results = None
        self.feature_importance = None
        self.shap_values = None
    
    def prepare_features(self, df):
        """准备特征"""
        try:
            # 根据数据模式选择特征列
            if self.data_mode == 'FLAIR':
                feature_cols = FLAIR_COLUMNS
            else:
                feature_cols = GAS_COLUMNS
            
            # 检查特征列是否存在
            available_features = [col for col in feature_cols if col in df.columns]
            
            if not available_features:
                logger.error("没有可用的特征列")
                return None, None
            
            logger.info(f"使用特征列: {available_features}")
            
            # 创建特征
            X = df[available_features].copy()
            
            # 处理缺失值
            X = X.fillna(0)
            
            # 处理异常值：仅截断低于下限的值，保留高值，仅剔除物理上不可能的值
            for col in X.columns:
                Q1 = X[col].quantile(0.25)
                Q3 = X[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                
                # 对于物理上不可能为负的值（如气体含量、压力等），设置下限为0
                if col in ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'C7', 'C8', 'MCH', 'TL', 'BZ', 'ROP', 'T15']:
                    lower_bound = max(lower_bound, 0)
                
                # 仅截断低于下限的值，保留高值
                X[col] = X[col].clip(lower=lower_bound)
            
            # 特征工程增强
            # 1. 组分间的比值
            if 'C2' in df.columns and 'C3' in df.columns:
                X['C2C3'] = np.where(df['C3'] == 0, 0, df['C2'] / df['C3'])
            if 'C3' in df.columns and 'IC4' in df.columns and 'NC4' in df.columns:
                X['C3C4'] = np.where((df['IC4'] + df['NC4']) == 0, 0, df['C3'] / (df['IC4'] + df['NC4']))
            if 'IC4' in df.columns and 'NC4' in df.columns:
                X['IC4NC4'] = np.where(df['NC4'] == 0, 0, df['IC4'] / df['NC4'])
            
            # 2. 总烃相关特征
            if 'T15' in df.columns:
                # T15的滑动平均
                X['T15_rolling_mean'] = df['T15'].rolling(window=5, center=True, min_periods=1).mean()
                # T15梯度
                X['T15_gradient'] = df['T15'].diff()
                X['T15_gradient'] = X['T15_gradient'].fillna(0)
            
            # 3. 轻重组分比例
            if all(col in df.columns for col in ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']):
                light_hydrocarbons = df['C1'] + df['C2']
                heavy_hydrocarbons = df['C3'] + df['IC4'] + df['NC4'] + df['IC5'] + df['NC5']
                X['light_heavy_ratio'] = np.where(heavy_hydrocarbons == 0, 0, light_hydrocarbons / heavy_hydrocarbons)
            
            # 4. 其他衍生特征
            if 'C1' in df.columns and 'C2' in df.columns and 'C3' in df.columns:
                X['C1C2C3'] = np.where((df['C2'] + df['C3']) == 0, 0, df['C1'] / (df['C2'] + df['C3']))
            
            # 标准化
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 获取所有特征名称（包括新添加的特征）
            all_feature_names = list(X.columns)
            
            logger.info(f"增强后特征列: {all_feature_names}")
            
            return X_scaled, all_feature_names
        except Exception as e:
            logger.error(f"特征准备失败: {e}")
            return None, None
    
    def prepare_labels(self, df):
        """准备标签"""
        try:
            # 使用传统解释结果作为标签
            if 'ITP_traditional' in df.columns:
                y = df['ITP_traditional'].copy()
            elif 'test_results' in df.columns and df['test_results'].notna().any():
                # 如果有试油结果，使用试油结果
                y = df['test_results'].copy()
                y = y.fillna('DRY')  # 将缺失值填充为DRY
            else:
                # 如果都没有，创建模拟标签
                logger.warning("没有可用的标签，创建模拟标签")
                y = pd.Series(['DRY'] * len(df), index=df.index)
            
            # 标准化标签
            y = y.apply(standardize_label)
            
            # 创建一个全为True的valid_mask，因为现在standardize_label不会返回UNKNOWN
            valid_mask = pd.Series([True] * len(y), index=y.index)
            
            # 检查标签分布
            label_counts = y.value_counts().to_dict()
            logger.info(f"标签分布: {label_counts}")
            
            # 如果所有标签都是DRY，尝试基于气测数据创建一些非DRY标签
            if len(label_counts) == 1 and 'DRY' in label_counts:
                logger.warning("所有标签都是DRY，尝试基于气测数据创建非DRY标签")
                
                # 基于总烃和气体比值创建一些非DRY标签
                if 'T15' in df.columns and 'C1C2' in df.columns:
                    # 找到总烃较高的样本
                    high_hc_mask = df['T15'] > df['T15'].quantile(0.75)
                    # 找到C1/C2比值较高的样本（可能是气层）
                    high_c1c2_mask = df['C1C2'] > df['C1C2'].quantile(0.75)
                    # 找到C1/C2比值适中的样本（可能是油层）
                    mid_c1c2_mask = (df['C1C2'] > df['C1C2'].quantile(0.25)) & (df['C1C2'] <= df['C1C2'].quantile(0.75))
                    
                    # 更新标签
                    y.loc[high_hc_mask & high_c1c2_mask] = 'GAS'
                    y.loc[high_hc_mask & mid_c1c2_mask] = 'OIL'
                    
                    logger.info(f"更新后的标签分布: {y.value_counts().to_dict()}")
            
            return y, valid_mask
        except Exception as e:
            logger.error(f"标签准备失败: {e}")
            return None, None
    
    def train_model(self, X, y):
        """训练模型"""
        try:
            logger.info(f"训练{ml_model_type}模型...")
            
            # 检查数据有效性
            if X is None or y is None or len(X) == 0 or len(y) == 0:
                logger.error("训练数据无效")
                return None
            
            # 检查标签是否有效
            unique_labels = y.unique()
            if len(unique_labels) < 2:
                logger.warning(f"标签类别不足，只有 {len(unique_labels)} 个类别，尝试继续训练")
                # 即使标签类别不足，也尝试训练模型
                return None
            
            # 改进训练/验证集划分策略：使用分组交叉验证按深度段分组
            # 这里我们先使用传统的划分方式，但后续可以扩展为分组交叉验证
            # 确保测试集大小至少等于类别数量
            test_size = 0.2
            min_test_size = len(unique_labels)
            if int(len(X) * test_size) < min_test_size:
                logger.warning(f"样本数量较少，调整测试集大小以确保覆盖所有类别")
                test_size = max(min_test_size / len(X), 0.1)
                logger.info(f"调整后的测试集大小: {test_size:.2f}")
                # 不使用stratify，因为样本数量不足
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=test_size, random_state=42
                )
            else:
                # 使用stratify确保类别分布
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=test_size, random_state=42, stratify=y
                )
            
            logger.info(f"Y HAS NaN: {y_train.isna().any()}, Y HAS INF: {np.isinf(X_train).any()}")
            
            # 特征选择
            from sklearn.feature_selection import SelectFromModel
            logger.info("进行特征选择...")
            selector = SelectFromModel(RandomForestClassifier(n_estimators=100), threshold='median')
            selector.fit(X_train, y_train)
            X_train_selected = selector.transform(X_train)
            X_test_selected = selector.transform(X_test)
            logger.info(f"特征选择前: {X_train.shape[1]} 个特征")
            logger.info(f"特征选择后: {X_train_selected.shape[1]} 个特征")
            
            # 类别不平衡处理
            logger.info("处理类别不平衡...")
            # 1. 加权损失：在随机森林中设置 class_weight='balanced'
            class_weight = 'balanced'
            
            # 模型调优：使用网格搜索
            logger.info("进行模型调优...")
            from sklearn.model_selection import GridSearchCV
            
            # 定义参数网格
            param_grid = {
                'n_estimators': [100, 200],
                'max_depth': [10, 20, None],
                'min_samples_split': [2, 5],
                'class_weight': ['balanced', None]
            }
            
            # 进行网格搜索
            grid = GridSearchCV(
                RandomForestClassifier(random_state=42, n_jobs=1), 
                param_grid, 
                cv=5, 
                scoring='f1_weighted',
                n_jobs=1
            )
            grid.fit(X_train_selected, y_train)
            
            logger.info(f"最佳参数: {grid.best_params_}")
            model = grid.best_estimator_
            
            # 集成多个模型
            logger.info("集成多个模型...")
            from sklearn.ensemble import VotingClassifier
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.neural_network import MLPClassifier
            
            # 创建多个基础模型
            rf_model = RandomForestClassifier(
                **grid.best_params_,
                random_state=42,
                n_jobs=-1
            )
            gbdt_model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            mlp_model = MLPClassifier(
                hidden_layer_sizes=(100, 50),
                max_iter=500,
                random_state=42
            )
            
            # 创建投票分类器
            ensemble_model = VotingClassifier(
                estimators=[
                    ('rf', rf_model),
                    ('gbdt', gbdt_model),
                    ('mlp', mlp_model)
                ],
                voting='hard',
                n_jobs=1
            )
            
            # 训练集成模型
            ensemble_model.fit(X_train_selected, y_train)
            
            # 评估模型
            y_train_pred = ensemble_model.predict(X_train_selected)
            y_test_pred = ensemble_model.predict(X_test_selected)
            
            train_accuracy = accuracy_score(y_train, y_train_pred)
            test_accuracy = accuracy_score(y_test, y_test_pred)
            
            logger.info(f"训练准确率: {train_accuracy:.3f}")
            logger.info(f"测试准确率: {test_accuracy:.3f}")
            
            # 计算其他指标
            precision = precision_score(y_test, y_test_pred, average='weighted', zero_division=0)
            recall = recall_score(y_test, y_test_pred, average='weighted', zero_division=0)
            f1 = f1_score(y_test, y_test_pred, average='weighted', zero_division=0)
            
            logger.info(f"精确率: {precision:.3f}")
            logger.info(f"召回率: {recall:.3f}")
            logger.info(f"F1得分: {f1:.3f}")
            
            # 计算油气层准确率
            hydrocarbon_labels = ['OIL', 'GAS']
            hydrocarbon_mask = y_test.isin(hydrocarbon_labels)
            if hydrocarbon_mask.any():
                hydrocarbon_accuracy = accuracy_score(
                    y_test[hydrocarbon_mask],
                    y_test_pred[hydrocarbon_mask]
                )
                logger.info(f"油气层准确率: {hydrocarbon_accuracy:.3f}")
            
            logger.info("训练完成")
            
            # 保存特征选择器
            self.feature_selector = selector
            
            self.model = ensemble_model
            return ensemble_model
        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def predict(self, X):
        """预测"""
        try:
            if self.model is None:
                logger.error("模型未训练")
                return None
            
            logger.info("PREDICTING...")
            
            # 使用特征选择器对输入特征进行转换
            if hasattr(self, 'feature_selector') and self.feature_selector is not None:
                X_selected = self.feature_selector.transform(X)
                logger.info(f"预测时特征选择: {X.shape[1]} → {X_selected.shape[1]} 个特征")
            else:
                X_selected = X
            
            predictions = self.model.predict(X_selected)
            
            logger.info(f"预测完成，共 {len(predictions)} 条记录")
            logger.info(f"预测结果分布: {pd.Series(predictions).value_counts().to_dict()}")
            
            return predictions
        except Exception as e:
            logger.error(f"预测失败: {e}")
            return None
    
    def explain(self, X, feature_names):
        """使用SHAP进行模型解释"""
        try:
            if not shap_available:
                logger.warning("SHAP库不可用，使用特征重要性替代")
                # 使用特征重要性
                if hasattr(self.model, 'feature_importances_'):
                    self.feature_importance = dict(zip(feature_names, self.model.feature_importances_))
                    logger.info(f"特征重要性: {self.feature_importance}")
                return None
            
            logger.info("使用SHAP进行模型解释...")
            
            # 创建SHAP解释器
            if ml_model_type == 'random_forest' or ml_model_type == 'gradient_boosting':
                explainer = shap.TreeExplainer(self.model)
            else:
                explainer = shap.KernelExplainer(self.model.predict, shap.kmeans(X, 10))
            
            # 计算SHAP值
            shap_values = explainer.shap_values(X)
            
            self.shap_values = shap_values
            
            logger.info("SHAP分析完成")
            
            return shap_values
        except Exception as e:
            logger.error(f"SHAP分析失败: {e}")
            return None
    
    def save_model_parameters(self, output_dir):
        """保存模型参数"""
        try:
            import pickle
            
            # 创建模板文件夹
            template_dir = os.path.join(output_dir, '模板')
            os.makedirs(template_dir, exist_ok=True)
            
            # 保存模型参数
            model_params = {
                'model_type': ml_model_type,
                'feature_importance': self.feature_importance,
                'shap_available': shap_available
            }
            
            # 如果模型存在，保存模型
            if self.model is not None:
                model_path = os.path.join(template_dir, 'ml_model.pkl')
                with open(model_path, 'wb') as f:
                    pickle.dump(self.model, f)
                model_params['model_path'] = model_path
                logger.info(f"机器学习模型保存至: {model_path}")
            
            # 保存参数到JSON文件
            params_path = os.path.join(template_dir, 'ml_parameters.json')
            with open(params_path, 'w', encoding='utf-8') as f:
                json.dump(model_params, f, ensure_ascii=False, indent=2)
            
            logger.info(f"机器学习参数保存至: {params_path}")
            return params_path
        except Exception as e:
            logger.error(f"保存模型参数失败: {e}")
            return None
    
    def run_interpretation(self):
        """运行机器学习解释"""
        try:
            logger.info("开始机器学习解释...")
            
            # 直接使用self.data，不创建副本
            #logger.info(f"初始self.data形状: {self.data.shape}")
            #logger.info(f"初始self.data列: {list(self.data.columns)}")
            
            # 准备特征和标签
            X, feature_names = self.prepare_features(self.data)
            y, valid_mask = self.prepare_labels(self.data)
            
            if X is None or y is None:
                logger.error("特征或标签准备失败")
                # 添加默认ml_prediction列
                if 'ml_prediction' not in self.data.columns:
                    self.data['ml_prediction'] = 'DRY'
                    logger.info("添加默认ml_prediction列")
                return False
            
            # 只使用有效数据训练模型
            X_valid = X[valid_mask]
            y_valid = y
            
            if len(X_valid) == 0:
                logger.error("没有有效的训练数据")
                # 添加默认ml_prediction列
                if 'ml_prediction' not in self.data.columns:
                    self.data['ml_prediction'] = 'DRY'
                    logger.info("添加默认ml_prediction列")
                return False
            
            # 训练模型
            model = self.train_model(X_valid, y_valid)
            
            if model is None:
                logger.error("模型训练失败")
                # 添加默认ml_prediction列
                if 'ml_prediction' not in self.data.columns:
                    self.data['ml_prediction'] = 'DRY'
                    logger.info("添加默认ml_prediction列")
                return False
            
            # 对所有数据进行预测
            predictions = self.predict(X)
            
            if predictions is None:
                logger.error("预测失败")
                # 添加默认ml_prediction列
                if 'ml_prediction' not in self.data.columns:
                    self.data['ml_prediction'] = 'DRY'
                    logger.info("添加默认ml_prediction列")
                return False
            
            # 添加预测结果到数据
            self.data['ml_prediction'] = predictions
            logger.info("添加ml_prediction列到self.data")
            
            # 应用过滤规则
            logger.info("应用过滤规则...")
            
            # 计算总烃
            if 'T15' in self.data.columns:
                total_hc = self.data['T15']
            else:
                gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
                available_gas_cols = [col for col in gas_cols if col in self.data.columns]
                if available_gas_cols:
                    total_hc = self.data[available_gas_cols].sum(axis=1)
                else:
                    total_hc = pd.Series([0] * len(self.data), index=self.data.index)
            
            # 过滤规则：总烃低于阈值且预测为油气层的，改为DRY
            hc_threshold = 0.01  # 降低总烃阈值，避免过度过滤
            oil_gas_mask = self.data['ml_prediction'].isin(['OIL', 'GAS'])
            low_hc_mask = total_hc < hc_threshold
            filter_mask = oil_gas_mask & low_hc_mask
            
            self.data.loc[filter_mask, 'ml_prediction'] = 'DRY'
            logger.info(f"过滤掉 {filter_mask.sum()} 个低总烃油气层预测")
            
            # SHAP分析
            shap_results = self.explain(X_valid, feature_names)
            
            self.results = self.data
            
            #logger.info(f"最终self.data形状: {self.data.shape}")
            #logger.info(f"最终self.data列: {list(self.data.columns)}")
            logger.info("机器学习解释完成")
            return True
        except Exception as e:
            logger.error(f"机器学习解释失败: {e}")
            import traceback
            traceback.print_exc()
            # 添加默认ml_prediction列
            if 'ml_prediction' not in self.data.columns:
                self.data['ml_prediction'] = 'DRY'
                logger.info("添加默认ml_prediction列")
            return False

# 深度学习解释模块
class DLInterpretationModule:
    """深度学习解释模块"""
    
    def __init__(self, data, data_mode, output_dir):
        self.data = data
        self.data_mode = data_mode
        self.output_dir = output_dir
        self.model = None
        self.results = None
    
    def prepare_features(self, df):
        """准备特征"""
        try:
            # 根据数据模式选择特征列
            if self.data_mode == 'FLAIR':
                feature_cols = FLAIR_COLUMNS
            else:
                feature_cols = GAS_COLUMNS
            
            # 检查特征列是否存在
            available_features = [col for col in feature_cols if col in df.columns]
            
            if not available_features:
                logger.error("没有可用的特征列")
                return None, None
            
            logger.info(f"使用特征列: {available_features}")
            
            # 创建特征
            X = df[available_features].copy()
            
            # 处理缺失值
            X = X.fillna(0)
            
            # 处理异常值：仅截断低于下限的值，保留高值，仅剔除物理上不可能的值
            for col in X.columns:
                Q1 = X[col].quantile(0.25)
                Q3 = X[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                
                # 对于物理上不可能为负的值（如气体含量、压力等），设置下限为0
                if col in ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'C7', 'C8', 'MCH', 'TL', 'BZ', 'ROP', 'T15']:
                    lower_bound = max(lower_bound, 0)
                
                # 仅截断低于下限的值，保留高值
                X[col] = X[col].clip(lower=lower_bound)
            
            # 特征工程增强
            # 1. 组分间的比值
            if 'C2' in df.columns and 'C3' in df.columns:
                X['C2C3'] = np.where(df['C3'] == 0, 0, df['C2'] / df['C3'])
            if 'C3' in df.columns and 'IC4' in df.columns and 'NC4' in df.columns:
                X['C3C4'] = np.where((df['IC4'] + df['NC4']) == 0, 0, df['C3'] / (df['IC4'] + df['NC4']))
            if 'IC4' in df.columns and 'NC4' in df.columns:
                X['IC4NC4'] = np.where(df['NC4'] == 0, 0, df['IC4'] / df['NC4'])
            
            # 2. 总烃相关特征
            if 'T15' in df.columns:
                # T15的滑动平均
                X['T15_rolling_mean'] = df['T15'].rolling(window=5, center=True, min_periods=1).mean()
                # T15梯度
                X['T15_gradient'] = df['T15'].diff()
                X['T15_gradient'] = X['T15_gradient'].fillna(0)
            
            # 3. 轻重组分比例
            if all(col in df.columns for col in ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']):
                light_hydrocarbons = df['C1'] + df['C2']
                heavy_hydrocarbons = df['C3'] + df['IC4'] + df['NC4'] + df['IC5'] + df['NC5']
                X['light_heavy_ratio'] = np.where(heavy_hydrocarbons == 0, 0, light_hydrocarbons / heavy_hydrocarbons)
            
            # 4. 其他衍生特征
            if 'C1' in df.columns and 'C2' in df.columns and 'C3' in df.columns:
                X['C1C2C3'] = np.where((df['C2'] + df['C3']) == 0, 0, df['C1'] / (df['C2'] + df['C3']))
            
            # 标准化 - 统一使用 StandardScaler 与 ML 模块保持一致
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 获取所有特征名称（包括新添加的特征）
            all_feature_names = list(X.columns)
            
            logger.info(f"增强后特征列: {all_feature_names}")
            
            return X_scaled, all_feature_names
        except Exception as e:
            logger.error(f"特征准备失败: {e}")
            return None, None
    
    def prepare_labels(self, df):
        """准备标签"""
        try:
            # 使用机器学习预测结果作为标签
            if 'ml_prediction' in df.columns:
                y = df['ml_prediction'].copy()
            elif 'ITP_traditional' in df.columns:
                y = df['ITP_traditional'].copy()
            else:
                logger.warning("没有可用的标签，创建模拟标签")
                y = pd.Series(['DRY'] * len(df), index=df.index)
            
            # 标准化标签
            y = y.apply(standardize_label)
            
            # 编码标签
            label_encoder = LabelEncoder()
            y_encoded = label_encoder.fit_transform(y)
            
            logger.info(f"标签分布: {y.value_counts().to_dict()}")
            logger.info(f"标签编码: {dict(zip(label_encoder.classes_, range(len(label_encoder.classes_))))}")
            
            return y_encoded, label_encoder
        except Exception as e:
            logger.error(f"标签准备失败: {e}")
            return None, None
    
    def train_model(self, X, y):
        """训练深度学习模型"""
        try:
            logger.info("正在使用深度学习模型进行预测...")
            
            # 检查数据有效性
            if X is None or y is None or len(X) == 0 or len(y) == 0:
                logger.error("训练数据无效")
                return None
            
            # 尝试使用Keras实现深度学习模型
            try:
                import tensorflow as tf
                from tensorflow.keras.models import Sequential, Model
                from tensorflow.keras.layers import Dense, Dropout, BatchNormalization, LSTM, Conv1D, MaxPooling1D, Flatten, Input
                from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
                from tensorflow.keras.utils import to_categorical
                
                logger.info("使用Keras实现深度学习模型...")
                
                # 获取类别数量
                num_classes = len(np.unique(y))
                
                # 转换标签为one-hot编码
                y_one_hot = to_categorical(y, num_classes)
                
                # 选择网络结构类型
                network_type = 'cnn'  # 可选: 'mlp', 'lstm', 'cnn'
                
                if network_type == 'mlp':
                    # 基础MLP网络
                    logger.info("使用MLP网络结构")
                    model = Sequential([
                        Dense(128, activation='relu', input_shape=(X.shape[1],)),
                        BatchNormalization(),
                        Dropout(0.3),
                        Dense(64, activation='relu'),
                        Dropout(0.3),
                        Dense(num_classes, activation='softmax')
                    ])
                elif network_type == 'lstm':
                    # LSTM网络处理序列特征
                    logger.info("使用LSTM网络结构")
                    # 重塑输入为序列形式 [samples, time_steps, features]
                    X_reshaped = X.reshape((X.shape[0], 1, X.shape[1]))
                    model = Sequential([
                        LSTM(128, return_sequences=True, input_shape=(1, X.shape[1])),
                        Dropout(0.3),
                        LSTM(64),
                        Dropout(0.3),
                        Dense(num_classes, activation='softmax')
                    ])
                elif network_type == 'cnn':
                    # CNN网络提取局部模式
                    logger.info("使用CNN网络结构")
                    # 重塑输入为适合CNN的形式 [samples, features, 1]
                    X_reshaped = X.reshape((X.shape[0], X.shape[1], 1))
                    model = Sequential([
                        Conv1D(64, 3, activation='relu', input_shape=(X.shape[1], 1)),
                        MaxPooling1D(2),
                        Conv1D(32, 3, activation='relu'),
                        MaxPooling1D(2),
                        Flatten(),
                        Dense(64, activation='relu'),
                        Dropout(0.3),
                        Dense(num_classes, activation='softmax')
                    ])
                
                # 编译模型
                model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
                
                # 创建早停回调
                early_stopping = EarlyStopping(
                    monitor='val_loss',
                    patience=10,
                    restore_best_weights=True
                )
                
                # 创建模板文件夹
                template_dir = os.path.join(self.output_dir, '模板')
                os.makedirs(template_dir, exist_ok=True)
                
                # 创建模型保存回调
                model_checkpoint_path = os.path.join(template_dir, f'dl_model_{network_type}_best.keras')
                model_checkpoint = ModelCheckpoint(
                    model_checkpoint_path,
                    monitor='val_accuracy',
                    save_best_only=True,
                    mode='max'
                )
                
                # 训练模型
                if network_type in ['lstm', 'cnn']:
                    # 使用重塑后的数据
                    history = model.fit(
                        X_reshaped, y_one_hot,
                        epochs=100,
                        batch_size=32,
                        validation_split=0.1,
                        callbacks=[early_stopping, model_checkpoint],
                        verbose=0
                    )
                else:
                    # 使用原始数据
                    history = model.fit(
                        X, y_one_hot,
                        epochs=100,
                        batch_size=32,
                        validation_split=0.1,
                        callbacks=[early_stopping, model_checkpoint],
                        verbose=0
                    )
                
                # 评估模型
                if network_type in ['lstm', 'cnn']:
                    train_loss, train_accuracy = model.evaluate(X_reshaped, y_one_hot, verbose=0)
                else:
                    train_loss, train_accuracy = model.evaluate(X, y_one_hot, verbose=0)
                
                logger.info(f"深度学习模型训练完成，训练准确率: {train_accuracy:.3f}")
                
                # 保存模型
                self.model = model
                self.model_path = model_checkpoint_path
                self.network_type = network_type
                logger.info(f"最佳模型保存至: {model_checkpoint_path}")
                
                return model
            except ImportError:
                logger.warning("TensorFlow/Keras不可用，使用scikit-learn MLP作为替代")
                # 如果Keras不可用，使用scikit-learn MLP
                model = MLPClassifier(
                    hidden_layer_sizes=(128, 64),
                    max_iter=500,
                    random_state=42,
                    early_stopping=True,
                    validation_fraction=0.1,
                    alpha=0.0001  # L2正则化，防止过拟合
                )
                
                # 训练模型
                model.fit(X, y)
                
                logger.info(f"深度学习模型训练完成，训练准确率: {model.score(X, y):.3f}")
                
                self.model = model
                return model
        except Exception as e:
            logger.error(f"深度学习模型训练失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def predict(self, X, label_encoder):
        """预测"""
        try:
            if self.model is None:
                logger.error("模型未训练")
                return None
            
            # 检查模型类型，处理Keras模型和scikit-learn MLP模型
            import tensorflow as tf
            if isinstance(self.model, tf.keras.Model):
                # Keras模型预测
                logger.info("使用Keras模型进行预测...")
                
                # 根据网络类型对输入数据进行重塑
                if hasattr(self, 'network_type'):
                    if self.network_type == 'lstm':
                        # 重塑输入为序列形式 [samples, time_steps, features]
                        X_reshaped = X.reshape((X.shape[0], 1, X.shape[1]))
                        predictions_prob = self.model.predict(X_reshaped, verbose=0)
                    elif self.network_type == 'cnn':
                        # 重塑输入为适合CNN的形式 [samples, features, 1]
                        X_reshaped = X.reshape((X.shape[0], X.shape[1], 1))
                        predictions_prob = self.model.predict(X_reshaped, verbose=0)
                    else:
                        # MLP网络使用原始数据
                        predictions_prob = self.model.predict(X, verbose=0)
                else:
                    # 默认使用原始数据
                    predictions_prob = self.model.predict(X, verbose=0)
                
                predictions_encoded = np.argmax(predictions_prob, axis=1)
            else:
                # scikit-learn MLP模型预测
                logger.info("使用scikit-learn MLP模型进行预测...")
                predictions_encoded = self.model.predict(X)
            
            # 解码标签
            predictions = label_encoder.inverse_transform(predictions_encoded)
            
            logger.info(f"深度学习预测完成，共 {len(predictions)} 条记录")
            logger.info(f"预测结果分布: {pd.Series(predictions).value_counts().to_dict()}")
            
            return predictions
        except ImportError:
            # 如果TensorFlow不可用，使用scikit-learn MLP模型预测
            logger.info("使用scikit-learn MLP模型进行预测...")
            if self.model is not None:
                predictions_encoded = self.model.predict(X)
                predictions = label_encoder.inverse_transform(predictions_encoded)
                logger.info(f"深度学习预测完成，共 {len(predictions)} 条记录")
                logger.info(f"预测结果分布: {pd.Series(predictions).value_counts().to_dict()}")
                return predictions
            else:
                logger.error("模型未训练")
                return None
        except Exception as e:
            logger.error(f"深度学习预测失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_model_parameters(self, output_dir):
        """保存模型参数"""
        try:
            import pickle
            
            # 创建模板文件夹
            template_dir = os.path.join(output_dir, '模板')
            os.makedirs(template_dir, exist_ok=True)
            
            # 保存模型参数
            model_params = {
                'model_type': 'mlp',
                'hidden_layer_sizes': (100, 50),
                'max_iter': 500,
                'random_state': 42
            }
            
            # 如果模型存在，保存模型
            if self.model is not None:
                model_path = os.path.join(template_dir, 'dl_model.pkl')
                with open(model_path, 'wb') as f:
                    pickle.dump(self.model, f)
                model_params['model_path'] = model_path
                logger.info(f"深度学习模型保存至: {model_path}")
            
            # 保存参数到JSON文件
            params_path = os.path.join(template_dir, 'dl_parameters.json')
            with open(params_path, 'w', encoding='utf-8') as f:
                json.dump(model_params, f, ensure_ascii=False, indent=2)
            
            logger.info(f"深度学习参数保存至: {params_path}")
            return params_path
        except Exception as e:
            logger.error(f"保存模型参数失败: {e}")
            return None
    
    def run_interpretation(self):
        """运行深度学习解释"""
        try:
            logger.info("开始深度学习解释...")
            
            # 直接使用self.data，不创建副本
            #logger.info(f"初始self.data形状: {self.data.shape}")
            #logger.info(f"初始self.data列: {list(self.data.columns)}")
            
            # 准备特征和标签
            X, feature_names = self.prepare_features(self.data)
            y, label_encoder = self.prepare_labels(self.data)
            
            if X is None or y is None:
                logger.error("特征或标签准备失败")
                # 添加默认dl_prediction列
                if 'dl_prediction' not in self.data.columns:
                    self.data['dl_prediction'] = 'DRY'
                    logger.info("添加默认dl_prediction列")
                return False
            
            # 训练模型
            model = self.train_model(X, y)
            
            if model is None:
                logger.error("模型训练失败")
                # 添加默认dl_prediction列
                if 'dl_prediction' not in self.data.columns:
                    self.data['dl_prediction'] = 'DRY'
                    logger.info("添加默认dl_prediction列")
                return False
            
            # 预测
            predictions = self.predict(X, label_encoder)
            
            if predictions is None:
                logger.error("预测失败")
                # 添加默认dl_prediction列
                if 'dl_prediction' not in self.data.columns:
                    self.data['dl_prediction'] = 'DRY'
                    logger.info("添加默认dl_prediction列")
                return False
            
            # 添加预测结果到数据
            self.data['dl_prediction'] = predictions
            logger.info("添加dl_prediction列到self.data")
            
            self.results = self.data
            
            #logger.info(f"最终self.data形状: {self.data.shape}")
            #logger.info(f"最终self.data列: {list(self.data.columns)}")
            logger.info("深度学习解释完成")
            return True
        except Exception as e:
            logger.error(f"深度学习解释失败: {e}")
            import traceback
            traceback.print_exc()
            # 添加默认dl_prediction列
            if 'dl_prediction' not in self.data.columns:
                self.data['dl_prediction'] = 'DRY'
                logger.info("添加默认dl_prediction列")
            return False

# 结果验证模块
class ValidationModule:
    """结果验证模块"""
    
    def __init__(self, data):
        self.data = data
        self.validation_results = None
    
    def validate_results(self):
        """验证解释结果"""
        try:
            logger.info("正在验证解释结果...")
            
            validation_results = {}
            
            # 验证传统解释结果
            if 'ITP_traditional' in self.data.columns:
                traditional_dist = self.data['ITP_traditional'].value_counts().to_dict()
                validation_results['traditional'] = {
                    'status': 'SUCCESS',
                    'distribution': traditional_dist
                }
                logger.info(f"传统解释结果验证通过: {traditional_dist}")
            
            # 验证机器学习解释结果
            if 'ml_prediction' in self.data.columns:
                ml_dist = self.data['ml_prediction'].value_counts().to_dict()
                validation_results['machine_learning'] = {
                    'status': 'SUCCESS',
                    'distribution': ml_dist
                }
                logger.info(f"机器学习解释结果验证通过: {ml_dist}")
            
            # 验证深度学习解释结果
            if 'dl_prediction' in self.data.columns:
                dl_dist = self.data['dl_prediction'].value_counts().to_dict()
                validation_results['deep_learning'] = {
                    'status': 'SUCCESS',
                    'distribution': dl_dist
                }
                logger.info(f"深度学习解释结果验证通过: {dl_dist}")
            
            # 与试油结果对比
            if 'test_results' in self.data.columns and self.data['test_results'].notna().any():
                # 创建数据副本，避免SettingWithCopyWarning
                test_data = self.data[self.data['test_results'].notna()].copy()
                
                logger.info(f"试油数据行数: {len(test_data)}")
                logger.info(f"试油数据前5行: {test_data[['MD', 'test_results']].head().to_dict('records')}")
                
                # 标准化test_results列的标签
                test_data['test_results'] = test_data['test_results'].apply(standardize_label)
                logger.info(f"标准化后试油结果分布: {test_data['test_results'].value_counts().to_dict()}")
                
                for method in ['ITP_traditional', 'ml_prediction', 'dl_prediction']:
                    if method in test_data.columns:
                        # 标准化解释结果的标签
                        test_data[method] = test_data[method].apply(standardize_label)
                        logger.info(f"{method} 解释结果分布: {test_data[method].value_counts().to_dict()}")
                        
                        # 计算准确率
                        correct_matches = (test_data[method] == test_data['test_results']).sum()
                        total_matches = len(test_data)
                        accuracy = correct_matches / total_matches if total_matches > 0 else 0
                        
                        validation_results[f'{method}_accuracy'] = {
                            'status': 'SUCCESS',
                            'accuracy': accuracy,
                            'correct_matches': correct_matches,
                            'total_matches': total_matches
                        }
                        logger.info(f"{method} 与试油结果对比: 准确率 {accuracy:.3f} ({correct_matches}/{total_matches})")
                        
                        # 打印前10行的对比结果，用于调试
                        #logger.info(f"前10行 {method} 与试油结果对比:")
                        logger.info(test_data[[method, 'test_results']].head(10).to_dict('records'))
            else:
                logger.warning("没有有效的试油数据，无法计算准确率")
                # 检查test_results列的情况
                if 'test_results' in self.data.columns:
                    logger.info(f"test_results列存在，但是所有值都是NaN: {self.data['test_results'].isna().all()}")
                    logger.info(f"test_results列值分布: {self.data['test_results'].value_counts(dropna=False).to_dict()}")
                else:
                    logger.info("test_results列不存在")
            self.validation_results = validation_results
            
            # 执行错误分析
            error_analysis_results = self.error_analysis()
            if error_analysis_results:
                validation_results['error_analysis'] = error_analysis_results
            
            logger.info("结果验证完成")
            return validation_results
        except Exception as e:
            logger.error(f"结果验证失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def error_analysis(self):
        """错误分析模块"""
        try:
            logger.info("开始错误分析...")
            
            error_analysis_results = {}
            
            # 检查是否有试油数据用于对比
            if 'test_results' not in self.data.columns or self.data['test_results'].isna().all():
                logger.warning("没有有效的试油数据，无法进行错误分析")
                return None
            
            # 创建数据副本，避免SettingWithCopyWarning
            test_data = self.data[self.data['test_results'].notna()].copy()
            
            # 标准化标签
            test_data['test_results'] = test_data['test_results'].apply(standardize_label)
            
            # 对每种解释方法进行错误分析
            for method in ['ITP_traditional', 'ml_prediction', 'dl_prediction']:
                if method in test_data.columns:
                    # 标准化解释结果的标签
                    test_data[method] = test_data[method].apply(standardize_label)
                    
                    # 找出误分类的样本
                    error_mask = test_data[method] != test_data['test_results']
                    error_samples = test_data[error_mask].copy()
                    correct_samples = test_data[~error_mask].copy()
                    
                    method_error_results = {
                        'total_samples': len(test_data),
                        'error_count': len(error_samples),
                        'error_rate': len(error_samples) / len(test_data) if len(test_data) > 0 else 0
                    }
                    
                    # 1. 深度段错误分析
                    if 'MD' in error_samples.columns:
                        # 按深度段分组（每100米）
                        error_samples['depth_segment'] = (error_samples['MD'] // 100) * 100
                        depth_error_distribution = error_samples['depth_segment'].value_counts().to_dict()
                        method_error_results['depth_error_distribution'] = depth_error_distribution
                        
                        if depth_error_distribution:
                            most_error_depth = max(depth_error_distribution, key=depth_error_distribution.get)
                            method_error_results['most_error_depth'] = most_error_depth
                            logger.info(f"{method} 错误最多的深度段: {most_error_depth}-{most_error_depth+100}m，错误数: {depth_error_distribution[most_error_depth]}")
                    
                    # 2. 误分类类型分析
                    error_types = error_samples.groupby(['test_results', method]).size().to_dict()
                    method_error_results['error_types'] = error_types
                    
                    # 3. 特征统计差异分析
                    if len(error_samples) > 0 and len(correct_samples) > 0:
                        # 选择重要特征进行分析
                        important_features = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'T15', 'C1C2', 'C1C3']
                        available_features = [f for f in important_features if f in test_data.columns]
                        
                        feature_diff = {}
                        for feature in available_features:
                            error_mean = error_samples[feature].mean()
                            correct_mean = correct_samples[feature].mean()
                            diff_percentage = ((error_mean - correct_mean) / correct_mean * 100) if correct_mean != 0 else 0
                            feature_diff[feature] = {
                                'error_mean': error_mean,
                                'correct_mean': correct_mean,
                                'diff_percentage': diff_percentage
                            }
                        method_error_results['feature_statistics_diff'] = feature_diff
                    
                    # 4. 保存错误样本详细信息
                    if len(error_samples) > 0:
                        # 保存前20个错误样本
                        error_sample_details = error_samples[['MD', 'test_results', method] + available_features].head(20).to_dict('records')
                        method_error_results['error_sample_details'] = error_sample_details
                    
                    error_analysis_results[method] = method_error_results
                    logger.info(f"{method} 错误分析完成，错误率: {method_error_results['error_rate']:.3f}")
            
            # 5. 全局错误分析
            # 修复索引不匹配问题，使用逐行比较
            error_mask = []
            for idx, row in test_data.iterrows():
                # 检查每行的解释结果是否与试油结果不同
                row_error = False
                for method in ['ITP_traditional', 'ml_prediction', 'dl_prediction']:
                    if method in test_data.columns:
                        if row[method] != row['test_results']:
                            row_error = True
                            break
                error_mask.append(row_error)
            
            all_error_samples = test_data[error_mask]
            error_analysis_results['global'] = {
                'total_error_samples': len(all_error_samples),
                'error_sample_percentage': len(all_error_samples) / len(test_data) if len(test_data) > 0 else 0
            }
            
            logger.info("错误分析完成")
            return error_analysis_results
        except Exception as e:
            logger.error(f"错误分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None

# 可视化模块
class VisualizationModule:
    """可视化模块"""
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    def plot_gas_curves(self, df, well_name, data_mode='REGULAR'):
        """绘制气测曲线"""
        try:
            logger.info("绘制气测曲线...")
            
            # 创建5列布局：气体曲线、传统解释方法、综合解释、试油结果、数据质量
            fig, axes = plt.subplots(1, 5, figsize=(25, 10), sharey=True)
            
            # 设置matplotlib字体，确保汉字正确显示
            plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体显示中文
            plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
            
            # 第一道：气体曲线
            # 根据数据模式选择要绘制的气体组分
            if data_mode == 'FLAIR':
                gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5', 'C6', 'C7', 'C8']
                title = 'Gas Curves (C1-C8)'
            else:
                gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
                title = 'Gas Curves (C1-C5)'
            
            for col in gas_cols:
                if col in df.columns:
                    axes[0].plot(df[col], df['MD'], label=col)
            
            # 设置对数刻度
            axes[0].set_xscale('log')
            axes[0].set_xlim(10, 100000)
            axes[0].set_xlabel('Gas Content (ppm)')
            axes[0].legend()
            axes[0].set_title(title)
            axes[0].grid(True)
            
            # 对深度轴标注刻度数据
            if len(df) > 0:
                # 计算合适的刻度间隔
                depth_min = df['MD'].min()
                depth_max = df['MD'].max()
                depth_range = depth_max - depth_min
                
                # 根据深度范围确定刻度间隔
                if depth_range > 1000:
                    interval = 200
                elif depth_range > 500:
                    interval = 100
                elif depth_range > 200:
                    interval = 50
                elif depth_range > 100:
                    interval = 20
                else:
                    interval = 10
                
                # 设置刻度
                ticks = np.arange(np.floor(depth_min/interval)*interval, depth_max + interval, interval)
                
                # 为所有子图设置深度范围
                for ax in axes:
                    # 反转y轴，使深度向下增加
                    ax.invert_yaxis()
                    # 确保所有子图使用相同的深度范围
                    ax.set_ylim(depth_max, depth_min)
                
                # 为其他道设置深度刻度，只显示刻度线不显示刻度数
                for i in range(1, len(axes)):
                    axes[i].set_yticks(ticks)
                    axes[i].set_yticklabels([])  # 不显示刻度数
                    axes[i].set_ylabel('')
                    axes[i].tick_params(axis='y', which='both', labelsize=1, length=4, width=1, direction='inout')
                    axes[i].yaxis.set_visible(True)
                    axes[i].yaxis.set_ticks_position('left')
                    # 确保刻度线显示
                    axes[i].yaxis.set_tick_params(which='both', direction='inout', pad=10)
                
                # 为第一道设置深度刻度，保留整数，显示刻度线和刻度数
                # 确保ticks不为空
                if len(ticks) > 0:
                    # 确保刻度标签正确设置
                    axes[0].set_yticks(ticks)
                    axes[0].set_yticklabels([f'{tick:.0f}' for tick in ticks])
                    axes[0].set_ylabel('深度 (m)', fontsize=10)  # 只在第一道显示y轴标签
                    
                    # 确保刻度参数正确设置
                    axes[0].tick_params(axis='y', which='both', labelsize=10, labelcolor='black', length=6, width=1.5, direction='inout')
                    axes[0].yaxis.set_visible(True)
                    axes[0].yaxis.set_ticks_position('left')
                    
                    # 确保刻度标签不被遮挡
                    axes[0].yaxis.set_tick_params(which='both', pad=15)
                    
                    # 调整布局，为标签留出空间
                    plt.subplots_adjust(left=0.15)
                
            
            # 第二道：传统解释方法（分开绘制）
            traditional_methods = ['ITP_pixler', 'ITP_triangle', 'ITP_3h', 'ITP_star']
            method_names = ['Pixler', 'Triangle', '3H', 'STAR']
            colors = {'OIL': 'green', 'GAS': 'red', 'DRY': 'gray', 'WATER': 'blue'}
            
            # 优化绘制：合并连续相同标签的深度段
            def plot_interpretation(ax, df, col, x_start, x_end):
                if col not in df.columns:
                    return
                
                # 找到标签变化的位置
                label_changes = df[col].ne(df[col].shift()).cumsum()
                # 按标签变化分组
                groups = df.groupby(label_changes)
                
                # 收集所有区间的信息
                segments = []
                for _, group in groups:
                    if len(group) < 1:
                        continue
                    md1 = group['MD'].iloc[0]
                    md2 = group['MD'].iloc[-1]
                    label = group[col].iloc[0]
                    color = colors.get(label, 'gray')
                    segments.append((md1, md2, color))
                
                # 缩小宽度，使用0.8的宽度
                width = x_end - x_start
                adjusted_start = x_start + width * 0.1
                adjusted_end = x_end - width * 0.1
                
                # 批量绘制所有区间
                for md1, md2, color in segments:
                    ax.fill_betweenx([md1, md2], adjusted_start, adjusted_end, color=color, alpha=0.5)
            
            for i, (col, name) in enumerate(zip(traditional_methods, method_names)):
                plot_interpretation(axes[1], df, col, i, i+1)
            
            axes[1].set_xlabel('Traditional Methods')
            axes[1].set_title('Traditional Interpretation Methods')
            axes[1].set_xticks([0.5, 1.5, 2.5, 3.5])
            axes[1].set_xticklabels(method_names)
            
            # 第三道：综合解释结果（传统、机器学习、深度学习）
            interpretation_cols = ['ITP_traditional', 'ml_prediction', 'dl_prediction']
            interp_names = ['Traditional', 'ML', 'DL']
            
            for i, (col, name) in enumerate(zip(interpretation_cols, interp_names)):
                plot_interpretation(axes[2], df, col, i, i+1)
            
            axes[2].set_xlabel('Interpretation Method')
            axes[2].set_title('Integrated Interpretation Results')
            axes[2].set_xticks([0.5, 1.5, 2.5])
            axes[2].set_xticklabels(interp_names)
            
            # 第四道：试油结果
            if 'test_results' in df.columns:
                # 过滤掉NaN值
                test_data = df[df['test_results'].notna()]
                if not test_data.empty:
                    # 找到标签变化的位置
                    label_changes = test_data['test_results'].ne(test_data['test_results'].shift()).cumsum()
                    # 按标签变化分组
                    groups = test_data.groupby(label_changes)
                    
                    # 批量处理：先收集所有需要绘制的段，然后一次性绘制
                    oil_water_segments = []
                    regular_segments = []
                    
                    for _, group in groups:
                        if len(group) < 1:
                            continue
                        md1 = group['MD'].iloc[0]
                        md2 = group['MD'].iloc[-1]
                        result = group['test_results'].iloc[0]
                        
                        # 缩减宽度为原宽度的一半（0.4的宽度）
                        adjusted_start = 0.3
                        adjusted_end = 0.5
                        
                        # 特殊处理油水同层
                        if result.upper() == 'OIL-WATER':
                            oil_water_segments.append((md1, md2, adjusted_start, adjusted_end))
                        else:
                            color = colors.get(result.upper(), 'gray')
                            regular_segments.append((md1, md2, adjusted_start, adjusted_end, color))
                    
                    # 批量绘制油水同层
                    for md1, md2, start, end in oil_water_segments:
                        axes[3].fill_betweenx([md1, md2], start, (start + end) / 2, color='green', alpha=0.5)
                        axes[3].fill_betweenx([md1, md2], (start + end) / 2, end, color='blue', alpha=0.5)
                    
                    # 批量绘制常规层段
                    for md1, md2, start, end, color in regular_segments:
                        axes[3].fill_betweenx([md1, md2], start, end, color=color, alpha=0.5)
                
                axes[3].set_xlabel('Test Results')
                axes[3].set_title('Test Results')
                # 设置试油道x轴刻度只保留一位小数
                axes[3].set_xticks([0.3, 0.4, 0.5])
                axes[3].set_xticklabels(['0.3', '0.4', '0.5'])
            
            # 第五道：数据质量
            axes[4].set_xlabel('Data Quality')
            axes[4].set_title('Data Quality')
            # 设置质量道x轴刻度只保留一位小数
            axes[4].set_xticks([0.3, 0.4, 0.5])
            axes[4].set_xticklabels(['0.3', '0.4', '0.5'])
            
            # 绘制数据质量指标，例如总烃含量作为质量指标
            if 'T15' in df.columns:
                # 归一化总烃值用于可视化
                t15_min = df['T15'].min()
                t15_max = df['T15'].max()
                if t15_max > t15_min:
                    normalized_t15 = (df['T15'] - t15_min) / (t15_max - t15_min)
                    
                    # 向量化绘制：使用fill_betweenx批量绘制
                    md = df['MD'].values
                    quality = normalized_t15.values
                    
                    # 收集所有深度段的信息
                    segments = []
                    colors = []
                    for i in range(len(md)-1):
                        segments.append((md[i], md[i+1]))
                        colors.append(plt.cm.Greens(quality[i]))
                    
                    # 批量绘制所有深度段
                    for (md1, md2), color in zip(segments, colors):
                        axes[4].fill_betweenx([md1, md2], 0.3, 0.5, color=color, alpha=0.7)
                else:
                    # 如果总烃值没有变化，使用默认颜色
                    axes[4].fill_betweenx([df['MD'].min(), df['MD'].max()], 0.3, 0.5, color='gray', alpha=0.5)
            else:
                # 如果没有总烃数据，使用默认颜色
                axes[4].fill_betweenx([df['MD'].min(), df['MD'].max()], 0.3, 0.5, color='gray', alpha=0.5)
            
            # 添加全图标题
            plt.suptitle(f'{well_name} - 气测曲线图', fontsize=16, fontweight='bold')
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])  # 调整布局，为标题留出空间
            
            output_path = os.path.join(self.output_dir, f'{well_name}_gas_curves.png')
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"气测曲线保存至: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"绘制气测曲线失败: {e}")
            return None
    
    def plot_test_layers(self, df, well_name, shap_values=None, feature_names=None):
        """绘制试油层段SHAP贡献分析图版"""
        try:
            logger.info("绘制试油层段SHAP贡献分析图版...")
            
            # 检查是否有试油结果
            if 'test_results' not in df.columns or df['test_results'].isna().all():
                logger.warning("没有试油结果数据，跳过试油层段分析")
                return None
            
            # 获取试油层段
            test_layers = []
            current_result = None
            start_depth = None
            
            for i, row in df.iterrows():
                result = row['test_results']
                depth = row['MD']
                
                if pd.notna(result):
                    if current_result is None:
                        current_result = result
                        start_depth = depth
                    elif result != current_result:
                        # 保存当前层段
                        test_layers.append({
                            'start_depth': start_depth,
                            'end_depth': depth,
                            'result': current_result
                        })
                        current_result = result
                        start_depth = depth
            
            # 保存最后一个层段
            if current_result is not None and start_depth is not None:
                test_layers.append({
                    'start_depth': start_depth,
                    'end_depth': df['MD'].iloc[-1],
                    'result': current_result
                })
            
            logger.info(f"识别到 {len(test_layers)} 个试油层段")
            
            # 为每个试油层段创建SHAP分析图
            for layer in test_layers:
                start_depth = layer['start_depth']
                end_depth = layer['end_depth']
                result = layer['result']
                
                # 获取层段数据
                layer_mask = (df['MD'] >= start_depth) & (df['MD'] <= end_depth)
                layer_data = df[layer_mask]
                
                if len(layer_data) == 0:
                    continue
                
                # 创建3x2子图
                fig, axes = plt.subplots(3, 2, figsize=(12, 15))
                axes = axes.flatten()
                
                # 使用真实的SHAP值（如果提供）
                if shap_values is not None and feature_names is not None:
                    logger.info("使用真实的SHAP值进行分析")
                    
                    # 计算每个特征的平均绝对SHAP值（作为贡献大小的指标）
                    feature_contributions = {}
                    for i, feature in enumerate(feature_names):
                        if feature in layer_data.columns:
                            # 检查SHAP值的形状
                            if isinstance(shap_values, list):
                                # 分类模型的SHAP值是列表
                                if len(shap_values) > 0:
                                    # 对于分类模型，使用第一个类别的SHAP值或平均SHAP值
                                    if isinstance(shap_values[0], np.ndarray):
                                        # 计算平均绝对SHAP值
                                        avg_shap = np.mean(np.abs(shap_values[0][:, i]))
                                        feature_contributions[feature] = avg_shap
                            elif isinstance(shap_values, np.ndarray):
                                # 回归模型的SHAP值是数组
                                if shap_values.shape[1] > i:
                                    avg_shap = np.mean(np.abs(shap_values[:, i]))
                                    feature_contributions[feature] = avg_shap
                else:
                    logger.warning("没有提供SHAP值，跳过SHAP分析")
                    # 不使用模拟数据，直接跳过SHAP分析
                    # 可以使用其他方式来可视化试油层段，例如显示特征值的分布
                    feature_contributions = None
                
                # 按贡献大小排序特征
                if feature_contributions:
                    sorted_features = sorted(feature_contributions.items(), key=lambda x: x[1], reverse=True)
                    sorted_feature_names = [feature for feature, _ in sorted_features][:6]  # 只取前6个贡献最大的特征
                    
                    # 按照排序后的顺序绘制SHAP图
                    for i, col in enumerate(sorted_feature_names):
                        if col in layer_data.columns and i < len(axes):
                            # 获取该特征的SHAP值
                            if shap_values is not None and feature_names is not None and col in feature_names:
                                # 使用真实的SHAP值
                                feature_idx = feature_names.index(col)
                                if isinstance(shap_values, list):
                                    # 分类模型的SHAP值
                                    if len(shap_values) > 0 and isinstance(shap_values[0], np.ndarray):
                                        # 找到层段在原始数据中的索引
                                        layer_indices = layer_data.index.tolist()
                                        # 确保索引不超出范围
                                        valid_indices = [idx for idx in layer_indices if idx < shap_values[0].shape[0]]
                                        if valid_indices:
                                            # 使用第一个类别的SHAP值
                                            feature_shap = shap_values[0][valid_indices, feature_idx]
                                            # 确保SHAP值的长度与层段数据长度匹配
                                            if len(feature_shap) == len(layer_data.loc[valid_indices]):
                                                axes[i].plot(feature_shap, layer_data.loc[valid_indices, 'MD'], 'b-', linewidth=1)
                                                axes[i].axvline(x=0, color='red', linestyle='--', alpha=0.5)
                                                axes[i].set_xlabel(f'SHAP Value ({col})')
                                                axes[i].set_ylabel('Depth (m)')
                                                axes[i].set_title(f'{col} Contribution')
                                                axes[i].invert_yaxis()
                                                axes[i].grid(True, alpha=0.3)
                else:
                    # 没有SHAP值时，绘制特征值的分布
                    gas_columns = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
                    if 'C6' in df.columns:
                        gas_columns.extend(['C6', 'C7', 'C8', 'MCH', 'TL', 'BZ'])
                    
                    # 选择前6个可用的特征
                    available_features = [col for col in gas_columns if col in layer_data.columns][:6]
                    
                    for i, col in enumerate(available_features):
                        if i < len(axes):
                            # 绘制特征值随深度的变化
                            axes[i].plot(layer_data[col], layer_data['MD'], 'b-', linewidth=1)
                            axes[i].set_xlabel(f'{col} Value')
                            axes[i].set_ylabel('Depth (m)')
                            axes[i].set_title(f'{col} Distribution')
                            axes[i].invert_yaxis()
                            axes[i].grid(True, alpha=0.3)
                
                # 根据是否有SHAP值设置不同的标题
                if feature_contributions:
                    plt.suptitle(f'{well_name} Test Layer {start_depth:.1f}-{end_depth:.1f}m ({result}) - SHAP Analysis', 
                                fontsize=14, fontweight='bold')
                else:
                    plt.suptitle(f'{well_name} Test Layer {start_depth:.1f}-{end_depth:.1f}m ({result}) - Feature Distribution', 
                                fontsize=14, fontweight='bold')
                plt.tight_layout()
                
                # 保存图像
                output_path = os.path.join(self.output_dir, 'test_layers', 
                                          f'{well_name}_test_layer_{start_depth:.1f}_{end_depth:.1f}_{result}_shap.png')
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
                plt.close()
                
                logger.info(f"试油层段SHAP分析图保存至: {output_path}")
            
            return True
        except Exception as e:
            logger.error(f"绘制试油层段SHAP分析图版失败: {e}")
            import traceback
            traceback.print_exc()
            return None

# 完整工作流
class CompleteWorkflow:
    """完整工作流类"""
    
    def __init__(self, rawdata_path, testdata_path, well_name='Unknown Well', config_path=None):
        self.rawdata_path = rawdata_path
        self.testdata_path = testdata_path
        self.well_name = well_name
        self.config_path = config_path
        self.output_dir = os.path.join('output', well_name)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 初始化各模块
        self.data_loader = DataLoader(rawdata_path, testdata_path)
        self.qc_module = None
        self.traditional_interp = None
        self.ml_interp = None
        self.dl_interp = None
        self.validation_module = None
        self.visualization_module = VisualizationModule(self.output_dir)
        
        # 结果存储
        self.data = None
        self.data_mode = None
        self.qc_report = None
        self.traditional_results = None
        self.ml_results = None
        self.dl_results = None
        self.validation_results = None
        self.improvement_suggestions = []
        self.accuracy_results = None
    
    def run_complete_workflow(self):
        """运行完整工作流"""
        try:
            logger.info("开始完整工作流")
            logger.info(f"数据模式检测: 将自动根据数据内容选择FLAIR或常规模式")
            
            # Step 1: 数据加载
            logger.info("Step 1: 数据加载")
            self.data = self.data_loader.load_data()
            
            if self.data is None:
                logger.error("数据加载失败")
                return None
            
            # 获取数据模式
            self.data_mode = self.data_loader.data_mode
            logger.info(f"数据模式: {self.data_mode}")
            
            # Step 2: 数据质量检查
            logger.info("Step 2: 数据质量检查")
            self.qc_module = QualityControlModule(self.data, self.data_mode)
            self.qc_report = self.qc_module.run_qc()
            
            # Step 3: 传统解释
            logger.info("Step 3: 传统解释")
            logger.info(f"传统解释前self.data形状: {self.data.shape}")
            logger.info(f"传统解释前self.data列: {list(self.data.columns)}")
            self.traditional_interp = TraditionalInterpretationModule(self.data, self.data_mode, self.output_dir, self.config_path)
            traditional_success = self.traditional_interp.run_interpretation(self.well_name)
            if traditional_success:
                logger.info("传统解释成功完成")
            else:
                logger.warning("传统解释执行过程中出现问题")
            # 传统解释已经直接修改了self.data
            #logger.info(f"传统解释后self.data形状: {self.data.shape}")
            #logger.info(f"传统解释后self.data列: {list(self.data.columns)}")
            # 检查是否包含解释列
            interpretation_cols = ['ITP_pixler', 'ITP_triangle', 'ITP_3h', 'ITP_star', 'ITP_traditional']
            for col in interpretation_cols:
                if col in self.data.columns:
                    logger.info(f"self.data 包含列 {col}")
                else:
                    logger.warning(f"self.data 不包含列 {col}")
            
            # Step 4: 机器学习解释
            logger.info("Step 4: 机器学习解释")
            #logger.info(f"机器学习解释前self.data形状: {self.data.shape}")
            #logger.info(f"机器学习解释前self.data列: {list(self.data.columns)}")
            self.ml_interp = MLInterpretationModule(self.data, self.data_mode, self.output_dir)
            ml_success = self.ml_interp.run_interpretation()
            if ml_success:
                logger.info("机器学习解释成功完成")
            else:
                logger.warning("机器学习解释执行过程中出现问题")
            
            # 机器学习解释已经直接修改了self.data
            #logger.info(f"机器学习解释后self.data形状: {self.data.shape}")
            #logger.info(f"机器学习解释后self.data列: {list(self.data.columns)}")
            # 检查是否包含ml_prediction列
            if 'ml_prediction' in self.data.columns:
                logger.info("self.data 包含列 ml_prediction")
            else:
                logger.warning("self.data 不包含列 ml_prediction，添加默认值")
                self.data['ml_prediction'] = 'DRY'
            
            # Step 5: 深度学习解释
            logger.info("Step 5: 深度学习解释")
            #logger.info(f"深度学习解释前self.data形状: {self.data.shape}")
            #logger.info(f"深度学习解释前self.data列: {list(self.data.columns)}")
            self.dl_interp = DLInterpretationModule(self.data, self.data_mode, self.output_dir)
            dl_success = self.dl_interp.run_interpretation()
            if dl_success:
                logger.info("深度学习解释成功完成")
            else:
                logger.warning("深度学习解释执行过程中出现问题")
            
            # 深度学习解释已经直接修改了self.data
            #logger.info(f"深度学习解释后self.data形状: {self.data.shape}")
            #logger.info(f"深度学习解释后self.data列: {list(self.data.columns)}")
            # 检查是否包含dl_prediction列
            if 'dl_prediction' in self.data.columns:
                logger.info("self.data 包含列 dl_prediction")
            else:
                logger.warning("self.data 不包含列 dl_prediction，添加默认值")
                self.data['dl_prediction'] = 'DRY'
            
            # Step 6: 结果验证
            logger.info("Step 6: 结果验证")
            self.validation_module = ValidationModule(self.data)
            self.validation_results = self.validation_module.validate_results()
            
            # Step 7: 计算准确率
            logger.info("Step 7: 计算准确率")
            self.accuracy_results = self.calculate_accuracy()
            
            # Step 8: 生成改进建议
            logger.info("Step 8: 生成改进建议")
            self.generate_improvement_suggestions()
            
            # Step 9: 可视化
            logger.info("Step 9: 可视化")
            self.visualization_module.plot_gas_curves(self.data, self.well_name, self.data_mode)
            
            # Step 10: 绘制试油层段SHAP分析图
            logger.info("Step 10: 绘制试油层段SHAP分析图")
            # 传递SHAP值和特征名称（如果有的话）
            shap_values = None
            feature_names = None
            if hasattr(self.ml_interp, 'shap_values') and self.ml_interp.shap_values is not None:
                shap_values = self.ml_interp.shap_values
            if hasattr(self.ml_interp, 'feature_importance') and self.ml_interp.feature_importance is not None:
                feature_names = list(self.ml_interp.feature_importance.keys())
            self.visualization_module.plot_test_layers(self.data, self.well_name, shap_values, feature_names)
            
            # Step 11: 生成报告
            logger.info("Step 11: 生成报告")
            report_file = self.generate_report()
            
            # Step 12: 保存模型参数和解释知识
            logger.info("Step 12: 保存模型参数和解释知识")
            # 保存机器学习参数
            if self.ml_interp is not None:
                self.ml_interp.save_model_parameters(self.output_dir)
            # 保存深度学习参数
            if self.dl_interp is not None:
                self.dl_interp.save_model_parameters(self.output_dir)
            # 保存解释油气水层知识
            self.save_interpretation_knowledge(self.output_dir)
            
            logger.info("完整工作流运行完成")
            
            # 确保ml_prediction和dl_prediction列存在
            if 'ml_prediction' not in self.data.columns:
                logger.warning("ml_prediction列不存在，添加默认值")
                self.data['ml_prediction'] = 'DRY'
            if 'dl_prediction' not in self.data.columns:
                logger.warning("dl_prediction列不存在，添加默认值")
                self.data['dl_prediction'] = 'DRY'
            
            # 保存最终结果到文件
            final_output_path = os.path.join(self.output_dir, 'final_results.csv')
            self.data.to_csv(final_output_path, index=False)
            logger.info(f"最终结果保存至: {final_output_path}")
            
            # 返回结果
            return {
                'well_name': self.well_name,
                'data_mode': self.data_mode,
                'rawdata_path': self.rawdata_path,
                'qc_report': self.qc_report,
                'traditional_results': self.traditional_results,
                'ml_results': self.ml_results,
                'dl_results': self.dl_results,
                'validation_results': self.validation_results,
                'accuracy_results': self.accuracy_results,
                'improvement_suggestions': self.improvement_suggestions,
                'visualization': self.visualization_module,
                'report_file': report_file,
                'final_output_path': final_output_path
            }
        except Exception as e:
            logger.error(f"完整工作流运行失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def calculate_accuracy(self):
        """计算准确率"""
        try:
            accuracy_results = {}
            
            if self.validation_results is None:
                return None
            
            # 计算各方法的准确率
            method_names = ['ITP_traditional', 'ml_prediction', 'dl_prediction']
            accuracies = []
            
            for method in method_names:
                accuracy_key = f'{method}_accuracy'
                if accuracy_key in self.validation_results:
                    accuracy_results[method] = self.validation_results[accuracy_key]
                    accuracies.append(self.validation_results[accuracy_key]['accuracy'])
            
            # 计算平均准确率
            if accuracies:
                accuracy_results['average_accuracy'] = np.mean(accuracies)
            
            return accuracy_results
        except Exception as e:
            logger.error(f"计算准确率失败: {e}")
            return None
    
    def generate_improvement_suggestions(self):
        """生成改进建议"""
        try:
            # 基于QC报告生成建议
            if self.qc_report:
                missing_columns = self.qc_report.get('missing_values', {})
                for col, count in missing_columns.items():
                    if count > 0:
                        self.improvement_suggestions.append(f"列 '{col}' 存在 {count} 个缺失值，建议进行数据插补或删除")
                
                outliers = self.qc_report.get('outliers', {})
                for col, count in outliers.items():
                    if count > 0:
                        self.improvement_suggestions.append(f"列 '{col}' 存在 {count} 个异常值，建议检查数据质量")
            
            # 基于准确率结果生成建议
            if self.accuracy_results:
                for method_name, res in self.accuracy_results.items():
                    if method_name != 'average_accuracy' and 'accuracy' in res:
                        if res['accuracy'] < 0.7:
                            self.improvement_suggestions.append(f"{method_name} 方法准确率较低 ({res['accuracy']:.3f})，建议优化模型参数或增加训练数据")
            
            # 基于数据模式生成建议
            if self.data_mode == 'REGULAR':
                self.improvement_suggestions.append("当前使用常规数据模式，如需更详细的分析，建议采集包含C6等组分的FLAIR数据")
            
            logger.info(f"生成了 {len(self.improvement_suggestions)} 条改进建议")
        except Exception as e:
            logger.error(f"生成改进建议失败: {e}")
    
    def save_interpretation_knowledge(self, output_dir):
        """保存解释油气水层知识"""
        try:
            # 创建模板文件夹
            template_dir = os.path.join(output_dir, '模板')
            os.makedirs(template_dir, exist_ok=True)
            
            # 解释知识
            interpretation_knowledge = {
                'oil_gas_water_identification': {
                    'OIL': {
                        'description': '油层',
                        'characteristics': [
                            'C1/C2比值通常在2-10之间',
                            'C1/C3比值通常在2-20之间',
                            'C1/C4比值通常在2-40之间',
                            '总烃含量较高',
                            '气体组分中重烃含量相对较高'
                        ],
                        'traditional_methods': {
                            'pixler': 'C1C2在2-10之间，C1C3在2-20之间，C1C4在2-40之间',
                            'triangle': 'lr < 0 或 (lr > 0 且 C1T14 <= 0.85)',
                            '3h': 'WH >= 0.05 且 WH <= 25 且 CH >= 0.05 且 BH <= WH * 2.0',
                            'star': '与油层模板相似度较高'
                        }
                    },
                    'GAS': {
                        'description': '气层',
                        'characteristics': [
                            'C1/C2比值通常大于10',
                            'C1/C3比值通常大于20',
                            'C1/C4比值通常大于40',
                            '总烃含量较高',
                            '气体组分中甲烷含量占绝对优势'
                        ],
                        'traditional_methods': {
                            'pixler': 'C1C2在8-40之间，C1C3在15-90之间，C1C4在30-250之间',
                            'triangle': 'lr > 0 且 C1T14 > 0.85',
                            '3h': 'WH >= 0.05 且 WH <= 25 且 不符合油层条件',
                            'star': '与气层模板相似度较高'
                        }
                    },
                    'WATER': {
                        'description': '水层',
                        'characteristics': [
                            '总烃含量较低',
                            '气体组分中甲烷含量可能较高，但总烃含量低',
                            '通常与油层或气层相伴生'
                        ],
                        'traditional_methods': {
                            'pixler': '不符合油层和气层条件',
                            'triangle': '不符合油层和气层条件',
                            '3h': '不符合油层和气层条件',
                            'star': '与水层模板相似度较高'
                        }
                    },
                    'DRY': {
                        'description': '干层',
                        'characteristics': [
                            '总烃含量较低',
                            '气体组分无明显特征',
                            '不具备油气显示'
                        ],
                        'traditional_methods': {
                            'pixler': 'C1C2 < 1.5 或 C1C2 >= 40 或 C1C3 < 1.5 或 C1C3 > 90 或 C1C4 < 1.5 或 C1C4 > 250',
                            'triangle': '不符合油层和气层条件',
                            '3h': 'WH < 0.05 或 WH > 25',
                            'star': '与所有模板相似度都较低'
                        }
                    }
                },
                'thresholds': {
                    'pixler': {
                        'oil': {
                            'C1C2_min': 1.5,
                            'C1C2_max': 15,
                            'C1C3_min': 1.5,
                            'C1C3_max': 25,
                            'C1C4_min': 1.5,
                            'C1C4_max': 50
                        },
                        'gas': {
                            'C1C2_min': 8,
                            'C1C2_max': 40,
                            'C1C3_min': 15,
                            'C1C3_max': 90,
                            'C1C4_min': 30,
                            'C1C4_max': 250
                        }
                    },
                    'triangle': {
                        'oil': 'C1T14 <= 0.85',
                        'gas': 'C1T14 > 0.85'
                    },
                    '3h': {
                        'oil': {
                            'WH_min': 0.05,
                            'WH_max': 25,
                            'CH_min': 0.05,
                            'BH_max_ratio': 2.0
                        },
                        'gas': {
                            'WH_min': 0.05,
                            'WH_max': 25
                        }
                    },
                    'star': {
                        'similarity_threshold': 0.1
                    }
                }
            }
            
            # 保存解释知识到JSON文件
            knowledge_path = os.path.join(template_dir, 'interpretation_knowledge.json')
            with open(knowledge_path, 'w', encoding='utf-8') as f:
                json.dump(interpretation_knowledge, f, ensure_ascii=False, indent=2)
            
            logger.info(f"解释油气水层知识保存至: {knowledge_path}")
            return knowledge_path
        except Exception as e:
            logger.error(f"保存解释知识失败: {e}")
            return None
    
    def generate_report(self):
        """生成报告"""
        try:
            report_path = os.path.join(self.output_dir, f"{self.well_name}_report.json")
            
            report_data = {
                'well_name': self.well_name,
                'data_mode': self.data_mode,
                'rawdata_path': self.rawdata_path,
                'run_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'qc_report': self.qc_report,
                'validation_results': self.validation_results,
                'accuracy_results': self.accuracy_results,
                'improvement_suggestions': self.improvement_suggestions
            }
            
            # 处理JSON序列化问题，将int64转换为int
            def convert_to_serializable(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {key: convert_to_serializable(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_to_serializable(item) for item in obj]
                else:
                    return obj
            
            report_serializable = convert_to_serializable(report_data)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_serializable, f, ensure_ascii=False, indent=2)
            
            logger.info(f"报告生成完成，保存至: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return None

# 主函数
def main():
    """主函数"""
    try:
        # 创建隐藏的tkinter窗口
        root = tk.Tk()
        root.withdraw()
        root.title("气测解释系统")
        
        print("=" * 60)
        print("气测解释系统 - 文件选择")
        print("=" * 60)
        
        # 选择原始气测数据文件
        print("\n请选择原始气测数据文件...")
        rawdata_path = filedialog.askopenfilename(
            title="选择原始气测数据文件",
            filetypes=[
                ("所有支持的文件", "*.csv;*.xlsx;*.xls;*.las;*.dlis"),
                ("CSV文件", "*.csv"),
                ("Excel文件", "*.xlsx;*.xls"),
                ("LAS文件", "*.las"),
                ("DLIS文件", "*.dlis"),
                ("所有文件", "*.*")
            ],
            initialdir="data"
        )
        
        if not rawdata_path:
            print("\n未选择原始数据文件，程序退出。")
            return
        
        print(f"已选择原始数据文件: {rawdata_path}")
        
        # 选择试油数据文件
        print("\n请选择试油结果数据文件...")
        testdata_path = filedialog.askopenfilename(
            title="选择试油结果数据文件",
            filetypes=[
                ("所有支持的文件", "*.csv;*.xlsx;*.xls"),
                ("CSV文件", "*.csv"),
                ("Excel文件", "*.xlsx;*.xls"),
                ("所有文件", "*.*")
            ],
            initialdir="data"
        )
        
        if not testdata_path:
            print("\n未选择试油数据文件，程序退出。")
            return
        
        print(f"已选择试油数据文件: {testdata_path}")
        
        # 选择解释配置文件
        print("\n请选择解释配置文件...")
        config_path = filedialog.askopenfilename(
            title="选择解释配置文件",
            filetypes=[
                ("JSON文件", "*.json"),
                ("所有文件", "*.*")
            ],
            initialdir="config"
        )
        
        if not config_path:
            print("\n未选择配置文件，程序退出。")
            return
        
        print(f"已选择配置文件: {config_path}")
        
        # 从文件路径提取井名
        well_name = os.path.basename(rawdata_path).split(' ')[0]
        # 如果文件名有扩展名，去掉扩展名
        if '.' in well_name:
            well_name = well_name.rsplit('.', 1)[0]
        
        print(f"\n提取的井名: {well_name}")
        print("\n" + "=" * 60)
        print("开始运行完整工作流...")
        print("=" * 60 + "\n")
        
        # 创建工作流实例
        workflow = CompleteWorkflow(rawdata_path, testdata_path, well_name, config_path)
        
        # 运行完整工作流
        results = workflow.run_complete_workflow()
        
        if results:
            logger.info("工作流运行成功！")
            
            # 获取准确率结果（已在工作流中计算）
            accuracy_results = results.get('accuracy_results')
            
            # 打印准确率结果
            if accuracy_results:
                print("\n=== 准确率对比结果 ===")
                for method_name, res in accuracy_results.items():
                    if method_name == 'average_accuracy':
                        print(f"所有方法平均准确率: {res:.3f}")
                    elif 'accuracy' in res:
                        print(f"{method_name}: {res['accuracy']:.3f} ({res['correct_matches']}/{res['total_matches']})")
            
            # 打印工作流摘要
            print("\n=== 工作流摘要 ===")
            print(f"井名: {results.get('well_name', 'Unknown')}")
            print(f"数据模式: {results.get('data_mode', 'Unknown')}")
            print(f"数据路径: {results.get('rawdata_path', 'Unknown')}")
            print(f"数据质量: {'通过' if results.get('qc_report') is not None else '失败'}")
            print(f"传统解释: {'完成' if results.get('traditional_results') is not None else '失败'}")
            print(f"机器学习解释: {'完成' if results.get('ml_results') is not None else '失败'}")
            print(f"深度学习解释: {'完成' if results.get('dl_results') is not None else '失败'}")
            print(f"结果验证: {'通过' if results.get('validation_results') is not None else '失败'}")
            print(f"准确率对比: {'完成' if accuracy_results is not None else '失败'}")
            print(f"改进建议: {len(results.get('improvement_suggestions', []))} 条")
            print(f"报告文件: {results.get('report_file', '未生成')}")
            
            # 打印改进建议
            improvement_suggestions = results.get('improvement_suggestions', [])
            if improvement_suggestions:
                print("\n=== 改进建议 ===")
                for i, suggestion in enumerate(improvement_suggestions, 1):
                    print(f"{i}. {suggestion}")
            
            # 显示完成消息
            messagebox.showinfo(
                "完成",
                f"工作流运行成功！\n\n"
                f"井名: {results.get('well_name', 'Unknown')}\n"
                f"数据模式: {results.get('data_mode', 'Unknown')}\n"
                f"报告文件: {results.get('report_file', '未生成')}\n\n"
                f"详细结果请查看控制台输出。"
            )
        else:
            logger.error("工作流运行失败")
            messagebox.showerror("错误", "工作流运行失败，请查看日志了解详情。")
        
        # 销毁tkinter窗口
        root.destroy()
        
    except Exception as e:
        logger.error(f"主函数执行失败: {e}")
        import traceback
        traceback.print_exc()
        messagebox.showerror("错误", f"程序运行出错：\n{e}")

if __name__ == "__main__":
    main()
