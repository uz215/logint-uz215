import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize
import pandas as pd
import tkinter as tk
from tkinter import filedialog
import os
import datetime
import json
from pathlib import Path
import logging

# 导入微电阻率成像模块
import sys
sys.path.append('src')
from microresistivity_imaging import MicroresistivityImagingProcessor

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('well_log_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 设置matplotlib中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'Heiti TC', 'Arial Unicode MS', 'DejaVu Sans'] # 中文字体
plt.rcParams['axes.unicode_minus'] = False # 解决负号显示问题
plt.rcParams['mathtext.default'] = 'regular' # 确保数学符号正确显示

# --- 配置管理类 ---
class ConfigManager:
    """配置管理类"""
    
    def __init__(self, config_path=None):
        """初始化配置管理器"""
        self.config_path = config_path
        self.config = self._load_config()
        
    def _load_config(self):
        """加载配置"""
        if self.config_path and Path(self.config_path).exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return self._get_default_config()
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'output_dir': 'output',
            'data_formats': ['csv', 'las', 'dlis'],
            'quality_check': True,
            'feature_engineering': True,
            'interpretation_methods': ['traditional', 'machine_learning', 'deep_learning'],
            'visualization': True,
            'report_generation': True,
            'model_config': {
                'traditional': {},
                'machine_learning': {
                    'model_type': 'random_forest',
                    'params': {}
                },
                'deep_learning': {
                    'model_type': 'mlp',
                    'params': {}
                }
            }
        }
    
    def get_config(self):
        """获取配置"""
        return self.config
    
    def update_config(self, new_config):
        """更新配置"""
        self.config.update(new_config)
        return self.config
    
    def save_config(self, save_path=None):
        """保存配置"""
        save_path = save_path or self.config_path
        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        return False

