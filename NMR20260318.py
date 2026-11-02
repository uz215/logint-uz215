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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    """数据加载类"""
    
    def __init__(self):
        """初始化数据加载器"""
        pass
    
    def load_data(self, file_path):
        """加载测井数据"""
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            
            logger.info(f"正在加载数据: {file_path}")
            
            if file_ext == '.csv':
                data = pd.read_csv(file_path)
            elif file_ext in ['.xlsx', '.xls']:
                try:
                    data = pd.read_excel(file_path, engine='openpyxl' if file_ext == '.xlsx' else 'xlrd')
                except ImportError as e:
                    if "openpyxl" in str(e):
                        logger.error("需要安装openpyxl库: pip install openpyxl")
                    elif "xlrd" in str(e):
                        logger.error("需要安装xlrd库: pip install xlrd")
                    else:
                        logger.error(f"数据加载失败: {e}")
                    return None
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
                    # 使用正确的dlisio API
                    with dlisio.dlis.load(file_path) as files:
                        data = pd.DataFrame()
                        for file in files:
                            for frame in file.frames:
                                for channel in frame.channels:
                                    if channel.name not in data.columns:
                                        data[channel.name] = channel.data
                except ImportError:
                    logger.error("需要安装dlisio库: pip install dlisio")
                    return None
                except AttributeError as e:
                    logger.error(f"dlisio API错误: {e}")
                    # 尝试另一种API方式
                    try:
                        import dlisio
                        files = dlisio.load(file_path)
                        data = pd.DataFrame()
                        for file in files:
                            for frame in file.frames:
                                for channel in frame.channels:
                                    if channel.name not in data.columns:
                                        data[channel.name] = channel.data
                        files.close()
                    except Exception as e2:
                        logger.error(f"数据加载失败: {e2}")
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
    
    def load_nmr_data(self, file_path=None):
        """
        加载NMR数据文件
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

        data = None
        try:
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
                        raise e

            elif file_ext == '.dlis':
                # 读取DLIS文件
                try:
                    import dlisio
                    # 使用dlisio 1.0.4的API
                    from dlisio import dlis
                    
                    def find_index_curve(recurse_channels):
                        """
                        遍历通道列表，查找最有可能作为索引曲线（通常是深度曲线）的通道。
                        """
                        for channel in recurse_channels:
                            # 检查标准的深度标识符
                            if hasattr(channel, 'reprc') and channel.reprc == 7:  # FDO (Floating Point Depth Origin)
                                return channel
                            if hasattr(channel, 'units') and channel.units.upper() in ['M', 'METER', 'METERS', 'FT', 'FOOT', 'FEET']:
                                # 如果找到带有深度单位的曲线，则很可能是索引曲线
                                return channel
                            # 常见的深度曲线名字模式
                            name_upper = channel.name.upper()
                            if any(pattern in name_upper for pattern in ['_DEPT', 'TDEP', 'INDEX']):
                                return channel
                        
                        # 如果没有明确的标志，则返回第一个通道作为备选
                        if recurse_channels:
                            return recurse_channels[0]
                        
                        return None
                    
                    def convert_feet_to_meters(feet_value):
                        """
                        将英尺转换为米。
                        """
                        return feet_value * 0.3048
                    
                    # 加载DLIS文件
                    with dlis.load(file_path) as files:
                        # 检查files是否为列表
                        if isinstance(files, str):
                            # 如果files是字符串，说明dlisio返回了错误信息
                            raise ValueError(f"DLIS文件加载失败: {files}")
                        
                        # 获取文件中的第一个逻辑文件集
                        logical_file = next(iter(files), None)
                        if not logical_file:
                            print("警告: 未在文件中找到任何逻辑文件集。")
                            raise ValueError("DLIS文件中未找到逻辑文件集")
                        
                        # 检查logical_file是否为字符串（错误信息）
                        if isinstance(logical_file, str):
                            raise ValueError(f"DLIS文件解析错误: {logical_file}")

                        # 打印逻辑文件信息
                        log_print(f"逻辑文件名称: {getattr(logical_file, 'name', 'N/A')}")
                        log_print(f"逻辑文件描述: {getattr(logical_file, 'description', 'N/A')}")

                        # 获取所有帧
                        frames = list(logical_file.frames)
                        log_print(f"找到 {len(frames)} 个帧:")
                        for i, frame in enumerate(frames):
                            log_print(f"  帧 {i+1}: {getattr(frame, 'name', 'N/A')}")
                            log_print(f"    通道数: {len(getattr(frame, 'channels', []))}")
                            channels_list = getattr(frame, 'channels', [])
                            log_print(f"    通道列表: {[getattr(ch, 'name', 'N/A') for ch in channels_list]}")
                            if hasattr(frame, 'index') and frame.index is not None:
                                index_obj = frame.index
                                if hasattr(index_obj, 'name'):
                                    log_print(f"    索引曲线: {index_obj.name} (单位: {getattr(index_obj, 'units', 'N/A')})")
                                else:
                                    log_print(f"    索引曲线: {str(index_obj)}")

                        # 递归获取所有通道
                        all_channels = list(logical_file.channels)
                        log_print(f"\n找到 {len(all_channels)} 个通道:")
                        for channel in all_channels:
                            ch_name = getattr(channel, 'name', 'N/A')
                            ch_units = getattr(channel, 'units', 'N/A')
                            log_print(f"  - {ch_name} (单位: {ch_units})")

                        # 查找索引曲线（通常是深度曲线）
                        index_channel = find_index_curve(all_channels)
                        
                        if not index_channel:
                            log_print("警告: 未找到合适的索引/深度曲线。")
                            raise ValueError("未找到合适的索引/深度曲线")

                        index_channel_name = getattr(index_channel, 'name', 'N/A')
                        index_channel_units = getattr(index_channel, 'units', '未知')
                        log_print(f"\n--- 正在处理来自 {file_path} 的数据 ---")
                        log_print(f"使用的索引曲线: {index_channel_name}")
                        log_print(f"索引曲线单位: {index_channel_units}")

                        # 获取索引曲线的数据
                        try:
                            index_data = index_channel.data
                            log_print(f"索引曲线数据类型: {type(index_data)}")
                            log_print(f"索引曲线数据长度: {len(index_data)}")
                            log_print(f"索引曲线前10个值: {index_data[:10]}")
                            log_print(f"索引曲线后10个值: {index_data[-10:]}")
                            log_print(f"索引曲线最小值: {min(index_data)}")
                            log_print(f"索引曲线最大值: {max(index_data)}")
                        except Exception as e:
                            log_print(f"Error reading index channel data: {e}")
                            # 尝试使用curves()方法
                            try:
                                index_data = index_channel.curves()
                                log_print(f"使用curves()方法获取数据成功")
                                log_print(f"索引曲线数据类型: {type(index_data)}")
                                log_print(f"索引曲线数据长度: {len(index_data)}")
                            except Exception as e2:
                                log_print(f"Error reading index channel curves: {e2}")
                                raise
                        
                        # 打印原始单位信息
                        original_units = getattr(index_channel, 'units', '未知')
                        log_print(f"\n原始索引曲线单位: {original_units}")

                        # 判断单位并进行转换
                        units_upper = original_units.upper()
                        if units_upper in ['FT', 'FOOT', 'FEET']:
                            log_print("检测到深度单位为英尺 (FT/FOOT/FEET)，正在进行转换...")
                            converted_index_data = convert_feet_to_meters(index_data)
                            final_units = "M"
                            log_print(f"转换前深度范围: {min(index_data):.2f} - {max(index_data):.2f} 英尺")
                            log_print(f"转换后深度范围: {min(converted_index_data):.2f} - {max(converted_index_data):.2f} 米")
                            log_print("转换成功！深度单位已更新为米 (M)。")
                        elif 'IN' in units_upper:
                            # 处理英寸单位，可能是"IN", "INCH", "0.1 IN"等
                            log_print(f"检测到深度单位为英寸 ({original_units})，正在进行转换...")
                            # 检查是否是带小数的单位，如"0.1 IN"
                            if '0.1' in original_units:
                                # 0.1英寸/单位
                                converted_index_data = index_data * 0.1 * 0.0254  # 0.1英寸转换为米
                            else:
                                # 1英寸/单位
                                converted_index_data = index_data * 0.0254  # 英寸转换为米
                            final_units = "M"
                            log_print(f"转换前深度范围: {min(index_data):.2f} - {max(index_data):.2f} {original_units}")
                            log_print(f"转换后深度范围: {min(converted_index_data):.2f} - {max(converted_index_data):.2f} 米")
                            log_print("转换成功！深度单位已更新为米 (M)。")
                        else:
                            log_print("深度单位不是英尺或英寸，无需转换。")
                            converted_index_data = index_data
                            final_units = original_units
                            log_print(f"深度范围: {min(converted_index_data):.2f} - {max(converted_index_data):.2f} {final_units}")
                        
                        # 获取所有通道数据
                        channels = {}
                        channels[index_channel_name] = converted_index_data
                        
                        # 遍历所有帧和通道，获取其他数据
                        for frame in logical_file.frames:
                            frame_name = getattr(frame, 'name', 'N/A')
                            log_print(f"\n处理帧: {frame_name}")
                            frame_channels = getattr(frame, 'channels', [])
                            log_print(f"Frame channels: {[getattr(ch, 'name', 'N/A') for ch in frame_channels]}")
                            # 尝试使用frame.curves()获取所有通道数据
                            try:
                                curves = frame.curves()
                                log_print(f"Curves type: {type(curves)}")
                                log_print(f"Curves shape: {curves.shape}")
                                
                                # curves是结构化numpy数组，通过dtype.names获取字段名
                                if hasattr(curves, 'dtype') and hasattr(curves.dtype, 'names'):
                                    field_names = curves.dtype.names
                                    log_print(f"Field names: {field_names}")
                                    
                                    # 遍历所有字段
                                    for field_name in field_names:
                                        if field_name == index_channel_name:
                                            continue  # 跳过索引曲线，已经添加过了
                                        
                                        field_data = curves[field_name]
                                        log_print(f"Field {field_name} shape: {field_data.shape}")
                                        
                                        # 检查是否是多维数组（如T2_DIST）
                                        if len(field_data.shape) > 1:
                                            # 多维数组，展开为多个列
                                            log_print(f"多维数组 {field_name}，展开为 {field_data.shape[1]} 列")
                                            for i in range(field_data.shape[1]):
                                                col_name = f"{field_name}_{i}"
                                                channels[col_name] = field_data[:, i]
                                                log_print(f"添加列: {col_name}")
                                        else:
                                            # 一维数组，直接添加
                                            channels[field_name] = field_data
                                            log_print(f"添加通道: {field_name}, 数据长度: {len(field_data)}")
                                else:
                                    # 如果不是结构化数组，尝试按字典处理
                                    log_print(f"Frame curves keys: {list(curves.keys())}")
                                    for ch_name, ch_data in curves.items():
                                        if ch_name != index_channel_name:
                                            channels[ch_name] = ch_data
                                            log_print(f"添加通道: {ch_name}, 数据长度: {len(ch_data)}")
                            except Exception as e:
                                log_print(f"Error reading frame curves: {e}")
                                import traceback
                                log_print(f"Traceback: {traceback.format_exc()}")
                                # 如果frame.curves()失败，尝试逐个通道读取
                                for channel in frame_channels:
                                    try:
                                        channel_name = getattr(channel, 'name', 'N/A')
                                        if channel_name != index_channel_name:  # 避免重复添加索引曲线
                                            # 直接访问通道数据
                                            ch_data = channel.data
                                            channels[channel_name] = ch_data
                                            log_print(f"Read channel {channel_name}, data shape: {ch_data.shape if hasattr(ch_data, 'shape') else len(ch_data)}")
                                    except Exception as e:
                                        channel_name = getattr(channel, 'name', 'N/A')
                                        log_print(f"Error reading channel {channel_name}: {e}")

                    # 转换为DataFrame
                    data = pd.DataFrame(channels)
                    # 打印所有列名，以便调试
                    log_print(f"\nDLIS文件中的所有列: {list(data.columns)}")
                    # 打印数据的基本信息
                    log_print(f"Data shape: {data.shape}")
                    log_print(f"Data head:\n{data.head()}")
                    log_print(f"Data tail:\n{data.tail()}")
                    
                    # 打印深度列的详细信息
                    if index_channel_name in data.columns:
                        depth_data = data[index_channel_name]
                        log_print(f"\n深度列 {index_channel_name} 信息:")
                        log_print(f"  数据类型: {depth_data.dtype}")
                        log_print(f"  非空值数量: {depth_data.notnull().sum()}")
                        log_print(f"  深度范围: {depth_data.min():.2f} - {depth_data.max():.2f}")
                        log_print(f"  深度前10个值: {depth_data.values[:10]}")
                        log_print(f"  深度后10个值: {depth_data.values[-10:]}")
                    
                    # 保存数据到CSV文件，以便检查
                    nmr_dir = os.path.join('output', 'nmr')
                    os.makedirs(nmr_dir, exist_ok=True)
                    dlis_csv_path = os.path.join(nmr_dir, 'dlis_data.csv')
                    data.to_csv(dlis_csv_path, index=False)
                    log_print(f"\nDLIS数据已保存到 {dlis_csv_path} 文件")
                except ImportError as e:
                    log_print(f"ImportError: {e}")
                    raise ImportError("需要安装dlisio库: pip install dlisio")
                except Exception as e:
                    log_print(f"Error reading DLIS file: {e}")
                    raise ValueError(f"无法读取DLIS文件: {e}")

            else: # 假设为CSV
                data = pd.read_csv(file_path)
                log_print("成功读取CSV文件")
        finally:
            log_file.close()

        # --- 通用数据处理逻辑 (适用于 CSV, Excel, DLIS) ---

        # 打印所有列名，以便调试
        print(f"所有列名: {list(data.columns)}")
        
        # 初始化深度相关变量
        depth_col = None
        depth = None
        valid_depth_mask = None
        
        # 对于DLIS文件，使用之前找到的索引曲线作为深度列
        if file_ext == '.dlis' and 'index_channel_name' in locals():
            depth_col = index_channel_name
            print(f"使用DLIS文件中的索引曲线作为深度列: {depth_col}")
            # 提取深度数据并转换为数值类型，移除NaN
            depth = pd.to_numeric(data[depth_col], errors='coerce').values
            valid_depth_mask = ~np.isnan(depth)
            depth = depth[valid_depth_mask]
        else:
            # 对于非DLIS文件，查找深度列
            depth_cols = ['MD', 'DEPTH', 'Depth', 'depth', 'DEPT', 'dept','TDEP','TDEPTH','tdep','tdepth']
            depth_col = next((col for col in depth_cols if col in data.columns), None)
            
            if not depth_col:
                # 如果没有找到深度列，尝试使用第一个数值列
                numeric_cols = data.select_dtypes(include=['float64', 'int64']).columns
                if numeric_cols.empty:
                    raise ValueError("未找到深度列，请确保数据文件包含深度信息")
                depth_col = numeric_cols[0]
                print(f"未找到标准深度列，使用 {depth_col} 作为深度")

            # 提取深度数据并转换为数值类型，移除NaN
            depth = pd.to_numeric(data[depth_col], errors='coerce').values
            valid_depth_mask = ~np.isnan(depth)
            depth = depth[valid_depth_mask]

        print(f"深度数据形状: {depth.shape}")
        
        # 初始化 found_valid_depth 变量，避免作用域问题
        found_valid_depth = False
        
        # 深度合理性检查
        if len(depth) > 0:
            depth_min = min(depth)
            depth_max = max(depth)
            print(f"=== 深度合理性检查 ===")
            print(f"深度列: {depth_col}")
            print(f"深度范围: {depth_min:.2f} - {depth_max:.2f}")
            print(f"深度前10个值: {depth[:10]}")
            
            # 检查深度是否在合理范围内（通常0-10000米）
            if depth_max > 100000:  # 10万米以上的深度显然不合理
                print("警告：深度值异常大，可能是识别错误的深度列")
                # 尝试查找其他可能的深度列
                possible_depth_cols = [col for col in data.columns if any(depth_keyword in col.lower() for depth_keyword in ['md', 'depth', 'dept', 'tdep'])]
                print(f"可能的深度列: {possible_depth_cols}")
                
                # 打印所有数值列及其范围，以便选择合适的深度列
                print("\n=== 所有数值列及其范围 ===")
                for col in data.select_dtypes(include=['float64', 'int64']).columns:
                    col_data = pd.to_numeric(data[col], errors='coerce').values
                    col_data = col_data[~np.isnan(col_data)]
                    if len(col_data) > 0:
                        col_min = min(col_data)
                        col_max = max(col_data)
                        print(f"{col}: {col_min:.2f} - {col_max:.2f}")
                
                # 尝试使用范围在合理范围内的列作为深度列
                for col in data.select_dtypes(include=['float64', 'int64']).columns:
                    col_data = pd.to_numeric(data[col], errors='coerce').values
                    col_data = col_data[~np.isnan(col_data)]
                    if len(col_data) > 0:
                        col_min = min(col_data)
                        col_max = max(col_data)
                        if 0 < col_max < 10000:  # 合理的深度范围
                            print(f"\n发现合理的深度列: {col}")
                            depth_col = col
                            depth = col_data
                            print(f"新深度范围: {min(depth):.2f} - {max(depth):.2f}")
                            print(f"新深度前10个值: {depth[:10]}")
                            found_valid_depth = True
                            break
                
                # 不进行深度归一化，保持原始深度值
                if not found_valid_depth:
                    print("\n未找到合理的深度列，保持原始深度值")
                    # 检查深度值是否过大，如果过大可能是单位问题
                    if depth_max > 100000:
                        print("警告：深度值异常大，可能是单位问题或深度列识别错误")
                        print("建议检查数据文件中的深度单位设置")

        # --- DLIS特定的单位转换逻辑 ---
        depth_unit = None
        if file_ext == '.dlis':
            try:
                import dlisio
                from dlisio import dlis
                with dlis.load(file_path) as files:
                    f = files[0]
                    for frame in f.frames:
                        for channel in frame.channels:
                            channel_name = getattr(channel, 'name', 'N/A')
                            if channel_name == depth_col:
                                if hasattr(channel, 'units'):
                                    depth_unit = channel.units
                                elif hasattr(channel, 'unit'):
                                    depth_unit = channel.unit
                                break
                        if depth_unit: break
            except:
                pass # 如果DLIS读取失败，depth_unit保持None

        # 打印转换前的深度信息
        if len(depth) > 0:
            print(f"=== 深度单位转换前 ===")
            print(f"深度列: {depth_col}")
            print(f"深度单位: {depth_unit}")
            print(f"深度范围: {min(depth):.2f} - {max(depth):.2f}")
            print(f"深度前5个值: {depth[:5]}")

        # 深度单位转换
        depth_converted = False
        if len(depth) > 0:
            # 重新计算深度的最小和最大值，确保使用的是最新的深度值
            depth_min = min(depth)
            depth_max = max(depth)
            
            if depth_unit:
                if 'feet' in depth_unit.lower() or 'ft' in depth_unit.lower():
                    print(f"=== 检测到深度单位: {depth_unit}，将从英尺转换为米 ===")
                    depth = depth * 0.3048 # 1英尺 = 0.3048米
                    depth_converted = True
            else:
                # 尝试基于深度值的范围来判断是否需要转换（如果没有单位信息）
                print(f"=== 未检测到深度单位，基于深度值范围判断 ===")
                print(f"深度最大值: {depth_max:.2f}")
                # 如果深度值范围看起来像英尺（通常大于10000，因为10000英尺约3048米），则进行转换
                # 注意：如果已经进行了归一化，深度值应该已经在合理范围内，不需要再次转换
                if depth_max > 10000 and not found_valid_depth:
                    print("=== 深度值范围看起来像英尺，自动转换为米 ===")
                    depth = depth * 0.3048 # 1英尺 = 0.3048米
                    depth_converted = True
                else:
                    print("=== 深度值范围不像英尺，无需转换 ===")
        else:
            print("=== 深度数据为空，无法进行单位转换 ===")
            raise ValueError("深度数据为空，无法继续处理")
        
        # 对深度数据进行升序排序
        if len(depth) > 0:
            print("=== 对深度数据进行升序排序 ===")
            # 保存排序前的前5个值
            before_sort = depth[:5].copy()
            # 排序
            depth = np.sort(depth)
            # 保存排序后的前5个值
            after_sort = depth[:5].copy()
            print(f"排序前深度前5个值: {before_sort}")
            print(f"排序后深度前5个值: {after_sort}")
            print("=== 深度排序完成 ===")

        # 打印转换后的深度信息
        if len(depth) > 0:
            print(f"=== 深度单位转换后 ===")
            print(f"深度范围: {min(depth):.2f} - {max(depth):.2f} m")
            print(f"深度前5个值: {depth[:5]}")
            if depth_converted:
                print("=== 深度单位转换成功 ===")
            else:
                print("=== 深度单位未转换 ===")
        
        # 调试信息：确保深度值已正确转换
        print(f"\n=== 深度转换调试信息 ===")
        print(f"转换后深度数组类型: {type(depth)}")
        print(f"转换后深度数组长度: {len(depth)}")
        if len(depth) > 0:
            print(f"转换后深度最大值: {max(depth):.2f}")
            print(f"转换后深度最小值: {min(depth):.2f}")
            print(f"转换后深度平均值: {np.mean(depth):.2f}")
            print(f"转换后深度前10个值: {depth[:10]}")


        # 提取T2分量数据
        # 尝试多种方式识别T2分量列
        t2_cols = []
        # 方式1: 包含T2或t2的列
        t2_cols.extend([col for col in data.columns if 'T2' in col or 't2' in col])
        # 方式2: 包含NMR或nmr的列
        t2_cols.extend([col for col in data.columns if 'NMR' in col or 'nmr' in col])
        # 方式3: 包含SPECTRUM或spectrum的列
        t2_cols.extend([col for col in data.columns if 'SPECTRUM' in col or 'spectrum' in col])
        # 方式4: 包含BIN或bin的列
        t2_cols.extend([col for col in data.columns if 'BIN' in col or 'bin' in col])

        # 去重
        t2_cols = list(set(t2_cols))
        # 排除深度列
        t2_cols = [col for col in t2_cols if col != depth_col]

        print(f"识别到的T2分量列: {t2_cols}")
        print(f"T2分量列数量: {len(t2_cols)}")

        if len(t2_cols) < 1:
            # 如果没有找到T2列，尝试使用所有非深度列
            all_non_depth_cols = [col for col in data.columns if col != depth_col]
            print(f"尝试使用所有非深度列: {all_non_depth_cols}")
            t2_cols = all_non_depth_cols
            if len(t2_cols) < 1:
                raise ValueError("未找到T2分量列，请确保数据文件包含T2谱数据")

        # 提取T2数据并转换为数值类型，移除NaN
        t2_spectra_df = data[t2_cols].apply(pd.to_numeric, errors='coerce')
        t2_spectra = t2_spectra_df.values
        
        # 应用与深度相同的掩码，移除无效行
        t2_spectra = t2_spectra[valid_depth_mask, :]
        
        # 确保数据类型为float64
        t2_spectra = np.asarray(t2_spectra, dtype=np.float64)
        # 处理可能的NaN值
        t2_spectra = np.nan_to_num(t2_spectra, nan=0.0)

        # 检查是否还有有效数据
        if len(depth) == 0 or t2_spectra.size == 0:
            raise ValueError("数据文件中没有有效的数值数据")

        # 生成T2中心值（对数刻度）
        t2_bins = t2_spectra.shape[1]
        t2_log_min, t2_log_max = np.log10(0.3), np.log10(3000)
        t2_bins_edges = np.logspace(t2_log_min, t2_log_max, t2_bins + 1)
        t2_centers = (t2_bins_edges[:-1] + t2_bins_edges[1:]) / 2

        print(f"从{file_ext.upper()}文件加载数据成功: 深度点数={len(depth)}, T2通道数={len(t2_centers)}")
        return depth, t2_centers, t2_spectra, well_name

# --- 数据计算模块 ---
class DataProcessor:
    """数据处理类"""
    
    def __init__(self):
        """初始化数据处理器"""
        pass
    
    def calculate_T1_from_T2(self, t2_spectra, t2_centers):
        """
        从T2谱计算T1值
        基于经验关系 T1 ≈ T2 * (1.5-2.0) 对于水
        """
        T1_values = []
        for i in range(t2_spectra.shape[0]):
            # 计算几何平均T2
            amplitude = t2_spectra[i, :]
            valid_idx = amplitude > np.max(amplitude) * 1e-3
            if np.sum(valid_idx) == 0:
                t2g = np.nan
            else:
                log_t2 = np.log(t2_centers[valid_idx])
                weighted_log_t2 = np.sum(amplitude[valid_idx] * log_t2) / np.sum(amplitude[valid_idx])
                t2g = np.exp(weighted_log_t2)
            
            # 假设T1 = 1.8 * T2（经验值）
            T1 = 1.8 * t2g
            T1_values.append(T1)
        return np.array(T1_values)
    
    def calculate_D_from_T2(self, t2_spectra, t2_centers, depth):
        """
        简化的D计算模型。
        实际应用中，D通常通过双TW或双TE实验反演得到。
        此处我们假设D与T2的几何平均值成正比，并加入深度相关的噪声。
        """
        # 检查输入数组是否为空
        if t2_spectra.size == 0 or len(t2_centers) == 0 or len(depth) == 0:
            return np.array([])
        
        D_values = []
        for i in range(t2_spectra.shape[0]):
            # 计算几何平均T2 (T2g)
            amplitude = t2_spectra[i, :]
            # 防止log(0)
            valid_idx = amplitude > np.max(amplitude) * 1e-3
            if np.sum(valid_idx) == 0:
                t2g = np.nan
            else:
                log_t2 = np.log(t2_centers[valid_idx])
                weighted_log_t2 = np.sum(amplitude[valid_idx] * log_t2) / np.sum(amplitude[valid_idx])
                t2g = np.exp(weighted_log_t2)

            # 简化假设: D = k / T2g (例如，受限扩散模型)
            # 或者 D 与粘度有关，这里简单模拟
            # 假设 D 随深度增加而减小（压实作用）
            D = 1e-9 / (1 + depth[i]/1000) * (t2g / 100) # 单位: m^2/s (示例)
            D_values.append(D)
        return np.array(D_values)
    
    def calculate_porosity(self, t2_spectra):
        """
        计算孔隙度
        假设T2谱的面积与孔隙度成正比
        """
        porosity = np.sum(t2_spectra, axis=1)
        # 归一化处理
        if np.max(porosity) > 0:
            porosity = porosity / np.max(porosity) * 0.4  # 假设最大孔隙度为40%
        return porosity
    
    def calculate_porosity_by_t2_interval(self, t2_spectra, t2_centers):
        """
        按T2区间计算孔隙度
        """
        # 定义T2区间（ms）
        intervals = [(0.3, 1), (1, 10), (10, 33), (33, 100), (100, 300), (300, 1000), (1000, 3000)]
        interval_porosities = []
        
        for lower, upper in intervals:
            # 找到T2中心值在当前区间内的索引
            mask = (t2_centers >= lower) & (t2_centers < upper)
            if np.any(mask):
                # 计算该区间的孔隙度
                interval_porosity = np.sum(t2_spectra[:, mask], axis=1)
            else:
                # 如果没有T2中心值在当前区间内，返回全零
                interval_porosity = np.zeros(t2_spectra.shape[0])
            interval_porosities.append(interval_porosity)
        
        # 归一化处理
        total_porosity = np.sum(t2_spectra, axis=1)
        if np.max(total_porosity) > 0:
            scale_factor = 0.4 / np.max(total_porosity)  # 假设最大孔隙度为40%
            for i in range(len(interval_porosities)):
                interval_porosities[i] *= scale_factor
        
        return interval_porosities
    
    def calculate_permeability_sdr(self, porosity, t2_spectra, t2_centers):
        """
        使用SDR模型计算渗透率
        SDR模型: k = C * φ^4 * (T2gm)^2
        其中C是常数，通常取0.01
        """
        # 计算T2几何平均值
        T2gm = []
        for i in range(t2_spectra.shape[0]):
            amplitude = t2_spectra[i, :]
            valid_idx = amplitude > np.max(amplitude) * 1e-3
            if np.sum(valid_idx) == 0:
                t2g = np.nan
            else:
                log_t2 = np.log(t2_centers[valid_idx])
                weighted_log_t2 = np.sum(amplitude[valid_idx] * log_t2) / np.sum(amplitude[valid_idx])
                t2g = np.exp(weighted_log_t2)
            T2gm.append(t2g)
        T2gm = np.array(T2gm)
        
        # SDR模型计算渗透率
        C = 0.01  # 常数
        permeability = C * (porosity ** 4) * (T2gm ** 2)
        
        # 处理可能的NaN值
        permeability = np.nan_to_num(permeability, nan=0.0)
        
        return permeability
    
    def calculate_permeability_coates(self, porosity, t2_spectra, t2_centers):
        """
        使用Coates模型计算渗透率
        Coates模型: k = C * (φ^4 / (1-φ)^2) * (BVI/φ)^2
        其中C是常数，通常取0.001，BVI是束缚流体体积
        """
        # 计算束缚流体体积（BVI）- 通常取T2 < 33ms的孔隙度
        BVI = np.zeros(porosity.shape)
        for i in range(t2_spectra.shape[0]):
            # 找到T2 < 33ms的通道
            mask = t2_centers < 33
            if np.any(mask):
                BVI[i] = np.sum(t2_spectra[i, mask])
        
        # 归一化BVI
        total_porosity = np.sum(t2_spectra, axis=1)
        if np.max(total_porosity) > 0:
            scale_factor = 0.4 / np.max(total_porosity)  # 与孔隙度归一化相同
            BVI *= scale_factor
        
        # Coates模型计算渗透率
        C = 0.001  # 常数
        # 避免除以零
        denominator = np.where((1 - porosity) == 0, 1e-10, (1 - porosity) ** 2)
        bvi_ratio = np.where(porosity == 0, 0, BVI / porosity)
        permeability = C * (porosity ** 4 / denominator) * (bvi_ratio ** 2)
        
        # 处理可能的NaN值
        permeability = np.nan_to_num(permeability, nan=0.0)
        
        return permeability
    
    def calculate_fluid_volumes(self, t2_spectra, t2_centers):
        """
        计算三种流体体积：
        1. Clay Bound Fluid (CBF): T2 < 1 ms
        2. Capillary Bound Fluid (CBF): 1 ms < T2 < 100 ms，碳酸盐岩取100ms
        3. Free Fluid (FF): T2 > 100 ms，碳酸盐岩取100ms
        """
        # 初始化流体体积数组
        clay_bound_fluid = np.zeros(t2_spectra.shape[0])
        capillary_bound_fluid = np.zeros(t2_spectra.shape[0])
        free_fluid = np.zeros(t2_spectra.shape[0])
        
        for i in range(t2_spectra.shape[0]):
            # 计算Clay Bound Fluid (T2 < 1 ms)
            cbf_mask = t2_centers < 1
            if np.any(cbf_mask):
                clay_bound_fluid[i] = np.sum(t2_spectra[i, cbf_mask])
            
            # 计算Capillary Bound Fluid (1 ms < T2 < 100 ms)
            capillary_mask = (t2_centers >= 1) & (t2_centers < 100)
            if np.any(capillary_mask):
                capillary_bound_fluid[i] = np.sum(t2_spectra[i, capillary_mask])
            
            # 计算Free Fluid (T2 > 100 ms)
            free_mask = t2_centers >= 100
            if np.any(free_mask):
                free_fluid[i] = np.sum(t2_spectra[i, free_mask])
        
        # 归一化处理
        total_porosity = np.sum(t2_spectra, axis=1)
        if np.max(total_porosity) > 0:
            scale_factor = 0.4 / np.max(total_porosity)  # 与孔隙度归一化相同
            clay_bound_fluid *= scale_factor
            capillary_bound_fluid *= scale_factor
            free_fluid *= scale_factor
        
        return clay_bound_fluid, capillary_bound_fluid, free_fluid

# --- 可视化模块 ---
class Visualizer:
    """可视化类"""
    
    def __init__(self, output_dir='output'):
        """初始化可视化器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
    
    def plot_t2_spectra_depth(self, depth, t2_spectra, t2_centers, well_name):
        """
        绘制T2谱随深度变化图（伪彩图）和单个深度点的Bin谱
        """
        # 检查输入数组是否为空
        if len(depth) == 0 or t2_spectra.size == 0 or len(t2_centers) == 0:
            print("输入数组为空，无法绘制T2谱随深度变化图")
            return
        
        print(f"调用plot_t2_spectra_depth函数，井名: {well_name}")
        # 创建图形布局 (1行2列)
        fig = plt.figure(figsize=(16, 8))

        # --- 子图1: T2 BIN 显示谱图 (随深度变化的图像) ---
        ax1 = plt.subplot(1, 2, 1)

        # 使用pcolormesh创建伪彩图
        # 创建网格
        X, Y = np.meshgrid(t2_centers, depth)

        # 处理无效值（负值）
        t2_spectra = np.clip(t2_spectra, 0, None) # 将负值设置为0

        # 绘制伪彩图
        max_amplitude = np.max(t2_spectra)
        min_amplitude = np.min(t2_spectra)
        # 确保最小值大于0，且最大值大于最小值
        if min_amplitude == 0:
            min_amplitude = 1e-10
        if max_amplitude == 0:
            max_amplitude = 1e-9

        # 使用更专业的颜色映射
        # 选择viridis颜色映射，它是一个从蓝色到绿色到黄色的渐变色，非常适合显示数据的动态范围
        cmap = plt.cm.viridis

        pc = ax1.pcolormesh(X, Y, t2_spectra, cmap=cmap, norm=LogNorm(vmin=min_amplitude, vmax=max_amplitude), shading='auto')

        # 设置轴属性
        ax1.set_xscale('log')
        ax1.set_xlabel('T2 弛豫时间 (ms)')
        ax1.set_ylabel('深度 (m)')
        ax1.set_title(f'{well_name} - T2 Bin谱随深度变化 (伪彩图)')
        ax1.set_xlim(min(t2_centers), max(t2_centers))
        ax1.set_ylim(min(depth), max(depth))
        ax1.invert_yaxis() # 通常深度增加向下

        # 添加颜色条
        cbar1 = plt.colorbar(pc, ax=ax1)
        cbar1.set_label('信号幅度 (a.u.)')

        # 添加网格
        ax1.grid(True, which='both', linestyle='--', alpha=0.3)


        # --- 子图2: 单个深度点的T2 Bin谱 (柱状图) ---
        ax2 = plt.subplot(1, 2, 2)

        # 选择数据中的中间深度点
        target_depth = depth[len(depth)//2]
        idx = np.argmin(np.abs(depth - target_depth))

        # 绘制T2 Bin谱柱状图
        # 计算宽度，确保np.diff结果不为空
        t2_diff = np.diff(np.log10(t2_centers))
        if len(t2_diff) > 0:
            width = t2_diff[0] * np.log(10) * t2_centers * 0.8
        else:
            width = 0.1 * t2_centers  # 使用默认宽度
        ax2.bar(t2_centers, t2_spectra[idx, :], width=width)
        ax2.set_xscale('log')
        ax2.set_xlabel('T2 弛豫时间 (ms)')
        ax2.set_ylabel('信号幅度 (a.u.)')
        ax2.set_title(f'{well_name} - T2 Bin谱 (深度: {depth[idx]:.2f} m)')
        ax2.grid(True, which="both", ls="--", c='0.7')

        # 调整布局并保存
        plt.tight_layout()

        # 保存T2谱随深度变化图
        output_path = self.output_dir / f'{well_name}_t2_spectra_depth.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"T2谱随深度变化图已保存至: {output_path}")
    
    def plot_t1_t2_crossplot(self, T1_values, T2_values, depth, well_name):
        """
        绘制T1/T2交汇图，纵轴为深度，包含油气水线
        """
        if len(T1_values) == 0 or len(T2_values) == 0 or len(depth) == 0:
            print("输入数组为空，无法绘制T1/T2交汇图")
            return
        
        # 处理NaN值
        valid_mask = ~np.isnan(T2_values) & ~np.isinf(T2_values) & (T2_values > 0)
        if not np.any(valid_mask):
            print("T2_values中没有有效的值，无法绘制T1/T2交汇图")
            return
        
        T2_values_valid = T2_values[valid_mask]
        T1_values_valid = T1_values[valid_mask]
        depth_valid = depth[valid_mask]
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 绘制散点图，深度作为纵轴
        scatter = ax.scatter(T2_values_valid, depth_valid, c=T1_values_valid/T2_values_valid, cmap='jet', alpha=0.5, s=20)
        
        # 添加颜色条，显示T1/T2比值
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('T1/T2 比值')
        
        # 添加油气水线（参考值，实际应用中可能需要调整）
        # 水线: T1/T2 ≈ 1.0-1.2
        # 油线: T1/T2 ≈ 1.5-2.0
        # 气线: T1/T2 ≈ 2.0-3.0
        
        # 计算T1/T2比值
        t1_t2_ratio = T1_values_valid / T2_values_valid
        
        # 设置x轴范围
        x_min = max(0.1, np.min(T2_values_valid) * 0.9)
        x_max = np.max(T2_values_valid) * 1.1
        
        # 绘制水线 (T1 = T2)
        ax.plot([x_min, x_max], [min(depth_valid), min(depth_valid)], 'b--', label='水线 (T1=T2)')
        
        # 绘制油线 (T1 = 1.8 * T2)
        ax.plot([x_min, x_max], [max(depth_valid)*0.7, max(depth_valid)*0.7], 'g--', label='油线 (T1=1.8*T2)')
        
        # 绘制气线 (T1 = 2.5 * T2)
        ax.plot([x_min, x_max], [max(depth_valid)*0.4, max(depth_valid)*0.4], 'r--', label='气线 (T1=2.5*T2)')
        
        # 设置轴属性
        ax.set_xscale('log')
        ax.set_xlabel('T2 (ms)')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - T1/T2 交汇图 (按深度顺序)')
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(min(depth_valid), max(depth_valid))
        ax.invert_yaxis()  # 深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth_valid))
        depth_max = np.ceil(max(depth_valid))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_t1_t2_crossplot.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"T1/T2交汇图已保存至: {output_path}")
    
    def plot_t2_d_crossplot(self, T2_values, D_values, depth, well_name):
        """
        绘制T2/D交汇图，纵轴为深度
        """
        if len(T2_values) == 0 or len(D_values) == 0 or len(depth) == 0:
            print("输入数组为空，无法绘制T2/D交汇图")
            return
        
        # 处理NaN值
        valid_mask = ~np.isnan(T2_values) & ~np.isinf(T2_values) & (T2_values > 0) & ~np.isnan(D_values) & ~np.isinf(D_values)
        if not np.any(valid_mask):
            print("T2_values或D_values中没有有效的值，无法绘制T2/D交汇图")
            return
        
        T2_values_valid = T2_values[valid_mask]
        D_values_valid = D_values[valid_mask]
        depth_valid = depth[valid_mask]
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 绘制散点图，深度作为纵轴
        scatter = ax.scatter(T2_values_valid, depth_valid, c=D_values_valid, cmap='jet', alpha=0.5, s=20)
        
        # 添加颜色条，显示D值
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('D (m²/s)')
        
        # 设置x轴范围
        x_min = max(0.1, np.min(T2_values_valid) * 0.9)
        x_max = np.max(T2_values_valid) * 1.1
        
        # 设置轴属性
        ax.set_xscale('log')
        ax.set_xlabel('T2 (ms)')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - T2/D 交汇图 (按深度顺序)')
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(min(depth_valid), max(depth_valid))
        ax.invert_yaxis()  # 深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth_valid))
        depth_max = np.ceil(max(depth_valid))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_t2_d_crossplot.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"T2/D交汇图已保存至: {output_path}")
    
    def plot_porosity_stack(self, depth, interval_porosities, well_name):
        """
        绘制孔隙度堆叠图，按照0.3-1，1-10，10-33等区间堆叠，不同区间使用不同颜色
        """
        if len(depth) == 0 or len(interval_porosities) == 0:
            print("输入数组为空，无法绘制孔隙度堆叠图")
            return
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 定义孔隙度区间和对应的颜色（使用用户指定的颜色，确保强区分度）
        intervals_info = [('black', '0.3-1 ms'),
                         ('red', '1-10 ms'),
                         ('darkgreen', '10-33 ms'),
                         ('blue', '33-100 ms'),
                         ('lightblue', '100-300 ms'),
                         ('purple', '300-1000 ms'),
                         ('yellow', '1000-3000 ms')]
        
        # 计算累积孔隙度，用于堆叠显示
        cumulative_porosity = np.zeros_like(depth, dtype=np.float64)
        
        # 绘制每个区间的堆叠区域
        for i, (color, label) in enumerate(intervals_info):
            if i < len(interval_porosities):
                interval_porosity = interval_porosities[i]
                # 绘制当前区间的堆叠区域
                ax.fill_betweenx(depth, cumulative_porosity, cumulative_porosity + interval_porosity, 
                               color=color, alpha=0.5, label=label)
                # 更新累积孔隙度
                cumulative_porosity += interval_porosity
        
        # 绘制总孔隙度曲线
        total_porosity = np.sum(interval_porosities, axis=0)
        ax.plot(total_porosity, depth, 'black', linewidth=2, label='总孔隙度')
        
        # 设置轴属性
        ax.set_xlabel('孔隙度')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - 孔隙度堆叠图')
        ax.set_xlim(0, np.max(total_porosity) * 1.1)
        ax.set_ylim(min(depth), max(depth))
        ax.invert_yaxis() # 通常深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth))
        depth_max = np.ceil(max(depth))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_porosity_stack.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"孔隙度堆叠图已保存至: {output_path}")
    
    def plot_fluid_volumes(self, depth, clay_bound_fluid, capillary_bound_fluid, free_fluid, well_name):
        """
        绘制三种流体体积随深度变化的面积堆叠图
        """
        if len(depth) == 0 or len(clay_bound_fluid) == 0 or len(capillary_bound_fluid) == 0 or len(free_fluid) == 0:
            print("输入数组为空，无法绘制流体体积图")
            return
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 定义流体类型和对应的颜色
        fluids = [(clay_bound_fluid, 'blue', 'Clay Bound Fluid'),
                  (capillary_bound_fluid, 'green', 'Capillary Bound Fluid'),
                  (free_fluid, 'red', 'Free Fluid')]
        
        # 计算累积流体体积，用于堆叠显示
        cumulative_fluid = np.zeros_like(depth, dtype=np.float64)
        
        # 绘制每个流体的堆叠区域
        for fluid, color, label in fluids:
            ax.fill_betweenx(depth, cumulative_fluid, cumulative_fluid + fluid, 
                           color=color, alpha=0.5, label=label)
            # 更新累积流体体积
            cumulative_fluid += fluid
        
        # 绘制总流体体积曲线
        total_fluid = clay_bound_fluid + capillary_bound_fluid + free_fluid
        ax.plot(total_fluid, depth, 'black', linewidth=2, label='总流体体积')
        
        # 设置轴属性
        ax.set_xlabel('流体体积')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - 流体体积随深度变化图')
        ax.set_xlim(0, np.max(total_fluid) * 1.1)
        ax.set_ylim(min(depth), max(depth))
        ax.invert_yaxis() # 通常深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth))
        depth_max = np.ceil(max(depth))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_fluid_volumes.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"流体体积随深度变化图已保存至: {output_path}")
    
    def plot_permeability_depth(self, depth, permeability_sdr, permeability_coates, well_name):
        """
        绘制两种渗透率随深度变化的图
        """
        if len(depth) == 0 or len(permeability_sdr) == 0 or len(permeability_coates) == 0:
            print("输入数组为空，无法绘制渗透率图")
            return
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 绘制渗透率曲线
        ax.plot(permeability_sdr, depth, 'blue', linewidth=2, label='渗透率 (SDR)')
        ax.plot(permeability_coates, depth, 'red', linewidth=2, label='渗透率 (Coates)')
        
        # 设置轴属性
        ax.set_xlabel('渗透率 (mD)')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - 渗透率随深度变化图')
        ax.set_xscale('log')  # 渗透率通常使用对数刻度
        ax.set_ylim(min(depth), max(depth))
        ax.invert_yaxis() # 通常深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth))
        depth_max = np.ceil(max(depth))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_permeability_depth.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"渗透率随深度变化图已保存至: {output_path}")
    
    def plot_porosity_100_1000(self, depth, interval_porosities, well_name):
        """
        绘制100-1000区间孔隙度随深度变化图
        """
        if len(depth) == 0 or len(interval_porosities) < 5:
            print("输入数组为空，无法绘制100-1000区间孔隙度图")
            return
        
        # 100-1000ms区间是第5个区间（索引4）
        porosity_100_1000 = interval_porosities[4]
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 绘制100-1000ms区间孔隙度曲线
        ax.plot(porosity_100_1000, depth, 'green', linewidth=2, label='100-1000ms 孔隙度')
        
        # 设置轴属性
        ax.set_xlabel('孔隙度')
        ax.set_ylabel('深度 (m)')
        ax.set_title(f'{well_name} - 100-1000ms区间孔隙度随深度变化图')
        ax.set_xlim(0, np.max(porosity_100_1000) * 1.1)
        ax.set_ylim(min(depth), max(depth))
        ax.invert_yaxis() # 通常深度增加向下
        
        # 设置深度轴刻度，每50米显示一个数字，每10米一个刻度
        depth_min = np.floor(min(depth))
        depth_max = np.ceil(max(depth))
        # 主刻度（每50米）
        major_ticks = np.arange(depth_min, depth_max + 50, 50)
        # 次刻度（每10米）
        minor_ticks = np.arange(depth_min, depth_max + 10, 10)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 调整布局并保存
        plt.tight_layout()
        output_path = self.output_dir / f'{well_name}_porosity_100_1000.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"100-1000ms区间孔隙度随深度变化图已保存至: {output_path}")

