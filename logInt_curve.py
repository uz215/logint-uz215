



# =============================================================================
# 依赖检查模块
# =============================================================================
import sys
import importlib.util

# 启动提示，让用户知道程序正在加载
print("正在加载程序模块，请稍候...", flush=True)

def check_dependency(module_name, install_command=None):
    """
    检查依赖是否已安装
    
    参数:
        module_name: 模块名称
        install_command: 可选的安装命令提示
    
    返回:
        (是否已安装, 模块对象或None)
    """
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return False, None
        module = importlib.import_module(module_name)
        return True, module
    except (ImportError, ModuleNotFoundError):
        return False, None

def print_dependency_status():
    """打印依赖状态"""
    print("="*60)
    print("  测井资料处理系统 - 依赖检查")
    print("="*60)
    print()
    
    # 核心依赖
    print("[核心依赖]")
    dependencies = [
        ('numpy', 'pip install numpy'),
        ('pandas', 'pip install pandas'),
        ('matplotlib', 'pip install matplotlib'),
        ('lasio', 'pip install lasio'),
    ]
    
    missing_core = []
    mod_installed = True
    for name, cmd in dependencies:
        installed, _ = check_dependency(name)
        status = "✓ 已安装" if installed else "✗ 未安装"
        print(f"  {name:15s} - {status}")
        if not installed:
            missing_core.append((name, cmd))
            mod_installed = False
    
    print()
    
    # 可选依赖
    print("[可选依赖]")
    optional_deps = [
        ('scipy', 'pip install scipy', '科学计算'),
        ('seaborn', 'pip install seaborn', '可视化增强'),
        ('sklearn', 'pip install scikit-learn', '机器学习'),
    ]
    
    for name, cmd, desc in optional_deps:
        installed, _ = check_dependency(name)
        status = "✓ 已安装" if installed else "○ 未安装（可选）"
        print(f"  {name:15s} - {status:20s} ({desc})")
    
    print()
    
    # 如果有缺失的核心依赖，提示安装
    if missing_core:
        print("="*60)
        print("  [警告] 缺少核心依赖！")
        print("="*60)
        print()
        print("请运行以下命令安装缺失的依赖：")
        for name, cmd in missing_core:
            print(f"  {cmd}")
        print()
        print("或者运行项目根目录下的 setup.bat 自动配置环境")
        print()
        print("按 Enter 键继续尝试运行...")
        input()
        print()
    
    return mod_installed

# 执行依赖检查
has_core_deps = print_dependency_status()

# =============================================================================
# 错误处理工具模块
# =============================================================================

def show_error_message(title, message, details=None):
    """
    显示友好的错误消息
    
    参数:
        title: 错误标题
        message: 错误消息
        details: 详细信息（可选）
    """
    print()
    print("="*70)
    print(f"  [错误] {title}")
    print("="*70)
    print()
    print(message)
    print()
    
    if details:
        print("详细信息：")
        print("-"*70)
        print(details)
        print()
    
    print("="*70)
    print()

def get_suggestion_for_error(error_type, error_msg):
    """
    根据错误类型提供建议
    
    参数:
        error_type: 错误类型
        error_msg: 错误消息
    
    返回:
        建议字符串
    """
    suggestions = {
        'ModuleNotFoundError': """
请检查依赖是否已安装：
1. 运行项目根目录下的 setup.bat 自动安装依赖
2. 或手动运行: pip install 缺失的模块名称
""",
        'FileNotFoundError': """
请检查：
1. 文件路径是否正确
2. 文件是否存在
3. 文件是否被其他程序占用
""",
        'PermissionError': """
请检查：
1. 是否有读写权限
2. 文件是否被其他程序占用
3. 输出目录是否可写
""",
        'ValueError': """
请检查：
1. 数据格式是否正确
2. 数据是否完整
3. 必需的数据列是否存在
""",
        'KeyError': """
请检查：
1. 数据中是否包含必需的列
2. 列名是否拼写正确
""",
        'MemoryError': """
数据量过大，建议：
1. 减少处理的数据量
2. 使用更小的数据文件
3. 增加系统内存
"""
    }
    
    for err_type, suggestion in suggestions.items():
        if err_type in error_type:
            return suggestion
    
    return """
请查看日志文件 well_log_processor.log 获取详细信息。
如问题持续存在，请联系技术支持。
"""

def handle_exception(exc_type, exc_value, exc_traceback, context="程序运行"):
    """
    统一处理异常
    
    参数:
        exc_type: 异常类型
        exc_value: 异常值
        exc_traceback: 异常堆栈
        context: 上下文描述
    """
    import traceback
    
    error_type = exc_type.__name__
    error_msg = str(exc_value)
    
    # 记录日志
    logger.error(f"{context}时出错: {error_type}: {error_msg}")
    logger.error("堆栈跟踪:")
    logger.error("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    
    # 显示友好错误
    show_error_message(
        f"{context}失败",
        f"错误类型: {error_type}\n错误信息: {error_msg}",
        get_suggestion_for_error(error_type, error_msg)
    )

# =============================================================================
# 主程序开始
# =============================================================================
import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib.colors import LogNorm, Normalize
import pandas as pd
import tkinter as tk
from tkinter import filedialog
import os
import datetime
import json
from pathlib import Path
import logging
import lasio
try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False
from matplotlib.lines import Line2D
import matplotlib.patches as patches

# 曲线名智能识别：基于 LAS 头注释（助记符/单位/API code）把厂商曲线名归一化为标准名
# 例：CNCF->CNL, ZDEN->DEN, DTC->DT, RD->RT, RMSL->R90, CALX->CAL
try:
    from curve_resolver import CurveResolver
    HAS_CURVE_RESOLVER = True
except ImportError:
    HAS_CURVE_RESOLVER = False

# 导入高级测井解释引擎
try:
    from advanced_interpretation import (
        InterpretationTemplates,
        AdvancedInterpretationEngine,
        create_interpretation_engine
    )
    HAS_ADVANCED_INTERPRETATION = True
except ImportError:
    HAS_ADVANCED_INTERPRETATION = False

# =============================================================================
# 增强的日志配置模块
# =============================================================================

def setup_logging():
    """
    配置日志系统
    
    功能:
        1. 同时输出到文件和控制台
        2. 文件日志按日期轮换
        3. 彩色控制台输出
        4. 详细的日志格式
    """
    import logging
    from logging.handlers import RotatingFileHandler
    import sys
    
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 获取logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    # 日志格式
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 文件日志处理器（按大小轮换）
    log_file = log_dir / "well_log_processor.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 控制台日志处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 记录启动信息
    logger.info("="*60)
    logger.info("  测井资料处理系统 - 日志系统启动")
    logger.info("="*60)
    logger.info(f"日志文件: {log_file.absolute()}")
    logger.info(f"Python版本: {sys.version}")
    
    return logger

# 初始化日志
logger = setup_logging()

# 设置matplotlib中文字体支持
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'WenQuanYi Micro Hei', 'Heiti TC', 'Arial Unicode MS'] # 中文字体
plt.rcParams['axes.unicode_minus'] = False # 解决负号显示问题
plt.rcParams['mathtext.default'] = 'regular' # 确保数学符号正确显示

# 统一刻度设置参数 - 刻度标签放在图头区内
TICK_PARAMS = {
    'axis': 'x',
    'top': False,  # 不显示默认刻度线
    'bottom': False,
    'labeltop': False,  # 不使用默认标签位置，手动设置
    'labelbottom': False,
    'pad': 1,
    'length': 0,  # 不显示tick标记
    'direction': 'in',
    'labelsize': 8
}

# 统一标签设置参数
LABEL_PARAMS = {
    'fontsize': 10,
    'labelpad': 2,
    'fontfamily': 'Microsoft YaHei'
}

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
            # 弹簧段校正配置
            'spring_correction': {
                'enabled': True,                    # 是否启用弹簧段校正
                'curves': ['MSFL', 'RHOB'],         # 要校正的曲线
                'depth_range': (2710, 2830),        # 弹簧段深度范围（可根据实际数据修改）
                'method': 'spline',                 # 校正方法: spline, moving_average, median
                'sensitivity': 3.0                  # 检测灵敏度
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
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        return save_path

# --- 数据加载类 ---
class DataLoader:
    """数据加载类"""
    
    def __init__(self):
        """初始化数据加载器"""
        self.data = None
        self.last_file_path = None
        self.file_info = None  # 统一的文件元信息 (LAS/DLIS)
        self.las_info = None   # 向后兼容别名（与 file_info 同步）
    
    def load_data(self, file_path):
        """加载测井数据（支持LAS/DLIS/CSV/XLSX格式）"""
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            
            logger.info(f"正在加载数据: {file_path}")
            
            if file_ext == '.csv':
                self.data = pd.read_csv(file_path)
                self.file_info = None
                self.las_info = None
            elif file_ext == '.las':
                try:
                    las = lasio.read(file_path)
                    self.data = las.df().reset_index()
                    # 曲线名归一化：厂商助记符(CNCF/ZDEN/DTC/RD...) -> 标准名(CNL/DEN/DT/RT...)
                    # 依据 LAS ~Curve 区的助记符、单位、API code 三级识别；
                    # 原始列保留不动，仅新增标准名列，保证可追溯。
                    if HAS_CURVE_RESOLVER:
                        try:
                            resolver = CurveResolver()
                            self.data = resolver.resolve(self.data, las=las, verbose=True)
                            self.curve_resolver = resolver
                            logger.info("曲线名归一化完成: 识别 %d 条, 未识别 %d 列",
                                        len(resolver.curve_meta), len(resolver.unresolved))
                        except Exception as e:
                            logger.warning("曲线名归一化失败（不影响后续处理）: %s", e)
                    info = self._extract_las_info(las)
                    self.file_info = info
                    self.las_info = info  # 向后兼容
                except ImportError:
                    logger.error("需要安装lasio库: pip install lasio")
                    return None
            elif file_ext == '.dlis':
                try:
                    import dlisio
                    with dlisio.load(str(file_path)) as f:
                        # 收集所有通道数据
                        curve_data = {}
                        for logical_file in f:
                            for frame in logical_file.frames:
                                for channel in frame.channels:
                                    ch_name = str(channel.name).strip() if hasattr(channel, 'name') else str(channel)
                                    try:
                                        curve_data[ch_name] = channel.curves()
                                    except Exception:
                                        pass
                        if not curve_data:
                            # 备用方式: 从顶层 channels() 遍历
                            f2 = dlisio.load(str(file_path))
                            for logical_file in f2:
                                for channel in logical_file.channels:
                                    ch_name = str(channel.name).strip() if hasattr(channel, 'name') else str(channel)
                                    try:
                                        curve_data[ch_name] = channel.curves()
                                    except Exception:
                                        pass
                            f2.close()
                        self.data = pd.DataFrame(curve_data) if curve_data else pd.DataFrame()
                    info = self._extract_dlis_info(str(file_path))
                    self.file_info = info
                    self.las_info = info  # 向后兼容
                except ImportError:
                    logger.error("需要安装dlisio库: pip install dlisio")
                    return None
                except Exception as e:
                    logger.error(f"DLIS文件读取失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
            elif file_ext in ('.xlsx', '.xls'):
                try:
                    self.data = pd.read_excel(file_path, engine='calamine')
                except (ValueError, ImportError):
                    if file_ext == '.xlsx':
                        self.data = pd.read_excel(file_path, engine='openpyxl')
                    else:
                        self.data = pd.read_excel(file_path)
                self.file_info = None
                self.las_info = None
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
            
            # 按深度排序（先精确匹配，再模糊匹配）
            depth_cols = ['MD', 'DEPTH', 'Depth', 'depth', 'DEPT', 'TDEP', 'tdep']
            depth_col = next((col for col in depth_cols if col in self.data.columns), None)
            # 模糊匹配：列名中包含 MD/DEPTH/DEPT 关键词
            if depth_col is None:
                depth_col = next(
                    (col for col in self.data.columns
                     if any(kw in str(col).upper() for kw in ['MD', 'DEPTH', 'DEPT'])),
                    None
                )
            if depth_col:
                # 确保深度列为数值类型
                self.data[depth_col] = pd.to_numeric(self.data[depth_col], errors='coerce')
                self.data = self.data.sort_values(depth_col).reset_index(drop=True)
                self.data = self.data.dropna(subset=[depth_col])
                # 统一深度列名为MD
                if depth_col != 'MD':
                    self.data = self.data.rename(columns={depth_col: 'MD'})
            
            # ========== 统一列名大小写（全部转换为大写）==========
            # 确保曲线名查找不受大小写影响，支持RHOB、NPHI等大写曲线名
            self.data.columns = [col.upper() for col in self.data.columns]
            
            # ========== 伽玛能谱衍生曲线计算 ==========
            # 如果有伽玛能谱数据（POTA钾、THOR钍、URAN铀），计算去铀伽玛GR_NOU
            # GR_NOU = POTA + THOR（钾+钍贡献，排除铀富集干扰）
            # 用于更准确计算泥质含量，区分砂泥岩
            
            # SGR→GR标准化：SGR是总伽玛的能谱测量值，可替代GR
            if 'SGR' in self.data.columns and 'GR' not in self.data.columns:
                self.data['GR'] = pd.to_numeric(self.data['SGR'], errors='coerce')
                logger.info("伽玛曲线: SGR → GR")
            
            if 'POTA' in self.data.columns and 'THOR' in self.data.columns:
                pota = pd.to_numeric(self.data['POTA'], errors='coerce')
                thor = pd.to_numeric(self.data['THOR'], errors='coerce')
                self.data['GR_NOU'] = (pota + thor).clip(lower=0)
                logger.info("伽玛能谱数据: 已计算去铀伽玛 GR_NOU = POTA + THOR")
                # 同时计算KTH（无铀伽马，与GR_NOU相同含义）
                if 'KTH' not in self.data.columns:
                    self.data['KTH'] = self.data['GR_NOU']
            if 'URAN' in self.data.columns and 'U' not in self.data.columns:
                # 统一铀曲线列名
                self.data['U'] = pd.to_numeric(self.data['URAN'], errors='coerce')
                logger.info("铀曲线: URAN → U")
            # 长石识别：POTA→K, THOR→TH
            if 'POTA' in self.data.columns and 'K' not in self.data.columns:
                self.data['K'] = pd.to_numeric(self.data['POTA'], errors='coerce')
            if 'THOR' in self.data.columns and 'TH' not in self.data.columns:
                self.data['TH'] = pd.to_numeric(self.data['THOR'], errors='coerce')
            
            logger.info(f"Data loaded successfully，共 {len(self.data)} records")
            logger.info(f"Loaded curves: {list(self.data.columns)}")
            if self.file_info:
                well_info = self.file_info.get('well', {})
                logger.info(f"File well info: {well_info}")
            
            # 数据加载后立即进行质量检测（QC）
            self.qc_report = self.run_quality_control()
            
            # 检测顶部/底部孔隙度曲线无效段（哨兵值 + 大段常值>=5m）
            self._detect_porosity_invalid_sections()
            
            return self.data
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run_quality_control(self):
        """数据质量检测模块（QC）- 根据测井原始资料验收国标进行质量评定"""
        if self.data is None:
            logger.error("数据未加载，无法进行质量检测")
            return None
        
        # 曲线别名映射（支持多种命名方式和行业常见名称）
        self.curve_aliases = {
            'depth': [
                'MD', 'DEPTH', 'Depth', 'depth', 'DEPT', 'TDEP', 'tdep',
                'Depth_m', 'DEPTH_M', 'MeasuredDepth', 'DEPT_M', 'depth_m'
            ],
            'gr': [
                'GR', 'GR_RAW', 'GR_COMP', 'GR_CORR', 'GAMMA', 'GRAP',
                'GR_EDTC', 'SGR', 'CGR', 'ECGR', 'HCGR', 'GRKT',
                'GRAT', 'GRBH', 'NGAM', 'GAMMA_RAY', 'GAMMARAY'
            ],
            'den': [
                'DEN', 'RHOB', 'DENSITY', 'RHOB_CORR', 'RHOB_COMP', 'RHO',
                'RHOZ', 'RHOM', 'DRHO', 'RHOB_RT', 'ZDEN', 'DEN_COMP',
                'DEN_CORR', 'BULK_DENSITY', 'ROB', 'DEN1', 'LDEN'
            ],
            'nphi': [
                'NPHI', 'CNL', 'NEUTRON', 'PHIN', 'NPHI_CORR', 'CNL_CORR',
                'PORN', 'TNPH', 'NPOR', 'NPH', 'NEU', 'NEUT', 'PHI_N',
                'NPHI_LS', 'NPHI_SS', 'NPHIL', 'HEN', 'NEUTRON_POROSITY'
            ],
            'ac': [
                'AC', 'DT', 'DTCO', 'Sonic', 'SONIC', 'DT_COMP', 'AC_COMP',
                'ACOUSTIC', 'DTC', 'DT24', 'DTSM', 'DTL', 'DT_SHEAR',
                'DT4P', 'DT4S', 'DTCO_SLOW', 'AC_SLOW', 'DTP', 'DTS',
                'delta_t', 'DELTAT', 'DTT', 'DT_COMPRESSIONAL'
            ],
            'pe': [
                'PE', 'PEF', 'PE_CORR', 'PEF_CORR', 'PHOTO', 'UPE',
                'PEFZ', 'PHOT', 'PEFL', 'PE_PHOTOELECTRIC', 'PHOTO_FACTOR'
            ],
            'rt': [
                # 深电阻率 - 侧向测井
                'RT', 'LLD', 'RLLD', 'LLD_RT', 'RLLD_RT',
                # 深电阻率 - 感应测井
                'RILD', 'ILD', 'ILD_DEEP', 'RILD_DEEP',
                # 深电阻率 - 阵列感应/阵列侧向
                'RDEEP', 'RLA5', 'AT90', 'AF90',
                'RLA1', 'RLA2', 'RLA3', 'RLA4',
                'HT01', 'HT02', 'HT03', 'HT04', 'HT05', 'HT06',
                'AT10', 'AT20', 'AT30', 'AT60', 'AT90_RAW',
                # 其他深电阻率别名
                'R90', 'RLD', 'DEEP_RES', 'DEEP_RESISTIVITY',
                'RES_DEEP', 'RT_HRLT', 'RT_DEEP', 'ILD_RAW', 'LLD_RAW'
            ],
            'lls': [
                # 浅电阻率 - 侧向测井
                'LLS', 'RLLS', 'LLS_RT', 'RLLS_CORR', 'RLLS_RT',
                # 中感应 - 感应测井（对应浅侧向）
                'RILM', 'ILM', 'ILM_CORR', 'RILM_CORR',
                # 其他浅电阻率别名
                'SHALLOW_RES', 'SHALLOW_RESISTIVITY', 'SHALLOW',
                'RSHAL', 'RLA3_S', 'RES_SHALLOW',
                'ILS', 'LLS_RAW', 'RILM_RAW'
            ],
            'msfl': [
                # 微球形聚焦
                'MSFL', 'MSFL_CORR', 'MSFL_RT', 'MSFL_COMP',
                'MSF', 'MICROSPHERICAL', 'MICRO_SPHERICAL',
                # 八侧向（感应测井配套微电阻率）
                'RLL8', 'LL8', 'LL8_CORR', 'RLL8_CORR',
                # 微侧向/邻近侧向
                'MLL', 'RMLL', 'PROX', 'RPROX',
                # 冲洗带电阻率通用
                'RXOZ', 'RXO', 'RMIC', 'MICRO',
                'MICRO_RES', 'RMICRO', 'RXO_CORR'
            ],
            'sp': [
                'SP', 'SP_CORR', 'SPONTANEOUS', 'SP_POTENTIAL',
                'SPL', 'SPDH', 'SP_RAW', 'SPONT', 'SP_POT',
                'SP_CALC', 'SP_FILT', 'SP_NORM'
            ],
            'cal': [
                'CAL', 'CALI', 'Caliper', 'CALIBER', 'CAL_CORR',
                'CAL1', 'CAL2', 'BS', 'BIT', 'HD1', 'HD2',
                'CALIPER1', 'CALIPER2', 'BITSIZE', 'BIT_SIZE',
                'CAL_AVG', 'CAL_MAX', 'CAL_MIN', 'CAVE', 'CAL_BIT'
            ],
            'por': [
                'POR', 'PHI', 'PHIE', 'PHID', 'POROSITY',
                'PHI_E', 'PHI_T', 'PHI_D', 'PHI_N', 'POR_EFF',
                'POR_TOT', 'PHI_S', 'POR_E', 'POROSITY_EFFECTIVE'
            ]
        }
        
        logger.info("=" * 60)
        logger.info("开始数据质量检测（QC）")
        logger.info("=" * 60)
        
        qc_report = {
            'total_records': len(self.data),
            'quality_level': 'UNKNOWN',
            'overall_score': 0,
            'check_items': {},
            'recommendations': []
        }
        
        # 1. 深度列检查
        depth_check = self._check_depth_column()
        qc_report['check_items']['depth_column'] = depth_check
        
        # 2. 数据完整性检查
        completeness_check = self._check_data_completeness()
        qc_report['check_items']['completeness'] = completeness_check
        
        # 3. 曲线有效性检查
        curves_check = self._check_curves_validity()
        qc_report['check_items']['curves_validity'] = curves_check
        
        # 4. 异常值检测
        outliers_check = self._detect_outliers()
        qc_report['check_items']['outliers'] = outliers_check
        
        # 5. 曲线相关性检查（用于识别弹簧段等问题）
        correlation_check = self._check_curve_correlation()
        qc_report['check_items']['correlation'] = correlation_check
        
        # 6. PE曲线质量检查（针对井径大导致PE虚高的问题）
        pe_check = self._check_pe_quality()
        qc_report['check_items']['pe_quality'] = pe_check
        
        # 7. 逐曲线质量评价（2012国标：SY/T 5132-2012）
        curve_quality_2012 = self._evaluate_curve_quality_2012()
        qc_report['check_items']['curve_quality_2012'] = curve_quality_2012
        
        # 7.1 密度曲线质量判断 → 是否优先使用密度孔隙度
        den_eval = curve_quality_2012.get('curve_evaluations', {}).get('den', {})
        den_grade = den_eval.get('grade', '不合格')
        if den_grade in ['优秀', '良好', '合格']:
            qc_report['density_porosity_priority'] = True
            qc_report['density_curve_quality'] = den_grade
            logger.info(f"密度曲线质量{den_grade}，将优先使用密度孔隙度（变骨架）")
        else:
            qc_report['density_porosity_priority'] = False
            qc_report['density_curve_quality'] = den_grade
            if den_eval:
                logger.warning(f"密度曲线质量{den_grade}，将使用中子孔隙度等其他方法")
        
        # 8. 综合质量评定
        qc_report = self._evaluate_overall_quality(qc_report)
        
        # 输出质量报告
        self._print_qc_report(qc_report)
        
        return qc_report
    
    def _find_curve(self, curve_type):
        """
        查找指定类型的曲线（支持大小写容错 + 模糊匹配）
        
        匹配策略（按优先级）：
        1. 精确匹配别名列表
        2. 大小写不敏感匹配
        3. 模糊匹配：列名包含关键标识词
        """
        if curve_type not in self.curve_aliases:
            return None
        
        aliases = self.curve_aliases[curve_type]
        
        # 获取所有列名（转换为小写用于比较）
        columns_lower = {col.lower(): col for col in self.data.columns}
        
        # 策略1&2：精确匹配 + 大小写不敏感
        for alias in aliases:
            # 先精确匹配
            if alias in self.data.columns:
                return alias
            # 大小写不敏感匹配
            alias_lower = alias.lower()
            if alias_lower in columns_lower:
                return columns_lower[alias_lower]
        
        # 策略3：模糊匹配——检查列名是否包含关键标识词
        # 为每种曲线类型定义一组关键词（小写）
        fuzzy_keywords = {
            'depth': ['dept', 'depth', 'md', 'tvd'],
            'gr':    ['gr', 'gamma', 'gam'],
            'den':   ['den', 'rho', 'density', 'rob'],
            'nphi':  ['nphi', 'cnl', 'neu', 'neut', 't nph', 'npor', 'ph i n'],
            'ac':    ['ac', 'dt', 'sonic', 'delta t', 'deltat', 'dtt'],
            'rt':    ['rt', 'lld', 'rild', 'ild', 'deep', 'r90', 'rla5', 'at90', 'rlld'],
            'lls':   ['lls', 'rlls', 'rilm', 'ilm', 'shallow', 'rshal'],
            'msfl':  ['msfl', 'micro', 'rxo', 'rll8', 'll8', 'mll', 'rmll', 'prox'],
            'sp':    ['sp', 'spont'],
            'cal':   ['cal', 'cali', 'bs', 'bit', 'hd'],
        }
        
        if curve_type in fuzzy_keywords:
            keywords = fuzzy_keywords[curve_type]
            for col_lower, col_original in columns_lower.items():
                for kw in keywords:
                    if kw in col_lower:
                        logger.info(f"模糊匹配曲线: '{col_original}' → 类型 '{curve_type}' (关键词 '{kw}')")
                        return col_original
        
        return None
    
    def _check_depth_column(self):
        """检查深度列"""
        result = {
            'passed': True,
            'message': '',
            'score': 100
        }
        
        depth_col = self._find_curve('depth')
        
        if not depth_col:
            result['passed'] = False
            result['message'] = '未找到深度列'
            result['score'] = 0
            return result
        
        depth_data = self.data[depth_col]
        
        # 检查是否有缺失值
        missing_count = depth_data.isnull().sum()
        if missing_count > 0:
            result['passed'] = False
            result['message'] = f'深度列有{missing_count}个缺失值'
            result['score'] = max(0, 100 - int(missing_count / len(depth_data) * 100))
        
        # 检查是否单调递增
        if not depth_data.is_monotonic_increasing:
            result['passed'] = False
            result['message'] = '深度列不是单调递增的'
            result['score'] = 60
        
        # 检查采样间隔是否均匀
        diffs = depth_data.diff().dropna()
        if len(diffs) > 0:
            std_ratio = diffs.std() / diffs.mean()
            if std_ratio > 0.1:
                result['message'] = f'采样间隔不均匀（标准差/均值={std_ratio:.2f}）'
                result['score'] = max(70, int(100 - std_ratio * 100))
        
        return result
    
    def _check_data_completeness(self):
        """检查数据完整性"""
        result = {
            'passed': True,
            'message': '',
            'score': 100,
            'missing_stats': {}
        }
        
        total_cells = self.data.size
        missing_cells = self.data.isnull().sum().sum()
        completeness_rate = (total_cells - missing_cells) / total_cells * 100
        
        result['missing_stats']['total_missing'] = int(missing_cells)
        result['missing_stats']['completeness_rate'] = round(completeness_rate, 2)
        result['missing_stats']['per_column'] = self.data.isnull().sum().to_dict()
        
        if completeness_rate < 50:
            result['passed'] = False
            result['message'] = f'数据完整性差（仅{completeness_rate:.1f}%）'
            result['score'] = 20
        elif completeness_rate < 80:
            result['message'] = f'数据完整性一般（{completeness_rate:.1f}%）'
            result['score'] = 60
        elif completeness_rate < 95:
            result['message'] = f'数据完整性良好（{completeness_rate:.1f}%）'
            result['score'] = 85
        
        return result
    
    def _check_curves_validity(self):
        """检查曲线有效性（支持曲线容错）"""
        result = {
            'passed': True,
            'message': '',
            'score': 100,
            'valid_curves': [],
            'invalid_curves': [],
            'curve_stats': {},
            'curve_types_found': {},
            'curve_types_missing': []
        }
        
        # 按曲线类型分组的正常值范围（放宽范围以适应实际数据）
        curve_type_ranges = {
            'gr': (0, 300),           # API
            'den': (0.8, 3.5),        # g/cm3（放宽下限以适应RHOB=0.88的情况）
            'nphi': (-0.2, 2.0),      # v/v（小数），放宽范围以适应异常值
            'ac': (30, 300),          # us/ft
            'pe': (0.5, 20),          # b/e
            'rt': (0.01, 100000),     # ohm·m
            'lls': (0.01, 100000),    # ohm·m
            'msfl': (0.01, 100000),   # ohm·m
            'sp': (-300, 300),        # mV
            'cal': (0, 60)            # in
        }
        
        # 记录每个曲线类型是否找到有效曲线
        for curve_type in curve_type_ranges:
            result['curve_types_found'][curve_type] = False
        
        numeric_cols = self.data.select_dtypes(include=['float64', 'int64']).columns
        
        for col in numeric_cols:
            # 跳过深度列
            if col in self.curve_aliases.get('depth', []):
                continue
            
            col_data = self.data[col].dropna()
            if len(col_data) == 0:
                result['invalid_curves'].append(col)
                result['curve_stats'][col] = {'status': 'empty', 'count': 0}
                continue
            
            min_val = col_data.min()
            max_val = col_data.max()
            mean_val = col_data.mean()
            
            # 查找该列属于哪种曲线类型
            curve_type = None
            for ctype, aliases in self.curve_aliases.items():
                if ctype == 'depth':
                    continue
                if col in aliases:
                    curve_type = ctype
                    break
            
            # ========== 无论数据是否有效，只要找到曲线类型就标记为已找到 ==========
            # 曲线类型找到与否独立于数据有效性检查
            if curve_type and curve_type in curve_type_ranges:
                result['curve_types_found'][curve_type] = True
            
            if curve_type and curve_type in curve_type_ranges:
                valid_min, valid_max = curve_type_ranges[curve_type]
                
                # 特殊处理：CNL可能以%为单位，需要转换
                if curve_type == 'nphi' and max_val > 10:
                    # 转换为小数
                    col_data_normalized = col_data / 100.0
                    min_val_norm = col_data_normalized.min()
                    max_val_norm = col_data_normalized.max()
                else:
                    min_val_norm, max_val_norm = min_val, max_val
                
                if min_val_norm < valid_min or max_val_norm > valid_max:
                    result['invalid_curves'].append(col)
                    result['curve_stats'][col] = {
                        'status': 'out_of_range',
                        'curve_type': curve_type,
                        'min': round(min_val, 3),
                        'max': round(max_val, 3),
                        'mean': round(mean_val, 3),
                        'valid_range': f'{valid_min}-{valid_max}'
                    }
                else:
                    result['valid_curves'].append(col)
                    result['curve_stats'][col] = {
                        'status': 'valid',
                        'curve_type': curve_type,
                        'min': round(min_val, 3),
                        'max': round(max_val, 3),
                        'mean': round(mean_val, 3)
                    }
                    result['curve_types_found'][curve_type] = True
            else:
                result['valid_curves'].append(col)
                result['curve_stats'][col] = {
                    'status': 'unknown_range',
                    'curve_type': curve_type,
                    'min': round(min_val, 3),
                    'max': round(max_val, 3),
                    'mean': round(mean_val, 3)
                }
        
        # 检查缺失的曲线类型
        for curve_type, found in result['curve_types_found'].items():
            if not found:
                result['curve_types_missing'].append(curve_type)
        
        # 评分逻辑：至少需要3种关键曲线类型（GR、密度、孔隙度）
        critical_types = ['gr', 'den', 'nphi']
        missing_critical = [ct for ct in critical_types if not result['curve_types_found'][ct]]
        
        if len(missing_critical) >= 2:
            result['passed'] = False
            result['message'] = f'缺少关键曲线类型: {", ".join(missing_critical)}，无法进行可靠解释'
            result['score'] = 30
        elif len(missing_critical) == 1:
            result['message'] = f'缺少曲线类型: {", ".join(missing_critical)}，解释结果可能受影响'
            result['score'] = 70
        elif len(result['invalid_curves']) > 0:
            result['passed'] = False
            result['message'] = f'发现{len(result["invalid_curves"])}条曲线超出正常范围: {", ".join(result["invalid_curves"])}'
            result['score'] = max(50, 100 - len(result['invalid_curves']) * 5)
        else:
            result['score'] = 100
        
        return result
    
    # 测井数据中常见的哨兵值（表示"未测量"，非真实测量值）
    # 这些值在质量检查中应被排除，不被当作异常值或负值错误
    _SENTINEL_VALUES = [-999.25, -999.9, -999.99, -9999, -9999.0, -9999.9, -9999.99,
                        -99999, -99999.0, -999, -999.0, -888.88, -888, -888.0,
                        -777.77, -777, -777.0]
    
    @staticmethod
    def _is_sentinel(series):
        """检测系列中的哨兵值（表示未测量的占位值）
        
        使用容差比较，避免浮点数精度问题。
        返回布尔Series，True表示该位置是哨兵值。
        """
        mask = pd.Series(False, index=series.index)
        for sv in DataLoader._SENTINEL_VALUES:
            mask = mask | np.isclose(series, sv, atol=1e-4)
        return mask
    
    @staticmethod
    def _detect_constant_segments(series, depth, min_length_m=5.0):
        """检测大段常值区间（>= min_length_m 米都为同一值）。
        
        返回布尔Series，True表示该位置属于大段常值段（应视为无效）。
        """
        mask = pd.Series(False, index=series.index)
        if len(series) < 2:
            return mask
        valid_mask = series.notna() & (~DataLoader._is_sentinel(series))
        # 只对非 NaN、非哨兵的值做游程检测
        s = series.copy()
        s[~valid_mask] = np.nan
        
        # 游程编码：标记变化点
        diff_flag = s.diff().fillna(0) != 0
        group_ids = diff_flag.cumsum()
        
        for gid, group in s.groupby(group_ids):
            if group.isna().all():
                continue
            if len(group) < 2:
                continue
            # 计算该段深度跨度
            idx = group.index
            d_start = depth.loc[idx[0]]
            d_end = depth.loc[idx[-1]]
            if abs(d_end - d_start) >= min_length_m:
                mask.loc[idx] = True
        
        return mask
    
    def _detect_porosity_invalid_sections(self):
        """检测顶部和底部孔隙度曲线无效段。
        
        当 NPHI、密度（RHOB/DEN）、声波（DT/DTCO/AC）三条曲线
        在同一深度点均为无效时，标记为孔隙度无效段。
        
        "无效"定义：
        - 哨兵值（-999.25 等）
        - 大段常值（>= 5 米内同一个值）
        
        返回：在 self.data 中新增 _POROSITY_VALID 列（bool），
              同时返回该列。
        """
        if self.data is None or len(self.data) == 0:
            return None
        
        data = self.data
        # 深度列
        depth_col = self._find_curve('depth')
        if depth_col is None or depth_col not in data.columns:
            logger.warning("孔隙度无效段检测：未找到深度列，跳过")
            return None
        depth = data[depth_col]
        
        # 三条孔隙度相关曲线
        curve_types = ['nphi', 'den', 'ac']
        invalid_flags = {}
        
        for ct in curve_types:
            col = self._find_curve(ct)
            if col is None or col not in data.columns:
                invalid_flags[ct] = pd.Series(True, index=data.index)  # 没有曲线=全部无效
                continue
            
            series = data[col]
            # 哨兵值
            sentinel_mask = self._is_sentinel(series)
            # 大段常值（>=5m）
            constant_mask = self._detect_constant_segments(series, depth, min_length_m=5.0)
            # 合并无效标记
            invalid_flags[ct] = sentinel_mask | constant_mask
        
        # 所有三条曲线都无效 → 孔隙度无效
        all_invalid = invalid_flags['nphi'] & invalid_flags['den'] & invalid_flags['ac']
        data['_POROSITY_VALID'] = ~all_invalid
        
        invalid_count = all_invalid.sum()
        total_count = len(data)
        logger.info(f"孔隙度无效段检测完成: {invalid_count}/{total_count} 点无效 "
                    f"({invalid_count/total_count*100:.1f}%)")
        
        # 报告顶部/底部无效段深度范围
        if invalid_count > 0:
            invalid_depth = depth[all_invalid]
            logger.info(f"  顶部/底部无效段深度: {invalid_depth.min():.1f} - {invalid_depth.max():.1f} m")
        
        return data['_POROSITY_VALID']
    
    def _detect_outliers(self):
        """检测异常值（基于IQR方法）
        
        注意：-999.25等哨兵值（表示未测量）会被排除，不会被当作异常值。
        """
        result = {
            'passed': True,
            'message': '',
            'score': 100,
            'outlier_stats': {}
        }
        
        numeric_cols = self.data.select_dtypes(include=['float64', 'int64']).columns
        total_outliers = 0
        
        for col in numeric_cols:
            if col in ['MD', 'DEPTH', 'Depth', 'depth', 'DEPT']:
                continue
            
            col_data = self.data[col].dropna()
            if len(col_data) < 4:
                continue
            
            # 排除哨兵值（-999.25等习惯表示未测量的占位值）
            sentinel_mask = self._is_sentinel(col_data)
            clean_data = col_data[~sentinel_mask]
            sentinel_count = sentinel_mask.sum()
            
            if len(clean_data) < 4:
                continue
            
            Q1 = clean_data.quantile(0.25)
            Q3 = clean_data.quantile(0.75)
            IQR = Q3 - Q1
            
            if IQR == 0:
                continue
            
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers = clean_data[(clean_data < lower_bound) | (clean_data > upper_bound)]
            outlier_ratio = len(outliers) / len(clean_data) * 100
            
            result['outlier_stats'][col] = {
                'count': len(outliers),
                'ratio': round(outlier_ratio, 2),
                'lower_bound': round(lower_bound, 3),
                'upper_bound': round(upper_bound, 3)
            }
            if sentinel_count > 0:
                result['outlier_stats'][col]['sentinel_count'] = int(sentinel_count)
            
            total_outliers += len(outliers)
            
            if outlier_ratio > 10:
                result['passed'] = False
        
        if total_outliers > 0:
            total_ratio = total_outliers / (len(self.data) * len(numeric_cols)) * 100
            if total_ratio > 5:
                result['message'] = f'异常值较多（占比{total_ratio:.1f}%），建议检查数据质量'
                result['score'] = 60
            elif total_ratio > 1:
                result['message'] = f'存在少量异常值（占比{total_ratio:.1f}%）'
                result['score'] = 85
        
        return result
    
    def _check_curve_correlation(self):
        """检查曲线相关性（用于识别弹簧段等问题，支持曲线容错）"""
        result = {
            'passed': True,
            'message': '',
            'score': 100,
            'correlation_matrix': {},
            'suspicious_segments': []
        }
        
        # 需要检查相关性的曲线类型对
        curve_type_pairs = [
            ('gr', 'sp'),       # 泥质指示曲线应该相关
            ('den', 'den'),     # 密度曲线应该一致（同一类型的不同命名）
            ('ac', 'ac'),       # 声波曲线应该一致（同一类型的不同命名）
            ('rt', 'rt'),       # 深电阻率应该一致（同一类型的不同命名）
            ('gr', 'pe')        # GR和PE在砂泥岩剖面应该有相关性
        ]
        
        for type1, type2 in curve_type_pairs:
            # 查找实际曲线名
            curve1 = self._find_curve(type1)
            curve2 = self._find_curve(type2)
            
            # 如果是同一类型，找两个不同的列名
            if type1 == type2 and curve1:
                # 找同一类型的另一个不同列
                other_cols = [c for c in self.curve_aliases[type1] 
                             if c in self.data.columns and c != curve1]
                if other_cols:
                    curve2 = other_cols[0]
                else:
                    curve2 = None
            
            if curve1 and curve2 and curve1 != curve2:
                corr = self.data[[curve1, curve2]].corr().iloc[0, 1]
                result['correlation_matrix'][f'{curve1}-{curve2}'] = round(corr, 3)
                
                # GR和SP应该正相关（泥岩时两者都高）
                if type1 == 'gr' and type2 == 'sp':
                    if corr < 0.3:
                        result['suspicious_segments'].append(f'{curve1}与{curve2}相关性低（{corr:.3f}）')
                
                # 同一类型的不同曲线应该高度相关（如DEN和RHOB）
                elif type1 == type2:
                    if abs(corr) < 0.8:
                        result['suspicious_segments'].append(f'{curve1}与{curve2}一致性差（{corr:.3f}）')
        
        if len(result['suspicious_segments']) > 0:
            result['passed'] = False
            result['message'] = '发现曲线相关性异常，可能存在弹簧段或数据质量问题'
            result['score'] = 70
        
        return result
    
    def _check_pe_quality(self):
        """检查PE曲线质量（针对井径大导致PE虚高的问题，支持曲线容错）"""
        result = {
            'passed': True,
            'message': '',
            'score': 100,
            'pe_valid': True,
            'suspicious_points': 0,
            'total_points': 0,
            'pe_col': None,
            'den_col': None
        }
        
        # 使用曲线容错查找PE和密度曲线
        pe_col = self._find_curve('pe')
        den_col = self._find_curve('den')
        
        result['pe_col'] = pe_col
        result['den_col'] = den_col
        
        if not pe_col:
            result['message'] = '未找到PE曲线（PE/PEF）'
            return result
        
        if not den_col:
            result['message'] = '缺少密度曲线（DEN/RHOB），无法检查PE质量'
            return result
        
        pe_data = self.data[pe_col].dropna()
        den_data = self.data[den_col].dropna()
        
        result['total_points'] = len(pe_data)
        
        # 检查PE值是否合理
        # 砂泥岩剖面中，PE一般在1.5-3.0之间
        # 碳酸盐岩剖面中，PE一般在3.0-6.0之间
        
        # 统计PE>3的点中密度<2.65的比例（可能是PE虚高）
        valid_mask = self.data[pe_col].notnull() & self.data[den_col].notnull()
        valid_data = self.data[valid_mask]
        
        suspicious_mask = (valid_data[pe_col] > 3.0) & (valid_data[den_col] < 2.65)
        suspicious_count = suspicious_mask.sum()
        suspicious_ratio = suspicious_count / len(valid_data) * 100 if len(valid_data) > 0 else 0
        
        result['suspicious_points'] = int(suspicious_count)
        result['suspicious_ratio'] = round(suspicious_ratio, 2)
        
        if suspicious_ratio > 20:
            result['passed'] = False
            result['pe_valid'] = False
            result['message'] = f'PE曲线可能存在虚高问题（{suspicious_ratio:.1f}%的点PE>3但密度<2.65），建议检查井径和数据质量'
            result['score'] = 50
        elif suspicious_ratio > 10:
            result['pe_valid'] = False
            result['message'] = f'PE曲线存在部分异常（{suspicious_ratio:.1f}%的点PE>3但密度<2.65）'
            result['score'] = 75
        
        return result
    
    def _evaluate_curve_quality_2012(self):
        """
        依据SY/T 5132-2012测井原始资料质量要求，逐曲线进行质量评价
        
        评价规则：
        - 空值检测：-999.25或-99999表示没有测量（不参与评价）
        - 平头检测：连续>=3个点值相同视为平头（flat）
        - 异常值检测：IQR方法检测离群值（outlier）
        - 负值规则：SP可出现负值，中子(NPHI)允许少量负值，其他曲线负值视为错误
        - 评分：优秀>=90，良好>=80，合格>=60，不合格<60
        - 扣分：每个异常值-1分，每个平头段-5分，每个错误负值-10分
        - BS（钻头尺寸）不参与评价
        """
        result = {
            'grade_map': {'优秀': 'EXCELLENT', '良好': 'GOOD', '合格': 'FAIR', '不合格': 'BAD'},
            'curve_evaluations': {},
            'summary': {'total': 0, '优秀': 0, '良好': 0, '合格': 0, '不合格': 0}
        }
        
        # 定义需要评价的曲线及其参数
        # (曲线类型, 期望刻度范围, 负值规则)
        curve_definitions = {
            'sp':   {'display': 'SP',         'range': (-300, 300),   'allow_negative': True,  'negative_max_ratio': None},
            'gr':   {'display': 'GR',         'range': (0, 300),      'allow_negative': False, 'negative_max_ratio': 0.0},
            'cal':  {'display': 'CAL',        'range': (6, 16),       'allow_negative': False, 'negative_max_ratio': 0.0},
            'den':  {'display': 'DEN/RHOB',   'range': (1.5, 3.0),    'allow_negative': False, 'negative_max_ratio': 0.0},
            'nphi': {'display': 'NPHI/CNL',   'range': (-0.15, 1.0),  'allow_negative': True,  'negative_max_ratio': 0.10},
            'ac':   {'display': 'DT/AC',      'range': (30, 200),     'allow_negative': False, 'negative_max_ratio': 0.0},
            'pe':   {'display': 'PE/PEF',     'range': (0.5, 15),     'allow_negative': False, 'negative_max_ratio': 0.0},
            'rt':   {'display': 'RT/LLD/ILD', 'range': (0.1, 100000), 'allow_negative': False, 'negative_max_ratio': 0.0},
            'lls':  {'display': 'LLS',        'range': (0.1, 100000), 'allow_negative': False, 'negative_max_ratio': 0.0},
            'msfl': {'display': 'MSFL',       'range': (0.1, 100000), 'allow_negative': False, 'negative_max_ratio': 0.0},
        }
        
        # 空值标记（表示未测量）—— 与 _SENTINEL_VALUES 保持同步
        # 使用 _is_sentinel() 做容差比较，避免浮点数精度问题
        
        for curve_type, cfg in curve_definitions.items():
            # 查找实际列名
            col = self._find_curve(curve_type)
            if col is None:
                # 曲线不存在则跳过
                continue
            
            eval_result = {'curve': col, 'curve_type': curve_type, 'display': cfg['display']}
            result['curve_evaluations'][curve_type] = eval_result
            result['summary']['total'] += 1
            
            col_data = self.data[col].copy()
            total_points = len(col_data)
            eval_result['total_points'] = total_points
            
            if total_points == 0:
                eval_result['grade'] = '不合格'
                eval_result['score'] = 0
                eval_result['message'] = '曲线无数据'
                result['summary']['不合格'] += 1
                continue
            
            base_score = 100
            issues = []
            
            # ========== 1. 空值检测 ==========
            # 使用容差比较检测哨兵值（-999.25等习惯表示未测量的占位值）
            null_mask = self._is_sentinel(col_data)
            
            null_count = null_mask.sum()
            null_ratio = null_count / total_points if total_points > 0 else 0
            
            # 有效数据（排除空值标记和NaN）
            effective_mask = (~null_mask) & col_data.notna()
            effective_data = col_data[effective_mask]
            effective_count = len(effective_data)
            eval_result['null_count'] = int(null_count)
            eval_result['null_ratio'] = round(null_ratio, 4)
            eval_result['effective_count'] = effective_count
            eval_result['effective_ratio'] = round(effective_count / total_points, 4) if total_points > 0 else 0
            
            if effective_count < 10:
                eval_result['grade'] = '不合格'
                eval_result['score'] = max(0, 100 - null_count)
                eval_result['message'] = f'大量空值' if null_count > 0 else '有效数据极少'
                result['summary']['不合格'] += 1
                continue
            
            if null_ratio > 0.3:
                issues.append(f'空值过多({null_ratio:.1%})')
                # 大量空值不一定是数据问题，可能是未测量的深度段
            
            # ========== 2. 负值检测 ==========
            negative_mask = effective_data < 0
            negative_count = negative_mask.sum()
            negative_ratio = negative_count / effective_count if effective_count > 0 else 0
            eval_result['negative_count'] = int(negative_count)
            eval_result['negative_ratio'] = round(negative_ratio, 4)
            
            if negative_count > 0:
                if not cfg['allow_negative']:
                    # 严格不允许负值：负值=错误
                    base_score -= min(10 * negative_count, 50)  # 最多扣50分
                    issues.append(f'负值错误({negative_count}点)')
                elif cfg['negative_max_ratio'] is not None and negative_ratio > cfg['negative_max_ratio']:
                    # NPHI允许少量负值：超过阈值扣分
                    excess_ratio = negative_ratio - cfg['negative_max_ratio']
                    base_score -= int(excess_ratio * 200)  # 每超额1%扣2分
                    if excess_ratio > 0.05:
                        issues.append(f'负值偏多({negative_ratio:.1%})')
                elif cfg['allow_negative'] and cfg['negative_max_ratio'] is None:
                    # SP允许负值：不扣分，只记录
                    pass
            
            # ========== 3. 平头检测（连续>=3点相同值）==========
            flat_segments = 0
            flat_points = 0
            if effective_count >= 3:
                # 只检测有效数据中的连续相同值
                values = effective_data.values
                i = 0
                while i < len(values):
                    run_start = i
                    while i < len(values) - 1 and values[i] == values[i + 1]:
                        i += 1
                    run_length = i - run_start + 1
                    if run_length >= 3:
                        flat_segments += 1
                        flat_points += run_length
                    i += 1
            
            flat_ratio = flat_points / effective_count if effective_count > 0 else 0
            eval_result['flat_segments'] = flat_segments
            eval_result['flat_points'] = flat_points
            eval_result['flat_ratio'] = round(flat_ratio, 4)
            
            if flat_segments > 0:
                flat_penalty = min(flat_segments * 5, 40)  # 每个平头段-5分，最多-40
                base_score -= flat_penalty
                if flat_ratio > 0.3:
                    issues.append(f'平头严重({flat_ratio:.1%}，{flat_segments}段)')
                elif flat_segments >= 3:
                    issues.append(f'平头段较多({flat_segments}段)')
                elif flat_segments > 0:
                    issues.append(f'平头({flat_segments}段{flat_points}点)')
            
            # ========== 4. 异常值检测（IQR方法）==========
            if effective_count >= 4:
                Q1 = effective_data.quantile(0.25)
                Q3 = effective_data.quantile(0.75)
                IQR = Q3 - Q1
                
                outlier_count = 0
                if IQR > 0:
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR
                    outlier_mask = (effective_data < lower_bound) | (effective_data > upper_bound)
                    outlier_count = outlier_mask.sum()
                
                outlier_ratio = outlier_count / effective_count
                eval_result['outlier_count'] = int(outlier_count)
                eval_result['outlier_ratio'] = round(outlier_ratio, 4)
                eval_result['Q1'] = round(float(Q1), 3)
                eval_result['Q3'] = round(float(Q3), 3)
                eval_result['IQR'] = round(float(IQR), 3)
                
                if outlier_count > 0:
                    base_score -= min(outlier_count, 30)  # 每个异常值-1分，最多-30
                    if outlier_ratio > 0.15:
                        issues.append(f'异常值严重({outlier_ratio:.1%})')
                    elif outlier_ratio > 0.05:
                        issues.append(f'异常值偏多({outlier_ratio:.1%})')
            
            # ========== 5. 基本统计 ==========
            eval_result['min'] = round(float(effective_data.min()), 3)
            eval_result['max'] = round(float(effective_data.max()), 3)
            eval_result['mean'] = round(float(effective_data.mean()), 3)
            eval_result['std'] = round(float(effective_data.std()), 3)
            
            # ========== 6. 综合评分与定级 ==========
            base_score = max(0, min(100, base_score))
            eval_result['score'] = base_score
            eval_result['issues'] = issues
            
            if base_score >= 90:
                grade = '优秀'
            elif base_score >= 80:
                grade = '良好'
            elif base_score >= 60:
                grade = '合格'
            else:
                grade = '不合格'
            
            eval_result['grade'] = grade
            eval_result['grade_en'] = result['grade_map'][grade]
            eval_result['message'] = '; '.join(issues) if issues else '数据质量良好'
            
            result['summary'][grade] += 1
        
        # 汇总
        all_scores = [v['score'] for v in result['curve_evaluations'].values() if 'score' in v]
        if all_scores:
            result['overall_score'] = round(sum(all_scores) / len(all_scores), 1)
            result['min_score'] = min(all_scores)
            result['max_score'] = max(all_scores)
        
        return result
    
    def _evaluate_overall_quality(self, qc_report):
        """综合质量评定（含2012国标逐曲线评价和密度优先判断）"""
        scores = []
        
        for item, check_result in qc_report['check_items'].items():
            if 'score' in check_result:
                scores.append(check_result['score'])
            # 2012逐曲线评价也纳入综合评分
            elif item == 'curve_quality_2012' and 'overall_score' in check_result:
                scores.append(check_result['overall_score'])
        
        if len(scores) == 0:
            qc_report['overall_score'] = 0
            qc_report['quality_level'] = 'UNKNOWN'
            return qc_report
        
        overall_score = int(sum(scores) / len(scores))
        qc_report['overall_score'] = overall_score
        
        # 根据国标评定质量等级
        if overall_score >= 90:
            qc_report['quality_level'] = 'EXCELLENT'  # 优秀
        elif overall_score >= 80:
            qc_report['quality_level'] = 'GOOD'       # 良好
        elif overall_score >= 70:
            qc_report['quality_level'] = 'FAIR'       # 合格
        elif overall_score >= 60:
            qc_report['quality_level'] = 'POOR'       # 较差
        else:
            qc_report['quality_level'] = 'BAD'        # 不合格
        
        # 生成建议
        recs = []
        if qc_report['quality_level'] == 'EXCELLENT':
            recs = ['数据质量优秀，可以直接进行解释']
        elif qc_report['quality_level'] == 'GOOD':
            recs = ['数据质量良好，建议在解释前检查少量异常值']
        elif qc_report['quality_level'] == 'FAIR':
            recs = [
                '数据质量合格，但存在一些问题，建议：',
                '1. 检查异常值较多的曲线',
                '2. 确认PE曲线是否存在虚高问题',
                '3. 检查弹簧段和数据跳变'
            ]
        elif qc_report['quality_level'] == 'POOR':
            recs = [
                '数据质量较差，建议：',
                '1. 重新检查原始数据文件',
                '2. 检查仪器校准和环境校正',
                '3. 考虑重新采集数据'
            ]
        else:
            recs = [
                '数据质量不合格，无法进行可靠解释，建议：',
                '1. 重新检查原始数据文件',
                '2. 确认仪器工作状态',
                '3. 考虑重新采集数据'
            ]
        
        # 添加密度孔隙度优先建议
        den_priority = qc_report.get('density_porosity_priority', False)
        if den_priority:
            recs.append('密度曲线质量合格，优先使用密度孔隙度（变骨架）')
        else:
            recs.append('密度曲线质量不佳，孔隙度计算将以中子孔隙度或交汇法为主')
        
        qc_report['recommendations'] = recs
        
        return qc_report
    
    def _print_qc_report(self, qc_report):
        """打印质量报告"""
        # 质量等级中文映射
        level_cn_map = {
            'EXCELLENT': '优秀',
            'GOOD': '良好',
            'FAIR': '合格',
            'POOR': '较差',
            'BAD': '不合格',
            'UNKNOWN': '未知'
        }
        
        quality_level_cn = level_cn_map.get(qc_report['quality_level'], qc_report['quality_level'])
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("数据质量检测报告（QC Report）")
        logger.info("=" * 60)
        
        logger.info(f"总记录数: {qc_report['total_records']}")
        logger.info(f"综合评分: {qc_report['overall_score']}")
        
        # 醒目显示质量评级
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"【质量评级】: {quality_level_cn} ({qc_report['quality_level']})")
        logger.info("=" * 60)
        logger.info("")
        
        for item, check_result in qc_report['check_items'].items():
            # 2012逐曲线评价单独处理
            if item == 'curve_quality_2012':
                continue
            
            status = "✓ 通过" if check_result.get('passed', True) else "✗ 不通过"
            score = check_result.get('score', '-')
            message = check_result.get('message', '')
            
            logger.info(f"【{item}】")
            logger.info(f"  状态: {status}")
            logger.info(f"  评分: {score}")
            if message:
                logger.info(f"  说明: {message}")
            
            # 打印详细统计
            if 'missing_stats' in check_result:
                stats = check_result['missing_stats']
                logger.info(f"  完整性: {stats['completeness_rate']}%")
                logger.info(f"  缺失值: {stats['total_missing']}个")
            
            if 'valid_curves' in check_result:
                logger.info(f"  有效曲线: {len(check_result['valid_curves'])}条")
                if check_result['invalid_curves']:
                    logger.info(f"  无效曲线: {', '.join(check_result['invalid_curves'])}")
            
            if 'suspicious_points' in check_result:
                logger.info(f"  可疑点: {check_result['suspicious_points']}个 ({check_result.get('suspicious_ratio', 0):.1f}%)")
            
            logger.info("")
        
        # ========== 2012国标逐曲线质量评价 ==========
        curve_eval = qc_report['check_items'].get('curve_quality_2012', {})
        if curve_eval and 'curve_evaluations' in curve_eval:
            logger.info("=" * 60)
            logger.info("【2012国标逐曲线质量评价（SY/T 5132-2012）】")
            logger.info("-" * 60)
            
            # 表头
            logger.info(f"{'曲线':<20s} {'评分':>5s} {'等级':<8s} {'异常值':>6s} {'平头段':>6s} {'负值':>6s} {'空值比':>7s}")
            logger.info("-" * 60)
            
            for ctype, ev in curve_eval['curve_evaluations'].items():
                name = f"{ev.get('display', ctype)} ({ev.get('curve', '')})"
                if len(name) > 19:
                    name = name[:19]
                score = ev.get('score', 'N/A')
                grade = ev.get('grade', 'N/A')
                outliers = ev.get('outlier_count', '-')
                flats = ev.get('flat_segments', '-')
                negatives = ev.get('negative_count', '-')
                null_ratio = f"{ev.get('null_ratio', 0)*100:.1f}%" if ev.get('null_ratio') else '0%'
                
                # 着色标记（通过日志等级表现）
                grade_mark = f"[{grade}]"
                logger.info(f"{name:<20s} {score:>4}  {grade_mark:<8s} {str(outliers):>6s} {str(flats):>6s} {str(negatives):>6s} {null_ratio:>7s}")
                
                # 打印问题详情
                issues = ev.get('issues', [])
                if issues:
                    for issue in issues:
                        logger.info(f"    ⚠ {issue}")
            
            logger.info("-" * 60)
            
            # 汇总
            summary = curve_eval.get('summary', {})
            logger.info("逐曲线评价汇总:")
            for grade_label in ['优秀', '良好', '合格', '不合格']:
                count = summary.get(grade_label, 0)
                if count > 0:
                    logger.info(f"  {grade_label}: {count}条曲线")
            logger.info(f"  综合评价分: {curve_eval.get('overall_score', 'N/A')}")
            logger.info("")
        
        # ========== 密度孔隙度优先级 ==========
        den_priority = qc_report.get('density_porosity_priority', False)
        den_quality = qc_report.get('density_curve_quality', '未知')
        if den_priority:
            logger.info(f"密度曲线质量评定: {den_quality} → 【优先使用密度孔隙度（变骨架）】")
        else:
            logger.info(f"密度曲线质量评定: {den_quality} → 【密度曲线不可靠，将使用其他孔隙度方法】")
        
        logger.info("")
        logger.info("建议:")
        for rec in qc_report['recommendations']:
            logger.info(f"  {rec}")
        
        logger.info("=" * 60)
        logger.info("质量检测完成")
        logger.info("=" * 60)
    
    # =========================================================================
    # 统一的字段定义 — 所有信息字段搜索策略
    # 优先级: ~WELL > ~PARAMETER > ~CURVE
    # =========================================================================
    
    # 井信息字段: LAS助记符 -> 输出字段名
    _WELL_FIELDS = {
        'COMP.': 'company',
        'CTRY.': 'country',
        'FLD.': 'field_name',
        'WELL.': 'well_name',
        'STAT.': 'state_or_province',
        'PDAT.': 'permanent_datum',
        'ENGI.': 'engineers_name',
        'LUN': 'logging_unit_name',
        'SRVC': 'service_company_name',
        'DATE': 'date',
        'API': 'api_number',
        'UOM': 'unit_of_measure',
        'FLD': 'field_name_alt',
        'PROV': 'province',
        'TDD': 'total_depth_driller',
        'TDL': 'total_depth_logger',
        'STRT': 'start_depth',
        'STOP': 'stop_depth',
    }
    
    # 参数信息字段: LAS助记符 -> 输出字段名
    _PARAM_FIELDS = {
        'EGL': 'elevation_ground_level',
        'EKB': 'elevation_kelly_bushing',
        'BS': 'bit_size',
        'CSIZ': 'current_casing_size',
        'DFT': 'drilling_fluid_type',
        'DFD': 'drilling_fluid_density',
        'DFV': 'drilling_fluid_viscosity',
        'DFPH': 'drilling_fluid_ph',
        'DFL': 'drilling_fluid_loss',
        'RMCS': 'resistivity_mud_cake_sample',
        'RMFS': 'resistivity_mud_filtrate_sample',
        'RMB': 'resistivity_mud_bht',
        'BSDF': 'bit_size_depth_from',
        'BSDT': 'bit_size_depth_to',
        'CDF': 'casing_depth_from',
        'CADT': 'casing_depth_to',
    }
    
    def _extract_las_info(self, las):
        """从LAS文件中提取所有元信息。
        
        所有字段在 ~WELL, ~PARAMETER, ~CURVE 三个区中按优先级搜索:
        WELL > PARAMETER > CURVE（任一命中即停止）。
        
        返回:
            {'well': {...}, 'parameter': {...}}
        """
        las_info = {
            'well': {},
            'parameter': {}
        }
        
        def _generate_key_variants(key):
            """生成多种键名变体（有/无小数点、大小写组合）"""
            variants = [key, key.lower()]
            key_without_dot = key.replace('.', '')
            if '.' not in key:
                variants.extend([key + '.', key.lower() + '.'])
            else:
                variants.extend([key_without_dot, key_without_dot.lower()])
            return variants
        
        def _find_in_section(section, key):
            """在LAS某区（dict-like）中搜索，返回字符串值或None"""
            if not section:
                return None
            for variant in _generate_key_variants(key):
                try:
                    item = section[variant]
                except (KeyError, IndexError, TypeError):
                    continue
                # 提取值: HeaderItem/CurveItem 有 .value 属性
                if hasattr(item, 'value'):
                    val = item.value
                else:
                    val = item
                if val is not None and str(val).strip():
                    return str(val).strip()
            return None
        
        def _find_in_curves(las, key):
            """在 ~CURVE 区按助记符搜索，返回曲线描述或单位"""
            if not las.curves:
                return None
            for variant in _generate_key_variants(key):
                try:
                    curve = las.curves[variant]
                    for attr in ('descr', 'unit'):
                        if hasattr(curve, attr) and getattr(curve, attr, None):
                            v = str(getattr(curve, attr)).strip()
                            if v:
                                return v
                except (KeyError, IndexError, TypeError):
                    continue
            return None
        
        # 统一搜索函数：按优先级 well > params > curves
        def _search_all(las, key):
            v = _find_in_section(las.well, key)
            if v is not None:
                return v
            v = _find_in_section(las.params, key)
            if v is not None:
                return v
            return _find_in_curves(las, key)
        
        # 提取井信息 — 所有字段在三个区中搜索
        for las_key, field_name in self._WELL_FIELDS.items():
            value = _search_all(las, las_key)
            if value:
                las_info['well'][field_name] = value
        
        # 提取参数信息 — 所有字段在三个区中搜索
        for las_key, field_name in self._PARAM_FIELDS.items():
            value = _search_all(las, las_key)
            if value:
                las_info['parameter'][field_name] = value
        
        return las_info
    
    def _extract_dlis_info(self, file_path):
        """从DLIS文件中提取所有元信息。
        
        数据来源优先级: Origin > Frame > Channel。
        返回与 _extract_las_info 相同的结构:
            {'well': {...}, 'parameter': {...}}
        """
        info = {
            'well': {},
            'parameter': {}
        }
        try:
            import dlisio
        except ImportError:
            logger.warning("dlisio库未安装，无法提取DLIS元信息: pip install dlisio")
            return info
        
        try:
            with dlisio.load(file_path) as f:
                logical_files = list(f)
                if not logical_files:
                    return info
                lf = logical_files[0]
                
                # Origin → well info 字段映射
                # dlisio 属性名可能因版本而异，故用 hasattr 探测
                origin_fields = [
                    ('company', 'company'),
                    ('well_name', 'well_name'),
                    ('well_id', 'api_number'),
                    ('field_name', 'field_name'),
                    ('producer', 'company'),
                    ('run_number', 'run_number'),
                    ('service_company', 'service_company_name'),
                ]
                
                if hasattr(lf, 'origins') and lf.origins:
                    origin = lf.origins[0]
                    for attr, field_name in origin_fields:
                        try:
                            val = getattr(origin, attr, None)
                            if val is not None and str(val).strip():
                                info['well'][field_name] = str(val).strip()
                        except Exception:
                            pass
                
                # Frame → 深度范围（start_depth, stop_depth）
                if hasattr(lf, 'frames') and lf.frames:
                    for frame in lf.frames:
                        try:
                            if hasattr(frame, 'index_type') and frame.index_type:
                                info['well']['index_type'] = str(frame.index_type).strip()
                        except Exception:
                            pass
                
                # Channel → parameter info（曲线描述/单位）
                if hasattr(lf, 'channels') and lf.channels:
                    param_info = {}
                    for channel in lf.channels:
                        try:
                            ch_name = str(channel.name).strip() if hasattr(channel, 'name') else ''
                            ch_unit = str(channel.units).strip() if hasattr(channel, 'units') and channel.units else ''
                            ch_desc = str(channel.long_name).strip() if hasattr(channel, 'long_name') and channel.long_name else ''
                            if ch_name:
                                param_info[ch_name] = {
                                    'unit': ch_unit,
                                    'description': ch_desc,
                                }
                        except Exception:
                            continue
                    if param_info:
                        info['parameter']['channel_info'] = param_info
                
                # 尝试从 fileheader / origin 提取更多信息
                for origin_attr in dir(lf.origins[0]) if (hasattr(lf, 'origins') and lf.origins) else []:
                    if origin_attr.startswith('_'):
                        continue
                    # 已知字段已在上面处理，跳过
                    known = {f[0] for f in origin_fields}
                    if origin_attr.lower() in known:
                        continue
                    try:
                        val = getattr(lf.origins[0], origin_attr, None)
                        if val is not None and str(val).strip():
                            info['parameter'][origin_attr] = str(val).strip()
                    except Exception:
                        pass
                
                return info
        except Exception as e:
            logger.warning(f"DLIS元信息提取失败: {e}")
            return info
    
    def get_las_well_info(self):
        """获取文件井信息（LAS/DLIS统一）"""
        info = self.file_info or self.las_info
        if info and 'well' in info:
            return info['well']
        return None
    
    def get_las_parameter_info(self):
        """获取文件参数信息（LAS/DLIS统一）"""
        info = self.file_info or self.las_info
        if info and 'parameter' in info:
            return info['parameter']
        return None
    
    def get_file_info(self):
        """获取统一的文件元信息"""
        return self.file_info or self.las_info
    
    def load_data_from_file(self, file_path=None):
        """从文件加载数据"""
        if file_path:
            self.last_file_path = file_path
            return self.load_data(file_path)
        else:
            # 打开文件选择对话框
            print("\n" + "="*60)
            print("  ★ 请在弹出的文件对话框中选择测井数据文件 ★")
            print("  ★ 如未看到对话框，请检查任务栏是否有窗口 ★")
            print("="*60 + "\n")
            root = tk.Tk()
            root.attributes('-topmost', True)  # 确保对话框在最前面
            root.withdraw()  # 隐藏主窗口
            
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择测井数据文件",
                filetypes=[
                    ("LAS文件", "*.las"),
                    ("DLIS文件", "*.dlis"),
                    ("Excel文件", "*.xlsx"),
                    ("CSV文件", "*.csv"),
                    ("所有文件", "*.*")
                ]
            )
            
            root.destroy()  # 销毁Tk根窗口，避免残留
            
            if file_path:
                self.last_file_path = file_path
                return self.load_data(file_path)
            else:
                print("未选择文件，已取消。")
                logger.error("未选择文件")
                return None
    
    def load_gas_data(self):
        """加载气测数据文件（可选）
        
        打开文件选择对话框，支持LAS/CSV/XLSX/XLS格式。
        加载后统一列名为大写，深度列重命名为MD。
        
        Returns:
            pd.DataFrame or None: 气测数据，用户取消则返回None
        """
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.attributes('-topmost', True)
        root.withdraw()
        
        file_path = filedialog.askopenfilename(
            title="选择气测数据文件（取消跳过）",
            filetypes=[
                ("气测数据文件", "*.las;*.csv;*.xlsx;*.xls"),
                ("LAS文件", "*.las"),
                ("Excel文件", "*.xlsx;*.xls"),
                ("CSV文件", "*.csv"),
                ("所有文件", "*.*")
            ]
        )
        root.destroy()
        
        if not file_path:
            logger.info("未选择气测数据文件")
            return None
        
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            logger.info(f"正在加载气测数据: {file_path}")
            
            if file_ext == '.csv':
                # 自动查找真正的表头行：找包含深度+气体组分关键词的行
                # 有些文件前几行可能是标题/说明，不是字段行
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    raw_lines = f.readlines()
                header_keywords = ['MD', 'DEPTH', 'DEPT', 'TDEP', 'TG', 'TGAS', 'TOTGAS',
                                   'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE',
                                   'MCH', 'BZ', 'TL', '苯', '甲苯', '甲基环己烷']
                header_row = None
                for i, line in enumerate(raw_lines):
                    fields = [f.strip().upper() for f in line.strip().split(',')]
                    # 检查该行是否包含深度关键词
                    has_depth = any(kw in field for field in fields for kw in ['MD', 'DEPTH', 'DEPT', 'TDEP'])
                    # 检查是否包含气体组分关键词（至少2个）
                    gas_keyword_count = sum(
                        1 for field in fields
                        for kw in ['TG', 'TGAS', 'TOTGAS', 'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE',
                                   'MCH', 'BZ', 'TL']
                        if kw in field
                    )
                    if has_depth and gas_keyword_count >= 2:
                        header_row = i
                        logger.info(f"气测CSV文件在第{i+1}行找到表头(深度+{gas_keyword_count}个气体组分)")
                        break
                if header_row is not None:
                    gas_df = pd.read_csv(file_path, skiprows=header_row)
                    logger.info(f"跳过前{header_row}行，以第{header_row+1}行为表头")
                else:
                    # 退一步：按旧逻辑（只检查第一行）
                    with open(file_path, 'r', encoding='utf-8-sig') as f:
                        first_line = f.readline().strip()
                        first_fields = len(first_line.split(','))
                    if first_fields == 1:
                        gas_df = pd.read_csv(file_path, skiprows=1)
                    else:
                        gas_df = pd.read_csv(file_path)
                    if len(gas_df.columns) <= 1:
                        gas_df = pd.read_csv(file_path, skiprows=1)
            elif file_ext == '.las':
                try:
                    las = lasio.read(file_path)
                    gas_df = las.df().reset_index()
                except ImportError:
                    logger.error("需要安装lasio库: pip install lasio")
                    return None
            elif file_ext in ('.xlsx', '.xls'):
                # 自动查找真正的表头行（Excel文件可能前几行是标题）
                header_keywords = ['MD', 'DEPTH', 'DEPT', 'TDEP', 'TG', 'TGAS', 'TOTGAS',
                                   'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE',
                                   'MCH', 'BZ', 'TL', '苯', '甲苯', '甲基环己烷']
                # 先读取所有行（无表头）
                try:
                    raw_df = pd.read_excel(file_path, engine='calamine', header=None)
                    raw_engine = 'calamine'
                except (ValueError, ImportError):
                    if file_ext == '.xlsx':
                        raw_df = pd.read_excel(file_path, engine='openpyxl', header=None)
                        raw_engine = 'openpyxl'
                    else:
                        raw_df = pd.read_excel(file_path, header=None)
                        raw_engine = 'xlrd'
                header_row = None
                for i in range(len(raw_df)):
                    row_vals = [str(v).upper().strip() for v in raw_df.iloc[i].values if pd.notna(v)]
                    has_depth = any(kw in val for val in row_vals for kw in ['MD', 'DEPTH', 'DEPT', 'TDEP'])
                    gas_keyword_count = sum(
                        1 for val in row_vals
                        for kw in ['TG', 'TGAS', 'TOTGAS', 'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE',
                                   'MCH', 'BZ', 'TL']
                        if kw in val
                    )
                    if has_depth and gas_keyword_count >= 2:
                        header_row = i
                        logger.info(f"气测Excel文件在第{i+1}行找到表头(深度+{gas_keyword_count}个气体组分)")
                        break
                if header_row is not None:
                    skip = header_row
                    try:
                        gas_df = pd.read_excel(file_path, engine='calamine', skiprows=skip)
                    except (ValueError, ImportError):
                        if file_ext == '.xlsx':
                            gas_df = pd.read_excel(file_path, engine='openpyxl', skiprows=skip)
                        else:
                            gas_df = pd.read_excel(file_path, skiprows=skip)
                else:
                    # 退一步：按旧逻辑
                    try:
                        gas_df = pd.read_excel(file_path, engine='calamine')
                    except (ValueError, ImportError):
                        if file_ext == '.xlsx':
                            gas_df = pd.read_excel(file_path, engine='openpyxl')
                        else:
                            gas_df = pd.read_excel(file_path)
                    if len(gas_df.columns) <= 1:
                        try:
                            gas_df = pd.read_excel(file_path, engine='calamine', skiprows=1)
                        except (ValueError, ImportError):
                            if file_ext == '.xlsx':
                                gas_df = pd.read_excel(file_path, engine='openpyxl', skiprows=1)
                            else:
                                gas_df = pd.read_excel(file_path, skiprows=1)
            else:
                logger.error(f"不支持的气测数据格式: {file_ext}")
                return None
            
            # 统一列名为大写
            gas_df.columns = [str(col).upper().strip() for col in gas_df.columns]
            logger.info(f"气测数据原始列名(大写化后): {list(gas_df.columns)}")
            
            # ========== 查找深度列（先精确匹配，再模糊匹配）==========
            depth_candidates = ['MD', 'DEPTH', 'DEP', 'DEPT', 'TDEP']
            # 1. 精确匹配
            depth_col = next((col for col in depth_candidates if col in gas_df.columns), None)
            # 2. 模糊匹配：列名中包含 MD/DEPTH/DEPT 关键词
            if depth_col is None:
                depth_col = next(
                    (col for col in gas_df.columns
                     if any(keyword in col for keyword in ['MD', 'DEPTH', 'DEPT'])),
                    None
                )
            if depth_col and depth_col != 'MD':
                gas_df = gas_df.rename(columns={depth_col: 'MD'})
            
            if 'MD' not in gas_df.columns:
                logger.warning("气测数据中未找到深度列(MD/DEPTH/DEPT)，将使用第一列作为深度")
                if len(gas_df.columns) > 0:
                    gas_df = gas_df.rename(columns={gas_df.columns[0]: 'MD'})
            
            # ========== 气体组分列匹配（先精确匹配，再模糊匹配）==========
            # 定义气体组分标准名称及对应关键词（用于模糊匹配）
            gas_groups = [
                ('TG',    ['TG', 'TOTGAS', 'TOTALGAS', 'TOTAL_GAS', 'GAS_TOTAL', 'TOTAL', 'TOTG', 'GAS']),
                ('C1',    ['C1', 'METHANE', 'CH4', 'METHAN', 'ME']),
                ('C2',    ['C2', 'ETHANE', 'C2H6', 'ETHAN', 'ET']),
                ('C3',    ['C3', 'PROPANE', 'C3H8', 'PROPAN', 'PR']),
                ('C4',    ['C4', 'BUTANE', 'C4PCT', 'C4%', 'C4_PCT']),        # 总丁烷
                ('IC4',   ['IC4', 'I-C4', 'IC4PCT', 'I-C4%']),                 # 异丁烷
                ('NC4',   ['NC4', 'N-C4', 'NC4PCT', 'N-C4%']),                 # 正丁烷
                ('C5',    ['C5', 'PENTANE', 'C5PCT', 'C5%', 'C5_PCT']),        # 总戊烷
                ('IC5',   ['IC5', 'I-C5', 'IC5PCT', 'I-C5%']),                 # 异戊烷
                ('NC5',   ['NC5', 'N-C5', 'NC5PCT', 'N-C5%']),                 # 正戊烷
                ('C6',    ['C6', 'HEXANE', 'C6%', 'C6PCT']),
                ('C7',    ['C7', 'HEPTANE', 'C7%', 'C7PCT']),
                ('C8',    ['C8', 'OCTANE', 'C8%', 'C8PCT']),
                ('MCH',   ['MCH', 'METHYLCYCLOHEXANE', 'C7H14', '甲基环己烷']),    # 甲基环己烷
                ('BZ',    ['BZ', 'BENZENE', 'C6H6', '苯']),                         # 苯
                ('TL',    ['TL', 'TOLUENE', 'C7H8', '甲苯']),                       # 甲苯
                ('H2',    ['H2', 'HYDROGEN', 'HYDRO']),
                ('CO2',   ['CO2', 'CARBON_DIOXIDE', 'CARBONDIOXIDE']),
                ('H2S',   ['H2S', 'HYDROGEN_SULFIDE']),
            ]
            gas_matched = {}
            for std_name, candidates in gas_groups:
                # 1. 精确匹配
                col = next((c for c in candidates if c in gas_df.columns), None)
                # 2. 模糊匹配：列名中包含关键词
                if col is None:
                    col = next(
                        (c for c in gas_df.columns
                         if any(keyword in c for keyword in candidates)),
                        None
                    )
                    if col:
                        logger.debug(f"  模糊匹配: {std_name} ← {col} (关键词: {candidates})")
                if col:
                    logger.debug(f"  气测组分匹配: {std_name} = {col}")
                    if col != std_name:
                        gas_matched[col] = std_name
                else:
                    logger.debug(f"  气测组分未匹配: {std_name} (查找: {candidates})")
            # 统一重命名
            if gas_matched:
                gas_df = gas_df.rename(columns=gas_matched)
                renamed = ', '.join(f'{k}→{v}' for k, v in gas_matched.items())
                logger.info(f"气测组分列重命名: {renamed}")
            
            # 确保MD列为数值类型（避免混合类型排序错误）
            if 'MD' in gas_df.columns:
                gas_df['MD'] = pd.to_numeric(gas_df['MD'], errors='coerce')
                # 删除深度为NaN的行
                gas_df = gas_df.dropna(subset=['MD'])
            
            # 按深度排序
            gas_df = gas_df.sort_values('MD').reset_index(drop=True)
            
            logger.info(f"气测数据加载成功，共 {len(gas_df)} 条记录，{len(gas_df.columns)} 列")
            return gas_df
            
        except Exception as e:
            logger.error(f"气测数据加载失败: {e}")
            import traceback
            traceback.print_exc()
            return None

def log_print(message):
    """打印日志消息"""
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    logger.info(message)

# --- 数据处理类 ---
class DataProcessor:
    """数据处理类"""
    
    def __init__(self, config=None):
        """初始化数据处理器"""
        self.config = config or ConfigManager().get_config()
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
        return self.data
    
    def data_quality_check(self):
        """Data quality check"""
        if self.data is None:
            logger.error("Data not loaded")
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
        logger.info("Data quality check完成")
        return qc_report
    

    
    def _apply_porosity_invalid_mask(self, data):
        """将孔隙度无效段的 PHI/PORD 置为 NaN。
        
        无效段由 _detect_porosity_invalid_sections() 标记在 _POROSITY_VALID 列中。
        顶部和底部无有效中子/密度/声波曲线时不计算孔隙度。
        """
        if '_POROSITY_VALID' in data.columns:
            invalid_mask = ~data['_POROSITY_VALID']
            for col in ['PHI', 'PORD', 'PHIE']:
                if col in data.columns:
                    data.loc[invalid_mask, col] = np.nan
            if invalid_mask.any():
                invalid_count = invalid_mask.sum()
                logger.info(f"孔隙度无效段: {invalid_count} 点 PHI/PORD 已置为 NaN")
    
    def calculate_porosity(self):
        """计算孔隙度
        
        核磁共振测井(NMR)是核心手段，能区分有效孔隙与束缚流体孔隙。
        缺乏核磁资料时，使用以下7种常规测井评价方法：
        
        M1: 密度泥质校正法
            PORD = (DM-DEN)/(DM-DF) - SH*(DM-DSH)/(DM-DF)
            DM=2.65, DF=1.0, DSH=2.2-2.65(默认2.45)
            
        M2: 声波时差泥质校正法
            PORA = (TC-TM)/(TF-TM) - SH*(TSH-TM)/(TF-TM)
            TM=55.5, TF=189, TSH=76.8-167(默认120)
            TC = TM + (AC-TM)/Cp,  Cp = BCP - ACP*DEPTH*10^-3
            BCP=1.67, ACP=0.203
            
        M3: 中子泥质校正法
            PORN = (CNL-NM)/(NF-NM) - SH*(NSH-NM)/(NF-NM)
            NM=-2, NF=100, NSH=35(默认)
            
        M4: 中子-密度加权平均
            PORND1 = ((PORN+PORD)/2 + sqrt((PORN^2+PORD^2)/2))/2
            
        M5: 交会图法（考虑岩性和流体校正）
            PORND2 = c1*PORN + c2*PORD  (c1,c2由岩性确定)
            
        M6: 中子密度算术平均
            PORND2 = (PORN+PORD)/2
            
        M7: 中子声波几何平均
            PORNA = sqrt((PORN^2+PORA^2)/2)
        
        选择策略：
        - 有核磁(NMR)：优先使用核磁孔隙度
        - 无核磁：根据可用资料选择M4(加权平均) > M5(交会图) > M6(算术平均) > M7(几何平均) > M1(密度) > M2(声波) > M3(中子)
        - 特殊岩性（煤层、膏盐、火山岩等）不计算孔隙度
        """
        if self.data is None:
            logger.error("Data not loaded")
            return None
        
        POROSITY_MAX = 0.4
        
        data = self.data.copy()
        
        # 定义特殊岩性列表（不计算孔隙度）
        special_liths = ['coal', 'anhydrite', 'salt', 'halite', 'evaporite', 
                         'volcanic', 'basement', 'tuff', 'basalt', 'granite',
                         '煤层', '膏盐', '盐岩', '硬石膏', '火山岩', '花岗岩']
        
        # 获取VSH列（泥质含量）
        vsh_col = None
        for name in ['VSH', 'SH']:
            if name in data.columns:
                vsh_col = name
                break
        has_vsh = vsh_col is not None
        
        # 获取深度列
        depth_col = None
        for name in ['MD', 'DEPT', 'DEPTH', 'TDEP']:
            if name in data.columns:
                depth_col = name
                break
        
        # ========== 计算核磁孔隙度（NMR - 核心手段）==========
        has_nmr = False
        for nmr_col in ['MPHE', 'PHIE', 'MRP', 'CMFF', 'CBW']:
            if nmr_col in data.columns:
                nmr = data[nmr_col].values
                if np.nanmax(nmr) > 1:
                    nmr = nmr / 100.0
                valid = (nmr >= 0) & (nmr < 1.5)
                phi_nmr = np.where(valid, nmr, np.nan)
                phi_nmr = np.clip(phi_nmr, 0, POROSITY_MAX)
                data['PHI_NMR'] = phi_nmr
                has_nmr = True
                logger.info(f"  核磁孔隙度({nmr_col}): 有效={np.isfinite(phi_nmr).sum()}, "
                           f"范围={np.nanmin(phi_nmr):.3f}-{np.nanmax(phi_nmr):.3f}")
                break
        
        # ========== M1: 密度泥质校正法 ==========
        # PORD = (DM-DEN)/(DM-DF) - SH*(DM-DSH)/(DM-DF)
        # DM=2.65, DF=1.0, DSH=2.45(默认)
        if 'RHOB' in data.columns:
            DM = 2.65  # 骨架密度
            DF = 1.0   # 流体密度
            DSH = 2.45  # 泥质密度（可调范围2.2-2.65）
            rhob = data['RHOB'].values
            valid = (rhob > 0) & (rhob < 5)
            # 无泥质校正的密度孔隙度
            phi_den_simple = np.where(valid, (DM - rhob) / (DM - DF), np.nan)
            # 泥质校正项
            if has_vsh:
                vsh = data[vsh_col].values
                shale_corr = vsh * (DM - DSH) / (DM - DF)
                phi_den_shale = phi_den_simple - shale_corr
            else:
                phi_den_shale = phi_den_simple
            phi_den_shale = np.clip(phi_den_shale, 0, POROSITY_MAX)
            data['PHI_DEN_SHALE'] = phi_den_shale
            logger.info(f"  M1 密度泥质校正法: 有效={np.isfinite(phi_den_shale).sum()}, "
                       f"范围={np.nanmin(phi_den_shale):.3f}-{np.nanmax(phi_den_shale):.3f}")
        
        # ========== M2: 声波时差泥质校正法 ==========
        # PORA = (TC-TM)/(TF-TM) - SH*(TSH-TM)/(TF-TM)
        # TC = TM + (AC-TM)/Cp,  Cp = BCP - ACP*DEPTH*10^-3
        # TM=55.5, TF=189, TSH=120(默认), BCP=1.67, ACP=0.203
        dt_col = None
        for name in ['DT', 'DTCO', 'AC', 'SONIC']:
            if name in data.columns:
                dt_col = name
                break
        if dt_col:
            TM = 55.5   # 骨架声波时差(us/ft)
            TF = 189.0  # 流体声波时差(us/ft)
            TSH = 120.0  # 泥质声波时差(us/ft, 可调76.8-167)
            BCP = 1.67   # 压实系数上限
            ACP = 0.203  # 压实系数斜率
            ac = data[dt_col].values
            valid = (ac > 30) & (ac < 500)
            # 压实校正系数 Cp = BCP - ACP*DEPTH*10^-3
            if depth_col is not None:
                depth = data[depth_col].values
                cp = BCP - ACP * depth * 1e-3
                cp = np.clip(cp, 0.5, 2.0)  # 限制Cp范围
            else:
                # 无深度时使用中值法
                ac_median = np.nanmedian(ac[valid]) if valid.any() else 90
                cp = np.full(len(data), 1.0 if ac_median < 90 else 0.85)
            # 压实校正后的声波时差
            tc = np.where(valid, TM + (ac - TM) / cp, np.nan)
            # 无泥质校正的声波孔隙度
            phi_sonic_simple = np.where(valid, (tc - TM) / (TF - TM), np.nan)
            # 泥质校正项
            if has_vsh:
                vsh = data[vsh_col].values
                shale_corr = vsh * (TSH - TM) / (TF - TM)
                phi_sonic_shale = phi_sonic_simple - shale_corr
            else:
                phi_sonic_shale = phi_sonic_simple
            phi_sonic_shale = np.clip(phi_sonic_shale, 0, POROSITY_MAX)
            data['PHI_SONIC_SHALE'] = phi_sonic_shale
            logger.info(f"  M2 声波泥质校正法: 有效={np.isfinite(phi_sonic_shale).sum()}, "
                       f"范围={np.nanmin(phi_sonic_shale):.3f}-{np.nanmax(phi_sonic_shale):.3f}")
        
        # ========== M3: 中子泥质校正法 ==========
        # PORN = (CNL-NM)/(NF-NM) - SH*(NSH-NM)/(NF-NM)
        # NM=-2, NF=100, NSH=35(默认)
        if 'NPHI' in data.columns:
            NM = -2.0   # 砂岩骨架中子值(pu)
            NF = 100.0  # 流体中子值(pu)
            NSH = 35.0  # 泥质中子值(pu, 可调)
            cnl = data['NPHI'].values
            # 转换为小数
            if np.nanmax(cnl) > 1:
                cnl = cnl / 100.0
            valid = (cnl > -0.15) & (cnl < 1.5)
            # 无泥质校正的中子孔隙度
            phi_cnl_simple = np.where(valid, (cnl - NM/100) / (NF/100 - NM/100), np.nan)
            # 泥质校正项（注意单位一致性）
            if has_vsh:
                vsh = data[vsh_col].values
                shale_corr = vsh * (NSH/100 - NM/100) / (NF/100 - NM/100)
                phi_cnl_shale = phi_cnl_simple - shale_corr
            else:
                phi_cnl_shale = phi_cnl_simple
            phi_cnl_shale = np.clip(phi_cnl_shale, 0, POROSITY_MAX)
            data['PHI_CNL_SHALE'] = phi_cnl_shale
            logger.info(f"  M3 中子泥质校正法: 有效={np.isfinite(phi_cnl_shale).sum()}, "
                       f"范围={np.nanmin(phi_cnl_shale):.3f}-{np.nanmax(phi_cnl_shale):.3f}")
        
        # ========== M4: 中子-密度加权平均 ==========
        # PORND1 = ((PORN+PORD)/2 + sqrt((PORN^2+PORD^2)/2))/2
        if 'PHI_DEN_SHALE' in data.columns and 'PHI_CNL_SHALE' in data.columns:
            pord = data['PHI_DEN_SHALE'].values
            porn = data['PHI_CNL_SHALE'].values
            valid = np.isfinite(pord) & np.isfinite(porn)
            with np.errstate(invalid='ignore'):
                term1 = (porn + pord) / 2.0
                term2 = np.sqrt((porn**2 + pord**2) / 2.0)
                phi_nd_weighted = np.where(valid, (term1 + term2) / 2.0, np.nan)
            phi_nd_weighted = np.clip(phi_nd_weighted, 0, POROSITY_MAX)
            data['PHI_ND_WEIGHTED'] = phi_nd_weighted
            logger.info(f"  M4 中子-密度加权平均: 有效={np.isfinite(phi_nd_weighted).sum()}, "
                       f"范围={np.nanmin(phi_nd_weighted):.3f}-{np.nanmax(phi_nd_weighted):.3f}")
        
        # ========== M5: 交会图法（考虑岩性和流体校正）==========
        # PORND2 = c1*PORN + c2*PORD
        # c1,c2由岩性确定：砂泥岩用VSH加权，碳酸盐岩用PE或岩性名称
        if 'PHI_DEN_SHALE' in data.columns and 'PHI_CNL_SHALE' in data.columns:
            pord = data['PHI_DEN_SHALE'].values
            porn = data['PHI_CNL_SHALE'].values
            phi_cross_litho = np.full(len(data), np.nan)
            for i in range(len(data)):
                if not np.isfinite(pord[i]) or not np.isfinite(porn[i]):
                    continue
                # 默认各50%权重
                c1, c2 = 0.5, 0.5
                # 根据岩性调整权重
                lith = str(data.iloc[i].get('LITHOLOGY', data.iloc[i].get('LITHOLOGY_EN', ''))).lower().strip()
                if 'sandstone' in lith or '砂岩' in lith:
                    c1, c2 = 0.4, 0.6  # 砂岩偏密度
                elif 'shale' in lith or '泥岩' in lith:
                    c1, c2 = 0.6, 0.4  # 泥岩偏中子
                elif 'limestone' in lith or '灰岩' in lith:
                    c1, c2 = 0.5, 0.5  # 灰岩各半
                elif 'dolomite' in lith or '白云岩' in lith:
                    c1, c2 = 0.6, 0.4  # 白云岩偏中子
                elif 'volcanic' in lith or '火山岩' in lith:
                    continue  # 火山岩不计算
                # 有VSH时用VSH辅助调整
                if has_vsh:
                    vsh = data.iloc[i].get(vsh_col, 0)
                    if np.isfinite(vsh) and vsh > 0.5:
                        c1 = 0.5 + vsh * 0.2  # 高泥质偏中子
                        c2 = 1.0 - c1
                phi_cross_litho[i] = c1 * porn[i] + c2 * pord[i]
            phi_cross_litho = np.clip(phi_cross_litho, 0, POROSITY_MAX)
            data['PHI_CROSS_LITHO'] = phi_cross_litho
            logger.info(f"  M5 交会图法(岩性加权): 有效={np.isfinite(phi_cross_litho).sum()}, "
                       f"范围={np.nanmin(phi_cross_litho):.3f}-{np.nanmax(phi_cross_litho):.3f}")
        
        # ========== M6: 中子密度算术平均 ==========
        # PORND2 = (PORN+PORD)/2
        if 'PHI_DEN_SHALE' in data.columns and 'PHI_CNL_SHALE' in data.columns:
            pord = data['PHI_DEN_SHALE'].values
            porn = data['PHI_CNL_SHALE'].values
            valid = np.isfinite(pord) & np.isfinite(porn)
            phi_nd_mean = np.where(valid, (porn + pord) / 2.0, np.nan)
            phi_nd_mean = np.clip(phi_nd_mean, 0, POROSITY_MAX)
            data['PHI_ND_MEAN'] = phi_nd_mean
            logger.info(f"  M6 中子密度算术平均: 有效={np.isfinite(phi_nd_mean).sum()}, "
                       f"范围={np.nanmin(phi_nd_mean):.3f}-{np.nanmax(phi_nd_mean):.3f}")
        
        # ========== M7: 中子声波几何平均 ==========
        # PORNA = sqrt((PORN^2+PORA^2)/2)
        if 'PHI_CNL_SHALE' in data.columns and 'PHI_SONIC_SHALE' in data.columns:
            porn = data['PHI_CNL_SHALE'].values
            pora = data['PHI_SONIC_SHALE'].values
            valid = np.isfinite(porn) & np.isfinite(pora)
            with np.errstate(invalid='ignore'):
                phi_ns_mean = np.where(valid, np.sqrt((porn**2 + pora**2) / 2.0), np.nan)
            phi_ns_mean = np.clip(phi_ns_mean, 0, POROSITY_MAX)
            data['PHI_NS_MEAN'] = phi_ns_mean
            logger.info(f"  M7 中子声波几何平均: 有效={np.isfinite(phi_ns_mean).sum()}, "
                       f"范围={np.nanmin(phi_ns_mean):.3f}-{np.nanmax(phi_ns_mean):.3f}")
        
        # ========== 选择最佳孔隙度 ==========
        # 优先级策略：
        # 1. 有核磁(NMR) → 核磁为第一优选（NMR能区分有效孔隙与束缚孔隙）
        # 2. 砂泥岩剖面 → 密度泥质校正法(M1)为第一优选
        # 3. 其他剖面（碳酸盐岩/混合） → 中子-密度加权平均(M4)为第一优选
        profile_type = self.results.get('profile_type', 'carbonate')
        if profile_type == 'sand_shale':
            # 砂泥岩剖面：密度 > 其它
            priority_order = ['PHI_NMR', 'PHI_DEN_SHALE', 'PHI_ND_WEIGHTED', 'PHI_CROSS_LITHO', 
                              'PHI_ND_MEAN', 'PHI_NS_MEAN', 
                              'PHI_SONIC_SHALE', 'PHI_CNL_SHALE']
        else:
            # 碳酸盐岩/混合剖面：中子-密度交汇 > 其它
            priority_order = ['PHI_NMR', 'PHI_ND_WEIGHTED', 'PHI_CROSS_LITHO', 
                              'PHI_ND_MEAN', 'PHI_NS_MEAN', 
                              'PHI_DEN_SHALE', 'PHI_SONIC_SHALE', 'PHI_CNL_SHALE']
        
        # 收集所有可用方法
        phi_methods = {}
        for name in priority_order:
            if name in data.columns:
                phi_methods[name] = data[name].values
        
        # 初始化PHI
        data['PHI'] = np.nan
        data['PHI_SOURCE'] = ''
        
        # 逐点选择最佳方法
        for i in range(len(data)):
            chosen = False
            for method_name in priority_order:
                if method_name not in phi_methods:
                    continue
                val = phi_methods[method_name][i]
                if np.isfinite(val) and val > 0:
                    # 限制孔隙度不超过0.4（40%），超过的可能是气层效应或井眼扩大
                    val = min(val, 0.4)
                    data.loc[data.index[i], 'PHI'] = val
                    data.loc[data.index[i], 'PHI_SOURCE'] = method_name
                    chosen = True
                    break
            if not chosen:
                # 所有方法都无效，尝试取第一个有效值（包括0值）
                for method_name in priority_order:
                    if method_name not in phi_methods:
                        continue
                    val = phi_methods[method_name][i]
                    if np.isfinite(val):
                        val = min(val, 0.4)
                        data.loc[data.index[i], 'PHI'] = val
                        data.loc[data.index[i], 'PHI_SOURCE'] = method_name
                        break
        
        # 特殊岩性不计算孔隙度
        if 'LITHOLOGY' in data.columns:
            special_mask = data['LITHOLOGY'].str.lower().isin(special_liths)
            if special_mask.any():
                data.loc[special_mask, 'PHI'] = np.nan
                data.loc[special_mask, 'PHI_SOURCE'] = 'excluded'
                logger.info(f"  特殊岩性孔隙度已排除: {special_mask.sum()}点 "
                           f"({', '.join(data.loc[special_mask, 'LITHOLOGY'].unique())})")
        
        # 始终计算PORD（密度孔隙度固定骨架，无泥质校正，用于向后兼容）
        if 'RHOB' in data.columns:
            rhob = data['RHOB']
            valid = (rhob > 0) & (rhob < 5)
            pord = np.where(valid, (2.65 - rhob) / (2.65 - 1.0), np.nan)
            pord = np.clip(pord, 0, POROSITY_MAX)
            data['PORD'] = pord
            if 'LITHOLOGY' in data.columns and special_mask.any():
                data.loc[special_mask, 'PORD'] = np.nan
        
        # 顶部/底部无效段
        self._apply_porosity_invalid_mask(data)
        
        # 统计
        phi_valid = data['PHI'].notna().sum()
        phi_mean = data['PHI'].mean()
        source_counts = data['PHI_SOURCE'].value_counts().to_dict() if phi_valid > 0 else {}
        logger.info(f"PHI计算完成: 有效={phi_valid}/{len(data)}, 均值={phi_mean:.3f}")
        logger.info(f"PHI来源分布: {source_counts}")
        
        self.data = data
        return data['PHI']
    
    def calculate_water_saturation(self):
        """计算含水饱和度"""
        if self.data is None:
            logger.error("Data not loaded")
            return None
        
        data = self.data.copy()
        
        if 'SW' in data.columns:
            data['Sw'] = data['SW']
            data['Sw'] = data['Sw'].clip(0, 1)
        elif 'RT' in data.columns and 'PHI' in data.columns:
            # 从配置文件读取阿尔奇公式参数
            archie_config = self.config.get('archie', {})
            Rw = archie_config.get('Rw', 0.05)
            a = archie_config.get('a', 1.0)
            m = archie_config.get('m', 2.0)
            n = archie_config.get('n', 2.0)
            Rsh = archie_config.get('Rsh', 2.0)
            
            data['Sw'] = (a * Rw / (data['PHI']**m * data['RT']))**(1/n)
            data['Sw'] = data['Sw'].clip(0, 1)
            
            if 'VSH' in data.columns:
                vsh_threshold = self.config.get('vsh_threshold', {}).get('sand_max', 0.3)
                data.loc[data['VSH'] > vsh_threshold, 'Sw'] = (a * Rw / (data.loc[data['VSH'] > vsh_threshold, 'PHI']**m * data.loc[data['VSH'] > vsh_threshold, 'RT']) + 
                                                      data.loc[data['VSH'] > vsh_threshold, 'VSH'] / Rsh)**(-1)
                data['Sw'] = data['Sw'].clip(0, 1)
        else:
            data['Sw'] = 0.0
        
        self.data = data
        return data['Sw']
    
    def interpretation(self):
        """油气水解释模型 - 使用英文存储解释结论"""
        logger.info("START INTERPRETATION...")   

        results = []   
        similarity_threshold = 0.3
        
        param_mapping = {
            'SW': ['SW', 'Sw', 'sw', 'S_w', 'WATER_SAT', 'SATW'],
            'VSH': ['VSH', 'Vsh', 'vsh', 'SHALE_VOL', 'CLAY_VOL'],
            'RT': ['RT', 'LLD', 'ILD', 'R90', 'RESISTIVITY', 'DEEP_RES'],
            'POR': ['POR', 'PHI', 'PHIE', 'NPHI', 'POROSITY', 'PORO']
        }
        
        core_params = []
        found_params = {}
        param_order = []
        
        for param, possible_names in param_mapping.items():
            for name in possible_names:
                if name in self.data.columns:
                    found_params[param] = name
                    core_params.append(name)
                    param_order.append(param)
                    break
        
        if len(found_params) < 2:
            logger.warning(f"解释所需参数不足，仅找到 {len(found_params)} 个: {list(found_params.keys())}")
            df = self.data.copy()
            df['ITP'] = 'Undefined'
            df['INTERPRETATION'] = 'Undefined'
            return df, results
        
        logger.info(f"使用的解释参数列: {found_params}")
        
        # 计算每列的统计信息用于归一化
        param_stats = {}
        for param, col_name in found_params.items():
            col_data = self.data[col_name].dropna().values
            if len(col_data) > 0:
                param_stats[param] = {
                    'min': np.min(col_data),
                    'max': np.max(col_data),
                    'median': np.median(col_data),
                    'range': np.max(col_data) - np.min(col_data)
                }
        
        # 定义标准化后的模板（0-1范围）
        # SW: 水层>0.8, 油层<0.5, 气层<0.5
        # VSH: 好层<0.3
        # RT: 油层中等, 气层高, 水层低（归一化后）
        # POR: 有效储层>0.1
        templates_norm = {
            'GAS': [0.4, 0.2, 0.8, 0.5],   # 气层：Sw低, Vsh低, Rt高, Phi中等
            'OIL': [0.4, 0.2, 0.6, 0.5],   # 油层：Sw低, Vsh低, Rt中等高, Phi中等
            'WATER': [0.9, 0.3, 0.2, 0.5], # 水层：Sw高, Vsh中等, Rt低, Phi中等
            'DRY': [0.7, 0.35, 0.6, 0.35]  # 干层：Sw中高, Vsh中, Rt中高, Phi中低(但有孔隙，是储层)
        }
        
        df = self.data.copy()
        df['ITP'] = ''
        df['INTERPRETATION'] = ''
        
        target_data = df[core_params].values
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            target = target_data[idx]
            
            if np.any(np.isnan(target)) or np.any(np.isinf(target)):
                result = "Undefined"
            else:
                # 归一化当前行数据到0-1范围
                target_norm = []
                for i, param in enumerate(param_order):
                    if param in param_stats and param_stats[param]['range'] > 0:
                        val = target[i]
                        pmin = param_stats[param]['min']
                        prange = param_stats[param]['range']
                        norm_val = (val - pmin) / prange
                        norm_val = max(0, min(1, norm_val))
                        target_norm.append(norm_val)
                    else:
                        target_norm.append(0.5)
                
                target_norm = np.array(target_norm)
                
                similarity = {}
                for fluid_type, template in templates_norm.items():
                    # 截取模板到实际参数数量
                    template_slice = np.array(template[:len(target_norm)])
                    distance = np.sqrt(np.sum((target_norm - template_slice) ** 2))
                    similarity[fluid_type] = 1 / (1 + distance)
                
                valid_types = {k: v for k, v in similarity.items() if v >= similarity_threshold}
                if valid_types:
                    result = max(valid_types.items(), key=lambda x: x[1])[0]
                else:
                    result = "Undefined"
            
            df.at[idx, 'ITP'] = result
            df.at[idx, 'INTERPRETATION'] = result
            
            results.append({
                    'MD': row['MD'],
                    'ITP': result,
                    'INTERPRETATION': result
                })
        
        logger.info(f"Interpretation completed, {len(df)} records")
        return df,results

# --- 数据可视化类（调用修复后的log_visualizer模块）---
class DataVisualizer:
    """数据可视化类 - 调用修复后的log_visualizer模块"""
    
    def __init__(self, output_dir):
        """初始化数据可视化器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.viz_dir = self.output_dir
    
    def visualize_composite_log(self, data, results, gas_data=None):
        """可视化综合测井曲线（调用修复后的模块）"""
        try:
            from log_visualizer import visualize_composite_log as fixed_visualize
            return fixed_visualize(data, results, gas_data=gas_data)
        except ImportError as e:
            logger.error(f"导入log_visualizer模块失败: {e}")
            # 降级使用内置简单可视化
            return self._simple_visualize_composite_log(data, results)
    
    def _simple_visualize_composite_log(self, data, results):
        """降级使用的简单可视化方法"""
        if data is None:
            logger.error("数据未加载")
            return None
        
        try:
            if 'MD' not in data.columns:
                logger.error("数据中缺少Depth列 'MD'")
                return None
            
            data = data.sort_values('MD').reset_index(drop=True)
            depth = data['MD']
            depth_min = depth.min()
            depth_max = depth.max()
            
            fig, axes = plt.subplots(1, 4, figsize=(16, 12))
            
            # 简单绘制GR曲线
            if 'GR' in data.columns:
                axes[0].plot(data['GR'], data['MD'], color='green')
                axes[0].set_title('GR')
            
            # 简单绘制电阻率曲线
            if 'LLD' in data.columns:
                axes[1].semilogx(data['LLD'], data['MD'], color='red')
                axes[1].set_title('Resistivity')
            
            # 简单绘制密度曲线
            if 'RHOB' in data.columns:
                axes[2].plot(data['RHOB'], data['MD'], color='blue')
                axes[2].set_title('Density')
            
            # 深度轴
            axes[3].set_ylim(depth_max, depth_min)
            axes[3].set_title('Depth')
            
            for ax in axes:
                ax.set_ylim(depth_max, depth_min)
            
            well_name = results.get('well_name', 'Unknown Well')
            well_output_dir = Path(results.get('output_dir', 'output'))
            well_output_dir.mkdir(exist_ok=True, parents=True)
            
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = well_output_dir / f'{well_name}_composite_log_{timestamp}.png'
            
            plt.savefig(output_path, dpi=80, bbox_inches='tight')
            plt.close(fig)
            
            return str(output_path.absolute())
        except Exception as e:
            logger.error(f"简单可视化失败: {e}")
            return None
    
    def visualize_all(self, results):
        """可视化所有结果"""
        if not results:
            logger.error("无结果可可视化")
            return None
        
        try:
            # 可视化其他曲线
            if 'processed_data' in results:
                #self.visualize_porosity(results['processed_data'])
                self.visualize_composite_log(results['processed_data'], results)
            
            logger.info("所有结果可视化完成")
            return str(self.viz_dir)
        except Exception as e:
            logger.error(f"可视化所有结果失败: {e}")
            return None

# --- 报告生成类 ---
# --- 报告生成类 ---
class ReportGenerator:
    """报告生成类"""
    
    def __init__(self, output_dir):
        """初始化报告生成器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.report_dir = self.output_dir
    
    def generate_report(self, results, config):
        """生成报告"""
        if not results:
            logger.error("无结果可生成报告")
            return None
        
        # 生成HTML报告
        well_name = results.get('well_name', 'Unknown')
        report_path = self.report_dir / f'{well_name}_report.html'
        
        # 报告内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>测井资料解释报告</title>
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
            <h1>测井资料解释报告</h1>
            
            <div class="section summary">
                <h2>摘要</h2>
                <p>报告生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>数据记录数: {results.get('qc_report', {}).get('total_records', 'N/A')}</p>
                <p>解释方法: {', '.join(config['interpretation_methods'])}</p>
            </div>
            
            <div class="section">
                <h2>Data quality check</h2>
                <table>
                    <tr>
                        <th>检查项</th>
                        <th>结果</th>
                    </tr>
                    <tr>
                        <td>total_records</td>
                        <td>{results.get('qc_report', {}).get('total_records', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td>missing_values</td>
                        <td>{len([k for k, v in results.get('qc_report', {}).get('missing_values', {}).items() if v > 0])} 列</td>
                    </tr>
                    <tr>
                        <td>outliers</td>
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
                <p>可视化Results saved to: {self.output_dir}</p>
            </div>
        </body>
        </html>
        """
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"报告生成完成，保存至: {report_path}")
        return str(report_path)

# --- 岩性图版分析类 ---
class LithologyCrossplotAnalyzer:
    """岩性交汇图分析类，用于确定本井主要岩性类型和骨架参数"""
    
    def __init__(self):
        """初始化交汇图分析器"""
        # 理论骨架参数（参考常见岩石骨架参数表）
        self.theoretical_skeleton = {
            'sandstone': {'density': 2.65, 'ac': 55.5, 'pe': 1.81, 'cnl': -0.02},
            'limestone': {'density': 2.71, 'ac': 47.5, 'pe': 5.08, 'cnl': 0.00},
            'dolomite': {'density': 2.87, 'ac': 43.5, 'pe': 3.14, 'cnl': 0.02},
            'shale': {'density': 2.55, 'ac': 80.0, 'pe': 3.45, 'cnl': 0.35},
            'volcanic': {'density': 2.75, 'ac': 50.0, 'pe': 6.0, 'cnl': 0.05},
            'anhydrite': {'density': 2.98, 'ac': 50.0, 'pe': 5.0, 'cnl': 0.005}
        }
    
    def analyze_density_ac_crossplot(self, data):
        """密度-声波时差交汇图分析，确定本井主要岩性类型"""
        density_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        ac_col = 'DT' if 'DT' in data.columns else ('AC' if 'AC' in data.columns else None)
        
        if density_col is None or ac_col is None:
            return {'main_lithology': ['sandstone'], 'estimated_skeleton': self.theoretical_skeleton}
        
        densities = data[density_col].values
        ac_values = data[ac_col].values
        
        valid_mask = (densities > 2.0) & (densities < 3.5) & (ac_values > 30) & (ac_values < 150)
        if np.sum(valid_mask) < 20:
            return {'main_lithology': ['sandstone'], 'estimated_skeleton': self.theoretical_skeleton}
        
        valid_densities = densities[valid_mask]
        valid_ac = ac_values[valid_mask]
        
        # 使用K-means聚类确定主要岩性群体
        from sklearn.cluster import KMeans
        
        features = np.column_stack([valid_densities, valid_ac])
        n_clusters = min(4, len(features) // 50)
        if n_clusters < 2:
            n_clusters = 2
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(features)
        
        # 识别每个聚类对应的岩性类型
        cluster_centers = kmeans.cluster_centers_
        main_lithology = []
        estimated_skeleton = self.theoretical_skeleton.copy()
        
        for i, center in enumerate(cluster_centers):
            cluster_density, cluster_ac = center
            
            # 计算与理论骨架的距离
            distances = {}
            for lith, params in self.theoretical_skeleton.items():
                dist = np.sqrt((cluster_density - params['density'])**2 + (cluster_ac - params['ac'])**2)
                distances[lith] = dist
            
            # 找到最匹配的岩性类型
            best_lith = min(distances, key=distances.get)
            
            if distances[best_lith] < 0.15:
                main_lithology.append(best_lith)
                estimated_skeleton[best_lith]['density'] = cluster_density
                estimated_skeleton[best_lith]['ac'] = cluster_ac
        
        if not main_lithology:
            main_lithology = ['sandstone']
        
        return {'main_lithology': list(set(main_lithology)), 'estimated_skeleton': estimated_skeleton}
    
    def analyze_pe_density_crossplot(self, data):
        """光电吸收截面指数-密度交汇图分析"""
        pe_col = 'PE' if 'PE' in data.columns else ('PEF' if 'PEF' in data.columns else None)
        density_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        
        if pe_col is None or density_col is None:
            return None
        
        pe_values = data[pe_col].values
        densities = data[density_col].values
        
        valid_mask = (pe_values > 0) & (pe_values < 20) & (densities > 2.0) & (densities < 3.5)
        if np.sum(valid_mask) < 20:
            return None
        
        valid_pe = pe_values[valid_mask]
        valid_densities = densities[valid_mask]
        
        features = np.column_stack([valid_pe, valid_densities])
        n_clusters = min(4, len(features) // 50)
        if n_clusters < 2:
            n_clusters = 2
        
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(features)
        
        cluster_centers = kmeans.cluster_centers_
        pe_skeleton = {}
        
        for center in cluster_centers:
            cluster_pe, cluster_density = center
            
            distances = {}
            for lith, params in self.theoretical_skeleton.items():
                dist = np.sqrt((cluster_pe - params['pe'])**2 + (cluster_density - params['density'])**2)
                distances[lith] = dist
            
            best_lith = min(distances, key=distances.get)
            if distances[best_lith] < 0.5:
                pe_skeleton[best_lith] = {'pe': cluster_pe, 'density': cluster_density}
        
        return pe_skeleton
    
    def analyze_cnl_density_crossplot(self, data):
        """中子-密度交汇图分析"""
        cnl_col = 'NPHI' if 'NPHI' in data.columns else ('CNL' if 'CNL' in data.columns else None)
        density_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        
        if cnl_col is None or density_col is None:
            return None
        
        cnl_values = data[cnl_col].values
        densities = data[density_col].values
        
        valid_mask = (cnl_values > -0.2) & (cnl_values < 1.0) & (densities > 2.0) & (densities < 3.5)
        if np.sum(valid_mask) < 20:
            return None
        
        valid_cnl = cnl_values[valid_mask]
        valid_densities = densities[valid_mask]
        
        features = np.column_stack([valid_cnl, valid_densities])
        n_clusters = min(4, len(features) // 50)
        if n_clusters < 2:
            n_clusters = 2
        
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(features)
        
        cluster_centers = kmeans.cluster_centers_
        cnl_skeleton = {}
        
        for center in cluster_centers:
            cluster_cnl, cluster_density = center
            
            distances = {}
            for lith, params in self.theoretical_skeleton.items():
                dist = np.sqrt((cluster_cnl - params['cnl'])**2 + (cluster_density - params['density'])**2)
                distances[lith] = dist
            
            best_lith = min(distances, key=distances.get)
            if distances[best_lith] < 0.15:
                cnl_skeleton[best_lith] = {'cnl': cluster_cnl, 'density': cluster_density}
        
        return cnl_skeleton
    
    def analyze_segment_type(self, data, window_size=50):
        """
        大段判断：根据密度、电阻率和交汇图特征判断每个深度点属于砂泥岩段还是碳酸盐岩段
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）
            
        返回:
            segment_type: 数组，'sand_shale' 或 'carbonate' 或 'mixed'
        """
        segment_type = np.array(['mixed'] * len(data))
        
        density_col = None
        rt_col = None
        nphi_col = None
        gr_col = None
        
        for name in ['RHOB', 'DEN']:
            if name in data.columns:
                density_col = name
                break
        for name in ['RT', 'LLD', 'ILD', 'AT90', 'AT60', 'M2RX', 'RDEEP']:
            if name in data.columns:
                rt_col = name
                break
        for name in ['NPHI', 'CNL']:
            if name in data.columns:
                nphi_col = name
                break
        for name in ['GR']:
            if name in data.columns:
                gr_col = name
                break
        
        if density_col and rt_col:
            density_vals = data[density_col].values
            rt_vals = data[rt_col].values
            nphi_vals = data[nphi_col].values if nphi_col else None
            gr_vals = data[gr_col].values if gr_col else None
            
            for i in range(len(data)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(data), i + window_size // 2)
                
                win_density = density_vals[start_idx:end_idx]
                win_rt = rt_vals[start_idx:end_idx]
                
                valid_ratio = (win_density > 0).sum() / len(win_density)
                if valid_ratio < 0.5:
                    continue
                
                # 砂泥岩段特征：密度>2.45（最低岩石密度）且电阻率<100
                sand_shale_density_ratio = (win_density > 2.45).sum() / len(win_density)
                low_rt_ratio = (win_rt < 100).sum() / len(win_rt)
                
                # 碳酸盐岩段特征：密度>2.65（接近灰岩骨架密度）且电阻率>100
                high_density_ratio = (win_density > 2.65).sum() / len(win_density)
                high_rt_ratio = (win_rt > 100).sum() / len(win_rt)
                
                # 结合交汇图特征判断
                # 碳酸盐岩区：密度较高(>2.65)，电阻率较高(>100)，伽马较低(<60)
                # 砂泥岩区：密度中等(2.45-2.65)，电阻率较低(<100)，伽马较高(>60)
                
                is_carbonate = False
                is_sand_shale = False
                
                # 碳酸盐岩段判断（降低阈值，更容易识别）
                if high_density_ratio > 0.3 and high_rt_ratio > 0.3:
                    is_carbonate = True
                    # 辅助判断：伽马低（<60）更支持碳酸盐岩
                    if gr_col:
                        win_gr = gr_vals[start_idx:end_idx]
                        win_gr_valid = win_gr[win_gr > 0]
                        if len(win_gr_valid) > 0:
                            low_gr_ratio = (win_gr_valid < 60).sum() / len(win_gr_valid)
                            if low_gr_ratio > 0.5:
                                is_carbonate = True
                
                # 砂泥岩段判断
                if sand_shale_density_ratio > 0.5 and low_rt_ratio > 0.5:
                    is_sand_shale = True
                
                # 最终判定
                if is_carbonate:
                    segment_type[i] = 'carbonate'
                elif is_sand_shale:
                    segment_type[i] = 'sand_shale'
        
        return segment_type
    
    def analyze_multi_crossplot_cluster(self, data):
        """
        基于多种交汇图的综合K-means聚类分析
        
        技术实现：
        1. 密度-声波（DEN-DT）：区分致密岩石和疏松岩石
        2. PE-密度（PE-DEN）：区分碳酸盐岩（高PE、高密度）和砂泥岩（低PE、中低密度）
        3. CNL-密度（CNL-DEN）：识别气层（中子低、密度低）和重矿物（中子低、密度高）
        
        返回每个深度点的岩性分类结果
        """
        from sklearn.cluster import KMeans
        
        # 收集可用的曲线
        available_curves = []
        curve_names = []
        
        density_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        ac_col = 'DT' if 'DT' in data.columns else ('AC' if 'AC' in data.columns else None)
        pe_col = 'PE' if 'PE' in data.columns else ('PEF' if 'PEF' in data.columns else None)
        cnl_col = 'NPHI' if 'NPHI' in data.columns else ('CNL' if 'CNL' in data.columns else None)
        
        if density_col:
            available_curves.append(data[density_col].values)
            curve_names.append('DEN')
        if ac_col:
            available_curves.append(data[ac_col].values)
            curve_names.append('AC')
        if pe_col:
            # PE不可信时不参与聚类（避免高PE干扰砂泥岩分类）
            pe_quality = getattr(self, 'pe_quality', {})
            if not pe_quality.get('pe_reliable', True):
                logger.info("PE不可信，多交汇图聚类跳过PE曲线")
            else:
                available_curves.append(data[pe_col].values)
                curve_names.append('PE')
        if cnl_col:
            cnl_values = data[cnl_col].values
            if cnl_values.max() > 1:
                cnl_values = cnl_values / 100.0
            available_curves.append(cnl_values)
            curve_names.append('CNL')
        
        if len(available_curves) < 2:
            logger.warning("可用曲线不足2条，无法进行交汇图聚类")
            return None
        
        # 构建特征矩阵
        features = np.column_stack(available_curves)
        
        # 处理NaN值
        valid_mask = ~np.any(np.isnan(features), axis=1)
        if np.sum(valid_mask) < 20:
            logger.warning("有效数据点不足，无法进行交汇图聚类")
            return None
        
        valid_features = features[valid_mask]
        
        # 标准化特征
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(valid_features)
        
        # 使用K-means聚类
        n_clusters = min(5, len(valid_features) // 50)
        if n_clusters < 2:
            n_clusters = 2
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(scaled_features)
        
        # 将聚类中心转换回原始坐标
        cluster_centers = scaler.inverse_transform(kmeans.cluster_centers_)
        
        # 识别每个聚类对应的岩性类型
        lith_labels = ['unknown'] * n_clusters
        cluster_skeleton = {}
        
        for i, center in enumerate(cluster_centers):
            distances = {}
            center_dict = dict(zip(curve_names, center))
            
            for lith, params in self.theoretical_skeleton.items():
                dist_sum = 0
                weight_sum = 0
                
                if 'DEN' in center_dict and 'density' in params:
                    dist_sum += (center_dict['DEN'] - params['density']) ** 2 * 2.0
                    weight_sum += 2.0
                if 'AC' in center_dict and 'ac' in params:
                    dist_sum += ((center_dict['AC'] - params['ac']) / 10) ** 2 * 1.5
                    weight_sum += 1.5
                if 'PE' in center_dict and 'pe' in params:
                    dist_sum += (center_dict['PE'] - params['pe']) ** 2 * 2.5
                    weight_sum += 2.5
                if 'CNL' in center_dict and 'cnl' in params:
                    dist_sum += (center_dict['CNL'] - params['cnl']) ** 2 * 2.0
                    weight_sum += 2.0
                
                if weight_sum > 0:
                    distances[lith] = np.sqrt(dist_sum / weight_sum)
                else:
                    distances[lith] = float('inf')
            
            best_lith = min(distances, key=distances.get)
            second_best_lith = sorted(distances.items(), key=lambda x: x[1])[1][0]
            distance_diff = distances[second_best_lith] - distances[best_lith]
            
            if distances[best_lith] < 0.15 and distance_diff > 0.05:
                lith_labels[i] = best_lith
                cluster_skeleton[best_lith] = center_dict
        
        # 将聚类结果映射回原始数据
        depth_lithology = {}
        lithology_array = np.array(['unknown'] * len(data))
        lithology_array[valid_mask] = [lith_labels[label] for label in labels]
        
        # 创建深度级别岩性字典
        depth_col = 'DEPT' if 'DEPT' in data.columns else ('DEPTH' if 'DEPTH' in data.columns else None)
        if depth_col:
            depths = data[depth_col].values
            for i, lith in enumerate(lithology_array):
                if lith != 'unknown':
                    depth_lithology[depths[i]] = lith
        
        logger.info(f"多交汇图聚类完成，识别到的岩性类型：{list(set(lith_labels))}")
        
        return {
            'lithology_array': lithology_array,
            'depth_lithology': depth_lithology,
            'cluster_skeleton': cluster_skeleton,
            'cluster_centers': cluster_centers,
            'curve_names': curve_names
        }
    
    def run_crossplot_analysis(self, data):
        """运行所有交汇图分析，综合确定本井主要岩性"""
        result = {
            'main_lithology': [],
            'estimated_skeleton': self.theoretical_skeleton.copy(),
            'depth_lithology': {}
        }
        
        # 密度-声波时差交汇图（最主要）
        density_ac_result = self.analyze_density_ac_crossplot(data)
        if density_ac_result:
            result['main_lithology'].extend(density_ac_result['main_lithology'])
            for lith, params in density_ac_result['estimated_skeleton'].items():
                result['estimated_skeleton'][lith].update(params)
        
        # PE-密度交汇图
        pe_result = self.analyze_pe_density_crossplot(data)
        if pe_result:
            for lith, params in pe_result.items():
                result['estimated_skeleton'][lith].update(params)
        
        # CNL-密度交汇图
        cnl_result = self.analyze_cnl_density_crossplot(data)
        if cnl_result:
            for lith, params in cnl_result.items():
                result['estimated_skeleton'][lith].update(params)
        
        # 多交汇图综合聚类分析（新增）
        multi_cluster_result = self.analyze_multi_crossplot_cluster(data)
        if multi_cluster_result:
            result['depth_lithology'] = multi_cluster_result['depth_lithology']
            # 更新主要岩性列表
            unique_liths = list(set(multi_cluster_result['lithology_array']))
            unique_liths = [l for l in unique_liths if l != 'unknown']
            if unique_liths:
                result['main_lithology'].extend(unique_liths)
            # 更新骨架参数
            for lith, params in multi_cluster_result['cluster_skeleton'].items():
                if lith in result['estimated_skeleton']:
                    result['estimated_skeleton'][lith].update(params)
        
        result['main_lithology'] = list(set(result['main_lithology']))
        if not result['main_lithology']:
            result['main_lithology'] = ['sandstone']
        
        logger.info(f"综合交汇图分析结果：主要岩性 {result['main_lithology']}")
        
        return result


# --- 特殊岩性图版分析类 ---
class SpecialLithologyPlateAnalyzer:
    """特殊岩性图版分析类，用于火山岩等特殊岩性识别"""
    
    def __init__(self):
        """初始化图版分析器"""
        pass
    
    def analyze_tas_plate(self, data):
        """TAS图版分析，用于火山岩分类"""
        si_col = 'SI' if 'SI' in data.columns else None
        ti_col = 'TI' if 'TI' in data.columns else None
        
        if si_col is None or ti_col is None:
            return None
        
        si_values = data[si_col].values
        ti_values = data[ti_col].values
        
        valid_mask = (si_values > -150) & (si_values < 100) & (ti_values > -100) & (ti_values < 50)
        if np.sum(valid_mask) < 10:
            return None
        
        result = []
        for si, ti in zip(si_values[valid_mask], ti_values[valid_mask]):
            # TAS图版分类规则（简化版）
            if si >= -40 and si <= 80:
                if ti >= -60 and ti <= -20:
                    result.append('basalt')
                elif ti > -20 and ti <= 10:
                    result.append('andesite')
                elif ti > 10 and ti <= 50:
                    result.append('dacite')
            elif si > 80 and si <= 100:
                if ti >= -60 and ti <= 50:
                    result.append('rhyolite')
            elif si >= -150 and si < -40:
                if ti >= -60 and ti <= 50:
                    result.append('komatiite')
        
        if result:
            from collections import Counter
            counter = Counter(result)
            dominant_type = counter.most_common(1)[0][0]
            return {'volcanic_type': dominant_type, 'distribution': dict(counter)}
        
        return None
    
    def analyze_pqf_plate(self, data):
        """PQF图版分析，用于区分不同成因石英"""
        qm_col = 'QM' if 'QM' in data.columns else None
        qp_col = 'QP' if 'QP' in data.columns else None
        
        if qm_col is None or qp_col is None:
            return None
        
        qm_values = data[qm_col].values
        qp_values = data[qp_col].values
        
        result = []
        for qm, qp in zip(qm_values, qp_values):
            total_q = qm + qp
            if total_q > 0:
                qm_ratio = qm / total_q
                qp_ratio = qp / total_q
                
                if qm_ratio > 0.7:
                    result.append('igneous_quartz')
                elif qp_ratio > 0.7:
                    result.append('metamorphic_quartz')
                else:
                    result.append('sedimentary_quartz')
        
        if result:
            from collections import Counter
            counter = Counter(result)
            dominant_type = counter.most_common(1)[0][0]
            return {'quartz_type': dominant_type, 'distribution': dict(counter)}
        
        return None


# --- 深度分段判别类 ---
class SegmentClassifier:
    """深度分段判别类，使用滑动窗口和聚类算法自动划分岩性段"""
    
    def __init__(self, well_name='Unknown', output_dir='output'):
        """初始化分段判别器"""
        self.well_name = well_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
    
    def load_lith_profile(self):
        """读取井名+lithprofile.json文件"""
        profile_path = self.output_dir / f"{self.well_name}_lithprofile.json"
        if profile_path.exists():
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取剖面文件失败: {e}")
                return None
        return None
    
    def save_lith_profile(self, profile_data):
        """保存剖面数据到井名+lithprofile.json文件"""
        profile_path = self.output_dir / f"{self.well_name}_lithprofile.json"
        try:
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
            logger.info(f"剖面数据已保存到: {profile_path}")
            return str(profile_path)
        except Exception as e:
            logger.error(f"保存剖面文件失败: {e}")
            return None
    
    def extract_window_features(self, data, window_size=50):
        """
        使用滑动窗口提取统计特征
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）
            
        返回:
            features: 特征矩阵 (n_samples x n_features)
            feature_names: 特征名称列表
        """
        n_samples = len(data)
        feature_names = []
        features = []
        
        # 需要提取的曲线和统计量
        curve_stats = {
            'RHOB': ['mean', 'median', 'std'],
            'DEN': ['mean', 'median', 'std'],
            'RT': ['mean', 'median', 'std'],
            'LLD': ['mean', 'median', 'std'],
            'GR': ['mean', 'median', 'std'],
            'PE': ['mean', 'median', 'std'],
            'PEF': ['mean', 'median', 'std'],
            'DT': ['mean', 'median', 'std'],
            'AC': ['mean', 'median', 'std'],
            'NPHI': ['mean', 'median', 'std'],
            'CNL': ['mean', 'median', 'std']
        }
        
        # 构建特征名称
        for curve_name, stats in curve_stats.items():
            if curve_name in data.columns:
                for stat in stats:
                    feature_names.append(f"{curve_name}_{stat}")
        
        # 提取特征
        for i in range(n_samples):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(n_samples, i + window_size // 2)
            
            window_data = data.iloc[start_idx:end_idx]
            sample_features = []
            
            for curve_name, stats in curve_stats.items():
                if curve_name in data.columns:
                    values = window_data[curve_name].dropna().values
                    if len(values) > 0:
                        for stat in stats:
                            if stat == 'mean':
                                sample_features.append(np.mean(values))
                            elif stat == 'median':
                                sample_features.append(np.median(values))
                            elif stat == 'std':
                                sample_features.append(np.std(values))
                    else:
                        for stat in stats:
                            sample_features.append(np.nan)
            
            features.append(sample_features)
        
        features = np.array(features)
        return features, feature_names
    
    def classify_segments(self, data, window_size=50, n_clusters=3):
        """
        使用K-means聚类自动划分岩性段
        
        技术实现：
        1. 数据输入：将交汇图中的每一个数据点（代表一个深度点的测井响应）作为输入
        2. 自动分组：算法根据数据点在图中的"聚集"趋势，自动将相似的数据点划分为若干个群组
        3. 识别岩性：每个群组通常对应一种特定的岩性
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小
            n_clusters: 聚类数量
            
        返回:
            local_profile_type: 每个深度点的局部剖面类型数组
            cluster_info: 聚类中心和统计信息
        """
        # 首先进行多交汇图聚类分析（识别主要岩性）
        crossplot_analyzer = LithologyCrossplotAnalyzer()
        multi_cluster_result = crossplot_analyzer.analyze_multi_crossplot_cluster(data)
        
        # 如果交汇图聚类成功，获取深度级别的岩性分类
        if multi_cluster_result:
            lithology_array = multi_cluster_result['lithology_array']
            logger.info(f"多交汇图聚类识别到的岩性：{list(set(lithology_array))}")
        
        # 提取统计特征（用于确定剖面类型）
        features, feature_names = self.extract_window_features(data, window_size)
        
        # 处理NaN值
        valid_mask = ~np.any(np.isnan(features), axis=1)
        if np.sum(valid_mask) < n_clusters * 10:
            logger.warning("有效特征点不足，使用默认分段")
            return np.array(['mixed'] * len(data)), None
        
        valid_features = features[valid_mask]
        
        # 使用K-means聚类
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(valid_features)
        
        # 映射聚类标签到剖面类型
        # 根据聚类中心的特征值判断每个簇的类型
        cluster_centers = kmeans.cluster_centers_
        cluster_types = ['mixed'] * n_clusters
        
        # 找到关键特征的索引
        rho_mean_idx = None
        rt_mean_idx = None
        gr_mean_idx = None
        pe_mean_idx = None
        
        for i, name in enumerate(feature_names):
            if 'RHOB_mean' == name or 'DEN_mean' == name:
                rho_mean_idx = i
            elif 'RT_mean' == name or 'LLD_mean' == name:
                rt_mean_idx = i
            elif 'GR_mean' == name:
                gr_mean_idx = i
            elif 'PE_mean' == name or 'PEF_mean' == name:
                pe_mean_idx = i
        
        # 计算每个簇的倾向指数（综合交汇图结果和统计特征）
        # 同时计算砂泥岩倾向指数和碳酸盐岩倾向指数，取较高者
        for i in range(n_clusters):
            center = cluster_centers[i]
            
            carbonate_score = 0  # 碳酸盐岩倾向指数
            sand_shale_score = 0  # 砂泥岩倾向指数
            weight_sum = 0
            
            # 密度指标
            # 高密度(>2.65)倾向碳酸盐岩，中等密度(2.45-2.65)倾向砂泥岩
            if rho_mean_idx is not None:
                rho_mean = center[rho_mean_idx]
                if rho_mean > 2.65:
                    carbonate_score += min((rho_mean - 2.65) / 0.2, 1.0) * 0.3
                elif rho_mean > 2.45:
                    sand_shale_score += min((rho_mean - 2.45) / 0.2, 1.0) * 0.3
                weight_sum += 0.3
            
            # 电阻率指标
            # 高电阻率(>100)倾向碳酸盐岩，低电阻率(<100)倾向砂泥岩
            if rt_mean_idx is not None:
                rt_mean = center[rt_mean_idx]
                rt_median = np.median(valid_features[:, rt_mean_idx])
                if rt_mean > rt_median * 2:
                    carbonate_score += 0.3
                elif rt_mean < rt_median:
                    sand_shale_score += 0.3
                weight_sum += 0.3
            
            # GR指标
            # 低GR(<60)倾向碳酸盐岩，高GR(>70)倾向砂泥岩
            if gr_mean_idx is not None:
                gr_mean = center[gr_mean_idx]
                if gr_mean < 60:
                    carbonate_score += 0.2
                elif gr_mean > 70:
                    sand_shale_score += 0.2
                weight_sum += 0.2
            
            # PE指标（需与密度一致性校验）
            # 碳酸盐岩：PE>3.0 且 密度>2.65 或 GR<60 → 可信
            # 砂泥岩：PE<2.5 且 密度2.45-2.65 → 可信
            # PE>3.0 但 密度<2.65：PE与密度不一致，PE质量存疑，不用于岩性判断
            if pe_mean_idx is not None:
                pe_mean = center[pe_mean_idx]
                rho_val = center[rho_mean_idx] if rho_mean_idx is not None else 2.65
                gr_val = center[gr_mean_idx] if gr_mean_idx is not None else 80
                rt_val = center[rt_mean_idx] if rt_mean_idx is not None else 50
                
                # PE质量校验：密度<2.65的砂泥岩剖面，PE应<3
                # PE>3时密度却不支持，说明PE不可信
                pe_trustworthy = True
                if pe_mean > 3.0 and rho_val < 2.65:
                    # PE与密度不一致：低密度不可能对应碳酸盐岩
                    # 典型砂泥岩密度范围，PE偏高属于仪器异常
                    pe_trustworthy = False
                elif pe_mean > 3.0 and rho_val >= 2.65:
                    # 密度支持碳酸盐岩，进一步校验GR和RT
                    if gr_val > 80:
                        # 高GR+高PE矛盾（泥岩PE约3.45，>3.0但不会太高）
                        # GR>80说明泥质含量高，不应该是纯净碳酸盐岩
                        pe_trustworthy = False
                    elif rt_val < 20:
                        # 低RT+高PE矛盾（碳酸盐岩通常RT较高）
                        pe_trustworthy = False
                
                if pe_trustworthy:
                    if pe_mean > 3.0:
                        carbonate_score += 0.2
                    elif pe_mean < 2.5:
                        sand_shale_score += 0.2
                    weight_sum += 0.2
                else:
                    # PE不可信，不参与评分
                    pass
            
            if weight_sum > 0:
                carbonate_score /= weight_sum
                sand_shale_score /= weight_sum
            
            # 根据倾向指数判断类型（砂泥岩优先原则）
            # 如果砂泥岩指数较高，优先判定为砂泥岩
            if sand_shale_score > carbonate_score + 0.05:
                cluster_types[i] = 'sand_shale'
            elif carbonate_score > sand_shale_score + 0.1:
                cluster_types[i] = 'carbonate'
            else:
                cluster_types[i] = 'mixed'
        
        # 将聚类结果映射回原始数据
        local_profile_type = np.array(['mixed'] * len(data))
        local_profile_type[valid_mask] = [cluster_types[label] for label in labels]
        
        # 结合交汇图聚类结果进行修正（谨慎修正，避免过度覆盖）
        # 使用加权投票方式，交汇图结果权重较低，统计特征权重较高
        if multi_cluster_result:
            lithology_array = multi_cluster_result['lithology_array']
            carbonate_liths = ['limestone', 'dolomite', 'anhydrite']
            
            for i in range(len(data)):
                # 只有当交汇图明确识别且统计特征不反对时才修正
                if lithology_array[i] in carbonate_liths:
                    # 只有当前已判定为mixed时才修正为carbonate
                    if local_profile_type[i] == 'mixed':
                        local_profile_type[i] = 'carbonate'
                elif lithology_array[i] in ['sandstone', 'shale']:
                    # 只有当前已判定为mixed时才修正为sand_shale
                    if local_profile_type[i] == 'mixed':
                        local_profile_type[i] = 'sand_shale'
        
        # 统计每个类型的数量
        from collections import Counter
        counter = Counter(local_profile_type)
        logger.info(f"聚类结果统计: {dict(counter)}")
        
        # 保存聚类信息
        cluster_info = {
            'n_clusters': n_clusters,
            'window_size': window_size,
            'cluster_types': cluster_types,
            'cluster_centers': {i: {feature_names[j]: float(cluster_centers[i, j]) for j in range(len(feature_names))} for i in range(n_clusters)},
            'statistics': dict(counter)
        }
        
        return local_profile_type, cluster_info
    
    def segment_classification(self, data, window_size=50, n_clusters=3):
        """
        深度分段判别主函数
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小
            n_clusters: 聚类数量
            
        返回:
            local_profile_type: 每个深度点的局部剖面类型数组
        """
        # 首先尝试读取已有的剖面文件
        profile_data = self.load_lith_profile()
        
        if profile_data and 'local_profile_type' in profile_data:
            # 检查数据长度是否匹配
            if len(profile_data['local_profile_type']) == len(data):
                logger.info(f"使用已有的剖面文件: {self.well_name}_lithprofile.json")
                return np.array(profile_data['local_profile_type'])
            else:
                logger.warning(f"剖面文件数据长度不匹配（旧文件:{len(profile_data['local_profile_type'])}, 当前数据:{len(data)}），弃用旧文件重新建立")
        
        # 如果没有或长度不匹配，进行自动分段
        logger.info("进行自动深度分段判别...")
        local_profile_type, cluster_info = self.classify_segments(data, window_size, n_clusters)
        
        # 保存结果
        profile_data = {
            'well_name': self.well_name,
            'segmentation_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'window_size': window_size,
            'n_clusters': n_clusters,
            'local_profile_type': list(local_profile_type),
            'cluster_info': cluster_info,
            'manual_edits': []
        }
        self.save_lith_profile(profile_data)
        
        return local_profile_type


# --- 多矿物分析类 ---
class MineralAnalyzer:
    """多矿物分析类，使用最优化方法计算矿物含量和流体饱和度"""
    
    def __init__(self, config=None):
        """初始化多矿物分析器"""
        # 读取配置文件
        self.config = self._load_config()
        if config:
            self.config.update(config)
        
        # 定义矿物及流体响应参数
        self.minerals = ['Quartz', 'Calcite', 'Dolomite', 'Anhydrite', 'Halite', 'Clay']
        self.fluids = ['Water', 'Oil', 'Gas']
        
        # 响应参数表（每行为一种组分，列为不同测井曲线）
        # 曲线顺序：DEN, CNL, AC, PE, GR
        # 单位：DEN(g/cm3), CNL(小数), AC(us/ft), PE(b/e), GR(API)
        self.params = {
            'Quartz':  [2.65, -0.02, 55.5, 1.81, 30],
            'Calcite': [2.71,  0.00, 47.5, 5.08, 15],
            'Dolomite':[2.87,  0.02, 43.5, 3.14, 20],
            'Anhydrite':[2.98, 0.0, 37.5, 5.0, 10],   # 硬石膏
            'Halite':  [2.03,  0.00, 67.0, 4.70, 5],   # 盐岩NaCl
            'Clay':    [2.55,  0.35, 80.0, 3.45, 150],
            'Water':   [1.00,  1.00, 189.0, 0.00, 0],
            'Oil':     [0.85,  0.80, 220.0, 0.00, 0],
            'Gas':     [0.25,  0.20, 350.0, 0.00, 0]
        }
        
        # 密度孔隙度优先标志（由2012国标质量评价确定）
        self.use_density_porosity = True
    
    def _load_config(self):
        """加载logint.json配置文件"""
        config_path = Path(__file__).parent / 'logint.json'
        if config_path.exists():
            try:
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
        return {
            # 泥质含量计算方法: 1=仅GR法, 2=仅密度中子交汇法, 3=两者结合取平均值(推荐), 6=高级7方法共识融合
            'vsh_method': 6,
            # 地层年代: 'paleozoic'=古生界(C=2), 'mesozoic'=中生界(C=2.5~3), 'cenozoic'=新生界(C=3.7~4), 'auto'=自动(默认C=2)
            'formation_age': 'auto',
            # 剖面类型: 'sand_shale'=砂泥岩剖面, 'carbonate'=碳酸盐岩剖面, ''=自动判定
            'profile_type': '',
            # 泥质含量阈值: shale_min=泥岩判定下限(>此值为泥岩), sand_max=砂岩判定上限(<此值为砂岩)
            'vsh_threshold': {'shale_min': 0.6, 'sand_max': 0.3},
            # 孔隙度阈值: 低于此值的层不参与解释
            'porosity_threshold': 0.05,
            # 电阻率阈值: 用于剖面类型判定
            'resistivity_threshold': 20,
            # 阿尔奇公式参数: a=常数, m=胶结指数, n=饱和度指数, Rw=地层水电阻率(Ω·m), Rsh=泥岩电阻率(Ω·m)
            'archie': {'a': 1.0, 'm': 2.0, 'n': 2.0, 'Rw': 0.05, 'Rsh': 2.0},
            # 油气水解释参数
            'interpretation': {
                'min_porosity': 0.08,           # 最小孔隙度阈值(<此值不解释)
                'max_vsh_for_oil_gas': 0.5,     # 油气层最大泥质含量
                'min_sw_for_water': 0.6,        # 水层最小含水饱和度
                'max_sw_for_oil': 0.5,          # 油层最大含水饱和度
                'max_sw_for_gas': 0.4,          # 气层最大含水饱和度
                'min_resistivity_for_oil': 20,   # 油层最小电阻率(Ω·m)
                'min_resistivity_for_gas': 50,   # 气层最小电阻率(Ω·m)
                'min_resistivity_for_water': 10, # 水层最小电阻率(Ω·m)
                'similarity_threshold': 0.5      # 相似度阈值(>此值才参与判定)
            },
            # 可视化参数
            'visualization': {
                'title_height_cm': 2,       # 图名高度(厘米)
                'title_las_gap_cm': 1,     # 图名与LAS信息区间隔(厘米)
                'las_height_cm': 4,        # LAS信息区高度(厘米)
                'las_header_gap_cm': 0.5,  # LAS信息区与图头区间隔(厘米)
                'header_height_cm': 7,     # 图头区高度(厘米)
                'depth_scale': 200,        # 深度比例尺(1:200)
                'cal_scale_min': 6,        # 井径刻度最小值(in)
                'cal_scale_max': 16,       # 井径刻度最大值(in)
                'gr_scale_min': 0,         # GR刻度最小值(API)
                'gr_scale_max': 200,       # GR刻度最大值(API)
                'sp_scale_min': -100,      # SP刻度最小值(mV)
                'sp_scale_max': 100,       # SP刻度最大值(mV)
                'den_scale_min': 1.85,     # 密度刻度最小值(g/cm3)
                'den_scale_max': 2.85,     # 密度刻度最大值(g/cm3)
                'nphi_scale_min': -0.15,   # 中子刻度最小值(小数)
                'nphi_scale_max': 0.45,    # 中子刻度最大值(小数)
                'ac_scale_min': 40,        # 声波刻度最小值(us/ft)
                'ac_scale_max': 140,       # 声波刻度最大值(us/ft)
                'resistivity_scale_min': 0.2,  # 电阻率刻度最小值(Ω·m)
                'resistivity_scale_max': 2000  # 电阻率刻度最大值(Ω·m)
            },
            # 多矿物模型参数
            'mineral_model': {
                'use_u_value': True,           # 是否使用U值参与最优化计算
                'max_carbonate_for_sand_shale': 0.1,  # 砂泥岩剖面最大碳酸盐含量
                'min_density_for_carbonate': 2.65,    # 碳酸盐岩最小密度(g/cm3)
                'min_resistivity_for_carbonate': 100,   # 碳酸盐岩最小电阻率(Ω·m)
                'lambda_reg': 0.05             # L1正则化系数(控制稀疏程度, 0.01~0.1)
            }
        }
    
    def _normalize_mineral_contents(self, data):
        """归一化矿物含量，确保所有矿物含量+孔隙度之和等于1"""
        try:
            mineral_cols = [f'V{m}' for m in self.minerals]
            mineral_cols = [col for col in mineral_cols if col in data.columns]
            
            if not mineral_cols:
                return data
            
            total = data[mineral_cols].sum(axis=1)
            if 'PHI' in data.columns:
                total += data['PHI']
            
            mask = total > 0
            for col in mineral_cols:
                data.loc[mask, col] = data.loc[mask, col] / total[mask]
            if 'PHI' in data.columns:
                data.loc[mask, 'PHI'] = data.loc[mask, 'PHI'] / total[mask]
            
            return data
        except Exception as e:
            logger.error(f"归一化矿物含量失败: {e}")
            return data
    
    def detect_gr_baseline(self, data):
        """
        自动检测本井的泥岩GR基线值
        原理：泥岩通常GR最高且最稳定，取GR分布的高端众数或P90分位数作为基线
        """
        if 'GR' not in data.columns:
            logger.warning("GR曲线不存在，使用默认基线80 API")
            return 80.0
        
        gr_values = data['GR'].dropna().values
        
        if len(gr_values) < 50:
            gr_baseline = np.percentile(gr_values, 90)
        else:
            hist, bin_edges = np.histogram(gr_values, bins=50)
            peak_bin = np.argmax(hist)
            peak_value = bin_edges[peak_bin]
            
            gr_baseline = np.percentile(gr_values, 85)
            
            if gr_baseline < 40:
                gr_baseline = np.median(gr_values) + 0.5 * np.std(gr_values)
        
        gr_baseline = max(gr_baseline, 30)
        logger.info(f"本井泥岩GR基线自动识别为: {gr_baseline:.1f} API")
        return gr_baseline
    
    def apply_4param_geological_prison(self, row, gr_baseline, pe_unreliable=False):
        """
        输入：单行测井值 + 本井GR基线
        输出：矿物含量的硬性上下界 [Quartz, Calcite, Dolomite, Anhydrite, Halite, Clay]
        
        PE质量检查：当密度低、电阻率低、伽玛有明显砂泥岩变化特征时，PE不应该大于3
        井径大时PE曲线可能虚高，导致砂泥岩被误判为碳酸盐岩
        pe_unreliable: 当全局PE质量检测判定PE不可信时，跳过所有PE相关约束
        """
        lower = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        upper = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        
        den = row.get('DEN', row.get('RHOB', 2.65))
        pe = row.get('PE', 2.0)
        rt = row.get('RT', row.get('LLD', 50))
        gr = row.get('GR', 80)
        
        # 计算泥质含量（取伽玛计算和密度中子交汇的较低值）
        vsh = row.get('VSH', 0)
        
        # 如果没有VSH，使用GR计算泥质含量
        if vsh == 0 or np.isnan(vsh):
            gr_rel = gr / gr_baseline
            vsh = gr_rel
        
        # ============ PE质量检查与修正 ============
        # 当密度低、电阻率低、泥质含量有明显砂泥岩变化时，PE不应该大于3
        # 这种情况通常是井径大导致PE虚高
        pe_valid = True
        corrected_pe = pe
        
        # 场景1：纯砂岩特征（密度低+电阻率低+泥质含量低），PE不应大于3.0
        if den < 2.60 and rt < 80 and vsh < 0.4:
            if pe > 3.0:
                corrected_pe = min(pe, 2.8)
                pe_valid = False
        
        # 场景2：泥岩特征（密度中等+电阻率低+泥质含量高），PE不应大于3.5
        elif den < 2.55 and rt < 60 and vsh > 0.5:
            if pe > 3.5:
                corrected_pe = min(pe, 3.3)
                pe_valid = False
        
        # 场景3：砂泥岩过渡带（密度低+电阻率中等），PE不应大于3.2
        elif den < 2.62 and rt < 100:
            if pe > 3.2:
                corrected_pe = min(pe, 3.0)
                pe_valid = False
        
        # 场景4：泥质含量大于0.6，明显砂泥岩特征，PE不应大于3
        if vsh > 0.6 and den < 2.65 and rt < 100:
            if pe > 3.0:
                corrected_pe = min(pe, 2.8)
                pe_valid = False
        
        # 使用修正后的PE值进行判断
        pe = corrected_pe
        
        # ========== 全局PE不可信：跳过所有PE相关约束，避免将砂泥岩误判为碳酸盐岩 ==========
        if pe_unreliable:
            # PE不可信时，使用中性PE值（既不触发pe<2.8也不触发pe>4.0）
            pe = 3.0
        
        if pe < 2.8:
            upper[1] = 0.05
            upper[2] = 0.05
            upper[3] = 0.05
        
        if pe > 4.0:
            upper[0] = 0.30
        
        if vsh > 0.8:
            upper[0] = 0.10
            upper[1] = 0.05
            upper[2] = 0.05
            upper[3] = 0.05
            upper[4] = 1.0
        
        if vsh < 0.3:
            upper[4] = 0.15
        
        if 0.3 < vsh < 0.6 and pe < 2.8:
            upper[1] = min(upper[1], 0.05)
            upper[2] = min(upper[2], 0.05)
            upper[3] = min(upper[3], 0.05)
        
        if rt < 30:
            upper[1] = min(upper[1], 0.10)
            upper[2] = min(upper[2], 0.10)
            upper[3] = min(upper[3], 0.10)
        
        if rt > 200 and pe > 3.5:
            upper[0] = min(upper[0], 0.20)
            upper[4] = min(upper[4], 0.20)
        
        if den < 2.65 and pe < 2.8:
            upper[1] = min(upper[1], 0.02)
            upper[2] = min(upper[2], 0.02)
            upper[3] = min(upper[3], 0.02)
        
        if den < 2.65 and pe > 4.0:
            upper[0] = min(upper[0], 0.15)
        
        return lower, upper
    
    def calculate_vsh(self, data, vsh_method=3):
        """计算泥质含量，根据配置选择计算方法"""
        try:
            vsh_methods = []
            
            # 方法1：密度中子交汇计算泥质含量
            dn_vsh = None
            rho_col = None
            nphi_col = None
            for name in ['RHOB', 'DEN', 'DRHO']:
                if name in data.columns:
                    rho_col = name
                    break
            for name in ['NPHI', 'CNL', 'NPOR']:
                if name in data.columns:
                    nphi_col = name
                    break
            
            if rho_col and nphi_col:
                rho_sand = 2.65
                rho_shale = 2.58  # 修正：泥岩密度约2.55-2.60，原值2.71是灰岩密度！
                nphi_sand = 0.0
                nphi_shale = 0.4
                
                # 密度方向反转：密度越低越接近泥岩（密度低于砂岩骨架=泥质增加）
                # 密度高于砂岩骨架的岩石（如灰岩2.71、白云岩2.87）不会被误判为泥质
                # 先替换异常值（-9999等）为NaN，避免污染计算
                rho_clean = data[rho_col].where((data[rho_col] > 0) & (data[rho_col] < 5), np.nan)
                nphi_clean = data[nphi_col].where((data[nphi_col] > -0.15) & (data[nphi_col] < 1.5), np.nan)
                rho_vsh = (rho_sand - rho_clean) / (rho_sand - rho_shale)
                nphi_values = nphi_clean / 100.0 if nphi_clean.max() > 1 else nphi_clean
                nphi_vsh = (nphi_values - nphi_sand) / (nphi_shale - nphi_sand)
                dn_vsh = (rho_vsh + nphi_vsh) / 2
                dn_vsh = dn_vsh.clip(0, 1)
            
            # 方法2：GR分位数计算泥质含量
            gr_vsh = None
            if 'GR' in data.columns:
                gr_data = data['GR'].dropna()
                # 过滤掉-9999/<=0等异常值，只使用正常测量值统计
                gr_valid = gr_data[(gr_data > 0) & (gr_data < 500)]
                if len(gr_valid) > 0:
                    gr_min = gr_valid.quantile(0.1)
                    gr_max = gr_valid.quantile(0.9)
                    
                    if gr_max <= gr_min:
                        gr_min = gr_valid.min()
                        gr_max = gr_valid.max()
                    
                    if gr_max > gr_min:
                        gr_vsh = (data['GR'] - gr_min) / (gr_max - gr_min)
                        gr_vsh = gr_vsh.clip(0, 1)
            
            # 根据vsh_method选择计算方法
            # 1: 仅GR方法
            # 2: 仅密度中子交汇方法
            # 3: 两者结合取平均值（默认）
            # 6: 高级6方法共识融合（含SP法）
            if vsh_method == 6:
                data = self.calculate_vsh_advanced(data)
                return data
            elif vsh_method == 1:
                if gr_vsh is not None:
                    data['VSH'] = gr_vsh
                elif dn_vsh is not None:
                    data['VSH'] = dn_vsh
                else:
                    data['VSH'] = 0
            elif vsh_method == 2:
                if dn_vsh is not None:
                    data['VSH'] = dn_vsh
                elif gr_vsh is not None:
                    data['VSH'] = gr_vsh
                else:
                    data['VSH'] = 0
            else:
                if gr_vsh is not None and dn_vsh is not None:
                    # 逐点平均：两个方法都有效时取平均，只有一个有效时用该值，都无效时为NaN
                    vsh_sum = gr_vsh.fillna(0) + dn_vsh.fillna(0)
                    vsh_count = gr_vsh.notna().astype(int) + dn_vsh.notna().astype(int)
                    vsh_count = vsh_count.replace(0, np.nan)
                    data['VSH'] = vsh_sum / vsh_count
                elif gr_vsh is not None:
                    data['VSH'] = gr_vsh
                elif dn_vsh is not None:
                    data['VSH'] = dn_vsh
                else:
                    data['VSH'] = 0
            
            data['VSH'] = data['VSH'].clip(0, 1)
            return data
        except Exception as e:
            logger.error(f"计算泥质含量失败: {e}")
            data['VSH'] = 0
            return data
    
    def calculate_vsh_advanced(self, data):
        """
        高级泥质含量计算方法（8种方法共识融合，融合GR、SP、中子、密度、声波、电阻率6条曲线）
        
        核心原则：
        1. 使用至少8种独立方法计算VSH，融合GR、SP、中子、密度、声波、电阻率6条曲线
        2. 自动识别特殊干扰（煤层、气层、铀富集、长石）
        3. 多方法共识：至少3种方法一致才可信
        4. 有矛盾时先找干扰源，再选择合适方法
        
        8种方法（覆盖6条曲线）：
        V1: GR法 - 自然伽马指数，Larionov非线性公式 Vsh = (2^(C·ΔGR)-1)/(2^C-1)（GR曲线）
        V2: 密度-中子交汇法 - DEN+NPHI交汇（密度+中子交汇）
        V3: 声波法 - DT/AC相对值（声波曲线）
        V4: 电阻率法 - RT上限法 Vsh ≤ [ (Rsh/Rt)·(Rmax-Rt)/(Rmax-Rsh) ]^1/b（电阻率曲线）
        V5: 中子法 - NPHI单独（中子曲线）
        V6: 密度法 - DEN单独（密度曲线）
        V7: SP法 - 自然电位（SP曲线）
        V8: 能谱法 - KTH/无铀伽马（能谱曲线）
        
        C参数（Larionov公式）：古生界C=2，中生界C=2.5~3，新生界C=3.7~4
        """
        result = pd.Series(np.nan, index=data.index)
        
        # 获取地层年代参数，用于Larionov非线性公式
        formation_age = self.config.get('formation_age', 'auto')
        c_value = 2.0  # 默认C=2（古生界/最保守）
        if formation_age == 'paleozoic':
            c_value = 2.0
        elif formation_age == 'mesozoic':
            c_value = 2.8
        elif formation_age == 'cenozoic':
            c_value = 3.7
        else:  # 'auto' - 尝试从数据自动判断，默认C=2
            c_value = 2.0
        
        # ========== 1. 特殊干扰识别 ==========
        n = len(data)
        interference = pd.DataFrame({
            'coal':      np.zeros(n, dtype=bool),
            'gas':       np.zeros(n, dtype=bool),
            'uranium':   np.zeros(n, dtype=bool),
            'feldspar':  np.zeros(n, dtype=bool),
        }, index=data.index)
        
        # 煤层：低密度+高中子+高声波时差
        if 'RHOB' in data.columns and 'NPHI' in data.columns and 'DTCO' in data.columns:
            den_qc = data['RHOB'].where((data['RHOB'] > 0) & (data['RHOB'] < 5), np.nan)
            nphi_qc = data['NPHI'].where((data['NPHI'] > -0.15) & (data['NPHI'] < 1.5), np.nan)
            dt_qc = data['DTCO'].where((data['DTCO'] > 30) & (data['DTCO'] < 500), np.nan)
            nphi_pct = nphi_qc / 100.0 if nphi_qc.max() is not None and nphi_qc.max() > 1 else nphi_qc
            interference['coal'] = (
                (den_qc.fillna(2.65) < 1.8) & 
                (nphi_pct.fillna(0) > 0.3) & 
                (dt_qc.fillna(60) > 90)
            )
        
        # 气层：低密度+高中子交汇(挖掘效应)+高声波
        if 'RHOB' in data.columns and 'NPHI' in data.columns:
            den_qc = data['RHOB'].where((data['RHOB'] > 0) & (data['RHOB'] < 5), np.nan)
            nphi_qc = data['NPHI'].where((data['NPHI'] > -0.15) & (data['NPHI'] < 1.5), np.nan)
            nphi_pct = nphi_qc / 100.0 if nphi_qc.max() is not None and nphi_qc.max() > 1 else nphi_qc
            # 天然气挖掘效应：中子孔隙度明显低于密度孔隙度
            den_por = (2.65 - den_qc) / 1.65
            gas_effect = den_por - nphi_pct
            interference['gas'] = gas_effect.fillna(0) > 0.10
        
        # 铀富集：GR >> KTH, U > 10
        if 'GR' in data.columns and 'KTH' in data.columns and 'U' in data.columns:
            gr_qc = data['GR'].where((data['GR'] > 0) & (data['GR'] < 500), np.nan)
            kth_qc = data['KTH'].where((data['KTH'] > 0) & (data['KTH'] < 500), np.nan)
            u_qc = data['U'].where((data['U'] >= 0) & (data['U'] < 100), np.nan)
            interference['uranium'] = (
                ((gr_qc - kth_qc).fillna(0) > 30) &
                (u_qc.fillna(0) > 10)
            )
        elif 'GR' in data.columns and 'KTH' in data.columns:
            gr_qc = data['GR'].where((data['GR'] > 0) & (data['GR'] < 500), np.nan)
            kth_qc = data['KTH'].where((data['KTH'] > 0) & (data['KTH'] < 500), np.nan)
            interference['uranium'] = (gr_qc - kth_qc).fillna(0) > 40
        
        # 长石：GR中高但K/TH比值高
        if 'K' in data.columns and 'TH' in data.columns:
            k_qc = data['K'].where((data['K'] >= 0) & (data['K'] < 20), np.nan)
            th_qc = data['TH'].where((data['TH'] >= 0) & (data['TH'] < 100), np.nan)
            kth_ratio = k_qc / th_qc.replace(0, np.nan)
            interference['feldspar'] = kth_ratio.fillna(0) > 0.5
        
        # ========== 2. 计算6种VSH方法 ==========
        vsh_methods = {}
        
        # V1: GR法（Larionov非线性公式）
        vsh_gr = None
        if 'GR' in data.columns:
            gr_data = data['GR'].dropna()
            gr_valid = gr_data[(gr_data > 0) & (gr_data < 500)]
            if len(gr_valid) > 0:
                # 铀富集修正：使用KTH替代GR
                if interference['uranium'].any() and 'KTH' in data.columns:
                    kth_data = data['KTH'].dropna()
                    kth_valid = kth_data[(kth_data > 0) & (kth_data < 500)]
                    if len(kth_valid) > 0:
                        gr_min = kth_valid.quantile(0.1)
                        gr_max = kth_valid.quantile(0.9)
                        logger.info(f"  铀富集干扰，GR法改用KTH：P10={gr_min:.1f}, P90={gr_max:.1f}")
                        dgr = (data['KTH'] - gr_min) / (gr_max - gr_min)
                    else:
                        gr_min = gr_valid.quantile(0.1)
                        gr_max = gr_valid.quantile(0.9)
                        dgr = (data['GR'] - gr_min) / (gr_max - gr_min)
                else:
                    gr_min = gr_valid.quantile(0.1)
                    gr_max = gr_valid.quantile(0.9)
                    dgr = (data['GR'] - gr_min) / (gr_max - gr_min)
                # Larionov非线性公式: Vsh = (2^(C·ΔGR) - 1) / (2^C - 1)
                dgr_clip = dgr.clip(0, 1)
                vsh_gr = (2.0**(c_value * dgr_clip) - 1.0) / (2.0**c_value - 1.0)
                vsh_gr = vsh_gr.clip(0, 1)
                logger.info(f"  GR法(Larionov C={c_value})：GR_min={gr_min:.1f}, GR_max={gr_max:.1f}")
                # 铀富集点：GR法结果不可信，置为NaN
                if interference['uranium'].any():
                    vsh_gr = vsh_gr.where(~interference['uranium'], np.nan)
        vsh_methods['V1_GR'] = vsh_gr
        
        # V2: 密度-中子交汇法
        vsh_dn = None
        rho_col = None
        nphi_col = None
        for name in ['RHOB', 'DEN', 'DRHO']:
            if name in data.columns:
                rho_col = name
                break
        for name in ['NPHI', 'CNL', 'NPOR']:
            if name in data.columns:
                nphi_col = name
                break
        if rho_col and nphi_col:
            rho_sand, rho_shale = 2.65, 2.58
            nphi_sand, nphi_shale = 0.0, 0.4
            rho_clean = data[rho_col].where((data[rho_col] > 0) & (data[rho_col] < 5), np.nan)
            nphi_clean = data[nphi_col].where((data[nphi_col] > -0.15) & (data[nphi_col] < 1.5), np.nan)
            rho_vsh = (rho_sand - rho_clean) / (rho_sand - rho_shale)
            nphi_values = nphi_clean / 100.0 if (nphi_clean.max() if nphi_clean.notna().any() else 0) > 1 else nphi_clean
            nphi_vsh = (nphi_values - nphi_sand) / (nphi_shale - nphi_sand)
            vsh_dn = (rho_vsh + nphi_vsh) / 2
            vsh_dn = vsh_dn.clip(0, 1)
            # 煤层/气层：密度中子交汇法结果不可信
            if interference['coal'].any():
                vsh_dn = vsh_dn.where(~interference['coal'], np.nan)
            if interference['gas'].any():
                vsh_dn = vsh_dn.where(~interference['gas'], np.nan)
        vsh_methods['V2_DN'] = vsh_dn
        
        # V3: 声波法（压实程度高的老地层适用）
        vsh_dt = None
        dt_col = None
        for name in ['DT', 'DTCO', 'AC', 'SONIC']:
            if name in data.columns:
                dt_col = name
                break
        if dt_col:
            dt_data = data[dt_col].dropna()
            dt_valid = dt_data[(dt_data > 30) & (dt_data < 500)]
            if len(dt_valid) > 0:
                # 压实程度检查：声波法只适用于压实程度高的老地层
                dt_median = dt_valid.median()
                # 如果DT中位数>90μs/ft，说明地层较疏松，声波法不适用
                is_compacted = dt_median < 90
                if not is_compacted:
                    logger.info(f"  DT中位数={dt_median:.1f}μs/ft，地层疏松，声波法仅作参考")
                dt_min = dt_valid.quantile(0.1)  # 砂岩声波时差（低值）
                dt_max = dt_valid.quantile(0.9)  # 泥岩声波时差（高值）
                if dt_max > dt_min:
                    vsh_dt = (data[dt_col] - dt_min) / (dt_max - dt_min)
                    vsh_dt = vsh_dt.clip(0, 1)
                    # 煤层：声波法结果不可信
                    if interference['coal'].any():
                        vsh_dt = vsh_dt.where(~interference['coal'], np.nan)
        vsh_methods['V3_DT'] = vsh_dt
        
        # V4: 电阻率法（泥岩电阻率上限法）
        # 公式: Vsh ≤ [ (Rsh/Rt) · (Rmax-Rt)/(Rmax-Rsh) ]^1/b
        # Rsh=泥岩电阻率, Rmax=纯砂岩最大电阻率, b=经验指数(通常1.0~2.0)
        # 只能算泥质含量上限，适合低孔隙度致密地层辅助校验
        vsh_rt = None
        rt_col = None
        for name in ['RT', 'LLD', 'ILD', 'AT90', 'AT60', 'M2RX', 'RDEEP']:
            if name in data.columns:
                rt_col = name
                break
        if rt_col:
            rt_data = data[rt_col].dropna()
            rt_valid = rt_data[(rt_data > 0.1) & (rt_data < 10000)]
            if len(rt_valid) > 0:
                # 泥岩电阻率：取低值段的P10作为泥岩电阻率
                rt_shale = rt_valid.quantile(0.1)     # 泥岩电阻率低值
                rt_sand = rt_valid.quantile(0.9)      # 砂岩电阻率高值
                b_exp = 1.0                           # 经验指数，默认1.0
                if rt_sand > rt_shale:
                    rt_clip = data[rt_col].clip(0.1, 10000)
                    # Vsh = [ (Rsh/Rt) · (Rmax-Rt)/(Rmax-Rsh) ]^1/b
                    ratio = (rt_shale / rt_clip) * (rt_sand - rt_clip) / (rt_sand - rt_shale)
                    vsh_rt = ratio ** (1.0 / b_exp)
                    vsh_rt = vsh_rt.clip(0, 1)
                    # 气层：电阻率法可能偏低（气层电阻率高）
                    if interference['gas'].any():
                        vsh_rt = vsh_rt.where(~interference['gas'], np.nan)
        vsh_methods['V4_RT'] = vsh_rt
        
        # V5: 中子法（单独）
        vsh_nphi = None
        if nphi_col:
            nphi_data = data[nphi_col].dropna()
            nphi_valid = nphi_data[(nphi_data > -0.15) & (nphi_data < 1.5)]
            if len(nphi_valid) > 0:
                nphi_vals = nphi_valid / 100.0 if nphi_valid.max() > 1 else nphi_valid
                nphi_clean_sand = nphi_vals.quantile(0.1)  # 砂岩中子低值
                nphi_shale = nphi_vals.quantile(0.9)       # 泥岩中子高值
                if nphi_shale > nphi_clean_sand:
                    vsh_nphi = (nphi_vals - nphi_clean_sand) / (nphi_shale - nphi_clean_sand)
                    vsh_nphi = vsh_nphi.clip(0, 1)
                    if interference['coal'].any():
                        vsh_nphi = vsh_nphi.where(~interference['coal'], np.nan)
                    if interference['gas'].any():
                        vsh_nphi = vsh_nphi.where(~interference['gas'], np.nan)
        vsh_methods['V5_NPHI'] = vsh_nphi
        
        # V6: 密度法（单独）
        vsh_den = None
        if rho_col:
            den_data = data[rho_col].dropna()
            den_valid = den_data[(den_data > 0) & (den_data < 5)]
            if len(den_valid) > 0:
                den_clean_sand = den_valid.quantile(0.9)  # 砂岩密度高值
                den_shale = den_valid.quantile(0.1)       # 泥岩密度低值
                if den_clean_sand > den_shale:
                    vsh_den = (den_clean_sand - data[rho_col]) / (den_clean_sand - den_shale)
                    vsh_den = vsh_den.clip(0, 1)
                    # 煤层/气层：密度法结果不可信
                    if interference['coal'].any():
                        vsh_den = vsh_den.where(~interference['coal'], np.nan)
                    if interference['gas'].any():
                        vsh_den = vsh_den.where(~interference['gas'], np.nan)
        vsh_methods['V6_DEN'] = vsh_den
        
        # V7: SP法（自然电位）
        vsh_sp = None
        sp_col = None
        for name in ['SP', 'SP_CORR', 'SPONTANEOUS', 'SP_POTENTIAL', 'SPL', 'SPDH', 'SPONT']:
            if name in data.columns:
                sp_col = name
                break
        if sp_col:
            sp_data = data[sp_col].dropna()
            # SP允许负值，但过滤极端异常值
            sp_valid = sp_data[(sp_data > -500) & (sp_data < 500)]
            if len(sp_valid) > 0:
                # SP在砂岩段负偏（左偏），泥岩段回到基线（右偏/高值）
                # 计算SP基线：取高值段的P90作为泥岩基线
                sp_baseline = sp_valid.quantile(0.9)   # 泥岩SP基线（高值）
                sp_clean = sp_valid.quantile(0.1)      # 纯砂岩SP（低值，最大负偏）
                if sp_baseline > sp_clean:
                    # SP越小(越负) → 越纯的砂岩 → VSH越低
                    # SP越大(越正/接近基线) → 泥质越多 → VSH越高
                    vsh_sp = (sp_baseline - data[sp_col]) / (sp_baseline - sp_clean)
                    vsh_sp = vsh_sp.clip(0, 1)
                    logger.info(f"  SP法计算VSH：基线={sp_baseline:.1f}, 纯砂岩SP={sp_clean:.1f}")
        vsh_methods['V7_SP'] = vsh_sp
        
        # V8: 自然伽马能谱法（最准确的放射性方法）
        # 使用KTH(无铀伽马)或GR_NOU(Th+K)计算泥质含量，完全排除铀富集干扰
        # 是复杂岩性剖面（火山碎屑岩、长石砂岩、煤系地层）最准确的放射性方法
        # 注意：SGR是总伽玛（含铀），不应作为无铀伽马使用
        vsh_kth = None
        kth_col = None
        for name in ['GR_NOU', 'KTH', 'CGR']:
            if name in data.columns:
                kth_col = name
                break
        if kth_col is None:
            # 如果没有KTH列，尝试用GR和U计算：KTH ≈ GR - 4*U
            if 'GR' in data.columns and 'U' in data.columns:
                u_qc = data['U'].where((data['U'] >= 0) & (data['U'] < 100), np.nan)
                gr_qc = data['GR'].where((data['GR'] > 0) & (data['GR'] < 500), np.nan)
                kth_estimated = gr_qc - 4.0 * u_qc
                kth_estimated = kth_estimated.clip(0, 500)
                data['KTH_EST'] = kth_estimated
                kth_col = 'KTH_EST'
                logger.info("  能谱法：无KTH列，用GR-4*U估计KTH")
        if kth_col:
            kth_data = data[kth_col].dropna()
            kth_valid = kth_data[(kth_data > 0) & (kth_data < 500)]
            if len(kth_valid) > 0:
                kth_min = kth_valid.quantile(0.1)  # 纯砂岩KTH
                kth_max = kth_valid.quantile(0.9)  # 纯泥岩KTH
                if kth_max > kth_min:
                    # 先用线性ΔGR，再用Larionov非线性公式
                    dkth = (data[kth_col] - kth_min) / (kth_max - kth_min)
                    dkth_clip = dkth.clip(0, 1)
                    vsh_kth = (2.0**(c_value * dkth_clip) - 1.0) / (2.0**c_value - 1.0)
                    vsh_kth = vsh_kth.clip(0, 1)
                    logger.info(f"  能谱法(KTH) Larionov C={c_value}：KTH_min={kth_min:.1f}, KTH_max={kth_max:.1f}")
        vsh_methods['V8_KTH'] = vsh_kth
        
        # ========== Reindex all methods to full data index ==========
        # 确保所有方法使用相同的索引，避免因过滤子集导致的索引不匹配
        for name in list(vsh_methods.keys()):
            if vsh_methods[name] is not None:
                vsh_methods[name] = vsh_methods[name].reindex(data.index)
        
        # ========== 3. 多方法共识融合 ==========
        # 统计每个深度点有多少种方法有效
        method_count = pd.DataFrame({k: v.notna() for k, v in vsh_methods.items() if v is not None}).sum(axis=1)
        
        # 逐点判断
        vsh_result = pd.Series(np.nan, index=data.index)
        vsh_confidence = pd.Series(0, index=data.index)
        
        for idx in data.index:
            # 收集该点所有有效VSH值
            vals = []
            val_names = []
            for name, vsh in vsh_methods.items():
                if vsh is not None and pd.notna(vsh.loc[idx]):
                    vals.append(vsh.loc[idx])
                    val_names.append(name)
            
            n_valid = len(vals)
            if n_valid == 0:
                continue
            
            # 检查特殊干扰
            flags = []
            for intr_type in ['coal', 'gas', 'uranium', 'feldspar']:
                if interference[intr_type].loc[idx]:
                    flags.append(intr_type)
            
            if n_valid == 1:
                # 只有一种方法可用，直接使用
                vsh_result.loc[idx] = vals[0]
                vsh_confidence.loc[idx] = 1
            elif n_valid == 2:
                # 两种方法：取平均（如果差异<0.2）
                if abs(vals[0] - vals[1]) < 0.2:
                    vsh_result.loc[idx] = np.mean(vals)
                    vsh_confidence.loc[idx] = 2
                else:
                    # 有干扰时取较小值（保守估计）
                    vsh_result.loc[idx] = min(vals)
                    vsh_confidence.loc[idx] = 1
            else:
                # 3种及以上方法：共识算法
                vals_arr = np.array(vals)
                median_val = np.median(vals_arr)
                mad = np.median(np.abs(vals_arr - median_val))  # 中位数绝对偏差
                
                if mad < 0.15:
                    # 方法一致 → 取中位数
                    vsh_result.loc[idx] = median_val
                    vsh_confidence.loc[idx] = n_valid
                elif mad < 0.25:
                    # 轻度分歧 → 排除离群值后取中位数
                    # 离群值：偏离中位数超过0.2
                    valid_mask = np.abs(vals_arr - median_val) <= 0.2
                    if valid_mask.sum() >= 2:
                        vsh_result.loc[idx] = np.median(vals_arr[valid_mask])
                        vsh_confidence.loc[idx] = valid_mask.sum()
                    else:
                        vsh_result.loc[idx] = median_val
                        vsh_confidence.loc[idx] = 2
                else:
                    # 严重分歧 → 有干扰
                    if flags:
                        # 已知干扰 → 排除受干扰的方法
                        reliable_vals = []
                        for j, name in enumerate(val_names):
                            is_affected = False
                            for intr_type in flags:
                                if intr_type == 'coal' and name in ['V2_DN', 'V5_NPHI', 'V6_DEN', 'V7_SP']:
                                    is_affected = True
                                elif intr_type == 'gas' and name in ['V2_DN', 'V4_RT', 'V5_NPHI', 'V6_DEN']:
                                    is_affected = True
                                elif intr_type == 'uranium' and name == 'V1_GR':
                                    # V8_KTH是能谱法，不受铀干扰，不排除
                                    is_affected = True
                            if not is_affected:
                                reliable_vals.append(vals[j])
                        
                        if len(reliable_vals) >= 2:
                            vsh_result.loc[idx] = np.median(reliable_vals)
                            vsh_confidence.loc[idx] = len(reliable_vals)
                        elif len(reliable_vals) == 1:
                            vsh_result.loc[idx] = reliable_vals[0]
                            vsh_confidence.loc[idx] = 1
                        else:
                            # 所有方法都受影响 → 取中位数
                            vsh_result.loc[idx] = median_val
                            vsh_confidence.loc[idx] = 1
                    else:
                        # 未知干扰 → 取中位数，但降低可信度
                        vsh_result.loc[idx] = median_val
                        vsh_confidence.loc[idx] = 2
        
        # 记录统计信息
        valid_count = vsh_result.notna().sum()
        logger.info(f"  高级VSH计算完成，有效点: {valid_count}/{len(data)}")
        logger.info(f"  VSH范围: {vsh_result.min():.4f}-{vsh_result.max():.4f}, 均值: {vsh_result.mean():.4f}")
        
        # 可信度统计
        for conf_level in [1, 2, 3, 4, 5, 6, 7, 8]:
            n_conf = (vsh_confidence >= conf_level).sum()
            if n_conf > 0:
                logger.info(f"  可信度≥{conf_level}: {n_conf}点")
        
        data['VSH'] = vsh_result.clip(0, 1)
        data['VSH_CONFIDENCE'] = vsh_confidence
        data['VSH_METHOD_COUNT'] = method_count
        
        # 输出干扰检测统计
        for intr_type in ['coal', 'gas', 'uranium', 'feldspar']:
            n_intr = interference[intr_type].sum()
            if n_intr > 0:
                logger.info(f"  检测到{intr_type}干扰: {n_intr}点")
        
        return data
    
    def get_dynamic_minerals(row, den_median, rt_median):
        """
        根据单点测井响应，动态选择该点应该参与最优化的矿物组合
        
        参数:
            row: 单行测井数据
            den_median: 全井密度中位数
            rt_median: 全井电阻率中位数
            
        返回:
            矿物列表
        """
        gr = row.get('GR', 80)
        pe = row.get('PE', row.get('PEF', 2.5))
        den = row.get('DEN', row.get('RHOB', den_median))
        rt = row.get('RT', row.get('LLD', row.get('LLS', rt_median)))
        phi = row.get('PHI', row.get('PHIE', 0.15))
        
        carbonate_likelihood = 0
        # 碳酸盐岩特征：GR低、PE高、密度高、电阻率高、孔隙度低
        if gr < 70: carbonate_likelihood += 0.25
        if gr < 50: carbonate_likelihood += 0.15
        # PE指标需与密度一致性校验：PE仅当密度也支持碳酸盐岩时才有效
        # 密度<2.65时PE>3是不一致信号，PE不可信
        if den > 2.60:
            # 密度支持碳酸盐岩，PE可以正常使用
            if pe > 2.8: carbonate_likelihood += 0.25
            if pe > 3.5: carbonate_likelihood += 0.15
        if den > 2.60: carbonate_likelihood += 0.25
        if den > 2.68: carbonate_likelihood += 0.15
        if rt > rt_median * 1.2: carbonate_likelihood += 0.2
        if rt > rt_median * 2: carbonate_likelihood += 0.1
        if phi < 0.15: carbonate_likelihood += 0.1
        
        sand_shale_likelihood = 0
        # 砂泥岩特征：GR高、PE低、密度中等、电阻率低、孔隙度中等
        if gr > 60: sand_shale_likelihood += 0.25
        if gr > 80: sand_shale_likelihood += 0.15
        # PE低值支持砂泥岩，但仅当密度也低时才可信
        if pe < 2.6 and den < 2.65: sand_shale_likelihood += 0.25
        if pe < 2.0 and den < 2.60: sand_shale_likelihood += 0.15
        if den >= 2.45 and den <= 2.65: sand_shale_likelihood += 0.25
        if den < 2.60: sand_shale_likelihood += 0.15
        if rt < rt_median * 1.5: sand_shale_likelihood += 0.2
        if rt < rt_median: sand_shale_likelihood += 0.1
        if phi >= 0.1 and phi <= 0.3: sand_shale_likelihood += 0.1
        
        if carbonate_likelihood > 0.5:
            return ['Quartz', 'Calcite', 'Dolomite', 'Anhydrite', 'Halite', 'Clay']
        elif sand_shale_likelihood > 0.5:
            return ['Quartz', 'Halite', 'Clay']  # 含盐岩以防蒸发岩序列井
        else:
            return ['Quartz', 'Calcite', 'Halite', 'Clay']
    
    def optimize_minerals(self, data, profile_type='mixed'):
        """使用最优化方法计算矿物含量和Porosity（全集矿物 + Lasso正则化稀疏约束）"""
        try:
            try:
                from scipy.optimize import minimize, Bounds, LinearConstraint
            except ImportError:
                logger.warning("scipy模块未安装，使用简化方法计算")
                vsh_method = self.config.get('vsh_method', 3)
                data = self.calculate_vsh(data, vsh_method)
                data['PHI'] = 0.2
                for mineral in self.minerals:
                    data[f'V{mineral}'] = 0.0
                data['VClay'] = data['VSH']
                data['VQuartz'] = 1 - data['VSH'] - data['PHI']
                return data
            
            # 固定使用全集矿物：石英、方解石、白云石、硬石膏、盐岩、粘土
            all_minerals = ['Quartz', 'Calcite', 'Dolomite', 'Anhydrite', 'Halite', 'Clay']
            n_min = len(all_minerals)
            logger.info(f"使用全集矿物进行优化: {all_minerals}, 剖面类型: {profile_type}")
            
            # ========== 读取全局PE质量（由run_mineral_analysis在井级别检测后存入）==========
            pe_quality = data.attrs.get('pe_quality', {})
            pe_unreliable = pe_quality.get('trend_only', False) or pe_quality.get('bad', False)
            if pe_unreliable:
                logger.warning(f"[optimize_minerals] PE曲线不可信: {pe_quality.get('reason', 'unknown')}，"
                              f"将跳过所有PE相关约束和PE段分类特征")
            
            # ========== 不再设置全局硬约束 ==========
            # 硬约束会导致矫枉过正：一旦剖面类型判断错误，优化结果完全错误
            # 改用软惩罚：profile_type只影响目标函数中的惩罚系数，不限制可行域
            
            # 构建响应矩阵
            A_min = np.array([self.params[m] for m in all_minerals])
            A_fluid = np.array([self.params['Water']])
            
            # 动态计算本井参考阈值（用分位数代替固定值）
            density_col = None
            for name in ['RHOB', 'DEN']:
                if name in data.columns:
                    density_col = name
                    break
            
            den_median = 2.65
            if density_col:
                valid_density = data[density_col].values[data[density_col].values > 0]
                if len(valid_density) > 0:
                    den_median = np.median(valid_density)
            
            # 定义曲线名称映射，支持模糊识别
            curve_mapping = {
                'DEN': ['DEN', 'RHOB', 'DRHO'],
                'CNL': ['CNL', 'NPHI', 'NPOR'],
                'AC': ['AC', 'DT', 'DTCO'],
                'PE': ['PE', 'PEF'],
                'GR': ['GR'],
            }
            
            mapped_curves = {}
            for curve_type, possible_names in curve_mapping.items():
                for name in possible_names:
                    if name in data.columns:
                        mapped_curves[curve_type] = name
                        break
            
            required_curves = ['DEN', 'CNL', 'AC']
            available_curves = [curve for curve in required_curves if curve in mapped_curves]
            
            if len(available_curves) < 2:
                logger.warning("曲线数量不足（需要至少DEN、CNL、AC中的2条），无法进行多矿物优化")
                vsh_method = self.config.get('vsh_method', 3)
                data = self.calculate_vsh(data, vsh_method)
                data['PHI'] = 0.2
                for mineral in self.minerals:
                    data[f'V{mineral}'] = 0.0
                data['VClay'] = data['VSH']
                data['VQuartz'] = 1 - data['VSH'] - data['PHI']
                return data
            
            # 获取GR基线（从数据中获取，如果不存在则使用默认值）
            gr_baseline = data.get('GR_REL', 1.0).mean() * data.get('GR', 80).mean()
            if gr_baseline < 30:
                gr_baseline = 80.0
            
            # 准备数据（曲线顺序：DEN, CNL, AC, PE, GR）
            measured_data = []
            pe_weights = []  # PE权重数组，质量不佳时降低权重
            
            for _, row in data.iterrows():
                sample = []
                # DEN
                if 'DEN' in mapped_curves:
                    den_val = row[mapped_curves['DEN']]
                    sample.append(den_val if not np.isnan(den_val) else den_median)
                else:
                    sample.append(den_median)
                # CNL（转换为小数）
                if 'CNL' in mapped_curves:
                    cnl_val = row[mapped_curves['CNL']]
                    if not np.isnan(cnl_val):
                        sample.append(cnl_val / 100.0 if cnl_val > 1 else cnl_val)
                    else:
                        sample.append(0)
                else:
                    sample.append(0)
                # AC
                if 'AC' in mapped_curves:
                    ac_val = row[mapped_curves['AC']]
                    sample.append(ac_val if not np.isnan(ac_val) else 55.5)
                else:
                    sample.append(55.5)
                # PE（质量检查，质量不佳时不使用）
                pe_val = row.get(mapped_curves.get('PE'), 2.0)
                if np.isnan(pe_val):
                    pe_val = 1.81
                
                # PE质量检查：当密度低、电阻率低、泥质含量有明显砂泥岩变化时，PE不应该大于3
                # 质量不佳时直接使用石英的PE值，不参与拟合
                # 注：井级别PE归一化已在run_mineral_analysis中完成，此处是逐点质量校验
                den = sample[0] if not np.isnan(sample[0]) else 2.65
                rt = row.get('RT', row.get('LLD', 50))
                
                # 使用泥质含量（取伽玛计算和密度中子交汇的较低值）
                vsh = row.get('VSH', 0)
                if vsh == 0 or np.isnan(vsh):
                    gr = row.get('GR', 80)
                    vsh = gr / gr_baseline
                
                # ========== PE质量检查（多指标交叉验证）==========
                # 核心原则：密度<2.65的砂泥岩剖面，PE应<3.0
                # PE>3.0且密度<2.65 → PE与密度不一致，PE质量存疑
                # 真灰岩剖面：PE>3.0 + 密度>2.65 + GR低值 + RT高值 → PE可信
                pe_valid = True  # PE是否有效
                
                # 统一规则：密度<2.65的砂泥岩剖面，PE>3就是矛盾
                if den < 2.65 and pe_val > 3.0:
                    # PE与密度不一致，需进一步判断是PE质量问题还是泥质碳酸盐岩
                    gr = row.get('GR', 80)
                    # 真灰岩即使密度受孔隙影响稍低，GR也应该低、RT应该高
                    if gr > 80:
                        # 高GR不可能对应灰岩，PE偏高属于仪器异常
                        pe_valid = False
                        pe_val = 3.45  # 使用粘土PE值
                    elif rt < 20:
                        # 低RT不可能对应灰岩（致密灰岩RT极高，含油气灰岩RT也较高）
                        pe_valid = False
                        pe_val = 2.0  # 使用中间值
                    elif den < 2.45 and pe_val > 5.0:
                        # 密度极低(<2.45)时PE>5.0明显矛盾，PE严重异常
                        pe_valid = False
                        pe_val = 1.81  # 使用石英PE值
                    elif den < 2.55:
                        # 密度<2.55属于典型砂泥岩范围，PE>3.0矛盾
                        pe_valid = False
                        pe_val = 2.0
                    # else: den在2.55-2.65之间且GR<80且RT>=20，可能是泥质碳酸盐岩，PE保持有效
                
                # 补充：纯砂岩特征（密度低+电阻率低+泥质含量低），PE不应>3.0
                if pe_valid and den < 2.60 and rt < 80 and vsh < 0.4:
                    if pe_val > 3.0:
                        pe_valid = False
                        pe_val = 1.81  # 使用石英的PE值
                
                # 补充：明显泥岩特征（泥质含量>0.6），PE不应>3.0
                if pe_valid and vsh > 0.6 and den < 2.65 and rt < 100:
                    if pe_val > 3.0:
                        pe_valid = False
                        pe_val = 3.45  # 使用粘土的PE值
                
                sample.append(pe_val)
                pe_weights.append(1.0 if pe_valid else 0.0)  # 无效时权重为0，不参与拟合
                
                # GR
                if 'GR' in mapped_curves:
                    gr_val = row[mapped_curves['GR']]
                    sample.append(gr_val if not np.isnan(gr_val) else 80)
                else:
                    sample.append(80)
                measured_data.append(sample)
            
            measured_data = np.array(measured_data)
            pe_weights = np.array(pe_weights)
            
            # 计算各曲线的方差用于归一化（平衡不同量纲）
            # 使用数据驱动的方差估计，更加准确
            measured_array = np.array(measured_data)
            curve_variances = np.var(measured_array, axis=0)
            curve_variances = np.where(curve_variances > 0, curve_variances, 
                                      np.array([0.05, 0.01, 100.0, 1.0, 400.0]))
            
            # L1正则化系数（控制稀疏程度，0.01~0.1），从配置文件读取
            base_lambda_reg = self.config.get('mineral_model', {}).get('lambda_reg', 0.05)
            
            # 当PE曲线不可用或不可信时，石英和方解石很难区分，增加正则化系数
            # pe_unreliable 来自井级别 PE 质量检测（与上方 WARNING 一致）
            has_pe = 'PE' in mapped_curves and not pe_unreliable
            lambda_reg = base_lambda_reg * (3.0 if not has_pe else 1.0)
            
            # 矿物类型惩罚系数（中性，仅硬石膏和盐岩略高）
            # 剖面类型通过profile_penalty_factor调整，M-N先验通过mn_weights调整
            base_penalties = np.array([1.0, 1.0, 1.0, 1.5, 2.0, 1.0])  # Quartz, Calcite, Dolomite, Anhydrite, Halite, Clay
            
            logger.info(f"L1正则化系数: {lambda_reg}, PE曲线可用: {has_pe}" + 
                       (f" (质量检查不可信，跳过PE约束)" if not has_pe and 'PE' in mapped_curves else ""))
            
            # ========== M-N交会图先验引导的L1正则化 ==========
            # 根据M-N交会图位置计算各矿物的先验权重
            # 距离越近，先验权重越高，L1惩罚越低
            
            def compute_mn_prior_weights(den, cnl):
                """根据M-N交会图位置计算各矿物的先验权重"""
                if np.isnan(den) or np.isnan(cnl):
                    return np.ones(5)  # 无先验信息，使用均匀权重
                
                # 标准矿物骨架点（DEN, CNL）
                sandstone_skeleton = np.array([self.params['Quartz'][0], self.params['Quartz'][1]])
                limestone_skeleton = np.array([self.params['Calcite'][0], self.params['Calcite'][1]])
                dolomite_skeleton = np.array([self.params['Dolomite'][0], self.params['Dolomite'][1]])
                clay_skeleton = np.array([self.params['Clay'][0], self.params['Clay'][1]])
                water_point = np.array([self.params['Water'][0], self.params['Water'][1]])
                
                point = np.array([den, cnl])
                
                # 计算到各矿物线的距离
                def dist_to_line(pt, start, end):
                    line_vec = end - start
                    pt_vec = pt - start
                    line_len_sq = np.dot(line_vec, line_vec)
                    if line_len_sq < 1e-10:
                        return np.linalg.norm(pt_vec)
                    t = max(0, min(1, np.dot(pt_vec, line_vec) / line_len_sq))
                    projection = start + t * line_vec
                    return np.linalg.norm(pt - projection)
                
                dist_sand = dist_to_line(point, sandstone_skeleton, water_point)
                dist_lime = dist_to_line(point, limestone_skeleton, water_point)
                dist_dolo = dist_to_line(point, dolomite_skeleton, water_point)
                dist_clay = dist_to_line(point, clay_skeleton, water_point)
                
                # 距离越小，先验权重越高（范围0.1~1.0）
                max_dist = max(dist_sand, dist_lime, dist_dolo, dist_clay, 1e-10)
                weights = np.array([
                    1.0 - dist_sand / max_dist * 0.9,  # Quartz
                    1.0 - dist_lime / max_dist * 0.9,  # Calcite
                    1.0 - dist_dolo / max_dist * 0.9,  # Dolomite
                    0.5,                               # Anhydrite（无先验信息）
                    1.0 - dist_clay / max_dist * 0.9   # Clay
                ])
                
                return weights
            
            def objective_with_lasso(x, measured, A_min, A_fluid, pe_weight=1.0, mn_weights=None, profile_penalty=None):
                """目标函数：归一化最小二乘 + L1正则化稀疏惩罚 + 矿物类型惩罚 + M-N先验引导 + 剖面类型软惩罚"""
                V_min = x[:-1]
                phi = x[-1]
                
                pred_response = V_min @ A_min + phi * A_fluid
                
                # PE质量不佳时完全跳过PE曲线拟合
                if pe_weight <= 0.01:
                    # 不使用PE，只拟合DEN, CNL, AC, GR（索引0,1,2,4）
                    valid_indices = [0, 1, 2, 4]
                    fit_error = np.sum(((measured[valid_indices] - pred_response[valid_indices]) ** 2) 
                                      / curve_variances[valid_indices])
                else:
                    # 正常拟合所有曲线
                    fit_error = np.sum(((measured - pred_response) ** 2) / curve_variances)
                
                # L1正则化（稀疏惩罚），促使多数矿物含量趋于0
                # 使用M-N先验权重调整惩罚系数：先验权重越高，惩罚越低
                if mn_weights is None:
                    mn_weights = np.ones(5)
                
                # 使用剖面类型惩罚因子：剖面类型仅影响惩罚权重，不限制可行域
                if profile_penalty is None:
                    profile_penalty = np.ones(n_min)
                
                # 综合惩罚系数 = 基础惩罚 * (1 - 先验权重 * 0.8) * 剖面类型惩罚因子
                # 先验权重高的矿物，惩罚系数低，更容易被选中
                # 剖面类型惩罚因子：砂泥岩剖面增加碳酸盐矿物惩罚，碳酸盐岩剖面增加石英惩罚
                combined_penalties = base_penalties * (1.0 - mn_weights * 0.8) * profile_penalty
                
                l1_penalty = lambda_reg * np.sum(combined_penalties * np.abs(V_min))
                
                # 当PE不可用或质量不佳时，添加额外的碳酸盐惩罚（方解石+白云石）
                extra_reg = 0.0
                if not has_pe or pe_weight < 0.5:
                    v_carbonate = V_min[1] + V_min[2]  # Calcite + Dolomite
                    extra_reg = 0.03 * v_carbonate * (1.0 - pe_weight + 0.1)
                
                return fit_error + l1_penalty + extra_reg
            
            # ========== 优先使用密度孔隙度（根据2012质量评价） ==========
            # 如果密度曲线质量不合格，使用其他方法计算初始孔隙度
            use_density = getattr(self, 'use_density_porosity', True)
            
            matrix_densities = {
                '砂岩': 2.65, 'sandstone': 2.65,
                '灰岩': 2.71, 'limestone': 2.71,
                '白云岩': 2.87, 'dolomite': 2.87,
                '碳酸盐岩': 2.71,
                '泥岩': 2.55, 'shale': 2.55,
                '硬石膏': 2.98, 'anhydrite': 2.98
            }
            fluid_density = 1.0
            
            # 初始化所有矿物含量为0
            for mineral in self.minerals:
                data[f'V{mineral}'] = 0.0
            
            # 计算初始孔隙度
            if 'RHOB' in data.columns and use_density:
                def calculate_phi(row):
                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                    rhob = row.get('RHOB', 2.65)
                    if lithology in matrix_densities:
                        matrix_density = matrix_densities[lithology]
                    else:
                        if rhob < 2.68:
                            matrix_density = 2.65
                        elif rhob < 2.80:
                            matrix_density = 2.71
                        else:
                            matrix_density = 2.87
                    phi = (matrix_density - rhob) / (matrix_density - fluid_density)
                    return max(0, min(1, phi))
                
                data['PHI'] = data.apply(calculate_phi, axis=1)
                # 限制孔隙度不超过0.4（40%），超过的可能是气层效应或井眼扩大导致的异常
                data['PHI'] = data['PHI'].clip(0, 0.4)
                logger.info(f"优先使用密度孔隙度（变骨架），PHI限制在0-0.4")
            elif any(nmr_col in data.columns for nmr_col in ['MPHE', 'PHIE', 'MRP']):
                for nmr_col in ['MPHE', 'PHIE', 'MRP']:
                    if nmr_col in data.columns:
                        data['PHI'] = data[nmr_col].clip(0, 1)
                        logger.info(f"使用核磁孔隙度 {nmr_col}")
                        break
            else:
                data['PHI'] = 0.2
            
            # 约束：sum(V_min)+phi=1
            A_eq = np.ones((1, n_min + 1))
            lin_constraint = LinearConstraint(A_eq, lb=1, ub=1)
            
            # ========== M-N交会图先验约束 ==========
            # 在密度-中子交会图上计算到标准矿物线的距离
            # 砂岩线：连接石英骨架(DEN=2.65, CNL=-0.02)和水(DEN=1.0, CNL=1.0)
            # 灰岩线：连接方解石骨架(DEN=2.71, CNL=0.0)和水(DEN=1.0, CNL=1.0)
            # 白云岩线：连接白云石骨架(DEN=2.87, CNL=0.02)和水(DEN=1.0, CNL=1.0)
            
            # 标准矿物骨架点（DEN, CNL）
            sandstone_skeleton = np.array([self.params['Quartz'][0], self.params['Quartz'][1]])
            limestone_skeleton = np.array([self.params['Calcite'][0], self.params['Calcite'][1]])
            dolomite_skeleton = np.array([self.params['Dolomite'][0], self.params['Dolomite'][1]])
            water_point = np.array([self.params['Water'][0], self.params['Water'][1]])
            
            def distance_to_line(point, line_start, line_end):
                """计算点到线段的垂直距离"""
                line_vec = line_end - line_start
                point_vec = point - line_start
                line_len_sq = np.dot(line_vec, line_vec)
                if line_len_sq < 1e-10:
                    return np.linalg.norm(point_vec)
                t = max(0, min(1, np.dot(point_vec, line_vec) / line_len_sq))
                projection = line_start + t * line_vec
                return np.linalg.norm(point - projection)
            
            def get_mn_prior_guess(den, cnl):
                """根据M-N交会图位置生成初始猜测"""
                if np.isnan(den) or np.isnan(cnl):
                    return None
                
                point = np.array([den, cnl])
                
                # 计算到各矿物线的距离
                dist_sand = distance_to_line(point, sandstone_skeleton, water_point)
                dist_lime = distance_to_line(point, limestone_skeleton, water_point)
                dist_dolo = distance_to_line(point, dolomite_skeleton, water_point)
                
                # 归一化距离（距离越小权重越高）
                total_dist = dist_sand + dist_lime + dist_dolo + 1e-10
                weight_sand = (1 - dist_sand / total_dist) / 3 + 0.33
                weight_lime = (1 - dist_lime / total_dist) / 3 + 0.33
                weight_dolo = (1 - dist_dolo / total_dist) / 3 + 0.33
                
                # 根据距离生成偏向性初始点
                # 如果距离砂线最近，偏向石英
                # 矿物顺序：Quartz, Calcite, Dolomite, Anhydrite, Halite, Clay, phi
                if dist_sand < dist_lime and dist_sand < dist_dolo:
                    # 偏向砂泥岩
                    v_quartz = 0.5 + weight_sand * 0.3
                    v_clay = 0.2 + (1 - weight_sand) * 0.2
                    v_calcite = 0.05 + weight_lime * 0.05
                    v_dolomite = 0.05 + weight_dolo * 0.05
                    v_anhydrite = 0.02
                    v_halite = 0.01
                    phi = max(0.05, 1 - v_quartz - v_clay - v_calcite - v_dolomite - v_anhydrite - v_halite)
                    return np.array([v_quartz, v_calcite, v_dolomite, v_anhydrite, v_halite, v_clay, phi])
                elif dist_lime < dist_sand and dist_lime < dist_dolo:
                    # 偏向灰岩
                    v_calcite = 0.5 + weight_lime * 0.3
                    v_dolomite = 0.1 + weight_dolo * 0.1
                    v_quartz = 0.1 + weight_sand * 0.1
                    v_clay = 0.05
                    v_anhydrite = 0.02
                    v_halite = 0.01
                    phi = max(0.05, 1 - v_quartz - v_clay - v_calcite - v_dolomite - v_anhydrite - v_halite)
                    return np.array([v_quartz, v_calcite, v_dolomite, v_anhydrite, v_halite, v_clay, phi])
                elif dist_dolo < dist_sand and dist_dolo < dist_lime:
                    # 偏向白云岩
                    v_dolomite = 0.5 + weight_dolo * 0.3
                    v_calcite = 0.1 + weight_lime * 0.1
                    v_quartz = 0.1 + weight_sand * 0.1
                    v_clay = 0.05
                    v_anhydrite = 0.02
                    v_halite = 0.01
                    phi = max(0.05, 1 - v_quartz - v_clay - v_calcite - v_dolomite - v_anhydrite - v_halite)
                    return np.array([v_quartz, v_calcite, v_dolomite, v_anhydrite, v_halite, v_clay, phi])
                else:
                    return None
            
            # M-N交会图距离计算辅助函数（逐点岩性识别用）
            def dist_to_line_mn(pt, start, end):
                """计算点到线段的距离"""
                line_vec = end - start
                pt_vec = pt - start
                line_len_sq = np.dot(line_vec, line_vec)
                if line_len_sq < 1e-10:
                    return np.linalg.norm(pt_vec)
                t = max(0, min(1, np.dot(pt_vec, line_vec) / line_len_sq))
                projection = start + t * line_vec
                return np.linalg.norm(pt - projection)
            
            # ========== 岩性分段：基于滑动窗口+交汇图 ==========
            # 使用30-50点窗口，计算GR/PE/RT/DEN中位数，通过M-N交汇图分类
            # 分为：sand_shale（砂泥岩）、carbonate（碳酸盐岩）、mixed（混合）
            window_size = min(50, len(data) // 3)  # 窗口大小，至少保证3个段
            if window_size < 10:
                window_size = len(data)
            
            # 初始化分段结果
            segment_labels = ['mixed'] * len(data)
            
            if len(data) >= window_size * 2:
                logger.info(f"开始岩性分段（滑动窗口={window_size}点）...")
                # 构建滑动窗口特征矩阵
                features = []
                for i in range(0, len(data) - window_size + 1, window_size // 2):
                    win = data.iloc[i:i + window_size]
                    # 提取特征：GR中位数、(PE中位数——PE不可信时跳过)、RT中位数、DEN中位数
                    gr_med = win.get('GR', pd.Series([80])).median()
                    if not pe_unreliable:
                        pe_med = win.get('PE', win.get('PEF', pd.Series([2.5]))).median()
                    rt_med = win.get('RT', win.get('LLD', win.get('ILD', win.get('R90', pd.Series([50]))))).median()
                    den_med = win.get('DEN', win.get('RHOB', pd.Series([2.65]))).median()
                    cnl_med = win.get('CNL', win.get('NPHI', pd.Series([0.15]))).median()
                    if cnl_med > 1:
                        cnl_med = cnl_med / 100.0
                    if pe_unreliable:
                        features.append([gr_med, rt_med, den_med, cnl_med])
                    else:
                        features.append([gr_med, pe_med, rt_med, den_med, cnl_med])
                
                if len(features) >= 3:
                    # 使用K-means聚类（3类：砂泥岩、碳酸盐岩、混合）
                    from sklearn.cluster import KMeans
                    features = np.array(features)
                    # 归一化特征
                    feat_means = np.nanmean(features, axis=0)
                    feat_stds = np.nanstd(features, axis=0) + 1e-10
                    features_norm = (features - feat_means) / feat_stds
                    
                    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
                    cluster_labels = kmeans.fit_predict(features_norm)
                    
                    # 判断每个聚类代表的岩性类型
                    cluster_lithology = {}
                    for c in range(3):
                        mask = cluster_labels == c
                        if mask.sum() < 2:
                            cluster_lithology[c] = 'mixed'
                            continue
                        if pe_unreliable:
                            # PE不可信时，特征列: [GR, RT, DEN, CNL]
                            avg_gr = np.nanmean(features[mask, 0])
                            avg_rt = np.nanmean(features[mask, 1])
                            avg_den = np.nanmean(features[mask, 2])
                            avg_pe = np.nan  # 不使用PE
                        else:
                            # 正常情况: [GR, PE, RT, DEN, CNL]
                            avg_gr = np.nanmean(features[mask, 0])
                            avg_pe = np.nanmean(features[mask, 1])
                            avg_rt = np.nanmean(features[mask, 2])
                            avg_den = np.nanmean(features[mask, 3])
                        
                        # 碳酸盐岩特征：GR低、密度高、电阻率高（PE不可信时不参与评分）
                        score_carbonate = 0
                        if avg_gr < 50: score_carbonate += 1
                        if not pe_unreliable and avg_pe > 3.0: score_carbonate += 1
                        if avg_den > 2.65: score_carbonate += 1
                        if avg_rt > 80: score_carbonate += 1
                        
                        # 砂泥岩特征：GR中高、密度中低、电阻率中低
                        score_sand_shale = 0
                        if avg_gr > 60: score_sand_shale += 1
                        if not pe_unreliable and avg_pe < 2.8: score_sand_shale += 1
                        if avg_den < 2.65: score_sand_shale += 1
                        if avg_rt < 80: score_sand_shale += 1
                        
                        # PE不可信时降低阈值（少了一个评分项）
                        if pe_unreliable:
                            carb_threshold = 2  # 需要3项中至少2项
                            ss_threshold = 2    # 需要3项中至少2项
                        else:
                            carb_threshold = 3
                            ss_threshold = 3
                        
                        if score_carbonate >= carb_threshold:
                            cluster_lithology[c] = 'carbonate'
                        elif score_sand_shale >= ss_threshold:
                            cluster_lithology[c] = 'sand_shale'
                        else:
                            cluster_lithology[c] = 'mixed'
                    
                    # 将聚类结果映射回每个采样点
                    half_win = window_size // 2
                    for i in range(len(cluster_labels)):
                        start_idx = i * (window_size // 2)
                        end_idx = min(start_idx + window_size, len(data))
                        lith = cluster_lithology.get(cluster_labels[i], 'mixed')
                        for j in range(start_idx, min(end_idx, start_idx + window_size)):
                            if j < len(segment_labels):
                                segment_labels[j] = lith
                    
                    # 统计各段占比
                    ss_count = segment_labels.count('sand_shale')
                    cb_count = segment_labels.count('carbonate')
                    mx_count = segment_labels.count('mixed')
                    logger.info(f"岩性分段完成: 砂泥岩段={ss_count}点({100*ss_count/len(data):.0f}%), "
                               f"碳酸盐岩段={cb_count}点({100*cb_count/len(data):.0f}%), "
                               f"混合段={mx_count}点({100*mx_count/len(data):.0f}%)")
            
            # ========== 构建逐点硬约束边界（段类型驱动） ==========
            # 砂泥岩段：碳酸盐矿物上限（方解石≤5%、白云石≤5%、硬石膏≤1%、盐岩≤1%）
            # 碳酸盐岩段：石英上限≤10%
            # 混合段：无额外约束
            segment_upper_bounds = []
            for i in range(len(data)):
                row = data.iloc[i]
                lower, upper = self.apply_4param_geological_prison(row, gr_baseline, pe_unreliable)
                seg_type = segment_labels[i] if i < len(segment_labels) else 'mixed'
                
                if seg_type == 'sand_shale':
                    # 砂泥岩段：碳酸盐矿物硬上限，盐岩硬上限
                    upper[0] = min(upper[0], 1.0)    # Quartz: 无额外约束
                    upper[1] = min(upper[1], 0.05)   # Calcite: ≤5%
                    upper[2] = min(upper[2], 0.05)   # Dolomite: ≤5%
                    upper[3] = min(upper[3], 0.01)   # Anhydrite: ≤1%
                    upper[4] = min(upper[4], 0.01)   # Halite: ≤1%（砂泥岩段不可能是盐岩）
                    upper[5] = min(upper[5], 1.0)    # Clay: 无额外约束
                elif seg_type == 'carbonate':
                    # 碳酸盐岩段：石英硬上限10%，盐岩无约束（蒸发岩序列可能出现）
                    upper[0] = min(upper[0], 0.10)   # Quartz: ≤10%
                    upper[1] = min(upper[1], 1.0)    # Calcite: 无额外约束
                    upper[2] = min(upper[2], 1.0)    # Dolomite: 无额外约束
                    upper[3] = min(upper[3], 1.0)    # Anhydrite: 无额外约束
                    upper[4] = min(upper[4], 1.0)    # Halite: 无额外约束（蒸发盐岩序列）
                    upper[5] = min(upper[5], 1.0)    # Clay: 无额外约束
                # mixed段：不额外约束，使用默认地质约束
                
                segment_upper_bounds.append(upper)
            
            # 逐点优化
            fail_count = 0
            last_valid_result = None
            
            optimize_options = {
                'maxiter': 1000,
                'ftol': 1e-8,
                'disp': False
            }
            
            for i in range(len(data)):
                meas = measured_data[i]
                
                if np.any(np.isnan(meas)) or np.any(np.isinf(meas)):
                    if last_valid_result is not None:
                        for j, mineral in enumerate(all_minerals):
                            data.at[i, f'V{mineral}'] = last_valid_result[j]
                        data.at[i, 'PHI'] = last_valid_result[-1]
                    fail_count += 1
                    continue
                
                # 获取当前行数据
                row = data.iloc[i]
                
                # ========== M-N交会图逐点岩性识别 ==========
                den = meas[0] if not np.isnan(meas[0]) else 2.65
                rt = row.get('RT', row.get('LLD', row.get('R90', 50)))
                gr = row.get('GR', 80)
                pe = row.get('PE', row.get('PEF', np.nan))
                cnl_for_ident = row.get('NPHI', row.get('CNL', np.nan))
                if not np.isnan(cnl_for_ident) and cnl_for_ident > 1:
                    cnl_for_ident = cnl_for_ident / 100.0
                
                # 使用泥质含量判断
                vsh = row.get('VSH', 0)
                if vsh == 0 or np.isnan(vsh):
                    vsh = gr / gr_baseline
                
                # ========== M-N交会图逐点识别岩性类型 ==========
                # 根据密度-中子交会图位置，判断当前深度点最可能属于哪种岩性
                # 这是最可靠的逐点岩性判别方法
                mn_lithology = 'unknown'  # 默认
                
                if not np.isnan(cnl_for_ident) and not np.isnan(den):
                    # 计算到各矿物骨架线的距离
                    point = np.array([den, cnl_for_ident])
                    sandstone_skeleton = np.array([self.params['Quartz'][0], self.params['Quartz'][1]])
                    limestone_skeleton = np.array([self.params['Calcite'][0], self.params['Calcite'][1]])
                    dolomite_skeleton = np.array([self.params['Dolomite'][0], self.params['Dolomite'][1]])
                    clay_skeleton = np.array([self.params['Clay'][0], self.params['Clay'][1]])
                    water_point = np.array([self.params['Water'][0], self.params['Water'][1]])
                    
                    dist_sand = dist_to_line_mn(point, sandstone_skeleton, water_point)
                    dist_lime = dist_to_line_mn(point, limestone_skeleton, water_point)
                    dist_dolo = dist_to_line_mn(point, dolomite_skeleton, water_point)
                    dist_clay = dist_to_line_mn(point, clay_skeleton, water_point)
                    
                    # 找到距离最近的矿物线
                    min_dist = min(dist_sand, dist_lime, dist_dolo, dist_clay)
                    
                    if min_dist == dist_sand:
                        mn_lithology = 'sandstone'
                    elif min_dist == dist_lime:
                        mn_lithology = 'limestone'
                    elif min_dist == dist_dolo:
                        mn_lithology = 'dolomite'
                    else:
                        mn_lithology = 'shale'
                    
                    # 使用PE辅助区分灰岩和白云岩（PE可靠时）
                    if not pe_unreliable and not np.isnan(pe) and pe > 0:
                        current_pe_weight = pe_weights[i] if i < len(pe_weights) else 1.0
                        if current_pe_weight > 0.5:
                            if mn_lithology == 'dolomite' and pe > 4.0:
                                mn_lithology = 'limestone'  # PE高更可能是灰岩
                            elif mn_lithology == 'limestone' and pe < 3.0:
                                mn_lithology = 'dolomite'  # PE低更可能是白云岩

                # 结合物理约束修正：高密度不可能是泥岩
                if den > 2.60 and mn_lithology == 'shale':
                    # 泥岩密度一般不超过2.60，高密度更可能是碳酸盐岩
                    # PE不可信时仅用密度判断
                    if not pe_unreliable and not np.isnan(pe) and pe > 3.0:
                        mn_lithology = 'limestone'
                    elif den > 2.75:
                        mn_lithology = 'dolomite'
                    else:
                        mn_lithology = 'sandstone'  # 致密砂岩

                # 高密度+低GR不可能是泥岩
                if den > 2.60 and gr < 60 and mn_lithology == 'shale':
                    if not pe_unreliable and not np.isnan(pe) and pe > 3.0:
                        mn_lithology = 'limestone'
                    elif den > 2.75:
                        mn_lithology = 'dolomite'
                    else:
                        mn_lithology = 'sandstone'
                
                # 设置逐点预判标志
                is_sand_shale = mn_lithology in ['sandstone', 'shale']
                is_carbonate = mn_lithology in ['limestone', 'dolomite']
                
                # 获取当前点的段类型
                seg_type = segment_labels[i] if i < len(segment_labels) else 'mixed'
                
                # ========== PE+密度强制覆盖：碳酸盐岩物理特征不可否认 ==========
                # 当密度>2.68（超过砂泥岩范围）+ PE>3.5（强碳酸盐信号）时，
                # 即使分段判为sand_shale，也要覆盖为carbonate，允许碳酸盐矿物
                # 解决3-SPS-111D井6450-6500m段密度>2.7、电阻率~200误判为砂岩的问题
                # 注意：PE不可信时（如XIMENIA-5井PE~8-11），跳过所有pe_override
                pe_override = False
                if not pe_unreliable:
                    if (den > 2.68 and not np.isnan(pe) and pe > 3.5):
                        pe_override = True
                    elif (is_carbonate and not np.isnan(pe) and pe > 3.0):
                        # M-N交汇图判为碳酸盐岩 + PE>3.0确认
                        pe_override = True
                
                if pe_override and seg_type != 'carbonate':
                    seg_type = 'carbonate'
                    # 重新计算上界：碳酸盐岩段允许碳酸盐矿物
                    upper_corrected = segment_upper_bounds[i].copy()
                    upper_corrected[0] = min(upper_corrected[0], 0.10)  # Quartz ≤ 10%
                    upper_corrected[1] = 1.0  # Calcite 无限制
                    upper_corrected[2] = 1.0  # Dolomite 无限制
                    upper_corrected[3] = 1.0  # Anhydrite 无限制
                    upper_corrected[4] = 1.0  # Halite 无限制
                else:
                    upper_corrected = segment_upper_bounds[i] if pe_override else None
                
                # 使用预计算的分段边界
                upper = upper_corrected if pe_override else segment_upper_bounds[i]
                # 下界始终为0（由地质约束提供）
                lower = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # Quartz, Calcite, Dolomite, Anhydrite, Halite, Clay
                
                # 分段惩罚权重：使用硬约束后，惩罚权重可以降低
                profile_penalty_factor = np.ones(n_min)  # 默认为1.0
                
                if seg_type == 'sand_shale':
                    # 砂泥岩段：已经在边界中限制了碳酸盐矿物，惩罚权重可以减轻
                    profile_penalty_factor[1] = 1.5  # Calcite（轻惩罚，边界已限制）
                    profile_penalty_factor[2] = 1.5  # Dolomite
                    profile_penalty_factor[3] = 2.0  # Anhydrite
                    profile_penalty_factor[4] = 3.0  # Halite（砂泥岩段极重惩罚，防止误判）
                elif seg_type == 'carbonate':
                    # 碳酸盐岩段：已经在边界中限制了石英
                    profile_penalty_factor[0] = 1.5  # Quartz（轻惩罚，边界已限制）
                    profile_penalty_factor[4] = 2.0  # Halite（碳酸盐岩段重惩罚，仅在蒸发岩序列出现）
                
                # 将孔隙度也加入边界约束
                lower_bounds = lower + [0.0]
                upper_bounds = upper + [1.0]
                
                # 创建动态边界
                bounds = Bounds(lower_bounds, upper_bounds)
                
                # ========== 诊断日志：确认约束是否生效（只打印第一个深度点）==========
                if i == 0:
                    logger.info(f"[DEBUG] mn_lithology={mn_lithology}, profile_type={profile_type}")
                    logger.info(f"[DEBUG] upper_bounds={upper_bounds}")
                    logger.info(f"[DEBUG] lower_bounds={lower_bounds}")
                    logger.info(f"[DEBUG] is_sand_shale={is_sand_shale}, is_carbonate={is_carbonate}")
                
                # 多个初始点：根据预判结果调整
                initial_guesses = []
                
                if last_valid_result is not None:
                    initial_guesses.append(last_valid_result.copy())
                
                # ========== M-N交会图先验初始点 ==========
                # 根据密度-中子交会图位置生成偏向性初始点
                cnl_value = row.get('NPHI', row.get('CNL', np.nan))
                # 确保CNL在有效范围内
                if not np.isnan(cnl_value):
                    # 如果CNL是百分比，转换为小数
                    if cnl_value > 1:
                        cnl_value = cnl_value / 100.0
                    mn_prior = get_mn_prior_guess(den, cnl_value)
                    if mn_prior is not None:
                        initial_guesses.append(mn_prior)
                
                # 根据M-N交会图岩性识别结果添加针对性初始点
                if mn_lithology == 'sandstone':
                    # 砂岩点：优先使用石英初始点
                    x0_sand = np.array([0.6, 0.02, 0.02, 0.01, 0.01, 0.24, 0.1])  # 砂岩初始点
                    initial_guesses.append(x0_sand)
                    x0_shale = np.array([0.2, 0.02, 0.02, 0.01, 0.01, 0.59, 0.15])  # 泥岩初始点
                    initial_guesses.append(x0_shale)
                elif mn_lithology == 'shale':
                    # 泥岩点：优先使用粘土初始点
                    x0_shale = np.array([0.2, 0.02, 0.02, 0.01, 0.01, 0.59, 0.15])  # 泥岩初始点
                    initial_guesses.append(x0_shale)
                    x0_sand = np.array([0.6, 0.02, 0.02, 0.01, 0.01, 0.24, 0.1])  # 砂岩初始点
                    initial_guesses.append(x0_sand)
                elif mn_lithology == 'limestone':
                    # 灰岩点：优先使用方解石初始点
                    x0_limestone = np.array([0.05, 0.7, 0.1, 0.02, 0.01, 0.03, 0.09])  # 灰岩初始点
                    initial_guesses.append(x0_limestone)
                    x0_dolomite = np.array([0.05, 0.1, 0.7, 0.02, 0.01, 0.03, 0.09])  # 白云岩初始点
                    initial_guesses.append(x0_dolomite)
                elif mn_lithology == 'dolomite':
                    # 白云岩点：优先使用白云石初始点
                    x0_dolomite = np.array([0.05, 0.1, 0.7, 0.02, 0.01, 0.03, 0.09])  # 白云岩初始点
                    initial_guesses.append(x0_dolomite)
                    x0_limestone = np.array([0.05, 0.7, 0.1, 0.02, 0.01, 0.03, 0.09])  # 灰岩初始点
                    initial_guesses.append(x0_limestone)
                else:
                    # 未知岩性：添加所有初始点
                    x0_sand = np.array([0.6, 0.02, 0.02, 0.01, 0.01, 0.24, 0.1])
                    initial_guesses.append(x0_sand)
                    x0_limestone = np.array([0.05, 0.7, 0.1, 0.02, 0.01, 0.03, 0.09])
                    initial_guesses.append(x0_limestone)
                    x0_dolomite = np.array([0.05, 0.1, 0.7, 0.02, 0.01, 0.03, 0.09])
                    initial_guesses.append(x0_dolomite)
                
                # 均匀初始点
                x0_uniform = np.ones(n_min + 1) / (n_min + 1)
                initial_guesses.append(x0_uniform)
                
                # 石英偏向初始点（砂泥岩优先）
                x0_quartz = np.array([0.5, 0.05, 0.05, 0.05, 0.01, 0.14, 0.2])
                initial_guesses.append(x0_quartz)
                
                success = False
                best_result = None
                best_fun = float('inf')
                
                # 使用SLSQP优化方法（trust-constr不适合处理L1正则化的非光滑目标函数）
                methods = ['SLSQP']
                
                # 获取当前点的PE权重
                current_pe_weight = pe_weights[i] if i < len(pe_weights) else 1.0
                
                # 计算M-N交会图先验权重
                cnl_for_mn = row.get('NPHI', row.get('CNL', np.nan))
                if not np.isnan(cnl_for_mn) and cnl_for_mn > 1:
                    cnl_for_mn = cnl_for_mn / 100.0  # 转换为小数
                mn_weights = compute_mn_prior_weights(den, cnl_for_mn)
                
                # ========== 使用已有孔隙度修正初始点 ==========
                # 如果已有孔隙度（密度孔隙度或核磁孔隙度），将初始猜测中的孔隙度值替换
                existing_phi = row.get('PHI', None)
                if existing_phi is not None and not (isinstance(existing_phi, float) and existing_phi == 0.2):
                    init_phi = max(0.01, min(0.4, float(existing_phi)))
                    for j in range(len(initial_guesses)):
                        x0 = initial_guesses[j].copy()
                        x0[-1] = init_phi
                        x0[:-1] = x0[:-1] * (1 - init_phi) / np.sum(x0[:-1])
                        initial_guesses[j] = x0
                
                # 验证并修正初始点，确保在约束范围内
                valid_initial_guesses = []
                for x0 in initial_guesses:
                    # 检查初始点是否在边界范围内
                    if np.all(x0 >= lower_bounds) and np.all(x0 <= upper_bounds):
                        # 检查是否满足sum(V_min) + phi = 1约束
                        if np.abs(np.sum(x0) - 1.0) < 0.01:
                            valid_initial_guesses.append(x0)
                        else:
                            # 归一化到满足约束
                            x0_normalized = x0 / np.sum(x0)
                            valid_initial_guesses.append(x0_normalized)
                    else:
                        # 投影到可行域
                        x0_clipped = np.clip(x0, lower_bounds, upper_bounds)
                        x0_normalized = x0_clipped / np.sum(x0_clipped)
                        valid_initial_guesses.append(x0_normalized)
                
                # 如果没有有效的初始点，使用均匀初始点
                if not valid_initial_guesses:
                    valid_initial_guesses.append(np.ones(n_min + 1) / (n_min + 1))
                
                for x0 in valid_initial_guesses:
                    for method in methods:
                        try:
                            # 根据方法设置不同的选项
                            if method == 'trust-constr':
                                opt_options = {'maxiter': 500, 'gtol': 1e-6, 'xtol': 1e-6}
                            else:
                                opt_options = optimize_options
                            
                            res = minimize(objective_with_lasso, x0, args=(meas, A_min, A_fluid, current_pe_weight, mn_weights, profile_penalty_factor),
                                           method=method, bounds=bounds, 
                                           constraints=[lin_constraint],
                                           options=opt_options)
                            
                            if res.success and res.fun < best_fun:
                                best_result = res
                                best_fun = res.fun
                                success = True
                        except Exception as e:
                            continue
                
                # 如果所有方法都失败，尝试放松约束
                if not success:
                    # 放松边界约束
                    # 将列表转换为numpy数组才能进行算术运算
                    lower_arr = np.array(lower_bounds)
                    upper_arr = np.array(upper_bounds)
                    relaxed_lower = np.maximum(lower_arr - 0.05, 0.0)
                    relaxed_upper = np.minimum(upper_arr + 0.05, 1.0)
                    relaxed_bounds = Bounds(relaxed_lower, relaxed_upper)
                    
                    for x0 in valid_initial_guesses:
                        try:
                            res = minimize(objective_with_lasso, x0, args=(meas, A_min, A_fluid, current_pe_weight, mn_weights, profile_penalty_factor),
                                           method='SLSQP', bounds=relaxed_bounds, 
                                           constraints=[lin_constraint],
                                           options=optimize_options)
                            
                            if res.success and res.fun < best_fun:
                                best_result = res
                                best_fun = res.fun
                                success = True
                                break
                        except Exception as e:
                            continue
                
                if success and best_result is not None:
                    for j, mineral in enumerate(all_minerals):
                        data.at[i, f'V{mineral}'] = best_result.x[j]
                    data.at[i, 'PHI'] = best_result.x[-1]
                    last_valid_result = best_result.x.copy()
                else:
                    # 优化失败时使用已有孔隙度或上次结果
                    existing_phi = row.get('PHI', None)
                    if existing_phi is not None and not (isinstance(existing_phi, float) and existing_phi == 0.2):
                        # 使用已有孔隙度（密度或核磁）
                        fallback_phi = max(0.01, min(0.4, float(existing_phi)))
                        data.at[i, 'PHI'] = fallback_phi
                        if last_valid_result is not None:
                            for j, mineral in enumerate(all_minerals):
                                data.at[i, f'V{mineral}'] = last_valid_result[j] * (1 - fallback_phi)
                        else:
                            for j, mineral in enumerate(all_minerals):
                                data.at[i, f'V{mineral}'] = (1 - fallback_phi) / n_min
                    elif last_valid_result is not None:
                        for j, mineral in enumerate(all_minerals):
                            data.at[i, f'V{mineral}'] = last_valid_result[j]
                        data.at[i, 'PHI'] = last_valid_result[-1]
                    fail_count += 1
                    if fail_count % 100 == 0:
                        logger.debug(f"优化失败次数: {fail_count}/{i+1}")
            
            logger.debug(f"最优化完成，失败次数: {fail_count}/{len(data)}，L1正则化系数: {lambda_reg}")
            
            # ========== 段边界平滑处理 ==========
            # 在段边界附近（前后5个点），将两种矿物组合的结果按距离加权平均
            logger.info("开始段边界平滑处理...")
            smooth_half_window = 5
            smooth_cols = [f'V{m}' for m in all_minerals] + ['PHI']
            
            # 找到段边界索引
            boundaries = []
            for i in range(1, len(segment_labels)):
                if segment_labels[i] != segment_labels[i-1]:
                    boundaries.append(i)
            
            # 对每个边界进行平滑处理
            smoothed_count = 0
            for boundary_idx in boundaries:
                start = max(0, boundary_idx - smooth_half_window)
                end = min(len(data), boundary_idx + smooth_half_window)
                
                for i in range(start, end):
                    if i < smooth_half_window or i >= len(data) - smooth_half_window:
                        continue
                    # 计算距离权重：离边界越近，权重越大（混合比例越高）
                    dist = abs(i - boundary_idx)
                    weight = max(0, 1.0 - dist / (smooth_half_window + 1))
                    
                    # 只在边界附近有过渡的区域做平滑
                    if weight > 0.3:
                        # 获取边界两侧的值（取边界外的最近有效点）
                        left_idx = max(0, boundary_idx - smooth_half_window - 1)
                        right_idx = min(len(data) - 1, boundary_idx + smooth_half_window + 1)
                        
                        left_valid = True
                        right_valid = True
                        
                        for col in smooth_cols:
                            if col not in data.columns:
                                continue
                            if pd.isna(data.iloc[left_idx][col]):
                                left_valid = False
                            if pd.isna(data.iloc[right_idx][col]):
                                right_valid = False
                        
                        if left_valid and right_valid:
                            smoothed_count += 1
                            # 距离加权平均
                            for col in smooth_cols:
                                if col not in data.columns:
                                    continue
                                left_val = data.iloc[left_idx][col]
                                right_val = data.iloc[right_idx][col]
                                # 当前点越靠近边界，混合比例越高
                                data.at[i, col] = left_val * (1 - weight * 0.5) + right_val * (weight * 0.5)
            
            if smoothed_count > 0:
                logger.info(f"段边界平滑完成，共处理 {smoothed_count} 个点")
            
            # 后优化阈值处理：将矿物含量小于0.05的置为0并重新归一化
            threshold = 0.05
            for mineral in all_minerals:
                col = f'V{mineral}'
                if col in data.columns:
                    data.loc[data[col] < threshold, col] = 0.0
            
            # 重新归一化：确保所有矿物含量+孔隙度之和等于1
            data = self._normalize_mineral_contents(data)
            
            # 记录优化统计
            total_samples = len(data)
            success_rate = (total_samples - fail_count) / total_samples * 100
            logger.debug(f"Optimization completed: success rate {success_rate:.1f}% ({total_samples - fail_count}/{total_samples})")
            
            if fail_count > total_samples * 0.3:
                logger.warning(f"High optimization failure rate: {fail_count}/{total_samples}，Suggest checking data quality")
            
            return data
        except Exception as e:
            logger.error(f"多矿物优化失败: {e}")
            import traceback
            traceback.print_exc()
            # 使用简化方法
            vsh_method = self.config.get('vsh_method', 3)
            data = self.calculate_vsh(data, vsh_method)
            data['PHI'] = 0.2
            for mineral in self.minerals:
                data[f'V{mineral}'] = 0.0
            data['VClay'] = data['VSH']
            data['VQuartz'] = 1 - data['VSH'] - data['PHI']
            return data
    
    def apply_non_reservoir_phi_zeroing(self, data):
        """
        非储层段孔隙度归0和矿物含量重新分配
        
        规则：
        1. 特殊岩性（煤层、膏盐、盐岩、火山岩等）→ PHI=0
        2. 泥岩段（VSH高、GR高）→ PHI=0
        3. 非储层段矿物含量重新分配：sum(minerals)=1.0
        4. 同步VSAND=VQuartz, VSH=VClay
        
        此方法应在optimize_minerals之后、calculate_saturation之前调用，
        确保饱和度计算使用正确的孔隙度值。
        """
        try:
            if 'PHI' not in data.columns:
                logger.warning("apply_non_reservoir_phi_zeroing: PHI列不存在，跳过")
                return data
            
            n_before = len(data)
            
            # ========== 1. 识别特殊岩性（非储层）==========
            exclude_liths = ['coal', 'anhydrite', 'salt', 'halite', 'evaporite',
                             'volcanic', 'basement', 'tuff', 'basalt', 'granite',
                             '煤层', '膏盐', '盐岩', '硬石膏', '火山岩', '花岗岩']
            special_mask = None
            if 'LITHOLOGY' in data.columns:
                special_mask = data['LITHOLOGY'].str.lower().isin(exclude_liths)
            
            # ========== 2. 识别泥岩段（非储层）==========
            # 泥岩特征：VSH高或GR高
            shale_mask = None
            
            # 方法1：使用VSH判断（如果VSH列存在）
            if 'VSH' in data.columns:
                # VSH > 0.6 且孔隙度低 → 可能是泥岩
                vsh_col = data['VSH']
                vsh_high = vsh_col > 0.6
                if 'PHI' in data.columns:
                    phi_low = data['PHI'] < 0.05  # 孔隙度极低
                    shale_mask = vsh_high & phi_low
                else:
                    shale_mask = vsh_high
            
            # 方法2：使用GR判断（如果VSH不可用）
            if shale_mask is None or shale_mask.sum() == 0:
                if 'GR' in data.columns:
                    gr = data['GR']
                    # GR高值段（使用P75或固定阈值）
                    gr_valid = gr[(gr > 0) & (gr < 500)]
                    if len(gr_valid) > 10:
                        gr_threshold = np.percentile(gr_valid, 75)
                    else:
                        gr_threshold = 120
                    if 'PHI' in data.columns:
                        shale_mask = (gr > gr_threshold) & (data['PHI'] < 0.05)
                    else:
                        shale_mask = gr > gr_threshold
            
            # ========== 3. 合并非储层mask ==========
            non_reservoir_mask = None
            if special_mask is not None:
                non_reservoir_mask = special_mask
            if shale_mask is not None:
                non_reservoir_mask = shale_mask if non_reservoir_mask is None else (non_reservoir_mask | shale_mask)
            
            if non_reservoir_mask is None or non_reservoir_mask.sum() == 0:
                logger.info("apply_non_reservoir_phi_zeroing: 无非储层段需要处理")
                return data
            
            nr_count = non_reservoir_mask.sum()
            logger.info(f"非储层段识别: 共{nr_count}点 (特殊岩性={special_mask.sum() if special_mask is not None else 0}, "
                       f"泥岩段={shale_mask.sum() if shale_mask is not None else 0})")
            
            # ========== 4. 非储层段PHI归0 ==========
            data.loc[non_reservoir_mask, 'PHI'] = 0.0
            if 'PORD' in data.columns:
                data.loc[non_reservoir_mask, 'PORD'] = 0.0
            
            # 非储层段饱和度也归0：Sw/So/Sg = 0
            sat_cols = ['Sw', 'So', 'Sg']
            available_sat_cols = [c for c in sat_cols if c in data.columns]
            if available_sat_cols:
                data.loc[non_reservoir_mask, available_sat_cols] = 0.0
            
            # ========== 5. 非储层段矿物含量重新分配 ==========
            # PHI=0的点，矿物含量按比例重新分配使sum(minerals)=1.0
            mineral_cols = ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite',
                            'VHalite', 'VClay']
            available_mineral_cols = [c for c in mineral_cols if c in data.columns]
            
            if available_mineral_cols:
                # 获取非储层点的矿物数据
                nr_minerals = data.loc[non_reservoir_mask, available_mineral_cols].copy()
                # 计算每行矿物总和
                mineral_sum = nr_minerals.sum(axis=1)
                # 避免除零：如果矿物总和为0，给泥岩一个默认值
                zero_sum = mineral_sum <= 0
                if zero_sum.any():
                    clay_col = 'VClay' if 'VClay' in nr_minerals.columns else available_mineral_cols[0]
                    nr_minerals.loc[zero_sum, clay_col] = 1.0
                    mineral_sum = nr_minerals.sum(axis=1)
                # 按比例重新分配使矿物总和=1.0
                nr_minerals = nr_minerals.divide(mineral_sum, axis=0)
                nr_minerals = nr_minerals.fillna(0.0)
                # 写回数据
                data.loc[non_reservoir_mask, available_mineral_cols] = nr_minerals
                
                # 同步VSAND = VQuartz
                if 'VQuartz' in data.columns:
                    data.loc[non_reservoir_mask, 'VSAND'] = data.loc[non_reservoir_mask, 'VQuartz']
                # 同步VSH = VClay
                if 'VClay' in data.columns:
                    data.loc[non_reservoir_mask, 'VSH'] = data.loc[non_reservoir_mask, 'VClay']
                
                logger.info(f"非储层矿物含量重新分配: {nr_count}点, sum(minerals) now = 1.0, PHI = 0")
            
            # ========== 6. 全局归一化保障：确保所有点 minerals + PHI = 1.0 ==========
            # 对储层段也做归一化，保证整体积守恒
            if available_mineral_cols and 'PHI' in data.columns:
                total_volume = data[available_mineral_cols].sum(axis=1) + data['PHI']
                # 避免除零
                zero_vol = total_volume <= 0
                if zero_vol.any():
                    logger.warning(f"发现{zero_vol.sum()}个体积为0的点，设置为全泥岩")
                    if 'VClay' in data.columns:
                        data.loc[zero_vol, 'VClay'] = 1.0
                        data.loc[zero_vol, 'PHI'] = 0.0
                    total_volume = data[available_mineral_cols].sum(axis=1) + data['PHI']
                # 归一化
                non_zero = total_volume > 0
                if non_zero.any():
                    for col in available_mineral_cols:
                        data.loc[non_zero, col] = data.loc[non_zero, col] / total_volume[non_zero]
                    data.loc[non_zero, 'PHI'] = data.loc[non_zero, 'PHI'] / total_volume[non_zero]
                # 同步VSAND/VSH
                if 'VQuartz' in data.columns and 'VSAND' in data.columns:
                    data['VSAND'] = data['VQuartz']
                if 'VClay' in data.columns and 'VSH' in data.columns:
                    data['VSH'] = data['VClay']
            
            logger.info(f"apply_non_reservoir_phi_zeroing完成: 处理{nr_count}个非储层点 (PHI归0 + 饱和度归0 + 矿物重新分配)")
            return data
            
        except Exception as e:
            logger.error(f"apply_non_reservoir_phi_zeroing失败: {e}")
            import traceback
            traceback.print_exc()
            return data

    def _sync_minerals_with_lithology(self, data):
        """
        同步矿物含量与LITHOLOGY列，确保大段岩性与profile道显示一致。

        在LITHOLOGY列确定后调用，根据岩性定名调整矿物含量列，使数据层
        （VQuartz/VHalite等）与岩性道（LITHOLOGY）使用同一套判别逻辑。
        替代log_visualizer.py中的显示层LITHOLOGY一致性补丁。

        规则：
        1. 特殊岩性（halite/anhydrite）：对应矿物强制主导(~0.85)，PHI=0
        2. 常规岩性（sandstone/shale/limestone/dolomite）：当LITHOLOGY对应矿物
           不是当前主导矿物时，调整使其主导(~0.55)
        3. 无对应矿物的特殊岩性（coal/gypsum/volcanic等）：保持不变
        4. 重新归一化 minerals + PHI = 1.0，同步VSAND/VSH
        """
        try:
            if 'LITHOLOGY' not in data.columns:
                return data

            mineral_cols = ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite',
                            'VHalite', 'VClay']
            available = [c for c in mineral_cols if c in data.columns]
            if not available:
                return data

            # 岩性 → 主导矿物列名
            # 特殊岩性（强覆盖）：对应矿物占绝对主导
            special_lith_map = {
                'halite': 'VHalite',
                'salt': 'VHalite',
                '盐岩': 'VHalite',
                '盐': 'VHalite',
                'anhydrite': 'VAnhydrite',
                '硬石膏': 'VAnhydrite',
            }
            # 常规岩性（弱覆盖）：仅在矿物含量严重不一致时调整
            regular_lith_map = {
                'limestone': 'VCalcite',
                '灰岩': 'VCalcite',
                '石灰岩': 'VCalcite',
                'dolomite': 'VDolomite',
                '白云岩': 'VDolomite',
                'sandstone': 'VQuartz',
                '砂岩': 'VQuartz',
                'shale': 'VClay',
                '泥岩': 'VClay',
                '页岩': 'VClay',
            }
            # 无对应矿物的岩性：跳过（由岩性道显示）
            skip_liths = {'coal', 'gypsum', 'volcanic', 'basalt', 'tuff',
                          'granite', 'basement', 'unknown', 'pyrite', 'mixed',
                          '煤层', '石膏', '火山岩', '花岗岩', '混合'}

            has_phi = 'PHI' in data.columns
            special_count = 0
            regular_count = 0

            for idx in data.index:
                lith_raw = data.loc[idx, 'LITHOLOGY']
                lith = str(lith_raw).lower().strip()
                if not lith or lith in ('nan', 'none', ''):
                    continue

                # 特殊岩性：强覆盖
                if lith in special_lith_map:
                    dom_col = special_lith_map[lith]
                    if dom_col not in available:
                        continue
                    # 强制主导矿物占0.85，其他按比例缩放到0.15
                    other_cols = [c for c in available if c != dom_col]
                    other_sum = sum(data.loc[idx, c] for c in other_cols)
                    if other_sum > 0.001:
                        scale = 0.15 / other_sum
                        for c in other_cols:
                            data.loc[idx, c] = data.loc[idx, c] * scale
                    else:
                        # 其他矿物都为0，均分0.15
                        if other_cols:
                            residual = 0.15 / len(other_cols)
                            for c in other_cols:
                                data.loc[idx, c] = residual
                    data.loc[idx, dom_col] = 0.85
                    # 特殊岩性为非储层，PHI=0
                    if has_phi:
                        data.loc[idx, 'PHI'] = 0.0
                    if 'PORD' in data.columns:
                        data.loc[idx, 'PORD'] = 0.0
                    # 饱和度归0
                    for sc in ['Sw', 'So', 'Sg']:
                        if sc in data.columns:
                            data.loc[idx, sc] = 0.0
                    special_count += 1

                # 常规岩性：清理微量无关矿物 + 在严重不一致时调整
                elif lith in regular_lith_map:
                    dom_col = regular_lith_map[lith]
                    if dom_col not in available:
                        continue

                    # 砂泥岩剖面：清理微量碳酸盐/盐岩/硬石膏矿物（<5%的无关矿物设为0）
                    if lith in ('sandstone', '砂岩', 'shale', '泥岩', '页岩'):
                        # 砂泥岩只保留VQuartz和VClay，其他矿物设为0
                        irrelevant_cols = [c for c in available
                                           if c not in ('VQuartz', 'VClay')]
                        for c in irrelevant_cols:
                            data.loc[idx, c] = 0.0
                        # 根据LITHOLOGY重新分配矿物含量，确保：
                        # 1. 主导矿物与LITHOLOGY一致且占绝对多数
                        # 2. 次要矿物保留原始含量（代表真实的夹层）
                        # 3. 矿物总和 = 1 - PHI（孔隙度）
                        phi_val = data.loc[idx, 'PHI'] if has_phi else 0.0
                        target_sum = max(1.0 - phi_val, 0.01)
                        if lith in ('sandstone', '砂岩'):
                            # 砂岩：Quartz主导，Clay为次要矿物（保留原始含量）
                            secondary_val = max(0.0, min(data.loc[idx, 'VClay'], target_sum * 0.4))
                            data.loc[idx, 'VClay'] = secondary_val
                            data.loc[idx, 'VQuartz'] = max(target_sum - secondary_val, 0.0)
                        else:
                            # 泥岩：Clay主导，Quartz为次要矿物（保留原始含量）
                            secondary_val = max(0.0, min(data.loc[idx, 'VQuartz'], target_sum * 0.4))
                            data.loc[idx, 'VQuartz'] = secondary_val
                            data.loc[idx, 'VClay'] = max(target_sum - secondary_val, 0.0)
                        regular_count += 1
                        continue

                    dom_val = data.loc[idx, dom_col]
                    # 找当前最大矿物
                    max_col = max(available, key=lambda c: data.loc[idx, c])
                    max_val = data.loc[idx, max_col]
                    # 仅当LITHOLOGY对应矿物不是当前最大，或其值<0.3时才调整
                    if max_col == dom_col and dom_val >= 0.3:
                        continue  # 已经一致，无需调整
                    # 调整：主导矿物占0.55，其他按比例缩放到0.45
                    other_cols = [c for c in available if c != dom_col]
                    phi_val = data.loc[idx, 'PHI'] if has_phi else 0.0
                    other_target = max(0.45 - phi_val, 0.05)  # 留出PHI空间
                    other_sum = sum(data.loc[idx, c] for c in other_cols)
                    if other_sum > 0.001:
                        scale = other_target / other_sum
                        for c in other_cols:
                            data.loc[idx, c] = data.loc[idx, c] * scale
                    else:
                        if other_cols:
                            residual = other_target / len(other_cols)
                            for c in other_cols:
                                data.loc[idx, c] = residual
                    data.loc[idx, dom_col] = 0.55
                    regular_count += 1

                # skip_liths 和其他：不处理
                # （mixed等由矿物含量自然决定，不做强制覆盖）

            # ========== 全局归一化：确保 minerals + PHI = 1.0 ==========
            if has_phi:
                total = data[available].sum(axis=1) + data['PHI']
                zero_vol = total <= 0
                if zero_vol.any():
                    if 'VClay' in data.columns:
                        data.loc[zero_vol, 'VClay'] = 1.0
                        data.loc[zero_vol, 'PHI'] = 0.0
                    total = data[available].sum(axis=1) + data['PHI']
                non_zero = total > 0
                if non_zero.any():
                    for c in available:
                        data.loc[non_zero, c] = data.loc[non_zero, c] / total[non_zero]
                    data.loc[non_zero, 'PHI'] = data.loc[non_zero, 'PHI'] / total[non_zero]

            # 同步 VSAND = VQuartz, VSH = VClay
            if 'VQuartz' in data.columns and 'VSAND' in data.columns:
                data['VSAND'] = data['VQuartz']
            if 'VClay' in data.columns and 'VSH' in data.columns:
                data['VSH'] = data['VClay']

            # 同步 VOL_* 列（LAS原始列），确保所有可能的列名一致
            # 防止其他代码路径读取到未同步的VOL_*列
            vol_sync_map = {
                'VQuartz': 'VOL_QUARTZ', 'VCalcite': 'VOL_CALCITE',
                'VDolomite': 'VOL_DOLOM', 'VAnhydrite': 'VOL_ANHY',
                'VHalite': 'VOL_HALITE', 'VClay': 'VOL_ILLITE',
            }
            for v_col, vol_col in vol_sync_map.items():
                if v_col in data.columns and vol_col in data.columns:
                    data[vol_col] = data[v_col]

            if special_count > 0 or regular_count > 0:
                logger.info(f"_sync_minerals_with_lithology: 特殊岩性调整{special_count}点, "
                           f"常规岩性调整{regular_count}点, 矿物含量现已与LITHOLOGY一致")

            return data

        except Exception as e:
            logger.error(f"_sync_minerals_with_lithology失败: {e}")
            import traceback
            traceback.print_exc()
            return data

    def _identify_typical_water_layers(self, data):
        """
        从全井段中识别典型水层（连续厚水层）。
        
        典型水层条件：
        1. 连续段厚度 >= 2米
        2. 孔隙度 > 储层下限（砂泥岩8%，碳酸盐岩6%）
        3. 泥质含量低（VSH < 0.4 或 GR低）
        4. 电阻率低（水层特征，RT较低）
        
        返回: [(start_md, end_md, thickness), ...] 典型水层列表
        """
        try:
            # 动态检测可用电阻率列
            rt_col_name = None
            for candidate in ['RT', 'LLD', 'AT90', 'ILD', 'RDEEP', 'M2RX', 'AT60', 'RLA5']:
                if candidate in data.columns:
                    rt_col_name = candidate
                    break
            if 'PHI' not in data.columns or rt_col_name is None:
                return []
            
            phi = data['PHI'].values
            rt = data[rt_col_name].values
            md = data['MD'].values
            n = len(md)
            
            # 深度步长（用于计算连续段厚度）
            md_diffs = np.diff(md)
            if len(md_diffs) > 0:
                median_step = np.median(md_diffs[md_diffs > 0])
            else:
                median_step = 0.1  
            if np.isnan(median_step) or median_step <= 0:
                median_step = 0.1
            
            # === 条件1: 储层识别（孔隙度 > 下限）===
            # 砂泥岩孔隙度下限8%，碳酸盐岩6%
            min_porosity = 0.06  # 用较低的碳酸盐岩下限，避免漏掉碳酸盐岩水层
            is_reservoir = (phi > min_porosity) & np.isfinite(phi)
            
            # === 条件2: 泥质含量低（干净地层）===
            if 'VSH' in data.columns:
                is_clean = (data['VSH'].values < 0.4) & np.isfinite(data['VSH'].values)
            elif 'GR' in data.columns:
                gr = data['GR'].values
                gr_valid = gr[np.isfinite(gr)]
                if len(gr_valid) > 10:
                    gr_clean = np.percentile(gr_valid, 25)
                    gr_dirty = np.percentile(gr_valid, 75)
                    gr_threshold = gr_clean + 0.35 * (gr_dirty - gr_clean)
                    is_clean = (gr < gr_threshold) & np.isfinite(gr)
                else:
                    is_clean = np.ones(n, dtype=bool)
            else:
                is_clean = np.ones(n, dtype=bool)
            
            # === 条件3: 电阻率低（水层特征）===
            # 使用电阻率分位数，取全井段电阻率较低的部分作为水层候选
            rt_valid = rt[np.isfinite(rt) & (rt > 0.05)]
            if len(rt_valid) < 10:
                return []
            rt_low_threshold = np.percentile(rt_valid, 35)  # 下35%分位作为水层电阻率上限
            is_low_rt = (rt < rt_low_threshold) & (rt > 0.05) & np.isfinite(rt)
            
            # === 综合水层候选标记 ===
            is_water_candidate = is_reservoir & is_clean & is_low_rt
            
            if np.sum(is_water_candidate) < 5:
                # 放宽条件：只要储层 + 低RT
                logger.info("水层候选点不足，放宽为仅需储层+低电阻率")
                is_water_candidate = is_reservoir & is_low_rt
            
            # === 分组：找出连续水层段 ===
            water_layers = []
            i = 0
            while i < n:
                if not is_water_candidate[i]:
                    i += 1
                    continue
                # 找到连续水层段的结束位置
                seg_start_md = md[i]
                j = i + 1
                while j < n and is_water_candidate[j]:
                    j += 1
                seg_end_md = md[min(j, n - 1)]
                thickness = seg_end_md - seg_start_md
                
                # 厚度 >= 2米 才认为是典型水层
                if thickness >= 2.0:
                    water_layers.append((seg_start_md, seg_end_md, thickness))
                i = j
            
            if water_layers:
                logger.info(f"识别到{len(water_layers)}个典型水层(>2m): " +
                           ", ".join([f"{s:.1f}-{e:.1f}m({t:.1f}m)" 
                                      for s, e, t in water_layers[:5]]) +
                           ("..." if len(water_layers) > 5 else ""))
            else:
                # 放宽：只要有连续水层候选段，取前几个最厚的
                logger.info("未找到>2m典型水层，尝试使用较薄连续水层段")
                # 重新分组，取所有连续段
                i = 0
                all_layers = []
                while i < n:
                    if not is_water_candidate[i]:
                        i += 1
                        continue
                    seg_start_md = md[i]
                    j = i + 1
                    while j < n and is_water_candidate[j]:
                        j += 1
                    seg_end_md = md[min(j, n - 1)]
                    thickness = seg_end_md - seg_start_md
                    all_layers.append((seg_start_md, seg_end_md, thickness))
                    i = j
                # 取最厚的几个段
                all_layers.sort(key=lambda x: x[2], reverse=True)
                water_layers = all_layers[:3]  # 取前3个最厚的水层段
            
            return water_layers
            
        except Exception as e:
            logger.error(f"识别典型水层失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _auto_detect_Rw(self, data, a=1.0, m=2.0):
        """从典型厚水层自动计算地层水电阻率 Rw
        
        原理：
        1. 识别典型水层（连续厚度>2m、储层、低VSH、低RT）
        2. 仅从典型水层反算 Rw = φ^m × Rt / a（假设Sw=1）
        3. 作 sqrt(Rw) 累计频率直方图
        4. 取频率50%处的 Rw 作为本井水层电阻率
        """
        try:
            rt_col_name = None
            for candidate in ['RT', 'LLD', 'AT90', 'ILD', 'RDEEP', 'M2RX', 'AT60', 'RLA5']:
                if candidate in data.columns:
                    rt_col_name = candidate
                    break
            if 'PHI' not in data.columns or rt_col_name is None:
                logger.warning("缺少PHI或电阻率列，无法自动计算Rw")
                return None, None
            
            rt = data[rt_col_name].copy()
            phi = data['PHI'].copy()
            md = data['MD'].values
            logger.info(f"自动检测Rw使用电阻率列: {rt_col_name}")
            
            # ========== 识别典型厚水层 ==========
            water_layers = self._identify_typical_water_layers(data)
            
            if water_layers:
                # 从典型水层中提取数据点
                logger.info(f"从{len(water_layers)}个典型水层计算Rw，" +
                           f"总厚度{sum(t for _,_,t in water_layers):.1f}m")
                
                # 构建水层掩码
                mask = np.zeros(len(data), dtype=bool)
                for start_md, end_md, _ in water_layers:
                    mask |= (md >= start_md) & (md <= end_md)
                
                n_water_pts = mask.sum()
                logger.info(f"典型水层数据点: {n_water_pts}个")
            else:
                # 降级：回退到逐点筛选模式
                logger.info("无典型水层，回退到逐点筛选模式")
                mask = (phi > 0.05) & (rt > 0.1) & (rt < 500)
                if 'VSH' in data.columns:
                    mask = mask & (data['VSH'] < 0.4)
                elif 'GR' in data.columns:
                    gr_data = data['GR'].dropna()
                    if len(gr_data) > 0:
                        gr_clean = gr_data.quantile(0.25)
                        gr_dirty = gr_data.quantile(0.75)
                        gr_threshold = gr_clean + 0.4 * (gr_dirty - gr_clean)
                        mask = mask & (data['GR'] < gr_threshold)
            
            if mask.sum() < 5:
                # 进一步放宽
                logger.info(f"候选点不足（{mask.sum()}个），使用全井段")
                mask = (phi > 0.03) & (rt > 0.1) & (rt < 1000)
            
            # ========== 反算 Rw ==========
            rw_values = (phi[mask] ** m) * rt[mask] / a
            rw_values = rw_values[(rw_values > 0.001) & (rw_values < 100)]
            
            if len(rw_values) < 5:
                logger.warning(f"有效Rw值不足（{len(rw_values)}个），无法计算")
                return None, None
            
            # ========== sqrt(Rw) 累计频率直方图 ==========
            sqrt_rw = np.sqrt(rw_values)
            sorted_sqrt_rw = np.sort(sqrt_rw)
            cum_freq = np.arange(1, len(sorted_sqrt_rw) + 1) / len(sorted_sqrt_rw)
            
            idx_50 = np.searchsorted(cum_freq, 0.5)
            idx_50 = min(idx_50, len(sorted_sqrt_rw) - 1)
            sqrt_rw_50 = sorted_sqrt_rw[idx_50]
            rw_50 = sqrt_rw_50 ** 2
            
            rw_stats = {
                'rw_50': rw_50,
                'sqrt_rw_50': sqrt_rw_50,
                'rw_mean': float(rw_values.mean()),
                'rw_median': float(rw_values.median()),
                'rw_std': float(rw_values.std()),
                'rw_p10': float(np.percentile(rw_values, 10)),
                'rw_p90': float(np.percentile(rw_values, 90)),
                'n_candidates': len(rw_values),
                'n_water_layers': len(water_layers),
                'water_layer_thickness': sum(t for _,_,t in water_layers) if water_layers else 0
            }
            
            logger.info(f"自动计算Rw: 候选点{len(rw_values)}个(来自{len(water_layers)}个水层), "
                       f"sqrt(Rw)50%={sqrt_rw_50:.4f}, Rw={rw_50:.4f}, "
                       f"Rw范围[{rw_stats['rw_p10']:.4f}-{rw_stats['rw_p90']:.4f}]")
            
            return rw_50, rw_stats
        except Exception as e:
            logger.error(f"自动计算Rw失败: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def calculate_saturation(self, data):
        """计算流体饱和度（有效曲线不足3条的井段不计算）"""
        try:
            # 使用阿尔奇公式计算含水饱和度
            # 动态检测可用电阻率列（支持阵列电阻率 AT90/AT60/AT30/M2RX 等）
            rt_col_name = None
            for candidate in ['RT', 'LLD', 'AT90', 'ILD', 'RDEEP', 'M2RX', 'AT60', 'RLA5']:
                if candidate in data.columns:
                    rt_col_name = candidate
                    break
            if 'PHI' in data.columns and rt_col_name is not None:
                # 从配置文件读取阿尔奇公式参数
                archie_config = self.config.get('archie', {})
                a = archie_config.get('a', 1.0)
                m = archie_config.get('m', 2.0)
                n = archie_config.get('n', 2.0)
                
                # ========== 自动检测 Rw（从明显水层）==========
                rw_result = self._auto_detect_Rw(data, a=a, m=m)
                if rw_result is not None and rw_result[0] is not None:
                    Rw = rw_result[0]
                    rw_stats = rw_result[1]
                    logger.info(f"使用自动检测的Rw={Rw:.4f}（来自水层sqrt(Rw)50%频率）")
                    # 保存Rw到config供后续使用
                    self.config['archie'] = self.config.get('archie', {})
                    self.config['archie']['Rw'] = Rw
                    if rw_stats:
                        self.config['archie']['rw_stats'] = rw_stats
                else:
                    Rw = archie_config.get('Rw', 0.05)
                    logger.debug(f"自动检测Rw失败，使用配置的Rw={Rw}")
                
                # 使用动态检测的电阻率列
                rt = data[rt_col_name]
                logger.info(f"使用电阻率列: {rt_col_name}")
                data['RT_COL'] = rt_col_name  # 记录使用的电阻率列名
                
                # 计算Sw
                # 使用阿尔奇公式：Sw = (a * Rw / (φ^m * RT))^(1/n)
                # 避免PHI=0导致除零错误（使用<0.001阈值判断，处理极小值）
                phi_safe = data['PHI'].copy()
                # PHI < 0.001 视为非储层，用NaN代替避免除零
                phi_safe[phi_safe < 0.001] = np.nan
                phi_safe = phi_safe.replace(np.inf, np.nan)
                
                # 计算饱和度
                sw_raw = (a * Rw / (phi_safe**m * rt))**(1/n)
                sw_raw = sw_raw.clip(0, 1)
                
                # PHI < 0.001 的点（非储层段），饱和度归0
                phi_zero_mask = data['PHI'] < 0.001
                sw_raw[phi_zero_mask] = 0.0
                
                data['Sw'] = sw_raw
                data['Sw'] = data['Sw'].fillna(0.0)  # NaN也设为0
                
                # 计算含油饱和度
                data['So'] = 1 - data['Sw']
                
                # 计算含气饱和度（简化处理）
                data['Sg'] = 0
                
                # 非储层段饱和度归0：Sw/So/Sg = 0
                data.loc[phi_zero_mask, ['Sw', 'So', 'Sg']] = 0.0
                
                # 有效曲线不足3条的井段不计算饱和度
                if 'VALID_CURVES_COUNT' in data.columns:
                    data.loc[data['VALID_CURVES_COUNT'] < 3, ['Sw', 'So', 'Sg']] = np.nan
            else:
                data['Sw'] = 0.0
                data['So'] = 0.0
                data['Sg'] = 0.0
            
            return data
        except Exception as e:
            logger.error(f"计算饱和度失败: {e}")
            data['Sw'] = 0.0
            data['So'] = 0.0
            data['Sg'] = 0.0
            return data
    
    def check_pe_quality(self, data, well_name='Unknown'):
        """
        井级别PE曲线质量检测
        
        判断PE曲线是否可靠，分三级：
        - reliable: PE绝对值可信，正常使用
        - trend_only: PE绝对值偏差（仪器校准问题），但趋势可用
        - bad: PE完全不可用
        
        检测规则：
        1. PE与密度一致性：密度<2.65的砂泥岩剖面，PE应<3.0
        2. PE与GR一致性：PE>3.0的碳酸盐岩剖面，GR应为低值
        3. PE与RT一致性：PE>3.0的碳酸盐岩剖面，RT应较高
        """
        pe_col = None
        den_col = None
        for name in ['PE', 'PEF']:
            if name in data.columns:
                pe_col = name
                break
        for name in ['RHOB', 'DEN']:
            if name in data.columns:
                den_col = name
                break
        
        result = {
            'pe_reliable': True,      # PE绝对值可信
            'pe_trend_only': False,   # PE趋势可用但绝对值偏差
            'pe_bad': False,          # PE完全不可用
            'pe_col': pe_col,
            'reason': 'PE quality OK',
            'pe_offset': 0.0,         # PE系统性偏移量
            'pe_scale': 1.0,          # PE缩放因子
        }
        
        if pe_col is None:
            result['pe_bad'] = True
            result['pe_reliable'] = False
            result['reason'] = 'No PE curve found'
            return result
        
        pe_vals = data[pe_col].dropna()
        pe_vals = pe_vals[pe_vals > -999]
        if len(pe_vals) < 50:
            result['pe_bad'] = True
            result['pe_reliable'] = False
            result['reason'] = f'Insufficient PE data ({len(pe_vals)} valid points)'
            return result
        
        pe_median = pe_vals.median()
        pe_high_ratio = (pe_vals > 3.5).sum() / len(pe_vals)
        
        # 获取密度、GR、RT统计
        den_median = 2.65
        gr_median = 80
        rt_median = 50
        if den_col:
            den_vals = data[den_col].dropna()
            den_vals = den_vals[den_vals > 0]
            if len(den_vals) > 50:
                den_median = den_vals.median()
        if 'GR' in data.columns:
            gr_vals = data['GR'].dropna()
            gr_vals = gr_vals[gr_vals > -999]
            if len(gr_vals) > 50:
                gr_median = gr_vals.median()
        rt_col = None
        for name in ['LLD', 'RT', 'ILD', 'AT90', 'M2RX', 'RDEEP']:
            if name in data.columns:
                rt_col = name
                break
        if rt_col:
            rt_vals = data[rt_col].dropna()
            rt_vals = rt_vals[rt_vals > -999]
            if len(rt_vals) > 50:
                rt_median = rt_vals.median()
        
        # ========== 检测1：PE与密度一致性 ==========
        # 密度<2.65（砂泥岩剖面），但PE偏高 → PE不合格
        pe_inconsistent_with_den = False
        if den_median < 2.65:
            # 砂泥岩剖面PE应该低
            if pe_median > 3.0:
                pe_inconsistent_with_den = True
                
                # 进一步判断PE异常程度
                den_gt_265 = (den_vals > 2.65).sum() / len(den_vals) if den_col else 0
                if den_median < 2.40 and pe_high_ratio > 0.8:
                    # 极低密度+全井PE高 → PE严重偏离，仪器校准问题
                    result['pe_trend_only'] = True
                    result['pe_reliable'] = False
                    result['reason'] = (
                        f'PE严重偏离：DEN中位数={den_median:.2f}(砂泥岩剖面)但PE中位数={pe_median:.1f}(>3.0)，'
                        f'PE>3.5占比={pe_high_ratio*100:.0f}%。PE绝对值不可信，仅趋势可用。'
                    )
                    # 计算PE偏移量用于归一化
                    # 砂泥岩PE正常约2.0（石英1.81+粘土3.45的混合），实际测得pe_median
                    # offset = pe_median - 2.0
                    result['pe_offset'] = pe_median - 2.5  # 减去正常砂泥岩PE基准
                elif den_median < 2.55:
                    result['pe_trend_only'] = True
                    result['pe_reliable'] = False
                    result['reason'] = (
                        f'PE与密度不一致：DEN中位数={den_median:.2f}(砂泥岩)但PE中位数={pe_median:.1f}(碳酸盐岩特征)。'
                        f'PE绝对值偏差，趋势可用。'
                    )
                    result['pe_offset'] = pe_median - 2.5
                elif pe_high_ratio > 0.7:
                    # 密度在2.55-2.65临界区，PE高占比很大，标记为可疑
                    # 但如果DEN>2.65占比>30%（混合剖面，有大量碳酸盐岩），PE可能是正确的
                    if den_gt_265 > 0.3:
                        # 混合剖面：虽然中位数低，但有大量高密度段，PE趋势可信
                        logger.info(
                            f'PE折中处理：DEN中位数={den_median:.2f}但DEN>2.65占比={den_gt_265*100:.0f}%，'
                            f'属于混合剖面，PE绝对值可信。'
                        )
                        # 不标记为trend_only，保留PE绝对值
                        result['pe_trend_only'] = False
                        result['pe_reliable'] = True
                        result['pe_offset'] = 0.0
                        result['reason'] = (
                            f'PE部分可信：DEN中位数={den_median:.2f}(临界)但DEN>2.65占比={den_gt_265*100:.0f}%，'
                            f'PE绝对值趋势可用于岩性判断。'
                        )
                    else:
                        result['pe_trend_only'] = True
                        result['pe_reliable'] = False
                        result['reason'] = (
                            f'PE可疑：DEN中位数={den_median:.2f}(临界)但PE>3.5占比={pe_high_ratio*100:.0f}%。'
                            f'保守处理，PE绝对值不用于岩性判断。'
                        )
                        result['pe_offset'] = pe_median - 3.0
        
        # ========== 检测2：PE与GR/RT一致性 ==========
        # PE>3.0的碳酸盐岩剖面，GR应低、RT应高
        if result['pe_reliable'] and pe_median > 3.0:
            inconsistencies = []
            if gr_median > 90:
                inconsistencies.append(f'GR中位数={gr_median:.0f}(高)')
            if rt_median < 15:
                inconsistencies.append(f'RT中位数={rt_median:.1f}(低)')
            
            if len(inconsistencies) >= 2:
                result['pe_reliable'] = False
                result['pe_trend_only'] = True
                result['reason'] = (
                    f'PE与GR/RT不一致：PE中位数={pe_median:.1f}(碳酸盐岩特征)但'
                    f'{", ".join(inconsistencies)}。PE绝对值不可信。'
                )
                result['pe_offset'] = pe_median - 2.5
            elif len(inconsistencies) == 1:
                result['pe_reliable'] = False
                result['pe_trend_only'] = True
                result['reason'] = (
                    f'PE部分不一致：PE={pe_median:.1f}但{inconsistencies[0]}。PE可能偏移。'
                )
                result['pe_offset'] = pe_median - 3.0
        
        # 日志输出
        if result['pe_bad']:
            logger.warning(f"[{well_name}] PE曲线不合格: {result['reason']}")
        elif result['pe_trend_only']:
            logger.warning(f"[{well_name}] PE绝对值不可信（趋势可用）: {result['reason']}")
        else:
            logger.info(f"[{well_name}] PE曲线质量合格: PE中位数={pe_median:.2f}, "
                       f"DEN中位数={den_median:.2f}, GR中位数={gr_median:.0f}, RT中位数={rt_median:.1f}")
        
        return result
    
    def check_hole_quality(self, data, well_name='Unknown'):
        """
        井级别井径扩径质量检测
        
        扩径对测井曲线的影响（根据SY/T 5132-2012和实际经验）：
        - cal_ratio > 1.15: 密度(DEN)偏低、中子(NPHI)偏高、PE异常 → 标记为不可信
        - cal_ratio > 1.25: 声波(DT)也受显著影响 → 标记为不可信
        - cal_ratio > 1.35: 所有贴井壁测量严重失真 → 全部标记不可信
        
        返回: {
            'cal_ratio_median': float,        # 井径比中位数
            'bad_hole_ratio': float,          # 扩径严重(>1.25)的深度占比
            'extreme_hole_ratio': float,      # 极度扩径(>1.35)的深度占比
            'bad_mask': Series(bool),         # 每个深度点是否井径严重
            'extreme_mask': Series(bool),     # 每个深度点是否极度扩径
            'summary': str,                   # 质量总结
        }
        """
        # 获取井径和钻头尺寸
        cal_col = None
        for name in ['CAL', 'CALS', 'CALI']:
            if name in data.columns:
                cal_col = name
                break
        
        bit_col = None
        for name in ['BIT', 'BS', 'BIT_SIZE']:
            if name in data.columns:
                bit_col = name
                break
        
        if cal_col is None:
            logger.info(f"[{well_name}] 无井径曲线，跳过井径质量检查")
            return {
                'cal_ratio_median': 1.0,
                'bad_hole_ratio': 0.0,
                'extreme_hole_ratio': 0.0,
                'bad_mask': pd.Series(False, index=data.index),
                'extreme_mask': pd.Series(False, index=data.index),
                'summary': '无井径数据',
            }
        
        # 计算井径比
        cal = data[cal_col].copy()
        if bit_col and bit_col in data.columns:
            bit = data[bit_col].copy()
            # 钻头尺寸应该是常数，取中位数
            bit_val = bit[bit > 0].median() if (bit > 0).sum() > 0 else 8.5
        else:
            bit_val = 8.5  # 默认8.5英寸钻头
            logger.info(f"[{well_name}] 无钻头尺寸曲线，使用默认值 {bit_val} in")
        
        cal_ratio = cal / max(bit_val, 0.1)
        cal_ratio = cal_ratio[cal > 0]  # 过滤无效井径值
        
        if len(cal_ratio) < 10:
            logger.warning(f"[{well_name}] 井径有效数据点不足")
            return {
                'cal_ratio_median': 1.0,
                'bad_hole_ratio': 0.0,
                'extreme_hole_ratio': 0.0,
                'bad_mask': pd.Series(False, index=data.index),
                'extreme_mask': pd.Series(False, index=data.index),
                'summary': '井径数据不足',
            }
        
        cal_median = cal_ratio.median()
        bad_ratio = (cal_ratio > 1.25).sum() / len(cal_ratio)
        extreme_ratio = (cal_ratio > 1.35).sum() / len(cal_ratio)
        
        # 构建全深度mask
        full_cal_ratio = cal / max(bit_val, 0.1)
        bad_mask = full_cal_ratio > 1.25
        extreme_mask = full_cal_ratio > 1.35
        
        # 判断
        if extreme_ratio > 0.3:
            quality = '差'
            summary = (f'井径质量差：井径比中位数={cal_median:.2f}，{extreme_ratio*100:.0f}%深度极度扩径(>1.35)，'
                      f'密度/中子/PE/声波均不可信')
        elif bad_ratio > 0.3:
            quality = '较差'
            summary = (f'井径质量较差：井径比中位数={cal_median:.2f}，{bad_ratio*100:.0f}%深度扩径(>1.25)，'
                      f'密度/中子/PE在扩径段不可信')
        elif bad_ratio > 0.1:
            quality = '一般'
            summary = f'井径质量一般：井径比中位数={cal_median:.2f}，{bad_ratio*100:.0f}%深度扩径，注意局部段'
        else:
            quality = '良好'
            summary = f'井径质量良好：井径比中位数={cal_median:.2f}，扩径比例低'
        
        logger.info(f"[{well_name}] 井径质量: {quality}, {summary}")
        
        return {
            'cal_ratio_median': cal_median,
            'bad_hole_ratio': bad_ratio,
            'extreme_hole_ratio': extreme_ratio,
            'bad_mask': bad_mask,
            'extreme_mask': extreme_mask,
            'quality': quality,
            'summary': summary,
        }
    
    def query_knowledge_base(self, profile_type, well_name='Unknown'):
        """
        查询本地知识库，获取与当前井剖面类型相关的解释经验
        
        知识库位于 data/knowledge_summary/，包含：
        - lithology_identification.md: 岩性识别标准
        - quality_control.md: 质量控制要点
        - fluid_identification.md: 流体识别
        - formation_evaluation_params.md: 地层评价参数
        等
        
        返回: dict of relevant knowledge snippets
        """
        import glob
        
        knowledge_dir = Path('data/knowledge_summary')
        if not knowledge_dir.exists():
            logger.info(f"[{well_name}] 知识库目录不存在: {knowledge_dir}")
            return {}
        
        # 加载所有知识文件
        knowledge = {}
        for md_file in sorted(knowledge_dir.glob('*.md')):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    topic = md_file.stem
                    knowledge[topic] = content
            except Exception as e:
                logger.debug(f"读取知识文件失败 {md_file}: {e}")
        
        # 根据剖面类型筛选相关知识
        relevant = {}
        
        if 'quality_control' in knowledge:
            relevant['quality_control'] = knowledge['quality_control']
        
        if 'lithology_identification' in knowledge:
            relevant['lithology_identification'] = knowledge['lithology_identification']
        
        if profile_type == 'sand_shale':
            if 'shale_volume' in knowledge:
                relevant['shale_volume'] = knowledge['shale_volume']
            if 'permeability' in knowledge:
                relevant['permeability'] = knowledge['permeability']
            if 'fluid_identification' in knowledge:
                relevant['fluid_identification'] = knowledge['fluid_identification']
        elif profile_type == 'carbonate':
            if 'formation_evaluation_params' in knowledge:
                relevant['formation_evaluation_params'] = knowledge['formation_evaluation_params']
            if 'fluid_identification' in knowledge:
                relevant['fluid_identification'] = knowledge['fluid_identification']
        else:
            # mixed profile: load all
            relevant = knowledge
        
        # 记录加载的知识
        logger.info(f"[{well_name}] 知识库已加载 {len(relevant)} 个相关文档: {list(relevant.keys())}")
        
        # 存储到 data.attrs 供下游使用
        return relevant
    
    def run_mineral_analysis(self, data, well_name='Unknown'):
        """运行多矿物分析（三层岩性识别架构）"""
        try:
            logger.info("Starting multi-mineral analysis (three-layer lithology identification)")
            
            # ========== 前置步骤0：PE曲线质量检测（井级别）==========
            logger.info("Pre-step 0: PE curve quality check")
            self.pe_quality = self.check_pe_quality(data, well_name)
            # 将PE质量信息存入data.attrs，供下游模块（optimize_minerals/地质约束/段分类）使用
            data.attrs['pe_quality'] = {
                'reliable': self.pe_quality.get('pe_reliable', True),
                'trend_only': self.pe_quality.get('pe_trend_only', False),
                'bad': self.pe_quality.get('pe_bad', False),
                'reason': self.pe_quality.get('reason', ''),
                'offset': self.pe_quality.get('pe_offset', 0),
            }
            
            # ========== 前置步骤0b：井径扩径质量检测 ==========
            # 扩径会导致密度偏低、中子偏高、PE异常、声波偏大
            # 当井径超出钻头尺寸一定比例时，测井值不可信
            hole_quality = self.check_hole_quality(data, well_name)
            data.attrs['hole_quality'] = hole_quality
            logger.info(f"Hole quality check: {hole_quality['summary']}")
            
            # ========== PE趋势归一化：PE绝对值不可信但趋势可用时，减去系统偏移 ==========
            if self.pe_quality.get('pe_trend_only', False):
                pe_offset = self.pe_quality.get('pe_offset', 0)
                pe_col_name = self.pe_quality.get('pe_col')
                if pe_col_name and pe_offset > 0:
                    # 对PE列做归一化：减去偏移量，保留趋势变化
                    # 例如XIMENIA-5 PE中位数约8.5，偏移量约6.0，归一化后范围约2.5
                    data[pe_col_name] = data[pe_col_name].apply(
                        lambda x: max(0.5, min(8.0, x - pe_offset)) if x > -999 else -99999.0
                    )
                    logger.info(f"PE trend normalization: subtracted offset={pe_offset:.1f} from {pe_col_name}, "
                               f"new median={data.loc[data[pe_col_name] > -999, pe_col_name].median():.2f}")
            
            # ========== 前置步骤：自动检测GR基线并计算相对GR ==========
            logger.info("Pre-step: Automatic GR baseline detection and relative GR calculation")
            gr_baseline = self.detect_gr_baseline(data)
            data['GR_REL'] = data['GR'] / gr_baseline
            
            # ========== 自适应骨架更新：根据本井纯净砂层动态调整石英骨架密度 ==========
            logger.info("Pre-step: Adaptive skeleton update based on pure sand intervals")
            den_col = None
            for name in ['DEN', 'RHOB']:
                if name in data.columns:
                    den_col = name
                    break
            
            pe_col = None
            for name in ['PE', 'PEF']:
                if name in data.columns:
                    pe_col = name
                    break
            
            rt_col = None
            for name in ['RT', 'LLD', 'AT90', 'AT60', 'M2RX', 'ILD', 'RDEEP']:
                if name in data.columns:
                    rt_col = name
                    break
            
            if den_col and pe_col and rt_col:
                pure_sand_mask = (data['GR_REL'] < 0.4) & (data[pe_col] < 2.8) & (data[rt_col] < 80)
                if pure_sand_mask.sum() > 10:
                    actual_sand_density = data.loc[pure_sand_mask, den_col].mean()
                    if 2.50 < actual_sand_density < 2.70:
                        old_density = self.params['Quartz'][0]
                        self.params['Quartz'][0] = actual_sand_density
                        logger.info(f"自适应骨架更新：石英密度从 {old_density:.3f} 调整为 {actual_sand_density:.3f} g/cm3")
            
            # ========== 第一层：深度分段判别（使用滑动窗口+K-means聚类）==========
            logger.info("Layer 1: Depth segment classification using sliding window + K-means")
            
            # 使用SegmentClassifier进行深度分段判别
            segment_classifier = SegmentClassifier(well_name=well_name)
            local_profile_type = segment_classifier.segment_classification(data)
            data['LOCAL_PROFILE_TYPE'] = local_profile_type
            
            carbonate_segment_count = (local_profile_type == 'carbonate').sum()
            sand_shale_segment_count = (local_profile_type == 'sand_shale').sum()
            mixed_segment_count = (local_profile_type == 'mixed').sum()
            logger.info(f"深度分段判别结果：碳酸盐岩段 {carbonate_segment_count} 个，砂泥岩段 {sand_shale_segment_count} 个，混合段 {mixed_segment_count} 个")
            
            # ========== 第二层：交汇图分析确定剖面类型（砂泥岩/碳酸盐岩/火成岩）==========
            logger.info("Layer 2: Crossplot analysis to determine profile type")
            crossplot_analyzer = LithologyCrossplotAnalyzer()
            crossplot_result = crossplot_analyzer.run_crossplot_analysis(data)
            
            main_lithology = crossplot_result['main_lithology']
            estimated_skeleton = crossplot_result['estimated_skeleton']
            
            logger.info(f"Main lithology types identified: {main_lithology}")
            logger.info(f"Estimated skeleton parameters: {estimated_skeleton}")
            
            # 基于交汇图结果确定剖面类型
            # ========== 优先使用交汇图分析结果（专家分析）==========
            has_sand_shale = 'sandstone' in main_lithology or 'shale' in main_lithology
            has_carbonate = 'limestone' in main_lithology or 'dolomite' in main_lithology
            
            # 初始判定：根据交汇图分析结果
            if has_sand_shale and not has_carbonate:
                profile_type = 'sand_shale'
                logger.info(f"交汇图判定：纯砂泥岩剖面，主要岩性 {main_lithology}")
            elif has_carbonate and not has_sand_shale:
                profile_type = 'carbonate'
                logger.info(f"交汇图判定：纯碳酸盐岩剖面，主要岩性 {main_lithology}")
            else:
                profile_type = 'mixed'
                logger.info(f"交汇图判定：混合剖面，主要岩性 {main_lithology}")
            
            # 将剖面类型存入data.attrs，供下游模块使用（特殊岩性检测、解释等）
            data.attrs['profile_type'] = profile_type
            data.attrs['main_lithology'] = main_lithology
            
            # 查询知识库，加载与当前剖面类型相关的解释经验
            knowledge_context = self.query_knowledge_base(profile_type, well_name)
            data.attrs['knowledge_context'] = knowledge_context
            
            # 特殊岩性图版分析（火成岩等）
            special_analyzer = SpecialLithologyPlateAnalyzer()
            tas_result = special_analyzer.analyze_tas_plate(data)
            pqf_result = special_analyzer.analyze_pqf_plate(data)
            
            has_volcanic = False
            if tas_result:
                logger.info(f"Volcanic rock identified: {tas_result['volcanic_type']}")
                has_volcanic = True
            
            # 结合密度和电阻率数据确认剖面类型（使用大段判断逻辑）
            density_col = None
            rt_col = None
            for name in ['RHOB', 'DEN']:
                if name in data.columns:
                    density_col = name
                    break
            for name in ['RT', 'LLD', 'ILD', 'AT90', 'AT60', 'M2RX', 'RDEEP']:
                if name in data.columns:
                    rt_col = name
                    break
            
            # PE-based carbonate override: PE > 3.5 is a strong carbonate indicator
            # This is critical for carbonate wells with moderate resistivity (e.g., deep water Brazil presalt)
            # ========== 密度一致性校验 + 井级别PE质量检测 ==========
            # 碳酸盐岩特征：PE高 + 密度高(>2.60) + PE质量合格，三者缺一不可
            # 仅PE高但密度低（<2.45）是砂泥岩剖面PE异常（仪器偏移），不应判为碳酸盐岩
            pe_col = None
            for name in ['PE', 'PEF']:
                if name in data.columns:
                    pe_col = name
                    break
            if pe_col and not has_carbonate:
                # ========== 井级别PE质量检查：PE不合格则直接跳过override ==========
                if not self.pe_quality.get('pe_reliable', True):
                    logger.info(f"PE override skipped: PE curve flagged as unreliable ({self.pe_quality.get('reason', 'unknown')})")
                else:
                    valid_pe = data[pe_col].dropna()
                    valid_pe = valid_pe[valid_pe > -999]  # filter null values
                    if len(valid_pe) > 100:
                        pe_carbonate_ratio = (valid_pe > 3.5).sum() / len(valid_pe)
                        if pe_carbonate_ratio > 0.5:
                            # ========== 密度物理约束校验 ==========
                            # 只有当密度也支持碳酸盐岩时才触发PE override
                            # 如果全井密度中位数<2.60，PE高很可能是仪器校准问题而非真实碳酸盐岩
                            den_supports_carbonate = True
                            if density_col:
                                den_vals = data[density_col].dropna()
                                den_vals = den_vals[den_vals > 0]
                                if len(den_vals) > 100:
                                    den_med = den_vals.median()
                                    den_high = (den_vals > 2.60).sum() / len(den_vals)
                                    # 密度不支持碳酸盐岩：中位数<2.55且>2.60占比<20%
                                    # 典型砂泥岩密度范围2.10-2.45，致密砂岩最高约2.68
                                    if den_med < 2.55 and den_high < 0.20:
                                        den_supports_carbonate = False
                                        logger.warning(
                                            f"PE anomaly detected but density rejects carbonate: "
                                            f"PE>3.5 in {pe_carbonate_ratio*100:.1f}% BUT DEN median={den_med:.3f}<2.55, "
                                            f"DEN>2.60 only {den_high*100:.1f}%. PE values may be miscalibrated. "
                                            f"Skipping PE override, keeping sand-shale profile."
                                        )
                            if den_supports_carbonate:
                                has_carbonate = True
                                logger.info(f"PE carbonate override: PE>3.5 in {pe_carbonate_ratio*100:.1f}% of points, density confirms carbonate, forcing carbonate detection")
                                if 'limestone' not in main_lithology:
                                    main_lithology.append('limestone')
            
            # ========== 密度强约束：密度中位数>2.70大概率是碳酸盐岩 ==========
            # 砂岩密度约2.65，即使致密砂岩也很少超过2.68
            # 密度中位数>2.70几乎可以排除纯砂泥岩剖面
            if density_col and not has_carbonate:
                valid_den = data[density_col].dropna()
                valid_den = valid_den[valid_den > 0]
                if len(valid_den) > 100:
                    den_median = valid_den.median()
                    den_high_ratio = (valid_den > 2.68).sum() / len(valid_den)
                    if den_median > 2.70 or den_high_ratio > 0.5:
                        has_carbonate = True
                        logger.info(f"密度强约束：密度中位数={den_median:.3f}，>2.68占比={den_high_ratio*100:.1f}%，强制检测碳酸盐岩")
                        if 'limestone' not in main_lithology:
                            main_lithology.append('limestone')
            
            if density_col and rt_col:
                valid_density = data[density_col].dropna()
                valid_rt = data[rt_col].dropna()
                
                if len(valid_density) > 0 and len(valid_rt) > 0:
                    # 使用滑动窗口进行大段判断
                    window_size = 50
                    density_vals = data[density_col].values
                    rt_vals = data[rt_col].values
                    
                    sand_shale_segment_count = 0
                    carbonate_segment_count = 0
                    total_segments = max(1, len(data) // window_size)
                    
                    for i in range(0, len(data), window_size):
                        end_idx = min(i + window_size, len(data))
                        win_density = density_vals[i:end_idx]
                        win_rt = rt_vals[i:end_idx]
                        
                        valid_ratio = (win_density > 0).sum() / len(win_density)
                        if valid_ratio < 0.5:
                            continue
                        
                        # 砂泥岩段特征：密度>2.45（最低岩石密度）且电阻率<100
                        is_sand_shale_segment = (win_density > 2.45).sum() / len(win_density) > 0.5 and \
                                               (win_rt < 100).sum() / len(win_rt) > 0.5
                        
                        # 碳酸盐岩段特征：密度>2.65（接近灰岩骨架密度）且电阻率>100
                        is_carbonate_segment = (win_density > 2.65).sum() / len(win_density) > 0.5 and \
                                               (win_rt > 100).sum() / len(win_rt) > 0.5
                        
                        if is_sand_shale_segment:
                            sand_shale_segment_count += 1
                        elif is_carbonate_segment:
                            carbonate_segment_count += 1
                    
                    # 大段统计结果（仅作为混合剖面时的参考，不覆盖交汇图分析结果）
                    sand_shale_ratio = sand_shale_segment_count / total_segments
                    carbonate_ratio = carbonate_segment_count / total_segments
                    
                    # 只有当交汇图判定为混合剖面时，才使用大段统计进行细分
                    if profile_type == 'mixed':
                        if carbonate_ratio > 0.5:
                            profile_type = 'carbonate'
                            logger.info(f"大段统计修正：混合剖面→碳酸盐岩剖面（碳酸盐岩段占比 {carbonate_ratio:.2f}）")
                        elif sand_shale_ratio > 0.5:
                            profile_type = 'sand_shale'
                            logger.info(f"大段统计修正：混合剖面→砂泥岩剖面（砂泥岩段占比 {sand_shale_ratio:.2f}）")
                        else:
                            profile_type = 'mixed'
                            logger.info(f"大段统计确认：混合剖面（砂泥岩段占比 {sand_shale_ratio:.2f}, 碳酸盐岩段占比 {carbonate_ratio:.2f}）")
                    else:
                        # 交汇图已明确判定，大段统计只作为参考
                        logger.info(f"交汇图已判定为{profile_type}剖面，大段统计参考：砂泥岩占比 {sand_shale_ratio:.2f}, 碳酸盐岩占比 {carbonate_ratio:.2f}")
                        # ========== 密度物理约束覆盖 ==========
                        # 当交汇图判为砂泥岩，但滑动窗口检测到明显碳酸盐岩段，
                        # 且密度中位数>2.68（超过砂泥岩范围），强制修正为混合剖面
                        # 解决3-SPS-111D井AC=60导致DEN-AC交会图误判砂岩的问题
                        den_med = np.median(density_vals[density_vals > 0]) if len(density_vals[density_vals > 0]) > 0 else 2.65
                        if profile_type == 'sand_shale' and carbonate_ratio > 0.3 and den_med > 2.68:
                            profile_type = 'mixed'
                            logger.info(f"密度物理约束修正：砂泥岩→混合剖面（DEN中位数={den_med:.3f}>2.68, 碳酸盐岩段占比={carbonate_ratio:.2f}>0.3）")
                    
                    logger.info(f"最终剖面类型判定：{profile_type}")
            else:
                if has_sand_shale and not has_carbonate:
                    profile_type = 'sand_shale'
                elif has_carbonate and not has_sand_shale:
                    profile_type = 'carbonate'
            
            # ========== 第二层：最优化方法计算矿物含量（基于剖面类型）==========
            # ========== 预检测：LAS文件中是否已有SLB预计算的矿物体积 ==========
            # 如果数据中有 VOL_CALCITE, VOL_DOLOM, VOL_ANHY, VOL_BASALT 等列
            # 并且这些列有正常的变化（非全零/非恒定值），则直接使用
            vol_columns_map = {
                'VOL_CALCITE': 'Calcite',   # 灰岩
                'VOL_DOLOM': 'Dolomite',    # 白云岩
                'VOL_ANHY': 'Anhydrite',    # 硬石膏
                'VOL_BASALT': 'Basalt',     # 玄武岩
            }
            # 检测LAS矿物体积是否有效
            use_las_volumes = False
            available_vol_cols = [c for c in vol_columns_map if c in data.columns]
            if available_vol_cols:
                # 验证有效性：每列需要有正常变化（std > 0.01 且 非全零）
                valid_count = 0
                for col in available_vol_cols:
                    col_data = data[col].dropna()
                    if len(col_data) > 10:
                        std_val = col_data.std()
                        max_val = col_data.max()
                        if std_val > 0.01 and max_val > 0.001:
                            valid_count += 1
                        else:
                            logger.info(f"LAS矿物体积 {col} 无效（std={std_val:.6f}, max={max_val:.6f}），不使用")
                
                if valid_count >= 2:  # 至少2列有效
                    use_las_volumes = True
                    logger.info(f"检测到有效LAS预计算矿物体积: {available_vol_cols}（有效{valid_count}/{len(available_vol_cols)}列）")
                else:
                    logger.info(f"LAS矿物体积有效列不足（{valid_count}/{len(available_vol_cols)}），使用最优化计算")
            
            if use_las_volumes:
                # 直接使用LAS预计算矿物体积，映射到内部 V{Mineral} 格式
                logger.info("Layer 2: Using LAS precomputed mineral volumes (skipping optimization)")
                all_minerals = ['Quartz', 'Calcite', 'Dolomite', 'Anhydrite', 'Halite', 'Clay']
                
                # 初始化所有矿物为0
                for mineral in all_minerals:
                    data[f'V{mineral}'] = 0.0
                
                # 映射LAS矿物体积
                mineral_col_to_las = {
                    'Calcite': 'VOL_CALCITE',
                    'Dolomite': 'VOL_DOLOM',
                    'Anhydrite': 'VOL_ANHY',
                }
                las_vol_sum = np.zeros(len(data))
                for mineral, las_col in mineral_col_to_las.items():
                    if las_col in data.columns:
                        vol = data[las_col].fillna(0).clip(0, 1).values
                        data[f'V{mineral}'] = vol
                        las_vol_sum += vol
                        logger.info(f"  {mineral}: 来自 {las_col}, 均值={vol.mean():.4f}, 最大值={vol.max():.4f}")
                
                # 玄武岩映射
                if 'VOL_BASALT' in data.columns:
                    basalt_vol = data['VOL_BASALT'].fillna(0).clip(0, 1).values
                    data['VBasalt'] = basalt_vol
                    las_vol_sum += basalt_vol
                    logger.info(f"  Basalt: 来自 VOL_BASALT, 均值={basalt_vol.mean():.4f}, 最大值={basalt_vol.max():.4f}")
                
                # 剩余体积分配给石英（Quartz）和粘土（Clay）
                # 用GR判断泥质含量，剩余为石英
                remaining = 1.0 - las_vol_sum
                remaining = np.clip(remaining, 0, 1)
                
                # 从GR计算泥质含量（只使用正常测量值，排除-9999等异常值）
                if 'GR' in data.columns:
                    gr = data['GR'].values
                    gr_valid = gr[(gr > 0) & (gr < 500)]
                    gr_min = np.nanmin(gr_valid) if len(gr_valid) > 0 else 0
                    gr_max = np.nanmax(gr_valid) if len(gr_valid) > 0 else 200
                    if gr_max > gr_min:
                        vsh_from_gr = np.clip((gr - gr_min) / (gr_max - gr_min), 0, 1)
                    else:
                        vsh_from_gr = np.zeros(len(data))
                else:
                    vsh_from_gr = np.zeros(len(data))
                
                # Clay = min(vsh_from_GR, remaining)
                data['VClay'] = np.minimum(vsh_from_gr, remaining)
                # Quartz = remaining - Clay
                data['VQuartz'] = np.clip(remaining - data['VClay'].values, 0, 1)
                
                # 归一化：确保所有矿物含量+孔隙度之和=1
                # 包含 VBasalt 在内的所有矿物列
                mineral_cols_for_norm = [f'V{m}' for m in all_minerals]
                if 'VBasalt' in data.columns:
                    mineral_cols_for_norm.append('VBasalt')
                mineral_cols_for_norm = [c for c in mineral_cols_for_norm if c in data.columns]
                
                total_minerals = np.zeros(len(data))
                for col in mineral_cols_for_norm:
                    total_minerals += data[col].fillna(0).values
                
                mask = total_minerals > 0
                for col in mineral_cols_for_norm:
                    data.loc[mask, col] = data.loc[mask, col] / total_minerals[mask]
                
                logger.info(f"LAS矿物体积使用完成: VCalcite均值={data['VCalcite'].mean():.4f}, VDolomite均值={data['VDolomite'].mean():.4f}, VAnhydrite均值={data['VAnhydrite'].mean():.4f}, VQuartz均值={data['VQuartz'].mean():.4f}, VClay均值={data['VClay'].mean():.4f}" + 
                           (f", VBasalt均值={data['VBasalt'].mean():.4f}" if 'VBasalt' in data.columns else ""))
            else:
                logger.info(f"Layer 2: Optimizing mineral content for {profile_type} profile")
                data = self.optimize_minerals(data, profile_type=profile_type)
            
            # ========== 计算 VSH（泥质含量）用于非储层段识别和解释引擎 ==========
            # 注意：optimize_minerals 只在异常回退路径中调用 calculate_vsh，
            # 正常优化成功路径中不创建 VSH 列，需要在此显式计算
            if 'VSH' not in data.columns:
                vsh_method = self.config.get('vsh_method', 3)
                data = self.calculate_vsh(data, vsh_method)
                logger.info(f"计算 VSH 完成（方法{vsh_method}），VSH 范围: {data['VSH'].min():.4f}-{data['VSH'].max():.4f}")
            
            # ========== 非储层段孔隙度归0和矿物含量重新分配 ==========
            # 在饱和度计算之前执行，确保饱和度计算使用正确的孔隙度值
            # 规则：非储层段（特殊岩性、泥岩）PHI=0，矿物含量重新分配使sum(minerals)=1.0
            logger.info("应用非储层段孔隙度归0规则...")
            data = self.apply_non_reservoir_phi_zeroing(data)
            
            data = self.calculate_saturation(data)
            
            # ========== 第三层：交汇图迭代核验（深度级别）==========
            logger.info("Layer 3: Crossplot iteration verification (depth level)")
            # 使用计算出的矿物含量和测井值进行深度级别的交汇图核验
            crossplot_analyzer2 = LithologyCrossplotAnalyzer()
            crossplot_result2 = crossplot_analyzer2.run_crossplot_analysis(data)
            
            depth_lithology = crossplot_result2.get('depth_lithology', {})
            if depth_lithology:
                logger.info(f"交汇图迭代核验完成，修正了 {len(depth_lithology)} 个深度点的岩性")
            
            # 更新骨架参数为迭代后的结果
            estimated_skeleton.update(crossplot_result2.get('estimated_skeleton', {}))
            main_lithology = list(set(main_lithology + crossplot_result2.get('main_lithology', [])))
            
            # ========== 第四层：综合岩性判断（基于剖面类型 + 最优化结果 + 交汇图核验 + 特征值）==========
            logger.info("Layer 4: Comprehensive lithology classification with iteration")
            
            # ========== 特殊矿物检测函数（在常规岩性分类之前执行） ==========
            # 特殊矿物：盐岩(Halite)、石膏(Gypsum)、硬石膏(Anhydrite)、煤层(Coal)、黄铁矿(Pyrite)
            # 这些矿物具有非常规测井响应特征，与常规砂泥岩/碳酸盐岩明显不同
            # 单独检测并标识，避免与常规岩性混淆
            
            # 读取井级别信息，供特殊矿物检测使用
            _well_profile_type = data.attrs.get('profile_type', 'mixed')
            _hole_quality = data.attrs.get('hole_quality', {})
            _bad_hole_mask = _hole_quality.get('bad_mask', pd.Series(False, index=data.index))
            _extreme_hole_mask = _hole_quality.get('extreme_mask', pd.Series(False, index=data.index))
            _skip_coal = (_well_profile_type == 'sand_shale')  # 砂泥岩剖面不会有煤层
            
            # ========== 蒸发岩沉积环境综合评估 ==========
            # 综合考虑沉积环境、岩性、测井响应三个维度
            # 蒸发岩只可能出现在局限海台地、潟湖、盐湖等高度蒸发封闭环境
            # 河道/三角洲/泛滥平原等碎屑岩沉积环境不会沉积蒸发岩
            
            # 井级别剖面类型标识（用于阈值严格程度调节，不绝对跳过）
            _skip_evaporite = (_well_profile_type == 'sand_shale')  # 砂泥岩剖面蒸发岩可能性低
            
            # 井级别基础蒸发岩环境得分（0=绝不可能是蒸发岩环境, 1=完全可能是蒸发岩环境）
            # 不绝对跳过：即使砂泥岩剖面，如果物理证据充分（大段密度2.85+低阻+低GR=硬石膏，
            # 大段密度<2.2+低阻+扩径=盐岩），仍可认定特殊岩性
            _evaporite_env_base = 0.5  # 默认中性
            if _well_profile_type == 'sand_shale':
                _evaporite_env_base = 0.05  # 砂泥岩剖面基础分极低，阈值会很严格
            elif _well_profile_type == 'carbonate':
                _evaporite_env_base = 0.6  # 碳酸盐岩剖面可能伴生蒸发岩
            # 全井统计辅助调整基础得分
            rt_median = data['RT'].median() if 'RT' in data.columns else (
                data['LLD'].median() if 'LLD' in data.columns else 50)
            den_median = data['RHOB'].median() if 'RHOB' in data.columns else (
                data['DEN'].median() if 'DEN' in data.columns else 2.65)
            if rt_median < 100 and den_median < 2.50:
                _evaporite_env_base = min(_evaporite_env_base, 0.05)  # 典型砂泥岩
            elif rt_median < 200 and den_median < 2.60:
                _evaporite_env_base = min(_evaporite_env_base, 0.15)  # 偏砂泥岩
            elif rt_median > 500 and den_median > 2.70:
                _evaporite_env_base = max(_evaporite_env_base, 0.7)  # 碳酸盐岩+高阻
            
            # VSH列可用性检查（用于逐点沉积环境评估）
            _has_vsh = 'VSH' in data.columns
            
            # 井段顶部深度范围（用于水泥块等非地层特征检测）
            # 水泥块只出现在套管鞋附近（刚出套管），在有效测井数据起点以下50米范围内
            # 有效数据定义：GR/DEN/RT/NPHI/AC等常用曲线中，非-999且非NaN的曲线>=3条
            _cement_top_min = 0  # 水泥块检测起始深度（动态计算）
            _cement_top_max = 50  # 水泥块检测结束深度（相对起始点+50m）
            
            # 计算有效曲线数量（排除-999和NaN）
            _curve_cols = []
            for col in ['GR', 'RHOB', 'DEN', 'LLD', 'RT', 'NPHI', 'CNL', 'DT', 'AC', 'PE', 'PEF']:
                if col in data.columns:
                    # 检查是否有有效值（排除-999和NaN）
                    valid_count = data[col].replace(-999, np.nan).notna().sum()
                    if valid_count > len(data) * 0.1:  # 至少10%有效
                        _curve_cols.append(col)
            
            if len(_curve_cols) >= 3:
                # 计算每个深度点的有效曲线数
                _valid_count_matrix = data[_curve_cols].replace(-999, np.nan).notna().sum(axis=1)
                # 找到第一个有效曲线数>=3的深度
                _valid_mask = _valid_count_matrix >= 3
                if _valid_mask.any():
                    _first_valid_idx = _valid_mask.idxmax()  # 第一个True的索引
                    _first_valid_depth = data.loc[_first_valid_idx, 'MD'] if 'MD' in data.columns else _first_valid_idx
                    _cement_top_min = _first_valid_depth
                    _cement_top_max = _first_valid_depth + 50
                    logger.info(f"水泥块检测范围: 深度 {_cement_top_min:.1f}m - {_cement_top_max:.1f}m "
                               f"(有效曲线起点={_first_valid_depth:.1f}m, 有效曲线数={len(_curve_cols)})")
                else:
                    logger.info("水泥块检测：无有效数据点（有效曲线>=3条），跳过水泥块检测")
                    _cement_top_max = 0  # 无有效数据，不检测水泥块
            else:
                logger.info(f"水泥块检测：有效曲线不足3条（{len(_curve_cols)}条），跳过水泥块检测")
                _cement_top_max = 0  # 有效曲线不足，不检测水泥块
            
            def _compute_evaporite_env_score(row):
                """
                综合评估该深度点是否处于可能沉积蒸发岩的环境
                
                综合三个维度：
                1. 沉积环境：GR值+VSH → 判断河道/三角洲/泛滥平原（碎屑岩沉积）vs 局限海/潟湖（蒸发岩）
                2. 岩性上下文：密度-声波交汇 → 判断该点是砂岩/泥岩还是可能的蒸发岩
                3. 测井响应一致性：各测井参数是否自洽地指向蒸发岩
                
                返回: 0.0-1.0 的得分
                  < 0.15: 几乎确定不是蒸发岩环境（典型河道砂岩/泛滥平原泥岩）
                  0.15-0.35: 不太可能是蒸发岩环境（碎屑岩沉积为主）
                  0.35-0.60: 不确定，需要强测井证据
                  0.60-0.80: 可能是蒸发岩环境（低GR+碳酸盐岩特征）
                  > 0.80: 很可能是蒸发岩环境（所有指标一致）
                """
                score = _evaporite_env_base
                gr = row.get('GR', 50)
                density = row.get('RHOB', row.get('DEN', 2.65))
                ac = row.get('DTCO', row.get('DT', row.get('AC', 55.5)))
                rt = row.get('AT90', row.get('LLD', row.get('RT', 50)))
                vsh = row.get('VSH', 0.5) if _has_vsh else 0.5
                nphi = row.get('NPHI', row.get('CNL', 0))
                cal = row.get('CAL', row.get('CALS', 8.5))
                bit = row.get('BIT', 8.5)
                cal_ratio = cal / max(bit, 0.1) if bit > 0 else 1.0
                
                # ========== 盐岩特征优先识别 ==========
                # 盐岩的不可替代特征：密度1.65-2.40 + 声波62-73 + 中子-8~8
                # 三个核心指标同时命中，几乎可以确定是盐岩（或蒸发岩环境）
                # 即使GR偏高（泥质夹层）、电阻率偏高（深电阻率饱和），
                # 只要密度+声波+中子三个核心指标一致，就应该识别为蒸发岩环境
                if (1.65 <= density < 2.40 and 
                    62 <= ac <= 73 and 
                    -8 <= nphi <= 8):
                    return max(score, 0.8)  # 盐岩特征明确，直接返回高环境得分
                
                # ---- 维度1：沉积环境（GR + VSH → 沉积相判别）----
                # 河道/水下分流河道：低GR + 低VSH → 碎屑岩沉积，无蒸发岩
                if gr < 50 and vsh < 0.3:
                    score *= 0.15  # 强惩罚：典型河道沉积
                elif gr < 70 and vsh < 0.4:
                    score *= 0.3  # 中等惩罚：可能是河道边缘或河口坝
                elif gr > 130 and vsh > 0.5:
                    score *= 0.2  # 泛滥平原/泥坪，泥质沉积为主
                elif gr > 100 and vsh > 0.4:
                    score *= 0.4  # 过渡带/天然堤
                elif 50 <= gr <= 100 and 0.3 <= vsh <= 0.5:
                    score *= 0.6  # 中等GR+中等VSH，可能是局限海
                # 低GR + 低VSH + 高RT → 可能是碳酸盐岩台地/潟湖
                elif gr < 40 and vsh < 0.2 and rt > 200:
                    score = max(score, 0.6)  # 提升：可能是局限海台地
                
                # ---- 维度2：岩性上下文（密度-声波交汇 → 判断砂岩vs蒸发岩）----
                # 砂岩特征区域：密度2.40-2.70 + 声波50-80
                if 2.40 < density < 2.70 and 50 < ac < 80:
                    score *= 0.3  # 典型砂岩DEN-AC区域，大幅降低蒸发岩可能性
                elif density < 2.40 and ac > 65:
                    # 低密度+高声波 → 高孔隙度砂岩（不是盐岩，盐岩AC~67但密度~2.03）
                    score *= 0.4
                elif density > 2.85 and ac < 55:
                    # 高密度+低声波 → 硬石膏/致密碳酸盐岩区域
                    score = max(score, 0.5)  # 提升：可能是蒸发岩
                
                # ---- 维度3：测井响应一致性 ----
                # 如果密度和声波互相矛盾（如低密度但高声波=砂岩，不是盐岩），降低得分
                if density < 2.40 and ac > 75:
                    # 低密度+高声波 → 高孔隙度砂岩或井眼影响，不是盐岩
                    score *= 0.3
                if density < 2.50 and ac > 70 and rt > 100:
                    # 低密度+高声波+高阻 → 可能是致密砂岩/气层，不是蒸发岩
                    score *= 0.4
                
                return max(0.0, min(1.0, score))
            
            def detect_special_mineral(row):
                """
                检测特殊矿物，返回 (special_mineral_type, score, reason)
                如果未检测到特殊矿物，返回 (None, 0, '')
                
                **核心原则：特殊矿物是近纯矿物，各参数必须同时落入紧密窗口，单参数宽松决不允许触发**
                
                检测顺序：
                1. 煤层 Coal —— 密度<1.6 + 声波>105 + 中子>40（三项必须同时满足）
                2. 黄铁矿 Pyrite —— 密度>3.5 + PE>10（必须同时满足）
                3. 盐岩 Halite —— 4个核心条件直接命中：密度1.65-2.50 + 中子-8~8 + 扩径>1.03 + (低阻rt_min<50或低GR<100)
                4. 石膏 Gypsum —— 密度2.20-2.45 + 中子>35(结晶水) + 声波45-60 + 低GR
                5. 硬石膏 Anhydrite —— 密度>2.80 + 声波<55 + 低GR（必须同时满足）
                
                各矿物标准参数（用于对比）：
                - 盐岩：密度2.03, AC 67, 中子~0, 低GR, 低阻, 扩径
                - 石膏：密度2.32, AC 52, 中子~49, PE 3.99, 低GR
                - 硬石膏：密度2.98, AC 50, PE 5.0, 低GR
                - 煤：密度<1.6, AC>105, 中子>40
                - 黄铁矿：密度5.0, PE>15
                
                严防误判：砂泥岩孔隙度20%时密度=2.12，与盐岩(2.03)接近但声波完全不同(砂岩AC高得多)
                """
                # 提取测井值
                density = row.get('RHOB', row.get('DEN', 2.65))
                ac = row.get('DTCO', row.get('DT', row.get('AC', 55.5)))
                gr = row.get('GR', 50)
                pe = row.get('PE', row.get('PEF', 2.5))
                nphi = row.get('NPHI', row.get('CNL', 0))
                rt = row.get('AT90', row.get('LLD', row.get('RT', 50)))
                bit = row.get('BIT', 8.5)
                cal = row.get('CAL', row.get('CALS', bit))
                cal_ratio = cal / max(bit, 0.1) if bit > 0 else 1.0
                
                # 跳过无效数据
                if density <= 0 or np.isnan(density):
                    return (None, 0, '')
                
                # ========== 水泥块/非地层检测 (Unknown) ==========
                # 水泥掉块是井内非地层物质（固井水泥落入井筒），判断依据：
                #   1. 位置：位于井筒顶部，刚出套管（深度<600m或顶部200m范围内）
                #   2. 多曲线同时异常：PE>5.0(水泥含钙) + 低密度(<2.30) + 高中子(>30)
                #   3. 辅助特征：井径平直(刚出套管，水泥环内壁光滑)
                # 关键特征组合(PE>5.0+低密度+高中子)在正常地层中不存在：
                #   - 盐岩：低密度但低中子(-8~8)，PE不高
                #   - 煤：低密度+高中子但PE低(<2.0)
                #   - 石膏：密度中等(2.32)+高中子但PE~4.0，不满足PE>5.0
                #   - 高孔隙砂岩：密度低但PE<3.0，中子一般<30
                # 注意：水泥块电阻率不一定高，声波时差变化不一定小(如XIMENIA-5 DT均值128)
                # 关键是多曲线组合异常(PE>5.0+低密度+高中子)，且位于有效测井数据起点以下50m内
                # PE不可信时（如XIMENIA-5井PE受泥浆影响全井>8），跳过PE>5.0条件
                depth = row.get('MD', row.get('DEPT', row.get('DEPTH', 0)))
                pe_ok_for_cement = (self.pe_quality.get('pe_reliable', True) and
                                    not np.isnan(pe) and pe > 5.0)
                if (_cement_top_max > 0 and
                    _cement_top_min <= depth <= _cement_top_max and
                    pe_ok_for_cement and
                    density < 2.30 and density > 1.0 and
                    nphi > 30):
                    return ('unknown', 5,
                            f'水泥块(depth={depth:.0f}m, 范围{_cement_top_min:.0f}-{_cement_top_max:.0f}m)+PE({pe:.1f})>5.0+低密度({density:.2f})'
                            f'+高中子({nphi:.0f}PU),非地层特征(水泥块)')
                
                # ========== 盐岩检测 (Halite) ==========
                # 盐岩的不可替代特征由4个核心条件组成：
                #   1. 低密度 (~2.03)：密度窗口 1.65-2.50
                #   2. 低中子 (~0)：中子窗口 -8 到 8
                #   3. 扩径：井径比 > 1.03（盐岩总会引起一定扩径，即使轻微）
                #   4. 低电阻率 (rt_min < 50) 或 低GR (gr < 100)
                #
                # 核心原则：4个条件同时满足，直接判定为盐岩，无需评分。
                # 声波(~67)是辅助参考，不作为必要条件。
                #
                # 特别说明：严重扩径会导致密度测井读值偏低（<1.95），
                # 深电阻率可能饱和（~2000），但浅电阻率仍显示低阻，
                # 因此使用所有电阻率曲线的最小值判断低阻特征。
                # 密度窗口放宽至1.65-2.50，考虑扩径和杂质影响。
                # GR阈值放宽至100（原80），因为盐岩GR可受围岩影响而偏高。
                
                # 获取所有可用电阻率曲线的最小值，避免单条曲线饱和导致误判
                rt_cols = ['AT10', 'AT20', 'AT30', 'AT60', 'AT90',
                           'M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX',
                           'LLS', 'LLD', 'RT']
                rt_vals = []
                for col in rt_cols:
                    v = row.get(col, None)
                    if v is not None and v > 0 and not np.isnan(v) and v < 10000:
                        rt_vals.append(v)
                rt_min = min(rt_vals) if rt_vals else rt
                
                # 4个核心条件检查
                density_low = 1.65 <= density < 2.50  # 条件1：低密度
                neutron_low = -8 < nphi < 8            # 条件2：低中子
                hole_enlarge = cal_ratio > 1.03        # 条件3：扩径（盐岩总会引起一定扩径，>1.03即可）
                low_res_or_gr = rt_min < 50 or gr < 100 # 条件4：低阻或低GR（盐岩GR可高达100）
                
                # 4个条件全部满足 → 直接判定为盐岩
                if density_low and neutron_low and hole_enlarge and low_res_or_gr:
                    return ('halite', 10, 
                            f'密度({density:.2f})+中子({nphi:.1f})+扩径({cal_ratio:.2f})'
                            f'+{"低阻" if rt_min < 50 else "低GR"}({rt_min if rt_min < 50 else gr:.1f})')
                
                # 声波+中子联合排除：盐岩AC~67、中子~0，
                # 两者同时异常时绝对不是盐岩
                if ac > 78 and nphi > 5:
                    pass  # 声波+中子联合排除：不是盐岩
                
                # 扩径严重(>1.25)时，密度/中子/PE/声波均已失真，跳过其他特殊矿物检测
                if cal_ratio > 1.25:
                    return (None, 0, '')
                
                # ---- 1. 煤层检测 (Coal) ----
                # 煤的特征极其鲜明：密度<1.6、声波>105、中子>40，三者缺一不可
                # 关键排除规则：
                #   - 砂泥岩剖面（_skip_coal=True）完全跳过煤层检测
                #   - 扩径严重(>1.25)时密度/中子/声波失真，跳过检测
                #   - GR不受扩径影响（穿透深度15-20cm），扩径段高GR是因扩径常发生于泥岩段（泥岩GR天然高），
                #     不能用于排除煤（煤GR低-中但扩径本身不改变GR读数）
                #   - 煤不会引起高电阻率（煤导电，高阻=排除）——这是最可靠的排除条件
                #   - 密度<0.8是井底坏数据
                
                # 井级别跳过：砂泥岩剖面不会有煤
                if _skip_coal:
                    pass  # 跳过所有煤层检测
                elif density < 1.6 and density > 0.8:  # 密度<0.8是井底坏数据
                    # 排除规则：高电阻率 → 不是煤（煤导电，电阻率低；高阻是坏井眼/扩径失真）
                    if rt > 100:
                        return (None, 0, '')
                    # 排除规则：密度太低+扩径 → 可能是井底坏数据
                    if density < 1.0 and cal_ratio > 1.15:
                        return (None, 0, '')
                    
                    coal_score = 0
                    coal_reasons = []
                    coal_reasons.append(f'极低密度({density:.3f})')
                    coal_score += 2
                    
                    if ac > 105:
                        coal_score += 2
                        coal_reasons.append(f'高声波({ac:.0f}>105)')
                    elif ac > 95:
                        coal_score += 1
                    else:
                        coal_score -= 1  # 密度低但声波不够高 → 可能是坏点
                    
                    if nphi > 40:
                        coal_score += 2
                        coal_reasons.append(f'高中子({nphi:.0f}>40)')
                    elif nphi > 35:
                        coal_score += 1
                    
                    # 煤的特征：低电阻率（导电）、低-中GR
                    if rt < 50:
                        coal_score += 1
                        coal_reasons.append('低电阻率')
                    
                    if gr < 80:
                        coal_score += 1
                    
                    if cal_ratio > 1.1:
                        coal_score += 1
                        coal_reasons.append(f'扩径({cal_ratio:.2f})')
                    
                    if coal_score >= 5:
                        return ('coal', coal_score, '; '.join(coal_reasons))
                
                # ---- 2. 黄铁矿检测 (Pyrite) ----
                # 黄铁矿密度>3.5 + PE>10，两者缺一不可
                # 密度>3.5本身排除所有常见沉积岩（石英2.65、灰岩2.71、白云石2.87、硬石膏2.98）
                if density > 3.5 and (not np.isnan(pe)) and pe > 10:
                    pyrite_reasons = [f'极高密度({density:.2f})+极高PE({pe:.1f})']
                    pyrite_score = 5
                    if ac < 50 and ac > 30:
                        pyrite_score += 1
                        pyrite_reasons.append(f'低声波({ac:.0f})')
                    if gr < 30:
                        pyrite_score += 1
                        pyrite_reasons.append(f'低GR({gr:.0f})')
                    if pyrite_score >= 5:
                        return ('pyrite', pyrite_score, '; '.join(pyrite_reasons))
                
                # ---- 4. 石膏检测 (Gypsum) [CaSO₄·2H₂O] ----
                # 标准值：密度2.32, AC 52, 中子~49(结晶水), PE 3.99, 低GR
                # 关键区分特征：密度中等+中子极高（其他矿物没有这个组合）
                # 砂泥岩中子一般为中等(5-25)，不会>35，因此中子>35是石膏的强区分特征
                # 综合判断：沉积环境+密度-中子交汇+声波+GR
                # 不绝对跳过：即使砂泥岩剖面，如果中子>35+密度2.2-2.45+低GR，仍可能是石膏
                env_score_gyp = _compute_evaporite_env_score(row)
                if (density > 2.20 and density < 2.45 and  # 密度窗口 ±0.12
                    nphi > 35 and                           # 必须极高中子（结晶水）
                    ac > 45 and ac < 60 and                 # 声波窗口 ±7.5
                    gr < 50):                               # 低GR（蒸发岩）
                    gypsum_score = 4  # 核心四项命中=4分（阈值=4）
                    gypsum_reasons = [
                        f'密度({density:.2f})≈2.32',
                        f'极高中子({nphi:.0f}PU,结晶水)',
                        f'声波({ac:.0f})≈52',
                        f'低GR({gr:.0f})',
                    ]
                    
                    # PE确认（石膏PE=3.99，但PE不一定可靠）
                    if not np.isnan(pe) and pe > 3.5 and pe < 4.5:
                        gypsum_score += 1
                        gypsum_reasons.append(f'PE({pe:.1f})≈3.99')
                    
                    if rt < 50:
                        gypsum_score += 0.5
                        gypsum_reasons.append('低电阻率')
                    
                    if cal_ratio > 1.05:
                        gypsum_score += 0.5
                    
                    # 沉积环境得分影响石膏确认阈值
                    #   env_score > 0.5 → 阈值3.5（环境支持）
                    #   env_score 0.2-0.5 → 阈值4.0（环境一般）
                    #   env_score < 0.2 → 阈值5.5（环境不利，需要更强证据）
                    gypsum_threshold = 4.0
                    if env_score_gyp > 0.5:
                        gypsum_threshold = 3.5
                    elif env_score_gyp < 0.2:
                        gypsum_threshold = 5.5
                    
                    # 环境得分辅助评分
                    if env_score_gyp > 0.5:
                        gypsum_score += 0.5
                        gypsum_reasons.append(f'沉积环境支持({env_score_gyp:.2f})')
                    elif env_score_gyp < 0.2:
                        gypsum_score -= 1.0
                        gypsum_reasons.append(f'沉积环境不利({env_score_gyp:.2f})')
                    
                    if gypsum_score >= gypsum_threshold:
                        return ('gypsum', gypsum_score, '; '.join(gypsum_reasons))
                
                # ---- 5. 硬石膏检测 (Anhydrite) [CaSO₄] ----
                # 标准值：密度2.98, AC 50, PE 5.0, 低GR
                # 
                # 综合判断框架（沉积环境+岩性+测井响应）：
                #   不绝对跳过：即使砂泥岩剖面，如果大段密度~2.85+低阻+低GR+低中子，
                #   仍应识别为硬石膏。环境得分只影响阈值严格程度。
                #
                #   综合判断逻辑：
                #     1. 密度 > 2.85 硬约束（超过所有砂泥岩和灰岩）
                #     2. 电阻率 > 100 硬约束（致密无孔，高阻）
                #     3. 环境得分影响确认阈值（而非绝对跳过）
                #     4. 密度-声波交汇确认（排除砂岩可能性）
                anhydrite_score = 0
                anhydrite_reasons = []
                env_score_anh = _compute_evaporite_env_score(row)
                
                if density <= 2.85:
                    pass  # 密度不够高，不可能是硬石膏（可能是受井眼影响的砂岩）
                elif rt < 100:
                    pass  # 电阻率不够高，硬石膏致密无孔应高阻
                else:
                    # 核心条件已满足（密度>2.85 + 高阻），开始评分
                    # 核心条件1：高密度（硬石膏密度2.98）
                    if density > 2.90:
                        anhydrite_score += 2
                        anhydrite_reasons.append(f'高密度({density:.2f})>2.90')
                    else:
                        anhydrite_score += 1.5
                        anhydrite_reasons.append(f'密度({density:.2f})>2.85')
                    
                    # 核心条件2：低声波（硬石膏AC约50）
                    if ac < 50:
                        anhydrite_score += 1.5
                        anhydrite_reasons.append(f'低声波({ac:.0f})<50')
                    elif ac < 55:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'中声波({ac:.0f})<55')
                    elif ac < 60:
                        anhydrite_score += 0.5
                    
                    # 核心条件3：低GR（蒸发岩特征）
                    if gr < 40:
                        anhydrite_score += 1.5
                        anhydrite_reasons.append(f'低GR({gr:.0f})')
                    elif gr < 60:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'中GR({gr:.0f})')
                    
                    # PE确认（硬石膏PE=5.0）
                    if not np.isnan(pe) and pe > 4.0:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'高PE({pe:.1f})')
                    
                    # 高电阻率确认
                    if rt > 200:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'高电阻率({rt:.0f})')
                    elif rt > 100:
                        anhydrite_score += 0.5
                        anhydrite_reasons.append(f'中-高电阻率({rt:.0f})')
                    
                    # 优化确认（兼容VAnhydrite和VOL_ANHY两种列名）
                    vanhydrite_val = row.get('VAnhydrite', row.get('VOL_ANHY', 0))
                    if vanhydrite_val > 0.2:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'优化确认(VAnh={vanhydrite_val:.2f})')
                    
                    # 综合阈值：沉积环境得分影响确认难度
                    #   env_score > 0.6 → 阈值3.5（环境支持，较宽松）
                    #   env_score 0.3-0.6 → 阈值4.5（环境一般）
                    #   env_score < 0.3 → 阈值6.0（环境不利，需要极强证据）
                    #   GR>60时额外+1.0
                    anhydrite_threshold = 4.5
                    if env_score_anh > 0.6:
                        anhydrite_threshold = 3.5
                    elif env_score_anh < 0.3:
                        anhydrite_threshold = 6.0
                    if gr > 60:
                        anhydrite_threshold += 1.0
                    
                    # 加入环境得分作为辅助评分
                    if env_score_anh > 0.5:
                        anhydrite_score += 0.5
                        anhydrite_reasons.append(f'沉积环境支持({env_score_anh:.2f})')
                    elif env_score_anh < 0.3:
                        anhydrite_score -= 1.0
                        anhydrite_reasons.append(f'沉积环境不利({env_score_anh:.2f})')
                    
                    if anhydrite_score >= anhydrite_threshold:
                        return ('anhydrite', anhydrite_score, '; '.join(anhydrite_reasons))
                
                return (None, 0, '')
            
            def _valid_vol(val):
                """将异常值（-999, -999.25, NaN等）转为0，有效值原样返回"""
                if val is None or np.isnan(val) or val < -100:
                    return 0.0
                return max(val, 0.0)
            
            def classify_lithology(row):
                # 矿物含量列名有两种格式：V{Mineral}（内部自算）或 VOL_{MINERAL}（LAS预计算/CSV导出）
                # 添加VOL_*格式备选，确保两种命名都能正确识别
                vclay = _valid_vol(row.get('VClay', row.get('VSH', row.get('VOL_ILLITE', row.get('VOL_CLAY', 0)))))
                vquartz = _valid_vol(row.get('VQuartz', row.get('VOL_QUARTZ', row.get('VOL_QZ', 0))))
                vcalcite = _valid_vol(row.get('VCalcite', row.get('VOL_CALCITE', 0)))
                vdolomite = _valid_vol(row.get('VDolomite', row.get('VOL_DOLOM', 0)))
                vanhydrite = _valid_vol(row.get('VAnhydrite', row.get('VOL_ANHY', 0)))
                vhalite = _valid_vol(row.get('VHalite', row.get('VOL_HALITE', 0)))
                vbasalt = _valid_vol(row.get('VBasalt', row.get('VOL_BASALT', 0)))
                
                density = row.get('RHOB', row.get('DEN', 2.65))
                ac = row.get('DTCO', row.get('DT', row.get('AC', 55.5)))
                gr = row.get('GR', 50)
                pe = row.get('PE', row.get('PEF', 2.5))
                nphi = row.get('NPHI', row.get('CNL', 0))
                rt = row.get('AT90', row.get('LLD', row.get('RT', 50)))
                
                # 井径/钻头尺寸比（用于盐岩扩径检测）
                bit = row.get('BIT', 8.5)
                cal = row.get('CAL', row.get('CALS', bit))
                cal_ratio = cal / max(bit, 0.1) if bit > 0 else 1.0
                
                # 计算碳酸盐岩总含量
                vcarbonate = vcalcite + vdolomite + vanhydrite
                
                # ========== 特殊矿物检测（最先执行，独立于常规岩性分类） ==========
                # 特殊矿物具有与常规砂泥岩/碳酸盐岩完全不同的测井响应
                # 检测到特殊矿物后直接返回，不再走常规分类流程
                special_mineral, special_score, special_reason = detect_special_mineral(row)
                if special_mineral is not None:
                    # 将特殊矿物信息写入行数据（用于后续报告和可视化）
                    row['SPECIAL_MINERAL'] = special_mineral
                    row['SPECIAL_SCORE'] = special_score
                    row['SPECIAL_REASON'] = special_reason
                    return special_mineral
                else:
                    row['SPECIAL_MINERAL'] = 'none'
                    row['SPECIAL_SCORE'] = 0
                    row['SPECIAL_REASON'] = ''
                
                # ========== 物理约束强制判定（优先于矿物含量>0.5判定） ==========
                # 密度>2.68且PE>3.5是明确的碳酸盐岩信号，即使矿物优化结果给vquartz>0.5
                # 也说明矿物优化有问题（DEN-AC交汇图偏差导致石英/方解石误判）。
                # PE作为碳酸盐岩最直接的指示剂，可靠性高于矿物优化结果。
                # 解决3-SPS-111D井6455-6505m段矿物优化错误给出VQuartz>0.5但实际为碳酸盐岩的问题。
                if density > 2.68 and not np.isnan(pe) and pe > 3.5:
                    if density > 2.85:
                        return 'dolomite'
                    else:
                        return 'limestone'
                
                # PE>5.0是极强的碳酸盐/蒸发岩信号（方解石PE=5.08，硬石膏PE=5.0）
                # 即使密度<2.68，PE>5.0也说明不可能是纯砂岩（石英PE=1.81）。
                # 盐岩是蒸发环境沉积，砂泥岩是河流/三角洲沉积，环境完全不同，
                # 盐岩段中不可能出现砂泥岩夹层，PE>5.0的点应为碳酸盐岩夹层。
                # 注意：仅在PE曲线可靠时使用此约束（PE不可信时PEF高值可能来自
                # 水泥环、井眼不规则等非地层因素，如TrakesKE-1顶部585-595m水泥块）
                #
                # 额外验证：必须同时检查中子和声波，排除非地层因素的PE高值
                #   - 碳酸盐岩：中子低(~0)，声波低(~47-50)
                #   - 水泥块：中子极高(>35)，声波较高(>60)
                #   - 砂泥岩：中子中等(5-25)，声波中等(55-80)
                # 中子>15或声波>65时，即使PE>5.0也不应判为碳酸盐岩
                if (self.pe_quality.get('pe_reliable', True) and
                    not np.isnan(pe) and pe > 5.0 and
                    nphi < 15 and ac < 65):
                    return 'limestone'
                
                # ========== 矿物含量>0.5优先判定（最硬标准） ==========
                # 任何矿物有效含量>0.5，该矿物就是主要岩性，物理约束不可覆盖
                # 这是最硬的标准：矿物优化结果>0.5 > 物理约束（密度/PE/GR）
                # 顺序：硬石膏/盐岩 > 玄武岩 > 碳酸盐岩 > 泥岩 > 砂岩
                
                # 硬石膏>0.5
                if vanhydrite > 0.5:
                    return 'anhydrite'
                
                # 盐岩（优化结果确认）
                if vhalite > 0.5:
                    return 'halite'
                
                # 玄武岩>0.3（玄武岩通常不是优化矿物，用更宽松的阈值）
                if vbasalt > 0.3 or (density > 2.70 and gr > 80 and pe < 3.5):
                    return 'volcanic'
                
                # 方解石>0.5
                if vcalcite > 0.5:
                    return 'limestone'
                
                # 白云石>0.5
                if vdolomite > 0.5:
                    return 'dolomite'
                
                # 泥岩>0.5（无密度限制：即使密度>2.65，但vclay>0.5仍判泥岩）
                if vclay > 0.5:
                    return 'shale'
                
                # 石英>0.5
                if vquartz > 0.5:
                    return 'sandstone'
                
                # ========== 矿物含量<0.5时的后备判断（物理约束+GR主导） ==========
                # 以下为矿物含量未达0.5时的后备逻辑，基于物理约束和GR信号
                # ========== 泥岩优先判断（GR主导，在物理约束之前） ==========
                # 泥岩/页岩的测井响应特征：高GR + 低电阻率 + 较低密度 + 低声波 + 高中子
                # 当GR足够高时，泥岩特征明确，不应被密度略高而排除
                # 
                # 问题背景：砂泥岩剖面中砂岩和泥岩对比明显时，
                # 高GR+低RT+较低密度 = 明确的泥岩，不应判为砂岩
                
                # 强泥岩信号：GR>100 → 几乎确定是泥岩（除非是碳酸盐岩或蒸发岩）
                if gr > 100 and rt < 50 and density < 2.65:
                    return 'shale'
                
                # 中等泥岩信号：GR 80-100 + 低阻 + 较低密度 + 较高VSH
                if gr > 80 and rt < 30 and density < 2.60 and vclay > 0.3:
                    return 'shale'
                
                # ========== 物理约束优先判断 ==========
                # 高密度(>2.60)不可能是纯泥岩：泥岩密度一般不超过2.55-2.60
                # 这是物理规律，必须在最优化结果之前检查
                # 例外：钙质泥岩/硅质泥岩密度可达2.65，但高GR+低RT仍可识别
                if density > 2.60:
                    # ========== 即使密度>2.60，泥岩仍可能（压实泥岩/钙质泥岩/粉砂质泥岩）==========
                    # 泥岩密度可达2.60-2.65，当GR较高+低阻时仍应判泥岩
                    # 解决TrakesKE-1井砂岩过多泥岩过少问题
                    if gr > 80 and rt < 30:
                        return 'shale'
                    if gr > 100 and rt < 50:
                        return 'shale'
                    if gr > 70 and rt < 20 and vclay > 0.25:
                        return 'shale'
                    
                    # 即使GR不高，如果低阻+较高VSH，也是泥岩
                    if rt < 15 and vclay > 0.4 and density < 2.68:
                        return 'shale'
                    
                    # 钙质泥岩/致密泥岩：GR较高但密度偏高
                    if gr > 120 and rt < 20:
                        return 'shale'
                    
                    # ========== 密度+PE强碳酸盐信号：无条件判定碳酸盐岩 ==========
                    # 密度>2.68排除纯砂岩和纯泥岩，PE>3.5是明确碳酸盐信号
                    # 此时即使GR较高（泥质灰岩）或最优化给石英（DEN-AC交汇图偏差），
                    # 也必须判为碳酸盐岩。解决3-SPS-111D井6450-6500m段误判砂岩问题
                    # PE不可信时仅用密度判断
                    if density > 2.68:
                        if self.pe_quality.get('pe_reliable', True) and not np.isnan(pe) and pe > 3.5:
                            if density > 2.85:
                                return 'dolomite'
                            else:
                                return 'limestone'
                    
                    # 高密度+低GR→碳酸盐岩或致密砂岩
                    if gr < 60:
                        pe_ok = self.pe_quality.get('pe_reliable', True) and not np.isnan(pe) and pe > 3.0
                        if vcarbonate > 0.3 or pe_ok:
                            # 碳酸盐岩：PE高或碳酸盐矿物含量高
                            if vcalcite > vdolomite:
                                return 'limestone'
                            else:
                                return 'dolomite'
                        else:
                            # 高密度(>2.75)不可能是纯砂岩，纯砂岩密度一般不超过2.65
                            if density > 2.75:
                                if vcalcite > vdolomite:
                                    return 'limestone'
                                else:
                                    return 'dolomite'
                            # 致密砂岩
                            return 'sandstone'
                    elif density > 2.68 and self.pe_quality.get('pe_reliable', True) and not np.isnan(pe) and pe > 3.0:
                        # 密度>2.68+PE>3.0但GR≥60（泥质碳酸盐岩）：仍判为碳酸盐岩
                        if vcalcite > vdolomite:
                            return 'limestone'
                        else:
                            return 'dolomite'
                    elif vcarbonate > 0.5:
                        # 高密度+碳酸盐矿物含量高→碳酸盐岩
                        if vcalcite > vdolomite:
                            return 'limestone'
                        else:
                            return 'dolomite'
                    elif vquartz > 0.3:
                        # 高密度+石英含量较高→致密砂岩（但排除PE>3.0的碳酸盐）
                        if self.pe_quality.get('pe_reliable', True) and not np.isnan(pe) and pe > 3.0:
                            # PE>3.0但矿物含量未达标→可能是泥质灰岩，PE是更可靠指标
                            return 'limestone'
                        # 密度>2.75不可能是纯砂岩
                        if density > 2.75:
                            if vcalcite > vdolomite:
                                return 'limestone'
                            else:
                                return 'dolomite'
                        return 'sandstone'
                
                # 泥岩判断（放宽密度约束）：
                # 纯泥岩密度一般<2.55，但压实泥岩/含粉砂泥岩可达2.60-2.65
                # 当GR足够高（>80）且电阻率低时，密度门槛放宽至2.65
                if vclay > 0.5 and density < 2.65:
                    return 'shale'
                if gr > 100 and density < 2.65:
                    return 'shale'
                if gr > 80 and rt < 50 and density < 2.58:
                    return 'shale'
                
                # 基于最优化矿物含量的判断（核心逻辑）
                # 矿物含量大于0.1认为含有该矿物
                if vcarbonate > 0.5:
                    # 使用PE值辅助区分灰岩和白云岩
                    # 灰岩PE较高(5.08)，白云岩PE较低(3.14)
                    pe_threshold = 3.8  # 区分灰岩和白云岩的PE阈值
                    
                    if vcalcite > vdolomite:
                        # 方解石含量高，且PE较高，判定为灰岩
                        if pe > pe_threshold or vcalcite > 0.6:
                            return 'limestone'
                        else:
                            # 方解石含量高但PE低，可能是含白云石的灰岩
                            return 'limestone'
                    else:
                        # 白云石含量高
                        if pe < pe_threshold or vdolomite > 0.6:
                            return 'dolomite'
                        else:
                            # 白云石含量高但PE高，可能是含方解石的白云岩
                            return 'dolomite'
                elif vquartz > 0.5:
                    return 'sandstone'
                
                # 基于交汇图骨架参数的判断（深度级别微调）
                best_lith = 'mixed'
                min_distance = float('inf')
                for lith_type in main_lithology:
                    if lith_type in estimated_skeleton:
                        skel = estimated_skeleton[lith_type]
                        density_dist = abs(density - skel.get('density', 2.65))
                        ac_dist = abs(ac - skel.get('ac', 55.5))
                        total_dist = density_dist * 2 + ac_dist / 10
                        
                        if total_dist < min_distance:
                            min_distance = total_dist
                            best_lith = lith_type
                
                # 深度级别交汇图迭代核验（优先使用）
                if depth_lithology:
                    depth = row.get('DEPT', row.get('DEPTH', 0))
                    if depth in depth_lithology:
                        crossplot_lith = depth_lithology[depth]
                        if crossplot_lith in ['sandstone', 'shale', 'limestone', 'dolomite', 'anhydrite', 'gypsum', 'halite', 'coal', 'pyrite']:
                            best_lith = crossplot_lith
                
                # 火山岩特殊判断
                if has_volcanic and density >= 2.70 and density <= 2.80:
                    if ac > 45 and ac < 55:
                        best_lith = 'volcanic'
                
                return best_lith
            
            # 先批量检测特殊矿物
            special_results = data.apply(detect_special_mineral, axis=1)
            data['SPECIAL_MINERAL'] = special_results.apply(lambda x: x[0] if x[0] else 'none')
            data['SPECIAL_SCORE'] = special_results.apply(lambda x: x[1])
            data['SPECIAL_REASON'] = special_results.apply(lambda x: x[2])
            
            special_count = (data['SPECIAL_MINERAL'] != 'none').sum()
            special_breakdown = data.loc[data['SPECIAL_MINERAL'] != 'none', 'SPECIAL_MINERAL'].value_counts().to_dict()
            logger.info(f"特殊矿物检测完成: 共{special_count}点, 分布: {special_breakdown}")
            logger.info(f"蒸发岩环境评估: 井级别base={_evaporite_env_base:.2f}, "
                       f"剖面类型={_well_profile_type}, "
                       f"{'砂泥岩剖面(阈值严格,物理证据充分时仍可认定)' if _skip_evaporite else '综合得分调制阈值（不绝对跳过）'}")
            
            # 然后执行常规岩性分类
            data['LITHOLOGY'] = data.apply(classify_lithology, axis=1)

            # ========== 同步矿物含量与LITHOLOGY（数据层一致性）==========
            # 确保大段岩性（如盐岩、灰岩）的矿物含量与岩性定名一致，
            # 使profile道与岩性道使用同一套判别逻辑。
            # 替代log_visualizer.py中的显示层LITHOLOGY一致性补丁。
            data = self._sync_minerals_with_lithology(data)

            # 保存岩性分析结果到数据中
            data['MAIN_LITHOLOGY'] = ', '.join(main_lithology)
            
            # ========== PE质量信息存入结果 ==========
            if hasattr(self, 'pe_quality') and self.pe_quality:
                data.attrs['pe_quality'] = {
                    'reliable': self.pe_quality.get('pe_reliable', True),
                    'trend_only': self.pe_quality.get('pe_trend_only', False),
                    'bad': self.pe_quality.get('pe_bad', False),
                    'reason': self.pe_quality.get('reason', ''),
                    'offset': self.pe_quality.get('pe_offset', 0),
                }
            
            logger.info("Multi-mineral analysis completed")
            return data
        except Exception as e:
            logger.error(f"多矿物分析失败: {e}")
            import traceback
            traceback.print_exc()
            return data

# --- 沉积相分析类 ---
class FaciesAnalyzer:
    """沉积相分析类"""
    
    def __init__(self, output_dir='output'):
        """初始化沉积相分析器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.facies_dir = self.output_dir
        self.mineral_analyzer = MineralAnalyzer()
    
    def calculate_mineral_proportions(self, data):
        """计算矿物比例"""
        try:
            # 使用多矿物分析器计算矿物比例
            data = self.mineral_analyzer.optimize_minerals(data)
            return data
        except Exception as e:
            logger.error(f"计算矿物比例失败: {e}")
            return data
    
    def generate_lithology_name(self, vsh, vss, vca):
        """生成Lithology名称"""
        if vsh > 0.5:
            return 'shale'
        elif vss > 0.5:
            return 'sandstone'
        elif vca > 0.5:
            return 'carbonate'
        else:
            return 'mixed'
    
    def classify_lithology(self, data):
        """Lithology分类（有效曲线不足3条的井段跳过）"""
        try:
            # 检查是否有VALID_CURVES_COUNT列
            if 'VALID_CURVES_COUNT' not in data.columns:
                data = self._count_valid_curves_per_segment(data)
            
            # 创建LITHOLOGY列，默认为空（有效曲线不足3条时不解释）
            if 'LITHOLOGY' not in data.columns:
                data['LITHOLOGY'] = ''
            
            # 获取有效曲线足够的索引
            valid_indices = data[data['VALID_CURVES_COUNT'] >= 3].index
            
            if len(valid_indices) > 0:
                # 只对有效曲线足够的井段进行岩性分析
                valid_data = data.loc[valid_indices].copy()
                valid_data = self.mineral_analyzer.run_mineral_analysis(valid_data)
                
                # 将结果合并回原始数据
                # 使用索引对齐，避免长度不匹配问题
                # 注意：必须包含V前缀列（VQuartz, VCalcite等），这些是_sync_minerals_with_lithology
                # 修改的列，如果不合并回原始data，profile道将使用未同步的旧数据
                merge_cols = ['QUARTZ', 'CALCITE', 'DOLOMITE', 'ANHYDRITE', 'CLAY', 'LITHOLOGY',
                              'LITHOLOGY_EN', 'Sw', 'So', 'PHI', 'VSH',
                              'VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite', 'VClay',
                              'VSAND', 'PORD', 'Sg']
                for col in merge_cols:
                    if col in valid_data.columns:
                        # 使用索引对齐赋值，只更新有对应索引的值
                        data.loc[valid_data.index, col] = valid_data[col].values
            
            # 有效曲线不足的井段保持默认值（空字符串，不进行岩性解释）
            data.loc[data['VALID_CURVES_COUNT'] < 3, 'LITHOLOGY'] = ''
            
            return data
        except Exception as e:
            logger.error(f"Lithology分类失败: {e}")
            return data
    
    def _detect_curve_shape(self, data, idx, window_size=10):
        """
        检测测井曲线形态
        返回: 'box' (箱型), 'bell' (钟型), 'funnel' (漏斗型), 'finger' (指状), 'sawtooth' (锯齿型), 'unknown'
        """
        start = max(0, idx - window_size)
        end = min(len(data), idx + window_size + 1)
        
        if end - start < 5:
            return 'unknown'
        
        gr_values = data['GR'].iloc[start:end].values
        if len(gr_values) < 5:
            return 'unknown'
        
        # 计算统计特征
        mean_val = np.mean(gr_values)
        std_val = np.std(gr_values)
        min_val = np.min(gr_values)
        max_val = np.max(gr_values)
        range_val = max_val - min_val
        
        # 计算形态特征
        # 箱型：顶部和底部都比较平坦，标准差小
        if std_val < 15 and range_val < 30:
            return 'box'
        
        # 获取中心位置的值
        center_idx = len(gr_values) // 2
        center_val = gr_values[center_idx]
        
        # 钟型：底部粗、顶部细，中心值较低
        if center_idx > 2:
            lower_half = gr_values[:center_idx]
            upper_half = gr_values[center_idx:]
            
            lower_mean = np.mean(lower_half)
            upper_mean = np.mean(upper_half)
            
            # 钟型：下部值高，上部值低
            if lower_mean > upper_mean + 20 and center_val < lower_mean - 10:
                return 'bell'
            
            # 漏斗型：上部值高，下部值低
            if upper_mean > lower_mean + 20 and center_val > lower_mean + 10:
                return 'funnel'
        
        # 指状：孤立的高幅度尖峰
        if range_val > 80 and std_val > 25:
            # 检查是否有明显的尖峰
            peaks = np.sum(gr_values > mean_val + 2 * std_val)
            if peaks <= 3:
                return 'finger'
        
        # 锯齿型：频繁的锯齿状变化
        if std_val > 20 and range_val > 50:
            # 计算相邻点之间的变化次数
            diffs = np.abs(np.diff(gr_values))
            frequent_changes = np.sum(diffs > 10)
            if frequent_changes > len(gr_values) // 3:
                return 'sawtooth'
        
        return 'unknown'
    
    def _calculate_facies_features(self, data):
        """计算沉积相分类特征"""
        features = pd.DataFrame(index=data.index)
        
        # 基础曲线值
        features['GR'] = data.get('GR', 0)
        features['RT'] = data.get('RT', data.get('LLD', data.get('ILD', data.get('R90', 1))))
        features['DEN'] = data.get('DEN', 2.65)
        features['NPHI'] = data.get('NPHI', data.get('CNL', 0))
        features['DT'] = data.get('DT', 60)
        
        # 曲线形态特征
        features['GR_shape'] = data.apply(lambda row: self._detect_curve_shape(data, row.name), axis=1)
        
        # 岩性信息
        features['VSH'] = data.get('VSH', 0.5)
        features['PHI'] = data.get('PHI', 0.15)
        
        # 导数特征（反映变化率）
        features['GR_diff'] = features['GR'].diff().fillna(0)
        features['RT_diff'] = features['RT'].diff().fillna(0)
        
        # 统计特征（滑动窗口）
        features['GR_mean_5'] = features['GR'].rolling(5, center=True, min_periods=1).mean()
        features['GR_std_5'] = features['GR'].rolling(5, center=True, min_periods=1).std().fillna(0)
        features['RT_mean_5'] = features['RT'].rolling(5, center=True, min_periods=1).mean()
        
        return features
    
    def classify_facies(self, data):
        """沉积相分类（使用机器学习模型结合曲线形态分析，有效曲线不足3条的井段跳过）"""
        try:
            # 检查是否有VALID_CURVES_COUNT列
            if 'VALID_CURVES_COUNT' not in data.columns:
                data = self._count_valid_curves_per_segment(data)
            
            # 创建FACIES列，默认为空（有效曲线不足3条时不解释）
            if 'FACIES' not in data.columns:
                data['FACIES'] = ''
            
            # 获取有效曲线足够的索引
            valid_indices = data[data['VALID_CURVES_COUNT'] >= 3].index
            
            if len(valid_indices) == 0:
                logger.info("有效曲线不足3条的井段，跳过沉积相分类")
                return data
            
            # 只对有效曲线足够的井段进行沉积相分析
            valid_data = data.loc[valid_indices].copy()
            
            # 确保必要的列存在
            if 'GR' not in valid_data.columns:
                valid_data['GR'] = 0
            if 'RT' not in valid_data.columns:
                if 'LLD' in valid_data.columns:
                    valid_data['RT'] = valid_data['LLD']
                elif 'ILD' in valid_data.columns:
                    valid_data['RT'] = valid_data['ILD']
                elif 'R90' in valid_data.columns:
                    valid_data['RT'] = valid_data['R90']
                else:
                    valid_data['RT'] = 1
            
            # 计算特征
            features = self._calculate_facies_features(valid_data)
            
            # 将形态特征编码
            shape_mapping = {'box': 0, 'bell': 1, 'funnel': 2, 'finger': 3, 'sawtooth': 4, 'unknown': 5}
            features['GR_shape_code'] = features['GR_shape'].map(shape_mapping)
            
            # 使用集成分类方法
            def classify_facies_row(row):
                gr = row['GR']
                rt = row['RT']
                vsh = row.get('VSH', 0.5)
                phi = row.get('PHI', 0.15)
                gr_shape = row['GR_shape']
                
                # Delta front subfacies
                if vsh < 0.3:
                    if rt > 15 and gr < 60 and gr_shape in ['box', 'bell']:
                        return 'underwater_distributary_channel'
                    elif rt > 8 and gr < 80 and gr_shape in ['funnel', 'bell']:
                        return 'mouth_bar'
                    elif rt > 4 and gr < 100 and gr_shape == 'funnel':
                        return 'distal_bar'
                    elif rt > 2 and gr < 120:
                        return 'sheet_sand'
                    elif gr > 100 and rt < 5:
                        return 'interdistributary_bay'
                
                # Delta plain subfacies
                if rt > 20 and gr < 50 and gr_shape == 'box':
                    return 'distributary_channel'
                elif gr >= 80 and gr <= 120 and rt > 5:
                    return 'natural_levee'
                elif gr_shape == 'finger' and gr < 100:
                    return 'crevasse_splay'
                elif gr > 140 and rt < 3:
                    if phi < 0.1:
                        return 'swamp'
                    else:
                        return 'flood_plain'
                
                # Prodelta subfacies
                if gr > 120 and vsh > 0.5 and phi < 0.2:
                    return 'prodelta_mud'
                
                # Lacustrine facies
                if gr > 130 and vsh > 0.6:
                    if rt < 2:
                        return 'deep_lake_mud'
                    else:
                        return 'shallow_lake_mud'
                
                # Fluvial facies
                if gr_shape == 'box' and rt > 10 and gr < 70:
                    return 'channel'
                elif gr >= 70 and gr <= 130:
                    return 'floodplain'
                
                # Default classification
                if gr < 60:
                    return 'sandy_deposit'
                elif gr < 100:
                    return 'transition'
                else:
                    return 'muddy_deposit'
            
            valid_data['FACIES'] = features.apply(classify_facies_row, axis=1)
            
            # 将结果合并回原始数据
            data.loc[valid_indices, 'FACIES'] = valid_data['FACIES'].values
            
            # 有效曲线不足的井段保持默认值（空字符串，不进行沉积相解释）
            data.loc[data['VALID_CURVES_COUNT'] < 3, 'FACIES'] = ''
            
            return data
        except Exception as e:
            logger.error(f"沉积相分类失败: {e}")
            import traceback
            traceback.print_exc()
            return data
    
    def generate_geological_interpretation(self, data, well_name='Unknown'):
        """生成地质解释"""
        try:
            interpretation = f"""# {well_name} 井地质解释报告

## 基本信息
- 井名: {well_name}
- Number of data points: {len(data)}
- 解释日期: {datetime.datetime.now().strftime('%Y-%m-%d')}

## 岩性统计
"""
            
            # 岩性统计
            if 'LITHOLOGY' in data.columns:
                lithology_counts = data['LITHOLOGY'].value_counts()
                interpretation += "\nLithology分布:\n"
                for lithology, count in lithology_counts.items():
                    interpretation += f"- {lithology}: {count} 个数据点\n"
            
            # 沉积相统计
            if 'FACIES' in data.columns:
                facies_counts = data['FACIES'].value_counts()
                interpretation += "\n沉积相分布:\n"
                for facies, count in facies_counts.items():
                    interpretation += f"- {facies}: {count} 个数据点\n"
            
            # 矿物含量统计
            mineral_cols = [col for col in data.columns if col.startswith('V') and len(col) > 1]
            if mineral_cols:
                interpretation += "\n矿物含量统计:\n"
                for col in mineral_cols:
                    avg_value = data[col].mean()
                    interpretation += f"- {col}: {avg_value:.3f}\n"
            
            # 流体饱和度统计
            if 'Sw' in data.columns and 'So' in data.columns:
                interpretation += "\n流体饱和度统计:\n"
                interpretation += f"- 平均Water Saturation: {data['Sw'].mean():.3f}\n"
                interpretation += f"- 平均含油饱和度: {data['So'].mean():.3f}\n"
            
            return interpretation
        except Exception as e:
            logger.error(f"生成地质解释失败: {e}")
            return ""
    
    def save_geological_interpretation(self, interpretation_text, well_name='Unknown'):
        """保存地质解释"""
        try:
            interpretation_path = self.facies_dir / f"{well_name}_geological_interpretation.txt"
            with open(interpretation_path, 'w', encoding='utf-8') as f:
                f.write(interpretation_text)
            return str(interpretation_path)
        except Exception as e:
            logger.error(f"保存地质解释失败: {e}")
            return None
    
    def _count_valid_curves_per_segment(self, data, window_size=50):
        """
        逐井段统计有效曲线数量
        有效曲线：当前深度点的曲线值有效（非NaN、非-999、>0）
        且滑动窗口内有效率>30%（排除单点偶然有效的情况）

        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）

        返回:
            data: 添加了 VALID_CURVES_COUNT 列的DataFrame
        """
        valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC']

        # 创建有效曲线计数列
        valid_counts = []

        for i in range(len(data)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(data), i + window_size // 2)

            count = 0
            for curve in valid_curves:
                if curve in data.columns:
                    # 检查当前深度点的值是否有效
                    point_val = data[curve].iloc[i]
                    if pd.isna(point_val) or point_val <= -999 or point_val <= 0:
                        continue
                    # 同时检查窗口内有效率（排除偶然单点有效）
                    window_data = data[curve].iloc[start_idx:end_idx]
                    valid_ratio = (window_data > 0).sum() / len(window_data)
                    if valid_ratio > 0.3:
                        count += 1

            valid_counts.append(count)

        data['VALID_CURVES_COUNT'] = valid_counts
        return data
    
    def run_facies_analysis(self, data, well_name='Unknown'):
        """运行沉积相分析"""
        try:
            logger.info(f"开始对 {well_name} 井进行沉积相分析")
            
            # 逐井段检查有效曲线数量
            data = self._count_valid_curves_per_segment(data)
            
            # 检查是否有足够的有效曲线
            # 有效曲线包括：GR, RT/LLD/ILD, DEN/RHOB, NPHI/CNL, DT/AC
            valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC']
            available_curves = [curve for curve in valid_curves if curve in data.columns]
            
            # 如果整个井的有效曲线少于3条，跳过岩性和沉积相分析
            if len(available_curves) < 3:
                logger.warning(f"有效曲线数量不足（{len(available_curves)}条），跳过岩性和沉积相分析")
                # 返回原始数据，不添加岩性和沉积相列
                return {
                    'data': data,
                    'interpretation': f"井名: {well_name}\n警告: 有效曲线数量不足（{len(available_curves)}条），未进行岩性和沉积相分析"
                }
            
            # 岩性分类（使用多矿物分析）
            data = self.classify_lithology(data)
            
            # 沉积相分类
            data = self.classify_facies(data)
            
            # 生成地质解释
            interpretation_text = self.generate_geological_interpretation(data, well_name)
            
            logger.info(f"沉积相分析完成（结果包含在processed数据中）")
            
            return {
                'data': data,
                'interpretation': interpretation_text
            }
        except Exception as e:
            logger.error(f"沉积相分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- 数据文件存储工具函数 ---
def save_data_to_file(data, file_path, well_name="Unknown"):
    """将数据保存到CSV文件"""
    try:
        data.to_csv(file_path, index=False, encoding="utf-8")
        logger.info(f"数据已保存到文件: {file_path}")
        return True
    except Exception as e:
        logger.error(f"保存数据到文件失败: {e}")
        return False

# --- 弹簧段校正类 ---
class SpringSegmentCorrector:
    """弹簧段校正类"""
    
    def __init__(self):
        """初始化弹簧段校正器"""
        pass
    
    def detect_spring_segments(self, data, curve_name='RHOB', sensitivity=3.0, min_segment_length=5.0):
        """
        检测弹簧段（基于密度变化）
        弹簧段特点：
        1. 在一段井段内变化的频率基本相同（周期性）
        2. 变化的最值相同（跳跃幅度一致）
        3. 和GR等其它曲线不相关
        4. 至少是1米长度范围内
        
        参数:
            data: 测井数据DataFrame
            curve_name: 要检测的曲线名称（默认RHOB密度曲线）
            sensitivity: 灵敏度（倍数），越高越敏感，默认3.0
            min_segment_length: 最小弹簧段长度（米），默认1米
        
        返回:
            弹簧段区间列表 [(start_depth, end_depth), ...]
        """
        if curve_name not in data.columns:
            logger.warning(f"曲线 {curve_name} 不存在，无法检测弹簧段")
            return []
        
        curve_data = data[curve_name].values
        depth_data = data['MD'].values
        
        if len(curve_data) < 50:
            logger.warning(f"数据点太少（{len(curve_data)}），无法检测弹簧段")
            return []
        
        # 移除NaN和异常值
        valid_mask = ~np.isnan(curve_data) & ~np.isinf(curve_data)
        if np.sum(valid_mask) < 50:
            logger.warning(f"有效数据点太少，无法检测弹簧段")
            return []
        
        valid_curve = curve_data[valid_mask]
        valid_depth = depth_data[valid_mask]
        
        # 计算采样间隔
        dz = np.mean(np.diff(valid_depth))
        if dz == 0 or np.isnan(dz):
            dz = 0.1  # 默认采样间隔
        
        # 计算密度一阶差分（相邻点差值）
        diffs = np.abs(np.diff(valid_curve))
        
        # 移除NaN和异常值
        valid_diffs = diffs[~np.isnan(diffs) & ~np.isinf(diffs)]
        
        if len(valid_diffs) == 0:
            logger.warning(f"曲线 {curve_name} 差值数据全部无效，无法检测弹簧段")
            return []
        
        # 使用中位数和MAD计算阈值（更稳健）
        diff_median = np.median(valid_diffs)
        diff_mad = np.median(np.abs(valid_diffs - diff_median))
        
        # 如果MAD为0，使用标准差作为替代
        if diff_mad == 0 or np.isnan(diff_mad):
            diff_mad = np.std(valid_diffs)
        
        # 阈值 = 正常变化的sensitivity倍
        threshold = diff_median + sensitivity * diff_mad
        
        # 绝对阈值：密度变化小于0.03 g/cm3不认为是跳跃
        min_abs_jump = 0.03
        threshold = max(threshold, min_abs_jump)
        
        # 1. 使用滑动窗口检测高频跳跃（1米窗口）
        window_size_1m = max(int(1 / dz), 10)  # 1米窗口
        if window_size_1m > 50:
            window_size_1m = 50
        
        # 计算每个点周围的跳跃率
        jump_rates_1m = np.zeros(len(diffs))
        for i in range(len(diffs) - window_size_1m + 1):
            jump_rates_1m[i] = np.sum(diffs[i:i+window_size_1m] > threshold) / window_size_1m
        
        # 2. 检测周期性模式（变化频率相同）
        # 使用自相关分析检测周期性
        acf_mask = np.zeros(len(diffs), dtype=bool)
        if len(valid_diffs) >= 20:
            from scipy.signal import correlate
            # 只分析跳跃区域的自相关
            jump_locations = np.where(diffs > threshold)[0]
            if len(jump_locations) >= 5:
                # 计算跳跃间隔的自相关
                jump_intervals = np.diff(jump_locations)
                if len(jump_intervals) >= 3:
                    # 归一化自相关
                    acf = correlate(jump_intervals - np.mean(jump_intervals), 
                                   jump_intervals - np.mean(jump_intervals), 
                                   mode='same')
                    acf = acf / (np.std(jump_intervals)**2 * len(jump_intervals))
                    # 检测峰值（排除自相关峰值）
                    for lag in range(1, min(10, len(acf)//2)):
                        if acf[len(acf)//2 + lag] > 0.5 or acf[len(acf)//2 - lag] > 0.5:
                            acf_mask[jump_locations] = True
        
        # 3. 检测最值一致性（变化幅度相似）
        # 在跳跃区域内，跳跃幅度的标准差较小
        amplitude_consistency = np.zeros(len(diffs), dtype=bool)
        if np.sum(diffs > threshold) >= 5:
            jump_amplitudes = diffs[diffs > threshold]
            if len(jump_amplitudes) >= 5:
                amp_mean = np.mean(jump_amplitudes)
                amp_std = np.std(jump_amplitudes)
                # 如果跳跃幅度的变异系数较小，说明幅度一致
                if amp_mean > 0 and amp_std / amp_mean < 0.5:
                    amplitude_consistency[diffs > threshold] = True
        
        # 4. 检测与GR曲线的相关性（弹簧段通常与GR无关）
        gr_correlation_mask = np.zeros(len(diffs), dtype=bool)
        if 'GR' in data.columns:
            gr_data = data['GR'].values[valid_mask]
            gr_diffs = np.abs(np.diff(gr_data))
            gr_diffs = gr_diffs[~np.isnan(gr_diffs) & ~np.isinf(gr_diffs)]
            
            if len(gr_diffs) > 0:
                # 计算局部相关性
                corr_window = max(int(2 / dz), 20)
                for i in range(len(diffs) - corr_window + 1):
                    if i + corr_window <= len(gr_diffs):
                        # 计算密度跳跃和GR变化的相关性
                        d_jump = diffs[i:i+corr_window]
                        gr_change = gr_diffs[i:i+corr_window]
                        if len(d_jump) > 5 and np.std(d_jump) > 0 and np.std(gr_change) > 0:
                            corr = np.corrcoef(d_jump, gr_change)[0, 1]
                            # 如果相关性很低，可能是弹簧段
                            if np.abs(corr) < 0.3:
                                gr_correlation_mask[i:i+corr_window] = True
        
        # 综合判定弹簧段
        # 条件1：跳跃率超过30%（更宽松）
        condition1 = jump_rates_1m > 0.3
        # 条件2：周期性或幅度一致性
        condition2 = acf_mask | amplitude_consistency
        # 条件3：与GR不相关
        condition3 = gr_correlation_mask
        
        spring_mask = condition1 & (condition2 | condition3)
        
        logger.info(f"弹簧段检测 - {curve_name}:")
        logger.info(f"  采样间隔: {dz:.3f}m, 1米窗口大小: {window_size_1m}")
        logger.info(f"  跳跃阈值: {threshold:.4f}, 中位数变化: {diff_median:.4f}")
        logger.info(f"  条件1(跳跃率>30%): {np.sum(condition1)}/{len(diffs)}")
        logger.info(f"  条件2(周期性/幅度一致): {np.sum(condition2)}/{len(diffs)}")
        logger.info(f"  条件3(与GR无关): {np.sum(condition3)}/{len(diffs)}")
        logger.info(f"  综合候选弹簧段点数: {np.sum(spring_mask)}/{len(diffs)}")
        
        # 合并连续的弹簧段候选点
        spring_segments = []
        in_spring = False
        start_depth = None
        
        for i in range(len(spring_mask)):
            if spring_mask[i]:
                if not in_spring:
                    in_spring = True
                    start_depth = valid_depth[i]
            else:
                if in_spring:
                    in_spring = False
                    end_depth = valid_depth[i]
                    # 只有长度超过一定阈值的才认为是弹簧段
                    if end_depth - start_depth > min_segment_length:
                        spring_segments.append((start_depth, end_depth))
        
        # 处理最后一个弹簧段
        if in_spring and start_depth is not None:
            end_depth = valid_depth[-1]
            if end_depth - start_depth > min_segment_length:
                spring_segments.append((start_depth, end_depth))
        
        # 进一步验证每个候选弹簧段
        validated_segments = []
        for start_depth, end_depth in spring_segments:
            seg_mask = (valid_depth >= start_depth) & (valid_depth <= end_depth)
            seg_curve = valid_curve[seg_mask]
            seg_diffs = np.abs(np.diff(seg_curve))
            
            if len(seg_diffs) >= 5:
                # 验证1：跳跃频率
                jump_count = np.sum(seg_diffs > threshold)
                jump_freq = jump_count / len(seg_diffs)
                
                # 验证2：幅度一致性
                jump_amps = seg_diffs[seg_diffs > threshold]
                if len(jump_amps) >= 3:
                    amp_mean = np.mean(jump_amps)
                    amp_std = np.std(jump_amps)
                    amp_consistency = amp_std / amp_mean if amp_mean > 0 else 1.0
                else:
                    amp_consistency = 1.0
                
                # 验证3：与GR的相关性
                gr_corr = 1.0
                if 'GR' in data.columns:
                    gr_seg = gr_data[seg_mask]
                    gr_seg_diffs = np.abs(np.diff(gr_seg))
                    if len(gr_seg_diffs) >= 3 and np.std(seg_diffs) > 0 and np.std(gr_seg_diffs) > 0:
                        gr_corr = np.abs(np.corrcoef(seg_diffs, gr_seg_diffs)[0, 1])
                
                # 综合验证：跳跃频率高，幅度一致，与GR无关
                if jump_freq > 0.2 and amp_consistency < 0.6 and gr_corr < 0.4:
                    validated_segments.append((start_depth, end_depth))
                    logger.info(f"  验证通过弹簧段: {start_depth:.1f}m - {end_depth:.1f}m")
                    logger.info(f"    跳跃频率: {jump_freq:.2f}, 幅度一致性: {amp_consistency:.2f}, GR相关性: {gr_corr:.2f}")
        
        spring_segments = validated_segments
        
        logger.info(f"{curve_name} 曲线检测到 {len(spring_segments)} 个弹簧段")
        if spring_segments:
            for seg in spring_segments:
                logger.info(f"  - 弹簧段: {seg[0]:.1f}m - {seg[1]:.1f}m")
        
        return spring_segments
    
    def _spline_smoothing(self, data, curve_name, start_depth, end_depth):
        """
        使用样条插值平滑校正弹簧段
        """
        # 获取弹簧段内的数据
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        spring_data = data[mask].copy()
        
        if len(spring_data) < 3:
            return data
        
        # 获取弹簧段前后的数据作为锚点
        before_mask = data['MD'] < start_depth
        after_mask = data['MD'] > end_depth
        
        if not before_mask.any() or not after_mask.any():
            return data
        
        # 获取前后各5个点作为锚点
        before_points = data[before_mask].tail(5)
        after_points = data[after_mask].head(5)
        
        # 合并锚点和弹簧段数据
        combined = pd.concat([before_points, spring_data, after_points])
        
        # 使用样条插值
        from scipy.interpolate import make_interp_spline
        
        x = combined['MD'].values
        y = combined[curve_name].values
        
        # 创建样条函数
        spline = make_interp_spline(x, y, k=3)
        
        # 对弹簧段内的深度进行插值
        spring_depths = spring_data['MD'].values
        corrected_values = spline(spring_depths)
        
        # 更新数据
        result = data.copy()
        result.loc[mask, curve_name] = corrected_values
        
        return result
    
    def _moving_average_smoothing(self, data, curve_name, start_depth, end_depth, window_size=3):
        """
        使用移动平均平滑校正弹簧段
        """
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        
        if not mask.any():
            return data
        
        # 使用移动平均
        result = data.copy()
        result.loc[mask, curve_name] = result[curve_name].rolling(window_size, center=True, min_periods=1).mean()
        
        return result
    
    def _median_filter(self, data, curve_name, start_depth, end_depth, window_size=3):
        """
        使用中值滤波校正弹簧段
        """
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        
        if not mask.any():
            return data
        
        # 使用中值滤波
        result = data.copy()
        result.loc[mask, curve_name] = result[curve_name].rolling(window_size, center=True, min_periods=1).median()
        
        return result
    
    def correct_spring_segments(self, data, curve_names=None, depth_range=None, method='spline', spring_segments=None):
        """
        校正弹簧段（使用预检测的弹簧段）
        参数:
            data: 测井数据DataFrame
            curve_names: 要校正的曲线名称列表，默认为['MSFL', 'RHOB']
            depth_range: 要校正的深度范围 (start_depth, end_depth)
            method: 校正方法 'spline', 'moving_average', 'median'
            spring_segments: 预检测的弹簧段列表，[(start_depth, end_depth), ...]
        
        返回:
            校正后的数据
        """
        if curve_names is None:
            curve_names = ['MSFL', 'RHOB']
        
        result = data.copy()
        
        # 如果没有提供预检测的弹簧段，使用深度范围作为单一弹簧段
        if spring_segments is None:
            if depth_range is not None:
                spring_segments = [depth_range]
            else:
                logger.info("没有弹簧段需要校正")
                return result
        
        # 如果指定了深度范围，只处理该范围内的弹簧段
        if depth_range is not None:
            start_range, end_range = depth_range
            spring_segments = [(s, e) for s, e in spring_segments 
                               if s >= start_range and e <= end_range]
        
        logger.info(f"校正弹簧段数量: {len(spring_segments)}")
        
        for curve_name in curve_names:
            if curve_name not in data.columns:
                logger.warning(f"曲线 {curve_name} 不存在，跳过校正")
                continue
            
            # 对每个弹簧段进行校正
            for start_depth, end_depth in spring_segments:
                logger.info(f"  校正 {curve_name}: {start_depth:.1f}m - {end_depth:.1f}m")
                if method == 'spline':
                    result = self._spline_smoothing(result, curve_name, start_depth, end_depth)
                elif method == 'moving_average':
                    result = self._moving_average_smoothing(result, curve_name, start_depth, end_depth)
                elif method == 'median':
                    result = self._median_filter(result, curve_name, start_depth, end_depth)
                else:
                    logger.warning(f"未知的校正方法: {method}")
            
            # 添加校正标记（只标记实际校正过的弹簧段）
            result[f'{curve_name}_corrected'] = False
            for start_depth, end_depth in spring_segments:
                result.loc[(result['MD'] >= start_depth) & (result['MD'] <= end_depth), f'{curve_name}_corrected'] = True
        
        return result
    
    def run_spring_correction(self, data, curve_names=None, detect_curve='RHOB', depth_range=None, method='spline'):
        """
        运行弹簧段校正
        如果没有检测到弹簧段，返回None，不进行校正
        
        参数:
            data: 测井数据DataFrame
            curve_names: 要校正的曲线名称列表，默认为['MSFL', 'RHOB']
            detect_curve: 用于检测弹簧段的曲线（默认RHOB密度曲线）
            depth_range: 要校正的深度范围
            method: 校正方法
        """
        try:
            logger.info("开始弹簧段校正")
            
            if curve_names is None:
                curve_names = ['MSFL', 'RHOB']
            
            # 只使用detect_curve检测弹簧段
            all_segments = {}
            if detect_curve in data.columns:
                segments = self.detect_spring_segments(data, detect_curve)
                all_segments[detect_curve] = segments
                total_segments = len(segments)
                logger.info(f"基于 {detect_curve} 曲线检测到 {len(segments)} 个弹簧段")
            else:
                logger.warning(f"检测曲线 {detect_curve} 不存在，无法检测弹簧段")
                return None
            
            # 如果没有检测到任何弹簧段，返回None，不进行校正
            if total_segments == 0:
                logger.info("未检测到弹簧段，跳过弹簧段校正")
                return None
            
            # 如果没有指定深度范围，使用检测到的所有弹簧段覆盖的范围
            if depth_range is None:
                all_depths = []
                for segments in all_segments.values():
                    for s, e in segments:
                        all_depths.extend([s, e])
                if all_depths:
                    depth_range = (min(all_depths), max(all_depths))
                    logger.info(f"自动确定校正深度范围: {depth_range}")
            
            # 进行校正（对所有指定曲线使用相同的弹簧段深度范围）
            corrected_data = self.correct_spring_segments(data, curve_names, depth_range, method, all_segments[detect_curve])
            
            logger.info("弹簧段校正完成")
            
            return {
                'data': corrected_data,
                'spring_segments': all_segments,
                'depth_range': depth_range,
                'corrected_curves': curve_names,
                'detect_curve': detect_curve
            }
        except Exception as e:
            logger.error(f"弹簧段校正失败: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- 测井资料处理主类 ---
class WellLogProcessor:
    """测井资料处理主类"""
    
    def __init__(self, config=None):
        """初始化处理器"""
        self.config = config or ConfigManager().get_config()
        self.data_loader = DataLoader()
        self.data_processor = DataProcessor(self.config)
        #self.interpretator = Interpretator(self.config)
        self.data_visualizer = DataVisualizer(self.config.get('output_dir', 'output'))
        self.report_generator = ReportGenerator(self.config.get('output_dir', 'output'))
        self.facies_analyzer = FaciesAnalyzer(self.config.get('output_dir', 'output'))
        self.spring_corrector = SpringSegmentCorrector()
        self.results = {}
    
    def load_data(self, file_path):
        """加载数据"""
        # 使用常规数据加载器
        data = self.data_loader.load_data(file_path)
        if data is not None:
            self.data_processor.set_data(data)
            self.results['raw_data'] = data
            
            # 优先使用从LAS文件读取的井名
            las_well_info = self.data_loader.get_las_well_info()
            if las_well_info and las_well_info.get('well_name'):
                self.well_name = str(las_well_info['well_name']).strip()
            else:
                # 如果LAS文件中没有井名，从文件路径提取
                file_path = Path(file_path)
                full_name = file_path.stem  # 文件名不含扩展名
                self.well_name = full_name
            
            # 更新输出目录为 output/井名
            well_output_dir = Path('output') / self.well_name
            well_output_dir.mkdir(exist_ok=True, parents=True)
            
            # 更新配置和所有模块的输出目录
            self.config['output_dir'] = str(well_output_dir)
            self.data_processor.output_dir = well_output_dir
            self.data_visualizer = DataVisualizer(str(well_output_dir))
            self.report_generator = ReportGenerator(str(well_output_dir))
            self.facies_analyzer = FaciesAnalyzer(str(well_output_dir))
            
            # 将井名添加到results字典中
            self.results['well_name'] = self.well_name
            
            logger.info(f"Data loaded successfully，井名: {self.well_name}")
            logger.info(f"输出目录已设置为: {well_output_dir}")
        return data
    
    def run_workflow(self, file_path=None):
        """运行完整工作流"""
        logger.info("Starting well log processing workflow")
        
        try:
            # 检查数据是否加载
            if self.data_processor.data is None or len(self.data_processor.data) == 0:
                # 使用文件选择对话框
                logger.info("打开文件选择对话框...")
                data = self.data_loader.load_data_from_file()
                
                if data is None:
                    # 如果用户取消选择，直接返回None
                    logger.info("用户取消选择文件，程序终止")
                    print("\n用户取消选择文件，程序终止")
                    return None
                else:
                    # 设置数据
                    self.data_processor.set_data(data)
                    self.results['raw_data'] = data
                    
                    # 优先使用从LAS文件读取的井名
                    las_well_info = self.data_loader.get_las_well_info()
                    if las_well_info and las_well_info.get('well_name'):
                        self.well_name = str(las_well_info['well_name']).strip()
                    else:
                        # 如果LAS文件中没有井名，从文件路径提取
                        file_path = Path(self.data_loader.last_file_path)
                        full_name = file_path.stem  # 文件名不含扩展名
                        self.well_name = full_name
                    
                    # 更新输出目录为 output/井名
                    well_output_dir = Path('output') / self.well_name
                    well_output_dir.mkdir(exist_ok=True, parents=True)
                    
                    # 更新配置和所有模块的输出目录
                    self.config['output_dir'] = str(well_output_dir)
                    self.data_processor.output_dir = well_output_dir
                    self.data_visualizer = DataVisualizer(str(well_output_dir))
                    self.report_generator = ReportGenerator(str(well_output_dir))
                    self.facies_analyzer = FaciesAnalyzer(str(well_output_dir))
                    
                    # 将井名添加到results字典中
                    self.results['well_name'] = self.well_name
                    
                    logger.info(f"Data loaded successfully，井名: {self.well_name}")
                    logger.info(f"输出目录已设置为: {well_output_dir}")
            elif file_path:
                # 如果数据已加载且提供了file_path，确保井名和输出目录正确设置
                # 优先使用从LAS文件读取的井名
                las_well_info = self.data_loader.get_las_well_info()
                if las_well_info and las_well_info.get('well_name'):
                    self.well_name = str(las_well_info['well_name']).strip()
                else:
                    file_path = Path(file_path)
                    self.well_name = file_path.stem  # 文件名不含扩展名
                
                # 更新输出目录为 output/井名
                well_output_dir = Path('output') / self.well_name
                well_output_dir.mkdir(exist_ok=True, parents=True)
                
                # 更新配置和所有模块的输出目录
                self.config['output_dir'] = str(well_output_dir)
                self.data_processor.output_dir = well_output_dir
                self.data_visualizer = DataVisualizer(str(well_output_dir))
                self.report_generator = ReportGenerator(str(well_output_dir))
                self.facies_analyzer = FaciesAnalyzer(str(well_output_dir))
                
                # 将井名添加到results字典中
                self.results['well_name'] = self.well_name
                
                logger.info(f"使用已加载的数据，井名: {self.well_name}")
                logger.info(f"输出目录已设置为: {well_output_dir}")
            
            # 1. 数据质量检查
            if self.config['quality_check']:
                logger.info("Step 1: Data quality check")
                qc_report = self.data_processor.data_quality_check()
                if qc_report:
                    self.results['qc_report'] = qc_report
                
                # 从DataLoader的2012国标逐曲线评价中获取密度曲线质量标志
                loader_qc = getattr(self.data_loader, 'qc_report', {})
                curve_quality_2012 = loader_qc.get('check_items', {}).get('curve_quality_2012', {})
                den_priority = loader_qc.get('density_porosity_priority', None)
                
                if den_priority is not None:
                    self.results['density_porosity_priority'] = den_priority
                    self.results['density_curve_quality'] = loader_qc.get('density_curve_quality', '未知')
                    self.results['curve_quality_2012'] = curve_quality_2012
                    # 同时存储到DataProcessor.results中，供后续计算使用
                    self.data_processor.results['density_porosity_priority'] = den_priority
                    self.data_processor.results['density_curve_quality'] = loader_qc.get('density_curve_quality', '未知')
                    # 传递到多矿物分析器，控制矿物优化的初始孔隙度计算方法
                    self.facies_analyzer.mineral_analyzer.use_density_porosity = den_priority
                    if den_priority:
                        logger.info("密度曲线质量合格，后续将优先使用密度孔隙度（变骨架）")
                    else:
                        logger.warning("密度曲线质量不佳，孔隙度计算将以其他方法为主")
            
            # 检查有效曲线数量
            # 有效曲线包括：GR, RT/LLD/ILD, DEN/RHOB, NPHI/CNL, DT/AC
            valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC']
            available_curves = [curve for curve in valid_curves if curve in self.data_processor.data.columns]
            
            # 逐井段统计有效曲线数量（用于后续逐段判断）
            logger.info("统计逐井段有效曲线数量")
            data = self.data_processor.data.copy()
            data = self._count_valid_curves_per_segment(data)
            self.results['processed_data'] = data
            
            # 如果整个井的有效曲线少于3条，跳过后续处理（岩性、沉积相、测井解释和可视化）
            if len(available_curves) < 3:
                logger.warning(f"有效曲线数量不足（{len(available_curves)}条），跳过岩性、沉积相分析和可视化")
                print(f"\n警告：有效曲线数量不足（{len(available_curves)}条），已跳过岩性、沉积相分析和可视化")
                return self.results
            
            # 2. 弹簧段校正（基于密度变化检测，校正时同时校正RHOB和MSFL）
            logger.info("Step 2: Spring segment correction")
            
            # 检测时只用RHOB，但校正时同时校正RHOB和MSFL
            detect_curve = 'RHOB'
            correct_curves = ['RHOB', 'MSFL']
            available_correct_curves = [curve for curve in correct_curves if curve in self.data_processor.data.columns]
            
            if detect_curve in self.data_processor.data.columns:
                spring_results = self.spring_corrector.run_spring_correction(
                    self.data_processor.data.copy(),
                    curve_names=available_correct_curves,
                    detect_curve=detect_curve,
                    depth_range=None,
                    method='spline'
                )
                if spring_results:
                    self.results['spring_correction'] = spring_results
                    # 保留VALID_CURVES_COUNT列
                    corrected_data = spring_results['data']
                    if 'VALID_CURVES_COUNT' in self.results['processed_data'].columns:
                        corrected_data['VALID_CURVES_COUNT'] = self.results['processed_data']['VALID_CURVES_COUNT']
                    self.results['processed_data'] = corrected_data
                    logger.info(f"弹簧段校正完成，校正曲线: {available_correct_curves}")
                else:
                    logger.info("未检测到弹簧段，跳过弹簧段校正")
            else:
                logger.info("未找到MSFL或RHOB曲线，跳过弹簧段校正")
            
            # 3. 岩性识别和沉积相分析
            logger.info("Step 2: Lithology识别和沉积相分析")
            try:
                # 获取井名，优先使用从LAS文件读取的井名
                well_name = getattr(self, 'well_name', 'Unknown')
                
                # 使用处理后的数据进行岩性分析
                if 'processed_data' in self.results and self.results['processed_data'] is not None:
                    # 检查有效曲线数量，至少需要3条曲线才能进行岩性和沉积相分析
                    valid_curves = ['GR', 'SP', 'LLS', 'CAL', 'PE', 'MSFL', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC']
                    data = self.results['processed_data']
                    available_curves = [curve for curve in valid_curves if curve in data.columns]
                    
                    if len(available_curves) > 2:
                        facies_results = self.facies_analyzer.run_facies_analysis(
                            data.copy(), 
                            well_name=well_name
                        )
                    else:
                        logger.info(f"有效曲线数量不足（{len(available_curves)}条），跳过岩性和沉积相分析")
                        facies_results = None
                    if facies_results:
                        self.results['facies_analysis'] = facies_results
                        # 更新处理后的数据，包含岩性和沉积相信息
                        self.results['processed_data'] = facies_results['data']
                        
                        # 4. 生成SwINTERPRETATION列
                        data = self.results['processed_data']

                        # 全局PHI限制：不超过0.4（40%）
                        # 超过的可能是气层效应、井眼扩大或中子孔隙度异常
                        if 'PHI' in data.columns:
                            over_mask = data['PHI'] > 0.4
                            over_count = over_mask.sum()
                            if over_count > 0:
                                # 记录clip前的PHI，用于后续矿物重归一化
                                phi_before = data['PHI'].copy()
                                data['PHI'] = data['PHI'].clip(0, 0.4)
                                logger.info(f"全局PHI限制：{over_count}个点PHI>0.4已限制到0.4")
                                
                                # PHI被截断后，矿物总和不再等于1-PHI
                                # 需要按比例缩放矿物，使 sum(minerals) = 1 - PHI_new
                                mineral_cols = [c for c in ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite', 'VClay']
                                                if c in data.columns]
                                if mineral_cols:
                                    mineral_sum = data[mineral_cols].sum(axis=1)
                                    target_sum = 1.0 - data['PHI']
                                    # 仅对PHI被截断且矿物总和>0的点进行缩放
                                    need_fix = over_mask & (mineral_sum > 0.001)
                                    if need_fix.sum() > 0:
                                        scale = target_sum[need_fix] / mineral_sum[need_fix]
                                        for col in mineral_cols:
                                            data.loc[need_fix, col] = data.loc[need_fix, col] * scale
                                        logger.info(f"PHI截断后矿物重归一化：{need_fix.sum()}个点")

                        # 确保VSH（泥质含量）列存在
                        if 'VSH' not in data.columns and 'SH' in data.columns:
                            # 注意：这里SH是含烃饱和度，不是泥质含量，应该使用其他方法计算VSH
                            # 暂时使用默认值
                            data['VSH'] = 0.0
                        
                        # ========== 剖面类型判定（砂泥岩 vs 碳酸盐岩）==========
                        sand_shale_liths = ['sandstone', 'shale', '砂岩', '泥岩', 'sandy_shale', 'shaly_sand']
                        carbonate_liths = ['limestone', 'dolomite', 'carbonate', '灰岩', '白云岩', '碳酸盐岩']
                        if 'LITHOLOGY' in data.columns:
                            lith_counts = data['LITHOLOGY'].value_counts()
                            ss_count = sum(v for k, v in lith_counts.items() 
                                         if str(k).lower() in [s.lower() for s in sand_shale_liths])
                            cb_count = sum(v for k, v in lith_counts.items() 
                                         if str(k).lower() in [c.lower() for c in carbonate_liths])
                            is_sand_shale_profile = ss_count > cb_count
                            logger.info(f"剖面判定: 砂泥岩段={ss_count}, 碳酸盐岩段={cb_count}, "
                                      f"→ {'砂泥岩剖面' if is_sand_shale_profile else '碳酸盐岩/混合剖面'}")
                        else:
                            is_sand_shale_profile = False
                            logger.info("无LITHOLOGY列，默认按碳酸盐岩/混合剖面处理")
                        
                        # ========== 使用7种方法计算孔隙度 ==========
                        # 将processed_data中的曲线列同步到data_processor.data
                        # 确保data_processor有最新的测井曲线数据
                        sync_cols = ['GR', 'SP', 'RHOB', 'NPHI', 'DT', 'DTCO', 'AC', 'PE', 'RT', 'CAL', 
                                     'LLD', 'LLS', 'MSFL', 'PEF', 'VSH', 'SH']
                        for col in sync_cols:
                            if col in data.columns and col not in self.data_processor.data.columns:
                                self.data_processor.data[col] = data[col].values
                            elif col in data.columns and col in self.data_processor.data.columns:
                                self.data_processor.data[col] = data[col].values
                        
                        # 同步LITHOLOGY列
                        for lith_col in ['LITHOLOGY', 'LITHOLOGY_EN']:
                            if lith_col in data.columns:
                                self.data_processor.data[lith_col] = data[lith_col].values
                        
                        # 同步_POROSITY_VALID（用于顶部/底部无效段检测）
                        if '_POROSITY_VALID' in data.columns:
                            self.data_processor.data['_POROSITY_VALID'] = data['_POROSITY_VALID'].values
                        
                        # 将剖面类型传递给孔隙度计算模块
                        self.data_processor.results['profile_type'] = 'sand_shale' if is_sand_shale_profile else 'carbonate'
                        
                        # 使用7种方法计算孔隙度（详见calculate_porosity方法）
                        self.data_processor.calculate_porosity()
                        
                        # 将计算结果复制回processed_data
                        phi_result_cols = ['PHI', 'PORD', 'PHI_SOURCE', 
                                           'PHI_DEN_SHALE', 'PHI_SONIC_SHALE', 'PHI_CNL_SHALE',
                                           'PHI_ND_WEIGHTED', 'PHI_CROSS_LITHO', 'PHI_ND_MEAN', 'PHI_NS_MEAN',
                                           'PHI_NMR']
                        for col in phi_result_cols:
                            if col in self.data_processor.data.columns:
                                data[col] = self.data_processor.data[col].values
                        
                        phi_valid = data['PHI'].notna().sum()
                        phi_mean = data['PHI'].mean()
                        logger.info(f"孔隙度计算完成: PHI有效={phi_valid}/{len(data)}, 均值={phi_mean:.3f}")
                        
                        # 计算Sw（含水饱和度）
                        # 注意：calculate_saturation（run_mineral_analysis中）已用阿尔奇公式计算 Sw
                        # 此时如果'Sw'已存在，则使用计算值，避免被原始LAS的SW默认填充值(1.0)覆盖
                        if 'Sw' in data.columns:
                            logger.info(f"Sw已存在（来自calculate_saturation），范围: {data['Sw'].min():.3f}-{data['Sw'].max():.3f}，跳过重算")
                        elif 'SW' in data.columns:
                            data['Sw'] = data['SW']
                            data['Sw'] = data['Sw'].clip(0, 1)
                            logger.info(f"使用原始SW列，Sw范围: {data['Sw'].min():.3f}-{data['Sw'].max():.3f}")
                        elif 'RT' in data.columns and 'PHI' in data.columns:
                            # 设置默认参数
                            Rw = 0.05  # 地层水Resistivity，单位欧姆·米
                            a = 1.0    # 阿尔奇系数a
                            m = 2.0    # 阿尔奇系数m（胶结指数）
                            n = 2.0    # 阿尔奇系数n（饱和度指数）
                            
                            # 计算Sw
                            # 使用阿尔奇公式：Sw = (a * Rw / (φ^m * RT))^(1/n)
                            data['Sw'] = (a * Rw / (data['PHI']**m * data['RT']))**(1/n)
                            data['Sw'] = data['Sw'].clip(0, 1)
                            
                            # 如果泥质含量较高，使用西门度公式
                            if 'VSH' in data.columns:
                                Rsh = 2.0  # 泥质Resistivity，单位欧姆·米
                                # 西门度公式：Sw = (a * Rw / (φ^m * RT) + Sh / Rsh)^(-1)
                                data.loc[data['VSH'] > 0.2, 'Sw'] = (a * Rw / (data.loc[data['VSH'] > 0.2, 'PHI']**m * data.loc[data['VSH'] > 0.2, 'RT']) + 
                                                                      data.loc[data['VSH'] > 0.2, 'VSH'] / Rsh)**(-1)
                                data['Sw'] = data['Sw'].clip(0, 1)
                        else:
                            # 如果缺少必要参数，使用简化计算
                            data['Sw'] = 0.0
                        
                        # 生成INTERPRETATION列
                        import numpy as np
                        results = []   
                        
                        # 全局归一化范围
                        GLOBAL_RANGES = {
                            'RT': {'min': 0.1, 'max': 1000.0},
                            'SW': {'min': 0.05, 'max': 1.0},
                            'PHI': {'min': 0.02, 'max': 0.35},
                            'VSH': {'min': 0.0, 'max': 0.60}
                        }
                        
                        # 使用高级解释引擎（如果可用）
                        if HAS_ADVANCED_INTERPRETATION:
                            # 创建解释引擎
                            engine = create_interpretation_engine()
                            
                            # 特征映射 - 动态检测可用列名
                            # 电阻率: 优先 RT > LLD > RDEEP > AT90 > ILD
                            rt_col = 'RT'
                            for candidate in ['RT', 'LLD', 'RDEEP', 'AT90', 'ILD', 'RLA5']:
                                if candidate in data.columns:
                                    rt_col = candidate
                                    break
                            
                            # 泥质含量: 优先 VSH > VSH_GR，否则从GR计算
                            vsh_col = None
                            for candidate in ['VSH', 'VSH_GR', 'SH']:
                                if candidate in data.columns:
                                    vsh_col = candidate
                                    break
                            if vsh_col is None and 'GR' in data.columns:
                                # 从自然伽马计算泥质含量: VSH = (GR - GRmin) / (GRmax - GRmin)
                                gr_valid = data['GR'][(data['GR'] > 0) & (data['GR'] < 500)].dropna()
                                gr_min = gr_valid.min() if len(gr_valid) > 0 else 0
                                gr_max = gr_valid.max() if len(gr_valid) > 0 else 200
                                if gr_max > gr_min:
                                    data['VSH'] = ((data['GR'] - gr_min) / (gr_max - gr_min)).clip(0, 1)
                                else:
                                    data['VSH'] = 0.0
                                vsh_col = 'VSH'
                            if vsh_col:
                                features_map = {
                                    'RT': rt_col,
                                    'SW': 'Sw',
                                    'PHI': 'PHI',
                                    'VSH': vsh_col
                                }
                            else:
                                features_map = {
                                    'RT': rt_col,
                                    'SW': 'Sw',
                                    'PHI': 'PHI'
                                }
                            logger.info(f"特征映射: {features_map}")
                            
                            # 对每一层进行解释
                            for idx in range(len(data)):
                                row = data.iloc[idx]
                                
                                # 有效曲线不足3条的井段不解释，设为空字符串
                                valid_count = row.get('VALID_CURVES_COUNT', 0)
                                if valid_count < 3:
                                    data.at[idx, 'INTERPRETATION'] = ''
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    continue
                                
                                # ========== 统一储层过滤 ==========
                                # 非储层不解释油气水干层——从源头拦截
                                lithology = row.get('LITHOLOGY', '其他')
                                carbonate_lithologies = ['灰岩', '白云岩', '碳酸盐岩', 'limestone', 'dolomite', 'carbonate']
                                min_porosity = 0.06 if lithology in carbonate_lithologies else 0.08
                                
                                phi_val = row.get('PHI', row.get('POR', 0))
                                vsh_val = row.get('VSH', row.get('VSHALE', 0))
                                gr_val = row.get('GR', -1)
                                lith_lower = str(lithology).lower().strip() if lithology else ''
                                
                                non_reservoir_keywords = [
                                    '泥岩', 'shale', 'shaly', 'shaley',
                                    '硬石膏', 'anhydrite',
                                    '石膏', 'gypsum',
                                    '岩盐', 'halite',
                                    '火山岩', 'volcanic',
                                    '煤层', 'coal',
                                    '黄铁矿', 'pyrite',
                                    'sandy_shale', 'sandstone_shale',
                                ]
                                
                                reasons = []
                                if phi_val < min_porosity:
                                    reasons.append(f"PHI={phi_val:.3f}<{min_porosity}")
                                if vsh_val > 0.40:
                                    reasons.append(f"VSH={vsh_val:.3f}>0.40")
                                if 0 <= gr_val <= 120:
                                    pass  # GR正常
                                elif gr_val > 120:
                                    reasons.append(f"GR={gr_val:.0f}>120")
                                if any(kw in lith_lower for kw in non_reservoir_keywords):
                                    reasons.append(f"岩性={lithology}")
                                
                                if reasons:
                                    data.at[idx, 'INTERPRETATION'] = 'NonReservoir'
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    continue
                                
                                # 构建特征字典
                                unknown = {}
                                for std_name, col_name in features_map.items():
                                    if col_name in data.columns:
                                        unknown[std_name] = row[col_name]
                                
                                if len(unknown) < 3:
                                    data.at[idx, 'INTERPRETATION'] = 'Undefined'
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    continue
                                
                                # 解释单层
                                result = engine.interpret_layer(
                                    unknown,
                                    global_ranges=GLOBAL_RANGES,
                                    log_features=['RT']
                                )
                                
                                # 保存解释结果（使用英文结论避免乱码）
                                conclusion_en = result.get('conclusion_en', result['conclusion'])
                                
                                # ========== 干层储层验证 ==========
                                # 干层首先是储层！非储层（孔隙度<下限、泥质含量过高、高GR）不能判为干层
                                # 干层 = 有孔隙度但被钙质/硅质胶结物充填，渗透性差的储层
                                if conclusion_en == 'DRY':
                                    phi_val = row.get('PHI', row.get('POR', 0))
                                    vsh_val = row.get('VSH', row.get('VSHALE', 0))
                                    gr_val = row.get('GR', -1)
                                    
                                    # 储层必要条件1：孔隙度 ≥ 储层下限
                                    is_reservoir_porosity = phi_val >= min_porosity
                                    
                                    # 储层必要条件2：泥质含量不能过高（VSH>40%→非储层）
                                    is_reservoir_vsh = vsh_val <= 0.40
                                    
                                    # 储层必要条件3：GR不能过高（GR>120API→泥岩段）
                                    is_reservoir_gr = (gr_val < 0) or (gr_val <= 120)
                                    
                                    # 储层必要条件4：不能是泥岩/蒸发岩/火山岩等非储层岩性（大小写容错）
                                    non_reservoir_keywords = [
                                        '泥岩', 'shale',
                                        '硬石膏', 'anhydrite',
                                        '石膏', 'gypsum',
                                        '岩盐', 'halite',
                                        '火山岩', 'volcanic',
                                        '煤层', 'coal',
                                        '黄铁矿', 'pyrite',
                                        'sandstone_shale', 'sandy_shale',
                                        'shaly', 'shaley',
                                    ]
                                    lith_lower = str(lithology).lower().strip() if lithology else ''
                                    is_reservoir_lithology = not any(
                                        kw in lith_lower for kw in non_reservoir_keywords
                                    )
                                    
                                    if not (is_reservoir_porosity and is_reservoir_vsh and is_reservoir_gr and is_reservoir_lithology):
                                        conclusion_en = 'TIGHT'
                                        reasons = []
                                        if not is_reservoir_porosity:
                                            reasons.append(f"PHI={phi_val:.3f}<{min_porosity}")
                                        if not is_reservoir_vsh:
                                            reasons.append(f"VSH={vsh_val:.3f}>0.40")
                                        if not is_reservoir_gr:
                                            reasons.append(f"GR={gr_val:.0f}>120")
                                        if not is_reservoir_lithology:
                                            reasons.append(f"岩性={lithology}")
                                        logger.debug(
                                            f"深度 {row.get('MD', idx):.1f}m: DRY→TIGHT "
                                            f"({'|'.join(reasons)}, 不满足储层条件)"
                                        )
                                
                                data.at[idx, 'INTERPRETATION'] = conclusion_en
                                data.at[idx, 'INTERPRETATION_SCORE'] = result['best_score']
                                data.at[idx, 'DISTANCE'] = result['details']['distance']
                                data.at[idx, 'HIT_RATE'] = result['details']['hit_rate']
                                data.at[idx, 'DIRECTION_SCORE'] = result['details']['direction_score']
                                data.at[idx, 'BETTER_COUNT'] = result['details']['better_than_template_count']
                                
                                results.append({
                                    'MD': row['MD'],
                                    'ITP': conclusion_en,
                                    'ITP_SCORE': result['best_score'],
                                    'DISTANCE': result['details']['distance'],
                                    'HIT_RATE': result['details']['hit_rate'],
                                    'DIRECTION_SCORE': result['details']['direction_score']
                                })
                        else:
                            # 使用简化解释方法
                            similarity_threshold = 0.35 
                            """INTERPRETATION SINGLE CORE POINTS""" 
                            core_params = ['SW', 'VSH', 'RT', 'POR'] 
                            default_templates = { 
                                'GAS': [0.5, 0.3, 50, 15], # 气层 
                                'OIL': [0.50, 0.3, 30, 15], # 油层 
                                'WATER': [0.5, 0.3, 20, 15], # 水层 
                                'DRY': [0.50, 0.3, 40, 15] # 干层 
                            }
                            
                            templates = { 
                               'GAS': [0.5, 0.3, 50, 15], # 气层 
                                'OIL': [0.50, 0.3, 30, 15], # 油层 
                                'WATER': [0.5, 0.3, 20, 15], # 水层 
                                'DRY': [0.50, 0.3, 40, 15] # 干层 
                            }
                            
                            for param in core_params:
                                if param not in data.columns:
                                    if param == 'SW' and 'Sw' in data.columns:
                                        data['SW'] = data['Sw']
                                    elif param == 'VSH':
                                        if 'SH' in data.columns:
                                            data['VSH'] = data['SH']
                                        elif 'GR' in data.columns:
                                            gr_min = data['GR'].min()
                                            gr_max = data['GR'].max()
                                            data['VSH'] = ((data['GR'] - gr_min) / (gr_max - gr_min)).clip(0, 1) if gr_max > gr_min else 0.0
                                        else:
                                            data[param] = 0
                                    elif param == 'RT' and 'LLD' in data.columns:
                                        data['RT'] = data['LLD']
                                    elif param == 'POR' and 'PHI' in data.columns:
                                        data['POR'] = data['PHI']
                                    else:
                                        data[param] = 0
                            
                            target_values = data[core_params].values 
                            
                            for idx in range(len(data)):
                                row = data.iloc[idx]
                                
                                # 有效曲线不足3条的井段不解释，设为空字符串
                                valid_count = row.get('VALID_CURVES_COUNT', 0)
                                if valid_count < 3:
                                    data.at[idx, 'INTERPRETATION'] = ''
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    results.append({
                                        'MD': row['MD'],
                                        'ITP': 'Undefined'
                                    })
                                    continue
                                
                                # ========== 统一储层过滤（简化路径） ==========
                                lithology = row.get('LITHOLOGY', '其他')
                                carbonate_lithologies = ['灰岩', '白云岩', '碳酸盐岩', 'limestone', 'dolomite', 'carbonate']
                                min_porosity = 0.06 if lithology in carbonate_lithologies else 0.08
                                
                                phi_val = row.get('PHI', row.get('POR', 0))
                                vsh_val = row.get('VSH', row.get('VSHALE', 0))
                                gr_val = row.get('GR', -1)
                                lith_lower = str(lithology).lower().strip() if lithology else ''
                                
                                non_reservoir_keywords = [
                                    '泥岩', 'shale', 'shaly', 'shaley',
                                    '硬石膏', 'anhydrite',
                                    '石膏', 'gypsum',
                                    '岩盐', 'halite',
                                    '火山岩', 'volcanic',
                                    '煤层', 'coal',
                                    '黄铁矿', 'pyrite',
                                    'sandy_shale', 'sandstone_shale',
                                ]
                                
                                reasons = []
                                if phi_val < min_porosity:
                                    reasons.append(f"PHI={phi_val:.3f}<{min_porosity}")
                                if vsh_val > 0.40:
                                    reasons.append(f"VSH={vsh_val:.3f}>0.40")
                                if gr_val > 120:
                                    reasons.append(f"GR={gr_val:.0f}>120")
                                if any(kw in lith_lower for kw in non_reservoir_keywords):
                                    reasons.append(f"岩性={lithology}")
                                
                                if reasons:
                                    data.at[idx, 'INTERPRETATION'] = 'NonReservoir'
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    results.append({
                                        'MD': row['MD'],
                                        'ITP': 'NonReservoir'
                                    })
                                    continue
                                
                                target = target_values[idx]
                                
                                similarity = {}
                                for fluid_type, template in templates.items():
                                    distance = np.sqrt(np.sum((target - np.array(template)) ** 2))
                                    similarity[fluid_type] = 1 / (1 + distance)
                                
                                valid_types = {k: v for k, v in similarity.items() if v >= similarity_threshold}
                                if valid_types:
                                    result = max(valid_types.items(), key=lambda x: x[1])[0]
                                else:
                                    result = "Undefined"
                                
                                # ========== 干层储层验证（简化路径） ==========
                                # 干层首先是储层！非储层不能判为干层
                                if result == 'DRY':
                                    phi_val = row.get('PHI', row.get('POR', 0))
                                    vsh_val = row.get('VSH', row.get('VSHALE', 0))
                                    gr_val = row.get('GR', -1)
                                    
                                    non_reservoir_keywords = [
                                        '泥岩', 'shale',
                                        '硬石膏', 'anhydrite',
                                        '石膏', 'gypsum',
                                        '岩盐', 'halite',
                                        '火山岩', 'volcanic',
                                        '煤层', 'coal',
                                        '黄铁矿', 'pyrite',
                                        'sandstone_shale', 'sandy_shale',
                                        'shaly', 'shaley',
                                    ]
                                    lith_lower = str(lithology).lower().strip() if lithology else ''
                                    
                                    is_dry_reservoir = (
                                        phi_val >= min_porosity and
                                        vsh_val <= 0.40 and
                                        (gr_val < 0 or gr_val <= 120) and
                                        not any(kw in lith_lower for kw in non_reservoir_keywords)
                                    )
                                    
                                    if not is_dry_reservoir:
                                        result = 'TIGHT'
                                
                                # 直接使用英文存储，不映射到中文
                                data.at[idx, 'INTERPRETATION'] = result
                                data.at[idx, 'INTERPRETATION_SCORE'] = similarity.get(result, 0) if result in similarity else 0
                                data.at[idx, 'DISTANCE'] = 999.0
                                data.at[idx, 'HIT_RATE'] = 0.0
                                data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                data.at[idx, 'BETTER_COUNT'] = 0
                                
                                results.append({
                                        'MD': row['MD'],
                                        'ITP': result
                                    })
                        
                        logger.info(f"Interpretation completed，共 {len(data)} records")
                        # 调试：输出解释结果分布
                        if 'INTERPRETATION' in data.columns:
                            vc = data['INTERPRETATION'].value_counts().to_dict()
                            logger.info(f"DEBUG INTERPRETATION分布: {vc}")
                            logger.info(f"DEBUG data is self.results['processed_data']: {data is self.results['processed_data']}")
                            
                            # ========== 特殊岩性孔隙度归0 ==========
                            # 【2026-10-19 用户定案】归0范围收窄为"特殊岩性"
                            #（膏/盐/煤/火山岩/黄铁矿）：用户明确"石膏是特殊岩性
                            # 归0可以，但灰岩和白云岩不是特殊岩性不能归0"——
                            # 灰岩/白云岩即使解释 NonReservoir 也保留真实孔隙度
                            # 与饱和度（与 logInt.py 保存前 PHI_DISP 同口径）。
                            # 原"NonReservoir 解释一律归0"把 88% 的灰岩段
                            # PHI/Sw 抹成 0，致第5/6道碳酸盐段孔隙度贴边。
                            if 'PHI' in data.columns:
                                # 特殊岩性（煤层、膏盐、盐岩、火山岩等非储层岩性）
                                exclude_liths = ['coal', 'anhydrite', 'salt', 'halite', 'evaporite',
                                                 'volcanic', 'basement', 'tuff', 'basalt', 'granite',
                                                 'pyrite', 'casing',
                                                 '煤层', '膏盐', '盐岩', '硬石膏', '火山岩', '花岗岩',
                                                 '黄铁矿', '套管']
                                special_mask = None
                                if 'LITHOLOGY' in data.columns:
                                    special_mask = data['LITHOLOGY'].astype(str).str.lower().isin(exclude_liths)

                                # 【2026-10-19】不再按 NonReservoir 解释归0：
                                # 灰岩/白云岩/砂岩/泥岩即使非有效储层也保留
                                # 真实 PHI/Sw（"非有效储层"只影响流体结论）
                                if special_mask is not None and special_mask.any():
                                    special_count = special_mask.sum()
                                    data.loc[special_mask, 'PHI'] = 0.0
                                    if 'PORD' in data.columns:
                                        data.loc[special_mask, 'PORD'] = 0.0
                                    # 特殊岩性饱和度也归0：Sw/So/Sg = 0
                                    sat_cols = ['Sw', 'So', 'Sg']
                                    available_sat_cols = [c for c in sat_cols if c in data.columns]
                                    if available_sat_cols:
                                        data.loc[special_mask, available_sat_cols] = 0.0
                                    logger.info(f"特殊岩性孔隙度归0+饱和度归0: {special_count} points "
                                                f"(灰岩/白云岩等正常岩性不归0), "
                                                f"剩余PHI有效点: {data['PHI'].notna().sum()}")

                                # ========== 非储层矿物含量重新分配 ==========
                                # PHI=0的点，矿物含量按比例重新分配使sum(minerals)=1.0
                                # 这样profile道中矿物+孔隙度=100%，且孔隙度为0
                                if non_reservoir_mask is not None and non_reservoir_mask.any():
                                    mineral_cols = ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite',
                                                    'VHalite', 'VClay']
                                    available_mineral_cols = [c for c in mineral_cols if c in data.columns]
                                    if available_mineral_cols:
                                        # 获取特殊岩性点的矿物数据（2026-10-19：
                                        # 只特殊岩性归0并重分配；灰岩/白云岩等
                                        # 正常岩性保留真实 PHI 与矿物比例）
                                        nr_minerals = data.loc[special_mask, available_mineral_cols].copy()
                                        # 计算每行矿物总和
                                        mineral_sum = nr_minerals.sum(axis=1)
                                        # 避免除零：如果矿物总和为0，给泥岩一个默认值
                                        zero_sum = mineral_sum <= 0
                                        if zero_sum.any():
                                            nr_minerals.loc[zero_sum, 'VClay' if 'VClay' in nr_minerals.columns else available_mineral_cols[0]] = 1.0
                                            mineral_sum = nr_minerals.sum(axis=1)
                                        # 按比例重新分配使矿物总和=1.0
                                        nr_minerals = nr_minerals.divide(mineral_sum, axis=0)
                                        nr_minerals = nr_minerals.fillna(0.0)
                                        # 写回数据
                                        data.loc[special_mask, available_mineral_cols] = nr_minerals
                                        # 同步VSAND = VQuartz
                                        if 'VQuartz' in data.columns:
                                            data.loc[special_mask, 'VSAND'] = data.loc[special_mask, 'VQuartz']
                                        # 同步VSH = VClay
                                        if 'VClay' in data.columns:
                                            data.loc[special_mask, 'VSH'] = data.loc[special_mask, 'VClay']
                                        logger.info(f"特殊岩性矿物含量重新分配: {special_mask.sum()} points, "
                                                    f"sum(minerals) now = 1.0, PHI = 0")
                                
                                # ========== 全局归一化保障：确保所有点 minerals + PHI = 1.0 ==========
                                # 经过矿物分析阶段和解释阶段两轮PHI归0后，可能存在体积不平衡
                                # 在此处做一次全局归一化，确保数据一致性
                                logger.info("执行全局矿物+孔隙度归一化保障...")
                                mineral_cols = ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite',
                                                'VHalite', 'VClay']
                                available_mineral_cols = [c for c in mineral_cols if c in data.columns]
                                if available_mineral_cols and 'PHI' in data.columns:
                                    total_volume = data[available_mineral_cols].sum(axis=1) + data['PHI']
                                    # 避免除零：总量为0的点设为默认（全泥岩）
                                    zero_vol_mask = total_volume <= 0
                                    if zero_vol_mask.any():
                                        logger.warning(f"发现{zero_vol_mask.sum()}个体积为0的点，设置为全泥岩")
                                        if 'VClay' in data.columns:
                                            data.loc[zero_vol_mask, 'VClay'] = 1.0
                                            data.loc[zero_vol_mask, 'PHI'] = 0.0
                                        total_volume = data[available_mineral_cols].sum(axis=1) + data['PHI']
                                    # 归一化：确保 minerals + PHI = 1.0
                                    non_zero = total_volume > 0
                                    if non_zero.any():
                                        for col in available_mineral_cols:
                                            data.loc[non_zero, col] = data.loc[non_zero, col] / total_volume[non_zero]
                                        data.loc[non_zero, 'PHI'] = data.loc[non_zero, 'PHI'] / total_volume[non_zero]
                                    # 同步VSAND = VQuartz
                                    if 'VQuartz' in data.columns and 'VSAND' in data.columns:
                                        data['VSAND'] = data['VQuartz']
                                    # 同步VSH = VClay
                                    if 'VClay' in data.columns and 'VSH' in data.columns:
                                        data['VSH'] = data['VClay']
                                    # 验证归一化结果
                                    total_after = data[available_mineral_cols].sum(axis=1) + data['PHI']
                                    max_deviation = (total_after - 1.0).abs().max()
                                    logger.info(f"全局归一化完成: max deviation from 1.0 = {max_deviation:.6f}, "
                                               f"min = {total_after.min():.6f}, max = {total_after.max():.6f}")
                        
                        logger.info("Lithology识别、沉积相分析和测井Interpretation completed")
            except Exception as e:
                logger.error(f"Lithology识别、沉积相分析和Log Interpretation失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 4. 保存处理后数据为CSV文件（包含原始数据 + 处理后数据）
            logger.info("Step 4: 保存处理后数据为CSV文件")
            well_output_dir = Path(self.config.get('output_dir', 'output'))
            well_output_dir.mkdir(exist_ok=True, parents=True)
            
            # 保存处理后数据CSV（包含原始数据 + 岩性、沉积相、解释结论等处理结果）
            if 'processed_data' in self.results and self.results['processed_data'] is not None:
                pd_data = self.results['processed_data']
                if 'INTERPRETATION' in pd_data.columns:
                    vc = pd_data['INTERPRETATION'].value_counts().to_dict()
                    logger.info(f"保存前 INTERPRETATION分布: {vc}")
                else:
                    logger.warning("保存前 INTERPRETATION列不存在!")

                # 全局PHI限制：不超过0.4（40%），在CSV保存前最终确保
                if 'PHI' in pd_data.columns:
                    over_mask = pd_data['PHI'] > 0.4
                    over_count = over_mask.sum()
                    if over_count > 0:
                        pd_data['PHI'] = pd_data['PHI'].clip(0, 0.4)
                        logger.info(f"CSV保存前全局PHI限制：{over_count}个点PHI>0.4已限制到0.4")
                        # PHI截断后矿物重归一化
                        mineral_cols = [c for c in ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite', 'VClay']
                                        if c in pd_data.columns]
                        if mineral_cols:
                            mineral_sum = pd_data[mineral_cols].sum(axis=1)
                            target_sum = 1.0 - pd_data['PHI']
                            need_fix = over_mask & (mineral_sum > 0.001)
                            if need_fix.sum() > 0:
                                scale = target_sum[need_fix] / mineral_sum[need_fix]
                                for col in mineral_cols:
                                    pd_data.loc[need_fix, col] = pd_data.loc[need_fix, col] * scale
                                logger.info(f"CSV保存前矿物重归一化：{need_fix.sum()}个点")

                processed_csv_path = well_output_dir / f"{well_name}_processed.csv"
                self.results['processed_data'].to_csv(processed_csv_path, index=False, encoding='utf-8')
                print(f"处理后数据已保存到: {processed_csv_path}")
                logger.info(f"处理后数据CSV已保存: {processed_csv_path}")
            
            # 将输出目录保存到结果中，供可视化模块使用
            self.results['output_dir'] = str(well_output_dir)
            
            # 将LAS文件信息保存到结果中，供可视化模块使用
            las_info = {
                'well': self.data_loader.get_las_well_info() or {},
                'parameter': self.data_loader.get_las_parameter_info() or {}
            }
            self.results['las_info'] = las_info
            
            # 加载气测数据（可选）
            gas_data = None
            logger.info("Step 5: 气测数据加载（可选，取消跳过）")
            if len(sys.argv) > 1:
                # 命令行模式跳过气测数据对话框
                logger.info("命令行模式，跳过气测数据选择对话框")
                gas_data = None
            else:
                gas_data = self.data_loader.load_gas_data()
            if gas_data is not None and 'MD' in gas_data.columns and len(gas_data) > 0:
                # 保存原始气测数据（对齐前，用于调试）
                self.results['gas_data_raw'] = gas_data.copy()
                logger.info(f"原始气测数据列名: {list(gas_data.columns)}")
                
                # 将气测数据深度对齐到主数据的深度网格
                # 使用 merge_asof 对齐，缺失值用 NaN 填充
                main_data = self.results['processed_data']
                if 'MD' in main_data.columns:
                    # 确保MD列类型一致（merge_asof要求相同dtype）
                    gas_sorted = gas_data.sort_values('MD')
                    gas_sorted['MD'] = gas_sorted['MD'].astype(float)
                    main_sorted = main_data[['MD']].sort_values('MD')
                    main_sorted['MD'] = main_sorted['MD'].astype(float)
                    gas_aligned = pd.merge_asof(
                        main_sorted, gas_sorted, on='MD', direction='nearest', tolerance=1.0
                    )
                    gas_data = gas_aligned.drop(columns=['MD'])
                    # 重建带深度列的气测DataFrame
                    gas_data.insert(0, 'MD', main_sorted['MD'].values)
                    gas_data = gas_data.sort_values('MD').reset_index(drop=True)
                    logger.info(f"气测数据已对齐到主数据深度网格，共 {len(gas_data)} 点")
                    self.results['gas_data'] = gas_data
                else:
                    logger.warning("主数据中缺少MD列，无法对齐气测数据")
                    gas_data = None
            else:
                gas_data = None
            
            # 5. 结果可视化（调用visualize_composite_log函数）- 图片将保存在同一目录下
            if self.config['visualization']:
                logger.info("Step 6: 结果可视化")
                if 'processed_data' in self.results and self.results['processed_data'] is not None:
                    data = self.results['processed_data']
                    # 调用visualize_composite_log函数，传入气测数据
                    viz_result = self.data_visualizer.visualize_composite_log(data, self.results, gas_data=gas_data)
                    if viz_result:
                        self.results['visualization_results'] = viz_result
                else:
                    logger.error("无处理数据可可视化")
            
            # 6. 生成报告
            if self.config['report_generation']:
                logger.info("Step 7: 生成报告")
                report_path = self.report_generator.generate_report(self.results, self.config)
                if report_path:
                    self.results['report_path'] = report_path
            
            logger.info("测井资料处理工作流完成")
            return self.results
            
        except Exception as e:
            logger.error(f"Workflow run failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _count_valid_curves_per_segment(self, data, window_size=50):
        """
        逐井段统计有效曲线数量
        有效曲线：当前深度点的曲线值有效（非NaN、非-999、>0）
        且滑动窗口内有效率>30%（排除单点偶然有效的情况）

        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）

        返回:
            data: 添加了 VALID_CURVES_COUNT 列的DataFrame
        """
        valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'NPH', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC', 'PE', 'LLS', 'MSFL', 'CAL', 'SP']

        valid_counts = []

        for i in range(len(data)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(data), i + window_size // 2)

            count = 0
            for curve in valid_curves:
                if curve in data.columns:
                    # 检查当前深度点的值是否有效
                    point_val = data[curve].iloc[i]
                    if pd.isna(point_val) or point_val <= -999 or point_val <= 0:
                        continue
                    # 同时检查窗口内有效率（排除偶然单点有效）
                    window_data = data[curve].iloc[start_idx:end_idx]
                    valid_ratio = (window_data > 0).sum() / len(window_data)
                    if valid_ratio > 0.3:
                        count += 1

            valid_counts.append(count)

        data['VALID_CURVES_COUNT'] = valid_counts
        return data

# --- 主函数 ---
import sys

def run_well_log_workflow():
    """运行测井资料处理工作流"""
    print("\n" + "="*70)
    print("           测井资料处理系统")
    print("="*70)
    print()
    logger.info("="*60)
    logger.info("开始运行测井资料处理工作流")
    logger.info("="*60)
    
    try:
        print("正在初始化处理器...")
        # 创建处理器
        processor = WellLogProcessor()
        print("✓ 处理器初始化成功")
        logger.info("Processor created successfully")
        
        # 检查命令行参数
        if len(sys.argv) > 1:
            # 使用命令行参数作为文件路径
            file_path = sys.argv[1]
            logger.info(f"Getting file path from command line: {file_path}")
            print(f"使用文件: {file_path}")
            
            # 加载数据文件
            print("正在加载数据...")
            logger.info(f"Loading data file: {file_path}")
            data = processor.load_data(file_path)
            
            if data is None:
                logger.error("Failed to load data")
                show_error_message(
                    "数据加载失败",
                    f"无法加载文件: {file_path}",
                    "请检查文件是否存在且格式正确。"
                )
                return
            
            # 运行工作流
            print("正在处理数据...")
            results = processor.run_workflow(file_path)
        else:
            # 没有命令行参数，直接运行工作流，工作流会打开文件选择对话框
            print()
            print("  提示: 若知道数据文件路径，可使用命令行参数:")
            print("        python logInt.py <文件路径>")
            print()
            logger.info("无命令行参数，打开文件选择对话框...")
            results = processor.run_workflow()
        
        if results:
            logger.info("Workflow ran successfully")
            print("\n" + "="*70)
            print("         ✓ 处理完成！")
            print("="*70)
            print()
            print(f"处理结果已保存到: {processor.config.get('output_dir', 'output')}")
            print()
            print("请查看输出目录下的结果文件和可视化图片。")
            print()
        else:
            logger.error("Workflow run failed")
            show_error_message(
                "处理失败",
                "工作流执行失败",
                "请查看日志文件 well_log_processor.log 获取详细信息。"
            )
            
    except KeyboardInterrupt:
        print()
        print("程序已被用户中断。")
        logger.info("Program interrupted by user (KeyboardInterrupt)")
    except Exception as e:
        import traceback
        # 使用统一的异常处理
        handle_exception(type(e), e, e.__traceback__, "程序运行")
        print()
        print("程序异常退出。")


if __name__ == "__main__":
    try:
        run_well_log_workflow()
    except KeyboardInterrupt:
        print()
        print("程序已被用户中断。")
    except Exception as e:
        import traceback
        handle_exception(type(e), e, e.__traceback__, "程序启动")
        print()
        print("程序异常退出。")