# --- 数据加载模块 ---
class DataLoader:
    """数据加载模块"""
    
    def __init__(self):
        """初始化数据加载器"""
        pass
    
    def load_data(self, file_path):
        """加载测录井数据"""
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            
            logger.info(f"正在加载数据: {file_path}")
            
            if file_ext == '.csv':
                data = pd.read_csv(file_path)
            elif file_ext == '.las':
                try:
                    import lasio
                    las = lasio.read(file_path)
                    data = las.df().reset_index()
                except ImportError:
                    logger.error("需要安装lasio库: pip install lasio")
                    return None
            elif file_ext == '.dlis':
                try:
                    import dlisio
                    with dlisio.dlis.load(file_path) as f:
                        logger.info(f"成功打开DLIS文件，包含 {len(f)} 个逻辑文件")
                        curves = {}
                        for i, logical_file in enumerate(f):
                            logger.info(f"处理逻辑文件 {i+1}")
                            for frame in logical_file.frames:
                                logger.info(f"处理帧: {frame.name}")
                                try:
                                    # 获取帧数据
                                    frame_data = frame.curves()
                                    logger.info(f"成功获取帧数据，形状: {frame_data.shape}")
                                    
                                    # 获取通道名称
                                    if hasattr(frame, 'channel_names'):
                                        channel_names = frame.channel_names
                                    else:
                                        channel_names = [channel.name for channel in frame.channels]
                                    logger.info(f"通道名称: {channel_names}")
                                    
                                    # 处理结构化数组
                                    if isinstance(frame_data, np.ndarray) and frame_data.dtype.names:
                                        logger.info("检测到结构化数组")
                                        # 遍历结构化数组的字段
                                        for field_name in frame_data.dtype.names:
                                            # 跳过FRAMENO等非数据字段
                                            if field_name == 'FRAMENO':
                                                continue
                                            # 检查字段是否在通道名称中
                                            for channel_name in channel_names:
                                                if channel_name in field_name or field_name in channel_name:
                                                    # 获取该字段的数据
                                                    field_data = frame_data[field_name]
                                                    logger.info(f"处理字段 {field_name} 对应通道 {channel_name}")
                                                    logger.info(f"字段数据形状: {field_data.shape}")
                                                    # 处理数据
                                                    if field_data.ndim == 2:
                                                        # 二维数据，计算平均值
                                                        processed_data = np.mean(field_data, axis=1)
                                                        curves[channel_name] = processed_data
                                                        logger.info(f"通道 {channel_name} 计算平均值，数据长度: {len(processed_data)}")
                                                    else:
                                                        # 一维数据，直接使用
                                                        curves[channel_name] = field_data
                                                        logger.info(f"通道 {channel_name} 数据长度: {len(field_data)}")
                                                    break
                                    elif isinstance(frame_data, np.ndarray):
                                        if frame_data.ndim == 2:
                                            # 二维数组，按列处理
                                            for i, channel_name in enumerate(channel_names):
                                                if i < frame_data.shape[1]:
                                                    curves[channel_name] = frame_data[:, i]
                                                    logger.info(f"添加通道 {channel_name}，数据长度: {len(frame_data[:, i])}")
                                        else:
                                            # 一维数组，尝试分割
                                            logger.warning(f"frame_data是一维数组，但有多个通道名称")
                                            if len(frame_data) >= len(channel_names):
                                                chunk_size = len(frame_data) // len(channel_names)
                                                for i, channel_name in enumerate(channel_names):
                                                    start = i * chunk_size
                                                    end = start + chunk_size
                                                    if start < len(frame_data):
                                                        channel_data = frame_data[start:end]
                                                        curves[channel_name] = channel_data
                                                        logger.info(f"添加通道 {channel_name}，数据长度: {len(channel_data)}")
                                    elif isinstance(frame_data, dict):
                                        # 字典形式的数据
                                        for channel_name, channel_data in frame_data.items():
                                            curves[channel_name] = channel_data
                                            logger.info(f"添加通道 {channel_name}，数据长度: {len(channel_data)}")
                                    else:
                                        # 其他类型，尝试遍历通道
                                        for channel in frame.channels:
                                            try:
                                                if hasattr(channel, 'curve'):
                                                    curve_data = channel.curve()
                                                    curves[channel.name] = curve_data
                                                    logger.info(f"添加通道 {channel.name}，数据长度: {len(curve_data)}")
                                                elif hasattr(channel, 'data'):
                                                    curve_data = channel.data
                                                    curves[channel.name] = curve_data
                                                    logger.info(f"添加通道 {channel.name}，数据长度: {len(curve_data)}")
                                            except Exception as e:
                                                logger.warning(f"获取通道 {channel.name} 数据失败: {e}")
                                except Exception as e:
                                    logger.error(f"获取帧数据失败: {e}")
                                    # 尝试另一种方法获取数据
                                    try:
                                        for channel in frame.channels:
                                            try:
                                                if hasattr(channel, 'curve'):
                                                    curve_data = channel.curve()
                                                    curves[channel.name] = curve_data
                                                    logger.info(f"添加通道 {channel.name}，数据长度: {len(curve_data)}")
                                                elif hasattr(channel, 'data'):
                                                    curve_data = channel.data
                                                    curves[channel.name] = curve_data
                                                    logger.info(f"添加通道 {channel.name}，数据长度: {len(curve_data)}")
                                            except Exception as e:
                                                logger.warning(f"获取通道 {channel.name} 数据失败: {e}")
                                    except Exception as e2:
                                        logger.error(f"尝试获取通道数据失败: {e2}")
                        
                        # 检查所有通道的数据长度是否一致
                        if curves:
                            lengths = [len(data) for data in curves.values()]
                            if len(set(lengths)) > 1:
                                logger.warning(f"通道数据长度不一致: {lengths}")
                                # 找到最小长度
                                min_length = min(lengths)
                                # 截断所有通道到最小长度
                                for channel_name, channel_data in curves.items():
                                    curves[channel_name] = channel_data[:min_length]
                                logger.info(f"所有通道数据已截断到长度: {min_length}")
                            
                            # 创建DataFrame
                            data = pd.DataFrame(curves)
                            logger.info(f"DLIS数据转换为DataFrame成功，形状: {data.shape}")
                        else:
                            logger.warning("未获取到任何DLIS数据")
                            return None
                except ImportError:
                    logger.error("需要安装dlisio库: pip install dlisio")
                    return None
                except Exception as e:
                    logger.error(f"读取DLIS文件失败: {e}")
                    return None
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
            
            # 按深度排序
            depth_cols = ['MD', 'DEPTH', 'Depth', 'depth']
            depth_col = next((col for col in depth_cols if col in data.columns), None)
            if depth_col:
                data = data.sort_values(depth_col).reset_index(drop=True)
                # 统一深度列名为MD
                if depth_col != 'MD':
                    data = data.rename(columns={depth_col: 'MD'})
            
            logger.info(f"数据加载成功，共 {len(data)} 条记录")
            return data
        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            return None
    
    def load_data_from_file(self, file_path=None):
        """
        加载数据文件
        支持CSV, XLSX, XLS, DLIS格式，文件应包含深度列和T2分量列
        参数:
            file_path: 文件路径（如果为None，则通过文件浏览器选择）
        返回:
            depth: 深度数组
            t2_centers: T2中心值
            t2_spectra: T2谱矩阵
            well_name: 井名（文件名空格前的部分）
        """
        # 如果没有提供文件路径，通过文件浏览器选择
        if file_path is None:
            # 弹出文件选择对话框
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口

            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择NMR数据文件",
                filetypes=[
                    ("Excel Files", "*.xlsx *.xls"),
                    ("DLIS文件", "*.dlis"),
                    ("CSV文件", "*.csv"),
                    ("所有文件", "*.*")
                ]
            )

            if not file_path:  # 如果没有选择文件，抛出异常
                raise FileNotFoundError("未选择文件，请重新运行并选择有效的NMR数据文件")

        print(f"选择的文件: {file_path}")

        # 提取井名（文件名空格前的部分）
        filename = os.path.basename(file_path)
        well_name = filename.split(' ')[0]
        print(f"提取井名: {well_name}")

        # 检查文件扩展名
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 创建日志文件
        log_file = open('dlis_processing_log.txt', 'w', encoding='utf-8')
        def log_print(message):
            print(message)
            log_file.write(message + '\n')
        
        log_print(f"选择的文件: {file_path}")
        log_print(f"提取井名: {well_name}")
        log_print(f"文件扩展名: {file_ext}")

        if file_ext in ['.xlsx', '.xls']:
            # 读取Excel文件
            try:
                data = pd.read_excel(file_path, engine='openpyxl' if file_ext == '.xlsx' else 'xlrd')
                log_print("成功读取Excel文件")
            except ImportError as e:
                if "openpyxl" in str(e):
                    raise ImportError("读取Excel文件需要安装openpyxl库: pip install openpyxl")
                elif "xlrd" in str(e):
                    raise ImportError("读取Excel文件需要安装xlrd库: pip install xlrd")
                else:
                    raise
        elif file_ext == '.csv':
            # 读取CSV文件
            try:
                data = pd.read_csv(file_path)
                log_print("成功读取CSV文件")
            except Exception as e:
                log_print(f"读取CSV文件失败: {e}")
                raise
        elif file_ext == '.dlis':
            # 读取DLIS文件
            try:
                import dlisio
                with dlisio.load(file_path) as f:
                    # 初始化数据存储
                    curves = {}
                    
                    # 遍历所有帧
                    for frame in f.frames:
                        log_print(f"处理帧: {frame.name}")
                        
                        # 获取索引通道（通常是深度）
                        index_channel = None
                        for channel in frame.channels:
                            if channel.name in ['DEPT', 'MD', 'DEPTH', 'Depth']:
                                index_channel = channel
                                break
                        
                        if not index_channel:
                            log_print("未找到深度通道")
                            continue
                        
                        # 读取索引通道数据
                        depth = index_channel.data
                        curves['MD'] = depth
                        
                        # 读取其他通道数据
                        try:
                            # 尝试使用frame.curves()方法
                            for channel in frame.channels:
                                if channel.name != index_channel.name:
                                    curves[channel.name] = channel.data
                        except Exception as e:
                            log_print(f"读取帧曲线失败: {e}")
                            # 如果frame.curves()失败，尝试逐个通道读取
                            for channel in frame.channels:
                                try:
                                    if channel.name != index_channel.name:
                                        # 直接访问通道数据
                                        ch_data = channel.data
                                        curves[channel.name] = ch_data
                                except Exception as e:
                                    log_print(f"读取通道 {channel.name} 失败: {e}")
                    
                    # 转换为DataFrame
                    data = pd.DataFrame(curves)
                    log_print("成功读取DLIS文件")
            except ImportError:
                raise ImportError("读取DLIS文件需要安装dlisio库: pip install dlisio")
            except Exception as e:
                log_print(f"读取DLIS文件失败: {e}")
                raise
        else:
            raise ValueError(f"不支持的文件格式: {file_ext}")
        
        # 关闭日志文件
        log_file.close()
        
        # 按深度排序
        if 'MD' in data.columns:
            data = data.sort_values('MD').reset_index(drop=True)
        
        # 提取深度列
        depth = data['MD'].values if 'MD' in data.columns else None
        
        # 提取T2分量列（假设列名包含'T2'）
        t2_cols = [col for col in data.columns if 'T2' in col or 't2' in col]
        t2_spectra = data[t2_cols].values if t2_cols else None
        
        # 生成T2中心值（假设列名格式为'T2_1', 'T2_2'等）
        t2_centers = []
        for col in t2_cols:
            try:
                # 尝试从列名中提取T2值
                t2_value = float(col.replace('T2_', '').replace('t2_', ''))
                t2_centers.append(t2_value)
            except:
                pass
        t2_centers = np.array(t2_centers) if t2_centers else None
        
        return depth, t2_centers, t2_spectra, well_name