# --- 主处理类 ---
class NMRProcessor:
    """NMR测井数据处理主类"""
    
    def __init__(self, config=None):
        """初始化NMR处理器"""
        self.config = config or {}
        self.output_dir = Path(self.config.get('output_dir', 'output'))
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # 初始化各个模块
        self.data_loader = DataLoader()
        self.data_processor = DataProcessor()
        self.visualizer = Visualizer(str(self.output_dir))
    
    def run_workflow(self, file_path=None):
        """
        运行完整的NMR处理工作流
        """
        try:
            # 1. 加载数据
            logger.info("Step 1: 加载NMR数据")
            depth, t2_centers, t2_spectra, well_name = self.data_loader.load_nmr_data(file_path)
            
            # 2. 计算T1
            logger.info("Step 2: 计算T1值")
            T1_values = self.data_processor.calculate_T1_from_T2(t2_spectra, t2_centers)
            
            # 3. 计算D
            logger.info("Step 3: 计算扩散系数D")
            D_values = self.data_processor.calculate_D_from_T2(t2_spectra, t2_centers, depth)
            
            # 4. 计算孔隙度
            logger.info("Step 4: 计算孔隙度")
            porosity = self.data_processor.calculate_porosity(t2_spectra)
            # 按T2区间计算孔隙度
            interval_porosities = self.data_processor.calculate_porosity_by_t2_interval(t2_spectra, t2_centers)
            
            # 5. 计算渗透率
            logger.info("Step 5: 计算渗透率")
            permeability_sdr = self.data_processor.calculate_permeability_sdr(porosity, t2_spectra, t2_centers)
            permeability_coates = self.data_processor.calculate_permeability_coates(porosity, t2_spectra, t2_centers)
            
            # 6. 计算流体体积
            logger.info("Step 6: 计算流体体积")
            clay_bound_fluid, capillary_bound_fluid, free_fluid = self.data_processor.calculate_fluid_volumes(t2_spectra, t2_centers)
            
            # 7. 可视化
            logger.info("Step 7: 结果可视化")
            
            # 6.1 绘制T2谱随深度变化图
            self.visualizer.plot_t2_spectra_depth(depth, t2_spectra, t2_centers, well_name)
            
            # 7.2 绘制T1/T2交汇图
            # 计算每个深度点的T2几何平均值
            T2_values = []
            for i in range(t2_spectra.shape[0]):
                amplitude = t2_spectra[i, :]
                valid_idx = amplitude > np.max(amplitude) * 1e-3
                if np.sum(valid_idx) == 0:
                    t2g = np.nan
                else:
                    log_t2 = np.log(t2_centers[valid_idx])
                    weighted_log_t2 = np.sum(amplitude[valid_idx] * log_t2) / np.sum(amplitude[valid_idx])
                    t2g = np.exp(weighted_log_t2)
                T2_values.append(t2g)
            T2_values = np.array(T2_values)
            
            self.visualizer.plot_t1_t2_crossplot(T1_values, T2_values, depth, well_name)
            
            # 7.3 绘制T2/D交汇图
            self.visualizer.plot_t2_d_crossplot(T2_values, D_values, depth, well_name)
            
            # 7.4 绘制孔隙度堆叠图
            self.visualizer.plot_porosity_stack(depth, interval_porosities, well_name)
            
            # 7.5 绘制流体体积随深度变化图
            self.visualizer.plot_fluid_volumes(depth, clay_bound_fluid, capillary_bound_fluid, free_fluid, well_name)
            
            # 7.6 绘制渗透率随深度变化图
            self.visualizer.plot_permeability_depth(depth, permeability_sdr, permeability_coates, well_name)
            
            # 7.7 绘制100-1000区间孔隙度随深度变化图
            self.visualizer.plot_porosity_100_1000(depth, interval_porosities, well_name)
            
            # 保存处理结果到CSV文件
            import pandas as pd
            import os
            from datetime import datetime
            
            # 创建nmr目录
            nmr_dir = os.path.join('output', 'nmr')
            os.makedirs(nmr_dir, exist_ok=True)
            
            # 准备数据
            data = {
                'Depth': depth,
                'T2_GM': T2_values,
                'T1': T1_values,
                'D': D_values,
                'Porosity': porosity,
                'Permeability_SDR': permeability_sdr,
                'Permeability_Coates': permeability_coates,
                'Clay_Bound_Fluid': clay_bound_fluid,
                'Capillary_Bound_Fluid': capillary_bound_fluid,
                'Free_Fluid': free_fluid
            }
            
            # 添加区间孔隙度
            interval_labels = ['0.3-1ms', '1-10ms', '10-33ms', '33-100ms', '100-300ms', '300-1000ms', '1000-3000ms']
            for i, label in enumerate(interval_labels):
                if i < len(interval_porosities):
                    data[label] = interval_porosities[i]
            
            # 创建DataFrame
            df = pd.DataFrame(data)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"{well_name}_nmr_results_{timestamp}.csv"
            csv_path = os.path.join(nmr_dir, csv_filename)
            
            # 保存到CSV文件
            df.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"处理结果已保存到: {csv_path}")
            
            logger.info("NMR测井数据处理工作流完成")
            return {
                'depth': depth,
                't2_centers': t2_centers,
                't2_spectra': t2_spectra,
                'T1_values': T1_values,
                'D_values': D_values,
                'porosity': porosity,
                'permeability_sdr': permeability_sdr,
                'permeability_coates': permeability_coates,
                'clay_bound_fluid': clay_bound_fluid,
                'capillary_bound_fluid': capillary_bound_fluid,
                'free_fluid': free_fluid,
                'well_name': well_name
            }
            
        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None

# 设置matplotlib中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'Heiti TC', 'Arial Unicode MS', 'DejaVu Sans'] # 中文字体
plt.rcParams['axes.unicode_minus'] = False # 解决负号显示问题
plt.rcParams['mathtext.default'] = 'regular' # 确保数学符号正确显示

# --- 主函数 ---
if __name__ == "__main__":
    try:
        # 创建NMR处理器
        print("创建NMR处理器...")
        processor = NMRProcessor()
        
        # 运行工作流
        print("开始运行工作流...")
        results = processor.run_workflow()
        
        if results:
            print("处理完成！结果已保存到output目录")
        else:
            print("处理失败，请检查日志信息")
    except Exception as e:
        print(f"主程序执行失败: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")