# --- 数据计算模块 ---
class DataProcessor:
    """数据计算模块"""
    
    def __init__(self, config=None):
        """初始化数据处理器"""
        self.config = config or self._get_default_config()
        self.data = None
        self.processed_data = None
        self.results = {}
        self.output_dir = Path(self.config.get('output_dir', 'output'))
        self.output_dir.mkdir(exist_ok=True)
        
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'output_dir': 'output',
            'data_formats': ['csv', 'las', 'dlis'],
            'quality_check': True,
            'feature_engineering': True,
            'interpretation_methods': ['traditional', 'machine_learning', 'deep_learning'],
            'visualization': True,
            'report_generation': True
        }
    
    def set_data(self, data):
        """设置数据"""
        self.data = data
    
    def data_quality_check(self):
        """数据质量检查"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        qc_report = {
            'total_records': len(self.data),
            'missing_values': self.data.isnull().sum().to_dict(),
            'outliers': {},
            'data_types': self.data.dtypes.to_dict()
        }
        
        # 异常值检测
        numeric_cols = self.data.select_dtypes(include=['float64', 'int64']).columns
        for col in numeric_cols:
            if self.data[col].notnull().any():
                Q1 = self.data[col].quantile(0.25)
                Q3 = self.data[col].quantile(0.75)
                IQR = Q3 - Q1
                outliers = self.data[(self.data[col] < Q1 - 1.5*IQR) | (self.data[col] > Q3 + 1.5*IQR)]
                qc_report['outliers'][col] = len(outliers)
        
        # 数据完整性检查
        required_cols = ['MD']
        missing_cols = [col for col in required_cols if col not in self.data.columns]
        if missing_cols:
            qc_report['missing_required_columns'] = missing_cols
        
        self.results['qc_report'] = qc_report
        logger.info("数据质量检查完成")
        return qc_report
    
    def feature_engineering(self):
        """特征工程"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        self.processed_data = self.data.copy()
        
        # 气体比值计算
        gas_ratios = [('C1', 'C2'), ('C1', 'C3'), ('C2', 'C3'), ('C1', 'C4'), ('C2', 'C4'), ('C3', 'C4')]
        for i, j in gas_ratios:
            if all(col in self.processed_data.columns for col in [i, j]):
                col_name = f"{i}{j}"
                self.processed_data[col_name] = np.where(self.processed_data[j] == 0, 0, 
                                                         self.processed_data[i] / self.processed_data[j])
        
        # 烃类组分计算
        gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
        available_gas_cols = [col for col in gas_cols if col in self.processed_data.columns]
        if available_gas_cols:
            self.processed_data['T15'] = self.processed_data[available_gas_cols].sum(axis=1)
        
        # 干燥系数
        if all(col in self.processed_data.columns for col in ['C1', 'T15']):
            self.processed_data['DRYNESS'] = np.where(self.processed_data['T15'] == 0, 0, 
                                                     self.processed_data['C1'] / self.processed_data['T15'])
        
        # 孔隙度计算
        # 1. 密度孔隙度
        if 'RHOB' in self.processed_data.columns:
            # 假设基质密度为2.65 g/cm³，流体密度为1.0 g/cm³
            matrix_density = 2.65
            fluid_density = 1.0
            self.processed_data['POR_DEN'] = (matrix_density - self.processed_data['RHOB']) / (matrix_density - fluid_density)
            # 限制孔隙度范围在0-1之间
            self.processed_data['POR_DEN'] = self.processed_data['POR_DEN'].clip(0, 1)
        
        # 2. 中子孔隙度
        if 'NPHI' in self.processed_data.columns:
            # 假设中子孔隙度已经是小数形式
            self.processed_data['POR_NEU'] = self.processed_data['NPHI'].clip(0, 1)
        
        # 3. 综合孔隙度（如果有密度和中子孔隙度）
        if all(col in self.processed_data.columns for col in ['POR_DEN', 'POR_NEU']):
            # 简单平均
            self.processed_data['POR'] = (self.processed_data['POR_DEN'] + self.processed_data['POR_NEU']) / 2
        elif 'POR_DEN' in self.processed_data.columns:
            self.processed_data['POR'] = self.processed_data['POR_DEN']
        elif 'POR_NEU' in self.processed_data.columns:
            self.processed_data['POR'] = self.processed_data['POR_NEU']
        
        # 其他特征计算...
        
        self.results['processed_data'] = self.processed_data
        logger.info("特征工程完成")
        return self.processed_data
    
    def apply_interpretation(self):
        """应用解释模型"""
        if self.processed_data is None:
            logger.error("数据未处理")
            return None
        
        interpretations = {}
        
        # 传统解释方法
        if 'traditional' in self.config['interpretation_methods']:
            # 简化的传统解释
            # 这里可以集成现有的NMR解释功能
            interpretations['traditional'] = {'method': 'NMR Analysis'}
        
        # 机器学习解释方法
        if 'machine_learning' in self.config['interpretation_methods']:
            # 简化的机器学习解释
            interpretations['machine_learning'] = {'method': 'ML Analysis'}
        
        # 深度学习解释方法
        if 'deep_learning' in self.config['interpretation_methods']:
            # 简化的深度学习解释
            interpretations['deep_learning'] = {'method': 'DL Analysis'}
        
        self.results['interpretations'] = interpretations
        logger.info("解释模型应用完成")
        return interpretations

# --- 数据可视化模块 ---
class DataVisualizer:
    """数据可视化模块"""
    
    def __init__(self, output_dir):
        """初始化可视化器"""
        self.output_dir = Path(output_dir)
        self.viz_dir = self.output_dir / 'visualization'
        self.viz_dir.mkdir(exist_ok=True, parents=True)
    
    def visualize_gas_logs(self, data):
        """可视化气测曲线"""
        if data is None:
            logger.error("无数据可可视化")
            return None
        
        try:
            fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
            
            # 绘制气体曲线
            gas_cols = ['C1', 'C2', 'C3', 'IC4', 'NC4']
            for col in gas_cols:
                if col in data.columns:
                    axes[0].plot(data['MD'], data[col], label=col)
            
            axes[0].set_ylabel('Gas Content (ppm)')
            axes[0].legend()
            axes[0].set_title('Gas Logs')
            
            # 绘制解释结果
            # 这里可以添加解释结果的可视化
            
            axes[1].set_xlabel('Depth (m)')
            axes[1].set_ylabel('Interpretation')
            axes[1].set_title('Interpretation Results')
            axes[1].set_yticks([])
            
            plt.tight_layout()
            output_path = self.viz_dir / 'gas_logs.png'
            plt.savefig(output_path)
            plt.close()
            
            logger.info(f"气测曲线保存至: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"可视化气测曲线失败: {e}")
            return None
    
    def visualize_porosity(self, data):
        """可视化孔隙度数据"""
        if data is None:
            logger.error("无数据可可视化")
            return None
        
        try:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # 绘制孔隙度曲线
            porosity_cols = ['POR', 'POR_DEN', 'POR_NEU']
            for col in porosity_cols:
                if col in data.columns:
                    ax.plot(data['MD'], data[col], label=col)
            
            ax.set_xlabel('Depth (m)')
            ax.set_ylabel('Porosity')
            ax.set_title('Porosity Logs')
            ax.legend()
            
            plt.tight_layout()
            output_path = self.viz_dir / 'porosity_logs.png'
            plt.savefig(output_path)
            plt.close()
            
            logger.info(f"孔隙度曲线保存至: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"可视化孔隙度数据失败: {e}")
            return None
    
    def visualize_interval_stacked_plot(self, data):
        """可视化孔隙区间堆积图"""
        if data is None:
            logger.error("无数据可可视化")
            return None
        
        try:
            # 检查是否有孔隙度数据
            porosity_cols = ['POR', 'PHI', 'NPHI', 'PHIE']
            porosity_col = next((col for col in porosity_cols if col in data.columns), None)
            
            if not porosity_col:
                logger.warning("未找到孔隙度数据，使用随机数据示例")
                # 使用随机数据示例
                depth = np.linspace(1000, 2000, 100)
                por = 0.05 + np.random.rand(100) * 0.25
            else:
                depth = data['MD'].values
                por = data[porosity_col].values
            
            # 定义孔隙区间
            intervals = [
                ('0-5%', 0, 0.05),
                ('5-10%', 0.05, 0.1),
                ('10-15%', 0.1, 0.15),
                ('15-20%', 0.15, 0.2),
                ('20-25%', 0.2, 0.25),
                ('25-30%', 0.25, 0.3),
                ('30%+', 0.3, 1.0)
            ]
            
            # 计算每个深度点在各区间的权重
            interval_data = {}
            for interval_name, min_por, max_por in intervals:
                interval_data[interval_name] = np.where((por >= min_por) & (por < max_por), por - min_por, 0)
                interval_data[interval_name] = np.where((por >= max_por), max_por - min_por, interval_data[interval_name])
            
            # 绘制堆积图
            fig, ax = plt.subplots(figsize=(12, 10))
            
            # 堆积绘制各区间
            bottom = np.zeros_like(depth)
            colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0']
            
            for i, (interval_name, min_por, max_por) in enumerate(intervals):
                ax.fill_between(depth, bottom, bottom + interval_data[interval_name], 
                               label=interval_name, color=colors[i], alpha=0.7)
                bottom += interval_data[interval_name]
            
            ax.set_xlabel('Porosity')
            ax.set_ylabel('Depth (m)')
            ax.set_title('Porosity Interval Stacked Plot')
            ax.invert_yaxis()  # 深度向下增加
            ax.legend(loc='upper right')
            
            plt.tight_layout()
            output_path = self.viz_dir / 'porosity_interval_stacked_plot.png'
            plt.savefig(output_path)
            plt.close()
            
            logger.info(f"孔隙区间堆积图保存至: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"可视化孔隙区间堆积图失败: {e}")
            return None
    
    def visualize_all(self, results):
        """可视化所有结果"""
        visualization_results = {}
        
        # 可视化气测曲线
        if 'processed_data' in results:
            gas_logs_path = self.visualize_gas_logs(results['processed_data'])
            if gas_logs_path:
                visualization_results['gas_logs'] = gas_logs_path
            
            # 可视化孔隙度数据
            porosity_path = self.visualize_porosity(results['processed_data'])
            if porosity_path:
                visualization_results['porosity_logs'] = porosity_path
            
            # 可视化孔隙区间堆积图
            interval_plot_path = self.visualize_interval_stacked_plot(results['processed_data'])
            if interval_plot_path:
                visualization_results['porosity_interval_stacked_plot'] = interval_plot_path
        
        return visualization_results

# --- 报告生成模块 ---
class ReportGenerator:
    """报告生成模块"""
    
    def __init__(self, output_dir):
        """初始化报告生成器"""
        self.output_dir = Path(output_dir)
        self.report_dir = self.output_dir / 'reports'
        self.report_dir.mkdir(exist_ok=True, parents=True)
    
    def generate_report(self, results, config):
        """生成报告"""
        if not results:
            logger.error("无结果可生成报告")
            return None
        
        # 生成HTML报告
        report_path = self.report_dir / 'interpretation_report.html'
        
        # 报告内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>测录井资料解释报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .summary {{ background-color: #f5f5f5; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .success {{ color: green; }}
                .warning {{ color: orange; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1>测录井资料解释报告</h1>
            
            <div class="section summary">
                <h2>摘要</h2>
                <p>报告生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>数据记录数: {results.get('qc_report', {}).get('total_records', 'N/A')}</p>
                <p>解释方法: {', '.join(config['interpretation_methods'])}</p>
            </div>
            
            <div class="section">
                <h2>数据质量检查</h2>
                <table>
                    <tr>
                        <th>检查项</th>
                        <th>结果</th>
                    </tr>
                    <tr>
                        <td>总记录数</td>
                        <td>{results.get('qc_report', {}).get('total_records', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td>缺失值</td>
                        <td>{len([k for k, v in results.get('qc_report', {}).get('missing_values', {}).items() if v > 0])} 列</td>
                    </tr>
                    <tr>
                        <td>异常值</td>
                        <td>{len([k for k, v in results.get('qc_report', {}).get('outliers', {}).items() if v > 0])} 列</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h2>解释结果</h2>
                <!-- 解释结果内容 -->
            </div>
            
            <div class="section">
                <h2>可视化结果</h2>
                <p>可视化结果已保存至: {self.output_dir / 'visualization'}</p>
            </div>
        </body>
        </html>
        """
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"报告生成完成，保存至: {report_path}")
        return str(report_path)

# --- 主工作流类 ---
class WellLogProcessor:
    """测录井资料处理主类"""
    
    def __init__(self, config=None):
        """初始化处理器"""
        self.config = config or ConfigManager().get_config()
        self.data_loader = DataLoader()
        self.data_processor = DataProcessor(self.config)
        self.data_visualizer = DataVisualizer(self.config.get('output_dir', 'output'))
        self.report_generator = ReportGenerator(self.config.get('output_dir', 'output'))
        self.microresistivity_processor = MicroresistivityImagingProcessor()
        self.results = {}
    
    def load_data(self, file_path):
        """加载数据"""
        # 检查文件扩展名
        file_ext = Path(file_path).suffix.lower()
        
        # 如果是图像文件，使用微电阻率成像模块加载
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
            logger.info(f"检测到图像文件，使用微电阻率成像模块加载: {file_path}")
            # 直接返回None，因为图像数据将在微电阻率处理步骤中处理
            return None
        else:
            # 否则使用常规数据加载器
            data = self.data_loader.load_data(file_path)
            if data is not None:
                self.data_processor.set_data(data)
                self.results['raw_data'] = data
            return data
    
    def run_workflow(self, file_path=None):
        """运行完整工作流"""
        logger.info("开始测录井资料处理工作流")
        
        try:
            # 检查是否为图像文件
            if file_path:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
                    logger.info("处理微电阻率成像数据")
                    # 使用微电阻率成像模块处理图像
                    imaging_results = self.microresistivity_processor.run_workflow(file_path)
                    if imaging_results:
                        self.results['microresistivity_imaging'] = imaging_results
                        logger.info("微电阻率成像处理完成")
                    else:
                        logger.warning("微电阻率成像处理失败")
                    return self.results
            
            # 检查数据是否加载（仅当不是图像文件时）
            if self.data_processor.data is None or len(self.data_processor.data) == 0:
                logger.error("数据未加载或为空")
                return None
            
            # 1. 数据质量检查
            if self.config['quality_check']:
                logger.info("Step 1: 数据质量检查")
                qc_report = self.data_processor.data_quality_check()
                if qc_report:
                    self.results['qc_report'] = qc_report
            
            # 2. 特征工程
            if self.config['feature_engineering']:
                logger.info("Step 2: 特征工程")
                processed_data = self.data_processor.feature_engineering()
                if processed_data is not None and len(processed_data) > 0:
                    self.results['processed_data'] = processed_data
                else:
                    logger.error("特征工程失败，处理后数据为空")
                    return None
            
            # 3. 应用解释模型
            logger.info("Step 3: 应用解释模型")
            interpretations = self.data_processor.apply_interpretation()
            if interpretations:
                self.results['interpretations'] = interpretations
            
            # 4. 结果可视化
            if self.config['visualization']:
                logger.info("Step 4: 结果可视化")
                visualization_results = self.data_visualizer.visualize_all(self.results)
                if visualization_results:
                    self.results['visualization_results'] = visualization_results
            
            # 5. 生成报告
            if self.config['report_generation']:
                logger.info("Step 5: 生成报告")
                report_path = self.report_generator.generate_report(self.results, self.config)
                if report_path:
                    self.results['report_path'] = report_path
            
            logger.info("测录井资料处理工作流完成")
            return self.results
            
        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- 主函数 ---
import sys

def run_well_log_workflow():
    """运行测录井资料处理工作流"""
    print("开始运行测录井资料处理工作流")
    logger.info("开始运行测录井资料处理工作流")
    
    try:
        print("创建处理器")
        # 创建处理器
        processor = WellLogProcessor()
        print("处理器创建成功")
        logger.info("处理器创建成功")
        
        # 检查命令行参数
        if len(sys.argv) > 1:
            # 使用命令行参数作为文件路径
            file_path = sys.argv[1]
            logger.info(f"从命令行获取文件路径: {file_path}")
        else:
            # 打开文件选择对话框
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择测录井数据文件或图像文件",
                filetypes=[
                    ("图像文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif"),
                    ("CSV文件", "*.csv"),
                    ("LAS文件", "*.las"),
                    ("DLIS文件", "*.dlis"),
                    ("所有文件", "*.*")
                ]
            )
            
            if not file_path:
                logger.error("未选择文件")
                return
        
        # 检查是否为图像文件
        file_ext = Path(file_path).suffix.lower()
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
            # 对于图像文件，直接运行工作流
            logger.info(f"检测到图像文件，使用微电阻率成像模块处理: {file_path}")
            results = processor.run_workflow(file_path)
        else:
            # 对于非图像文件，先加载数据
            logger.info(f"加载数据文件: {file_path}")
            data = processor.load_data(file_path)
            
            if data is None:
                logger.error("数据加载失败")
                return
            
            # 运行工作流
            results = processor.run_workflow(file_path)
        
        if results:
            logger.info("工作流运行成功")
            print("\n工作流运行成功！")
            print(f"结果已保存至: {processor.config.get('output_dir', 'output')}")
        else:
            logger.error("工作流运行失败")
            print("\n工作流运行失败，请查看日志了解详细信息。")
            
    except Exception as e:
        logger.error(f"运行工作流时出错: {e}")
        print(f"\n运行工作流时出错: {e}")

if __name__ == "__main__":
    run_well_log_workflow()
