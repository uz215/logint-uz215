

# =============================================================================
# 依赖检查模块
# =============================================================================
import sys
import importlib.util

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
import copy
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

# 导入高级测井解释引擎
# 【2026-10-26 并库】advanced_interpretation.py 文件不存在(死导入), 按四程序
# 并库要求移除 try-import, 直接置 False(13730 行的分支行为不变)。
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
            # 【2026-10-08 增强】方法默认 'trend'（趋势分解校正）：段内保留真实
            # 地层趋势、仅扣除螺旋周期振荡，优于 spline（spline 用段外锚点重建
            # 会抹掉段内真实薄层/岩性变化）。
            'spring_correction': {
                'enabled': True,                    # 是否启用弹簧段校正
                'curves': ['MSFL', 'RHOB'],         # 要校正的曲线
                'depth_range': (2710, 2830),        # 弹簧段深度范围（可根据实际数据修改）
                'method': 'trend',                  # 校正方法: trend, spline, moving_average, median
                'sensitivity': 3.0,                 # 检测灵敏度
                # 检测增强开关（螺旋井眼专业判据）
                'detect': {
                    'use_drho': True,               # DRHO/Δρ 异常判据（standoff 直接证据）
                    'use_caliper': True,            # 井径 CALI 周期同步判据
                    'use_cross_curve': True,        # 密度与 MSFL/电阻率跨曲线同步判据
                    'use_gr_independent': True,     # 与 GR 不相关判据（弱证据）
                },
                # 趋势分解校正参数（method='trend' 时生效）
                'trend': {
                    'window_m': 3.0,                # 趋势提取窗口（≈1~2 倍螺旋周期）
                    'residual_ratio': 3.0,          # 振荡/噪声比，超过则判为螺旋振荡并替换
                    'drho_max': 0.15,               # |DRHO| 超过此值（约25mm standoff）视为校正不可靠
                },
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
# 元素测井矿物干重→体积转换颗粒密度 (g/cm³)【2026-10-15 用户要求】
# 元素测井（ECS等）交付的 VOL_* 矿物含量实为干重（质量分数），
# 测井体积模型按体积加权响应，用前必须转换为体积分数
_ELEMENT_VOL_DRY_DENSITY = {
    'CALCITE': 2.71, 'DOLOM': 2.87, 'ANHY': 2.98, 'ILLITE': 2.55,
    'BASALT': 2.90, 'QUARTZ': 2.65, 'KSPAR': 2.56, 'CLAY': 2.55,
    'CHLORITE': 2.80, 'GYPS': 2.32, 'SALT': 2.16, 'COAL': 1.40,
    'PYRITE': 5.01, 'SIDERITE': 3.94, 'HEMATITE': 5.27,
}

def convert_element_vol_dry_to_volume(data):
    """元素测井 VOL_* 矿物含量干重→体积分数原地转换。

    公式：V_i = (W_i/ρ_i) / Σ_j(W_j/ρ_j)——固体部分转换后自动闭合
    （Σ V_mineral = 1），孔隙度另由测井曲线求取，总体积闭合 ΣV+φ=1。
    未知矿物名按泥质密度 2.55 兜底；缺测标记（≤-900）与野值（>2.0）剔除。
    【调用约束】仅在原始 LAS 加载分支调用一次——程序输出的 processed
    CSV/LAS 中 VOL_* 已是体积分数，重复调用会二次转换出错。
    """
    try:
        vol_cols = [c for c in data.columns if str(c).upper().startswith('VOL_')]
        if not vol_cols:
            return data
        w = pd.DataFrame(index=data.index)
        _src_ok = {}
        for c in vol_cols:
            key = str(c).upper()[4:]
            rho = _ELEMENT_VOL_DRY_DENSITY.get(key, 2.55)
            s = pd.to_numeric(data[c], errors='coerce')
            _sv = s.where((s > -900) & (s <= 2.0))
            _src_ok[c] = _sv.notna()
            w[c] = _sv.clip(lower=0).fillna(0.0) / rho
        solid = w.sum(axis=1)
        ok = solid > 1e-6
        if not ok.any():
            return data
        for c in vol_cols:
            v = w[c] / solid.where(ok, 1.0)
            v = v.where(ok, data[c])
            # 【2026-10-26 R24 根因修复】保留缺测语义：源缺测(缺测标记/野值/
            #   NaN)→NaN 而非 0——此前 fillna(0)+clip 把缺测变 0，使
            #   apply_elemental_vsh 把缺测点当"元素=0"直接采用，ECS 缺测段
            #   (111D 顶部 270m)泥质被置 0 且 KTH/GR 外推不触发(泥质充填
            #   断续、与连续伽马脱节的根因)。下游消费方
            #   (refine/矿物分析/arbitrate)均已 fillna(0)/notna 兼容 NaN。
            v = v.where(_src_ok[c])
            data[c] = v.clip(0, 1)
        logger.info('元素测井VOL_*干重→体积转换完成: %d列 V=(W/ρ)/Σ(W/ρ)，矿物=%s',
                    len(vol_cols), ','.join(str(c) for c in vol_cols))
        return data
    except Exception as _e:
        logger.warning('VOL_*干重→体积转换跳过: %s', _e)
        return data

# ---------------- 元素矿物精化（2026-10-16 用户要求） ----------------
# 干重→体积转换后有效元素段 ΣV≈1；ΣV 低于该阈值视为元素无效段
_ELEM_VOL_VALID_MIN = 0.3
# 泥质回归（KTH/GR ↔ VOL_ILLITE）所需最少有效样本数
_ELEM_CLAY_REG_MIN_N = 50

# 无效元素段剩余体积 (1-φ-Vclay) 按已识别岩性分配的目标矿物列；
# 未列出的岩性（shale/coal/未知等）按全泥归并闭合
_LITH_FILL_MINERAL = {
    'limestone': 'VOL_CALCITE', 'carbonate': 'VOL_CALCITE',
    '灰岩': 'VOL_CALCITE', '石灰岩': 'VOL_CALCITE',
    'dolomite': 'VOL_DOLOM', '白云岩': 'VOL_DOLOM',
    'sandstone': 'VOL_QUARTZ', '砂岩': 'VOL_QUARTZ',
    'anhydrite': 'VOL_ANHY', 'gypsum': 'VOL_GYPS',
    'halite': 'VOL_SALT', 'salt': 'VOL_SALT',
    'basalt': 'VOL_BASALT', '玄武岩': 'VOL_BASALT',
    'coal': 'VOL_COAL', '煤': 'VOL_COAL',
}

def refine_element_mineral_volumes(data):
    """元素矿物体积精化：总体闭合 ΣV_mineral+φ=1 + 无效段泥质关联填充。

    用户要求（2026-10-16）：元素含量第一位；VOL_ILLITE 可与 KTH/伽玛关联
    计算元素无效段的泥质含量；总体考虑并满足矿物+孔隙度之和=1。

    1) 有效元素段（非套管且 ΣV≥_ELEM_VOL_VALID_MIN）：保持元素矿物比例，
       仅整体缩放 V_i *= (1-φ)/ΣV 实现闭合（φ 取最终 PHI，缺失按 0）；
    2) 无效元素段（非套管且 ΣV<阈值）：泥质用 KTH（缺失回退 GR）对有效段
       VOL_ILLITE 的线性回归关联计算并截到 (1-φ) 物理上限，剩余体积
       (1-φ-Vclay) 按已识别岩性分配给对应矿物，无岩性映射时归泥闭合；
    3) 套管段与回归不可用段不填充，保持原值。
    需列：VOL_*、PHI、KTH/GR（回归）、LITHOLOGY（分配）；无 VOL_* 直接返回。
    """
    try:
        import numpy as _np
        vol_cols = [c for c in data.columns if str(c).upper().startswith('VOL_')]
        if not vol_cols:
            return data
        v = data[vol_cols].apply(pd.to_numeric, errors='coerce') \
                          .fillna(0.0).clip(0, 1)
        vsum = v.sum(axis=1).values
        if 'IS_CASING' in data.columns:
            casing = pd.Series(data['IS_CASING']).fillna(False) \
                       .astype(bool).values
        else:
            casing = _np.zeros(len(data), dtype=bool)
        valid = (~casing) & (vsum >= _ELEM_VOL_VALID_MIN)
        n_valid = int(valid.sum())
        if n_valid < _ELEM_CLAY_REG_MIN_N:
            logger.info('元素矿物精化跳过: 有效元素点不足(%d<%d)',
                        n_valid, _ELEM_CLAY_REG_MIN_N)
            return data
        phi = (pd.to_numeric(data['PHI'], errors='coerce').fillna(0.0)
               if 'PHI' in data.columns
               else pd.Series(0.0, index=data.index))
        phi = phi.clip(0, 0.95).values

        # ---- 1) 有效段闭合: V_i *= (1-φ)/ΣV（矿物比例不变） ----
        scale = (1.0 - phi) / _np.where(vsum > 1e-6, vsum, 1.0)
        for c in vol_cols:
            data[c] = _np.where(valid, v[c].values * scale, v[c].values)
        logger.info('元素矿物闭合(有效段%d点): ΣV+φ 中位 %.3f → %.3f',
                    n_valid,
                    float(_np.median(vsum[valid] + phi[valid])),
                    float(_np.median(vsum[valid] * scale[valid] + phi[valid])))

        # ---- 2) 无效段泥质关联填充（元素第一位，KTH/GR 补齐+总体闭合） ----
        fill_mask = (~casing) & (~valid)
        n_fill = int(fill_mask.sum())
        if n_fill == 0:
            return data
        ill = 'VOL_ILLITE' if 'VOL_ILLITE' in data.columns else 'VOL_CLAY'
        if ill not in data.columns:
            data[ill] = 0.0
            v[ill] = 0.0
        # 回归目标=闭合后泥质（与输出数据同一尺度；无效点为0不参与拟合）
        y = (v[ill].values * scale).astype(float)

        def _fit_reg(src):
            if src not in data.columns:
                return None, None
            x = pd.to_numeric(data[src], errors='coerce')
            m = valid & x.notna().values & _np.isfinite(y)
            if int(m.sum()) < _ELEM_CLAY_REG_MIN_N:
                return None, None
            xs = x.values[m]
            if float(xs.std()) < 1e-9:
                return None, None
            b = float(((xs - xs.mean()) * (y[m] - y[m].mean())).sum()
                      / max(((xs - xs.mean()) ** 2).sum(), 1e-12))
            a = float(y[m].mean() - b * xs.mean())
            # 泥质恒定时 corrcoef 除零告警，r 记 0（b=0 均值预测仍可用）
            r = (float(_np.corrcoef(xs, y[m])[0, 1])
                 if float(y[m].std()) > 1e-12 else 0.0)
            if not _np.isfinite(r):
                r = 0.0
            return (a, b, r), x

        reg = x = src = None
        for _src in ('KTH', 'GR'):
            reg, x = _fit_reg(_src)
            if reg is not None:
                src = _src
                break
        if reg is None:
            logger.info('元素无效段%d点: KTH/GR 泥质回归不可用(样本/方差不足)，'
                        '保持原值不填充', n_fill)
            return data
        a, b, r = reg
        # 【2026-10-26 R24】逐点兜底：首选源(KTH)缺测的点用次选源(GR)
        # 回归值——与 apply_elemental_vsh 的 KTH/GR 外推同口径，保证泥质
        # 剖面连续(KTH 缺测点此前 clay.fillna(0)=0，造成充填断续)
        _reg2 = _x2 = None
        for _src2 in ('KTH', 'GR'):
            if _src2 == src:
                continue
            _reg2, _x2 = _fit_reg(_src2)
            if _reg2 is not None:
                break
        clay = (a + b * x).clip(0, 1)
        if _reg2 is not None and _x2 is not None:
            _sec = (_reg2[0] + _reg2[1] * _x2).clip(0, 1)
            clay = clay.where(x.notna(), _sec)
        clay = clay.fillna(0.0).values
        clay = _np.clip(clay, 0.0, 1.0 - phi)      # 为孔隙度保留物理空间
        room = _np.clip(1.0 - phi - clay, 0.0, 1.0)
        _orig = pd.to_numeric(data[ill], errors='coerce') \
                  .fillna(0.0).clip(0, 1).values
        # 泥质=回归值写入所有填充点（映射岩性=回归泥质+剩余矿物；未映射=全泥）
        data[ill] = _np.where(fill_mask, clay, _orig)
        if 'LITHOLOGY' in data.columns:
            lith_vals = data['LITHOLOGY'].astype(str).str.lower() \
                                      .str.strip().values
            n_min = 0
            for name, col in _LITH_FILL_MINERAL.items():
                sel = fill_mask & (lith_vals == name)
                if not sel.any():
                    continue
                if col not in data.columns:
                    data[col] = 0.0
                data[col] = _np.where(
                    sel, room,
                    pd.to_numeric(data[col], errors='coerce')
                    .fillna(0.0).clip(0, 1).values)
                n_min += int(sel.sum())
            _mapped = _np.zeros(len(data), dtype=bool)
            for name in _LITH_FILL_MINERAL:
                _mapped |= (lith_vals == name)
            sel_clay = fill_mask & (~_mapped)
            if sel_clay.any():
                # 未映射岩性归泥：泥质=回归值+剩余体积（全泥闭合）
                data[ill] = _np.where(sel_clay, clay + room,
                                      _np.where(fill_mask, clay, _orig))
            logger.info('元素无效段填充%d点: 泥质回归 %s=%.5f%+.5f*%s (r=%.3f)，'
                        '按岩性分配矿物%d点、归泥%d点',
                        n_fill, ill, a, b, src, r, n_min, int(sel_clay.sum()))
        else:
            data[ill] = _np.where(fill_mask, clay + room, _orig)
            logger.info('元素无效段填充%d点: 泥质回归 %s=%.5f%+.5f*%s (r=%.3f)，'
                        '无LITHOLOGY列全部归泥闭合',
                        n_fill, ill, a, b, src, r)
        return data
    except Exception as _e:
        logger.warning('元素矿物精化跳过: %s', _e)
        return data

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
            # 记录本次加载路径（气测自动发现等下游依赖，2026-10-08）：
            # 主流程直接调 load_data 时此前 last_file_path 恒为 None，
            # 导致气测文件自动发现失效、CLI 被对话框阻塞
            self.last_file_path = str(file_path)
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
                    # 【2026-10-15 用户要求】元素测井 VOL_* 交付为干重（质量分数），
                    # 原始LAS加载后立即转换为体积分数（程序输出CSV/LAS已是体积，勿重复转换）
                    self.data = convert_element_vol_dry_to_volume(self.data)
                    info = self._extract_las_info(las)
                    self.file_info = info
                    self.las_info = info  # 向后兼容
                    # 2026-10-09 深度单位修复：综合图深度道此前恒按米制
                    # （logvis.DEPTH_UNIT 默认 auto→_detect 恒返回 'm'），
                    # 英尺井（如 BET-1，STRT.FEET=6307.0）被标成 Depth(m)。
                    # 现从 LAS 深度曲线单位（las.index_unit，即 ~C 区
                    # DEPT.FEET 点后的 FEET）解析，写入 self.depth_unit 并
                    # 同步通知绘图模块；解析失败回退 config.depth_unit。
                    du = None
                    try:
                        _iu = str(getattr(las, 'index_unit', '') or '').strip().upper()
                        if _iu:
                            du = 'ft' if _iu.startswith('F') else (
                                'm' if _iu.startswith('M') else None)
                    except Exception:
                        du = None
                    if not du:
                        _cfg = getattr(self, 'config', None)
                        _cu = (_cfg or {}).get('depth_unit', 'ft') \
                            if isinstance(_cfg, dict) else 'ft'
                        du = 'ft' if str(_cu).strip().lower().startswith('f') else 'm'
                    self.depth_unit = du
                    # 【2026-10-15】深度单位写入 las_info：报告逐层解释等下游
                    # 从 results['las_info']['depth_unit'] 读取真实单位；
                    # 此前该键缺失，报告兜底按"MD中位>10000判英尺井"推断，
                    # 公制深井（如3-SPS-111D，中位6600m）被误标为ft
                    info['depth_unit'] = du
                    # 【2026-10-16 用户要求】LAS 曲线描述智能挖掘：~C 区每条曲线
                    # 的注释描述（descr）写明曲线意义（如 MPHE: MR effective
                    # porosity、SW_CORE: Water saturation predicted using
                    # COREANALYSIS），解析建立语义标签，供核磁孔隙度/渗透率
                    # 选择与综合图岩心点绘制使用
                    self.curve_descriptions = self._mine_curve_semantics(las)
                    try:
                        from logvis import set_depth_unit
                        set_depth_unit(du)
                        logger.info('LAS 深度单位: %s（综合图深度道将按该单位绘制）', du)
                    except Exception:
                        pass
                    # 【2026-10-15】声波DT曲线单位检测：骨架AC特征值英制/公制自适应
                    # （骨架表按英制us/ft存储，灰岩47.5us/ft=公制156us/m）。
                    # 解析失败默认英制（保持历史行为）。
                    _dtu = 'us/ft'
                    try:
                        for _c in las.curves:
                            if str(getattr(_c, 'mnemonic', '') or '').strip().upper() \
                                    in ('DT', 'DTC', 'AC', 'DT4', 'DTS'):
                                _cu_dt = str(getattr(_c, 'unit', '') or '')
                                if _cu_dt.strip():
                                    _dtu = set_dt_curve_unit(_cu_dt)
                                break
                    except Exception:
                        pass
                    logger.info('声波DT曲线单位: %s（骨架AC特征值按该单位换算）', _dtu)
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

            # ========== 曲线名统一归一化(2026-10-08, BET-1) ==========
            # SLAM/LWD成果曲线名(ZDEN/CNCF/DTC/RD/CALX)归一为程序标准名
            # (DEN/CNL/DT/RT/CAL) —— QC的2012国标曲线质量评价此前认不出CNCF
            # 为中子, 导致评价错位/声波误判不合格; 归一化后QC/岩性/孔隙度/
            # 绘图/解释全流程共用统一口径。须在大写化之后执行(别名表全大写)。
            self.data = standardize_curve_names(
                self.data, context=os.path.basename(str(file_path)))

            # ========== 全局缺测标记清洗(2026-10-15) ==========
            # -999/-999.25/-9999等负大值是缺测标记不是有效值，置NaN后方可
            # 进入QC统计/泥质基线/解释/绘图——须在曲线名归一化之后、
            # 泥质调和之前(净砂基线P25曾被-9999标记污染为-9999.0)。
            self.data = sanitize_null_markers(self.data)

            # ========== 泥质含量调和(2026-10-08, BET-1) ==========
            # 交付VSH在高孔纯砂岩段把孔隙响应误归泥质(GR最纯处VSH随孔隙度
            # 升高)，与GR自适应泥质取较低值 —— "伽马最低处是纯砂岩"。
            # 此后储层过滤/矿物体积/解释/绘图共用调和后的VSH。
            self.data = reconcile_vsh_with_gr(self.data)

            logger.info(f"Data loaded successfully，共 {len(self.data)} records")
            logger.info(f"Loaded curves: {list(self.data.columns)}")
            if self.file_info:
                well_info = self.file_info.get('well', {})
                logger.info(f"File well info: {well_info}")

            # ========== LAS 元信息（含套管）挂到 data.attrs（2026-10-07）==========
            # 完整的 LAS 头段应含套管信息：CSIZ（当前套管尺寸）、
            # CDF/CADT（套管下入/上返深度）等。这些是**工程记录**，
            # 比曲线反演可靠，套管检测应优先采用。
            # 此前 las_info 只存在 DataLoader 实例上，工作流取不到。
            self.data.attrs['las_info'] = self.file_info or {}
            self.data.attrs['file_info'] = self.file_info or {}
            # 源文件路径（masterlog/录井PDF自动发现依赖，2026-10-15）
            self.data.attrs['source_file'] = str(file_path)
            # 单独存一份套管参数，便于下游直接取用
            _params = (self.file_info or {}).get('parameter', {}) or {}
            _casing_hdr = {}
            for _k in ('current_casing_size', 'casing_depth_from',
                       'casing_depth_to', 'bit_size', 'bit_size_depth_from',
                       'bit_size_depth_to'):
                if _params.get(_k) not in (None, '', 'NONE'):
                    _casing_hdr[_k] = _params[_k]
            if _casing_hdr:
                self.data.attrs['casing_header'] = _casing_hdr
                logger.info('LAS 头段套管/钻具信息: %s', _casing_hdr)
            else:
                logger.info('LAS 头段未提供套管字段（CSIZ/CDF/CADT），'
                            '套管段将由测井响应多判据推断')

            # 数据加载后立即进行质量检测（QC）
            # 【2026-10-15 用户定案】QC只评价裸眼段数据：套管段内是泥浆/水泥
            # 响应、井底到底后的大段常值"直线"是无效数据，均不参与质量统计。
            # 本井(3-SPS-111D)头段有4层套管(CS1-4)，6425m以上全是套管，此前
            # QC统计包含套管段2400+点泥浆响应，造成RHOB/PE/NPHI等被误判
            # "超出正常范围"。套管掩码在此检测一次并缓存，Step1.5直接复用。
            _full_data_qc = self.data
            try:
                _cm_early, _ci_early = detect_casing_interval(
                    self.data,
                    str((self.file_info or {}).get('well', {}).get('well_name')
                        or getattr(self, 'well_name', '') or 'Unknown'),
                    depth_unit=getattr(self, 'depth_unit', None))
                if _cm_early is not None and np.asarray(_cm_early).any():
                    self.data.attrs['casing_mask_early'] = _cm_early
                    self.data.attrs['casing_info_early'] = _ci_early
                    _keep = ~pd.Series(_cm_early, dtype=bool).values
                    self.data = self.data.loc[_keep]
                    logger.info("★ QC仅评价裸眼段: 剔除套管/水泥段%d点（全井%d点）；"
                                "井底到底后常值直线段在QC内另行剔除",
                                int((~_keep).sum()), len(_full_data_qc))
            except Exception as _e:
                logger.warning("QC前套管检测失败，按全井评价: %s", _e)
            try:
                self.qc_report = self.run_quality_control()
            finally:
                self.data = _full_data_qc
            
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
                'NPHI_LS', 'NPHI_SS', 'NPHIL', 'HEN', 'NEUTRON_POROSITY',
                'CNCF', 'CNC'   # SLAM/LWD中子(CNCF=Corrected Near-to-Far, BET-1)
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
                # LWD/SLAM成果深电阻率(BET-1, 2026-10-08)
                'RD',
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
                'CAL1', 'CAL2', 'HD1', 'HD2',
                # 【2026-10-08】BS/BIT/BITSIZE/BIT_SIZE 是钻头尺寸工程输入
                # 参数（常量），不是测量曲线，不得作为井径参与质量评价
                'CALIPER1', 'CALIPER2',
                'CAL_AVG', 'CAL_MAX', 'CAL_MIN', 'CAVE', 'CAL_BIT',
                'CALX', 'HCAL'   # SLAM/LWD井径(CALX=X向井径, BET-1)
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

        # 6.1 中子曲线质量专项检查（与密度/声波孔隙度一致性，2026-10-08）
        # 用户指出QC此前漏判中子曲线：套管/水泥段CNL 31-55%是泥浆/水泥
        # 含氢信号，通用检查给了"合格"。此检查给出中子可靠性与污染段提示。
        nphi_check = self._check_nphi_quality()
        qc_report['check_items']['nphi_quality'] = nphi_check
        qc_report['neutron_reliable'] = nphi_check.get('nphi_reliable', True)
        qc_report['neutron_quality'] = nphi_check.get('grade', '未评价')
        if nphi_check.get('grade') == '不合格':
            logger.warning("中子曲线质量不合格: %s", nphi_check.get('message', ''))
        elif nphi_check.get('grade') == '可疑':
            logger.warning("中子曲线质量可疑: %s", nphi_check.get('message', ''))
        elif nphi_check.get('message'):
            logger.info("中子曲线质量检查: %s", nphi_check['message'])
        
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
            # 【2026-10-08】模糊关键词剔除 bs/bit —— 钻头尺寸是输入参数不是井径
            'cal':   ['cal', 'cali', 'hd'],
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

            # 【2026-10-15】BIT/BITSIZE/BIT_SIZE/BS 是钻头尺寸工程输入参数
            # （阶跃常值曲线属正常），不参与质量评价（与2012评价循环同口径，
            # 防止被井底常值段检测判"constant_only"误伤）
            if str(col).strip().upper() in ('BIT', 'BITSIZE', 'BIT_SIZE', 'BS'):
                result['curve_stats'][col] = {
                    'status': 'engineering_param',
                    'note': '钻头尺寸输入参数，不参与质量评价'}
                continue

            col_data = self.data[col].dropna()
            if len(col_data) == 0:
                result['invalid_curves'].append(col)
                result['curve_stats'][col] = {'status': 'empty', 'count': 0}
                continue

            # 【2026-10-15 用户定案】井底到底后的大段常值"直线"是无效数据，
            # 不参与质量统计（>=5m完全相同的常值段剔除，孤立点/短段保留）
            try:
                if 'MD' in self.data.columns:
                    _const = DataLoader._detect_constant_segments(
                        self.data[col],
                        pd.to_numeric(self.data['MD'], errors='coerce'),
                        min_length_m=5.0)
                    _const_idx = _const.reindex(col_data.index, fill_value=False)
                    if bool(_const_idx.any()):
                        result.setdefault('constant_pts', {})[col] = int(_const_idx.sum())
                        col_data = col_data[~_const_idx]
                        if len(col_data) == 0:
                            result['invalid_curves'].append(col)
                            result['curve_stats'][col] = {
                                'status': 'constant_only', 'count': 0,
                                'note': '全部为常值直线段(井底/卡钻)，判无效'}
                            continue
            except Exception:
                pass

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
                    col_data_norm = col_data / 100.0
                    min_val_norm = col_data_norm.min()
                    max_val_norm = col_data_norm.max()
                else:
                    col_data_norm = col_data
                    min_val_norm, max_val_norm = min_val, max_val

                # 【2026-10-15 用户定案】孤立超量程尖峰是异常值而非曲线无效：
                # 超量程点占比>=2%才判"超出正常范围"，占比记入统计备查。
                # 此前 3-SPS-111D 因缺测标记与套管段污染把 AT10-90/CAL/DT/GR/
                # CNL/RHOB 整条误判无效（裸眼段实测全部在量程内）。
                _oor_mask = (col_data_norm < valid_min) | (col_data_norm > valid_max)
                _oor_pct = float(_oor_mask.mean() * 100.0) if len(col_data_norm) else 0.0

                if _oor_pct >= 2.0:
                    result['invalid_curves'].append(col)
                    result['curve_stats'][col] = {
                        'status': 'out_of_range',
                        'curve_type': curve_type,
                        'min': round(min_val, 3),
                        'max': round(max_val, 3),
                        'mean': round(mean_val, 3),
                        'valid_range': f'{valid_min}-{valid_max}',
                        'oor_pct': round(_oor_pct, 2)
                    }
                else:
                    result['valid_curves'].append(col)
                    _st = {
                        'status': 'valid' if _oor_pct <= 0 else 'isolated_outliers',
                        'curve_type': curve_type,
                        'min': round(min_val, 3),
                        'max': round(max_val, 3),
                        'mean': round(mean_val, 3)
                    }
                    if _oor_pct > 0:
                        _st['oor_pct'] = round(_oor_pct, 2)
                    result['curve_stats'][col] = _st
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
        【2026-10-15】气测等LAS曲线可能解析出字符串列（对象dtype），
        np.isclose 对字符串会抛 TypeError → 先按数值强制转换，非数值视为非哨兵。
        """
        if not pd.api.types.is_numeric_dtype(series):
            series = pd.to_numeric(series, errors='coerce')
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

    def _check_nphi_quality(self):
        """中子曲线质量专项检查（2026-10-08 BET-1 用户指出QC漏判中子曲线）

        背景：BET-1 的 CNCF(PU) 在套管/水泥段读数 31-55%（泥浆/水泥含氢，
        不是地层孔隙度），通用2012检查（空值/负值/平头/IQR离群）判不出
        这种"数值合法但物理矛盾"的问题，给了合格70分。

        三项判据：
        1) 量程合理性：PU单位中位应在(0,80]、P95≤100（小数单位×100换算）
        2) 与密度/声波孔隙度一致性（干净点 VSH<0.35）：
           r = max(corr(CNL,φd), corr(CNL,φs))
           r≥0.60 合格；0.40-0.60 可疑(降级)；<0.40 不合格(禁用中子判据)
           ——相关性对单位/刻度偏移不敏感，是刻度错误的稳健探针
        3) 套管/水泥污染段探测：CNL>30 且 DEN<2.2(泥浆密度) 且浅阻<1.2
           的点聚簇 → 提示该段中子是泥浆/水泥含氢信号（与套管检测互证）

        Returns
        -------
        dict: nphi_reliable / nphi_suspect / grade / message / polluted_points
        """
        result = {
            'passed': True,
            'nphi_reliable': True,
            'nphi_suspect': False,
            'grade': '合格',
            'message': '',
            'score': 100,
            'nphi_col': None,
            'den_col': None,
            'polluted_points': 0,
        }

        nphi_col = self._find_curve('nphi')
        den_col = self._find_curve('den')
        ac_col = self._find_curve('ac')
        result['nphi_col'] = nphi_col
        result['den_col'] = den_col
        if not nphi_col:
            result['message'] = '未找到中子曲线（NPHI/CNL/CNCF）'
            result['grade'] = '未评价'
            return result
        if not den_col:
            result['message'] = '缺少密度曲线，无法做中子一致性检查'
            result['grade'] = '未评价'
            return result

        cnl = pd.to_numeric(self.data[nphi_col], errors='coerce')
        den = pd.to_numeric(self.data[den_col], errors='coerce')

        # ---------- 1. 量程合理性（PU单位，小数自动×100） ----------
        cnl_med = cnl.median()
        if pd.notna(cnl_med) and cnl_med <= 1.5:
            cnl_pct = cnl * 100.0        # 小数 → %
        else:
            cnl_pct = cnl                # 已是 PU
        p95 = cnl_pct.quantile(0.95)
        if not (0 < cnl_pct.median() <= 80) or p95 > 100:
            result['nphi_reliable'] = False
            result['grade'] = '不合格'
            result['score'] = 40
            result['message'] = ('中子曲线量程异常（中位%.1f%%、P95=%.1f%%），'
                                 '疑似非孔隙度曲线或刻度错误'
                                 % (cnl_pct.median(), p95))
            return result

        # ---------- 2. 与密度/声波孔隙度一致性（干净点） ----------
        vsh = (pd.to_numeric(self.data['VSH'], errors='coerce')
               if 'VSH' in self.data.columns else None)
        if vsh is not None and vsh.notna().sum() > 100:
            clean = vsh < 0.35
        else:
            clean = pd.Series(True, index=self.data.index)   # 无泥质列 → 全井
        valid = clean & cnl_pct.notna() & den.notna()
        r_max = None
        if valid.sum() >= 30:
            phi_d = (2.65 - den[valid]) / 1.65 * 100     # 密度孔隙度 %
            r1 = cnl_pct[valid].corr(phi_d)
            r_list = [('密度', r1)]
            if ac_col:
                dtv = pd.to_numeric(self.data[ac_col], errors='coerce')
                m2 = valid & dtv.notna()
                if m2.sum() >= 30:
                    phi_s = (dtv[m2] - 55.5) / (189 - 55.5) * 100
                    r2 = cnl_pct[m2].corr(phi_s)
                    r_list.append(('声波', r2))
            r_best = max(r_list, key=lambda x: (x[1] if pd.notna(x[1]) else -1))
            r_max = r_best[1]
            result['consistency_r'] = {k: (round(v, 3) if pd.notna(v) else None)
                                       for k, v in r_list}
            result['consistency_points'] = int(valid.sum())
            if pd.isna(r_max) or r_max < 0.40:
                # 【2026-10-15 用户定案】量程正常即总体合格：相关度不高只作
                # "可疑"提示并明确指出，不再判不合格/一刀切禁用中子——
                # 3-SPS-111D 裸眼段中子与密度孔隙度 r≈-0.14、与声波 r≈0.48，
                # 用户确认"部分点可能有问题，但总体合格"，且该不一致本身就是
                # 质量结论要指出的依据
                result['nphi_reliable'] = True
                result['nphi_suspect'] = True
                result['grade'] = '可疑'
                result['score'] = 60
                result['message'] = ('中子与密度/声波孔隙度相关度不高(r=%.2f<0.40)，'
                                     '部分点可疑；量程正常、总体合格，解释以密度/声波'
                                     '孔隙度为主、中子作辅助判据（质量结论已指出）'
                                     % (r_max if pd.notna(r_max) else float('nan')))
                return result
            if r_max < 0.60:
                result['nphi_reliable'] = True
                result['nphi_suspect'] = True
                result['grade'] = '可疑'
                result['score'] = 70
                result['message'] = ('中子曲线与密度/声波孔隙度一致性偏弱'
                                     '(r=%.2f，0.40≤r<0.60)，部分点可疑；总体合格，'
                                     '孔隙度以密度为主、中子作辅助判据' % r_max)
                return result

        # ---------- 3. 套管/泥浆污染段探测（信息项，与套管检测互证） ----------
        shallow = [pd.to_numeric(self.data[c], errors='coerce')
                   for c in ('RMSL', 'RS', 'MSFL') if c in self.data.columns]
        shallow = [s for s in shallow if s.notna().any()]
        rt_shallow = (pd.concat(shallow, axis=1).min(axis=1)
                      if shallow else pd.Series(np.nan, index=self.data.index))
        poll = ((cnl_pct > 30) & (den < 2.2) &
                (rt_shallow < 1.2 if rt_shallow.notna().any() else True))
        result['polluted_points'] = int(poll.sum())
        if result['polluted_points'] > 30:
            _pm = pd.to_numeric(self.data.get('MD', pd.Series(
                np.arange(len(self.data)), index=self.data.index)), errors='coerce')
            _pz = _pm[poll]
            result['message'] = (
                '中子曲线量程与一致性合格，但有 %d 点高含氢低密度响应'
                '(CNL>30%%且ρ<2.2且浅阻<1.2，%.0f-%.0f深度段)——若与套管段'
                '重合为泥浆/水泥含氢信号（套管检测将排除），其余多为煤层'
                % (result['polluted_points'], np.nanmin(_pz), np.nanmax(_pz)))
        elif not result['message']:
            result['message'] = ('中子曲线质量合格（与密度/声波孔隙度相关系数'
                                 'r=%s）' % ('%.2f' % r_max if r_max is not None
                                             and pd.notna(r_max) else '未计算'))
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
            # 【2026-10-08】BIT/BITSIZE/BIT_SIZE/BS 是钻头尺寸工程输入参数
            # （常量），不是测量曲线，任何情况下不参与质量评价
            # （防止别名/模糊匹配误选，双保险）
            if col is not None and str(col).strip().upper() in (
                    'BIT', 'BITSIZE', 'BIT_SIZE', 'BS'):
                result['curve_evaluations'][curve_type] = {
                    'curve': col, 'curve_type': curve_type,
                    'display': cfg['display'], 'grade': '参数列',
                    'message': f'{col}为钻头尺寸输入参数，不参与质量评价'}
                continue
            if col is None:
                # 【2026-10-08】曲线缺失显式记录"未测"（如 BET-1 无 SP），
                # 不计入评分汇总，但报告中可见
                result['curve_evaluations'][curve_type] = {
                    'curve': None, 'curve_type': curve_type,
                    'display': cfg['display'], 'grade': '未测',
                    'message': '无此曲线（未测量），不参与评价'}
                continue
            
            eval_result = {'curve': col, 'curve_type': curve_type, 'display': cfg['display']}
            result['curve_evaluations'][curve_type] = eval_result
            result['summary']['total'] += 1
            
            col_data = self.data[col].copy()
            # 【2026-10-15】气测等LAS曲线可能因坏段解析出字符串列（对象dtype），
            # 后续统计均为数值运算 → 统一强制转数值（非数值→NaN），避免 TypeError
            if not pd.api.types.is_numeric_dtype(col_data):
                col_data = pd.to_numeric(col_data, errors='coerce')
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
            
            # ========== 5.5 PE与密度一致性（2026-10-08 用户要求）==========
            # PE 与密度响应冲突（套管/重晶石污染段 PE 虚高至十几，而密度对应
            # 砂泥岩期望 PE 1.5-4.5）→ PE 刻度失效，直接定不合格。
            # 判据复用 _check_pe_quality 单一实现（一处一功能）。
            if curve_type == 'pe':
                _pe_chk = self._check_pe_quality()
                if _pe_chk and not _pe_chk.get('pe_valid', True):
                    base_score = min(base_score, 40)
                    issues.append('PE与密度冲突: %s'
                                  % _pe_chk.get('message', 'PE响应与密度矛盾'))

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

        # 中子曲线质量建议（2026-10-08 专项检查）
        if qc_report.get('neutron_quality') == '不合格':
            recs.append('中子曲线质量不合格：%s' %
                        qc_report['check_items'].get('nphi_quality', {}).get('message', ''))
        elif qc_report.get('neutron_quality') == '可疑':
            recs.append('中子曲线质量可疑：%s' %
                        qc_report['check_items'].get('nphi_quality', {}).get('message', ''))
        elif qc_report['check_items'].get('nphi_quality', {}).get('polluted_points', 0) > 30:
            recs.append('中子曲线： %s' %
                        qc_report['check_items'].get('nphi_quality', {}).get('message', ''))
        
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
                # 未测/参数列等特殊行补充说明
                if grade in ('未测', '参数列') and ev.get('message'):
                    logger.info(f"    ↳ {ev['message']}")
                
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
        'COMPANY': 'company',
        'CTRY.': 'country',
        'FLD.': 'field_name',
        'FLD': 'field_name',
        'AREA': 'area',
        'LOC': 'well_coordinate',
        'LATI': 'latitude',
        'LONG': 'longitude',
        'WELL.': 'well_name',
        'STAT.': 'state_or_province',
        'PDAT.': 'permanent_datum',
        'ENGI.': 'engineers_name',
        'LUN': 'logging_unit_name',
        'SRVC': 'service_company_name',
        'DATE': 'log_date',
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
        'EDF': 'elevation_drill_floor',
        'BS': 'bit_size',
        'CSIZ': 'current_casing_size',
        'DFT': 'drilling_fluid_type',
        'DFD': 'drilling_fluid_density',
        'DFV': 'drilling_fluid_viscosity',
        'DFPH': 'drilling_fluid_ph',
        'DFL': 'drilling_fluid_loss',
        # 【2026-10-14 二二轮】泥浆电阻率键名映射修正：原 RMCS/RMFS/RMB 映射到
        # resistivity_mud_* 死键（无任何消费方），导致 LAS ~P 泥浆电阻率参数
        # 无法进入表2/json；统一映射到泥浆信息组消费键 rm_meas_temp/rmf_meas_temp/
        # rmc_meas_temp/rm_bht。主助记符(RM/RMF/RMC)放后, 与样品变体(RMFS/RMCS)
        # 同现时主值优先生效
        'RMFS': 'rmf_meas_temp',
        'RMF': 'rmf_meas_temp',
        'RMCS': 'rmc_meas_temp',
        'RMC': 'rmc_meas_temp',
        'RM': 'rm_meas_temp',
        'RMB': 'rm_bht',
        'BSDF': 'bit_size_depth_from',
        'BSDT': 'bit_size_depth_to',
        'CDF': 'casing_depth_from',
        'CADT': 'casing_depth_to',
    }
    
    # 曲线描述语义关键词表（小写包含匹配）：语义标签 → 关键词组
    _CURVE_SEM_KEYWORDS = [
        ('nmr',       ('mr ', 'mr)', 'mr.', 'nmr', 'magnetic resonance', '核磁')),
        ('phi_eff',   ('effective porosity', '有效孔隙度')),
        ('phi_total', ('total porosity', '总孔隙度')),
        ('perm',      ('permeability', '渗透率')),
        ('core',      ('core', '岩心', '岩芯')),
        ('sw',        ('water saturation', '含水饱和度')),
        ('movable',   ('moveable', 'movable', '可动')),
    ]

    def _mine_curve_semantics(self, las):
        """LAS 曲线描述智能挖掘（2026-10-16 用户要求）。

        解析 ~C 区每条曲线的注释描述（descr，如 "MR effective porosity"、
        "Water saturation predicted using COREANALYSIS"），按关键词识别
        曲线语义，返回 {列名: {'desc': 描述, 'tags': [语义标签]}}。
        识别到核磁孔隙度/核磁渗透率/岩心分析等特殊资料时输出利用说明日志，
        供孔隙度/渗透率选择与综合图岩心点绘制使用。
        """
        sem = {}
        try:
            for c in getattr(las, 'curves', []) or []:
                mne = str(getattr(c, 'mnemonic', '') or '').strip()
                if not mne:
                    continue
                desc = str(getattr(c, 'descr', '') or '').strip()
                unit = str(getattr(c, 'unit', '') or '').strip()
                low = desc.lower()
                tags = [tag for tag, kws in self._CURVE_SEM_KEYWORDS
                        if any(kw in low for kw in kws)]
                sem[mne.upper()] = {'desc': desc, 'unit': unit, 'tags': tags}
        except Exception as e:
            logger.warning("曲线描述挖掘失败: %s", e)
            return sem
        # ---- 挖掘结果利用说明 ----
        def _cols_with(tag):
            return [k for k, v in sem.items() if tag in v['tags']]
        nmr_eff = _cols_with('phi_eff')
        nmr_tot = _cols_with('phi_total')
        perms = _cols_with('perm')
        cores = [k for k, v in sem.items()
                 if 'core' in v['tags'] and 'sw' in v['tags']]
        if nmr_eff:
            logger.info("曲线语义挖掘 → 核磁资料利用: 有效孔隙度 %s（孔隙度以核磁有效孔隙度为准）",
                        {k: sem[k]['desc'] for k in nmr_eff})
        if nmr_tot:
            logger.info("曲线语义挖掘 → 核磁资料利用: 总孔隙度 %s", nmr_tot)
        if perms:
            logger.info("曲线语义挖掘 → 核磁资料利用: 渗透率 %s（渗透率以核磁渗透率为主）",
                        {k: sem[k]['desc'][:60] for k in perms})
        if cores:
            logger.info("曲线语义挖掘 → 岩心资料利用: %s（岩心分析点将绘制于综合图饱和度道）",
                        {k: sem[k]['desc'][:60] for k in cores})
        if not (nmr_eff or perms or cores):
            logger.info("曲线语义挖掘: 未识别到核磁/岩心等特殊资料描述")
        return sem

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

        # 【2026-10-15】全量原始参数（键=原始助记符大写）：白名单 _PARAM_FIELDS
        # 不含编号套管记录 CS1..10/CBL1..10，套管头段源
        # (_casing_layers_from_header) 曾因此永远取不到编号记录——头段源失效
        # 被 masterlog 单源成功掩盖。此处保留全量原始键值供其解析。
        try:
            _raw = {}
            for _hi in getattr(las, 'params', []) or []:
                try:
                    _k = str(getattr(_hi, 'mnemonic', '') or '').strip().upper()
                    _v = getattr(_hi, 'value', None)
                    if _k and _v is not None and str(_v).strip():
                        _raw[_k] = str(_v).strip()
                except Exception:
                    continue
            if _raw:
                las_info['params_raw'] = _raw
        except Exception:
            pass

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
            
            if file_path:
                self.last_file_path = file_path
                return self.load_data(file_path)
            else:
                logger.error("未选择文件")
                return None
    
    def load_gas_data(self):
        """加载气测数据文件（可选）

        优先使用数据选择界面选定的气测文件(2026-10-15 二五轮)，其次按井名
        自动发现(主数据目录及其子目录, 支持 xls/xlsx/csv/txt/dat/las)，
        未找到再弹出文件选择对话框。
        加载后统一列名为大写，深度列重命名为MD，单位统一为ppm。

        Returns:
            pd.DataFrame or None: 气测数据，用户取消则返回None
        """
        # ========== 数据选择界面选定文件优先(2026-10-15 二五轮) ==========
        # 用户在数据选择界面显式选定的气测文件优先级最高；
        # 文件不存在或加载失败则回退到按井名自动发现。
        _picked = str(getattr(self, 'gas_file_selected', '') or '').strip()
        if _picked:
            if Path(_picked).exists():
                try:
                    _load_gas_file_std = load_gas_file  # 2026-10-26 并库: gas_constraint 已内联本文件
                    logger.info(f"使用数据选择界面选定的气测文件: {_picked}")
                    print(f"★ 气测: 使用数据选择界面选定的文件 {_picked}")
                    return _load_gas_file_std(_picked)
                except Exception as _e:
                    logger.warning(f"选定气测文件加载失败，回退自动发现: {_e}")
            else:
                logger.warning(f"选定的气测文件不存在，回退自动发现: {_picked}")

        # ========== 自动发现气测文件(2026-10-08, BET-1) ==========
        # 按井名在主数据所在目录(含子目录, 如 supportdata/)递归查找;
        # 文件名前导零剥离匹配(BET-001 ↔ BET-1)。找到则直接加载
        # (gas_constraint.load_gas_file 内含列归一化/单位统一ppm/T15计算),
        # 未找到再弹对话框 —— CLI批处理模式下不再被对话框阻塞。
        try:
            _load_gas_file_std = load_gas_file  # 2026-10-26 并库: gas_constraint 已内联本文件(find_gas_file 走全局)
            _well_info = self.get_las_well_info() or {}
            _well_name = ''
            if isinstance(_well_info, dict):
                _well_name = _well_info.get('well_name') or _well_info.get('WELL') or ''
            if _well_name and self.last_file_path:
                _search_dirs = [os.path.dirname(os.path.abspath(self.last_file_path))]
                # 【2026-10-22 用户要求】quicklook 把气测数据也绘制上 → 气测文件
                # 常放在程序 data/ 目录而不在井文件夹内（如 3-SPS-111D_DDP_GasAv-prof.las
                # 在 F:/360/src/data/），自动发现范围须补上，否则取不到气测
                for _extra_dir in (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'),
                                   os.path.join(os.getcwd(), 'data')):
                    if os.path.isdir(_extra_dir) and _extra_dir not in _search_dirs:
                        _search_dirs.append(_extra_dir)
                _gas_path = find_gas_file(str(_well_name), search_dirs=_search_dirs)
                if _gas_path:
                    logger.info(f"自动发现气测文件: {_gas_path}")
                    print(f"★ 气测: 按井名'{_well_name}'自动发现气测文件 {_gas_path}")
                    return _load_gas_file_std(_gas_path)
            logger.info("未自动发现气测文件，弹出文件选择对话框")
        except Exception as _e:
            logger.warning(f"气测文件自动发现失败，回退到对话框选择: {_e}")

        # 【2026-10-20 RASHIDPUR_13】CLI 批处理模式（--quicklook）不弹对话框：
        # 后台/无人值守运行时 askopenfilename 会永久阻塞（本轮实录卡死 25 分钟），
        # 自动发现失败即返回 None 跳过气测（quick look 主流程不受影响）。
        if '--quicklook' in sys.argv:
            logger.warning("CLI --quicklook 模式跳过气测文件选择对话框（气测不参与本次解释）")
            return None

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.attributes('-topmost', True)
        root.withdraw()

        file_path = filedialog.askopenfilename(
            title="选择气测数据文件（取消跳过）",
            filetypes=[
                ("气测数据文件", "*.las;*.csv;*.xlsx;*.xls;*.txt;*.dat"),
                ("LAS文件", "*.las"),
                ("Excel文件", "*.xlsx;*.xls"),
                ("CSV文件", "*.csv"),
                ("文本文件", "*.txt;*.dat"),
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
                                   'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE']
                header_row = None
                for i, line in enumerate(raw_lines):
                    fields = [f.strip().upper() for f in line.strip().split(',')]
                    # 检查该行是否包含深度关键词
                    has_depth = any(kw in field for field in fields for kw in ['MD', 'DEPTH', 'DEPT', 'TDEP'])
                    # 检查是否包含气体组分关键词（至少2个）
                    gas_keyword_count = sum(
                        1 for field in fields
                        for kw in ['TG', 'TGAS', 'TOTGAS', 'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE']
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
            elif file_ext in ('.txt', '.dat'):
                # 文本格式(2026-10-08, BET-1): 制表符/逗号/空白分隔，自动定位表头行
                # 2026-10-26 并库: read_gas_text_table 走本文件内联定义
                gas_df = read_gas_text_table(str(file_path))
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
                                   'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE']
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
                        for kw in ['TG', 'TGAS', 'TOTGAS', 'C1', 'C2', 'C3', 'C4', 'C5', 'METHANE', 'ETHANE', 'PROPANE']
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

            # 气测单位统一为ppm(2026-10-08): 两级识别 —— 表头显式标注(权威) +
            # 值域判定兜底(规则B/C演绎优先于规则A归纳, BET-1的TGAS(%)max>100)
            try:
                # 2026-10-26 并库: normalize_gas_units 走本文件内联定义
                gas_df = normalize_gas_units(gas_df)
            except Exception as _ue:
                logger.warning(f"气测单位归一化跳过: {_ue}")

            # 确保MD列为数值类型（避免混合类型排序错误）
            if 'MD' in gas_df.columns:
                gas_df['MD'] = pd.to_numeric(gas_df['MD'], errors='coerce')
                # 删除深度为NaN的行
                gas_df = gas_df.dropna(subset=['MD'])
            
            # 按深度排序
            gas_df = gas_df.sort_values('MD').reset_index(drop=True)

            # 全局缺测标记清洗(2026-10-15)：气测曲线同样禁止-999类缺测标记
            # 与非法负值进入统计/解释/绘图
            gas_df = sanitize_null_markers(gas_df)

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

# 默认深电阻率候选列（按优先级）。RD 为 LWD/SLAM 成果深电阻率(BET-1, 2026-10-08)
RESISTIVITY_CANDIDATES = ['RT', 'RD', 'LLD', 'RDEEP', 'AT90', 'ILD', 'M2RX',
                          'AT60', 'RLA5', 'RMSL', 'RS',
                          # 【2026-10-20 RASHIDPUR_13】HAL 阵列电阻率 RAL1-5
                          # （RP-13 老 LAS 无 RT/RD/LLD，只有 RAL1-5；实测
                          # RAL1 在油气段读数最高=探测最深，Sw 用深探测优先）
                          'RAL1', 'RAL2', 'RAL3', 'RAL4', 'RAL5']

# 曲线名统一归一化映射(2026-10-08, BET-1): SLAM/LWD成果曲线命名(ZDEN/CNCF/
# DTC/RD/CALX)与行业常规名(DEN/CNL/DT/RT/CAL)不一致, QC的2012国标评价认不出
# CNCF为中子 -> 中子质量评价缺位、声波被误判不合格。在数据加载入口一次性把
# 别名归一为程序标准名(岩性规则/QC/绘图/解释共用口径), 全流程受益。
# 规则: 仅当"标准名不存在且别名存在"时改名, 绝不覆盖已有标准曲线;
#       横波(DTSM/DTS)不映射为纵波DT; 阵列电阻率(AT系列)不映射为RT。
CURVE_NAME_ALIASES = {
    'DEN': ['ZDEN', 'RHOZ', 'DENB', 'DENX', 'RHO', 'BUPD', 'RHO8'],
    'CNL': ['CNCF', 'CNC', 'CN', 'TNPH', 'NPHI', 'PHIN'],
    'DT':  ['DTC', 'DTCO', 'DT4P', 'AC', 'SONIC', 'SON'],
    'RT':  ['RD', 'RDEEP', 'RILD'],
    'CAL': ['CALX', 'CALI', 'HCAL'],
    'PE':  ['PEF', 'PEFZ', 'PEFL'],
    'GR':  ['GR_XMAC', 'GRGC', 'GRTO', 'GRAP'],
}

def standardize_curve_names(data, context=""):
    """把曲线列名统一归一化为程序标准名（DEN/CNL/DT/RT/CAL/PE/GR）。

    在 DataLoader.load_data 加载数据后、QC 之前调用一次 —— 此后 QC 的
    2012国标曲线质量评价、岩性识别、孔隙度计算、绘图、解释全部使用统一
    标准名, 无需各环节再做各自的别名猜测。
    """
    if data is None or len(data.columns) == 0:
        return data
    rename_map = {}
    for std, aliases in CURVE_NAME_ALIASES.items():
        if std in data.columns:
            continue  # 已有标准名, 不覆盖
        for alias in aliases:
            if alias in data.columns:
                rename_map[alias] = std
                break
    if not rename_map:
        return data
    data = data.rename(columns=rename_map)
    renamed = ', '.join(f'{k}→{v}' for k, v in rename_map.items())
    logger.info(f"曲线名统一归一化{('(' + context + ')') if context else ''}: {renamed}")
    print(f"★ 曲线名统一: {renamed}"
          f"{(' [' + context + ']') if context else ''} —— QC/解释/绘图共用标准名")
    return data

def select_resistivity_column(data, candidates=None, min_positive_ratio=0.3):
    """按优先级选择第一个含有效正值数据的电阻率列。

    常见坑(2026-10-08, BET-1): RT 列缺失时参数兜底生成全 0 的 RT 列，
    旧逻辑按列名顺序直接选中全零 RT -> Sw 恒为 1 -> 全井被判非储层。
    现要求候选列有实际有效数据（有限值占比高且正值占比 >= min_positive_ratio），
    否则跳过该列继续尝试下一个候选。
    """
    if candidates is None:
        candidates = RESISTIVITY_CANDIDATES
    n_total = len(data)
    if n_total == 0:
        return None
    fallback = None
    for cand in candidates:
        if cand not in data.columns:
            continue
        s = pd.to_numeric(data[cand], errors='coerce')
        n_finite = int(np.isfinite(s).sum())
        if n_finite == 0:
            continue
        n_pos = int((s > 0).sum())
        if n_pos >= max(1, int(n_finite * min_positive_ratio)):
            return cand
        if fallback is None and n_pos > 0:
            fallback = cand
    return fallback

# --- 解释储层过滤统一实现（一处一功能，简化路径与高级引擎共用，禁止重复） ---
_NON_RESERVOIR_KEYWORDS = [
    '泥岩', 'shale', 'shaly', 'shaley',
    '硬石膏', 'anhydrite',
    '石膏', 'gypsum',
    '岩盐', 'halite',
    '火山岩', 'volcanic',
    # 【2026-10-20 3-SPS-111D】玄武岩等火成岩补入：元素泥质定源后火成岩段
    # VSH 不再恒 1.0，缺此关键词时玄武岩点（PHI 0.11、RT 38）会通过储层
    # 过滤被判出 OIL（6943m 实测误判）。注意 'salt' 是 'basalt' 的子串、
    # 会一并命中，语义一致（两者均非储层）。
    '玄武岩', 'basalt', '凝灰岩', 'tuff', '花岗岩', 'granite',
    '基底', 'basement', '盐岩', 'salt', 'evaporite',
    '煤层', 'coal',
    '黄铁矿', 'pyrite',
    'sandstone_shale', 'sandy_shale',
]

def _normalize_petro_params(row):
    """从解释行提取归一化 petro 参数 (phi_val, vsh_val, gr_val)。
    单位容错：百分数(0-100)自动换算为小数（PHI/POR、VSH/VSHALE）。"""
    phi_val = row.get('PHI', row.get('POR', 0))
    vsh_val = row.get('VSH', row.get('VSHALE', 0))
    gr_val = row.get('GR', -1)
    try:
        phi_val = float(phi_val)
    except (TypeError, ValueError):
        phi_val = np.nan
    try:
        vsh_val = float(vsh_val)
    except (TypeError, ValueError):
        vsh_val = np.nan
    if np.isfinite(phi_val) and phi_val > 1.5:
        phi_val = phi_val / 100.0
    if np.isfinite(vsh_val) and vsh_val > 1.5:
        vsh_val = vsh_val / 100.0
    return phi_val, vsh_val, gr_val

def _reservoir_filter_reasons(row, min_porosity):
    """统一储层过滤：返回拒绝原因列表（空列表=通过），
    并返回归一化后的 (phi_val, vsh_val, gr_val) 供后续图版判别复用。"""
    phi_val, vsh_val, gr_val = _normalize_petro_params(row)
    lithology = row.get('LITHOLOGY', '其他')
    lith_lower = str(lithology).lower().strip()
    reasons = []
    if phi_val < min_porosity:
        reasons.append(f"PHI={phi_val:.3f}<{min_porosity}")
    if vsh_val > 0.40:
        reasons.append(f"VSH={vsh_val:.3f}>0.40")
    if gr_val > 120:
        reasons.append(f"GR={gr_val:.0f}>120")
    if any(kw in lith_lower for kw in _NON_RESERVOIR_KEYWORDS):
        reasons.append(f"岩性={lithology}")
    return reasons, phi_val, vsh_val, gr_val

def _is_dry_reservoir_point(phi_val, vsh_val, gr_val, lithology, min_porosity):
    """统一干层储层验证：干层首先是储层（DRY→TIGHT 判定共用）。"""
    lith_lower = str(lithology).lower().strip() if lithology else ''
    return (phi_val >= min_porosity and
            vsh_val <= 0.40 and
            (gr_val < 0 or gr_val <= 120) and
            not any(kw in lith_lower for kw in _NON_RESERVOIR_KEYWORDS))

# ========== 解释结论 must/core/deny 规则表（2026-10-08，一处一功能） ==========
# 用户要求：任何解释结论的判断都要符合 must/core/deny，避免单一条件判断。
#   must  —— 特征条件，全部满足才可能是该结论（缺一即否决）；
#   core  —— 核心计算模块（Sw/POR/RT）给出的量化证据，需 core_min 项同时成立；
#   deny  —— 否决条件，命中即排除该结论。
# 规则按顺序匹配，第一个通过的生效（GAS 排在 OIL 前：RT>50 时 GAS 的 core
# 优先命中，30<RT≤50 时 GAS 不通过自然落入 OIL）。
# 依据用户图版：气层{Sw<0.5, POR>10%, RT>50}；油层{Sw<0.5, POR>10%, RT>30}；
#              水层{Sw>0.5, POR>10%, RT<20}；干层为低孔储层（POR 6-10%）。
INTERPRETATION_RULES = [
    # 【2026-10-20 用户定案 3-SPS-111D】碳酸盐岩储层"这个地方标准"：
    # 孔隙度超过 6% 的储层都应解释成油气层（盐岩/硬石膏是优质盖层，
    # 盖层下有孔隙度+气测异常即为油气层）。GAS/OIL must 的 POR 门槛
    # 0.10→0.06，与 deny 'POR<0.06' 否决线一致；DRY 保持 [0.06,0.10)
    # 兜底（Sw 高、无含烃证据的低孔储层仍归干层）。
    {
        'key': 'GAS', 'core_min': 1,
        'must': [('Sw', '<', 0.5), ('POR', '>=', 0.06)],
        'core': [('RT', '>', 50.0, 2.0), ('RT', '>', 55.0, 1.0)],
        'deny': [('Sw', '>', 0.65), ('POR', '<', 0.06)],
    },
    {
        'key': 'OIL', 'core_min': 1,
        'must': [('Sw', '<', 0.5), ('POR', '>=', 0.06)],
        'core': [('RT', '>', 30.0, 2.0), ('RT', '>', 35.0, 1.0)],
        'deny': [('Sw', '>', 0.65), ('POR', '<', 0.06)],
    },
    {
        'key': 'WATER', 'core_min': 1,
        'must': [('Sw', '>=', 0.5), ('POR', '>=', 0.10)],
        'core': [('RT', '<', 20.0, 2.0), ('RT', '<', 25.0, 1.0)],
        'deny': [],
    },
    {
        'key': 'DRY', 'core_min': 1,
        'must': [('POR', '>=', 0.06), ('POR', '<', 0.10)],
        'core': [('Sw', '>=', 0.5, 1.0), ('Sw', '<', 0.5, 0.5)],
        'deny': [],
    },
]

# 【2026-10-27 R28 用户定案】解释截止值分井配置：下列默认值（孔隙度 0.06 等）
# 是巴西海上深水的经验知识，不能作为所有井的统一要求——每个区块每口井可能
# 不同。井级覆盖走 <井名>info.json 的「解释截止值」组（人工填非空数值即生效，
# 留空=用默认）；键值 None 表示未配置（沿用各使用处的内联默认）。
DEFAULT_CUTOFFS = {
    'por_hc': None,       # 油气层孔隙度下限（默认 0.06；储层过滤碳酸盐岩/其它分叉 0.06/0.08）
    'por_dry_max': None,  # 干层孔隙度上限 = 水层孔隙度下限（默认 0.10）
    'sw_hc': None,        # 油气层含水饱和度上限（默认 0.5）
    'sw_deny': None,      # Sw 否决线（默认 0.65）
    'rt_gas': None,       # 气层 RT 下限（默认 50 ohm·m）
    'rt_oil': None,       # 油层 RT 下限（默认 30）
    'rt_water': None,     # 水层 RT 上限（默认 20）
}

# 当前井生效的解释截止值（run_workflow 读取 info.json 后设置；
# 模块级单井流程缓存——logInt 单进程一次处理一口井）
_ACTIVE_CUTOFFS = dict(DEFAULT_CUTOFFS)


def set_active_cutoffs(cut):
    global _ACTIVE_CUTOFFS
    _ACTIVE_CUTOFFS = dict(cut or DEFAULT_CUTOFFS)


def get_active_cutoffs():
    return _ACTIVE_CUTOFFS


def _norm_cutoffs(raw):
    """「解释截止值」组 → 规范化 dict（空/非法值回落 None=默认并告警）。"""
    cut = dict(DEFAULT_CUTOFFS)
    if not isinstance(raw, dict):
        return cut
    for k in list(cut):
        v = raw.get(k)
        if v is None or str(v).strip() == '':
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            logger.warning("解释截止值 %s=%r 非数值, 用默认", k, v)
            continue
        if k.startswith(('por_', 'sw_')):
            if not (0.0 < f < 1.0):
                logger.warning("解释截止值 %s=%s 超出 (0,1), 用默认", k, f)
                continue
        elif f <= 0:
            logger.warning("解释截止值 %s=%s 需为正数, 用默认", k, f)
            continue
        cut[k] = f
    return cut


def load_interpretation_cutoffs(well_dir, well_name=''):
    """读 <井名>info.json「解释截止值」组 → cutoffs dict（无文件/无组=全默认）。

    候选位置: well_dir/<井名>info.json 与 well_dir 父目录同名文件（各试一次，
    先命中先用）；找不到 → 打印默认口径说明并返回全 None（用内联默认）。
    """
    _name = str(well_name or '').strip() or 'well'
    _cands = []
    try:
        wd = Path(well_dir)
        _cands.append(wd / (_name + 'info.json'))
        _cands.append(wd.parent / (_name + 'info.json'))
    except Exception:
        pass
    for p in _cands:
        try:
            if not p.exists():
                continue
            cfg = json.loads(p.read_text(encoding='utf-8'))
            sec = cfg.get('解释截止值') if isinstance(cfg, dict) else None
            cut = _norm_cutoffs(sec)
            _ov = [k for k in DEFAULT_CUTOFFS if cut[k] is not None]
            if _ov:
                print('  解释截止值: %s 覆盖 %s' % (
                    p.name, ', '.join('%s=%g' % (k, cut[k]) for k in _ov)))
            else:
                print('  解释截止值: %s 未配置（默认=巴西海上深水经验值, '
                      '可在该 json「解释截止值」组分井覆盖）' % p.name)
            return cut
        except Exception as e:
            logger.warning("解释截止值读取失败 %s: %s", p, e)
    print('  解释截止值: 未找到 <井名>info.json 配置（默认=巴西海上深水经验值: '
          'por_hc 0.06 / por_dry_max 0.10 / sw_hc 0.5 / sw_deny 0.65 / '
          'rt_gas 50 / rt_oil 30 / rt_water 20）')
    return dict(DEFAULT_CUTOFFS)


def build_interpretation_rules(cut=None):
    """按分井截止值构建解释规则表（cut 全空 → 直接返回默认 INTERPRETATION_RULES）。

    must/core/deny 中与默认阈值相同的数值按 cutoffs 替换；RT 次档阈值
    （55/35/25）按原表与主档的比例缩放，保持"严格/宽松"两档打分结构。
    """
    if not cut or not any(cut.get(k) is not None for k in DEFAULT_CUTOFFS):
        return INTERPRETATION_RULES
    por = cut['por_hc'] if cut.get('por_hc') is not None else 0.06
    dry = cut['por_dry_max'] if cut.get('por_dry_max') is not None else 0.10
    swh = cut['sw_hc'] if cut.get('sw_hc') is not None else 0.5
    swd = cut['sw_deny'] if cut.get('sw_deny') is not None else 0.65
    rg = cut['rt_gas'] if cut.get('rt_gas') is not None else 50.0
    ro = cut['rt_oil'] if cut.get('rt_oil') is not None else 30.0
    rw = cut['rt_water'] if cut.get('rt_water') is not None else 20.0
    _vmap = {0.06: por, 0.10: dry, 0.5: swh, 0.65: swd,
             50.0: rg, 55.0: rg * 1.1,
             30.0: ro, 35.0: ro * 35.0 / 30.0,
             20.0: rw, 25.0: rw * 25.0 / 20.0}
    import copy as _copy
    rules = _copy.deepcopy(INTERPRETATION_RULES)
    for r in rules:
        for sec in ('must', 'deny', 'core'):
            r[sec] = [tuple(c[:2]) + (_vmap[c[2]],) + tuple(c[3:])
                      if len(c) > 2 and c[2] in _vmap else tuple(c)
                      for c in r[sec]]
    return rules


def match_interpretation_rules(sw_v, phi_val, rt_v, rules=None):
    """解释结论 must/core/deny 判定（简化路径与高级引擎共用的唯一阈值实现）。

    Args:
        sw_v/phi_val/rt_v: 归一化后的含水饱和度(小数)、孔隙度(小数)、电阻率(ohm·m)。
        rules: 规则表，默认 INTERPRETATION_RULES。

    Returns:
        (结论, score, 命中说明) 或 None（无规则通过 → 调用方走距离兜底）。
    """
    rules = rules or INTERPRETATION_RULES
    vals = {'Sw': sw_v, 'POR': phi_val, 'RT': rt_v}

    def _cmp(key, op, thr):
        v = vals.get(key)
        if v is None or not np.isfinite(v):
            return False
        if op == '<':
            return v < thr
        if op == '<=':
            return v <= thr
        if op == '>':
            return v > thr
        if op == '>=':
            return v >= thr
        return False

    for rule in rules:
        reasons = []
        # must：全部满足
        if not all(_cmp(c, o, t) for c, o, t in rule['must']):
            continue
        # deny：命中即否决
        if any(_cmp(c, o, t) for c, o, t in rule['deny']):
            continue
        # core：M-of-K 一致性
        hits = []
        for it in rule['core']:
            c, o, t = it[0], it[1], it[2]
            w = it[3] if len(it) > 3 else 1.0
            if _cmp(c, o, t):
                hits.append((c, o, t, w))
        if len(hits) < rule.get('core_min', 1):
            continue
        score = sum(h[3] for h in hits) + 0.5 * len(rule['must'])
        reasons = ['%s%s%.2f' % (c, o, t) for c, o, t, _w in hits]
        return rule['key'], score, '; '.join(reasons)
    return None

# 层内流体重力分异（2026-10-09）==============================================
# 逐点图版判定只看单点物性，同一砂层内油水交错（"一会油一会水"）违反
# 重力分异规律：同一储层内油气水按密度分异，自上而下 气→油→水 单调叠置。
# FLUID_FAMILY_MAP/GRAVITY_ORDER 为层内分异的统一口径（一处一功能）。
FLUID_FAMILY_MAP = {
    'GAS': 'GAS', 'GAS_POSSIBLE': 'GAS',
    'OIL': 'OIL', 'OIL_POSSIBLE': 'OIL',
    'WATER': 'WATER', 'WATER_POSSIBLE': 'WATER',
}
GRAVITY_ORDER = {'GAS': 0, 'OIL': 1, 'WATER': 2}
_GRAV_NAME = {0: 'GAS', 1: 'OIL', 2: 'WATER'}

def enforce_fluid_segregation(data, min_fluid_pts=4, max_gap=3):
    """层内流体重力分异整饰（解释结论后处理统一入口）。

    流动单元 = 连续储层段：非储层点打断砂体（≤max_gap-1 点小缺口容忍，
    泥岩薄夹层不分裂同一砂体）；DRY/TIGHT 属物性原因，不参与分异但也
    不断开砂体。段内流体点（GAS/OIL/WATER 及 *_POSSIBLE，POSSIBLE 归入
    对应主类）≥min_fluid_pts 且出现 ≥2 个主类时，按重力序
    气(上)→油(中)→水(下) 用前缀和穷举"错配最小"的单调切分界面，再把
    各区域内不属于该区主类家族的流体点改判为区域主类（区域内目标家族
    的众数具体值，保持 *_POSSIBLE 语义）。干层/致密层保持原判。

    Returns:
        改判点数（原地修改 data 的 INTERPRETATION/ITP 列）。
    """
    if data is None or len(data) < 10 or 'INTERPRETATION' not in data.columns:
        return 0
    itp = data['INTERPRETATION'].astype(str).str.upper().str.strip()
    vals = np.array(itp.values, dtype=object)
    fam_arr = np.array([FLUID_FAMILY_MAP.get(v, '') for v in vals], dtype=object)
    is_res = np.array([(v in FLUID_FAMILY_MAP) or v in ('DRY', 'TIGHT')
                       for v in vals])
    md = pd.to_numeric(data['MD'], errors='coerce').values.astype(float)
    n = len(data)

    # ---- 流动单元划分：连续储层点（索引 gap≤max_gap 容忍小缺口）----
    segs = []
    i = 0
    while i < n:
        if not is_res[i]:
            i += 1
            continue
        j = i
        while j + 1 < n:
            if is_res[j + 1]:
                j += 1
                continue
            k = j + 1
            while k < n and not is_res[k] and k - j < max_gap:
                k += 1
            if k < n and is_res[k]:
                j = k
            else:
                break
        segs.append((i, j))
        i = j + 1

    total_fix = 0
    idx_pos = data.columns.get_loc('INTERPRETATION')
    for (s, e) in segs:
        f_idx = np.array([k for k in range(s, e + 1) if fam_arr[k]])
        if len(f_idx) < min_fluid_pts:
            continue
        y = np.array([GRAVITY_ORDER[fam_arr[k]] for k in f_idx])
        types = sorted(set(y))
        if len(types) < 2:
            continue
        nf = len(f_idx)
        cum = {t: np.concatenate(([0], np.cumsum(y == t))) for t in types}
        # ---- 错配最小的单调切分界面（上=轻流体，下=重流体）----
        if len(types) == 2:
            t0, t1 = types
            b = np.arange(nf + 1)
            cost = (b - cum[t0][b]) + ((nf - b) - (cum[t1][nf] - cum[t1][b]))
            bounds = [int(cost.argmin())]
        else:  # 气/油/水三类
            t0, t1, t2 = types
            best, bounds = None, None
            for b1 in range(nf + 1):
                b2 = np.arange(b1, nf + 1)
                tot = ((b1 - cum[t0][b1])
                       + ((b2 - b1) - (cum[t1][b2] - cum[t1][b1]))
                       + ((nf - b2) - (cum[t2][nf] - cum[t2][b2])))
                m = int(tot.argmin())
                if best is None or int(tot[m]) < best:
                    best = int(tot[m])
                    bounds = [b1, int(b2[m])]
        # ---- 区域内错配点改判 ----
        edges = [0] + bounds + [nf]
        seg_fix = 0
        for r, t in enumerate(types):
            tname = _GRAV_NAME[t]
            region = f_idx[edges[r]:edges[r + 1]]
            wrong = [k for k in region if fam_arr[k] != tname]
            if not wrong:
                continue
            tgt_pts = [vals[k] for k in region if fam_arr[k] == tname]
            new_val = pd.Series(tgt_pts).mode().iloc[0] if tgt_pts else tname
            for k in wrong:
                vals[k] = new_val
                fam_arr[k] = tname   # 【2026-10-14 修复】同步家族数组，保证
                                     # 后续层间整饰的层块计数与 vals 一致
                data.iloc[k, idx_pos] = new_val
                if 'ITP' in data.columns:
                    data.iloc[k, data.columns.get_loc('ITP')] = new_val
                seg_fix += 1
        if seg_fix:
            total_fix += seg_fix
            ifaces = ','.join('%.1f' % ((md[f_idx[b - 1]] + md[f_idx[b]]) / 2.0)
                              if 0 < b < nf else '--'
                              for b in bounds)
            logger.info('层内分异整饰 %.1f-%.1fft: %s 叠置(界面 %s ft)，改判 %d 点',
                        md[s], md[e], '/'.join(_GRAV_NAME[t] for t in types),
                        ifaces, seg_fix)
    if total_fix:
        logger.info('层内重力分异整饰完成: 共 %d 点改判（气上/油中/水下单调界面，'
                    'DRY/TIGHT 不参与）', total_fix)
    else:
        logger.info('层内重力分异整饰: 未发现违反重力分异的层段')

    # ---- 层间油水分布规律整饰【2026-10-14 用户定案】----
    # 同一油组内按重力分异规律（轻烃聚顶部、水居底部）：
    # R1 顶部油帽：全井第一个含油气砂体若为油气+水并存（油气水同层），
    #    且下一个含油气砂体为纯油/纯气主导 → 该砂体改判为纯油/纯气
    #    （盖层之下的油组顶部第一层富集轻烃，不宜标油水同层，如 BET-1 8号层）。
    # R2 过渡带底水：纯油/纯气主导砂体，若上邻含油气砂体为油气+水并存
    #    （油水同层带）、下邻含油气砂体为水层且跨度≥10 个深度单位
    #    → 改判为水层（油水过渡带底部紧邻底水，解释水层可能性大，
    #    如 BET-1 17号层）。
    inter_fix = 0
    try:
        def _body_rejudge(_b, _tgt):
            """砂体内非 _tgt 家族流体点改判为 _tgt 家族众数值。"""
            _s, _e, _fidx, _cnt = _b
            _pts = [vals[k] for k in _fidx if fam_arr[k] == _tgt]
            _nv = pd.Series(_pts).mode().iloc[0] if _pts else _tgt
            _nf = 0
            for k in _fidx:
                if fam_arr[k] != _tgt:
                    vals[k] = _nv
                    fam_arr[k] = _tgt
                    data.iloc[k, idx_pos] = _nv
                    if 'ITP' in data.columns:
                        data.iloc[k, data.columns.get_loc('ITP')] = _nv
                    _nf += 1
            if _nf:
                _cnt.clear()
                _cnt[_tgt] = len(_fidx)   # 同步家族计数（后续 R2 扫描用）
                logger.info('层间油水规律整饰 %.1f-%.1fft: 改判为 %s（%d 点）',
                            md[_s], md[_e], _nv, _nf)
            return _nf

        # 层块组装：gap<3 深度单位的相邻砂体归同一层块（与显示分层规则
        # 一致：泥岩隔层跨度≥3 才分层），层块级判定贴合用户层号语义
        # （如 BET-1 18号层 = 3 个碎 seg 组块后 WATER span 23.25ft）
        _bodies = []
        for (s, e) in segs:
            _fidx = [k for k in range(s, e + 1) if fam_arr[k]]
            if len(_fidx) < min_fluid_pts:
                continue
            if _bodies and md[s] - md[_bodies[-1][1]] < 3:
                _ps, _pe, _pf = _bodies[-1]
                _bodies[-1] = (_ps, e, _pf + list(_fidx))
            else:
                _bodies.append((s, e, list(_fidx)))
        _bodies = [(s, e, fidx,
                    {fam: sum(1 for k in fidx if fam_arr[k] == fam)
                     for fam in {fam_arr[k] for k in fidx}})
                   for (s, e, fidx) in _bodies]
        # 含油气层块（OIL/GAS 家族出现即算，含油水并存）
        _hc = [(ix, b) for ix, b in enumerate(_bodies)
               if ('OIL' in b[3] or 'GAS' in b[3])]

        if len(_hc) >= 2:
            # R1 顶部油帽：第一个含油气层块为油气+水并存 → 改纯油气
            _c0 = _hc[0][1][3]
            if ('WATER' in _c0 and ('OIL' in _c0 or 'GAS' in _c0)):
                _dom1 = max(_hc[1][1][3], key=_hc[1][1][3].get)
                if _dom1 in ('OIL', 'GAS'):
                    _tgt = 'OIL' if 'OIL' in _c0 else 'GAS'
                    inter_fix += _body_rejudge(_hc[0][1], _tgt)

            # R2 过渡带底水：纯油气层块 + 紧邻上块油水并存 + 下邻大水层
            for _hi in range(1, len(_hc) - 1):
                _bi, _b = _hc[_hi]
                _dom = max(_b[3], key=_b[3].get)
                if _dom not in ('OIL', 'GAS') or 'WATER' in _b[3]:
                    continue          # 当前块须纯油气（油水并存块本身即同层特征）
                if _bi == 0:
                    continue
                _cp = _bodies[_bi - 1][3]
                if not ('WATER' in _cp and ('OIL' in _cp or 'GAS' in _cp)):
                    continue          # 层块序列紧邻上块须为油水同层带
                # 下邻：层块序列中往后找第一个水主导块；第一个水主导块
                # span≥10 触发、<10 不触发；途中 span≥10 的油气主导块终止
                _ok = False
                for _bj in range(_bi + 1, len(_bodies)):
                    _b2 = _bodies[_bj]
                    _d2 = max(_b2[3], key=_b2[3].get)
                    _sp2 = md[_b2[1]] - md[_b2[0]]
                    if _d2 == 'WATER':
                        if _sp2 >= 10:
                            _ok = True
                        break
                    if _sp2 >= 10:
                        break
                if not _ok:
                    continue
                inter_fix += _body_rejudge(_b, 'WATER')
        if inter_fix:
            logger.info('层间油水分布规律整饰完成: 共 %d 点改判（顶部油帽/过渡带底水）',
                        inter_fix)
    except Exception as _e_ie:
        logger.warning('层间油水分布规律整饰失败(跳过): %s', _e_ie)

    return total_fix

# ========== 全局缺测标记规则(2026-10-15 用户定案) ==========
# -999/-999.25/-9999等"前3个9"的负大值是缺测标记(NULL marker)不是有效值，
# 相当于NaN，禁止参与统计/计算/绘图——对任何曲线全局适用。负值合法性仅
# SP自然电位(不会低于-200mV)与中子(不会低于-15)两族，其余曲线出现负值
# 一律视为无效值置NaN。
_NULL_MARKER_MAX = -999.0   # ≤该值的负大数视为缺测标记(覆盖-999/-999.25/-9999/-99999)
_SP_NEG_MIN = -200.0        # SP负值合法下限
_NPHI_NEG_MIN = -15.0       # 中子负值合法下限

def sanitize_null_markers(data):
    """全局缺测标记清洗（一处一功能：无效值统一入口，任何曲线都适用）。

    对所有数值列：①值≤-999(缺测标记)置NaN；②负值合法性按曲线族判定——
    SP列负值<-200置NaN、中子列(CNL/NPHI/CNCF等)负值<-15置NaN、其余列
    任何负值置NaN。须在 standardize_curve_names 之后调用(中子列名已归一)。
    幂等：清洗后的数据再次清洗不变。
    """
    if data is None or not hasattr(data, 'columns'):
        return data
    n_mark = n_neg = 0
    for c in data.columns:
        s = data[c]
        if pd.api.types.is_numeric_dtype(s):
            v = s.astype(float)
        else:
            v = pd.to_numeric(s, errors='coerce')
            if int(v.notna().sum()) < int(s.notna().sum()):
                continue  # 含非数值内容，非纯数值列，跳过
        _mark = v.notna() & (v <= _NULL_MARKER_MAX)
        cu = str(c).upper()
        if cu.startswith('SP'):
            _bad = v.notna() & (v > _NULL_MARKER_MAX) & (v < _SP_NEG_MIN)
        elif any(t in cu for t in ('NPHI', 'CNL', 'CNCF', 'PHIN', 'TNPH', 'NEUT')):
            _bad = v.notna() & (v > _NULL_MARKER_MAX) & (v < _NPHI_NEG_MIN)
        else:
            _bad = v.notna() & (v > _NULL_MARKER_MAX) & (v < 0)
        if _mark.any():
            n_mark += int(_mark.sum())
        if _bad.any():
            n_neg += int(_bad.sum())
        if _mark.any() or _bad.any():
            data[c] = v.mask(_mark | _bad)
    if n_mark or n_neg:
        logger.warning('缺测标记/无效值清洗: %d个≤-999缺测标记、%d个非法负值置NaN '
                       '(全局规则: -999类负大值为缺测标记，不参与统计/计算/绘图)',
                       n_mark, n_neg)
    return data

def reconcile_vsh_with_gr(data):
    """交付泥质列与GR自适应泥质取较低值（一处一功能：泥质含量统一入口）。

    交付VSH(SLAM/ELAN等多矿物模型成果)在高孔纯砂岩段常把孔隙/流体响应
    误归泥质 —— BET-1 8622-8627ft GR最纯段(48-58API)交付VSH随孔隙度
    0.068→0.123同步升高，违反"伽马最低处是纯砂岩"的物理事实，且中段
    非单调(GR=82时0.227 > GR=115时0.166)。GR自适应泥质以本井净砂/净泥
    基线（分界两侧P25/P75，与半幅度划层同一口径）线性内插，纯砂岩段≈0。
    两者取较低值 = 泥质指示的保守下界（程序既有原则："取伽玛计算和
    密度中子交汇的较低值"）。VSH_GR列保留供追溯；无VSH列时VSH_GR即
    泥质列；GR缺失的深度点保留交付值。
    """
    if data is None or len(data) == 0 or 'GR' not in data.columns:
        return data
    gr = pd.to_numeric(data['GR'], errors='coerce')
    g = gr.dropna().values.astype(float)
    if len(g) < 50:
        return data
    thr = (adaptive_thresholds({'GR': g}) or {}).get('GR_sand_max')
    if thr is None or not np.isfinite(thr):
        return data
    lo = g[g < thr]
    hi = g[g >= thr]
    if len(lo) < 10 or len(hi) < 10:
        return data
    sand_base = float(np.nanpercentile(lo, 25))
    shale_base = float(np.nanpercentile(hi, 75))
    if not (np.isfinite(sand_base) and np.isfinite(shale_base)) \
            or shale_base <= sand_base:
        return data
    vsh_gr = ((gr - sand_base) / (shale_base - sand_base)).clip(0, 1)
    data['VSH_GR'] = vsh_gr.values
    if 'VSH' not in data.columns:
        data['VSH'] = vsh_gr.values
        logger.info('泥质含量: 无交付VSH，采用GR自适应泥质 '
                    '(净砂基线%.1f/净泥基线%.1f)', sand_base, shale_base)
        return data
    vsh = pd.to_numeric(data['VSH'], errors='coerce')
    if pd.notna(vsh.median()) and vsh.median() > 1.5:  # 百分数 → 小数
        vsh = vsh / 100.0
    # 【2026-10-08 泥质连续性】交付VSH常为SLAM/ELAN分区输出，分区边界存在
    # 台阶(BET-1 7784.75-7785.25ft GR不变而VSH 0.295→1.000)，min调和无法
    # 消除(交付<GR泥质处直接暴露交付台阶)。min之前先做5点(1.25ft)中心滑
    # 动平均削台阶——台阶变缓坡且量级与伽马隐含变化相当；纯砂岩段GR泥质=0
    # 处min恒为0不受影响，"伽马最低处纯砂岩"保持。幂等：平滑后再min结果
    # 稳定。NaN窗口由min_periods=1跳过，缺测不造数据。
    vsh = vsh.rolling(5, center=True, min_periods=1).mean()
    _v = vsh.values.astype(float)
    _lo = vsh_gr.values.astype(float)
    _g = gr.values.astype(float)
    # 仅在GR有效且自适应泥质更低处取较低值（GR缺失点保留交付值）
    _use_gr = np.isfinite(_g) & np.isfinite(_lo) & (_lo < _v)
    _v = np.where(_use_gr, _lo, _v)
    n_low = int(_use_gr.sum())
    data['VSH'] = np.clip(np.nan_to_num(_v, nan=0.0), 0.0, 1.0)
    logger.info('泥质含量调和: 交付VSH与GR自适应泥质(净砂基线%.1f/净泥基线%.1f)'
                '取较低值，%d点被GR泥质调低', sand_base, shale_base, n_low)
    return data

def apply_elemental_vsh(data):
    """【2026-10-20 用户定案】元素泥质定源：VSH ← 元素测井泥质体积。

    用户口径：本井部分段有元素测井泥质含量（VOL_ILLITE），用元素泥质与
    伽玛的关系外推全井（除火成岩段），泥质含量应当是准的——蒸发岩-
    碳酸盐岩剖面 GR 基线整体抬升（盐岩段钾/铀贡献），GR 自适应泥质严重
    高估（3-SPS-111D 实测：灰岩段 GR 自适应/交付泥质中位 0.49，元素
    VOL_ILLITE 中位仅 0.07），泥质高估连带泥岩误判与储层误筛。

    规则：
    1) VOL_ILLITE 有效点（元素测井直接给值）→ VSH = VOL_ILLITE；
    2) 缺测点用 KTH 线性回归外推（有效点上拟合，与
       refine_element_mineral_volumes 的泥质回归同一口径），KTH 也缺测
       → 保留原 VSH；
    3) 火成岩段（VOL_BASALT>0.5）与套管段不动（火成岩"泥质"无储层意义）；
    4) 结果写入 VSH_ELEM 列留痕，VSH 同步更新（下游岩性识别/储层筛选/
       流体解释统一用元素泥质）；
    5) 元素有效点不足（<30%）不启用，保持原泥质链路。

    Returns: 处理后的 data（原地修改）。
    """
    if data is None or len(data) == 0 or 'VOL_ILLITE' not in data.columns:
        return data
    ill = pd.to_numeric(data['VOL_ILLITE'], errors='coerce')
    _valid = ill.notna() & (ill >= 0) & (ill <= 1)
    # 排除套管段（非岩石）
    if 'LITHOLOGY' in data.columns:
        _valid &= ~(data['LITHOLOGY'].astype(str).str.lower().str.strip()
                    .isin(['casing', '套管']))
    n_valid = int(_valid.sum())
    if n_valid < max(30, int(0.30 * len(data))):
        logger.info("元素泥质定源: VOL_ILLITE 有效点不足(%d/%d)，不启用",
                    n_valid, len(data))
        return data

    vsh_elem = ill.copy()
    # 缺测点：伽马系回归外推（2026-10-26 R24 用户要求：除火成岩段外全井
    # 泥质按 ECS↔伽马关系补全，保证泥质剖面连续——此前 111D 顶部 270m
    # ECS 缺测段泥质被置 0，与连续伽马脱节）。KTH(无铀伽马)与 ECS 相关
    # 最高(111D r=0.91、零值占比更低)作首选，GR 兜底覆盖 KTH 缺测点。
    _miss = ~_valid
    if _miss.any():
        _y = vsh_elem.loc[_valid].values.astype(float)
        for _src in ('KTH', 'GR'):
            if not bool(_miss.any()):
                break
            if _src not in data.columns:
                continue
            _xf = pd.to_numeric(data.loc[_valid, _src], errors='coerce')
            if _xf.notna().sum() < 30:
                continue
            _x = _xf.values.astype(float)
            _m = np.isfinite(_x) & np.isfinite(_y)
            if _m.sum() < 30:
                continue
            _k, _b = np.polyfit(_x[_m], _y[_m], 1)
            _r = float(np.corrcoef(_x[_m], _y[_m])[0, 1])
            _all = pd.to_numeric(data[_src], errors='coerce')
            _fill = _k * _all + _b
            _use = _miss & _fill.notna()
            if int(_use.sum()) == 0:
                continue
            vsh_elem[_use] = _fill[_use]
            _miss = _miss & ~_use
            logger.info("元素泥质定源: 缺测点 %s 回归外推 "
                        "VSH=%.5f%+.5f*%s (r=%.3f)，补 %d 点",
                        _src, _k, _b, _src, _r, int(_use.sum()))

    # 火成岩段不动（保留原泥质链路结果）
    if 'VOL_BASALT' in data.columns:
        _bas = pd.to_numeric(data['VOL_BASALT'], errors='coerce') > 0.5
        _bas = _bas.fillna(False).values
        vsh_elem[_bas] = np.nan
    _covered = vsh_elem.notna()
    if _covered.any():
        vsh_elem = vsh_elem.clip(0.0, 1.0)
        data['VSH_ELEM'] = vsh_elem
        vsh_old = pd.to_numeric(data.get('VSH'), errors='coerce')
        data['VSH'] = vsh_elem.where(_covered, vsh_old).clip(0.0, 1.0).values
        logger.info("元素泥质定源: VSH ← VOL_ILLITE(元素)+KTH回归外推，"
                    "覆盖 %d/%d 点（火成岩段保留原值）",
                    int(_covered.sum()), len(data))
    return data

def arbitrate_lithology_by_elements(data):
    """【2026-10-20 用户定案】元素含量仲裁岩性：修复"无证据泥岩"。

    用户口径：泥质含量以元素测井定源后应当是准的，很容易根据含量判断
    岩性。111D 实测：6766-6774m 判泥岩，但元素泥质 0.09-0.10 与邻侧灰岩
    完全相同、GR/RT/CNL 无对比度——是识别器无规则命中时的 shale 兜底
    （conf=0），不是证据判泥岩；且泥岩属非储层需归0，误判连带孔隙度
    显示与流体解释全部失真。

    规则（仅元素体积有效的裸眼段；强判据岩性不仲裁）：
    1) 判泥岩但元素泥质<0.45 且碳酸盐矿物（方解石+白云石）>=0.45
       → 主矿物定名（方解石主导=灰岩 / 白云石主导=白云岩）；
    2) 判灰岩/白云岩但元素泥质>=0.60 → 改泥岩（元素证据压倒定名）；
    3) 煤/盐/膏/玄武岩/火山岩/黄铁矿/套管等强判据岩性一律不仲裁。

    Returns: (data, 仲裁点数)
    """
    if data is None or len(data) == 0:
        return data, 0
    _need = ['LITHOLOGY', 'VOL_ILLITE', 'VOL_CALCITE', 'VOL_DOLOM']
    if not all(c in data.columns for c in _need):
        return data, 0
    _keep = {'coal', 'halite', 'salt', 'anhydrite', 'gypsum', 'evaporite',
             'basalt', 'volcanic', 'tuff', 'granite', 'basement', 'pyrite',
             'casing', '煤', '盐岩', '膏盐', '硬石膏', '石膏', '玄武岩',
             '火山岩', '花岗岩', '黄铁矿', '套管'}
    lith_s = data['LITHOLOGY'].astype(str).str.lower().str.strip()
    clay = pd.to_numeric(data['VOL_ILLITE'], errors='coerce')
    calc = pd.to_numeric(data['VOL_CALCITE'], errors='coerce')
    dol = pd.to_numeric(data['VOL_DOLOM'], errors='coerce')
    _elem_ok = clay.notna() & calc.notna() & dol.notna()
    _arb = _elem_ok & ~lith_s.isin(_keep) \
        & ~(lith_s == 'unknown')
    _arb &= ~(data['LITHOLOGY'].astype(str).str.strip().isin(_keep))

    _n = 0
    # ① 无证据泥岩 → 碳酸盐岩
    _m1 = _arb & (lith_s == 'shale') & (clay < 0.45) \
        & ((calc + dol) >= 0.45)
    # ② 泥质漏判 → 泥岩
    _m2 = _arb & lith_s.isin(['limestone', 'dolomite', 'carbonate']) \
        & (clay >= 0.60)
    for mask, to_lith in (( _m1, 'carb'), (_m2, 'shale')):
        idx = data.index[mask]
        for i in idx:
            if to_lith == 'carb':
                new = 'dolomite' if dol.at[i] > calc.at[i] else 'limestone'
            else:
                new = 'shale'
            old = data.at[i, 'LITHOLOGY']
            data.at[i, 'LITHOLOGY'] = new
            if 'LITHOLOGY_MC' in data.columns:
                data.at[i, 'LITHOLOGY_MC'] = new
            if 'LITH_MC_WHY' in data.columns:
                data.at[i, 'LITH_MC_WHY'] = (
                    f'元素仲裁:{old}->{new}(泥质{clay.at[i]:.2f},'
                    f'灰{calc.at[i]:.2f},云{dol.at[i]:.2f})')
            _n += 1
    if _n:
        logger.info("元素仲裁岩性: %d 点（无证据泥岩→碳酸盐岩 %d，"
                    "高泥质碳酸盐岩→泥岩 %d）",
                    _n, int(_m1.sum()), int(_m2.sum()))
    return data, _n

# 核磁曲线描述关键词（2026-10-16 用户定案）：描述必须出现核磁词汇才认定为
# 核磁测量；'mr' 按词边界匹配，避免 chamber 等普通单词误命中
_NMR_DESC_KEYWORDS = ('mr', 'nmr', 'nuclear magnetic',
                      'magnetic resonance', '核磁')

def _find_nmr_effective_porosity_col(data, desc_map):
    """按曲线描述识别**核磁**有效孔隙度列（2026-10-16 用户定案）。

    判定必须同时满足：
      1) 列描述（descr）含核磁词汇（MR / NMR / nuclear magnetic /
         magnetic resonance / 核磁）；
      2) 描述含有效孔隙度语义（effective porosity / 有效孔隙度）。
    仅列名像 MPHE/PHIE 但描述无核磁证据的列一律不予采用；
    无满足条件的列返回 None（孔隙度保持原有计算方式）。
    """
    import re as _re
    if data is None or not len(data.columns):
        return None
    desc_map = desc_map or {}
    for col in data.columns:
        info = desc_map.get(str(col).upper()) or {}
        d = str(info.get('desc', '')).lower()
        if not d:
            continue
        if not ('effective porosity' in d or '有效孔隙度' in d):
            continue
        if pd.to_numeric(data[col], errors='coerce').notna().any():
            _is_nmr = any(
                (kw == 'mr' and bool(_re.search(r'\bmr\b', d)))
                or (kw != 'mr' and kw in d)
                for kw in _NMR_DESC_KEYWORDS)
            if _is_nmr:
                return col
    return None

def calculate_mineral_volumes(data):
    """统一矿物体积计算（一处一功能）：仅有泥质(VSH/VSHALE)而无矿物体积列时，
    按三分量体积模型 泥质+骨架+孔隙度=1 计算矿物含量列（VClay/VQuartz/VCalcite/VDolomite），
    骨架按 LITHOLOGY 归入砂岩(默认)/灰岩/白云岩；百分数单位自动换算；已有列不覆盖。
    泥质连续性(2026-10-08)：全井统一 VClay=VSH（不按岩性并入骨架），非储层点
    φ按0参与（无有效孔隙度）——PROFILE道泥岩带处处=VSH，随伽马连续平滑。
    供 PROFILE 道矿物比例显示与解释使用。"""
    if data is None or len(data) == 0 or 'LITHOLOGY' not in data.columns:
        return data
    vsh_src = next((c for c in ('VSH', 'VClay', 'VSHALE', 'SH') if c in data.columns), None)
    if vsh_src is None:
        return data
    vsh = pd.to_numeric(data[vsh_src], errors='coerce')
    _med = vsh.median()
    if pd.notna(_med) and _med > 1.5:  # 百分数 → 小数
        vsh = vsh / 100.0
    vsh = vsh.clip(0, 1)
    _vclay_new = 'VClay' not in data.columns
    if _vclay_new:
        data['VClay'] = vsh
    phi_src = next((c for c in ('PHI', 'POR') if c in data.columns), None)
    if phi_src:
        phi = pd.to_numeric(data[phi_src], errors='coerce')
        _pmed = phi.median()
        if pd.notna(_pmed) and _pmed > 1.5:  # 百分数 → 小数
            phi = phi / 100.0
        phi = phi.clip(0, 1)
    else:
        phi = pd.Series(0.0, index=data.index)
    phi = phi.fillna(0.0)
    lith = data['LITHOLOGY'].astype(str).str.lower().str.strip()
    is_dol = lith.str.contains('dolom', na=False)
    # carbonate 而非 carbon：防止 carbonaceous_shale（碳质泥岩）被误归灰岩
    is_cal = lith.str.contains('lime|calc|carbonate', na=False) & ~is_dol
    # 【2026-10-08 泥质连续性】非储层点孔隙度按0参与矿物体积（判定集合与
    # PHI_DISP归0同一套、同一显示语义）：非储层无有效孔隙度，骨架=1-泥质。
    # 否则PROFILE道非储层铺满整道时泥岩带被放大1/(1-φ_raw)，砂岩-泥岩
    # 交接处跳变。仅影响第5道矿物显示列，原始PHI/PHIE与一切判断逻辑不动。
    if 'INTERPRETATION' in data.columns:
        _itp = data['INTERPRETATION'].astype(str).str.upper().str.strip()
        # 【R30】TIGHT(低于截止不解释)保留真实孔隙——与非储层的区别
        _nonres = (~_itp.isin(('OIL', 'GAS', 'WATER', 'DRY', 'TIGHT',
                               'OIL_POSSIBLE', 'GAS_POSSIBLE'))).values
        phi = phi.mask(_nonres, 0.0)
    rest = (1.0 - vsh.fillna(0.0) - phi).clip(0, 1)
    # 【2026-10-08 泥质连续性】取消泥质类岩性(shale/coal等)骨架并入VClay：
    # 并入使泥岩点VClay=1-φ（PROFILE整道100%泥岩），与砂岩点VClay=VSH在
    # 岩性交接处形成阶梯跳变，违反"泥质变化应像伽马曲线一样连续平滑"。
    # 统一公式 VClay=VSH、VQuartz=1-VSH-φ 后泥岩带处处=VSH（随伽马线性
    # 内插，储层/非储层两侧同值）。煤/碳质泥岩/套管等特殊岩性的PROFILE
    # 显示走LITHOLOGY整带特殊分支，不经矿物列，不受影响。
    if 'VQuartz' not in data.columns:
        data['VQuartz'] = rest.where(~(is_dol | is_cal), 0.0)
    if 'VCalcite' not in data.columns:
        data['VCalcite'] = rest.where(is_cal, 0.0)
    if 'VDolomite' not in data.columns:
        data['VDolomite'] = rest.where(is_dol, 0.0)
    logger.info(f"矿物体积已计算(泥质源={vsh_src}): 砂岩均值{data['VQuartz'].mean():.3f} "
                f"灰岩均值{data['VCalcite'].mean():.3f} 白云岩均值{data['VDolomite'].mean():.3f}")
    return data

# 主要岩性 → 闭合补齐用的主矿物 VOL 列（2026-10-19 用户定案）
_MAIN_LITH_VOL_COL = {
    'limestone': 'VOL_CALCITE', 'carbonate': 'VOL_CALCITE', '灰岩': 'VOL_CALCITE',
    'dolomite': 'VOL_DOLOM', '白云岩': 'VOL_DOLOM',
    'shale': 'VOL_ILLITE', 'mudstone': 'VOL_ILLITE', '泥岩': 'VOL_ILLITE',
    'anhydrite': 'VOL_ANHY', 'gypsum': 'VOL_ANHY', '硬石膏': 'VOL_ANHY',
    'basalt': 'VOL_BASALT', 'volcanic': 'VOL_BASALT', '玄武岩': 'VOL_BASALT',
    'coal': 'VOL_ILLITE', 'carbonaceous_shale': 'VOL_ILLITE', '煤': 'VOL_ILLITE',
    'sandstone': 'VOL_QUARTZ',
    # 【2026-10-19 岩盐判据修复】halite/salt/岩盐 → VOL_SALT（原缺失，
    # 6442-6454m 盐岩段闭合时无法归属主矿物）
    'halite': 'VOL_SALT', 'salt': 'VOL_SALT', '岩盐': 'VOL_SALT',
}

def _resolve_main_vol_col(name):
    """主要岩性 → 主矿物 VOL 列：精确匹配 → 关键词包含 → None。"""
    name = str(name).lower().strip()
    if name in _MAIN_LITH_VOL_COL:
        return _MAIN_LITH_VOL_COL[name]
    for k, v in _MAIN_LITH_VOL_COL.items():
        if k and k in name:
            return v
    return None

def close_mineral_balance(data):
    """矿物含量+孔隙度闭合=1（2026-10-19 用户定案，一处一功能）。

    口径：
    - 孔隙度取显示口径 PHI_DISP（核磁优先=原始 PHI、非储层归0；无 PHI_DISP
      回退 PHI）——原始 PHI/PHIE/Sw 一律不动，一切解释判断不受影响。
    - 缺口（1-PHI_DISP-ΣVOL>0，典型=非储层行 PHI 未归入）用**主要岩性**
      对应主矿物补齐；缺口<0（超出）按 ΣVOL 比例等比缩减（最优化最小改动）。
    - 套管/无岩性行（LITHOLOGY 空/casing/nan/NaN）无矿物概念，跳过不闭合。
    - 岩性映射：精确匹配 → 关键词包含 → 当前最大矿物列；目标列（如
      VOL_QUARTZ）不存在时按需创建。
    最终对所有有效岩性行：ΣVOL_* + PHI_DISP = 1。
    """
    if data is None or len(data) == 0 or 'LITHOLOGY' not in data.columns:
        return data
    vol_cols = [c for c in ('VOL_ILLITE', 'VOL_CALCITE', 'VOL_DOLOM',
                            'VOL_ANHY', 'VOL_BASALT', 'VOL_QUARTZ',
                            'VOL_SALT')
                if c in data.columns]
    _phi_src = ('PHI_DISP' if 'PHI_DISP' in data.columns
                else ('PHI' if 'PHI' in data.columns else None))
    if not vol_cols or _phi_src is None:
        return data
    lith = data['LITHOLOGY'].astype(str).str.lower().str.strip()
    # astype(str) 会把真实 NaN 保留为 NaN（不变成 'nan' 字符串），必须显式兜底
    lith = lith.where(lith.notna(), 'nan')
    # 目标列按需创建（如 sandstone → VOL_QUARTZ）
    for name in lith.unique():
        c = _resolve_main_vol_col(name)
        if c and c not in vol_cols:
            data[c] = 0.0
            vol_cols.append(c)
            logger.info('矿物闭合: 按岩性"%s"新建主矿物列 %s', name, c)
    phi_d = pd.to_numeric(data[_phi_src], errors='coerce').fillna(0.0).clip(0.0, 1.0)
    mv = data[vol_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0).clip(lower=0.0)
    sv = mv.sum(axis=1)
    _skip = ('', 'casing', 'nan', 'none')
    valid = (~lith.isin(_skip)).values
    target = (1.0 - phi_d).values
    deficit = target - sv.values
    act = valid & (np.abs(deficit) > 1e-6)
    if not act.any():
        logger.info('矿物+孔隙度闭合=1: 全部有效行已闭合，无需调整')
        return data
    vals = mv.values.copy()
    n_add = n_scale = n_skip = 0
    for i in np.where(act)[0]:
        d = deficit[i]
        if d > 0:
            col = _resolve_main_vol_col(lith.iloc[i])
            if col not in vol_cols:
                # 回退：当前最大矿物列（主要岩性组分）
                col = (vol_cols[int(np.argmax(vals[i]))]
                       if vals[i].sum() > 1e-9 else None)
            if col is None:
                n_skip += 1
                continue
            vals[i, vol_cols.index(col)] += d
            n_add += 1
        else:
            vals[i, :] *= (target[i] / sv.values[i])   # 等比缩减（最小改动）
            n_scale += 1
    for j, c in enumerate(vol_cols):
        data[c] = vals[:, j]
    _resid = np.abs(1.0 - vals.sum(axis=1) - phi_d.values)[valid]
    logger.info('矿物+孔隙度闭合=1: 主矿物补齐 %d 行、等比缩 %d 行、无法归属跳过 %d 行；'
                '有效行闭合残差 max=%.2e（PHI 口径=%s）',
                n_add, n_scale, n_skip,
                float(_resid.max()) if len(_resid) else 0.0, _phi_src)
    return data

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
        # 曲线名统一归一化兜底(2026-10-08): 外部注入数据同样走标准名口径
        self.data = standardize_curve_names(data, context="set_data注入")
        # 全局缺测标记清洗兜底：与 load_data 同一口径（幂等）
        self.data = sanitize_null_markers(self.data)
        # 泥质含量调和兜底：与 load_data 同一口径（幂等，重复调用结果不变）
        self.data = reconcile_vsh_with_gr(self.data)
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
        """计算孔隙度（根据2012国标质量评价结果优先使用密度孔隙度）
        
        砂泥岩剖面：使用密度孔隙度 PORD = (2.65 - RHOB)/(2.65 - 1.0)，固定骨架2.65，上限0.4
        碳酸盐岩剖面：变骨架密度，上限0.4
        
        顶部/底部无有效中子、密度、声波曲线时不计算孔隙度（置 NaN）。
        """
        if self.data is None:
            logger.error("Data not loaded")
            return None
        
        POROSITY_MAX = 0.4  # 岩石物理理论极限约0.48，保守取0.4
        
        data = self.data.copy()
        
        # 检查密度曲线质量：如果2012评价为不合格则跳过密度法
        den_priority = self.results.get('density_porosity_priority', None)
        use_density = (den_priority is None) or (den_priority is True)
        
        # ========== 始终计算 PORD (密度孔隙度, 固定骨架2.65) ==========
        # 密度/中子曲线别名识别(2026-10-08, BET-1): ZDEN为密度、CNCF为中子孔隙度
        den_col = None
        for _c in ('RHOB', 'ZDEN', 'DEN', 'RHOZ'):
            if _c in data.columns:
                den_col = _c
                break
        nphi_col = None
        for _c in ('NPHI', 'CNCF', 'CNL'):
            if _c in data.columns:
                nphi_col = _c
                break
        if den_col:
            data['PORD'] = (2.65 - data[den_col]) / (2.65 - 1.0)
            data['PORD'] = data['PORD'].clip(0, POROSITY_MAX)
            logger.info(f"PORD (密度孔隙度, 骨架2.65, 源曲线{den_col}) 已计算, 范围: {data['PORD'].min():.3f}-{data['PORD'].max():.3f}")
        
        # 判断砂泥岩剖面
        sand_shale_liths = ['sandstone', 'shale', '砂岩', '泥岩', 'sandy_shale', 'shaly_sand']
        carbonate_liths = ['limestone', 'dolomite', 'carbonate', '灰岩', '白云岩', '碳酸盐岩']
        is_sand_shale = True
        if 'LITHOLOGY' in data.columns:
            lith_counts = data['LITHOLOGY'].value_counts()
            ss_count = sum(v for k, v in lith_counts.items() if str(k).lower() in sand_shale_liths)
            cb_count = sum(v for k, v in lith_counts.items() if str(k).lower() in carbonate_liths)
            is_sand_shale = ss_count > cb_count
        
        # ========== 优先使用密度计算孔隙度 ==========
        if den_col and use_density:
            if is_sand_shale:
                # 砂泥岩剖面：直接使用 PORD
                data['PHI'] = data['PORD'].copy()
                logger.info("砂泥岩剖面 → 使用PORD (密度孔隙度, 骨架2.65, 上限0.4)")
            else:
                logger.info("碳酸盐岩剖面 → 使用密度孔隙度（变骨架, 上限0.4）")
                matrix_densities = {
                    '砂岩': 2.65, '砂': 2.65, 'sandstone': 2.65,
                    '灰岩': 2.71, 'limestone': 2.71,
                    '白云岩': 2.87, 'dolomite': 2.87,
                    '碳酸盐岩': 2.71,
                    '泥岩': 2.55, 'shale': 2.55,
                    '硬石膏': 2.98, 'anhydrite': 2.98
                }
                fluid_density = 1.0
                def calculate_phi(row):
                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                    rhob = row.get(den_col, 2.65)
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
                    return max(0, min(POROSITY_MAX, phi))
                data['PHI'] = data.apply(calculate_phi, axis=1)
        elif den_col and nphi_col:
            # ========== 密度中子交汇计算孔隙度 ==========
            if is_sand_shale:
                data['PHI'] = data['PORD'].copy()
                logger.info("砂泥岩剖面(无密度优先) → 使用PORD")
            else:
                logger.info("碳酸盐岩剖面 → 使用密度中子交汇（上限0.4）")
                matrix_densities = {
                    '砂岩': 2.65, '砂': 2.65, 'sandstone': 2.65,
                    '灰岩': 2.71, 'limestone': 2.71,
                    '白云岩': 2.87, 'dolomite': 2.87,
                    '碳酸盐岩': 2.71,
                    '泥岩': 2.55, 'shale': 2.55,
                    '硬石膏': 2.98, 'anhydrite': 2.98
                }
                fluid_density = 1.0
                def calculate_phi_dn(row):
                    rhob = row.get(den_col, 2.65)
                    nphi = row.get(nphi_col, 0.15)
                    if nphi > 1:
                        nphi = nphi / 100.0
                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                    if lithology in matrix_densities:
                        matrix_density = matrix_densities[lithology]
                    else:
                        if rhob < 2.68:
                            matrix_density = 2.65
                        elif rhob < 2.80:
                            matrix_density = 2.71
                        else:
                            matrix_density = 2.87
                    phi_den = (matrix_density - rhob) / (matrix_density - fluid_density)
                    phi_cnl = nphi
                    phi = (phi_den + phi_cnl) / 2.0
                    return max(0, min(POROSITY_MAX, phi))
                data['PHI'] = data.apply(calculate_phi_dn, axis=1)
        elif any(nmr_col in data.columns for nmr_col in ['MPHE', 'PHIE', 'MRP']):
            # ========== 使用核磁孔隙度 ==========
            for nmr_col in ['MPHE', 'PHIE', 'MRP']:
                if nmr_col in data.columns:
                    data['PHI'] = data[nmr_col].clip(0, POROSITY_MAX)
                    logger.info(f"使用核磁孔隙度 {nmr_col}（上限0.4）")
                    break
        elif 'POR' in data.columns:
            # ========== 成果孔隙度列(2026-10-08, BET-1): 单位感知 ==========
            data['PHI'] = pd.to_numeric(data['POR'], errors='coerce')
            if data['PHI'].max() > 1.5:
                data['PHI'] = data['PHI'] / 100.0
                logger.info("POR孔隙度为%单位，已/100转小数")
            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
            logger.info("使用POR孔隙度（上限0.4）")
        elif nphi_col:
            # ========== 仅中子孔隙度 ==========
            logger.info(f"使用中子孔隙度 {nphi_col}（上限0.4）")
            data['PHI'] = data[nphi_col]
            if data['PHI'].max() > 1:
                data['PHI'] = data['PHI'] / 100.0
            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
        elif 'DT' in data.columns or 'DTCO' in data.columns or 'DTC' in data.columns:
            # ========== 声波计算孔隙度 ==========
            logger.info("使用声波计算孔隙度（上限0.4）")
            dt_col = 'DT' if 'DT' in data.columns else ('DTC' if 'DTC' in data.columns else 'DTCO')
            data['PHI'] = (data[dt_col] - 55.5) / (189 - 55.5)
            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
        else:
            # ========== 默认孔隙度 ==========
            logger.info("使用默认孔隙度0.2")
            data['PHI'] = 0.2
            if 'PORD' not in data.columns:
                data['PORD'] = 0.2
        
        # ========== 核磁有效孔隙度优先（2026-10-16 用户要求） ==========
        # LAS 描述明确核磁有效孔隙度（如 MPHE .PU : MR effective porosity）时，
        # 孔隙度以有效孔隙度为准——核磁直接测量值优于密度骨架模型推断；
        # 该 PHI 随后驱动 Sw（阿尔奇）、PHI_DISP（非储层归0显示列），
        # 综合图第5道孔隙度曲线与 profile 道自动与核磁有效孔隙度一致
        _nmr_phi = _find_nmr_effective_porosity_col(
            data, getattr(self, 'curve_descriptions', {}) or {})
        if _nmr_phi:
            _raw = pd.to_numeric(data[_nmr_phi], errors='coerce')
            if _raw.max() > 1.5:  # % 单位转小数
                _raw = _raw / 100.0
                logger.info("核磁有效孔隙度 %s 为%%单位，已/100转小数", _nmr_phi)
            data['PHI'] = _raw.clip(0, POROSITY_MAX)
            logger.info("孔隙度以核磁有效孔隙度为准: PHI ← %s（覆盖密度计算值，上限0.4）",
                        _nmr_phi)

        # 顶部/底部无效段：无有效中子/密度/声波曲线 → PHI/PORD 置 NaN
        self._apply_porosity_invalid_mask(data)
        
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
            data['Sw'] = 1.0
        
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

# --- 数据可视化类（调用修复后的logvis模块）---
class DataVisualizer:
    """数据可视化类 - 调用修复后的logvis模块"""
    
    def __init__(self, output_dir):
        """初始化数据可视化器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.viz_dir = self.output_dir
    
    def visualize_composite_log(self, data, results, gas_data=None,
                                quicklook_config=None):
        """可视化综合测井曲线（综合图绘制流程入口，见 logvis.visualize_composite_log）"""
        try:
            from logvis import visualize_composite_log as fixed_visualize
            return fixed_visualize(data, results, gas_data=gas_data,
                                   quicklook_config=quicklook_config)
        except ImportError as e:
            logger.error(f"导入logvis模块失败: {e}")
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
            
            plt.savefig(output_path, dpi=80, bbox_inches='tight',
                        metadata={'Software': None})
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

def _ql_find_col(data, possible_names):
    """在 DataFrame 中查找第一个存在的列名（忽略大小写与空白）"""
    if data is None:
        return None
    _low = {str(c).strip().lower(): c for c in data.columns}
    for name in possible_names:
        if name.strip().lower() in _low:
            return _low[name.strip().lower()]
    return None

def _build_hc_reason_sections(results):
    """【2026-10-13 用户要求】解释报告逐油气层归因 + 交汇图。

    对每个储层流体段（OIL/GAS/WATER 及 *_POSSIBLE/*_PROBABLE），
    对比「段内曲线均值」与「全井有效数据中位数（基线）」，
    说明测井曲线（RT/密度/中子/孔隙度/Sw/GR）、地质（岩性/物性）、
    气测（TG）各维度参数变化如何导致其被解释为油气层，
    并为每个油气层生成 中子-密度、电阻率-孔隙度 两张交汇图
    （段内红/绿点 vs 全井灰点背景）嵌入报告。

    Returns:
        (sections_html, plot_dir_rel)
    """
    data = results.get('processed_data') if isinstance(results, dict) else None
    if data is None or not hasattr(data, 'columns') or 'INTERPRETATION' not in data.columns:
        return '', None
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception as _e:
        logger.warning('交汇图依赖不可用: %s', _e)
        plt = None

    well_name = str(results.get('well_name') or 'Well')
    out_dir = Path(results.get('output_dir') or str(Path('output') / well_name))
    plot_dir = out_dir / 'crossplots'
    try:
        plot_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    df = data.reset_index(drop=True)
    md = pd.to_numeric(df['MD'], errors='coerce')

    # 深度单位自适应（公制 m / 英制 ft）：优先取 las_info，其次按数值量级推断
    _unit = 'm'
    _unit_from_las = False
    _las = results.get('las_info') if isinstance(results, dict) else None
    if isinstance(_las, dict):
        for _k in ('depth_unit', 'unit', 'depth_units', 'depth_metric'):
            if _las.get(_k):
                _u = str(_las[_k]).strip().lower()
                if _u in ('ft', 'feet', 'foot', 'ft.',
                          'f', '0.3048', 'imperial', 'english'):
                    _unit = 'ft'
                else:
                    _unit = 'm'
                _unit_from_las = True
                break
    if not _unit_from_las:
        # 兜底推断（仅当 las_info 无单位信息时）：MD 中位数 > 10000 判英尺井；
        # 浅于 10000 的深度值公制/英制无法区分，按公制处理
        try:
            _md_mid = float(md.median())
            if _md_mid > 10000:
                _unit = 'ft'
        except Exception:
            pass

    # 常用曲线列
    rt_col = _ql_find_col(df, ['RT', 'LLD', 'RESD', 'RES', 'RD', 'ILD'])
    den_col = _ql_find_col(df, ['RHOB', 'DEN', 'DENSITY', 'ZDEN'])
    nphi_col = _ql_find_col(df, ['NPHI', 'CNCF', 'CNL', 'TNPH', 'NEUTRON'])
    dt_col = _ql_find_col(df, ['DT', 'AC', 'SONIC'])
    phi_col = _ql_find_col(df, ['PHI', 'PHIE', 'POR', 'POROSITY', 'PHID'])
    sw_col = _ql_find_col(df, ['SW', 'Sw', 'S_W', 'WATER_SAT'])
    gr_col = _ql_find_col(df, ['GR', 'GAMMA', 'CGR'])
    vsh_col = _ql_find_col(df, ['VSH', 'V_SH', 'SHALE', 'VCL'])
    # 【2026-10-16】候选移除 'K'——K 是自然伽马能谱钾含量曲线，非渗透率，
    # 无 PERM 井此前会误把钾曲线当渗透率（核磁渗透率以 PERM 为主）
    perm_col = _ql_find_col(df, ['PERM', 'PERMEABILITY', 'PERM_K'])

    _num = lambda s: pd.to_numeric(df[s], errors='coerce') if s else None
    rt, den, nphi, dt = _num(rt_col), _num(den_col), _num(nphi_col), _num(dt_col)
    phi, sw, gr, vsh, perm = _num(phi_col), _num(sw_col), _num(gr_col), _num(vsh_col), _num(perm_col)

    # 气测（results 里的 gas_data）
    gas_data = results.get('gas_data') if isinstance(results, dict) else None
    tg_col = None
    if gas_data is not None and hasattr(gas_data, 'columns'):
        tg_col = _ql_find_col(gas_data, ['TG', 'GAS_TG', 'TOTALGAS', 'GAS', 'C1', 'CH4'])
        _gmd_col = _ql_find_col(gas_data, ['MD', 'DEPTH', 'DEP', 'DEPT']) or gas_data.columns[0]
        _gmd = pd.to_numeric(gas_data[_gmd_col], errors='coerce')
        _tg = pd.to_numeric(gas_data[tg_col], errors='coerce') if tg_col else None

    # ---- 切分储层流体段（连续相同结论；排除空/非储层/干层/致密层） ----
    itp = df['INTERPRETATION'].apply(
        lambda x: str(x).upper().strip() if x is not None else '')
    skip = {'', 'NAN', 'NONE', 'UNDEFINED', 'NONRESERVOIR', 'NON-RESERVOIR', 'DRY', 'TIGHT'}
    segments = []
    i = 0
    n = len(df)
    while i < n:
        if itp.iloc[i] in skip:
            i += 1
            continue
        seg_start = float(md.iloc[i])
        lab = str(itp.iloc[i])
        j = i + 1
        while j < n and str(itp.iloc[j]) == lab:
            j += 1
        seg_end = float(md.iloc[j - 1])
        segments.append((seg_start, seg_end, lab, i, j))
        i = j
    # 合并同结论相邻段（间隔 ≤ 3 个深度单位的小缺口容忍）
    if len(segments) > 1:
        _merged = [segments[0]]
        for _s in segments[1:]:
            _p = _merged[-1]
            if _s[2] == _p[2] and (_s[0] - _p[1]) <= 3.0:
                _merged[-1] = (_p[0], _s[1], _s[2], _p[3], _s[4])
            else:
                _merged.append(_s)
        segments = _merged

    # ---- 全井基线（有效数据中位数） ----
    def _base(s):
        if s is None:
            return None
        v = s.dropna()
        return float(v.median()) if len(v) > 5 else None

    base = {k: _base(s) for k, s in
            {'RT': rt, 'DEN': den, 'NPHI': nphi, 'DT': dt,
             'PHI': phi, 'SW': sw, 'GR': gr, 'VSH': vsh, 'PERM': perm}.items()}

    def _seg_mean(s, i0, i1):
        if s is None:
            return None
        v = s.iloc[i0:i1].dropna()
        return float(v.mean()) if len(v) > 0 else None

    # ---- 水层储层基准（用户2026-10-15"说清楚异于其它不是油气层的储层的地方"） ----
    _wmask = itp.str.startswith('WATER').values
    wb = {}
    if _wmask.sum() > 5:
        for _k, _s in (('RT', rt), ('PHI', phi), ('SW', sw)):
            if _s is not None:
                _v = _s[_wmask].dropna()
                if len(_v) > 5:
                    wb[_k] = float(_v.mean())

    # ---- 交汇图背景仅用储层点（用户2026-10-15"交汇图只用储层数据，泥岩等非储层不用"） ----
    _nonres_pts = itp.isin({'', 'NAN', 'NONE', 'UNDEFINED', 'NONRESERVOIR',
                            'NON-RESERVOIR', 'TIGHT'}).values
    _res_mask = ~_nonres_pts

    # 中文结论名
    _zh = {'GAS': '气层', 'OIL': '油层', 'WATER': '水层',
           'GAS_POSSIBLE': '可能气层', 'OIL_POSSIBLE': '可能油层',
           'WATER_POSSIBLE': '可能水层', 'GAS_PROBABLE': '较可能气层',
           'OIL_PROBABLE': '较可能油层'}

    sections = []
    layer_no = 0
    for seg_start, seg_end, lab, i0, i1 in segments:
        layer_no += 1
        sm = {k: _seg_mean(s, i0, i1) for k, s in
              {'RT': rt, 'DEN': den, 'NPHI': nphi, 'DT': dt,
               'PHI': phi, 'SW': sw, 'GR': gr, 'VSH': vsh, 'PERM': perm}.items()}

        # ---- 归因文本：逐参数对比基线 ----
        reasons = []
        stat_rows = []
        def _cmp(name, cur, bl, unit=''):
            if cur is None or bl is None:
                return
            ratio = cur / bl if abs(bl) > 1e-12 else None
            if ratio is not None and ratio > 1.3:
                tag = '显著升高'
                rsn = f'{name}{unit}较基线抬升 {ratio:.2f} 倍（{cur:.3g}{unit} → 基线{bl:.3g}{unit}）'
            elif ratio is not None and ratio < 0.75:
                tag = '显著降低'
                rsn = f'{name}{unit}较基线降低（{cur:.3g}{unit} → 基线{bl:.3g}{unit}，-{max(1 - ratio, 0):.0%}）'
            elif abs(cur - bl) > 0.15 * abs(bl):
                tag = '升高' if cur > bl else '降低'
                rsn = f'{name}{unit}较基线{tag}（{cur:.3g}{unit} vs 基线{bl:.3g}{unit}）'
            else:
                tag = '相近'
                rsn = f'{name}{unit}与基线相近（{cur:.3g}{unit} vs {bl:.3g}{unit}）'
            stat_rows.append((name, cur, bl, tag))
            reasons.append(rsn)

        # 测井维度
        _cmp('深电阻率RT', sm['RT'], base['RT'], 'Ω·m')
        _cmp('密度DEN', sm['DEN'], base['DEN'], 'g/cc')
        _cmp('中子NPHI', sm['NPHI'], base['NPHI'])
        _cmp('声波DT', sm['DT'], base['DT'], 'μs/ft')
        _cmp('孔隙度PHI', sm['PHI'], base['PHI'])
        _cmp('含水饱和度Sw', sm['SW'], base['SW'])
        _cmp('自然伽马GR', sm['GR'], base['GR'], 'API')
        # 地质维度
        if sm['PHI'] is not None and sm['VSH'] is not None and base['VSH'] is not None:
            if sm['PHI'] >= 0.05:
                reasons.append(f'孔隙度 {sm["PHI"]*100:.1f}% ≥ 5%：具备有效储层物性（地质上可作储层）')
            else:
                reasons.append(f'孔隙度仅 {sm["PHI"]*100:.1f}%，储集物性一般')
            if sm['VSH'] <= 0.4:
                reasons.append(f'泥质含量低（Vsh={sm["VSH"]*100:.1f}%）：砂质/碳酸盐储层特征，围岩泥岩为高GR高Vsh背景')
        # 气测维度
        if tg_col is not None and _tg is not None:
            _tg_seg = _tg[(_gmd >= seg_start) & (_gmd <= seg_end)]
            _tg_base = _tg.dropna().median()
            if len(_tg_seg.dropna()) > 0 and _tg_base is not None and _tg_base > 0:
                _tg_mean = float(_tg_seg.dropna().mean())
                _tg_ratio = _tg_mean / float(_tg_base)
                if _tg_ratio >= 2:
                    reasons.append(f'气测全烃TG段均值 {_tg_mean:.0f} ppm，为全井基线（{_tg_base:.0f} ppm）的 {_tg_ratio:.1f} 倍：气测异常明显')
                else:
                    reasons.append(f'气测全烃TG段均值 {_tg_mean:.0f} ppm 与基线相近（{_tg_base:.0f} ppm）')

        # ---- 图版判定：段均值对照 INTERPRETATION_RULES must/core/deny 逐条说明 ----
        plate_html = ''
        _bk = lab.split('_')[0]
        _rules_eff = build_interpretation_rules(get_active_cutoffs())
        _rule = next((r for r in _rules_eff if r['key'] == _bk), None)
        if _rule is not None:
            def _pv(key):
                v = {'Sw': sm['SW'], 'POR': sm['PHI'], 'RT': sm['RT']}.get(key)
                if v is None or not np.isfinite(v):
                    return None
                return v

            def _vf(key, v):
                if key == 'POR':
                    return f'{v * 100:.1f}%'
                if key == 'RT':
                    return f'{v:.1f}Ω·m'
                return f'{v:.2f}'

            def _tf(key, thr):
                if key == 'POR':
                    return f'{thr * 100:g}%'
                if key == 'RT':
                    return f'{thr:g}Ω·m'
                return f'{thr:g}'

            def _ok(key, op, thr):
                v = _pv(key)
                if v is None:
                    return False
                return ((v < thr) if op == '<' else (v <= thr) if op == '<='
                        else (v > thr) if op == '>' else (v >= thr))

            _must_items, _must_ok = [], True
            for c in _rule['must']:
                _v = _pv(c[0])
                if _v is None:
                    _must_items.append(f'{c[0]}缺测')
                    _must_ok = False
                    continue
                _o = _ok(c[0], c[1], c[2])
                _must_ok = _must_ok and _o
                _opz = {'<': '<', '<=': '≤', '>': '>', '>=': '≥'}[c[1]]
                _must_items.append(
                    f'{c[0]}={_vf(c[0], _v)}{_opz}{_tf(c[0], c[2])}{"✓" if _o else "✗"}')

            _deny_items, _deny_hit = [], False
            for c in _rule['deny']:
                _v = _pv(c[0])
                if _v is None:
                    continue
                _o = _ok(c[0], c[1], c[2])
                _deny_hit = _deny_hit or _o
                _opz = {'<': '<', '<=': '≤', '>': '>', '>=': '≥'}[c[1]]
                _deny_items.append(
                    f'{c[0]}={_vf(c[0], _v)}{_opz}{_tf(c[0], c[2])}（{"触发" if _o else "未触发"}）')

            _core_items, _core_w = [], 0.0
            for c in _rule['core']:
                _v = _pv(c[0])
                if _v is None:
                    continue
                _o = _ok(c[0], c[1], c[2])
                _w = c[3] if len(c) > 3 else 1.0
                if _o:
                    _core_w += _w
                _opz = {'<': '<', '<=': '≤', '>': '>', '>=': '≥'}[c[1]]
                _core_items.append(
                    f'{c[0]}={_vf(c[0], _v)}{_opz}{_tf(c[0], c[2])}{"✓" if _o else "✗"}(权重{_w:g})')

            _core_hit = _core_w >= float(_rule.get('core_min', 1))
            if _must_ok and not _deny_hit and _core_hit:
                _plate_word = '完全命中'
            elif _must_ok and not _deny_hit:
                _plate_word = '必选/否决条件满足，但核心证据未达权重'
            else:
                _plate_word = '未完全命中（逐点判定经距离兜底就近归类）'
            plate_html = (
                f'<div style="font-size:12px;background:#f0f7ff;border:1px solid #bcd8f0;'
                f'border-radius:4px;padding:6px 8px;margin:6px 0;">'
                f'<b>图版判定（{_zh.get(lab, lab)}·{_bk}图版，段均值）：</b>'
                f'必选条件 {"、".join(_must_items) or "—"}；'
                f'否决条件 {"、".join(_deny_items) if _deny_items else "无"}'
                f'{"【触发】" if _deny_hit else "未触发"}；'
                f'核心条件 {"、".join(_core_items) or "—"}'
                f'（累计权重{_core_w:g}/需≥{float(_rule.get("core_min", 1)):g}）；'
                f'→ <b>{_plate_word}</b></div>')

        # ---- 与水层储层（非油气储层）对比：说明异于水层之处 ----
        if wb and lab.startswith(('GAS', 'OIL')):
            _wc = []
            if 'RT' in wb and sm['RT'] is not None and wb['RT'] > 0:
                _wc.append(f'RT均值 {sm["RT"]:.1f}Ω·m 为水层储层均值（{wb["RT"]:.1f}Ω·m）的 {sm["RT"] / wb["RT"]:.1f} 倍')
            if 'SW' in wb and sm['SW'] is not None:
                if sm['SW'] <= wb['SW'] - 0.05:
                    _wc.append(f'Sw均值 {sm["SW"] * 100:.0f}% 显著低于水层储层均值（{wb["SW"] * 100:.0f}%）')
                elif sm['SW'] >= wb['SW'] + 0.05:
                    _wc.append(f'Sw均值 {sm["SW"] * 100:.0f}% 反高于水层储层均值（{wb["SW"] * 100:.0f}%），需结合RT与气测综合判断')
                else:
                    _wc.append(f'Sw均值 {sm["SW"] * 100:.0f}% 与水层储层均值（{wb["SW"] * 100:.0f}%）相近')
            if _wc:
                reasons.append('与水层储层（非油气储层）对比：' + '；'.join(_wc) +
                               '——此差异是本段被判为油气层而水层不是的关键')
        elif wb and lab.startswith('WATER'):
            _wc = []
            if 'RT' in wb and sm['RT'] is not None:
                _wc.append(f'RT均值 {sm["RT"]:.1f}Ω·m（水层储层均值 {wb["RT"]:.1f}Ω·m）')
            if 'SW' in wb and sm['SW'] is not None:
                _wc.append(f'Sw均值 {sm["SW"] * 100:.0f}%（水层储层均值 {wb["SW"] * 100:.0f}%）')
            if _wc:
                reasons.append('与全井水层储层一致：' + '、'.join(_wc) +
                               '，落水层图版区间，无烃类聚集证据')

        # ---- 综合结论句 ----
        if lab.startswith('GAS'):
            verdict = '综合判断为气层：电阻率相对围岩抬升、中子-密度呈挖掘效应（中子降低+密度降低）是气层区别于油层的核心证据'
            if sm['DEN'] is not None and base['DEN'] is not None and sm['DEN'] < base['DEN'] - 0.03:
                verdict += '；本段密度确较基线降低，符合挖掘效应特征'
            elif sm['DEN'] is not None and base['DEN'] is not None:
                verdict += '；本段密度未明显降低，气层判断更多依赖气测与电阻率'
        elif lab.startswith('OIL'):
            verdict = '综合判断为油层：电阻率相对围岩抬升、Sw降低（含烃）、孔隙度有效'
        else:
            verdict = '综合判断为水层：电阻率低、Sw高（>60%）、无气测异常，无烃类聚集证据'

        # ---- 交汇图 ----
        img_tags = []
        if plt is not None:
            try:
                if den_col and nphi_col:
                    _bg_d = pd.to_numeric(df[den_col], errors='coerce').values
                    _bg_n = pd.to_numeric(df[nphi_col], errors='coerce').values
                    _seg_d = _bg_d[i0:i1]
                    _seg_n = _bg_n[i0:i1]
                    # 中子：仅当整段为小数（0~1.5 v/v）才换算为 %；已是 %（如 CNL 6~65）不再乘
                    if 0 < np.nanmax(_seg_n) < 1.5:
                        _bg_n, _seg_n = _bg_n * 100.0, _seg_n * 100.0
                    _ok_bg = _res_mask & (~np.isnan(_bg_d)) & (~np.isnan(_bg_n)) & (_bg_d > 1.5) & (_bg_d < 3.2) & (_bg_n > -10) & (_bg_n < 70)
                    if _ok_bg.sum() > 10:
                        _f, _ax = plt.subplots(figsize=(4.6, 3.4), dpi=130)
                        _ax.scatter(_bg_d[_ok_bg], _bg_n[_ok_bg], s=3, c='#b0b0b0', alpha=0.35, label='全井储层背景')
                        _ok_s = (~np.isnan(_seg_d)) & (~np.isnan(_seg_n))
                        if _ok_s.sum() > 1:
                            _ax.scatter(_seg_d[_ok_s], _seg_n[_ok_s], s=22, c='red', alpha=0.85,
                                        label=f'{lab} {seg_start:.0f}-{seg_end:.0f}')
                        _ax.set_xlabel('Density (g/cc)'); _ax.set_ylabel('Neutron (%)')
                        _ax.set_title(f'{well_name} 中子-密度交会 #{layer_no} ({_zh.get(lab, lab)})')
                        _ax.legend(fontsize=6, loc='upper right'); _ax.grid(alpha=0.3)
                        _f.tight_layout()
                        _p = plot_dir / f'{well_name}_{layer_no:02d}_nd.png'
                        _f.savefig(_p, bbox_inches='tight'); plt.close(_f)
                        img_tags.append(f'<img src="crossplots/{_p.name}" width="460" />')
                if rt_col and phi_col:
                    _bg_r = pd.to_numeric(df[rt_col], errors='coerce').values
                    _bg_p = pd.to_numeric(df[phi_col], errors='coerce').values
                    _seg_r = _bg_r[i0:i1]; _seg_p = _bg_p[i0:i1]
                    if _seg_p.max() > 1.5:
                        _bg_p, _seg_p = _bg_p * 100.0, _seg_p * 100.0
                    _ok_bg = _res_mask & (~np.isnan(_bg_r)) & (~np.isnan(_bg_p)) & (_bg_r > 0.05) & (_bg_p > -1)
                    if _ok_bg.sum() > 10:
                        _f, _ax = plt.subplots(figsize=(4.6, 3.4), dpi=130)
                        _ax.scatter(_bg_p[_ok_bg], _bg_r[_ok_bg], s=3, c='#b0b0b0', alpha=0.35, label='全井储层背景')
                        _ok_s = (~np.isnan(_seg_r)) & (~np.isnan(_seg_p))
                        if _ok_s.sum() > 1:
                            _ax.scatter(_seg_p[_ok_s], _seg_r[_ok_s], s=22, c='green', alpha=0.85,
                                        label=f'{lab} {seg_start:.0f}-{seg_end:.0f}')
                        _ax.set_xlabel('Porosity (%)'); _ax.set_ylabel('Resistivity (Ω·m)'); _ax.set_yscale('log')
                        _ax.set_title(f'{well_name} 电阻率-孔隙度交会 #{layer_no} ({_zh.get(lab, lab)})')
                        _ax.legend(fontsize=6, loc='upper right'); _ax.grid(alpha=0.3, which='both')
                        _f.tight_layout()
                        _p = plot_dir / f'{well_name}_{layer_no:02d}_rt.png'
                        _f.savefig(_p, bbox_inches='tight'); plt.close(_f)
                        img_tags.append(f'<img src="crossplots/{_p.name}" width="460" />')
            except Exception as _e:
                logger.warning('交汇图生成失败(层%d): %s', layer_no, _e)

        # ---- 参数统计表 ----
        stat_rows_html = ''.join(
            f'<tr><td>{nm}</td><td>{cur:.3g}</td><td>{bl:.3g}</td><td>{tag}</td></tr>'
            for nm, cur, bl, tag in stat_rows if cur is not None and bl is not None)
        reasons_html = '<ul style="margin:2px 0;">' + ''.join(
            f'<li>{r}</li>' for r in reasons) + '</ul>'
        sections.append(f'''
        <div style="margin:12px 0;padding:10px;border:1px solid #ccc;border-radius:6px;">
          <h4 style="margin:4px 0;">#{layer_no}  {_zh.get(lab, lab)}  {seg_start:.1f} - {seg_end:.1f} {_unit}</h4>
          <table style="border-collapse:collapse;font-size:12px;margin:6px 0;">
            <tr><th style="border:1px solid #ddd;padding:4px;">参数</th>
                <th style="border:1px solid #ddd;padding:4px;">段均值</th>
                <th style="border:1px solid #ddd;padding:4px;">全井基线</th>
                <th style="border:1px solid #ddd;padding:4px;">变化</th></tr>
            {stat_rows_html}
          </table>
          <div style="font-size:12px;">{reasons_html}</div>
          {plate_html}
          <div style="font-size:13px;color:#8b0000;margin:4px 0;"><b>结论依据：</b>{verdict}</div>
          <div>{''.join(img_tags)}</div>
        </div>''')
    if not sections:
        return '', None
    _plate_desc = (
        '<div style="font-size:12px;background:#f7f7f7;border:1px solid #ddd;'
        'border-radius:6px;padding:8px 10px;margin:6px 0;">'
        '<b>解释图版标准（must/core/deny 原则）：</b>'
        '气层 = Sw&lt;0.50 且 孔隙度≥10%（必选）+ RT&gt;50Ω·m（核心）；'
        '油层 = Sw&lt;0.50 且 孔隙度≥10%（必选）+ RT&gt;30Ω·m（核心）；'
        '水层 = Sw≥0.50 且 孔隙度≥10%（必选）+ RT&lt;20~25Ω·m（核心）；'
        '干层 = 孔隙度6%~10%的低孔储层。'
        '否决条件：Sw&gt;0.65 或 孔隙度&lt;6% 时排除油气层；'
        '逐点未命中图版时按归一化距离就近归类（RT取对数域）。'
        '各层交汇图背景点仅取全井储层段数据，泥岩等非储层不参与。</div>')
    return '<h3>逐油气层解释原因分析与交汇图</h3>' + _plate_desc + ''.join(sections), 'crossplots'

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

        # 【2026-10-13】逐油气层解释原因归因 + 交汇图（用户第7条）
        _hc_html, _plot_dir_rel = _build_hc_reason_sections(results)

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
                <!-- 【2026-10-13】逐油气层解释原因归因 + 交汇图 -->
                {_hc_html}
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
# ========== 声波DT曲线单位与骨架AC特征值换算（2026-10-15 用户定案）==========
# 骨架AC特征值表（theoretical_skeleton / 多矿物响应矩阵）按**英制 us/ft** 存储
# （灰岩47.5、砂岩55.5、白云岩43.5...），公制井(us/m)读取时按 3.28084 换算
# （灰岩 47.5us/ft = 156us/m）。DT_CURVE_UNIT 由 DataLoader 在 LAS 加载时设置。
DT_CURVE_UNIT = 'us/ft'
_AC_USFT_TO_USM = 3.28084

def set_dt_curve_unit(unit):
    """设置声波DT曲线单位（'us/ft' | 'us/m'），由DataLoader在LAS加载时调用。"""
    global DT_CURVE_UNIT
    s = str(unit or '').strip().lower().replace('μ', 'u').replace('µ', 'u')
    if 'ft' in s or s in ('us/f', 'f'):
        DT_CURVE_UNIT = 'us/ft'
    elif 'm' in s:
        DT_CURVE_UNIT = 'us/m'
    else:
        DT_CURVE_UNIT = 'us/ft'
    return DT_CURVE_UNIT

def dt_ac_scale():
    """骨架AC特征值随DT曲线单位的换算系数：英制井1.0，公制井3.28084。"""
    return _AC_USFT_TO_USM if DT_CURVE_UNIT == 'us/m' else 1.0

def _limestone_ac_locked():
    """灰岩骨架AC锁定值（用户定案常数）：英制47.5us/ft，公制156us/m。"""
    return 156.0 if DT_CURVE_UNIT == 'us/m' else 47.5

def _dolomite_cnl_matrix(phi):
    """白云岩骨架CNL特征值（2026-10-15 用户定案，随孔隙度分段）：
    φ 5.5%~30% → 0.085（SNP井壁中子0.035）；
    φ 1.5%~5.5% 或 >30% → 0.065（SNP井壁中子0.020）。"""
    try:
        phi = float(phi)
    except (TypeError, ValueError):
        return 0.065
    return 0.085 if (0.055 <= phi <= 0.30) else 0.065

class LithologyCrossplotAnalyzer:
    """岩性交汇图分析类，用于确定本井主要岩性类型和骨架参数"""
    
    def __init__(self):
        """初始化交汇图分析器"""
        # 理论骨架参数（参考常见岩石骨架参数表）
        # 【2026-10-15 用户定案修正】
        #   灰岩：ρ=2.71（**常数**，禁止任何聚类估计覆盖）、AC=47.5us/ft（公制156us/m）、CNL=0
        #   白云岩：CNL骨架值随孔隙度分段（φ5.5~30%→0.085/SNP0.035；
        #           φ1.5~5.5%或>30%→0.065/SNP0.020），静态表取低孔段0.065，
        #           中子-密度交汇图逐簇按簇密度估计孔隙度后取值（见analyze_cnl_density_crossplot）
        #   硬石膏：CNL=-0.02（SNP井壁中子=0.005）
        # AC单位：表值按英制us/ft存储，公制井由 self._acs 换算（灰岩156us/m）
        self._acs = dt_ac_scale()
        self.theoretical_skeleton = {
            'sandstone': {'density': 2.65, 'ac': 55.5 * self._acs, 'pe': 1.81, 'cnl': -0.02},
            'limestone': {'density': 2.71, 'ac': _limestone_ac_locked(), 'pe': 5.08, 'cnl': 0.00},
            'dolomite': {'density': 2.87, 'ac': 43.5 * self._acs, 'pe': 3.14, 'cnl': 0.065},
            'shale': {'density': 2.55, 'ac': 80.0 * self._acs, 'pe': 3.45, 'cnl': 0.35},
            'volcanic': {'density': 2.75, 'ac': 50.0 * self._acs, 'pe': 6.0, 'cnl': 0.05},
            'anhydrite': {'density': 2.98, 'ac': 50.0 * self._acs, 'pe': 5.0, 'cnl': -0.02}
        }
        # 灰岩骨架值为用户定案常数：任何交汇图聚类/自适应估计都不得覆盖
        self.locked_skeleton = {
            'limestone': {'density': 2.71, 'ac': _limestone_ac_locked(),
                          'pe': 5.08, 'cnl': 0.00}
        }
    
    def analyze_density_ac_crossplot(self, data):
        """密度-声波时差交汇图分析，确定本井主要岩性类型"""
        density_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        ac_col = 'DT' if 'DT' in data.columns else ('AC' if 'AC' in data.columns else None)
        
        if density_col is None or ac_col is None:
            return {'main_lithology': ['sandstone'],
                    'estimated_skeleton': copy.deepcopy(self.theoretical_skeleton)}
        
        densities = data[density_col].values
        ac_values = data[ac_col].values
        
        # AC有效范围随DT曲线单位换算（英制30-150us/ft，公制约98-492us/m）
        _acs = self._acs
        valid_mask = (densities > 2.0) & (densities < 3.5) & \
                     (ac_values > 30 * _acs) & (ac_values < 150 * _acs)
        if np.sum(valid_mask) < 20:
            return {'main_lithology': ['sandstone'],
                    'estimated_skeleton': copy.deepcopy(self.theoretical_skeleton)}
        
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
        # 深拷贝：浅拷贝会让聚类估计直接污染 self.theoretical_skeleton 理论表
        estimated_skeleton = copy.deepcopy(self.theoretical_skeleton)
        
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
                _p_cnl = params['cnl']
                if lith == 'dolomite':
                    # 白云岩骨架CNL随孔隙度分段（2026-10-15 用户定案）：
                    # 由簇密度反推白云岩孔隙度 φ=(2.87-ρ)/1.87 后取 0.085/0.065
                    _phi_c = float(np.clip((2.87 - cluster_density) / 1.87, 0.0, 0.45))
                    _p_cnl = _dolomite_cnl_matrix(_phi_c)
                dist = np.sqrt((cluster_cnl - _p_cnl)**2 + (cluster_density - params['density'])**2)
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
        for name in ['NPHI', 'CNL', 'CNCF']:
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

                # ========== 段类型判定改为多判据一致性 ==========
                # 【2026-10-07 修正】原逻辑：`high_density_ratio>0.3 and
                # high_rt_ratio>0.3` 即判碳酸盐，而低伽马只能**单向加强**
                # （`is_carbonate = True`），从不否决 —— 实质两条曲线。
                # 致密砂岩/粉砂质岩 ρ 可达 2.68-2.70，在砂泥岩井里占比过半
                # 并不罕见，会让整段被误判碳酸盐。
                # 现在要求：密度高 + 电阻高 + **中子低/伽马低**同时成立。
                _seg_cnl_low = False
                _seg_gr_low = False
                if nphi_col:
                    _cn = nphi_vals[start_idx:end_idx]
                    _cn = _cn[~np.isnan(_cn)]
                    if len(_cn) > 0 and np.nanmedian(_cn) < 15.0:
                        _seg_cnl_low = True
                if gr_col:
                    win_gr = gr_vals[start_idx:end_idx]
                    win_gr_valid = win_gr[win_gr > 0]
                    if len(win_gr_valid) > 0:
                        if (win_gr_valid < 60).mean() > 0.5:
                            _seg_gr_low = True
                # 密度 + 电阻 + 至少一项（低中子/低伽马）→ 碳酸盐
                if (high_density_ratio > 0.3 and high_rt_ratio > 0.3
                        and (_seg_cnl_low or _seg_gr_low)):
                    is_carbonate = True
                # 明确否决：伽马普遍高（中位>110）且中子普遍高 → 不是碳酸盐
                _gr_hi = False
                if gr_col:
                    win_gr2 = gr_vals[start_idx:end_idx]
                    w2 = win_gr2[win_gr2 > 0]
                    if len(w2) > 0 and np.nanmedian(w2) > 110.0:
                        _gr_hi = True
                _cnl_hi = False
                if cnl_col:
                    _c2 = cnl_vals[start_idx:end_idx]
                    _c2 = _c2[~np.isnan(_c2)]
                    if len(_c2) > 0 and np.nanmedian(_c2) > 20.0:
                        _cnl_hi = True
                if is_carbonate and _gr_hi and _cnl_hi:
                    is_carbonate = False   # 泥质/含水，高伽马+高中子 → 砂泥岩

                # 砂泥岩段判断（保持原样）
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
            # 深拷贝：下方各子分析结果的 merge 会改写内层dict，浅拷贝会污染理论表
            'estimated_skeleton': copy.deepcopy(self.theoretical_skeleton),
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
        
        # 【2026-10-15 用户定案】灰岩骨架值锁定：各交汇图聚类估计一律不得覆盖
        # 灰岩 ρ=2.71、AC=47.5us/ft(公制156us/m)、CNL=0 —— 此前聚类中心曾把
        # 灰岩密度估到2.348（物理错误），并污染距离判别导致岩性误分类
        for _lith, _locked in self.locked_skeleton.items():
            _sk = result['estimated_skeleton'].get(_lith)
            if _sk is None:
                continue
            for _k, _v in _locked.items():
                try:
                    _drifted = abs(float(_sk.get(_k, _v)) - float(_v)) > 1e-6
                except (TypeError, ValueError):
                    _drifted = False
                if _drifted:
                    logger.info("锁定%s骨架%s=%.3f（聚类估计%.3f不采用）",
                                _lith, _k, float(_v), float(_sk.get(_k)))
                    _sk[_k] = _v

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
        # 【2026-10-15 用户定案修正】
        #   白云岩 CNL 骨架值随孔隙度分段：φ5.5~30%→0.085（SNP0.035）、
        #   φ1.5~5.5%或>30%→0.065（SNP0.020）——静态表取低孔段0.065，
        #   优化循环内逐点按密度估计孔隙度取值（见 optimize_minerals）
        #   硬石膏 CNL=-0.02（SNP井壁中子=0.005）
        self.params = {
            'Quartz':  [2.65, -0.02, 55.5, 1.81, 30],
            'Calcite': [2.71,  0.00, 47.5, 5.08, 15],
            'Dolomite':[2.87,  0.065, 43.5, 3.14, 20],
            'Anhydrite':[2.98, -0.02, 37.5, 5.0, 10],   # 硬石膏
            'Halite':  [2.03,  0.00, 67.0, 4.70, 5],   # 盐岩NaCl
            'Clay':    [2.55,  0.35, 80.0, 3.45, 150],
            'Water':   [1.00,  1.00, 189.0, 0.00, 0],
            'Oil':     [0.85,  0.80, 220.0, 0.00, 0],
            'Gas':     [0.25,  0.20, 350.0, 0.00, 0]
        }
        # 【2026-10-15】AC单位自适应：表值按英制us/ft存储（灰岩47.5us/ft），
        # 公制井(us/m)整列换算（灰岩→156、水189→620、油220→722、气350→1148）
        _acs_mm = dt_ac_scale()
        if _acs_mm != 1.0:
            for _m in self.params:
                self.params[_m][2] = self.params[_m][2] * _acs_mm
            logger.info('声波DT为公制(us/m)：多矿物响应矩阵AC列已×%.4f换算', _acs_mm)
        
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
            # 泥质含量计算方法: 1=仅GR法, 2=仅密度中子交汇法, 3=两者结合取平均值(推荐)
            'vsh_method': 3,
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
                rho_vsh = (rho_sand - data[rho_col]) / (rho_sand - rho_shale)
                nphi_values = data[nphi_col] / 100.0 if data[nphi_col].max() > 1 else data[nphi_col]
                nphi_vsh = (nphi_values - nphi_sand) / (nphi_shale - nphi_sand)
                dn_vsh = (rho_vsh + nphi_vsh) / 2
                dn_vsh = dn_vsh.clip(0, 1)
            
            # 方法2：GR分位数计算泥质含量
            gr_vsh = None
            if 'GR' in data.columns:
                gr_data = data['GR'].dropna()
                if len(gr_data) > 0:
                    gr_min = gr_data.quantile(0.1)
                    gr_max = gr_data.quantile(0.9)
                    
                    if gr_max <= gr_min:
                        gr_min = gr_data.min()
                        gr_max = gr_data.max()
                    
                    if gr_max > gr_min:
                        gr_vsh = (data['GR'] - gr_min) / (gr_max - gr_min)
                        gr_vsh = gr_vsh.clip(0, 1)
            
            # 根据vsh_method选择计算方法
            # 1: 仅GR方法
            # 2: 仅密度中子交汇方法
            # 3: 两者结合取平均值（默认）
            if vsh_method == 1:
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
                    data['VSH'] = (gr_vsh + dn_vsh) / 2
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

            # 密度曲线别名识别(2026-10-08, BET-1): ZDEN/DEN/RHOZ 等价于 RHOB
            _den_col = None
            for _c in ('RHOB', 'ZDEN', 'DEN', 'RHOZ'):
                if _c in data.columns:
                    _den_col = _c
                    break

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
            if _den_col and use_density:
                def calculate_phi(row):
                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                    rhob = row.get(_den_col, 2.65)
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
                logger.info(f"优先使用密度孔隙度（变骨架）")
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
                            avg_cnl = np.nanmean(features[mask, 3])
                        else:
                            # 正常情况: [GR, PE, RT, DEN, CNL]
                            avg_gr = np.nanmean(features[mask, 0])
                            avg_pe = np.nanmean(features[mask, 1])
                            avg_rt = np.nanmean(features[mask, 2])
                            avg_den = np.nanmean(features[mask, 3])
                            avg_cnl = np.nanmean(features[mask, 4])
                        
                        # 碳酸盐岩特征：GR低、密度高、电阻率高
                        # 【2026-10-07 修正】PE 从碳酸盐评分中**移除**。
                        # PE 是黏土/孔隙度敏感曲线，泥岩与粉砂岩可达 4-5，
                        # 用它加分等于把砂泥岩推向碳酸盐。
                        # 改为用**中子**（碳酸盐骨架几乎不含氢，CNL<10，
                        # 且不受泥质干扰）替代 PE。
                        score_carbonate = 0
                        if avg_gr < 50: score_carbonate += 1
                        if avg_cnl < 12.0: score_carbonate += 1     # 中子极低（核心）
                        if avg_den > 2.65: score_carbonate += 1
                        if avg_rt > 80: score_carbonate += 1

                        # 砂泥岩特征：GR中高、密度中低、电阻率中低、中子偏高
                        score_sand_shale = 0
                        if avg_gr > 60: score_sand_shale += 1
                        if avg_cnl > 18.0: score_sand_shale += 1   # 中子高 = 泥质/含水
                        if avg_den < 2.65: score_sand_shale += 1
                        if avg_rt < 80: score_sand_shale += 1

                        # 阈值：满分4 项，碳酸盐需 ≥3（多判据一致性，
                        # 单项不决定结论）；砂泥岩同样需 ≥3。
                        # 两者都不满足 → mixed（保持不确定，不强行归类）
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
                    halite_skeleton = np.array([self.params['Halite'][0], self.params['Halite'][1]])
                    water_point = np.array([self.params['Water'][0], self.params['Water'][1]])

                    dist_sand = dist_to_line_mn(point, sandstone_skeleton, water_point)
                    dist_lime = dist_to_line_mn(point, limestone_skeleton, water_point)
                    dist_dolo = dist_to_line_mn(point, dolomite_skeleton, water_point)
                    dist_clay = dist_to_line_mn(point, clay_skeleton, water_point)
                    dist_halite = dist_to_line_mn(point, halite_skeleton, water_point)

                    # 【2026-10-19 岩盐】负中子是盐岩独有特征（挖掘效应），
                    # 优先于距离判定：一切含氢骨架的中子响应都 >0
                    if cnl_for_ident < -1.0 and den < 2.20:
                        mn_lithology = 'halite'
                    else:
                        # 找到距离最近的矿物线
                        min_dist = min(dist_sand, dist_lime, dist_dolo, dist_clay,
                                       dist_halite)

                        if min_dist == dist_halite:
                            mn_lithology = 'halite'
                        elif min_dist == dist_sand:
                            mn_lithology = 'sandstone'
                        elif min_dist == dist_lime:
                            mn_lithology = 'limestone'
                        elif min_dist == dist_dolo:
                            mn_lithology = 'dolomite'
                        else:
                            mn_lithology = 'shale'
                    
                    # 使用PE辅助区分灰岩和白云岩（PE可靠时）
                    if not np.isnan(pe) and pe > 0:
                        current_pe_weight = pe_weights[i] if i < len(pe_weights) else 1.0
                        if current_pe_weight > 0.5:
                            if mn_lithology == 'dolomite' and pe > 4.0:
                                mn_lithology = 'limestone'  # PE高更可能是灰岩
                            elif mn_lithology == 'limestone' and pe < 3.0:
                                mn_lithology = 'dolomite'  # PE低更可能是白云岩
                
                # 结合物理约束修正：高密度不可能是泥岩
                # 【2026-10-07 修正】原写法 `den>2.60 and pe>3.0 → limestone`
                # 是两条曲线、无中子/声波/伽马验证，且 PE 在砂泥岩中同样可达 4-5。
                # 实测 BET-1 砂泥岩剖面 ρ2.47-2.73 / PE3.5-4.8，
                # 按原写法全井都会被改判成灰岩。
                # 现在要求：改判灰岩必须**中子极低 + 伽马低**同时成立；
                # 高密度但中子/伽马不支持的段改判为**砂岩**（致密砂岩/粉砂岩），
                # 这是物理上更合理的归属。
                if den > 2.60 and mn_lithology == 'shale':
                    _cnl_m = row.get('NPHI', row.get('CNL', np.nan))
                    try:
                        _cnl_m = float(_cnl_m)
                    except (TypeError, ValueError):
                        _cnl_m = np.nan
                    # 中子低 + 伽马低 → 碳酸盐；否则归致密砂岩
                    _carb_like = (not np.isnan(_cnl_m) and _cnl_m < 12.0
                                  and not np.isnan(gr) and gr < 70.0)
                    if _carb_like:
                        mn_lithology = 'dolomite' if den > 2.85 else 'limestone'
                    elif den > 2.85 and not np.isnan(_cnl_m) and _cnl_m < 8.0:
                        mn_lithology = 'dolomite'
                    else:
                        mn_lithology = 'sandstone'  # 致密砂岩/粉砂岩

                # 高密度+低GR不可能是泥岩
                # 同样要求中子配合（低伽马只说明"不是泥质"，可能是致密砂岩）
                if den > 2.60 and gr < 60 and mn_lithology == 'shale':
                    _cnl_m2 = row.get('NPHI', row.get('CNL', np.nan))
                    try:
                        _cnl_m2 = float(_cnl_m2)
                    except (TypeError, ValueError):
                        _cnl_m2 = np.nan
                    if not np.isnan(_cnl_m2) and _cnl_m2 < 12.0:
                        mn_lithology = 'dolomite' if den > 2.85 else 'limestone'
                    else:
                        mn_lithology = 'sandstone'  # 低伽马+高密度 → 致密砂岩
                
                # 设置逐点预判标志
                is_sand_shale = mn_lithology in ['sandstone', 'shale']
                is_carbonate = mn_lithology in ['limestone', 'dolomite']
                
                # 获取当前点的段类型
                seg_type = segment_labels[i] if i < len(segment_labels) else 'mixed'
                
                # ========== PE+密度强制覆盖：改为多判据一致性 ==========
                # 【原逻辑缺陷（2026-10-07 修正，闭环自证）】
                #   原写法：`den > 2.68 and pe > 3.5` 就强制 seg_type='carbonate'，
                #   并把 Calcite/Dolomite 上界从砂泥岩段的 0.05 **放开到 1.0**。
                #   这构成一个**自证闭环**：
                #       PE 高 → 放开碳酸盐约束 → 优化器必然能压出高 VCalcite
                #       → classify_lithology 的 vcarbonate>0.5 命中 → 判灰岩
                #   即"PE 高"既当判据又当"允许碳酸盐"的许可，判据自我实现。
                #
                #   为什么 PE 不能单独定性：PE 是**黏土/孔隙度敏感**曲线，
                #   泥岩、粉砂岩、碳酸质泥岩 PE 可达 4-5。实测 BET-1 砂泥岩剖面
                #   PE 3.5-4.8，若按原逻辑，6460-8935 ft 会有 70 多段被判灰岩
                #   （实测那些段 ρ2.47-2.73、Δt66-107、CNL 11-34、GR 86-142，
                #   没有一项符合灰岩的 CNL<10 / Δt45-80 / GR<40）。
                #
                # 【修正后的多判据】
                #   碳酸盐岩的**核心判别项是中子**（CaCO3/CaMg(CO3)2 骨架几乎
                #   不含氢，CNL 通常 <10%，且不受泥质干扰），PE/密度/伽马/
                #   电阻率都受泥质与孔隙度干扰，只能辅助。因此要求：
                #       中子低（核心，双倍权重）+ 伽马低 + 密度高，三者同时成立
                #   才放开碳酸盐约束。
                pe_override = False
                _carb_ev = 0.0
                # 中子：本循环内没有 nphi 变量，从 row 直接取
                _cnl_e = row.get('NPHI', row.get('CNL', np.nan))
                if isinstance(_cnl_e, (int, float)) and np.isnan(_cnl_e):
                    _cnl_e = np.nan
                try:
                    _cnl_e = float(_cnl_e)
                except (TypeError, ValueError):
                    _cnl_e = np.nan
                if not pe_unreliable:
                    if (not np.isnan(pe) and pe > 3.5 and not np.isnan(_cnl_e)
                            and _cnl_e < 12.0):
                        _carb_ev += 2.0        # 中子极低 + PE 高（强碳酸盐）
                    if (is_carbonate and not np.isnan(pe) and pe > 3.0
                            and not np.isnan(_cnl_e) and _cnl_e < 15.0):
                        _carb_ev += 1.5        # M-N交汇图 + 中子低
                    if (not np.isnan(gr) and gr < 70.0):
                        _carb_ev += 1.0        # 伽马低（碳酸盐不放伽马）
                    if den > 2.65:
                        _carb_ev += 1.0
                    # 中子或伽马明确不支持 → 硬否决（防止泥质段被放开）
                    if (not np.isnan(_cnl_e) and _cnl_e > 18.0) or \
                            (not np.isnan(gr) and gr > 110.0):
                        _carb_ev = 0.0
                    pe_override = _carb_ev >= 3.5

                if pe_override and seg_type != 'carbonate':
                    seg_type = 'carbonate'
                    logger.debug('PE覆盖为碳酸盐段@深度%.1f: 证据分%.1f', den, _carb_ev)
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
                elif mn_lithology == 'halite':
                    # 【2026-10-19 岩盐】盐岩初始点：Halite 主导、φ≈0
                    x0_halite = np.array([0.03, 0.02, 0.02, 0.01, 0.80, 0.10, 0.02])
                    initial_guesses.append(x0_halite)
                    x0_halite_pure = np.array([0.01, 0.01, 0.01, 0.005, 0.95, 0.01, 0.005])
                    initial_guesses.append(x0_halite_pure)
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

                # 【2026-10-15 用户定案】白云岩骨架CNL随孔隙度分段：
                # φ5.5~30%→0.085、φ1.5~5.5%或>30%→0.065。按本点白云岩密度
                # 孔隙度 φ=(2.87-ρ)/1.87 选取，逐点覆盖响应矩阵 Dolomite 行
                # CNL 列（列1）。其余矿物/流体值不变。
                _den_col_i = mapped_curves.get('DEN')
                try:
                    _den_i = float(row[_den_col_i]) if _den_col_i else np.nan
                except (TypeError, ValueError):
                    _den_i = np.nan
                if np.isnan(_den_i):
                    _phi_dol = 0.05
                else:
                    _phi_dol = float(np.clip((2.87 - _den_i) / 1.87, 0.0, 0.45))
                A_min_i = A_min.copy()
                A_min_i[2, 1] = _dolomite_cnl_matrix(_phi_dol)
                
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
                            
                            res = minimize(objective_with_lasso, x0, args=(meas, A_min_i, A_fluid, current_pe_weight, mn_weights, profile_penalty_factor),
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
                            res = minimize(objective_with_lasso, x0, args=(meas, A_min_i, A_fluid, current_pe_weight, mn_weights, profile_penalty_factor),
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
    
    def _identify_typical_water_layers(self, data, por_hc=None):
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
            # 动态检测可用电阻率列（跳过全零/全NaN列，见 select_resistivity_column）
            rt_col_name = select_resistivity_column(data)
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
            # 默认碳酸盐岩下限；分井覆盖 ← <井名>info.json「解释截止值」(por_hc)
            min_porosity = 0.06 if por_hc is None else por_hc
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
            rt_col_name = select_resistivity_column(data)
            if 'PHI' not in data.columns or rt_col_name is None:
                logger.warning("缺少PHI或有效电阻率列，无法自动计算Rw")
                return None, None
            
            rt = data[rt_col_name].copy()
            phi = data['PHI'].copy()
            md = data['MD'].values
            logger.info(f"自动检测Rw使用电阻率列: {rt_col_name}")
            
            # ========== 识别典型厚水层 ==========
            water_layers = self._identify_typical_water_layers(
                data, por_hc=get_active_cutoffs().get('por_hc'))
            
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
            # 动态检测可用电阻率列（支持阵列电阻率 AT90/AT60/M2RX 及 LWD 深电阻率 RD；
            # 跳过全零/全NaN列 —— BET-1 兜底生成的全 0 RT 列曾致 Sw 恒为 1）
            rt_col_name = select_resistivity_column(data)
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
                # 选中列非RT时回填标准RT列(BET-1: RT全0兜底列被RD替换)，
                # 使绘图RT道/高级解释引擎/知识库统一使用有效深电阻率
                if rt_col_name != 'RT':
                    data['RT'] = data[rt_col_name]
                    logger.info(f"RT列无效/缺失，已用 {rt_col_name} 回填标准RT列")
                
                # 计算Sw
                # 使用阿尔奇公式：Sw = (a * Rw / (φ^m * RT))^(1/n)
                data['Sw'] = (a * Rw / (data['PHI']**m * rt))**(1/n)
                data['Sw'] = data['Sw'].clip(0, 1)
                
                # 计算含油饱和度
                data['So'] = 1 - data['Sw']
                
                # 计算含气饱和度（简化处理）
                data['Sg'] = 0
                
                # 有效曲线不足3条的井段不计算饱和度
                if 'VALID_CURVES_COUNT' in data.columns:
                    data.loc[data['VALID_CURVES_COUNT'] < 3, ['Sw', 'So', 'Sg']] = np.nan
                return data
            else:
                # 【2026-10-20 修复 3-SPS-111D 全井 Sw=1.0 → 0 个油气结论】
                # 本方法在矿物分析阶段运行，早于孔隙度计算（111D 实测时序：
                # Multi-mineral analysis 14:49:28 → PORD/PHI←MPHE 14:49:34）。
                # 此前缺 PHI 时写常数 Sw=1.0，被主流程"Sw已存在→跳过重算"
                # 守卫误信，全井 Sw 恒 1，Sw≥0.5 只能判 WATER/DRY。
                # 现改为**不写 Sw 列**，留待主流程孔隙度就绪后统一计算
                # （一处一功能：Sw 计算唯一入口仍是本方法）。
                logger.info("calculate_saturation: PHI或有效电阻率列缺失，"
                            "跳过（不写常数Sw，留待主流程孔隙度就绪后计算）")
                return data
        except Exception as e:
            logger.error(f"计算饱和度失败: {e}")
            # 【2026-10-20】异常时同样不写常数 Sw=1.0（留待主流程重算，
            # 常数会被"Sw已存在"守卫误信——见上方 else 分支注释）
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
        for name in ['RHOB', 'DEN', 'ZDEN']:
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
        for name in ['GR', 'GRX', 'GR_XMAC']:
            if name in data.columns:
                gr_vals = data[name].dropna()
                gr_vals = gr_vals[gr_vals > -999]
                if len(gr_vals) > 50:
                    gr_median = gr_vals.median()
                break
        rt_col = None
        for name in ['LLD', 'RD', 'RT', 'ILD', 'AT90', 'RMSL', 'M2RX', 'RDEEP']:
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
                            den_supports_carbonate = True
                            if density_col:
                                den_vals = data[density_col].dropna()
                                den_vals = den_vals[den_vals > 0]
                                if len(den_vals) > 100:
                                    den_med = den_vals.median()
                                    den_high = (den_vals > 2.60).sum() / len(den_vals)
                                    # 密度不支持碳酸盐岩
                                    if den_med < 2.60 or den_high < 0.30:
                                        den_supports_carbonate = False
                                        logger.warning(
                                            f"PE anomaly but density rejects carbonate: "
                                            f"PE>3.5 in {pe_carbonate_ratio*100:.1f}% BUT "
                                            f"DEN median={den_med:.3f}, DEN>2.60 only "
                                            f"{den_high*100:.1f}%. Skipping PE override."
                                        )
                            # ========== 【2026-10-07 修正】中子与伽马校验 ==========
                            # 原逻辑只查密度（且密度否决条件写得很松：
                            # 需"中位数<2.55 且 >2.60占比<20%"两个同时成立才否决，
                            # 任一不满足就放行），导致 BET-1 这类砂泥岩井
                            # PE 3.5-4.8 的高占比直接触发 carbonate override。
                            #
                            # 碳酸盐岩的**核心判别项是中子**（CaCO3 骨架几乎不含氢，
                            # CNL<10），伽马也极低（<40）。实测 BET-1 砂泥岩剖面
                            # CNL 中位 23.4、GR 中位 155、低伽马(<40)占 0%，
                            # 两项都明确不支持碳酸盐。
                            cnl_supports = True
                            gr_supports = True
                            for _cn in ('NPHI', 'CNL', 'CNCF'):
                                if _cn in data.columns:
                                    _v = pd.to_numeric(data[_cn], errors='coerce').dropna()
                                    if len(_v) > 100 and _v.median() > 15.0:
                                        cnl_supports = False
                                    break
                            for _g in ('GR', 'GRX', 'GR_XMAC'):
                                if _g in data.columns:
                                    _v = pd.to_numeric(data[_g], errors='coerce').dropna()
                                    if len(_v) > 100:
                                        _low = (_v < 40).mean()
                                        if _low < 0.20 or _v.median() > 110.0:
                                            gr_supports = False
                                    break
                            if not (cnl_supports and gr_supports):
                                den_supports_carbonate = False
                                logger.warning(
                                    f"PE anomaly rejected by CNL/GR: "
                                    f"CNL_supports={cnl_supports}, "
                                    f"GR_supports={gr_supports}. "
                                    f"Skipping PE override (砂泥岩剖面特征)."
                                )
                            if den_supports_carbonate:
                                has_carbonate = True
                                logger.info(f"PE carbonate override: PE>3.5 in {pe_carbonate_ratio*100:.1f}% of points, "
                                            f"density+CNL+GR confirm carbonate")
                                if 'limestone' not in main_lithology:
                                    main_lithology.append('limestone')
            
            # ========== 密度强约束：密度中位数>2.70大概率是碳酸盐岩 ==========
            # 【2026-10-07 修正】原判据 `den_median > 2.70 or den_high_ratio > 0.5`
            # 是**单一密度统计量**，而致密砂岩/粉砂质岩 ρ 可达 2.68-2.70，
            # 在砂泥岩井里 den>2.68 占比过半并不罕见。
            # 碳酸盐岩的密度高必须与"中子极低 + 伽马极低"同时成立，
            # 因为后两者不受致密性影响。密度只是一项辅助。
            if density_col and not has_carbonate:
                valid_den = data[density_col].dropna()
                valid_den = valid_den[valid_den > 0]
                if len(valid_den) > 100:
                    den_median = valid_den.median()
                    den_high_ratio = (valid_den > 2.68).sum() / len(valid_den)
                    # 中子与伽马也要支持碳酸盐
                    cnl_ok = True
                    gr_ok = True
                    for _cn in ('NPHI', 'CNL', 'CNCF'):
                        if _cn in data.columns:
                            _v = pd.to_numeric(data[_cn], errors='coerce').dropna()
                            if len(_v) > 100 and _v.median() > 15.0:
                                cnl_ok = False
                            break
                    for _g in ('GR', 'GRX', 'GR_XMAC'):
                        if _g in data.columns:
                            _v = pd.to_numeric(data[_g], errors='coerce').dropna()
                            if len(_v) > 100 and (( _v < 40).mean() < 0.20
                                                   or _v.median() > 110.0):
                                gr_ok = False
                            break
                    if (den_median > 2.70 or den_high_ratio > 0.5) and cnl_ok and gr_ok:
                        has_carbonate = True
                        logger.info(f"密度强约束：ρ中位={den_median:.3f}，>2.68占比="
                                    f"{den_high_ratio*100:.1f}%，且中子/伽马支持碳酸盐")
                        if 'limestone' not in main_lithology:
                            main_lithology.append('limestone')
                    elif den_median > 2.70 or den_high_ratio > 0.5:
                        logger.info(f"密度偏高但中子/伽马不支持碳酸盐"
                                    f"（ρ中位={den_median:.3f}, CNL_ok={cnl_ok}, "
                                    f"GR_ok={gr_ok}），不注入 limestone")
            
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
                
                # 从GR计算泥质含量
                if 'GR' in data.columns:
                    gr = data['GR'].values
                    gr_min = np.nanmin(gr)
                    gr_max = np.nanmax(gr)
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
            
            data = self.calculate_saturation(data)
            
            # ========== 计算 VSH（泥质含量）用于解释引擎 ==========
            # 注意：optimize_minerals 只在异常回退路径中调用 calculate_vsh，
            # 正常优化成功路径中不创建 VSH 列，需要在此显式计算
            if 'VSH' not in data.columns:
                vsh_method = self.config.get('vsh_method', 3)
                data = self.calculate_vsh(data, vsh_method)
                logger.info(f"计算 VSH 完成（方法{vsh_method}），VSH 范围: {data['VSH'].min():.4f}-{data['VSH'].max():.4f}")
            
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
            
            def detect_special_mineral(row):
                """
                检测特殊矿物，返回 (special_mineral_type, score, reason)
                如果未检测到特殊矿物，返回 (None, 0, '')
                
                **核心原则（2026-10-07 重写）：多判据一致性判定，
                任何单一参数都不足以定性一个岩性**
                
                判定采用三段式：
                  1. **必要项**：该矿物物理上不可缺的特征，缺一即否决；
                  2. **一致性项**：至少 N 项（M-of-K）同时成立才判定，
                     单条判据不决定结论；
                  3. **排除项**：命中即否决，用于区分易混矿物/岩性。
                这样可避免"密度低就判煤""中子高就判碳质泥岩"这类误判。
                
                检测顺序与判据：
                1. 煤层 Coal —— 必要项 ρ<2.00 且 Δt>100（煤必须明显高声波、
                   高阻、中子、低伽马；**不是密度小于1.7就是煤**）；
                   一致性项要求至少 4 项：极低密度/高声波/高中子/低Pe/
                   低伽马/中高阻
                2. 黄铁矿 Pyrite —— ρ>3.5 且 PE>10（必须同时满足）
                3. 盐岩 Halite —— 密度1.95-2.15 + 声波60-75 + 中子-5~5 + 
                   低GR(<40) + 低电阻率(<50) + 扩径（六项必须同时满足）
                4. 石膏 Gypsum —— 密度2.20-2.45 + 中子>35(结晶水) + 声波45-60 + 低GR
                5. 硬石膏 Anhydrite —— 密度>2.80 + 声波<55 + 低GR（必须同时满足）
                
                各矿物标准参数（用于对比）：
                - 盐岩：密度2.03, AC 67, 中子~0, 低GR, 低阻, 扩径
                - 石膏：密度2.32, AC 52, 中子~49, PE 3.99, 低GR
                - 硬石膏：密度2.98, AC 50, PE 5.0, 低GR
                - 煤：密度1.45-1.80, AC 115-127, 中子40-55, PE 1.2-2.2,
                  **GR 86-110（低伽马）**
                - 碳质泥岩：密度2.00-2.40, AC 88-105, 中子24-36, PE 2.3-3.0,
                  **GR 105-190（中高伽马）**
                - 黄铁矿：密度5.0, PE>15
                
                严防误判：砂泥岩孔隙度20%时密度=2.12，与盐岩(2.03)接近但声波完全不同(砂岩AC高得多)
                """
                # 提取测井值
                density = row.get('RHOB', row.get('DEN', 2.65))
                ac = row.get('DT', row.get('AC', 55.5))
                gr = row.get('GR', 50)
                pe = row.get('PE', row.get('PEF', 2.5))
                # 【2026-10-07 修正】中子缺省值必须用 NaN，不能用 0。
                # 原写法 `row.get('NPHI', row.get('CNL', 0))` 有致命后果：
                # 无中子曲线时 nphi=0，而 0 < 12.0 成立 → 碳酸盐判据直接顶满；
                # 再叠加 ac 缺省 55.5(<85)、gr 缺省 50(<75)、ρ>2.65，
                # 只要密度>2.65 就必然判成灰岩。缺省值一律用 NaN，
                # 让"该判据不可用"而不是"该判据成立"。
                nphi = row.get('NPHI', row.get('CNL', np.nan))
                if isinstance(nphi, (int, float)) and np.isnan(nphi):
                    nphi = np.nan
                rt = row.get('AT90', row.get('LLD', row.get('RT', 50)))
                bit = row.get('BIT', 8.5)
                cal = row.get('CAL', row.get('CALS', bit))
                cal_ratio = cal / max(bit, 0.1) if bit > 0 else 1.0
                
                # 跳过无效数据
                if density <= 0 or np.isnan(density):
                    return (None, 0, '')
                
                # 扩径严重(>1.25)时，密度/中子/PE/声波均已失真，跳过所有特殊矿物检测
                if cal_ratio > 1.25:
                    return (None, 0, '')
                
                # ---- 1. 煤层检测 (Coal) [多判据一致性，2026-10-07 重写] ----
                # 【原逻辑缺陷】以 `density < 1.6` 作为**唯一触发条件**，
                #   虽名为"打分"，但入口判断本身就是单条件：任何密度够低的
                #   地层（高孔隙砂岩、泥质疏松层、坏数据）都会进入打分区，
                #   再靠"高声波/高中子"两个加分项凑够 5 分而被误判为煤。
                #   正确做法：密度只是必要条件之一，还必须**同时**满足
                #   高声波、高中子、低 Pe、**低伽马**（用户指出煤低伽马、
                #   碳质泥岩中高伽马，这是煤与泥岩/碳质泥岩的最强判别项）。
                #
                # 【多判据设计】必要项(全满足) + 一致性项(至少 N 项)
                #   必要项: ρ<2.00、Δt>100（用户：煤必须明显高声波高阻，
                #           不是"密度小于1.7就是煤"）
                #   一致性: 至少 4 项成立 —— 极低密度/高声波/高中子/低Pe/
                #           低伽马/中高阻
                #   排除项: 高伽马且密度不够低 → 泥质层（用 AND 语义，
                #           避免误杀 GR 140-150 的灰分煤）
                if _skip_coal:
                    pass  # 井级排除：砂泥岩剖面不会有煤
                elif (0.80 < density < 2.00          # 必要项1：极低密度
                      and ac > 100.0):              # 必要项2：高声波（必备！）
                    # 井眼质量否决：扩径严重时密度/中子/PE 全部失真
                    if cal_ratio > 1.25:
                        return (None, 0, '')

                    coal_score = 0.0
                    coal_hits = 0
                    coal_reasons = [f'极低密度({density:.3f})', f'高声波({ac:.0f})']
                    coal_score += 2.0 + 2.0   # 两条必要项各计 2 分

                    # 一致性项（多判据印证）
                    cons = [
                        (density < 1.80, 2.0, f'密度极低({density:.2f}<1.80)'),
                        (density < 1.60, 1.5, f'密度<1.60({density:.2f})'),
                        (ac > 115.0, 1.5, f'高声波({ac:.0f}>115)'),
                        (ac > 120.0, 1.0, f'极高声波({ac:.0f}>120)'),
                        (nphi > 32.0, 1.5, f'高中子({nphi:.0f}>32)'),
                        (nphi > 38.0, 1.0, f'极高中子({nphi:.0f}>38)'),
                        (not np.isnan(pe) and pe < 2.20, 1.5, f'低Pe({pe:.2f})'),
                        (gr < 110.0, 2.0, f'低伽马({gr:.0f}<110)'),
                        (gr < 95.0, 1.0, f'极低伽马({gr:.0f}<95)'),
                        (rt > 2.50, 1.0, f'中高阻({rt:.1f})'),
                        (cal_ratio > 1.05, 0.5, f'扩径({cal_ratio:.2f})'),
                    ]
                    for hit, w, txt in cons:
                        if hit:
                            coal_hits += 1
                            coal_score += w
                            coal_reasons.append(txt)

                    # 排除项（多条件 AND）：高伽马且密度不够低 → 泥质层
                    if gr > 150.0 and density > 1.80:
                        return (None, 0, '')
                    if gr > 135.0 and density > 1.95:
                        return (None, 0, '')

                    # M-of-K：必须至少 4 项一致性判据同时成立
                    if coal_hits >= 4 and coal_score >= 7.0:
                        return ('coal', coal_score,
                                '%s [%d项一致]' % ('; '.join(coal_reasons),
                                                  coal_hits))
                
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
                
                # ---- 3. 盐岩检测 (Halite) [NaCl] ----
                # 标准值：密度2.03, AC 67, 中子~0, 低电阻率（盐溶于水导电）, 低GR, 扩径
                # 盐岩溶于钻井液→井径扩大+钻井液变咸→电阻率降低
                # 实际测井中密度常偏高(2.15-2.25)，因杂质/扩径影响，放宽密度上限至2.25
                # 核心六项全部同时满足才触发，砂泥岩绝不可能通过全部六项
                if (density > 1.95 and density < 2.25 and  # 密度窗口（放宽，实际常偏高）
                    ac > 60 and ac < 75 and                 # 声波窗口 ±7.5
                    nphi > -5 and nphi < 5 and              # 中子窗口 ±5
                    gr < 40 and                             # 低GR（蒸发岩）
                    rt < 50 and                             # 低电阻率（盐溶于水）
                    cal_ratio > 1.05):                      # 扩径（盐岩溶解）
                    halite_score = 6  # 核心六项全部命中=6分
                    halite_reasons = [
                        f'密度({density:.2f})≈2.03',
                        f'声波({ac:.0f})≈67',
                        f'中子({nphi:.1f})≈0',
                        f'低GR({gr:.0f})',
                        f'低电阻率({rt:.1f})',
                        f'扩径({cal_ratio:.2f})',
                    ]
                    if halite_score >= 4:
                        return ('halite', halite_score, '; '.join(halite_reasons))
                
                # ---- 4. 石膏检测 (Gypsum) [CaSO₄·2H₂O] ----
                # 标准值：密度2.32, AC 52, 中子~49(结晶水), PE 3.99, 低GR
                # 关键区分特征：密度中等+中子极高（其他矿物没有这个组合）
                # 砂泥岩中子一般为中等(5-25)，不会>35，因此中子>35是石膏的强区分特征
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
                    
                    if gypsum_score >= 4:
                        return ('gypsum', gypsum_score, '; '.join(gypsum_reasons))
                
                # ---- 5. 硬石膏检测 (Anhydrite) [CaSO₄] ----
                # 标准值：密度2.98, AC 50, PE 5.0, 低GR
                # 砂岩最高密度约2.65，灰岩2.71，白云石2.87
                # 密度>2.80即超过所有砂泥岩和灰岩，是硬石膏的强区分特征
                if (density > 2.80 and      # 必须>2.80（超过砂泥岩和灰岩范围）
                    ac < 55 and             # 低声波（比灰岩47略高，远低于砂岩）
                    gr < 60):               # 低GR（蒸发岩）
                    anhydrite_score = 3  # 核心三项命中=3分（阈值=3）
                    anhydrite_reasons = [
                        f'极高密度({density:.2f})>2.80',
                        f'低声波({ac:.0f})<55',
                        f'低GR({gr:.0f})',
                    ]
                    
                    # PE确认
                    if not np.isnan(pe) and pe > 4.0:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'高PE({pe:.1f})')
                    
                    # 排除白云岩（密度2.87，声波43.5）
                    # 白云岩密度也在2.87附近，但声波更低且GR不一定低
                    if density > 2.90:
                        anhydrite_score += 1
                        anhydrite_reasons.append('密度>2.90(排除白云岩)')
                    
                    # 优化确认
                    vanhydrite_val = row.get('VAnhydrite', 0)
                    if vanhydrite_val > 0.2:
                        anhydrite_score += 1
                        anhydrite_reasons.append(f'优化确认(VAnh={vanhydrite_val:.2f})')
                    
                    if anhydrite_score >= 3:
                        return ('anhydrite', anhydrite_score, '; '.join(anhydrite_reasons))
                
                return (None, 0, '')
            
            def classify_lithology(row):
                vclay = row.get('VClay', row.get('VSH', 0))
                vquartz = row.get('VQuartz', 0)
                vcalcite = row.get('VCalcite', 0)
                vdolomite = row.get('VDolomite', 0)
                vanhydrite = row.get('VAnhydrite', 0)
                vhalite = row.get('VHalite', 0)
                vbasalt = row.get('VBasalt', 0)
                
                density = row.get('RHOB', row.get('DEN', 2.65))
                ac = row.get('DT', row.get('AC', 55.5))
                gr = row.get('GR', 50)
                pe = row.get('PE', row.get('PEF', 2.5))
                # 【2026-10-07 修正】中子缺省值必须用 NaN，不能用 0。
                # 原写法 `row.get('NPHI', row.get('CNL', 0))` 有致命后果：
                # 无中子曲线时 nphi=0，而 0 < 12.0 成立 → 碳酸盐判据直接顶满；
                # 再叠加 ac 缺省 55.5(<85)、gr 缺省 50(<75)、ρ>2.65，
                # 只要密度>2.65 就必然判成灰岩。缺省值一律用 NaN，
                # 让"该判据不可用"而不是"该判据成立"。
                nphi = row.get('NPHI', row.get('CNL', np.nan))
                if isinstance(nphi, (int, float)) and np.isnan(nphi):
                    nphi = np.nan
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
                
                # ========== 玄武岩优先判断 ==========
                # 玄武岩特征：高密度+高GR+高电阻率，常见于碳酸盐岩剖面底部
                # 注意：特殊矿物（硬石膏等）已在上方拦截
                if vbasalt > 0.3 or (density > 2.70 and gr > 80 and pe < 3.5):
                    return 'volcanic'

                # ========== 物理约束优先判断 ==========
                # 高密度(>2.60)不可能是纯泥岩：泥岩密度一般不超过2.55-2.60
                # 这是物理规律，必须在最优化结果之前检查
                # 【2026-10-07】把中子提到外层：砂泥岩兜底判定也要用它
                _cnl_v = nphi
                _dt_v = ac
                if density > 2.60:
                    # ========== 密度+PE 碳酸盐信号：改为多判据一致性 ==========
                    # 【原逻辑缺陷（2026-10-07 修正）】
                    #   原写法：`density > 2.68 and pe > 3.5` 就**无条件**判灰岩。
                    #   问题：PE 是**孔隙度/泥质敏感的**曲线 —— 泥岩、粉砂岩
                    #   只要有黏土，PE 就可达 3.5-4.5，**根本不能单独定性**。
                    #   BET-1 实测反例（砂泥岩剖面被误判成灰岩 70+ 段）：
                    #     6716 ft  ρ2.59 PE4.83 GR137 → 判灰岩（实际是泥岩）
                    #     7466 ft  ρ2.37 PE4.52 GR137 → 判灰岩（实际是泥岩）
                    #     8486 ft  ρ2.64 PE4.50 GR97  → 判灰岩（实际是砂泥岩）
                    #   这些段 ρ 明显低于灰岩下限 2.65，Δt 88-107 也不是灰岩的
                    #   45-80，中子 23-34 更不是灰岩的 0-8。
                    #
                    # 【正确的多判据】
                    #   灰岩必须**同时**满足：密度高 + 中子极低 + 声波低 + 伽马低。
                    #   中子是碳酸盐岩的**核心判别项**（碳酸盐骨架几乎不含氢，
                    #   CNL 通常 <10%），密度只是辅助 —— 因为密度会被泥质、
                    #   孔隙度影响，而中子在碳酸盐中不受这些干扰。
                    # 碳酸盐岩 4 项一致性：CNL<12（核心）、Δt<85、ρ>2.62、GR<75
                    # （_cnl_v/_dt_v 已在上面提到本分支之外）
                    _carb_hits = 0
                    if not np.isnan(_cnl_v) and _cnl_v < 12.0:
                        _carb_hits += 2          # 中子极低是碳酸盐的强判别项（双倍权重）
                    if not np.isnan(_dt_v) and _dt_v < 85.0:
                        _carb_hits += 1
                    if density > 2.65:
                        _carb_hits += 1
                    if gr < 75.0:
                        _carb_hits += 1
                    # PE 只作**辅助**（权重 0.5），且要求中子也低才生效：
                    # 泥岩 PE 高是因为含黏土，不是碳酸盐
                    if (not np.isnan(pe) and pe > 3.5
                            and not np.isnan(_cnl_v) and _cnl_v < 18.0):
                        _carb_hits += 0.5

                    # 至少 3.5 分（即中子极低 + 至少两项）才判碳酸盐
                    # 【硬否决 2026-10-07】伽马/中子明确不支持时一律不判碳酸盐。
                    # 缺了这一条会漏掉：BET-1 的 GR=142 高泥质段靠
                    # "CNL<12(+2) + Δt<85(+1) + ρ>2.65(+1)" 就能拿 4 分判灰岩。
                    _carb_blocked = False
                    if not np.isnan(_cnl_v) and _cnl_v > 15.0:
                        _carb_blocked = True
                    if not np.isnan(gr) and gr > 110.0:
                        _carb_blocked = True
                    if not _carb_blocked and _carb_hits >= 3.5:
                        if density > 2.85:
                            return 'dolomite'
                        else:
                            return 'limestone'

                    # 【2026-10-07 修正】以下三条原路径依赖 PETRO 矿物含量或
                    # 单条 PE，均为**实质单条件判断**，已删除：
                    #   原① gr<60 and (vcarbonate>0.3 or pe>3.0) → 灰岩/白云岩
                    #   原② vcarbonate > 0.5 → 灰岩/白云岩
                    #   原③ vquartz > 0.3 → 砂岩
                    # 原因：vcarbonate/vquartz 是 PETRO/Wyllie 优化量，而在
                    # 高密度段它必然偏高（要同时满足 ρ 观测与低 CNL 观测，
                    # 方解石是唯一能把 CNL 拉低的矿物），于是
                    # "密度高 + 中子偏高" 一定被解释成"含方解石"——
                    # 与真实岩性无关。加上 pe_override 曾放开碳酸盐约束，
                    # 形成"PE高 → 放开约束 → 优化出方解石 → 判灰岩"的闭环。
                    # 现在：碳酸盐只由 _carb_hits（中子为核心）决定；
                    # 未命中 _carb_hits 的高密度段一律交给下面的砂泥岩逻辑。
                    # 高密度+低GR→碳酸盐岩或致密砂岩
                    if gr < 60:
                        return 'sandstone'
                    # 其余高密度但中子/伽马不支持碳酸盐的段 → 落到砂泥岩逻辑
                
                # 泥岩判断：需要同时满足低密度和高泥质含量
                # 密度>2.60的层不应判为泥岩
                if (vclay > 0.5 or gr > 100) and density < 2.60:
                    return 'shale'

                # ========== 砂泥岩兜底：按伽马+密度多判据判定 ==========
                # 【2026-10-07 新增】删除了原"基于最优化矿物含量的核心逻辑"
                # （vcarbonate>0.5→灰岩、vquartz>0.5→砂岩）之后，
                # 高密度且 GR 在 95-110 的段会一路穿透到这里并被标成 mixed/
                # Unknown。实测 BET-1 修正后 LITHOLOGY 变成"几乎全砂岩"，
                # 就是因为这里缺了砂泥岩的判定。
                #
                # 专家意见：**"全井段是明显的砂泥岩剖面…就是凭伽马就很好判断"**
                # 砂泥岩的判别核心是**伽马**（泥质含量）与**密度**：
                #   泥岩：GR 高（>110）+ 密度中高（2.40-2.60）
                #   砂岩：GR 低（<80）+ 密度中低（2.10-2.45）
                _ss_hits = 0
                if gr > 110:
                    _ss_hits += 2          # 高伽马 = 泥质（核心）
                elif gr > 95:
                    _ss_hits += 1
                if density > 2.40:
                    _ss_hits += 1          # 中高密度
                if not np.isnan(_cnl_v) and _cnl_v > 20.0:
                    _ss_hits += 1          # 中子偏高（含泥质水）
                if gr > 140 and density > 2.45:
                    _ss_hits += 1          # 高伽马+高密度 → 典型泥岩
                if _ss_hits >= 3:
                    return 'shale'
                if gr < 85:
                    return 'sandstone'
                # 介于两者之间 → 按砂泥岩互层处理，倾向砂（保守）

                # 【2026-10-07 删除】原"基于最优化矿物含量的判断（核心逻辑）"：
                #   原代码：if vcarbonate > 0.5: → limestone/dolomite
                #           elif vquartz > 0.5: → sandstone
                #   这是**实质单条件判断**，且是误判的主要穿透路径：
                #     · 高密度段必然算出高 vcarbonate（见上方说明）
                #     · vcarbonate = vcalcite + vdolomite + vanhydrite，
                #       把**硬石膏也算进碳酸盐**，物理上错误
                #     · 原代码 6309-6322 的 if/else 两支返回值完全相同
                #       （都是 'limestone' / 都是 'dolomite'），是死代码残留，
                #       说明 PE 分支逻辑早已失效却仍在维护
                #   现在碳酸盐定性只由 _carb_hits（中子为核心）决定，
                #   vcarbonate/vquartz/vclay 在高密度段仅作诊断输出，不参与定性。
                
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
            
            # 然后执行常规岩性分类
            data['LITHOLOGY'] = data.apply(classify_lithology, axis=1)
            
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
def _step_of(md, default=0.25):
    """由深度数组估算采样间隔（ft/m），用于把点数换算成厚度。

    取相邻差值的中位数；深度无效时返回默认值。
    注意：不能用 `diffs < p99` 过滤 —— 采样完全等间隔时 p99 就等于间隔本身，
    会把所有点都排掉（曾经踩过这个坑）。
    """
    d = np.asarray(md, dtype=float)
    if d.size < 2:
        return default
    diffs = np.abs(np.diff(d))
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    return float(np.median(diffs)) if diffs.size else default

def detect_well_profile_type(data, well_name='Unknown',
                             carbonate_cnl_max=12.0,
                             sandstone_gr_max=100.0):
    """井级剖面类型预判（砂泥岩 / 碳酸盐岩 / 混合）。

    为什么需要这一步
    ----------------
    逐点岩性识别容易被**局部异常**带跑：BET-1 实测在 6460-8935 ft
    出现 70 多个"灰岩"碎段（ρ2.47-2.73、Δt66-107、GR 86-142、PE 3.5-4.8），
    但这些段的参数**明显不是碳酸盐**（中子 11-34、声波 66-107 都不在灰岩
    的 CNL<10 / Δt45-80 范围）。根源是用"PE>3.5"这种**单条判据**判碳酸盐，
    而泥岩/粉砂岩含黏土 PE 本来就能到 4-5。

    而本井 6460-8935 ft 的**整体**特征极其一致，是典型的砂泥岩剖面：
        密度 2.47-2.60（<2.65，达不到灰岩下限）
        伽马 82-264（高低起伏明显 → 砂泥互层）
        电阻中低值
        声波 66-108
    专家意见：**"凭伽马就很好判断砂泥岩"** —— 伽马高且起伏大 = 泥质含量变化
    = 砂泥岩剖面；碳酸盐岩伽马极低（<40）且平直。

    判定逻辑（与逐点识别同一思想：多判据 + 统计量）
    ----------------------------------------------
    对全井（可排除套管段）统计：
        · GR 中位数与起伏度（IQR）
        · CNL 中位数（碳酸盐 <12，砂泥岩 >18）
        · DEN 中位数（碳酸盐 >2.65，砂泥岩 <2.62）
        · 低伽马(<40)与高伽马(>120)所占比例 —— 碳酸盐岩应以低伽马为主，
          砂泥岩应为中高伽马且起伏大
    综合打分，输出剖面类型，供岩性识别器做**井级约束**：
    砂泥岩剖面下，逐点判碳酸盐必须拿出足够的多判据证据。

    返回 (profile_type, info)
    """
    def pick(*names):
        for nm in names:
            if nm in data.columns:
                return pd.to_numeric(data[nm], errors='coerce')
        return pd.Series(np.nan, index=data.index)

    gr = pick('GR', 'GRX', 'GR_XMAC')
    den = pick('RHOB', 'DEN', 'ZDEN')
    cnl = pick('NPHI', 'CNL', 'CNCF')

    def _kb_enrich(_info, _ptype):
        """知识库联动【2026-10-15】：查询地区岩性知识交叉验证剖面判定。
        用户质疑"知识库没用"——巴西蒸发岩-碳酸盐岩序列知识在
        BuiltInKnowledge(brazil_evaporite_sequence)里，此前从未参与
        剖面判定。此处把KB命中记入info['kb_hits']；若KB含巴西碳酸盐
        知识而本井判成砂泥岩，打冲突告警提示人工复核。"""
        # source_file 守卫【2026-10-15】：合成/自检数据无源文件时跳过KB
        # 查询（BuiltInKnowledge 索引构建约8秒/次，自检多场景调用会拖慢
        # --selftest；生产数据经 DataLoader 均有 source_file 不受影响）
        _src = None
        try:
            _src = data.attrs.get('source_file')
        except Exception:
            _src = None
        if not _src:
            logger.debug(f"[{well_name}] 知识库联动跳过: 数据无 source_file"
                         f"（合成/自检数据）")
            return _info
        try:
            import logKnow as _lkw
            _kb = _lkw.WellLogKnowledgeBase(auto_scan=False)
            _hits = _kb.search('巴西 碳酸盐岩 硬石膏 蒸发岩 地层序列 剖面',
                               top_n=3)
            _names = [h.get('title', '?') for h in (_hits or [])]
            if _names:
                _info['kb_hits'] = _names
                logger.info(f"[{well_name}] 知识库联动: 命中知识条目 {_names}")
                if (_ptype == 'sand_shale'
                        and any('brazil' in str(n).lower() or '巴西' in str(n)
                                for n in _names)):
                    logger.warning(
                        f"[{well_name}] 知识库冲突: KB含巴西碳酸盐岩/蒸发岩知识"
                        f"但本井判定为砂泥岩剖面，建议人工复核剖面类型")
        except Exception as _e:   # 知识库不可用不阻断主流程
            logger.debug(f"[{well_name}] 知识库联动跳过: {_e}")
        return _info

    # ---- 0. 元素测井矿物含量（VOL_*）第一优先判据【2026-10-15】----
    # 用户：元素测井处理的矿物含量没有对判断起大作用。LAS 交付的
    # VOL_CALCITE/DOLOM/ANHY/ILLITE/BASALT 是矿物含量最权威证据——
    # 碳酸盐矿物合计中位>=0.5 直接判碳酸盐岩剖面（3-SPS-111D 实测
    # calcite 0.63+dolom 0.16=0.84；而 GR P50=90 的"绝对伽马"统计
    # 曾把它带偏成 mixed → 按砂泥岩规则全判错）。VOL 证据也天然规避
    # "绝对伽马阈值不通用"问题（泥质灰岩 GR 70-120 与砂泥岩重叠）。
    def _vol_series(*names):
        for nm in names:
            if nm in data.columns:
                s = pd.to_numeric(data[nm], errors='coerce')
                return s.where((s > -900) & (s <= 2.0))   # 剔缺测标记与野值
        return None

    _cb_tot = None
    for _vc in ('VOL_CALCITE', 'VOL_DOLOM', 'VOL_ANHY', 'VOL_BASALT'):
        _s = _vol_series(_vc)
        if _s is not None:
            _cb_tot = _s if _cb_tot is None else _cb_tot.add(_s, fill_value=0)
    _ill = _vol_series('VOL_ILLITE')
    if _cb_tot is not None and _cb_tot.notna().sum() >= 50:
        _cb_med = float(_cb_tot.clip(-0.5, 2.0).median())
        _ill_med = (float(_ill.median())
                    if _ill is not None and _ill.notna().sum() >= 50 else 0.0)
        if _cb_med >= 0.50:
            _info = {'profile_type': 'carbonate',
                     'vol_carb_med': _cb_med, 'vol_illite_med': _ill_med,
                     'summary': ('碳酸盐岩剖面（元素测井矿物含量主控: 碳酸盐矿物合计'
                                 '中位%.0f%%、泥质%.0f%%——VOL_*交付成果直接定性)'
                                 % (_cb_med * 100, _ill_med * 100))}
            logger.info(f"[{well_name}] 井级剖面预判: {_info['summary']}")
            _kb_enrich(_info, 'carbonate')
            return 'carbonate', _info
        if _ill_med >= 0.60 and _cb_med < 0.25:
            _info = {'profile_type': 'sand_shale',
                     'vol_carb_med': _cb_med, 'vol_illite_med': _ill_med,
                     'summary': ('砂泥岩剖面（元素测井矿物含量: 泥质中位%.0f%%、'
                                 '碳酸盐%.0f%%）' % (_ill_med * 100, _cb_med * 100))}
            logger.info(f"[{well_name}] 井级剖面预判: {_info['summary']}")
            _kb_enrich(_info, 'sand_shale')
            return 'sand_shale', _info
        # 矿物曲线存在但特征不突出 → 继续走统计打分（证据留待 info 补充）

    valid = gr.notna() & den.notna() & cnl.notna()
    if valid.sum() < 50:
        return 'mixed', {'summary': '有效点不足，未做剖面预判'}

    g, d, c = gr[valid], den[valid], cnl[valid]
    info = {
        'gr_p50': float(g.median()), 'gr_p25': float(g.quantile(.25)),
        'gr_p75': float(g.quantile(.75)),
        'den_p50': float(d.median()), 'cnl_p50': float(c.median()),
        'gr_low_frac': float((g < 40).mean()),    # 低伽马（碳酸盐特征）
        'gr_high_frac': float((g > 120).mean()),  # 高伽马（泥质）
        'gr_iqr': float(g.quantile(.75) - g.quantile(.25)),
        'n_valid': int(valid.sum()),
    }
    info['gr_fluct'] = info['gr_iqr'] / max(info['gr_p50'], 1.0)

    # ---- 多判据打分 ----
    ss_score = 0.0        # 砂泥岩得分
    cb_score = 0.0        # 碳酸盐岩得分

    # 1) 伽马中位数：砂泥岩中高伽马，碳酸盐极低伽马
    if info['gr_p50'] > 120:
        ss_score += 2.0
    elif info['gr_p50'] > 100:
        ss_score += 1.5
    elif info['gr_p50'] > 70:
        ss_score += 0.4   # 【2026-10-15降权】灰岩含泥段GR 70-120与砂泥岩重叠，
                          # 绝对伽马不作强判据（2026-10-08全局规则），3-SPS-111D
                          # GR P50=90曾因此被带偏成mixed
    if info['gr_p50'] < 45:
        cb_score += 2.0
    elif info['gr_p50'] < 70:
        cb_score += 1.0

    # 2) 伽马起伏（专家强调：凭伽马起伏判砂泥岩）
    if info['gr_fluct'] > 0.35:
        ss_score += 2.0
    elif info['gr_fluct'] > 0.22:
        ss_score += 1.2
    if info['gr_low_frac'] > 0.25:
        cb_score += 1.5
    if info['gr_high_frac'] > 0.35:
        ss_score += 1.5

    # 3) 中位数（碳酸盐几乎不含氢，中子低）
    if info['cnl_p50'] > carbonate_cnl_max + 6:
        ss_score += 2.0
    elif info['cnl_p50'] > carbonate_cnl_max:
        ss_score += 1.0
    else:
        cb_score += 2.0

    # 4) 密度中位数
    if info['den_p50'] < 2.62:
        ss_score += 1.5
    elif info['den_p50'] < 2.68:
        ss_score += 0.8
    else:
        cb_score += 1.5

    # 4.5) PE光电吸收截面指数【2026-10-15新增】——矿物铁证：
    # 方解石5.08、白云石3.14、硬石膏5.05（碳酸盐岩>3.8），
    # 石英砂岩1.81、泥岩~3.4边缘值。3-SPS-111D裸眼段PE P50=5.16
    # ≈方解石，是灰岩的最强单曲线证据（GR/密度/中子均受孔隙与
    # 泥质干扰，PE不受孔隙度影响）。有VOL_*早返回时不经此处。
    _pe = pick('PE', 'PEF')
    _pe_v = _pe[valid & (_pe > -900)]
    if _pe_v.notna().sum() >= 50:
        _pe_p50 = float(_pe_v.median())
        info['pe_p50'] = _pe_p50
        if _pe_p50 > 3.8:
            cb_score += 1.5
        elif _pe_p50 < 2.6:
            ss_score += 1.0

    if cb_score > ss_score + 1.0:
        ptype = 'carbonate'
    elif ss_score > cb_score + 1.0:
        ptype = 'sand_shale'
    else:
        ptype = 'mixed'

    info['ss_score'] = ss_score
    info['cb_score'] = cb_score
    info['profile_type'] = ptype
    cn = {'sand_shale': '砂泥岩', 'carbonate': '碳酸盐岩', 'mixed': '混合'}
    info['summary'] = (
        '%s剖面（砂泥岩%.1f : 碳酸盐%.1f）；GR中位%.0f/IQR%.0f(起伏%.0f%%)、'
        'CNL中位%.1f、ρ中位%.2f、低伽马(<40)占%.0f%%、高伽马(>120)占%.0f%%'
        % (cn[ptype], ss_score, cb_score, info['gr_p50'], info['gr_iqr'],
           info['gr_fluct'] * 100, info['cnl_p50'], info['den_p50'],
           info['gr_low_frac'] * 100, info['gr_high_frac'] * 100))
    logger.info(f"[{well_name}] 井级剖面预判: {info['summary']}")
    _kb_enrich(info, ptype)
    return ptype, info

def parse_casing_from_mudlog(mudlog_path, well_name='Unknown'):
    """从录井 PDF 的 CASING DATA 表解析套管鞋深度（权威来源）。

    背景（2026-10-07）
    ------------------
    BET-1 的 LAS 头段**没有套管字段**（无 CDF/CADT/CSIZ），
    套管信息只在录井 PDF 的 "CASING DATA" 表里（图形布局，文本提取需按坐标）。
    实测该表记录：
        17-1/2"  0-118 ftMD      26"
        12-1/4"  118-2640 ftMD   12
        9-5/8"   2640-6450 ftMD  8-1/2"（Shoe 6441 ft）
    其中 9-5/8" 的 shoe = **6441 ft**，与曲线推断的套管段 6344-6447 ft 吻合。

    为什么重要
    ----------
    录井的套管鞋深度是**工程记录**，比曲线反演可靠得多。曲线检测（PE/ρ/CNL/
    浅阻多判据）作为没有录井数据时的兜底，两者互为校验：
    录井优先，曲线检测兜底。

    返回 [(顶深, 底深, 套管尺寸, 鞋深), ...]，解析失败返回 []
    """
    import re
    try:
        import pdfplumber
    except Exception:
        return []
    if not mudlog_path or not os.path.exists(str(mudlog_path)):
        return []

    # 【重要】pdfminer/pdfplumber 内部用标准 logging 输出大量 DEBUG 日志
    # （每个 PDF 操作符一条）。若本程序的 logging 级别是 DEBUG 且日志文件
    # 被其他进程占用（Windows 文件锁），RotatingFileHandler 会反复报
    # PermissionError 并递归触发，产生 GB 级错误输出、拖垮解释流程。
    # 因此解析录井前把相关 logger 提到 WARNING，并在结束后恢复。
    _restore = {}
    for _lg in ('pdfminer', 'pdfplumber', 'pdfminer.pdfinterp',
                'pdfminer.pdfpage', 'pdfminer.converter', 'pdfminer.layout',
                'pdfminer.psparser', 'pdfminer.pdfdocument', 'pdfminer.utils'):
        _lg_obj = logging.getLogger(_lg)
        _restore[_lg] = _lg_obj.level
        _lg_obj.setLevel(logging.WARNING)

    out = []
    # 形如 "12-1/4" / "9-5/8" 的尺寸，以及后续的顶/底深
    pat = re.compile(r'(\d{1,2})-(\d)/(\d)\s*"')
    try:
        with pdfplumber.open(mudlog_path) as pdf:
            if not pdf.pages:
                return []
            # CASING DATA 通常在首页；逐页找，避免漏检
            for page in pdf.pages[:3]:
                words = page.extract_words(use_text_flow=False)
                if not words:
                    continue
                texts = [(w['text'], w['x0'], w['top']) for w in words]
                for i, (t, x, y) in enumerate(texts):
                    m = pat.fullmatch(t.strip())
                    if not m:
                        continue
                    size = '%s-%s/%s"' % (m.group(1), m.group(2), m.group(3))
                    # 取同一行的后续文本（向右），找 top/bottom 数值
                    row = [(xx, tt) for tt, xx, yy in texts
                           if abs(yy - y) < 8 and xx > x]
                    row.sort()
                    nums = []
                    for xx, tt in row:
                        for tok in re.findall(r'\d+(?:\.\d+)?', tt):
                            try:
                                nums.append(float(tok))
                            except ValueError:
                                pass
                    if len(nums) >= 2:
                        top_d, bot_d = nums[0], nums[1]
                        out.append((top_d, bot_d, size, bot_d))
                    elif len(nums) == 1:
                        out.append((0.0, nums[0], size, nums[0]))
        if out:
            out.sort(key=lambda x: x[0])
            logger.info("[%s] 从录井解析到 %d 条套管记录: %s",
                        well_name, len(out),
                        '; '.join('%s: %.0f-%.0fft(鞋%.0f)'
                                  % (s, a, b, sh) for a, b, s, sh in out[:6]))
        return out
    except Exception as e:
        logger.warning("[%s] 录井套管解析失败: %s", well_name, e)
        return []
    finally:
        for _lg, _lv in _restore.items():
            logging.getLogger(_lg).setLevel(_lv)

def apply_mudlog_casing(data, casing_records, min_len_ft=5.0):
    """把录井套管记录应用到数据上，生成套管掩码。

    参数
    ----
    data          : 测井 DataFrame（需含 MD/DEPT）
    casing_records: parse_casing_from_mudlog() 的结果

    返回 (mask, info)
    """
    if not casing_records or 'MD' not in data.columns:
        return None, {'summary': '无录井套管记录'}
    md = pd.to_numeric(data['MD'], errors='coerce').values
    mask = np.zeros(len(data), dtype=bool)
    used = []
    for top_d, bot_d, size, shoe in casing_records:
        # 套管下深（鞋深）以上全部是套管内
        sel = (md >= top_d) & (md <= bot_d)
        if not sel.any():
            continue
        seg_len = bot_d - top_d
        if seg_len < min_len_ft:
            continue
        mask |= sel
        used.append((top_d, bot_d, size, shoe))
    if not used:
        return None, {'summary': '录井套管记录与深度范围无交集'}
    info = {
        'casing_mask': pd.Series(mask, index=data.index),
        'casing_ratio': float(mask.mean()),
        'segments': [(a, b) for a, b, _s, _sh in used],
        'records': used,
        'summary': '录井套管%d层：%s；占全井%.1f%%'
                   % (len(used),
                      ', '.join('%s %.0f-%.0fft(鞋%.0f)' % (s, a, b, sh)
                                for a, b, s, sh in used[:5]),
                      mask.mean() * 100),
    }
    logger.info("[套管-录井] %s", info['summary'])
    return pd.Series(mask, index=data.index), info

def export_las_with_casing(data, las_path, casing_info=None, well_name='Unknown',
                           depth_unit='ft', null_value=-9999.25,
                           units_map=None):
    """导出解释成果 LAS，**并在头段写入套管信息**（LAS 2.0 规范）。

    背景（2026-10-07）
    ------------------
    SLAM 输出的 LAS 头段没有套管字段（实测 BET-1 的 ~WELL 段只有
    VERS/WRAP/STRT/STOP/STEP/NULL/WELL/FLD/DATE/MUDDEN/MUDRES/LOC/
    CATENAME/AREA 共 15 项，无 CSIZ/CDF/CADT）。
    后果：后续解释只能靠曲线反演猜"哪段是套管"，虽有兜底但不如工程记录可靠。

    本函数在 ~PARAMETER 段补齐：
        CSIZ —— 当前套管尺寸（in）
        CDF  —— 套管下入深度（套管鞋深）
        CADT —— 套管上返深度
        BS   —— 钻头尺寸
        CSGSRC —— 套管信息来源（LAS header / log response inference）
    多层套管时用 CSIZ2/CDF2/CADT2 … 依次编号。

    实现说明
    --------
    **不使用 lasio 写出**。实测 lasio 0.32 在设置 ft 单位后写 LAS 会抛
    `KeyError: "STRT not in ['STRT:1', 'STOP:1', ..., 'STRT:2', 'STOP:2']"`
    （单位换算产生重复助记符），且 `las.well.STRT = 6307.0` 会写出 nan。
    因此这里直接按 LAS 2.0 文本格式写出，格式完全可控。

    返回输出路径；失败返回 None
    """
    try:
        if data is None or len(data) == 0:
            return None
        md_col = 'MD' if 'MD' in data.columns else (
            'DEPT' if 'DEPT' in data.columns else None)
        if md_col is None:
            logger.warning('数据缺 MD/DEPT 列，无法导出 LAS')
            return None

        du = 'ft' if str(depth_unit).lower().startswith('f') else 'm'
        md = pd.to_numeric(data[md_col], errors='coerce')
        step = md.diff().median()
        step_v = float(step) if pd.notna(step) and step > 0 else (
            0.25 if du == 'ft' else 0.1)

        default_units = {
            'BIT': 'in', 'CALX': 'in', 'CALY': 'in', 'CAL': 'in',
            'CNCF': 'PU', 'CNC': 'PU', 'NPHI': 'v/v',
            'DTC': 'us/ft', 'DT': 'us/ft', 'GR': 'GAPI', 'GR_XMAC': 'GAPI',
            'PE': 'b/e', 'PERM': 'mD', 'POR': '%', 'RD': 'OHMM',
            'RMSL': 'OHMM', 'RS': 'OHMM', 'SW': '%', 'VSH': 'V/V',
            'WTBHQS': 'DEGF', 'ZDEN': 'G/CC', 'RHOB': 'G/CC', 'DEN': 'G/CC',
            'SP': 'MV',
        }
        if units_map:
            default_units.update(units_map)

        raw_keys = ['BIT', 'CALX', 'CALY', 'CAL', 'CNCF', 'CNC', 'NPHI', 'DTC',
                    'DT', 'GR', 'GR_XMAC', 'PE', 'PERM', 'POR', 'RD', 'RMSL',
                    'RS', 'SW', 'VSH', 'WTBHQS', 'ZDEN', 'RHOB', 'DEN', 'SP']
        interp_keys = ['LITHOLOGY', 'LITHOLOGY_MC', 'FACIES', 'INTERPRETATION',
                       'INTERPRETATION_SCORE', 'PHI', 'So', 'Sw', 'IS_CASING',
                       'IS_COAL', 'IS_CARB_SHALE']
        curves = [c for c in raw_keys + interp_keys
                  if c in data.columns and c != md_col]
        if not curves:
            logger.warning('无可导出的曲线列')
            return None

        ci = casing_info or {}
        las_records = ci.get('las_records') or []
        segs = ci.get('segments') or []

        # ---------------- 组装头段 ----------------
        well_items = [
            ('STRT', '%.4f' % float(md.min()), du, 'START DEPTH'),
            ('STOP', '%.4f' % float(md.max()), du, 'STOP DEPTH'),
            ('STEP', '%.6f' % step_v, du, 'STEP'),
            ('NULL', '%.2f' % null_value, '', 'NULL VALUE'),
            ('COMP', 'CNPC', '', 'COMPANY'),
            ('WELL', str(well_name), '', 'WELL'),
            ('FLD', 'Jabung', '', 'FIELD'),
            ('LOC', 'Indonesia', '', 'LOCATION'),
            ('PROV', 'Jabung Tengah', '', 'PROVINCE'),
            ('DATE', '', '', 'DATE'),
        ]
        # ============ 套管与钻具（关键补充）============
        param_items = []
        if las_records:
            for idx, (top, bot, size) in enumerate(las_records, start=1):
                k_s = 'CSIZ' if idx == 1 else 'CSIZ%d' % idx
                k_f = 'CDF' if idx == 1 else 'CDF%d' % idx
                k_t = 'CADT' if idx == 1 else 'CADT%d' % idx
                if idx == 1:
                    param_items.append((k_s, str(size), 'in', 'CASING SIZE'))
                param_items.append((k_f, '%.4f' % float(top), du,
                                    'CASING DEPTH FROM'))
                param_items.append((k_t, '%.4f' % float(bot), du,
                                    'CASING DEPTH TO'))
        elif segs:
            # 无工程记录时用曲线反演结果补写，并明确标注来源
            a, b = max(segs, key=lambda x: x[1])
            param_items += [
                ('CSIZ', 'UNKNOWN', 'in', 'CASING SIZE'),
                ('CDF', '%.4f' % float(a), du, 'CASING DEPTH FROM'),
                ('CADT', '%.4f' % float(b), du, 'CASING DEPTH TO'),
                ('CMT1', 'Casing interval inferred from log response '
                         '(PE/rho/CNL/shallow-resistivity); '
                         'no CSIZ/CDF/CADT in source LAS', '', 'COMMENT'),
            ]
        if 'BIT' in data.columns:
            try:
                _bit = pd.to_numeric(data['BIT'], errors='coerce').dropna()
                if len(_bit):
                    param_items.append(('BS', '%.4f' % float(_bit.median()),
                                        'in', 'BIT SIZE'))
            except Exception:
                pass
        param_items.append((
            'CSGSRC', 'LAS header' if las_records
            else ('log response inference' if segs else 'none'),
            '', 'CASING INFO SOURCE'))
        param_items.append((
            'CMT', 'Interpreted log by logInt; '
                   'casing header CSIZ/CDF/CADT populated', '', 'COMMENT'))

        # ---------------- 写文件 ----------------
        lines = []
        lines.append('~VERSION INFORMATION')
        lines.append(' VERS.                2.0   : CWLS LOG ASCII STANDARD'
                     '-VERSION 2.0')
        lines.append(' WRAP.                NO    : ONE LINE PER DEPTH STEP')
        lines.append('~WELL INFORMATION BLOCK')
        lines.append('#MNEM.UNIT          DATA       DESCRIPTION')
        lines.append('#---------         ------     ---------------')
        for mn, val, un, de in well_items:
            lines.append(' %-6s%-14s %-10s : %s' % (mn + '.', un, val, de))
        lines.append('~PARAMETER INFORMATION')
        lines.append('#MNEM.UNIT          DATA       DESCRIPTION')
        lines.append('#---------         ------     ---------------')
        for mn, val, un, de in param_items:
            lines.append(' %-6s%-14s %-10s : %s' % (mn + '.', un, val, de))
        lines.append('~CURVE INFORMATION')
        lines.append('#MNEM.UNIT          API CODE   DESCRIPTION')
        lines.append('#---------         ------     ---------------')
        for c in curves:
            lines.append(' %-16s%-12s : ' % (c + '.', default_units.get(c, '')))
        lines.append('~A  ' + ' '.join(['%-16s' % md_col] + curves))

        # ---------------- 写数据 ----------------
        cols = [md] + [pd.to_numeric(data[c], errors='coerce') for c in curves]
        mat = pd.concat(cols, axis=1)
        mat = mat.replace([np.inf, -np.inf], np.nan)
        for c in mat.columns:
            mat[c] = mat[c].where(mat[c] != null_value, np.nan)
        for i in range(len(mat)):
            vals = []
            first = True
            for c in mat.columns:
                v = mat[c].iloc[i]
                if pd.isna(v):
                    s = str(null_value)
                else:
                    s = '%.4f' % float(v) if isinstance(v, (int, float)) \
                        else str(v)
                # 第一列不补空格，其余列右对齐到 12 字符
                vals.append(s if first else s.rjust(12))
                first = False
            lines.append(' ' + ' '.join(vals))

        with open(las_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines))
            f.write('\n')
        logger.info('带套管头的 LAS 已写出: %s（%d 曲线、%d 行、套管%d段）',
                    las_path, len(curves), len(mat), len(segs))
        return str(las_path)
    except Exception as e:
        logger.warning('导出带套管头的 LAS 失败: %s', e)
        return None

def _merge_casing_segs(segs, gap_ft=10.0):
    """合并相邻/重叠的套管段（间隔小于 gap_ft 视为同一套管程序）。"""
    if not segs:
        return []
    ss = sorted((float(a), float(b)) for a, b in segs if b >= a)
    out = [list(ss[0])]
    for a, b in ss[1:]:
        if a - out[-1][1] <= gap_ft:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]

def _casing_shoe_from_masterlog(data, well_name='Unknown'):
    """从 masterlog/录井 PDF 井身结构取套管/尾管鞋深记录（用户定案权威来源）。

    背景（2026-10-15，3-SPS-111D）
    ------------------------------
    LAS 头段多层套管记录（CS1-4/CBL1-4/CBD1-4）相互混杂，单一 CDF/CADT 只是
    "当前钻进井段"的套管，不代表套管程序。用户明确：**以 masterlog 图上
    well architecture 为准**——最后一层 10-3/4" 尾管下深 6425m，即 6425m
    以上全是套管（与裸眼测井曲线对应）。PDF 文本层该行词元为
        "LINER | 10 | 3/4\": | 6425 | m"
    尺寸与深度分属不同词元，需按行聚类后配对；只认含 CASING/LINER/CSG
    标注的行（12-1/4" 等钻头井段行无此标注，自动跳过——防止把井眼TD
    当套管鞋）。BET-1 类"CASING DATA"表格行无逐行 CASING 字样，解析为空
    时自然回退头段/曲线反演，不影响老井。

    返回 (鞋深, 尺寸文本, [(鞋深, 尺寸文本), ...])；解析失败返回 (None, None, [])
    """
    import re
    try:
        import pdfplumber
    except Exception:
        return None, None, []
    src = None
    try:
        src = data.attrs.get('source_file')
    except Exception:
        src = None
    if not src:
        return None, None, []
    well_dir = os.path.dirname(str(src))
    try:
        pdf_path = find_mudlog_pdf(well_dir)
    except Exception:
        pdf_path = None
    if not pdf_path:
        return None, None, []

    # pdfplumber/pdfminer DEBUG 日志抑制（同 parse_casing_from_mudlog，防日志膨胀）
    _restore = {}
    for _lg in ('pdfminer', 'pdfplumber', 'pdfminer.pdfinterp', 'pdfminer.pdfpage',
                'pdfminer.converter', 'pdfminer.layout', 'pdfminer.psparser',
                'pdfminer.pdfdocument', 'pdfminer.utils'):
        _lg_obj = logging.getLogger(_lg)
        _restore[_lg] = _lg_obj.level
        _lg_obj.setLevel(logging.WARNING)

    # 尺寸词元："10-3/4"" / "10 3/4":" / "13.625"" / "22":"
    size_pat = re.compile(r'^(?:(\d{1,2})[-\s](\d)/(\d)|(\d{1,2}(?:\.\d+)?))["”]?:?$')
    frac_pat = re.compile(r'^(\d)/(\d)["”]?:?$')
    num_pat = re.compile(r'^(\d{2,5}(?:\.\d+)?)(?:\s*(?:m|ft))?$', re.I)
    out = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:3]:
                words = page.extract_words(use_text_flow=False)
                if not words:
                    continue
                # 按 top 坐标聚类成行（容差9pt：masterlog实测CASING标注与
                # 尺寸/深度词元间最大8pt差，6pt会把同行拆散漏配），行内按 x 排序
                toks = sorted([(float(w['top']), float(w['x0']), str(w['text']))
                               for w in words])
                rows = []
                for y, x, t in toks:
                    if rows and abs(y - rows[-1][0][0]) <= 9:
                        rows[-1].append((y, x, t))
                    else:
                        rows.append([(y, x, t)])
                for row in rows:
                    row.sort(key=lambda z: z[1])
                    labels = [t for _y, _x, t in row]
                    rowtext = ' '.join(labels).upper()
                    if not re.search(r'\b(CASING|LINER|CSG)\b', rowtext):
                        continue
                    i = 0
                    while i < len(labels):
                        m = size_pat.match(labels[i].strip())
                        if m:
                            if m.group(1):
                                size_txt = '%s-%s/%s' % (m.group(1), m.group(2), m.group(3))
                            else:
                                size_txt = m.group(4)
                                # 整数+分数分属两个词元（"10" + "3/4\":"）
                                if i + 1 < len(labels):
                                    fm = frac_pat.match(labels[i + 1].strip())
                                    if fm:
                                        size_txt = '%s-%s/%s' % (size_txt, fm.group(1), fm.group(2))
                                        i += 1
                            for j in range(i + 1, len(labels)):
                                nm = num_pat.match(labels[j].strip())
                                if nm:
                                    out.append((float(nm.group(1)), size_txt))
                                    break
                        i += 1
        if out:
            out.sort()
            logger.info('[%s] masterlog(%s) 井身结构套管/尾管记录: %s',
                        well_name, os.path.basename(str(pdf_path)),
                        ', '.join('%s"@%.0f' % (s, d) for d, s in out[:8]))
            return out[-1][0], out[-1][1], out
        return None, None, []
    except Exception as e:
        logger.warning('[%s] masterlog 套管解析失败: %s', well_name, e)
        return None, None, []
    finally:
        for _lg, _lv in _restore.items():
            logging.getLogger(_lg).setLevel(_lv)

def _casing_layers_from_header(data):
    """解析 LAS 头段编号套管记录，返回全部层位 [(鞋深, 尺寸), ...]（升序）。

    【三重校验之一：LAS 头段】头段套管数据复杂：多层套管
    （CS1-4/CBL1-4/CBD1-4 各自记录 36"/22"/14"/10.75" 的鞋深），而单一
    CDF/CADT 只是"当前井段"套管（3-SPS-111D 为 2004-6380m），直接采用
    会把套管鞋判短。解析规则：
        1) 编号记录 CS1..CS10（尺寸）+ CBL1..CBL10（测录鞋深，缺则 CBD
           钻工鞋深）→ 全部层位列表（本井 36"@2112、22"@3328、14"@5071.8、
           10.75"@6380）
        2) 无编号记录回退（CS/CSIZ/CDIA + CBL/CBD/CADT）
    注意：人工测量在井下会变形拉伸（~0.1%误差），头段记录可能滞后于
    实际下深 —— 本结果仅作为三重校验之一，不单独定案。
    """
    info = None
    try:
        if 'casing_header' in data.attrs:
            info = data.attrs.get('casing_header')
        if not info or not any(str(k).startswith(('CS', 'CBL', 'CBD'))
                               for k in (info.keys() if hasattr(info, 'keys') else [])):
            las_info = data.attrs.get('las_info') or {}
            # 【2026-10-15】优先取全量原始参数 params_raw（键=原始助记符大写，
            # 含 CS1..10/CBL1..10 编号套管记录）；白名单 parameter 键已规范化
            # （current_casing_size 等），编号记录从未进入
            params = None
            if isinstance(las_info, dict):
                params = las_info.get('params_raw')
                if not params:
                    params = las_info.get('parameter', {})
            if params:
                # 编号记录(CS1..CBL10)只存在于完整 parameter 区，优先用全量
                info = params if params else info
        if not info:
            return []

        def _num(v):
            try:
                f = float(str(v).split()[0])
                # -999.25 等缺测标记不是有效鞋深（全局规则）
                if not np.isfinite(f) or f <= -999:
                    return None
                return f
            except (TypeError, ValueError, IndexError):
                return None

        # ---- 1. 编号套管记录 CS1..CS10 + CBL/CBD1..10 ----
        layers = []
        for _i in range(1, 11):
            _size = _num(info.get('CS%d' % _i))
            if _size is None:
                continue
            _shoe = _num(info.get('CBL%d' % _i))
            if _shoe is None:
                _shoe = _num(info.get('CBD%d' % _i))
            if _shoe is not None:
                layers.append((_shoe, _size))
        layers.sort()

        # ---- 2. 无编号记录回退（CS/CSIZ/CDIA + CBL/CBD/CADT）----
        if not layers:
            _size = _num(info.get('CS')) or _num(info.get('CSIZ')) or _num(info.get('CDIA'))
            _shoe = _num(info.get('CBL')) or _num(info.get('CBD')) or _num(info.get('CADT'))
            if _size is not None and _shoe is not None:
                layers.append((_shoe, _size))

        return layers
    except Exception:
        return []

def _triple_verify_casing_shoe(data, well_name, curve_shoe=None):
    """套管鞋三重交叉验证【2026-10-15 用户定案】。

    用户：套管判断要三重逻辑 —— LAS头段、masterlog、测井曲线三个来源
    要**对应**，不能只看一个；套管是人工测量数据，在井下会变形拉伸
    （~0.1%误差），单一来源可能遗漏/误差/误判。

    三个来源
    --------
    1. masterlog 井身结构图（工程记录，用户定案权威）
    2. LAS 头段编号套管记录（工程记录，可能滞后/只记当层）
    3. 测井曲线反演鞋深（detect_casing_interval 多判据段的纯响应底界，
       水泥返高/人工井底延伸**之前**，与工程记录比对才公平）

    仲裁规则（容差 tol = max(0.1%×鞋深, 5.0)，0.1% 即用户给出的人工
    测量变形拉伸误差）
    - 两源一致（|差|≤tol）→ 采纳一致对中权威级更高者
      （masterlog > 头段 > 曲线），第三源偏差记日志
    - 三源互不一致 → 采纳最权威来源，**打 ⚠ 冲突告警建议人工复核**
    - 单源可用 → 直接采纳（行为与旧版一致）

    返回 (shoe, size_txt, info)；全部来源缺失返回 (None, None, {})。
    info 含 has_engineering（是否有工程记录参与）——仅曲线单源时
    调用方不应生成工程掩码（保持旧版曲线反演行为）。
    """
    info = {}
    hdr_layers = _casing_layers_from_header(data)
    ml_shoe, ml_size, _ml_layers = _casing_shoe_from_masterlog(data, well_name)

    def _fmt_size(s):
        if s is None:
            return None
        try:
            return '%g"' % float(s)
        except (TypeError, ValueError):
            # 分数尺寸文本（masterlog "10-3/4"）保留原样
            return '%s"' % s

    cands = []   # [(来源名, shoe, size_txt, 权威级)] 权威级小 = 更权威
    if ml_shoe is not None and np.isfinite(ml_shoe):
        cands.append(('masterlog', float(ml_shoe), _fmt_size(ml_size), 0))
    if hdr_layers:
        _d, _s = hdr_layers[-1]
        if np.isfinite(_d):
            cands.append(('LAS头段', float(_d), _fmt_size(_s), 1))
    if curve_shoe is not None and np.isfinite(curve_shoe):
        cands.append(('曲线反演', float(curve_shoe), None, 2))
    if not cands:
        return None, None, {}
    info['sources'] = [(c[0], c[1]) for c in cands]
    info['has_engineering'] = any(c[3] in (0, 1) for c in cands)

    if len(cands) == 1:
        n, d, s, _p = cands[0]
        info.update({'adopted': (n, d), 'agreement': 'single',
                     'reason': '仅%s可用' % n})
        logger.info('[%s] ★套管三重校验: %s=%.0f → 采纳（%s）',
                    well_name, n, d, info['reason'])
        return d, s, info

    d_ref = max(c[1] for c in cands)
    tol = max(0.001 * d_ref, 5.0)
    info['tol'] = tol

    def _agree(a, b):
        return abs(a[1] - b[1]) <= tol

    # 两两比对找一致对
    pairs = []
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if _agree(cands[i], cands[j]):
                pairs.append((cands[i], cands[j]))
    if pairs:
        grp = [c for p in pairs for c in p]
        n, d, s, _p = min(grp, key=lambda c: c[3])   # 一致对中权威级最高
        _dis = [c for c in cands if abs(c[1] - d) > tol]
        _names = '、'.join(sorted({c[0] for p in pairs for c in p}))
        info.update({'adopted': (n, d), 'agreement': 'majority',
                     'reason': '%s一致(容差%.0f内)' % (_names, tol)})
        if _dis:
            info['reason'] += ('；%s偏差 %.0f-%.0f（已按一致源修正）'
                               % ('、'.join(c[0] for c in _dis),
                                  min(abs(c[1] - d) for c in _dis),
                                  max(abs(c[1] - d) for c in _dis)))
        logger.info('[%s] ★套管三重校验: %s（容差%.0f）→ 采纳%s 鞋深%.0f'
                    '（%s）', well_name,
                    ' / '.join('%s=%.0f' % (c[0], c[1]) for c in cands),
                    tol, n, d, info['reason'])
        return d, s, info

    # 三源互不一致 → 按权威序采纳 + 冲突告警（人工复核）
    cands.sort(key=lambda c: c[3])
    n, d, s, _p = cands[0]
    info.update({'adopted': (n, d), 'agreement': 'conflict',
                 'reason': '三源互不一致(容差%.0f)，按权威序采纳%s' % (tol, n)})
    logger.warning('[%s] ⚠套管三重校验冲突: %s（容差%.0f）→ 采纳%s 鞋深%.0f，'
                   '建议人工复核井身结构资料', well_name,
                   ' / '.join('%s=%.0f' % (c[0], c[1]) for c in cands),
                   tol, n, d)
    return d, s, info

def detect_casing_interval(data, well_name='Unknown',
                            pe_thr=8.0, den_thr=2.30, cnl_thr=35.0,
                            rt_thr=0.60, min_len_ft=2.0,
                            use_las_header=True, depth_unit=None):
    """检测套管井段（casing interval）—— 多判据一致性判定。

    三个来源，互相印证（三重校验，2026-10-15 用户定案）
    ------------------------------------------------
    1. **masterlog 井身结构图** —— 工程记录，用户定案权威。
    2. **LAS 头段编号套管记录**（CS1-10/CBL/CBD）—— 工程记录，可能滞后
       或只记到当层（3-SPS-111D 头段 6380m vs 实际 6425m）。
    3. **测井响应多判据反演** —— PE/ρ/CNL/浅阻 的套管响应组合（兜底）。
    三源经 _triple_verify_casing_shoe 仲裁鞋深（两源一致采纳权威高者、
    三源冲突打告警人工复核），再与曲线掩码取**并集**
    （水泥返高/固结段延伸保留）。

    背景（2026-10-07 BET-1 实测发现）
    --------------------------------
    BET-1 的 6307-6460 ft 段被识别成"灰岩"，专家指出**实际是套管内**：
        声波  54-95（偏低，且因套管不干净而起伏）
        密度  1.42-2.12（是**泥浆密度**，不是岩石密度）
        中子  38-54（是**泥浆含氢**，不是岩石孔隙度）
        PE    15.0-17.1（**铁的信号**，只有钢套管能到这个值）
        伽马  58-90（被**手套管**压制，裸岩应为 130-160）
        电阻  RMSL 0.10-0.15 / RS 0.12-0.13（**近乎平头**）
    这套组合是**教科书式的套管内响应**，任何岩石都不可能有 PE>15。

    为什么原来的 `check_hole_quality` 检不出来
    ----------------------------------------
    它只按**井径比**判扩径。而套管内井径正常
    （实测 CALX 8.77 / BIT 8.5 = 1.03，完全"合格"），
    所以井径质量检查对套管段完全无感 —— 必须引入**测井响应**判据。

    判据（多判据一致性，与岩性识别同一思想）
    ----------------------------------------
    单条判据都不足以判定套管：
        PE>8      泥浆/水泥也能到（较少见，但存在）
        ρ<2.30    泥浆密度 1.2-1.9，气侵泥浆可到 0.8
        CNL>35    淡水/泥浆含氢高
        浅阻极低   conductive 泥浆
    但**三条以上同时成立**（PE 极高 + ρ 极低 + CNL 极高）在裸岩段
    是不可能的：岩石 PE 极少超过 6，ρ 极少低于 2.2。

    **电阻率必须用浅电阻率（RMSL/RS/MSFL），不能用深电阻率（RD/LLD）**。
    BET-1 实测：套管段 RMSL 中位 **0.12**、裸岩段 **3.44**（差 28 倍）；
    而深电阻率 RD 在套管段中位 2.15，与裸岩段 8.52 区分度远不如浅电阻率
    —— 泥浆侵入浅层，深电阻率测的是冲洗带以外，受泥浆影响小。
    取三者的**最小值**作为判据值，任一条浅阻极低即命中。

    伽马**不作为判据**：手套管会压制伽马，但压制程度取决于泥浆屏蔽性，
    不好定量；用上面几条更稳健。

    返回 (mask, info)
    """
    def pick(*names):
        for nm in names:
            if nm in data.columns:
                return pd.to_numeric(data[nm], errors='coerce')
        return pd.Series(np.nan, index=data.index)

    pe = pick('PE', 'PEF')
    den = pick('RHOB', 'DEN', 'ZDEN')
    cnl = pick('NPHI', 'CNL', 'CNCF')
    gr = pick('GR', 'GRX', 'GR_XMAC')
    # 井径与钻头尺寸 —— 用于识别套管鞋以下的水泥返高污染带
    cal = pick('CALX', 'CAL', 'CALY', 'CALS')
    bit = pick('BIT', 'BIT_LAS', 'DIA')
    # 声波 —— 用于识别套管鞋以下的人工井底水泥固结段（2026-10-08 BET-1）
    dt = pick('DT', 'AC', 'DTC', 'DTCO')

    n = len(data)
    if n == 0:
        return pd.Series(False, index=data.index), {'summary': '无数据'}

    # 浅电阻率：取所有浅电阻率列的**最小值**（任一条被泥浆侵入即极低）
    shallow = [pd.to_numeric(data[c], errors='coerce')
               for c in ('RMSL', 'RS', 'MSFL', 'M2RX', 'AT90')
               if c in data.columns]
    shallow = [s for s in shallow if s.notna().any()]
    if shallow:
        rt = pd.concat(shallow, axis=1).min(axis=1)
    else:
        rt = pd.Series(np.nan, index=data.index)

    # 各判据（缺列则该判据不参与，valid_count 相应减少）
    c1 = pe > pe_thr          # PE 极高 → 钢
    c2 = den < den_thr        # 密度极低 → 泥浆
    c3 = cnl > cnl_thr        # 中子极高 → 泥浆含氢
    c4 = rt < rt_thr          # 浅电阻率极低 → 导电泥浆
    # 【套管底部过渡带】水泥返高段：PE 从 15 降到 5-7、密度 1.9-2.3、
    # 浅阻仍很低。PE 不够高但"密度低 + 浅阻极低"仍不是岩石。
    # BET-1 实测 6446-6456 ft 就是这一段（原判据把它漏掉了）。
    #
    # 【重要】PE 门槛必须 > 7，否则会把**煤层**误判成套管 ——
    # 实测 BET-1 的 7466-7468 ft（煤）PE 4.2-5.1、ρ2.16-2.28、CNCF 41.7、
    # RMSL 0.85，与水泥返高段几乎一样。真正的区分是：
    #   真套管      PE 中位 15.5、GR 78.6（被手套管压低）
    #   煤层        PE 中位  4.7、GR 128（正常伽马）
    # 因此这里要求 PE>7.0，并**把伽马作为区分判据**（手套管压制伽马，
    # 岩石伽马正常）。
    c5 = (pe > 7.0) & (den < den_thr) & (rt < 1.20)
    c6 = (gr < 110.0) & (pe > 7.0) & (den < den_thr)   # 伽马被压低 → 套管
    crit = [c1, c2, c3, c4, c5, c6]
    names = ['PE>%.0f' % pe_thr, 'ρ<%.2f' % den_thr,
             'CNL>%.0f' % cnl_thr, '浅阻<%.2f' % rt_thr,
             '水泥返高(PE>7&ρ低&浅阻<1.2)', '伽马受压(GR<110&PE>7&ρ低)']

    # 有效判据数（列存在的才计入）
    valid = [c for c, col_ok in zip(
        crit, [pe.notna().any(), den.notna().any(),
               cnl.notna().any(), rt.notna().any(),
               pe.notna().any(), gr.notna().any()]) if col_ok]
    if len(valid) < 3:
        logger.info(f"[{well_name}] 有效曲线不足，无法检测套管")
        return pd.Series(False, index=data.index), {
            'summary': '有效曲线不足，未做套管检测',
            'valid_criteria': len(valid),
        }

    # **多判据一致性**：至少 3 条同时成立（而非任一条）。
    # 阈值 0.6 而非 0.75：水泥返高段的 cnl 可能已降到 35 以下、浅阻已回升，
    # 靠 c2(密度低) + c5/c6 仍能命中。
    hit = pd.DataFrame({n_: c.fillna(False) for n_, c in zip(names, valid)}).sum(axis=1)
    need = max(3, int(len(valid) * 0.55))
    mask = hit >= need

    # 最小长度过滤：孤立点不算套管段（套管段是连续的）
    if mask.any() and 'MD' in data.columns:
        mv = mask.values
        md = pd.to_numeric(data['MD'], errors='coerce').values
        nz = np.flatnonzero(mv)
        keep = np.zeros(n, dtype=bool)
        start = nz[0]
        for k in range(1, len(nz) + 1):
            contiguous = (k < len(nz)) and (nz[k] - nz[k - 1] == 1)
            if not contiguous:
                end = nz[k - 1]
                # 段长用采样点数×采样间隔估算，避免 md 端点 NaN 造成误判
                seg_len = (end - start) * _step_of(md)
                if seg_len >= min_len_ft:
                    keep[start:end + 1] = True
                if k < len(nz):
                    start = nz[k]
        mask = pd.Series(keep, index=data.index)

    # 曲线反演鞋深（三重校验用）【2026-10-15】：取水泥返高/人工井底延伸
    # **之前**的纯曲线套管响应底界 —— 水泥带会人为抬高底界十几米，
    # 不剔除会与工程记录假性"冲突"
    _curve_shoe = None
    if mask.any() and 'MD' in data.columns:
        _mdi0 = pd.to_numeric(data['MD'], errors='coerce').values
        _mv0 = np.asarray(mask.values, dtype=bool)
        if _mv0.any():
            _curve_shoe = float(np.nanmax(_mdi0[_mv0]))

    # ========== 套管鞋以下水泥带延伸（扩径返高带 + 声波固结段）==========
    # 【2026-10-15 修复】原两段判据在"三重校验并集"之前执行且被 mask.any()
    # 短路——曲线反演 0 命中的井（如 3-SPS-111D 套管内 CNL 为负、浅阻不低）
    # 会整体跳过水泥带延伸，工程记录鞋深之下的水泥返高/固结段漏排 →
    # 被误判成泥岩/砂岩并产生假 DRY 解释。
    # 现封装为本函数，移到三重校验并集**之后**重跑（见下方调用处）：
    # 以并集掩码底界（含工程记录鞋深）为起点，对曲线反演是否命中不再敏感。
    #
    # 距离常数（影响带 60 / 基线窗 [30,230] / 延伸上限 30）按**数据深度
    # 单位**解释——BET-1(英尺井) 验证为 60ft 口径、3-SPS-111D(米井) 验证
    # 为 60m 口径（水泥返高带 6425-6454m 恰好覆盖），故不做换算；
    # 仅日志单位标签随 depth_unit 显示。点数上限按采样步长自适应。
    def _extend_cement_below(mask_in, _unit_tag):
        """从掩码底界向下延伸水泥返高带（扩径）与人工井底固结段（声波）。"""
        mask_cur = mask_in
        parts = []
        # ---- 扩径带水泥返高：套管鞋以下 60(数据单位) 内 扩径比>1.25 ----
        if cal.notna().any() and bit.notna().any() and 'MD' in data.columns:
            _bitv = np.where(np.asarray(bit) > 0.1, np.asarray(bit), np.nan)
            with np.errstate(divide='ignore', invalid='ignore'):
                _calr = np.asarray(cal, dtype=float) / _bitv
            _mv = np.asarray(mask_cur.values, dtype=bool)
            _mdi = pd.to_numeric(data['MD'], errors='coerce').values
            _nz = np.flatnonzero(_mv)
            if len(_nz):
                _shoe = np.nanmax(_mdi[_nz])
                # 固井影响带：套管鞋以下 60(数据单位) 内
                _band = (~np.isnan(_mdi)) & (_mdi >= _shoe) & \
                        (_mdi <= _shoe + 60.0)
                _mud = _band & (_calr > 1.25)
                if _mud.any():
                    mask_cur = pd.Series(_mv | _mud, index=data.index)
                    _n_mud = int(_mud.sum())
                    _z = _mdi[_mud]
                    parts.append('水泥返高段 %.0f-%.0f%s(%d点,扩径比>1.25)'
                                 % (np.nanmin(_z), np.nanmax(_z), _unit_tag, _n_mud))
                    logger.info('[%s] 套管鞋以下 %.0f%s 内识别出水泥返高段 %d 点'
                                '（扩径比>1.25），已一并排除岩性识别',
                                well_name, _shoe, _unit_tag, _n_mud)
        # ---- 人工井底水泥固结段：声波>裸眼基线P10×1.12 向下延伸 ----
        if dt.notna().any() and 'MD' in data.columns and mask_cur.any():
            # copy()：上游 Series 可能持有只读底层缓冲，直接写 .values 会崩
            _mv = np.asarray(mask_cur.values, dtype=bool).copy()
            _mdi = pd.to_numeric(data['MD'], errors='coerce').values
            _dtv = pd.to_numeric(dt, errors='coerce').values
            _nz = np.flatnonzero(_mv)
            if len(_nz):
                _bot_i = int(_nz[-1])                    # 掩码最后一行的行号
                # 裸眼基线：掩码底界以下 30~230(数据单位) 窗口内的声波低分位（P10）
                _base_lo = _mdi[_bot_i] if not np.isnan(_mdi[_bot_i]) else 0.0
                _base_win = _dtv[(_mdi >= _base_lo + 30.0) & (_mdi <= _base_lo + 230.0)]
                _base_win = _base_win[~np.isnan(_base_win)]
                if len(_base_win) >= 20:
                    # 基线取窗口 P10：贴近裸眼基线，避免大段高声波地层抬高阈值
                    _base = float(np.percentile(_base_win, 10))
                    _ext = 0
                    _k = _bot_i + 1
                    # 点数上限按采样步长自适应（公制密采样若沿用60点会过早截断）
                    _ext_cap = max(60, int(30.0 / max(_step_of(_mdi), 1e-9)) + 10)
                    while (_k < n and _ext < _ext_cap
                           and not np.isnan(_mdi[_k])
                           and _mdi[_k] - _mdi[_bot_i] <= 30.0):
                        _v = _dtv[_k]
                        _hit = (not np.isnan(_v)) and _v > _base * 1.12
                        if _hit:
                            _mv[_k] = True
                            _ext += 1
                        elif np.isnan(_v):
                            pass          # 声波缺测的点不终止延伸（与套管段同性质）
                        else:
                            break
                        _k += 1
                    if _ext:
                        mask_cur = pd.Series(_mv, index=data.index)
                        parts.append('人工井底水泥固结段%d点(声波>裸眼基线×1.12)' % _ext)
                        logger.info('[%s] 套管底界 %.0f%s 以下识别出人工井底水泥固结段 '
                                    '%d 点（声波>裸眼基线%.0f×1.12），已一并排除',
                                    well_name, _mdi[_bot_i], _unit_tag, _ext, _base)
        return mask_cur, parts

    ratio = float(mask.mean()) if n else 0.0
    segs = []
    if mask.any() and 'MD' in data.columns:
        # 用原始行位置切分连续段，避免布尔掩码索引错位
        mv = mask.values
        md = pd.to_numeric(data['MD'], errors='coerce').values
        i = 0
        while i < n:
            if not mv[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and mv[j + 1]:
                j += 1
            # 该连续段 [i, j] 已在长度过滤中保留，记入结果
            a, b = md[i], md[j]
            if not (np.isnan(a) or np.isnan(b)) and b >= a:
                segs.append((float(a), float(b)))
            i = j + 1

    # 汇总消息推迟到三重校验并集/整体化之后组装（见下方 parts 最终组装）
    extra_parts = []

    # ========== 套管鞋三重校验（masterlog / LAS头段 / 曲线反演）==========
    # 【2026-10-15 用户定案】三源互相印证：套管是人工测量数据，在井下
    # 会变形拉伸（~0.1%误差），单看一个来源可能遗漏/误差/误判 ——
    # 两源一致才采纳（masterlog > 头段 > 曲线），三源互不一致打 ⚠ 告警
    # 人工复核，仲裁逻辑见 _triple_verify_casing_shoe。采纳鞋深后仍与
    # 曲线掩码取并集（水泥返高/固结段延伸保留）。
    las_recs = []
    las_segs = []
    if use_las_header:
        _tri_shoe, _tri_size, _tri_info = _triple_verify_casing_shoe(
            data, well_name, _curve_shoe)
        if _tri_shoe is not None and _tri_info.get('has_engineering'):
            las_recs = [(0.0, float(_tri_shoe), _tri_size or '')]
        if las_recs and 'MD' in data.columns:
            md_v = pd.to_numeric(data['MD'], errors='coerce').values
            las_mask = np.zeros(len(data), dtype=bool)
            for _top, _bot, _size in las_recs:
                las_mask |= ((md_v >= _top) & (md_v <= _bot))
            if las_mask.any():
                las_ratio = float(las_mask.mean())
                las_segs = [(float(t), float(b)) for t, b, _s in las_recs]
                # 交叉校验：与曲线反演结果比对
                if segs:
                    iou = float((mask & las_mask).sum()) / max(
                        float((mask | las_mask).sum()), 1.0)
                    if iou > 0.5:
                        extra_parts.append('曲线反演与工程记录吻合(重叠%.0f%%)'
                                           % (iou * 100))
                    else:
                        extra_parts.append('⚠曲线反演与工程采纳鞋深不一致(重叠%.0f%%)'
                                           '，按三重校验结果合并' % (iou * 100))
                else:
                    extra_parts.append('套管来自三重校验工程记录（曲线无明显套管响应）')
                # 取并集：工程记录 + 曲线反演
                mask = mask | las_mask
                ratio = float(mask.mean())
                segs = _merge_casing_segs(segs + las_segs)

    # ========== 水泥返高带/固结段延伸（三重校验并集之后重跑）==========
    # 【2026-10-15 修复】原扩径带/声波两段判据位于并集之前且被 mask.any()
    # 短路——曲线反演 0 命中的井（如 3-SPS-111D 套管内 CNL 为负、浅阻不低）
    # 会整体跳过水泥带延伸，工程记录鞋深之下的水泥返高段（6425-6454m）
    # 漏排 → 被误判成泥岩/砂岩并产生假 DRY 解释。现以并集后掩码（含工程
    # 记录鞋深）底界为起点重跑，即使曲线反演 0 命中也能捕捉。
    _du_s = str(depth_unit or '').strip().lower()
    _unit_tag = 'm' if _du_s.startswith('m') else 'ft'
    mask, _cement_parts = _extend_cement_below(mask, _unit_tag)
    extra_parts.extend(_cement_parts)
    if _cement_parts and 'MD' in data.columns:
        # 掩码已向下延伸 → 从掩码重建 segs（行位置切分，逻辑同上方初建）
        ratio = float(mask.mean())
        _mv_c = np.asarray(mask.values, dtype=bool)
        _mdi_c = pd.to_numeric(data['MD'], errors='coerce').values
        _segs2 = []
        _i = 0
        while _i < n:
            if not _mv_c[_i]:
                _i += 1
                continue
            _j = _i
            while _j + 1 < n and _mv_c[_j + 1]:
                _j += 1
            _a, _b = _mdi_c[_i], _mdi_c[_j]
            if not (np.isnan(_a) or np.isnan(_b)) and _b >= _a:
                _segs2.append((float(_a), float(_b)))
            _i = _j + 1
        segs = _merge_casing_segs(_segs2)

    # ========== 套管段整体化：套管顶以上至数据起点均并入套管段（2026-10-08）==========
    # 本程序只解释裸眼段。套管自地面一直下到套管鞋，凡深度浅于套管底界
    # （含水泥固结段延伸）的测点都在套管内。曲线反演可能漏标套管顶以上的
    # 井段（如 BET-1 数据起点6307ft、检测套管顶6344ft，6307-6344ft 实为
    # 套管内）→ 统一并入：不作岩性/沉积相/油气解释，可视化不绘制。
    if mask.any() and 'MD' in data.columns:
        _md_all = pd.to_numeric(data['MD'], errors='coerce').values
        _mb = np.asarray(mask, dtype=bool)
        _bot = float(np.nanmax(_md_all[_mb]))
        _ext = (_md_all <= _bot) & ~_mb
        if _ext.any():
            _top_new = float(np.nanmin(_md_all[_ext | _mb]))
            extra_parts.append('套管顶以上扩展%d点(自%.0fft)并入套管段——程序仅解释裸眼段'
                               % (int(_ext.sum()), _top_new))
            mask = _mb | _ext
            ratio = float(mask.mean())
            segs = _merge_casing_segs(segs + [(_top_new, _bot)])

    # 【2026-10-15】汇总在并集/整体化完成后组装 —— 套管段列表与占全井
    # 比例反映三重校验合并后的最终掩码（旧版提前组装导致显示0.0%）
    parts = []
    if segs:
        parts.append('套管段%d个：' % len(segs) +
                     ', '.join('%.0f-%.0f' % (a, b) for a, b in segs[:6]) +
                     ('…' if len(segs) > 6 else ''))
    parts.append('占全井%.1f%%' % (ratio * 100))
    if segs:
        parts.append('实测PE %.1f-%.1f、ρ %.2f-%.2f、CNL %.0f-%.0f、RT %.2f-%.2f'
                     % (pe[mask].min(), pe[mask].max(),
                        den[mask].min(), den[mask].max(),
                        cnl[mask].min(), cnl[mask].max(),
                        rt[mask].min(), rt[mask].max()))
    parts.extend(extra_parts)

    info = {
        'casing_mask': pd.Series(mask, index=data.index),
        'casing_ratio': ratio,
        'segments': segs,
        'criteria': names,
        'need': need,
        'las_records': las_recs,
        'las_segments': las_segs,
        'summary': '；'.join(parts) if parts else '未检测到套管',
    }
    if mask.any():
        logger.info(f"[{well_name}] 检测到{info['summary']} —— "
                    f"该段测井响应为套管/泥浆，岩性识别必须排除")
    else:
        logger.info(f"[{well_name}] 未检测到套管段")
    return mask, info

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

            # 创建LITHOLOGY列
            if 'LITHOLOGY' not in data.columns:
                data['LITHOLOGY'] = 'Unknown'

            # 【一处一功能 2026-10-08】多判据识别器（must/core/deny）是岩性判定
            # 的唯一来源。若 LITHOLOGY_MC 已存在，本方法不再写 LITHOLOGY 列
            # （只保留矿物含量/Sw/So/PHI 计算），防止旧单条件分类覆盖多判据结果
            # —— 实测 BET-1：多判据判出 sandstone 1239/碳质泥岩 364/煤 94，
            # 旧链路覆盖后 LITHOLOGY 变成 shale 8854，6460-6487ft 明显砂岩被
            # 泥岩覆盖、煤层碳质泥岩全被抹掉。
            _mc_exists = 'LITHOLOGY_MC' in data.columns

            # 获取有效曲线足够的索引
            valid_indices = data[data['VALID_CURVES_COUNT'] >= 3].index

            # 【2026-10-20 用户定案】元素泥质定源（岩性识别之前）：
            # VSH ← 元素测井泥质 VOL_ILLITE（缺测点 KTH 回归外推，火成岩段
            # 除外）。蒸发岩-碳酸盐岩剖面 GR 基线抬升，GR/交付泥质严重高估
            # （111D 灰岩段 0.49 vs 元素 0.07），先定准泥质再识别岩性。
            try:
                data = apply_elemental_vsh(data)
            except Exception as _e_ev:
                logger.warning("元素泥质定源失败（保持原泥质链路）: %s", _e_ev)

            if len(valid_indices) > 0:
                # 只对有效曲线足够的井段进行岩性分析
                valid_data = data.loc[valid_indices].copy()
                valid_data = self.mineral_analyzer.run_mineral_analysis(valid_data)

                # 将结果合并回原始数据
                # 使用索引对齐，避免长度不匹配问题
                _merge_cols = ['QUARTZ', 'CALCITE', 'DOLOMITE', 'ANHYDRITE', 'CLAY', 'LITHOLOGY',
                               'LITHOLOGY_EN', 'Sw', 'So', 'PHI']
                if _mc_exists:
                    _merge_cols = [c for c in _merge_cols if c != 'LITHOLOGY']
                for col in _merge_cols:
                    if col in valid_data.columns:
                        # 使用索引对齐赋值，只更新有对应索引的值
                        data.loc[valid_data.index, col] = valid_data[col].values

            # 有效曲线不足的井段保持默认值
            if not _mc_exists:
                data.loc[data['VALID_CURVES_COUNT'] < 3, 'LITHOLOGY'] = 'Unknown'

            # 【2026-10-20 用户定案】元素含量仲裁岩性：修正"无证据泥岩"
            # （识别器兜底产物）与高泥质漏判，判据=元素矿物体积
            try:
                data, _n_arb = arbitrate_lithology_by_elements(data)
            except Exception as _e_arb:
                logger.warning("元素仲裁岩性失败（保持识别器结果）: %s", _e_arb)

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
    
    # ========== 煤层/碳质泥岩沉积相（2026-10-07 加入，同属沼泽相） ==========
    # 地质依据：**煤与碳质泥岩都是沼泽（泥炭沼泽）环境的产物**。
    #   沼泽是植物遗体在缺氧、静止水体中分解不完全的地带，有机质得以保存：
    #     · 有机质高度富集 → 煤层        → swamp_peatro（沼泽泥炭相）
    #     · 有机质中富集、混入泥质 → 碳质泥岩 → swamp_carbonaceous（沼泽碳质泥岩相）
    #   二者是**同一沉积环境、不同有机质富集程度**，因此归入同一相组。
    #   BET-1 实测：7 个煤层段全部与碳质泥岩共生（煤层±30ft 内 152 点），
    #   垂向序列为"泥炭→碳质泥岩→泥炭"，佐证二者同属沼泽相。
    # 这两类既不是砂也不是泥，若不先识别出来，沉积相会被误落到
    # 三角洲前缘（underwater_distributary_channel）或湖相（deep_lake_mud）。
    # 判据使用岩性识别器输出的 IS_COAL / IS_CARB_SHALE 标记，
    # 而非再次用单条件阈值重复判断，避免两处逻辑不一致。
    def _special_facies_flags(self, data):
        """基于 LITHOLOGY 列（岩性识别输出）生成煤/碳质泥岩沉积相标记。

        返回 DataFrame，含：
          IS_COAL       : 煤层（沼泽泥炭相的物源基础）
          IS_CARB_SHALE : 碳质泥岩（含碳泥质沉积）
          GEOPHYS_COAL  : 地球物理特征标志（极低密度+高声波+高中子+低伽马）
          GEOPHYS_CARB  : 地球物理特征标志（低密度+高声波+中高子+中高伽马）

        若 LITHOLOGY 列不存在，则退化为多判据曲线判定（而非单条件）：
        煤需要同时满足 低密度+高声波+高中子+低伽马；碳质泥岩需要
        中高伽马+密度低于泥岩+中子偏高+声波偏高。
        """
        flags = pd.DataFrame(index=data.index)
        lith = None
        # 优先使用多判据岩性识别结果（LITHOLOGY_MC）——
        # 它用"必要项+排除项+M-of-K一致性项"判定，比单条件可靠；
        # 其次才用常规 LITHOLOGY 列。
        if 'LITHOLOGY_MC' in data.columns:
            lith = data['LITHOLOGY_MC'].astype(str).str.lower()
        elif 'LITHOLOGY' in data.columns:
            lith = data['LITHOLOGY'].astype(str).str.lower()

        if lith is not None:
            flags['IS_COAL'] = (lith == 'coal')
            flags['IS_CARB_SHALE'] = lith.isin(
                ['carbonaceous_shale', 'carbonaceous mudstone', '碳质泥岩'])
        else:
            flags['IS_COAL'] = False
            flags['IS_CARB_SHALE'] = False

        # ---- 地球物理特征标志（多判据，不依赖岩性列）----
        # 列名需覆盖 LAS 原始名：ZDEN(密度)/CNCF(中子)/DTC(声波)/PE/RD
        def _pick(*names):
            for nm in names:
                if nm in data.columns:
                    return pd.to_numeric(data[nm], errors='coerce')
            return pd.Series(np.nan, index=data.index)

        gr = _pick('GR', 'GRX', 'GR_LAS', 'GR_XMAC')
        den = _pick('RHOB', 'DEN', 'ZDEN', 'DEN_LAS')
        cnl = _pick('NPHI', 'CNL', 'CNCF', 'CNL_LAS')
        dt = _pick('DT', 'DTC', 'DTCO', 'AC')
        pe = _pick('PE', 'PEF')

        # 煤的地球物理指纹：极低密度 + 高声波 + 高中子 + 低伽马（4项同时）
        flags['GEOPHYS_COAL'] = (
            (den < 1.85) & (dt > 105) & (cnl > 30) & (gr < 110))
        # 碳质泥岩指纹：密度低于泥岩 + 声波偏高 + 中子偏高 + 中高伽马
        flags['GEOPHYS_CARB'] = (
            (den < 2.42) & (den > 1.90) & (dt > 88) &
            (cnl > 24) & (gr > 105))
        # 指纹成立但岩性列缺失时兜底
        if lith is None:
            flags['IS_COAL'] = flags['GEOPHYS_COAL']
            flags['IS_CARB_SHALE'] = flags['GEOPHYS_CARB']
        else:
            flags['IS_COAL'] = flags['IS_COAL'] | flags['GEOPHYS_COAL']
            flags['IS_CARB_SHALE'] = flags['IS_CARB_SHALE'] | flags['GEOPHYS_CARB']
        return flags

    def classify_facies(self, data):
        """沉积相分类（使用机器学习模型结合曲线形态分析，有效曲线不足3条的井段跳过）"""
        try:
            # 煤/碳质泥岩标记（多判据，见 _special_facies_flags 说明）
            _flags = self._special_facies_flags(data)
            data['IS_COAL'] = _flags['IS_COAL']
            data['IS_CARB_SHALE'] = _flags['IS_CARB_SHALE']
            data['GEOPHYS_COAL'] = _flags['GEOPHYS_COAL']
            data['GEOPHYS_CARB'] = _flags['GEOPHYS_CARB']
            # 检查是否有VALID_CURVES_COUNT列
            if 'VALID_CURVES_COUNT' not in data.columns:
                data = self._count_valid_curves_per_segment(data)
            
            # 创建FACIES列
            if 'FACIES' not in data.columns:
                data['FACIES'] = 'Unknown'

            # 【2026-10-27 R26 用户定案】火成岩段不做沉积相分析：火山岩相
            # 不是沉积相，硬套沉积相分类无意义（要做也是火山岩相分析）。
            # 火成岩行直接标'火山岩相'并排除出沉积相分类。
            _ig = pd.Series(False, index=data.index)
            if 'LITHOLOGY' in data.columns:
                _ls_ig = data['LITHOLOGY'].astype(str).str.lower()
                for _kw in ('basalt', 'andesite', 'rhyolite', 'dacite',
                            'tuff', 'igneous', 'volcanic', 'granite',
                            'diorite', '玄武', '安山', '流纹', '凝灰',
                            '火成', '火山'):
                    _ig = _ig | _ls_ig.str.contains(_kw, na=False)
            if _ig.any():
                data.iloc[np.where(_ig.values)[0],
                          data.columns.get_loc('FACIES')] = '火山岩相'
                logger.info('火成岩段 %d 点跳过沉积相分析（标火山岩相）',
                            int(_ig.sum()))

            # 获取有效曲线足够的索引（排除火成岩段）
            valid_indices = data[(data['VALID_CURVES_COUNT'] >= 3)
                                 & (~_ig)].index
            
            if len(valid_indices) == 0:
                logger.info("有效曲线不足3条的井段，跳过沉积相分类")
                return data
            
            # 只对有效曲线足够的井段进行沉积相分析
            valid_data = data.loc[valid_indices].copy()
            
            # 确保必要的列存在
            if 'GR' not in valid_data.columns:
                valid_data['GR'] = 0
            if 'RT' not in valid_data.columns:
                _rt_src = select_resistivity_column(valid_data)
                if _rt_src:
                    valid_data['RT'] = valid_data[_rt_src]
                elif 'R90' in valid_data.columns:
                    valid_data['RT'] = valid_data['R90']
                else:
                    valid_data['RT'] = 1
            
            # 计算特征
            features = self._calculate_facies_features(valid_data)

            # 把煤/碳质泥岩标记并入 features —— classify_facies_row 只拿到
            # features 的行，标记必须在这里带进去，否则读不到会漏判
            for _c in ('IS_COAL', 'IS_CARB_SHALE', 'GEOPHYS_COAL', 'GEOPHYS_CARB'):
                if _c in valid_data.columns:
                    features[_c] = valid_data[_c].values
            
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

                # ========== 煤层与碳质泥岩：优先判别（2026-10-07 加入/修订）==========
                # 二者既不是砂也不是泥，必须在三角洲/湖相判定之前拦截，
                # 否则煤层会被误判成湖相泥、碳质泥岩会被误判成前三角洲。
                #
                # 【地质依据：均为沼泽相】（用户指出"碳质泥岩也是沼泽相"）
                #   沼泽（泥炭沼泽）是植物遗体在**缺氧、静止的水体**中分解
                #   不完全的地带。有机质不能被完全氧化，混入泥质沉积，
                #   就形成碳质泥岩；有机质高度富集则形成煤层。
                #   因此**碳质泥岩与煤是同一沉积环境（沼泽）下的产物**，
                #   差别只是有机质富集程度：
                #     · 煤        swamp_peatro      沼泽泥炭相（有机质极富集）
                #     · 碳质泥岩  swamp_carbonaceous 沼泽碳质泥岩相（有机质中富集）
                #   BET-1 实测佐证：7 个煤层段（7066-7070、7638-7644、7712-7715、
                #   7736-7739、7911-7913、8036-8037、8459-8462 ft）**全部**
                #   与碳质泥岩共生（煤层±30 ft 内共 152 点碳质泥岩），
                #   其中 7712-7742 ft 煤层直接夹在 51 点碳质泥岩之间 ——
                #   典型的"泥炭沼泽→碳质泥岩→泥炭"垂向序列。
                if bool(row.get('IS_COAL', False)) or bool(row.get('GEOPHYS_COAL', False)):
                    return 'swamp_peatro'
                if bool(row.get('IS_CARB_SHALE', False)) or bool(row.get('GEOPHYS_CARB', False)):
                    return 'swamp_carbonaceous'

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
                    # 统一用 flood_plain（与上面三角洲平原分支同名），
                    # 原写法 floodplain 会让同一相在图例里裂成两项
                    return 'flood_plain'
                
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
            
            # 有效曲线不足的井段保持默认值
            data.loc[data['VALID_CURVES_COUNT'] < 3, 'FACIES'] = 'Unknown'
            
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
"""
            
            # 查询 Wiki 知识库上下文
            try:
                from logKnow import query_wiki_context  # 2026-10-26 并库: logWiki 已并入 logKnow
                wiki_context = query_wiki_context(well_name)
                if wiki_context:
                    interpretation += f"\n## Wiki 知识库上下文\n\n{wiki_context}\n"
            except Exception as e:
                logger.debug(f"Wiki 查询失败: {e}")
            
            interpretation += """
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
        有效曲线：曲线值 > 0 且 非NaN
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）
        
返回:
            data: 添加了 VALID_CURVES_COUNT 列的DataFrame
        """
        # 候选名必须覆盖 LAS 原始列名，否则统计不到有效曲线。
        # 实测 BET-1（LAS 列名 ZDEN/CNCF/DTC/RD/RMSL/CALX/CALY）在原列表下
        # 只能数出 1 条曲线，导致"有效曲线数量不足"而跳过岩性/沉积相/绘图。
        valid_curves = ['GR', 'GRX', 'GR_LAS', 'RT', 'RT_LAS', 'LLD', 'ILD', 'R90',
                        'RD', 'RS', 'RMSL', 'MSFL', 'LLS',
                        # 【2026-10-21 R18】HAL7506 等老井的阵列电阻率 RAL1-5
                        'RAL1', 'RAL2', 'RAL3', 'RAL4', 'RAL5',
                        'DEN', 'DEN_LAS', 'RHOB', 'ZDEN',
                        'NPHI', 'CNL', 'CNL_LAS', 'CNCF', 'CNC',
                        'DT', 'DTCO', 'DTC', 'AC', 'DTTC', 'DTTST', 'DTTXX',
                        'PE', 'PEF',
                        # 【2026-10-21 R18】井径：RP-13 的井径列名是 CAL_AVERAGE，
                        # 原名单只有 CAL/CALS/CALX/CALY → 井径这条有效曲线数不出来
                        'CAL', 'CALS', 'CALX', 'CALY', 'CALI',
                        'CAL_AVERAGE', 'CAL-AVG', 'CALAVG', 'CAL_MEAN',
                        'SP', 'BIT']

        # 创建有效曲线计数列
        valid_counts = []
        
        for i in range(len(data)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(data), i + window_size // 2)
            
            count = 0
            for curve in valid_curves:
                if curve in data.columns:
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
            # 必须覆盖 LAS 原始列名（ZDEN/CNCF/DTC/RD/RMSL），否则会误判为"曲线不足"
            valid_curves = ['GR', 'GRX', 'RT', 'LLD', 'ILD', 'R90', 'RD', 'RMSL', 'MSFL',
                            'DEN', 'RHOB', 'ZDEN', 'NPHI', 'CNL', 'CNCF',
                            'DT', 'DTCO', 'DTC', 'AC', 'PE', 'PEF']
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

# ============================================================================
# 岩性识别（按矿物特征值 + 曲线响应）
#   放在解释侧（logInt）而非绘图侧：岩性属于解释成果，绘图只负责呈现。
#   与 FaciesAnalyzer 的关系：岩性识别是沉积相判别的**输入** —— 煤与碳质泥岩
#   既不是砂也不是泥，若不先识别出来，沉积相会被误落到三角洲前缘或湖相。
#   用法：rec = LithologyRecognizer(df, depth_unit='ft')
#         df['LITHOLOGY'] = rec.run()
# ============================================================================
# -*- coding: utf-8 -*-
"""岩性识别规则表 —— 按"矿物特征值 + 曲线响应"识别特殊岩性。

设计原则
--------
1. 岩石的**矿物骨架**决定密度(ρb)、声波(Δt)、光电指数(Pe)、
   中子响应(φn) 与自然伽马(GR) 的基线；
2. **流体/有机质**会改写孔隙度类曲线：中子↑、电阻率↓（水）或
   电阻率↑（油气）、声波↑（油/气）、密度↓（气）；
3. 判别用**多个判据打分**，而不是单一门限 —— 单一门限会被局部异常带跑，
   多判据一致性才可靠；
4. 阈值区分**矿物本征值**（ρb、Δt、Pe 这类几乎只由骨架决定）
   与**可被流体改写的响应**（中子、电阻率），后者用相对判据。

每条规则字段
------------
key       : 岩性英文名（与 LITHOLOGY_TO_SYMBOL / LITH_BG_COLORS 对应）
cn        : 中文名
hard      : 硬判据（全部满足才计分），每个判据是 (列候选, 比较符, 阈值)
soft      : 软判据（部分满足即计分），用于打细分
score_min : 进入该岩性所需的最低总分
priority  : 多岩性同时得分时的优先级（越大越优先，用于煤/碳质泥岩压过泥岩）
"""

# 曲线列候选名（按优先级尝试，第一个存在且有效的列被采用）
# 注意 CNL 的候选顺序：CNL_LAS/CNL 在前，NPHI/CNCF 在后。
# LAS 里的原始中子列名是 CNCF（补偿中子），若把 CNCF 映射成 DT 是错的
# （CNCF 是孔隙度 PU，不是声波），会造成中子道缺失而声波道画成中子。
COL_CANDIDATES = {
    'GR':   ['GR_LAS', 'GR', 'GRX', 'GR_XMAC'],
    'DEN':  ['DEN_LAS', 'DEN', 'ZDEN', 'RHOB'],
    'CNL':  ['CNL_LAS', 'CNL', 'CNCF', 'NPHI', 'CNC'],
    'DT':   ['DT', 'DTC', 'DTCO', 'AC'],
    'RT':   ['RT_LAS', 'RT', 'RMSL', 'RD', 'MSFL'],
    'PE':   ['PE', 'PEF'],
    'CAL':  ['CAL_LAS', 'CAL', 'CALX', 'CALY'],
    'BIT':  ['BIT', 'BIT_LAS'],
    # 扩径比 CAL/BIT —— 识别**水泥返高段**（套管鞋以下、固井水泥污染带）
    # 的关键信号。实测 BET-1 6447-6460ft 水泥返高段 CAL/BIT=1.38，
    # 而正常裸岩段中位仅 1.02。扩径段的密度/中子测的是水泥+岩屑，
    # 不能当作岩石响应做岩性判断。
    'CALR': ['CALR', 'CAL_OVER_BIT'],
    'PHI':  ['PHI_LAS', 'PHI', 'POR'],
    'SW':   ['SW_LAS', 'SW'],
}

# 各矿物的理论特征值（用于生成判据与报告说明，不直接参与打分）
MINERAL_PROPS = {
    'coal':        {'rho': '1.2-1.8',  'dt': '100-140', 'cnl': '30-60',
                    'pe': '0.2-1.5',  'gr': '低-中(30-120)', 'rt': '高(煤为绝缘体)'},
    'carbonaceous_shale': {'rho': '1.95-2.42', 'dt': '90-120', 'cnl': '22-38',
                    'pe': '1.8-3.0',  'gr': '中-高(90-190)', 'rt': '中-高'},
    'shale':       {'rho': '2.4-2.8',  'dt': '75-110',  'cnl': '15-35',
                    'pe': '2.5-4.0',  'gr': '高(90-200)', 'rt': '低-中'},
    'sandstone':   {'rho': '2.1-2.6',  'dt': '55-95',   'cnl': '0-25',
                    'pe': '1.5-3.5',  'gr': '低(<75)',  'rt': '高(储层)'},
    'limestone':   {'rho': '2.5-2.85', 'dt': '45-80',   'cnl': '0-8',
                    'pe': '4.5-5.5',  'gr': '极低(<40)', 'rt': '极高'},
    'dolomite':    {'rho': '2.7-3.0',  'dt': '40-75',   'cnl': '0-6',
                    'pe': '3.0-3.5',  'gr': '低(<45)',  'rt': '极高'},
    'halite':      {'rho': '2.0-2.2',  'dt': '45-55',   'cnl': '0-3',
                    'pe': '0.1-0.3',  'gr': '极低(<25)', 'rt': '极高(盐为绝缘体)'},
    'igneous':     {'rho': '2.6-3.1',  'dt': '50-90',   'cnl': '0-5',
                    'pe': '5-10',     'gr': '不定',     'rt': '极高'},
    'pyrite':      {'rho': '4.8-5.2',  'dt': '90-120',  'cnl': '0-10',
                    'pe': '8-12',     'gr': '低(<60)',  'rt': '高'},
}

# ============================================================================
#  多判据一致性识别引擎（2026-10-07 重写）
#  ---------------------------------------------------------------------------
#  【为什么重写】原先的规则表用 hard（全部满足）+ soft（加权计分），
#  但每条规则的 hard 里其实只有 1-2 个"真正的鉴别项"，导致：
#    · 煤 只要 DEN<2.00 且 PE<2.20 且 CNL>24 就判煤 —— 密度是主判据，
#      于是一段高孔隙的泥岩/砂岩（DEN 1.9-2.0）也会被判成煤；
#    · 碳质泥岩 只要 CNL>24 且 DEN<2.38 —— 而 7660 ft 砂岩实测
#      CNL=25.7、DEN=2.27、GR=44（明显低伽马）就被误判成碳质泥岩。
#  根源是"单条件/少条件触发"，而不是阈值没调好。
#
#  【新设计】三条硬约束同时成立才允许定岩性：
#   1) **必要项 (must)**   —— 该岩性物理上不可缺的特征，缺一即否决；
#   2) **一致性项 (core)** —— 至少满足 N 项（M-of-K），单条不决定结论；
#   3) **排除项 (deny)**   —— 出现即否决（用于区分易混岩性）。
#  另外对每条曲线同时使用**绝对判据**与**相对判据**（本井分位数），
#  换井/换仪器标定时相对判据仍然成立。
#
#  【煤 vs 碳质泥岩 —— 用户明确指出的关键差异】
#   曲线      煤                碳质泥岩          判别意义
#   密度 ρ    极低 1.45-1.80    2.00-2.40         骨架孔隙 vs 泥质骨架
#   中子CNL   极高 40-55        中高 24-36        含氢/有机质 vs 泥质水
#   声波 Δt   极高 115-127      中等 88-105       骨架结构 vs 压实泥岩
#   伽马 GR   **低** 86-110     **中高** 105-190  ← 最强判别项
#   光电 Pe   极低 1.2-2.2     中等 2.3-3.2       轻元素 vs 黏土
#  BET-1 实测：煤 7067-7068.5 GR仅 86-92、ρ1.45-1.65、CNL 40-54、Δt 122-127；
#              碳质泥岩 GR 105-190、ρ 2.00-2.40、CNL 24-36、Δt 88-105。
#  7600/7620(GR 109-114, ρ 2.48-2.50, CNL 16-19) 是**泥岩**，密度不够低；
#  7660(GR 44, ρ 2.27, CNL 25.7) 是**砂岩**，伽马太低、中子虽高但密度偏高。
# ============================================================================

# 规则字段：
#   key/cn      : 岩性英文名 / 中文名
#   priority    : 同分时的优先级（越大越优先）
#   score_min   : 加权一致性总分门槛
#   must        : 必要项，全部满足才继续评估（否则直接否决）
#   core        : 一致性项，(列, 比较符, 阈值, 权重)，要求至少满足 core_min 项
#   core_min    : 至少满足多少项一致性判据（M-of-K 机制，杜绝单条件触发）
#   deny        : 排除项，命中即否决。支持 {'all': [...]} 多条件 AND 写法
#   desc        : 判别说明（写入报告供专家复核）

def _fmt_thr(t):
    """阈值格式化：数值保留两位小数；'@KEY?fallback' 自适应引用显示为可读文本。"""
    if isinstance(t, str) and t.startswith('@'):
        body = t[1:].split('?', 1)[0]
        return '%s(自适应)' % body
    try:
        return '%.2f' % t
    except (TypeError, ValueError):
        return str(t)

def _fmt_criteria(items):
    """把判据列表格式化为可读文本（支持 tuple 与 {'all': [...]} 两种写法）。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            cols = it.get('all', [])
            out.append('[' + ' & '.join('%s%s%s' % (c, o, _fmt_thr(t)) for c, o, t in cols) + ']')
        else:
            out.append('%s%s%s' % (it[0], it[1], _fmt_thr(it[2])))
    return '  '.join(out)

LITHOLOGY_RULES = [
    # ================= 煤 =================
    # 必要项：密度极低（<2.00）—— 煤的唯一物理底线
    # 一致性项：至少 4 项满足（低密度/极高声波/极高中子/极低 Pe/低伽马/中高阻）
    #   关键：把 **GR 低** 写进一致性项，把 **DT 高** 写进必要项，
    #         这样"密度低但伽马高"的地层（泥质）不会被判成煤。
    {
        'key': 'coal', 'cn': '煤', 'priority': 100, 'score_min': 6.0,
        'core_min': 4,
        'desc': '煤：ρ 极低(<2.00) 且 Δt 高(>100) 为必要条件（用户指出：'
                '煤不是密度小于1.7就是煤，而是必须明显高声波、高阻、中子）；'
                '再要求"极低密度+高声波+高中子+低 Pe+低伽马"中至少 4 项同时成立。'
                '判别核心是**多参数一致性**：密度低 + 声波高 + 中子高 + 伽马低'
                '同时成立。灰分煤（GR 可达150）用多条件排除项处理，不被误杀',
        'must': [
            ('DEN', '<', 2.00),     # 密度极低：骨架极度多孔
            ('DT',  '>', 100.0),    # 声波显著高：煤疏松、孔隙极发育
        ],
        'core': [
            ('DEN', '<', 1.85, 2.0),   # 极低密度（煤核部）
            ('DEN', '<', 1.70, 1.0),   # 极低密度（更强）
            ('DT',  '>', 115.0, 1.5),  # 高声波
            ('DT',  '>', 105.0, 1.0),  # 中高声波
            ('CNL', '>', 35.0, 1.5),   # 高中子（含氢）
            ('CNL', '>', 28.0, 0.8),   # 中子偏高
            ('PE',  '<', 2.20, 1.5),   # 低光电指数（轻元素为主）
            ('PE',  '<', 1.60, 0.8),   # 极低 Pe
            ('GR',  '<', 110.0, 2.0),  # **低伽马**（与碳质泥岩的最强判别项）
            ('GR',  '<', 95.0, 1.0),   # 更低伽马
            ('RT',  '>', 2.50, 1.0),   # 中等以上电阻率
            ('CAL', '>', 8.60, 0.5),   # 煤段常扩径
        ],
        'deny': [
            # 多条件排除：高伽马**且**密度不够低 → 是泥质层/碳质泥岩，不是煤。
            # 这样既排除高伽马泥岩，又不误杀 GR 140-150 的灰分煤（其 ρ<1.7）。
            {'all': [('GR', '>', 150.0), ('DEN', '>', 1.80)]},
            {'all': [('GR', '>', 135.0), ('DEN', '>', 1.95)]},
            # 密度不够低（必须由必要项把关，这里兜底）
            {'all': [('DEN', '>', 2.05)]},
        ],
    },
    # ================= 碳质泥岩 =================
    # 与煤的区别（用户强调）：密度、中子、声波、伽马全都不同。
    # 必要项：中高伽马（这是与煤/砂岩的分水岭）+ 密度明显低于泥岩
    # 排除项：低伽马(<85)排除砂岩；密度>2.45 排除（那是普通泥岩）
    {
        'key': 'carbonaceous_shale', 'cn': '碳质泥岩', 'priority': 90,
        'score_min': 6.0, 'core_min': 4,
        'desc': '碳质泥岩：中高伽马(>95)为必要条件（用户指出：煤低伽马、'
                '碳质泥岩中高伽马，这是两者最强判别项）；'
                '密度 1.95-2.45（明显低于泥岩 2.50+）、CNL 偏高(>24)、Δt 偏高(>88)、'
                'Pe 2.0-3.2 —— 泥质骨架中富含有机质/碳质。'
                '要求上述特征至少 4 项同时成立，单靠 CNL 高不足以判碳质泥岩。'
                '排除项用多条件语义：低伽马(<85)排除砂岩（7660 ft GR=44 就是砂岩）；'
                '密度>2.42 且中子<26 则归泥岩（7600/7620 ft 实测 ρ2.48-2.50）',
        'must': [
            # 【2026-10-08 自适应】中高伽马（碳质泥岩位于砂泥分界的泥岩侧，
            # 煤为低伽马、砂岩更低）
            ('GR', '>', '@GR_shale_min?95'),
        ],
        'core': [
            ('DEN', '<', 2.45, 2.0),   # 密度低于泥岩
            ('DEN', '>=', 1.95, 1.5),  # 排除煤（煤 ρ<1.95）
            ('DEN', '<', 2.35, 1.0),   # 更低密度
            ('GR',  '>', '@GR_sand_max?115', 2.0),  # 中高伽马（泥质）
            ('GR',  '>', 135.0, 1.0),  # 高伽马
            ('CNL', '>', 24.0, 1.5),   # 中子偏高（有机质+泥质水）
            ('CNL', '>', 28.0, 0.8),   # 更高中子
            ('DT',  '>', 88.0, 1.5),   # 声波偏高
            ('PE',  '>=', 2.00, 1.0),  # Pe 中等（黏土）
            ('PE',  '<', 3.20, 0.8),
        ],
        'deny': [
            # 低伽马 → 砂岩（石英骨架不放伽马）。用多条件语义避免误杀
            # 灰质砂岩：要求伽马确实低。
            {'all': [('GR', '<', 85.0), ('CNL', '>', 20.0)]},
            {'all': [('GR', '<', 75.0)]},
            # 密度太高且中子不高 → 普通泥岩（实测 7600/7620 ft：
            # GR 109-114、ρ 2.48-2.50、CNL 16-19，是泥岩不是碳质泥岩）
            {'all': [('DEN', '>', 2.46)]},
            {'all': [('DEN', '>', 2.42), ('CNL', '<', 26.0)]},
            # 密度太低 → 煤
            {'all': [('DEN', '<', 1.90)]},
            # Pe 太高 → 泥岩/灰质
            {'all': [('PE', '>', 3.60)]},
        ],
    },
    # ---------- 石灰岩：ρ 高、Δt 极低、CNL 极低、Pe 高、GR 极低 ----------
    {
        'key': 'limestone', 'cn': '灰岩', 'priority': 80, 'score_min': 5.0,
        'core_min': 3,
        'desc': '灰岩：**CNL 极低中子为核心判别项**（碳酸盐骨架几乎不含氢，'
                '中子不受泥质干扰；泥岩 CNL16-35、砂岩 10-30 都不会落入）。'
                'ρ>2.62、Δt<85、CNL<12 为必要条件；再要求低 GR/高 RT/ρ 更高 至少 3 项。'
                'PE 只作辅助（权重 0.5）—— 泥岩因含黏土 PE 也可达 4-5，'
                '不能用 PE 单独定性（这是原逻辑把砂泥岩误判成灰岩的主因，'
                'BET-1 实测 6716 ft ρ2.59/PE4.83/GR137 被误判为灰岩）',
        'must': [
            ('DEN', '>', 2.62),
            ('DT',  '<', 85.0),
            ('CNL', '<', 12.0),    # 核心判别项：碳酸盐几乎不含氢
        ],
        'core': [
            ('CNL', '<', 8.0, 2.5),    # 极低中子（碳酸盐的强标志）
            ('PE',  '>', 4.20, 0.5),   # 辅助（权重低：泥岩也会高）
            ('GR',  '<', 55.0, 1.5),
            ('RT',  '>', 3.00, 1.0),
            ('DEN', '>', 2.70, 1.0),
            ('DT',  '<', 72.0, 1.0),
        ],
        'deny': [
            # 中子偏高 → 绝不可能是碳酸盐（泥质/粉砂质）
            {'all': [('CNL', '>', 15.0)]},
            # 伽马偏高 → 是泥岩/砂泥岩，不是灰岩
            {'all': [('GR', '>', 110.0)]},
        ],
    },
    # ---------- 白云岩：比灰岩更重、Δt 更低、Pe 略低 ----------
    {
        'key': 'dolomite', 'cn': '白云岩', 'priority': 82, 'score_min': 5.0,
        'core_min': 3,
        'desc': '白云岩：ρ>2.74、Δt<74、CNL<10 为必要条件；'
                '再要求中 Pe、低 GR、高阻 至少 3 项（同样以中子为核心）',
        'must': [
            ('DEN', '>', 2.74),
            ('DT',  '<', 74.0),
            ('CNL', '<', 10.0),
        ],
        'core': [
            ('CNL', '<', 7.0, 2.5),
            ('PE',  '>', 3.00, 0.8),
            ('GR',  '<', 50.0, 1.5),
            ('RT',  '>', 3.00, 1.0),
            ('DEN', '>', 2.82, 1.0),
        ],
        'deny': [
            {'all': [('CNL', '>', 14.0)]},
            {'all': [('GR', '>', 110.0)]},
        ],
    },
    # ---------- 岩盐：负中子 + 低密度 + 低声波【2026-10-19 用户反馈重写】 ----------
    # 3-SPS-111D 6442-6454m 实测 12m 连续盐岩（ρ2.04-2.15、CNL≈-4.5
    # **负中子**、Δt53-68、GR65-86、RT>500）被旧规则判成砂岩/泥岩。
    # 旧规则三处条件与本井物理实际矛盾，且与程序自身骨架参数表
    # Halite=[2.03, 0.00, 67.0, 4.70]（5612行）自相矛盾：
    #   ① must Δt<62 —— 盐岩骨架声波就是 67us/ft（重结晶盐 55-67），
    #      实测中位 67.1，<62 把整段盐岩挡在必要项门外；
    #   ② core PE<1.20 —— 本井 PE 曲线系统偏高（灰岩段实测也 6.0+，
    #      方解石理论值 5.08），该条件永假，盐岩永远拿不到 core 分；
    #   ③ core GR<40 —— 纯石盐 GR≈0，但泥质盐/钾盐化段 GR 可达 86，
    #      实测中位 78，该条件同样永假。
    # 【Must/Core/Deny 重构】
    #   Must（物理底线，缺一即否）：
    #     · CNL<2 —— 负~零中子是盐岩铁证（无氢+挖掘效应）；一切含氢
    #       响应（泥岩 CNL15-35、砂岩 5-30、灰岩 8-12）均被挡在门外；
    #     · 1.90≤ρ<2.35 —— 低于一切沉积骨架（泥岩2.55/砂岩2.65/灰岩
    #       2.71），同时 ρ≥1.90 排除煤（煤 ρ<1.9 且 Δt>100，由 coal
    #       规则 priority100 优先分流）；
    #     · Δt<75 —— 盐岩声波窗（骨架 67，重结晶盐可至 55；>75 是
    #       疏松层/煤/泥质，绝无盐）。
    #   Core（M-of-K，≥3 项同时成立）：
    #     · CNL<-1（负中子挖掘效应）权重2.0、ρ<2.15（盐核 2.03-2.16）
    #       权重2.0、RT>5（盐高阻）1.5、Δt<70 1.0、ρ≥1.95（盐核下限）
    #       1.0、PE<5 0.5（本井 PE 系统偏高，仅作低权辅助）。
    #     本段实测命中前 5 项共 7.5 分 > 砂岩同段 6.5 分，priority 84
    #     > 砂岩 45，双保险胜出。
    #   Deny（一票否决）：
    #     · CNL>8（含氢）、ρ>2.45（硬石膏/灰岩密度）、Δt>85（疏松/煤）、
    #       GR>120（纯泥质；泥质盐 GR 65-86 不否决）。
    {
        'key': 'halite', 'cn': '岩盐', 'priority': 84, 'score_min': 5.0,
        'core_min': 3,
        'desc': '岩盐：CNL<2（负~零中子=无氢+挖掘效应）且 1.90≤ρ<2.35 且 '
                'Δt<75 为必要条件；再要求负中子/盐核密度/高阻/低声波 至少 3 项。'
                '【2026-10-19 重写】旧条件 Δt<62/PE<1.2/GR<40 与骨架参数表 '
                'Halite=[2.03,0,67,4.70] 矛盾，3-SPS-111D 6442-6454m 12m '
                '盐岩（CNL≈-4.5 负中子、ρ2.04-2.15、Δt53-68、RT>500）'
                '因此整段漏判为砂岩/泥岩',
        'must': [
            ('CNL', '<', 2.0),
            ('DEN', '>=', 1.90),
            ('DEN', '<', 2.35),
            ('DT',  '<', 75.0),
        ],
        'core': [
            ('CNL', '<', -1.0, 2.0),   # 负中子挖掘效应——盐岩铁证
            ('DEN', '<', 2.15, 2.0),   # 盐核密度 2.03-2.16
            ('RT',  '>', 5.00, 1.5),   # 盐高阻（孔隙不导电）
            ('DT',  '<', 70.0, 1.0),   # 声波低于盐骨架值附近
            ('DEN', '>=', 1.95, 1.0),  # 盐核下限
            ('PE',  '<', 5.00, 0.5),   # 低 Pe 辅助（本井 PE 偏高，低权重）
        ],
        'deny': [
            ('CNL', '>', 8.0),    # 含氢响应，绝无盐
            ('DEN', '>', 2.45),   # 密度太高：硬石膏/灰岩
            ('DT',  '>', 85.0),   # 高声波：疏松层/煤
            {'all': [('GR', '>', 120.0)]},  # 纯泥质（泥质盐 GR 65-86 不否决）
        ],
    },
    # ---------- 火成岩：ρ 高、Pe 高、CNL 极低 ----------
    {
        'key': 'igneous', 'cn': '火成岩', 'priority': 86, 'score_min': 5.0,
        'core_min': 3,
        'desc': '火成岩：ρ>2.62 且 Pe>4.0 且 CNL<8 为必要条件；'
                '再要求中等 Δt、高阻 至少 3 项',
        'must': [
            ('DEN', '>', 2.62),
            ('PE',  '>', 4.00),
            ('CNL', '<', 8.0),
        ],
        'core': [
            ('DT',  '<', 85.0, 1.0),
            ('RT',  '>', 3.00, 1.0),
            ('DEN', '>', 2.75, 1.0),
            ('GR',  '<', 120.0, 0.5),
        ],
        'deny': [],
    },
    # ---------- 硬石膏：巴西蒸发岩序列特殊岩性【2026-10-15新增】 ----------
    # 用户：3-SPS-111D 硬石膏层是"很明显的特殊岩性"却没有识别出来。
    # 物性铁证（知识库 brazil_evaporite_sequence）：ρ~2.98、CNL≈0、
    # Δt 45-55、PE~5.05、GR≈0、极高阻 —— 每一项都与灰岩/白云岩可区分。
    {
        'key': 'anhydrite', 'cn': '硬石膏', 'priority': 90, 'score_min': 5.0,
        'core_min': 3,
        'desc': '硬石膏：ρ>2.83（石膏族骨架2.98，远超灰岩2.71）且中子≈0、'
                'Δt<62 为必要条件；ρ>2.92 权重3.5——灰岩体密度上限2.71，'
                'ρ>2.92 对灰岩不可能，是决定性证据【2026-10-15 提权：无元素'
                '测井井纯硬石膏(score 6.3)曾被灰岩(7.5)压过翻成灰岩】。'
                '巴西深海井盐下蒸发岩序列(盐岩→硬石膏→灰岩/白云岩)'
                '的标志性夹层',
        'must': [
            ('DEN', '>', 2.83),
            ('DT',  '<', 62.0),
            ('CNL', '<', 6.0),
        ],
        'core': [
            ('PE',  '>', 4.00, 1.0),
            ('GR',  '<', 40.0, 1.5),
            ('RT',  '>', 10.0, 1.5),
            ('DEN', '>', 2.92, 3.5),
            ('DT',  '<', 56.0, 0.8),
        ],
        'deny': [
            # 中子偏高（孔隙/泥质） → 不是硬石膏
            {'all': [('CNL', '>', 12.0)]},
            # 伽马明显偏高 → 泥岩/泥膏岩，不是纯硬石膏
            # （碳酸盐岩剖面下此阈值由 _rule_match 自动放宽+45）
            {'all': [('GR', '>', 85.0)]},
        ],
    },
    # ---------- 黄铁矿：高密度 + 极高 PE ----------
    {
        'key': 'pyrite', 'cn': '黄铁矿', 'priority': 92, 'score_min': 4.0,
        'core_min': 2,
        'desc': '黄铁矿：ρ>4.0 且 Pe>6 为必要条件（铁原子序数高）；'
                '再要求 CNL 极低 1 项即可',
        'must': [
            ('DEN', '>', 4.00),
            ('PE',  '>', 6.00),
        ],
        'core': [
            ('CNL', '<', 8.0, 1.0),
            ('RT',  '>', 3.00, 1.0),
            ('GR',  '<', 90.0, 0.5),
        ],
        'deny': [],
    },
    # ---------- 砾岩规则已禁用(用户2026-10-08, BET-1): 本井无砾岩特征，
    # DEN>2.35+CNL<20 与砂岩高度重叠导致546点误判砾岩；禁用后这些点按
    # 伽马/密度/声波自然落入砂岩或泥岩 ----------
    # ---------- 砂岩：低 GR + 中低密度 + 中低中子 ----------
    # GR 阈值放宽到 105：7660 ft 实测 GR=44、CNCF=25.7、ρ=2.27、Δt=86、
    # 高阻 9.6 —— 密度与中子都落在碳质泥岩窗口内，唯一能把它与碳质泥岩
    # 分开的可靠依据就是**伽马明显偏低**（44 vs 碳质泥岩 105-190）。
    {
        'key': 'sandstone', 'cn': '砂岩', 'priority': 45, 'score_min': 4.0,
        'core_min': 3,
        'desc': '砂岩：低伽马为第一判别项（石英骨架不放伽马）；'
                '要求中低密度、中低中子、中低声波至少 3 项同时成立。'
                '这保证 GR 44 的 7660 ft 砂岩不会被误判为碳质泥岩',
        'must': [
            # 【2026-10-08 自适应】伽马绝对阈值不通用（BET-1 GR中位155、高伽马
            # 占82%，用105会把 105-135 的明显砂岩漏判成泥岩）。'@GR_sand_max'
            # 由 adaptive_thresholds() 按本井 GR 分布（直方图谷值/分位）确定，
            # 无统计量时回退 105。
            ('GR', '<', '@GR_sand_max?105'),
        ],
        'core': [
            ('GR',  '<', '@GR_sand_max?105', 2.0),
            ('GR',  '<', '@GR_p10?80', 1.0),
            ('CNL', '<', 26.0, 1.5),
            ('DEN', '>', 2.10, 1.0),
            ('DEN', '<', 2.62, 1.0),
            ('DT',  '<', 100.0, 1.0),
            ('PE',  '<', 3.60, 0.5),
        ],
        'deny': [
            ('DEN', '<', 2.05),      # 密度太低 → 煤/碳质泥岩
            # 【2026-10-20 用户定案·物理否决】石英砂岩骨架极限 2.65 g/cm3
            # （零孔隙），任何真实砂岩 DEN 必 <2.65。3-SPS-111D 6473-6480m
            # 灰岩间致密灰岩段（DEN 2.77-2.89/GR 80/CNL 8.5/PE 5.2/RT 761，
            # 上下皆灰岩）曾凑满 GR+GR+CNL+DEN+DT 5 项 6.5 分误判砂岩——
            # DEN>2.65 一票否决，物理上无例外（重晶石校正已在步骤 0d 完成）
            ('DEN', '>', 2.65),
            # 2026-10-09 BET-1 泥岩误判修复：GR 落在直方图谷底附近模糊带
            # （GR<分界但仍偏高）时，单凭"GR<分界"不足以免除泥质嫌疑。
            # 若电阻率低（引用本井 RT P30，非普适 8Ω·m——不同井泥岩低阻
            # 端差异大）且声波偏高(>80us/ft)同时成立——这是
            # 泥岩的典型双响应（含水黏土低阻 + 泥质骨架高声波），
            # 无论 GR 是否低于谷底，一律不得判砂岩。
            # 实测 7390-7408/7549-7585ft：GR 115-135（谷底134.36）、
            # RT 2-3Ω·m、DT 90-110、CNL 23-30，此前被"GR<134.36→砂岩"
            # 全部误判，改后落入泥岩。
            {'all': [('GR', '>', '@GR_shale_soft?95'),
                     ('RT', '<', '@RT_mud_max?8'),
                     ('DT', '>', 80.0)]},
            # 2026-10-09 强泥质一票否决：GR 低于软分界（如 110-114 vs
            # 谷底134.36）但 RT 显著低阻（引用本井 RT P20，非普适 4Ω·m）
            # 且 DT>85us/ft——强低阻含水黏土 +
            # 泥质骨架高声波，双泥质响应足够定泥岩，砂岩一律否决。
            # BET-1 7549-7585ft 残留10点（GR 110-114/RT 2-3.6/DT 85-96）
            # 即此型，此前因 GR 未达软分界而漏判。
            {'all': [('GR', '>', '@GR_mud_strong?90'),
                     ('RT', '<', '@RT_mud_strong?4'),
                     ('DT', '>', 85.0)]},
        ],
    },
    # ---------- 泥岩（兜底）：中高 GR + 中高密度 ----------
    {
        'key': 'shale', 'cn': '泥岩', 'priority': 10, 'score_min': 2.0,
        'core_min': 2,
        'desc': '泥岩：高 GR(>95) 为必要条件；再要求密度/声波/中子/伽马中'
                '至少 2 项同时成立（中高密度 + 中高声波是泥质骨架的体现）。'
                '这是兜底岩性——7600/7620 ft（GR 109-114、ρ2.48-2.50）落在此处',
        'must': [
            # 【2026-10-09】must 从"GR>分界"放宽到"GR>0.85×分界（软分界）"：
            # 直方图谷底附近的模糊带不再一票否决泥岩，改由 core 多判据
            # 核验（DEN>2.4 / DT>85 / CNL>20 / GR 加权）。BET-1 实测
            # 7390-7408/7549-7585ft GR 115-135（谷底134.36）但 RT 2-3Ω·m、
            # DT 90-110、CNL 23-30 全为泥质响应，此前因 GR 略低于谷底
            # 被砂岩规则抢占，改后判泥岩。
            ('GR', '>', '@GR_shale_soft?95'),
        ],
        'core': [
            ('DEN', '>', 2.40, 1.5),
            ('DT',  '>', 85.0, 1.0),
            ('CNL', '>', 20.0, 1.0),
            ('GR',  '>', '@GR_sand_max?120', 1.0),
        ],
        'deny': [],
    },
]

# 数据驱动阈值：自动统计本井的 P5/P50/P95，把绝对门限换成相对判据
def adaptive_thresholds(series_map):
    """按本井统计量为硬判据给出"相对阈值"（返回 {key: (列, 比较符, 相对阈值)}）。

    用于把普适阈值（如 DEN<2.0 判煤）在不同井、不同仪器标定下仍然稳健：
    取该井 DEN 的 P5 作为"极低密度"参考等。
    """
    out = {}
    def q(col, p):
        cands = COL_CANDIDATES.get(col, [col])
        v = None
        for c in cands:
            if c in series_map:
                v = series_map[c]
                break
        if v is None or len(v) == 0:
            return None
        try:
            import numpy as _np
            return float(_np.nanpercentile(v, p))
        except Exception:
            return None
    out['DEN_p05'] = q('DEN', 5)
    out['DEN_p20'] = q('DEN', 20)
    out['DEN_p80'] = q('DEN', 80)
    out['CNL_p80'] = q('CNL', 80)
    out['CNL_p90'] = q('CNL', 90)
    out['PE_p10'] = q('PE', 10)
    out['PE_p20'] = q('PE', 20)
    out['PE_p80'] = q('PE', 80)
    out['DT_p60'] = q('DT', 60)
    out['GR_p05'] = q('GR', 5)
    out['GR_p10'] = q('GR', 10)
    out['GR_p20'] = q('GR', 20)
    out['GR_p80'] = q('GR', 80)
    out['GR_p90'] = q('GR', 90)

    # ---- GR 自适应砂泥分界（2026-10-08 用户要求）----
    # 伽马绝对阈值（如砂岩 GR<105 / 泥岩 GR>95）不通用：不同地区/地层/井段
    # 的伽马基线差别很大（BET-1 全井 GR 中位 155，高伽马占 82%，若用绝对
    # 阈值则 105-135 的明显砂岩全被漏判）。本井分界由分布形态确定：
    #   1) 双峰分布 → 取两峰间直方图谷底（砂岩群与泥岩群的自然分界）；
    #   2) 单峰/峰距不足 → 回退 min(P25, P50*0.8)。
    # 结果供规则表以 '@GR_sand_max?105' 形式引用；不同井自动适配。
    gr_sand_max = None
    try:
        gr_vals = None
        for c in COL_CANDIDATES.get('GR', ['GR']):
            if c in series_map:
                gr_vals = np.asarray(series_map[c], dtype=float)
                break
        if gr_vals is not None:
            gr_vals = gr_vals[np.isfinite(gr_vals)]
        if gr_vals is not None and len(gr_vals) >= 50:
            p1, p99 = np.nanpercentile(gr_vals, 1), np.nanpercentile(gr_vals, 99)
            if p99 - p1 > 20:
                hist, edges = np.histogram(gr_vals, bins=48, range=(p1, p99))
                hs = np.convolve(hist, np.ones(3) / 3.0, mode='same')
                i1 = int(np.argmax(hs))
                masked = hs.copy()
                masked[max(0, i1 - 5):i1 + 6] = 0.0
                i2 = int(np.argmax(masked))
                # 次峰须有足够高度（≥主峰15%）才认为真的双峰
                if hs[i2] >= 0.15 * hs[i1] and abs(i2 - i1) >= 5:
                    a, b = (i1, i2) if i1 < i2 else (i2, i1)
                    vpos = a + int(np.argmin(hs[a:b + 1]))
                    gr_sand_max = float(edges[min(vpos + 1, len(edges) - 1)])
    except Exception:
        gr_sand_max = None
    if gr_sand_max is None:
        p25, p50 = q('GR', 25), q('GR', 50)
        if p25 is not None and p50 is not None:
            gr_sand_max = float(min(p25, p50 * 0.8))
        elif p25 is not None:
            gr_sand_max = float(p25)
    if gr_sand_max is not None:
        out['GR_sand_max'] = gr_sand_max
        out['GR_shale_min'] = gr_sand_max    # 同一分界，砂/泥 must 互斥
        # 2026-10-09 软分界：直方图谷底附近存在模糊带（GR 接近分界的点），
        # 该带内单凭 GR 不足以区分砂泥——必须由 RT/DT/CNL 等泥质响应联合
        # 裁决。0.85×分界作为"进入泥岩候选"的软门槛：低于分界但仍接近的
        # 点不再被砂岩 must 一票抢走，交给 core 多判据核验。
        out['GR_shale_soft'] = 0.85 * gr_sand_max
        # 2026-10-09 强泥质门槛（0.70×分界）：GR 即使低于软分界，若同时
        # 电阻率极低+声波高(>85us/ft)——含水黏土强低阻+泥质骨架
        # 高声波——仍是典型泥岩响应（BET-1 7549-7585ft 残留10点 GR 110-114、
        # RT 2-3.6Ω·m、DT 85-96 即此型），砂岩一票否决。
        out['GR_mud_strong'] = 0.70 * gr_sand_max

    # ---- RT 自适应泥质电阻率上限（2026-10-09 用户要求）----
    # 泥岩"低阻端"不是普适定值：不同井泥岩 RT 分布差异很大（BET-1
    # 裸眼段 RT P40=4.20/P50=7.60，其泥岩 RT 主体 2.7-3.6、砂岩 P10=4.7，
    # 泥/砂 RT 分界恰在 4-4.7；高阻泥岩井 P50 可能 >20）。故砂岩 deny
    # 组合的电阻率阈值改为引用本井统计量：
    #   RT_mud_max     = 裸眼段 RT P50 —— "泥质响应上限"（原定值 8.0；
    #                    BET-1=7.60，与原行为等价且自动贴井）
    #   RT_mud_strong  = 裸眼段 RT P40 —— "显著低阻/强泥质上界"（原定值
    #                    4.0；BET-1=4.20，恰在泥/砂 RT 分界处，覆盖
    #                    7549-7585 段 RT 2.6-4.2 的泥岩、不误伤 RT>4.7
    #                    的砂岩）
    # 下限保护：P50<3.0 取 3.0、P40<2.0 取 2.0（拒收统计噪音）；RT 曲线
    # 缺失时置 None，由规则表 '@?fallback' 回退普适 8.0/4.0。
    # 2026-10-09 曾用 P30/P20（3.04/2.54）实测偏严：7549-7585 段
    # RT 2.6-3.6 的泥岩被漏出（泥岩 135→108），故上修为 P50/P40。
    _rt50 = q('RT', 50)
    _rt40 = q('RT', 40)
    out['RT_mud_max'] = (max(_rt50, 3.0) if _rt50 else None)
    out['RT_mud_strong'] = (max(_rt40, 2.0) if _rt40 else None)
    return out

# -*- coding: utf-8 -*-
"""基于矿物特征值与曲线响应的岩性识别器。

用法
----
    import lithology_recognizer as lr
    rec = lr.LithologyRecognizer(data, depth_unit='ft')
    lith = rec.recognize()          # 返回与 data 等长的 LITHOLOGY 序列
    print(rec.summary())            # 各岩性厚度统计

设计要点
--------
1. **多判据打分**：每条规则含 hard（必须全满足）+ soft（加权计分），
   避免单一门限被局部异常带跑；
2. **中值滤波**：识别前对各曲线做 5 点（≈1.25 ft）中值滤波，压制
   单点野值；煤层边界因此更干净；
3. **薄层合并**：厚度小于阈值的层并入相邻层，符合测井解释惯例；
4. **置信度**：每个样点给出得分与次优岩性，便于人工复核；
5. **自适应阈值**：同时输出本井的 P5/P20/P80 统计量，便于换井时调阈值。
"""
import numpy as np
import pandas as pd

# 煤层等需要更细的分辨率：最小保留厚度（ft）
# 各岩性最小保留厚度（ft）—— 薄于该厚度就并入邻段，避免毛刺。
# 煤与碳质泥岩是**标志层**，本身就很薄（BET-1 实测 7 个煤层段厚
# 2.5-6.0 ft，碳质泥岩薄层仅 1.25-1.5 ft），阈值必须放宽 ——
# 否则这些有地质意义的薄层会被当成毛刺抹平，煤层/碳质泥岩就从图上消失了。
MIN_THICKNESS_FT = {
    'coal': 0.5, 'carbonaceous_shale': 1.0, 'pyrite': 0.8,
    'halite': 1.5, 'anhydrite': 1.5, 'igneous': 2.0, 'limestone': 2.0,
    'dolomite': 2.0,
    'conglomerate': 2.0, 'sandstone': 1.5, 'shale': 1.5,
}
SMOOTH_PTS = 3          # 中值滤波点数（0.25 ft 采样 → 0.75 ft；再重会把煤层薄层边界抹掉）

class LithologyRecognizer:
    def __init__(self, data, depth_unit='ft', smooth=SMOOTH_PTS,
                 casing_mask=None, pe_reliable=True, profile_type='mixed',
                 neutron_reliable=True):
        self.raw = data
        self.depth_unit = str(depth_unit).lower()
        self.smooth = int(smooth)
        self.series = {}
        self._resolve_series()
        self.stats = adaptive_thresholds(self.series)
        self.confidence = None
        self.runner_up = None
        self.why = None
        self.scores = {}
        # 套管段掩码：套管内测井反映的是泥浆/钢材，不是岩石，
        # 必须整段排除岩性识别（否则会判成灰岩等，见 BET-1 6344-6447ft）
        # 注意长度必须与 data 一致 —— 弹簧段校正后的数据是剔除套管的子集，
        # 若掩码长度不匹配会错位，这里做严格校验
        _n_rows = len(data)
        if casing_mask is None:
            self.casing_mask = pd.Series(False, index=data.index)
        else:
            _cm = pd.Series(casing_mask).reset_index(drop=True)
            if len(_cm) == _n_rows:
                self.casing_mask = _cm.values
            else:
                logger.warning('套管掩码长度(%d)与数据行数(%d)不一致，'
                               '为安全起见忽略套管掩码', len(_cm), _n_rows)
                self.casing_mask = pd.Series(False, index=data.index)
        self.n_casing = int(self.casing_mask.sum())
        # PE 质量：程序本来就有 check_pe_quality()，它检测 PE 与密度/GR/RT 的
        # 一致性。**PE 与密度不匹配时不能用 PE 判断岩性** —— 这是既有设计，
        # 但此前只作用于 optimize_minerals 的 pe_override，岩性识别的规则表
        # 仍在用 PE 判据。实测 BET-1：DEN 中位 2.55（砂泥岩剖面）而 PE 中位 3.5，
        # 正是"PE 与密度不匹配"，此时 PE 判据必须全部失效。
        self.pe_reliable = bool(pe_reliable)
        # 中子质量（2026-10-08 QC专项检查）：中子与密度/声波孔隙度矛盾时，
        # CNL 相关判据（must/deny/core）全部跳过 —— 与 PE 门控同一思想
        self.neutron_reliable = bool(neutron_reliable)
        # 井级剖面约束：砂泥岩剖面下判碳酸盐需要更强证据
        self.profile_type = str(profile_type or 'mixed')
        # 元素测井矿物含量【2026-10-15】：VOL_* 交付成果是矿物最权威证据
        # （3-SPS-111D：VOL_CALCITE P50=0.63、VOL_DOLOM 0.16，此前从未参与
        # 逐点岩性判定，硬石膏层因此漏判）。>=3条矿物曲线时启用
        # "矿物主控"逐点定性，防止砂泥岩规则在碳酸盐井复发的系统性错误
        self.mineral_map = {}
        for _vc, _lk in (('VOL_CALCITE', 'limestone'),
                         ('VOL_DOLOM', 'dolomite'),
                         ('VOL_ANHY', 'anhydrite'),
                         ('VOL_SALT', 'halite'),
                         ('VOL_HALITE', 'halite'),
                         ('VOL_ILLITE', 'shale'),
                         ('VOL_BASALT', 'basalt')):
            if _vc in self.raw.columns:
                _s = pd.to_numeric(self.raw[_vc], errors='coerce')
                _a = _s.where((_s > -900) & (_s <= 2.0)).values.astype(float)
                if self.smooth >= 3:
                    _a = (pd.Series(_a)
                          .rolling(self.smooth, center=True, min_periods=1)
                          .median().values)
                self.mineral_map[_vc] = (_lk, _a)
        self.mineral_enabled = len(self.mineral_map) >= 3
        if self.mineral_enabled:
            import logging as _lgm   # _lg 在本方法后段才导入，此处自备
            _lgm.getLogger('logInt').info(
                '元素测井矿物主控已启用: %s',
                ', '.join('%s→%s' % (k, v[0]) for k, v in
                          sorted(self.mineral_map.items())))
        # 用标准 logging 而非模块级 logger —— 本段代码可能被
        # test_lithology_multicriteria.py 以 exec 方式单独提取执行，
        # 那种情况下模块级 logger 不存在。
        import logging as _lg
        _lg.getLogger('logInt').info(
            '岩性识别器初始化: 数据%d行, 套管掩码%d行(True %d), PE可信=%s, 中子可信=%s, 剖面=%s',
            _n_rows, len(self.casing_mask), self.n_casing,
            self.pe_reliable, self.neutron_reliable, self.profile_type)

    # ------------------------------------------------------------------
    def _resolve_series(self):
        """按候选名取出各条曲线，做中值滤波并转为 float 数组。"""
        for key, cands in COL_CANDIDATES.items():
            v = None
            used = None
            for c in cands:
                if c in self.raw.columns:
                    s = pd.to_numeric(self.raw[c], errors='coerce')
                    if s.notna().sum() > len(self.raw) * 0.05:
                        v = s
                        used = c
                        break
            if v is None:
                continue
            arr = v.values.astype(float)
            if self.smooth >= 3:
                s = pd.Series(arr)
                med = s.rolling(self.smooth, center=True, min_periods=1).median()
                arr = med.values
            self.series[key] = arr
            if used != key:
                self.series.setdefault('_used', {})[key] = used

        # 派生列：扩径比 CAL/BIT。用于识别水泥返高段（固井污染带）——
        # 那段测井反映的是水泥+岩屑，不是岩石，密度/中子/声波全都失真。
        if 'CALR' not in self.series:
            cal = self.series.get('CAL')
            bit = self.series.get('BIT')
            if cal is not None and bit is not None:
                bit_a = np.where(np.asarray(bit) > 0.1, np.asarray(bit),
                                 np.nan)
                with np.errstate(divide='ignore', invalid='ignore'):
                    self.series['CALR'] = np.asarray(cal, dtype=float) / bit_a
                self.series.setdefault('_used', {})['CALR'] = 'CAL/BIT(derived)'

    # ------------------------------------------------------------------
    def _val(self, row_idx, key):
        arr = self.series.get(key)
        if arr is None:
            return None
        try:
            v = arr[row_idx]
        except Exception:
            return None
        if v is None or np.isnan(v):
            return None
        return float(v)

    def _cmp(self, v, op, thr):
        thr = self._resolve_thr(thr)
        if v is None or thr is None:
            return False
        if op == '<':
            return v < thr
        if op == '<=':
            return v <= thr
        if op == '>':
            return v > thr
        if op == '>=':
            return v >= thr
        return False

    def _resolve_thr(self, thr):
        """自适应阈值引用解析（2026-10-08 用户要求：伽马绝对阈值不通用）。

        规则表中的阈值可写为 '@KEY?fallback'：KEY 是 adaptive_thresholds()
        输出的本井统计量（如 GR_sand_max），按本井 GR 分布（直方图谷值/分位）
        动态确定；统计量缺失时回退 '?' 后的普适绝对值。
        """
        if isinstance(thr, str) and thr.startswith('@'):
            body = thr[1:]
            if '?' in body:
                key, fb = body.split('?', 1)
            else:
                key, fb = body, None
            v = (self.stats or {}).get(key)
            if v is not None and np.isfinite(v):
                return float(v)
            try:
                return float(fb) if fb is not None else None
            except (TypeError, ValueError):
                return None
        return thr

    def _resolve_rule_thresholds(self, rule):
        """深拷贝规则并把其中所有 '@KEY?fallback' 阈值解析为本井数值。

        must/deny 支持单条件元组与 {'all': [...]} 多条件字典；
        core 为 (列, 比较符, 阈值[, 权重]) 元组。
        """
        def _conv3(t):
            return (t[0], t[1], self._resolve_thr(t[2]))

        out = dict(rule)
        resolved = []
        for item in rule.get('must', []):
            if isinstance(item, dict):
                resolved.append({'all': [_conv3(t) for t in item.get('all', [])]})
            else:
                resolved.append(_conv3(item))
        out['must'] = resolved

        resolved = []
        for item in rule.get('deny', []):
            if isinstance(item, dict):
                resolved.append({'all': [_conv3(t) for t in item.get('all', [])]})
            else:
                resolved.append(_conv3(item))
        out['deny'] = resolved

        out['core'] = [(_conv3(it)) + tuple(it[3:]) for it in rule.get('core', [])]
        return out

    # ------------------------------------------------------------------
    def _rule_match(self, i, rule):
        """多判据一致性判定（单条判据不决定结论，多条相互印证才定性）。

        返回 (是否通过, 加权总分, 命中说明)。

        判定链（三段，缺一不可）：
          1. **必要项 must**  —— 该岩性物理上不可缺的特征，缺一即否决。
             作用是杜绝"只靠一条曲线就定性"。
          2. **排除项 deny**  —— 命中即否决。排除项支持两种写法：
               · 单条件: ('GR', '>', 135.0)          —— 该条件本身即足以否决
               · 多条件: {'all': [(...),(...)]}     —— 全部满足才否决
             多条件写法很重要：煤层可含灰分（GR 可达 150），若把 GR>135
             写成单条件会误杀灰分煤；写成"GR>135 **且** DEN>1.90"（密度不够低
             时高伽马说明是泥质层）才是正确的排除逻辑。
          3. **一致性项 core**—— 要求至少 core_min 项同时成立（M-of-K）。
             单条判据不决定结论，多条判据相互印证才定性。
        """
        reasons = []
        # ---- 0. 自适应阈值解析：'@KEY?fallback' 统一换算为本井数值 ----
        # （用户 2026-10-08：伽马等绝对阈值不通用，须按本井分布动态确定；
        #   预先解析保证后续 must/deny/core 与命中说明里都是数值格式化）
        rule = self._resolve_rule_thresholds(rule)
        # ---- 0.5 PE 质量门控：PE 与密度不匹配时，PE 判据一律失效 ----
        # 程序本来就有 check_pe_quality()，它检查 PE 与密度/GR/RT 的一致性。
        # 实测 BET-1：DEN 中位 2.55（典型砂泥岩）而 PE 中位 3.5 → PE 不可信。
        # 此时若还用 PE 判岩性，会把 70 多段砂泥岩判成灰岩（那些段 ρ2.47-2.73、
        # Δt66-107、CNL 11-34，没有一项符合灰岩的 CNL<10/Δt<80/GR<40）。
        # 因此：**PE 相关的 must / deny / core 判据在此直接跳过**。
        _skip_pe = not self.pe_reliable
        # 中子门控（2026-10-08）：QC判定中子与孔隙度体系矛盾时跳过CNL判据
        _skip_nphi = not self.neutron_reliable

        def _skipped(col):
            """该列的判据是否因曲线质量不可信而失效"""
            return ((_skip_pe and col == 'PE') or
                    (_skip_nphi and col in ('CNL', 'NPHI')))
        # 井级剖面约束：砂泥岩剖面下判碳酸盐需要更多一致性项
        _ss_profile = (self.profile_type == 'sand_shale')
        # 镜像守门【2026-10-15】：碳酸盐岩剖面下判砂岩同样要求更多一致性项
        _cb_profile = (self.profile_type == 'carbonate')
        # 碳酸盐岩剖面下，碳酸盐类岩性的"高伽马=泥岩"排除项放宽【2026-10-15】：
        # 泥质灰岩 GR 70-120 与砂泥岩重叠（3-SPS-111D 实测 GR P50=90，
        # DEN 2.63/PE 5.16 是铁证灰岩），GR>110 的绝对否决会把含泥
        # 碳酸盐层全杀掉 → 剖面为碳酸盐时 GR 排除阈值 +45（110→155）
        _cb_gr_relax = (self.profile_type == 'carbonate' and
                        rule['key'] in ('limestone', 'dolomite', 'anhydrite'))

        def _dthr(col, op, thr):
            if _cb_gr_relax and col == 'GR' and op == '>':
                return thr + 45.0
            return thr

        # ---- 1. 必要项：全部满足 ----
        for item in rule.get('must', []):
            cols = item.get('all') if isinstance(item, dict) else None
            if cols:
                # 多条件必要项：全部满足才算命中
                bad = None
                for col, op, thr in cols:
                    if _skipped(col):
                        continue      # 判据曲线不可信 → 该判据不作数
                    v = self._val(i, col)
                    if not self._cmp(v, op, thr):
                        bad = (col, op, thr, v)
                        break
                if bad:
                    return (False, 0.0,
                            ['必要项不满足: %s%s%.2f(实测%s)'
                             % (bad[0], bad[1], bad[2],
                                'NaN' if bad[3] is None else '%.2f' % bad[3])])
                reasons.append('&'.join('%s%s%.2f' % (c, o, t) for c, o, t in cols
                                       if not _skipped(c)))
            else:
                col, op, thr = item
                if _skipped(col):
                    continue
                v = self._val(i, col)
                if not self._cmp(v, op, thr):
                    return (False, 0.0, ['必要项不满足: %s%s%.2f(实测%s)'
                                         % (col, op, thr,
                                            'NaN' if v is None else '%.2f' % v)])
                reasons.append('%s%s%.2f' % (col, op, thr))

        # ---- 2. 排除项：命中即否决（支持多条件 AND 语义）----
        for item in rule.get('deny', []):
            cols = item.get('all') if isinstance(item, dict) else None
            if cols:
                # 多条件排除项：全部满足才否决
                use = [(c, o, _dthr(c, o, t))
                       for c, o, t in cols if not _skipped(c)]
                if len(use) != len(cols):
                    continue          # 含被跳过的判据 → 无法确认命中
                if all(self._cmp(self._val(i, c), o, t) for c, o, t in use):
                    txt = '&'.join('%s%s%.2f' % (c, o, t) for c, o, t in use)
                    vals = ', '.join('%s=%.2f' % (c, self._val(i, c))
                                     for c, _o, _t in use)
                    return (False, 0.0, ['排除项命中: %s (实测 %s)' % (txt, vals)])
            else:
                col, op, thr = item
                if _skipped(col):
                    continue
                thr = _dthr(col, op, thr)
                v = self._val(i, col)
                if self._cmp(v, op, thr):
                    return (False, 0.0, ['排除项命中: %s%s%.2f(实测%.2f)'
                                         % (col, op, thr, v)])

        # ---- 3. 一致性项：M-of-K ----
        core = [it for it in rule.get('core', []) if not _skipped(it[0])]
        need = int(rule.get('core_min', 1))
        # 砂泥岩剖面下，判碳酸盐类岩性要求更多一致性项
        if _ss_profile and rule['key'] in ('limestone', 'dolomite'):
            need += 1
        # 碳酸盐岩剖面下判砂岩 need+2【2026-10-15 镜像守门】：自适应GR
        # 分界（@GR_sand_max?105）在碳酸盐井单峰GR分布下回退105，泥质
        # 灰岩（GR90/DEN2.63/CNL2/PE5.16）能凑出 sandstone 5.5 分 >
        # limestone 5.0 而翻成砂岩（3-SPS-111D"岩性不对"反复翻面的
        # 机制之一）。真砂岩 CNL/PE/DEN/DT 多项全中，通常仍能过守门。
        if _cb_profile and rule['key'] == 'sandstone':
            need += 2
        score = 0.0
        hits = 0
        hit_txt = []
        for it in core:
            col, op, thr = it[0], it[1], it[2]
            w = it[3] if len(it) > 3 else 1.0
            v = self._val(i, col)
            if self._cmp(v, op, thr):
                hits += 1
                score += w
                hit_txt.append('%s%s%.2f' % (col, op, thr))
        if hits < need:
            return (False, score, ['一致性不足: 命中%d项/需%d项 [%s]'
                                   % (hits, need, '; '.join(hit_txt))])
        # 必要项同样计入总分，使其与一致性项等价重要
        score += 1.0 * len(rule.get('must', []))
        reasons.extend(hit_txt)
        return (True, score, reasons)

    # ------------------------------------------------------------------
    def _basalt_like(self, i):
        """曲线特征判玄武岩（标准2.2: DEN 2.65-2.95、AC 45-62 μs/ft、
        PE 3-6，蚀变段放宽；本井灰岩 GR 基线 112 API 与玄武岩段重叠，
        GR 不可作判据）。"""
        den = self._val(i, 'DEN')
        dt = self._val(i, 'DT')
        pe = self._val(i, 'PE')
        if den is not None:
            if not (2.55 <= den <= 2.95):
                return False
            if den >= 2.80:
                # 高密度强证据：时差放宽、PE 不限（黄铁矿化玄武岩 PE 达 7-12）
                return dt is not None and 45.0 <= dt <= 70.0
            return dt is not None and 45.0 <= dt <= 65.0
        # 密度缺测：DT+PE 组合
        return (dt is not None and 45.0 <= dt <= 65.0
                and pe is not None and 3.0 <= pe <= 6.5)

    def _basalt_context_ranges(self, md):
        """玄武岩段上下文扩展【2026-10-16】。

        元素测井反演在玄武岩顶界附近常把蚀变玄武岩分解为
        CALCITE+ILLITE（蚀变钙化富Ca、蚀变粘土富Al），按矿物主控把
        3-SPS-111D 6913.6-6920.3m 蚀变玄武岩误判 limestone；底界之下
        元素缺测段(6941.6-6944.6m, DEN 2.86-2.89)则兜底 shale。
        修复：以 VOL_BASALT>=0.45 连续段为锚，向两侧扩展——顶界向上
        <=12m、底界向下<=8m，且曲线满足玄武岩特征(_basalt_like)，
        从锚段边界向外连续扩展、遇不合格点即停。
        """
        if 'VOL_BASALT' not in self.mineral_map:
            return []
        bas = self.mineral_map['VOL_BASALT'][1]
        n = len(md)
        anchors = []
        i = 0
        while i < n:
            if np.isfinite(bas[i]) and bas[i] >= 0.45:
                j = i + 1
                while j < n and np.isfinite(bas[j]) and bas[j] >= 0.45:
                    j += 1
                anchors.append((i, j - 1))
                i = j
            else:
                i += 1
        if not anchors:
            return []
        rng = []
        for ai, aj in anchors:
            top = ai
            k = ai - 1
            while k >= 0 and (md[ai] - md[k]) <= 12.0 and self._basalt_like(k):
                top = k
                k -= 1
            bot = aj
            k = aj + 1
            while k < n and (md[k] - md[aj]) <= 8.0 and self._basalt_like(k):
                bot = k
                k += 1
            # 【2026-10-20 用户定案】锚段之下的元素/密度缺测段（DEN/CNL/PE 全
            # NaN）此前直接落 shale 兜底（3-SPS-111D 6944.6-6966m 整段泥岩，
            # 与上部玄武岩 GR/DT/RT 无差别）。修复：缺测但 GR/DT 连续的段
            # 随玄武岩锚段继续向外扩展（上限 40m、连续扩展遇不合格点即停）——
            # 从上到下一整套玄武岩；若出现真实泥岩（DT>70 等）自然中断。
            # 注意：严格扩展(bot>aj)之后仍要进宽松阶段——6941.6-6944.6 有
            # DEN 证据可严格扩展，6944.6 以下全缺测，两段要接力。
            if bot + 1 < n:
                _g = self.raw.get('GR')
                _dtc = self.raw.get('DT')
                if _g is not None and _dtc is not None:
                    _ga = np.asarray(_g, dtype=float)[ai:aj + 1]
                    _ga = _ga[np.isfinite(_ga)]
                    if _ga.size:
                        _gmed = float(np.median(_ga))
                        while (k < n and (md[k] - md[aj]) <= 40.0):
                            _den_k = self._val(k, 'DEN')
                            _cnl_k = self._val(k, 'CNL')
                            _pe_k = self._val(k, 'PE')
                            _dt_k = self._val(k, 'DT')
                            _gr_k = self._val(k, 'GR')
                            if not (_den_k is None and _cnl_k is None
                                    and _pe_k is None):
                                break     # 有密度/中子/PE 证据 → 交回严格判据
                            if _dt_k is not None and not (45.0 <= _dt_k <= 70.0):
                                break     # 声波有值但超出玄武岩带 → 岩性变化
                            _rt_k = self._val(k, 'RT')
                            if _rt_k is not None and _rt_k < 3.0:
                                break     # 明确低阻泥岩证据（如本井页岩 RT≈4）
                            if _gr_k is None or abs(_gr_k - _gmed) > 25.0:
                                break     # 伽马跳变 → 岩性变化
                            # 全缺测（仅 GR 连续、无低阻证据）→ 无岩性变化
                            # 支撑，延续锚段玄武岩（用户定案 2026-10-20）
                            bot = k
                            k += 1
            if top < ai or bot > aj:
                rng.append((md[top], md[bot], md[ai], md[aj]))
        return rng

    # ------------------------------------------------------------------
    def recognize(self, depth_min=None, depth_max=None):
        """执行识别，返回长度与 data 相同的岩性名数组（小写英文）。"""
        md = pd.to_numeric(self.raw['MD'], errors='coerce').values
        n = len(md)
        lith = np.array(['shale'] * n, dtype=object)
        conf = np.zeros(n, dtype=float)
        rup = np.array([''] * n, dtype=object)
        why = np.array([''] * n, dtype=object)
        all_scores = np.zeros((n, len(LITHOLOGY_RULES)), dtype=float)
        # 玄武岩段上下文扩展区间（元素测井锚段 + 曲线特征边界扩展）
        _bas_rng = (self._basalt_context_ranges(md)
                    if self.mineral_enabled else [])
        if _bas_rng:
            logger.info('玄武岩段边界扩展: %s',
                        ['%.1f-%.1fm(锚段%.1f-%.1fm)' % r for r in _bas_rng])

        for i in range(n):
            if depth_min is not None and not (depth_min <= md[i] <= (depth_max or 1e18)):
                continue
            # 套管段：测井反映泥浆/钢材，不是岩石 → 不做岩性识别
            if self.n_casing and bool(self.casing_mask[i]):
                lith[i] = 'casing'
                why[i] = '套管内测井（泥浆/钢），不做岩性识别'
                continue
            # 玄武岩段上下文扩展【2026-10-16】：元素测井锚段边界外，
            # 曲线特征符合玄武岩的连续段直接判玄武岩（优先于矿物主控，
            # 修正元素反演在火成岩界面的 CALCITE+ILLITE 分解误差）
            if _bas_rng:
                for _t, _b, _at, _ab in _bas_rng:
                    if _t <= md[i] <= _b:
                        lith[i] = 'basalt'
                        conf[i] = 6.5
                        why[i] = ('玄武岩段边界扩展: 邻段元素测井VOL_BASALT'
                                  '>=0.45(锚段%.1f-%.1fm), 曲线特征'
                                  '(DEN/DT/PE)符合玄武岩' % (_at, _ab))
                        break
                if lith[i] == 'basalt':
                    continue
            # 元素测井矿物含量主控【2026-10-15】：某矿物体积>=0.45 且占
            # 全部矿物 >=50% 时直接定性 —— 元素测井交付成果比曲线规则更
            # 权威；未达主导时回落到多判据规则链
            if self.mineral_enabled:
                _vv = {k: a[i] for k, (_lk, a) in self.mineral_map.items()
                       if np.isfinite(a[i])}
                if _vv:
                    _mx = max(_vv, key=_vv.get)
                    _tot = sum(_vv.values())
                    if (_vv[_mx] >= 0.45 and _tot > 0
                            and _vv[_mx] / _tot >= 0.50):
                        lith[i] = self.mineral_map[_mx][0]
                        conf[i] = 4.0 + 4.0 * (_vv[_mx] / _tot)
                        why[i] = ('元素测井矿物含量主控: %s=%.2f'
                                  '(占矿物总量%.0f%%)'
                                  % (_mx, _vv[_mx], _vv[_mx] / _tot * 100))
                        continue
            cands = []
            for ri, rule in enumerate(LITHOLOGY_RULES):
                ok, s, reasons = self._rule_match(i, rule)
                if ok:
                    all_scores[i, ri] = s
                    cands.append((s, rule.get('priority', 0), rule['key'],
                                  '; '.join(reasons)))
            if not cands:
                # 无任何岩性通过多判据检验 → 保持默认泥岩（兜底）
                continue
            # 排序：先按加权总分，同分再按优先级（煤/碳质泥岩优先于砂泥岩）
            cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
            best_s, _pri, best_key, best_why = cands[0]
            if best_s < self._min_score(best_key):
                continue
            lith[i] = best_key
            conf[i] = best_s
            rup[i] = cands[1][2] if len(cands) > 1 else ''
            why[i] = best_why
        self.confidence = conf
        self.runner_up = rup
        self.why = why
        self.scores = all_scores
        self.lith = lith
        return lith

    @staticmethod
    def _min_score(key):
        for r in LITHOLOGY_RULES:
            if r['key'] == key:
                return r.get('score_min', 2.0)
        return 2.0

    # ------------------------------------------------------------------
    def _merge_thin(self, lith, min_ft):
        """把厚度 < 阈值的段并入相邻段（优先并入厚度更大的一侧）。"""
        md = pd.to_numeric(self.raw['MD'], errors='coerce').values
        n = len(lith)
        if n < 3:
            return lith
        # 聚成连续段
        segs = []
        i = 0
        while i < n:
            j = i + 1
            while j < n and lith[j] == lith[i]:
                j += 1
            segs.append([i, j - 1, lith[i]])
            i = j
        # 套管段是"非岩石"，不参与薄层合并，否则会被并入邻段岩性
        if self.n_casing:
            segs = [s for s in segs if s[2] != 'casing']
        # 段厚必须**加上一个采样间隔** —— 否则 6 个点(0.25ft 采样)的层
        # 算成 5×0.25=1.25ft，恰好卡在 1.5ft 阈值以下被误并掉。
        # 实测 BET-1 碳质泥岩有 8 段 1.25-1.5ft 的薄层因此被抹平。
        _step = _step_of(md)
        changed = True
        rounds = 0
        while changed and rounds < 6:
            changed = False
            rounds += 1
            for si in range(len(segs)):
                a, b, key = segs[si]
                th = (md[b] - md[a]) + _step
                if th >= min_ft.get(key, 1.5):
                    continue
                # 找左右邻居（跳过自身）
                left = segs[si - 1][2] if si > 0 else None
                right = segs[si + 1][2] if si + 1 < len(segs) else None
                if left is None and right is None:
                    continue
                if left is None:
                    target = right
                elif right is None:
                    target = left
                else:
                    tl = md[segs[si - 1][1]] - md[segs[si - 1][0]]
                    tr = md[segs[si + 1][1]] - md[segs[si + 1][0]]
                    target = left if tl >= tr else right
                lith[a:b + 1] = target
                # 同步识别说明：薄层被并入邻层，why 必须与新岩性一致
                # （否则出现 lith=shale 而 why=GR<134(sandstone) 的错位误导）
                if getattr(self, 'why', None) is not None:
                    try:
                        self.why[a:b + 1] = ['薄层%.1fft并入%s' % (th, target)] * (b - a + 1)
                    except Exception:
                        pass
                segs[si][2] = target
                changed = True
            # 重新聚合
            newsegs = []
            i = 0
            while i < n:
                j = i + 1
                while j < n and lith[j] == lith[i]:
                    j += 1
                newsegs.append([i, j - 1, lith[i]])
                i = j
            segs = newsegs
        return lith

    # ------------------------------------------------------------------
    def _refine_sand_shale_layers(self, lith):
        """按GR半幅度点补划砂/泥岩薄夹层（2026-10-08 用户要求）。

        逐点阈值法对薄夹层系统性失效：泥岩夹层的GR峰值被围岩砂岩稀释
        （BET-1 7956-7957ft 峰值仅136，全幅度泥岩GR>180），达不到自适应
        分界(134.36)就被逐点判成砂岩；薄于1.5ft的夹层又被 _merge_thin
        并入邻层（7946-7947ft WHY='薄层1.2ft并入sandstone'）。
        测井解释惯例：**层界面取曲线半幅度点**——夹层极值与围岩基线的
        中值处，层厚=两半幅度点间距。

        本方法在逐点识别 + 薄层合并之后运行，只"补夹层"不重排全井：
          1. 自适应分界 GR_sand_max 分出砂岩群/泥岩群，P25/P75 作净砂/
             净泥基线，中值线(与分界取小)作夹层检测线；
          2. 检测线以上连续段(≥3点)且两侧为砂岩=泥岩夹层候选；
             检测线以下连续段且两侧为泥岩=砂岩夹层候选；
          3. 幅度守卫(≥30%净砂-净泥幅度)防弱起伏成层；密度守卫(局部化)：
             夹层中位DEN与**局部围岩**(段±32点对侧岩性中位)对比——泥岩
             夹层比邻近砂岩致密+0.02、砂岩夹层比邻近泥岩轻-0.02（全局
             P20在砂岩占比高的井会落进砂岩密度区间内误拦真夹层），无
             局部围岩回退全局P20/P50混合值；
          4. 夹层界面向两侧扩展到半幅度处（GR越过半幅值或遇非砂/泥点
             停止，密度守卫逐点同样生效，限8ft），扩展重叠取中点；
          5. 仅改写 sandstone/shale 两类点，同步 why/conf。
        """
        import logging as _lg
        gr = self.series.get('GR')
        if gr is None or len(gr) != len(lith):
            return lith
        thr = (self.stats or {}).get('GR_sand_max')
        if thr is None or not np.isfinite(thr):
            return lith
        n = len(lith)
        # 可重划点：仅砂/泥两类（煤/碳质泥岩/灰岩/套管等标志层不动）
        refinable = np.array([lk in ('sandstone', 'shale') for lk in lith],
                             dtype=bool)
        _fin = np.isfinite(gr)
        # 基线：砂岩群/泥岩群代表值（只统计当前判为砂/泥的点，排除
        # 煤层/套管等GR污染；套管GR低会拉低砂岩基线）
        _base_ok = _fin & refinable
        if self.n_casing:
            _base_ok &= ~np.asarray(self.casing_mask, dtype=bool)
        sand_vals = gr[_base_ok & (gr < thr)]
        shale_vals = gr[_base_ok & (gr > thr)]
        if len(sand_vals) < 30 or len(shale_vals) < 30:
            return lith
        sand_base = float(np.nanpercentile(sand_vals, 25))
        shale_base = float(np.nanpercentile(shale_vals, 75))
        if not (shale_base - sand_base) >= 25:
            return lith
        mid = min(0.5 * (sand_base + shale_base), float(thr))
        contrast = shale_base - sand_base

        # 密度守卫阈值（DEN缺失时跳过该守卫）
        den = self.series.get('DEN')
        # 【2026-10-09 泥质响应守卫】半幅度扩展向**砂岩**侧推进时，
        # 若扩展点呈泥质双响应（RT<8Ω·m 且 DT>80us/ft，与识别器砂岩
        # deny 同口径），说明该点实际是泥岩，不得划入砂岩——纯 GR
        # 半幅度会把 GR 略低但低阻高声波的泥岩整体翻回砂岩（BET-1
        # 7390-7408ft 49 点即被"层界GR=154"半幅度划层翻回砂岩）。
        rt = self.series.get('RT')
        dt = self.series.get('DT')
        _mud = None
        if rt is not None and dt is not None \
                and len(rt) == n and len(dt) == n:
            # 电阻率上限引用本井统计量 RT_mud_max（裸眼段 RT P30，
            # 与原 deny 组合同一口径；缺失回退 8.0），与识别器判据一致
            _rt_mud_max = (self.stats or {}).get('RT_mud_max') or 8.0
            _mud = np.zeros(n, dtype=bool)
            _mud[(np.isfinite(rt) & np.isfinite(dt)
                  & (rt < _rt_mud_max) & (dt > 80.0))] = True
        den_lo = den_hi = None
        if den is not None and len(den) == n:
            p20 = (self.stats or {}).get('DEN_p20')
            p80 = (self.stats or {}).get('DEN_p80')
            if p20 is not None and np.isfinite(p20):
                den_lo = float(p20)          # 泥岩夹层下限
            if p20 is not None and p80 is not None:
                den_hi = 0.5 * (float(p20) + float(p80))  # 砂岩夹层上限

        # ---- 初步分层：GR≥mid 为泥质段(M)，<mid 为砂质段(S) ----
        is_m = np.where(_fin, gr >= mid, False)
        runs = []
        i = 0
        while i < n:
            j = i
            while j + 1 < n and is_m[j + 1] == is_m[i]:
                j += 1
            runs.append([i, j, bool(is_m[i])])
            i = j + 1
        # 噪声段（<3点≈0.75ft）并入前段，防毛刺成层；首段太小并入后段
        merged = []
        for r in runs:
            if not merged or (r[1] - r[0] + 1) >= 3:
                merged.append(r)
            else:
                merged[-1][1] = r[1]
        if len(merged) >= 2 and (merged[0][1] - merged[0][0] + 1) < 3:
            merged[1][0] = merged[0][0]
            merged.pop(0)

        def _ctx(k, step):
            """从k出发按step方向找最近可重划点的当前岩性（≤32点）。"""
            for _ in range(32):
                if k < 0 or k >= n:
                    return None
                if refinable[k]:
                    return lith[k]
                k += step
            return None

        spans = []  # [L, R, cls, half, extremum, base]
        for a, b, m in merged:
            ext = float(np.nanmax(gr[a:b + 1])) if m else float(np.nanmin(gr[a:b + 1]))
            if not np.isfinite(ext):
                continue
            base = sand_base if m else shale_base
            # 幅度守卫：极值与围岩基线差 ≥30% 净砂-净泥幅度
            if abs(ext - base) < 0.30 * contrast:
                continue
            # 【2026-10-08 密度守卫局部化】夹层密度应与**局部围岩**对比：
            # 泥夹层比邻近砂岩致密、砂夹层比邻近泥岩轻。全局DEN_p20在砂岩
            # 占比高的井会落进砂岩密度区间内部(BET-1 P20=2.478 vs 砂岩群
            # 2.31-2.47)，真泥岩夹层(中位2.448)被当海绿石砂岩拦下——改为
            # 段两侧32点内对侧岩性DEN中位作基线(泥夹层+0.02余量/砂夹层
            # -0.02余量)，无局部围岩时回退全局P20/P50混合值。
            opp_lith = 'sandstone' if m else 'shale'
            den_ref = None
            if den is not None and len(den) == n:
                _lv = [den[kk] for kk in range(max(0, a - 32), a)
                       if refinable[kk] and lith[kk] == opp_lith
                       and np.isfinite(den[kk])]
                _rv = [den[kk] for kk in range(b + 1, min(n, b + 33))
                       if refinable[kk] and lith[kk] == opp_lith
                       and np.isfinite(den[kk])]
                _all = _lv + _rv
                if len(_all) >= 5:
                    den_ref = float(np.median(_all))
                else:
                    den_ref = den_lo if m else den_hi
            if den is not None and den_ref is not None:
                dseg = den[a:b + 1]
                dseg = dseg[np.isfinite(dseg)]
                if len(dseg) >= 3:
                    dmed = float(np.median(dseg))
                    if m and dmed <= den_ref + 0.02:
                        continue   # 密度与围岩砂岩相当 → 更像砂岩(海绿石等)
                    if (not m) and dmed >= den_ref - 0.02:
                        continue   # 密度与围岩泥岩相当 → 更像粉砂质泥岩
            # 上下文：两侧最近砂/泥点（夹层必须嵌在对侧岩性中）
            lctx = _ctx(a - 1, -1)
            rctx = _ctx(b + 1, +1)
            want = 'shale' if m else 'sandstone'
            opp = 'sandstone' if m else 'shale'
            if opp not in (lctx, rctx):
                continue
            half = base + 0.5 * (ext - base)
            # 向两侧扩展到半幅度点（遇非可重划点/越界/超8ft停止，
            # 密度守卫逐点同样生效——与核心守卫同一局部基线）
            L = a
            while L - 1 >= 0 and refinable[L - 1] and _fin[L - 1] \
                    and (gr[L - 1] > half if m else gr[L - 1] < half) \
                    and (a - (L - 1)) < 32 \
                    and (den is None or den_ref is None or not m
                         or (np.isfinite(den[L - 1]) and den[L - 1] > den_ref)) \
                    and (m or _mud is None or not _mud[L - 1]):
                L -= 1
            R = b
            while R + 1 < n and refinable[R + 1] and _fin[R + 1] \
                    and (gr[R + 1] > half if m else gr[R + 1] < half) \
                    and ((R + 1) - b) < 32 \
                    and (den is None or den_ref is None or m
                         or (np.isfinite(den[R + 1]) and den[R + 1] < den_ref)) \
                    and (m or _mud is None or not _mud[R + 1]):
                R += 1
            spans.append([L, R, want, half, ext, base])

        # 重叠消解：同类重叠合并，异类重叠/相邻取中点为界
        spans.sort(key=lambda s: s[0])
        resolved = []
        for sp in spans:
            if resolved and sp[0] <= resolved[-1][1] + 1:
                prev = resolved[-1]
                if prev[2] == sp[2]:
                    prev[1] = max(prev[1], sp[1])
                    continue
                cut = (prev[1] + sp[0]) // 2
                prev[1] = min(prev[1], cut)
                sp[0] = max(sp[0], cut + 1)
                if sp[0] > sp[1]:
                    continue
            resolved.append(sp)

        n_flip = 0
        for L, R, cls, half, ext, base in resolved:
            for i in range(L, R + 1):
                if not (refinable[i] and _fin[i] and lith[i] != cls):
                    continue
                # 【2026-10-09 泥质响应守卫·种子点】半幅度 span 内部点
                # 同样受泥质双响应约束：want=sandstone 时，RT<8Ω·m 且
                # DT>80us/ft 的点是泥岩响应，不得被半幅度划层翻成砂岩
                # （BET-1 7390.0/7392.0 GR 118-127 但 RT 1.6-1.8、DT 106-110
                # 即被"层界GR=154"翻回砂岩；识别器已正确判泥岩）。
                if cls == 'sandstone' and _mud is not None and _mud[i]:
                    continue
                lith[i] = cls
                self.why[i] = ('半幅度点划层: 层界GR=%.0f'
                               '(极值%.0f与基线%.0f中值)' % (half, ext, base))
                self.confidence[i] = 6.0
                n_flip += 1
        if n_flip:
            _lg.getLogger('logInt').info(
                '半幅度点划层: 净砂基线%.0f/净泥基线%.0f/检测线%.0f, '
                '补划夹层重划%d点', sand_base, shale_base, mid, n_flip)
        return lith

    # ------------------------------------------------------------------
    def run(self, depth_min=None, depth_max=None, merge_thin=True):
        """完整流程：识别 → 薄层合并 → 半幅度划层 → 输出结果数组。"""
        lith = self.recognize(depth_min, depth_max)
        if merge_thin:
            min_ft = dict(MIN_THICKNESS_FT)
            if self.depth_unit == 'm':
                min_ft = {k: v * 0.3048 for k, v in MIN_THICKNESS_FT.items()}
            lith = self._merge_thin(lith, min_ft)
        # 【2026-10-08 用户要求】砂泥岩层界面按曲线半幅度点补划薄夹层：
        # 逐点阈值+薄层合并对薄夹层系统性失效（BET-1 7946-7947ft 泥岩
        # 夹层被并入砂岩、7956-7957ft 峰值被中值滤波稀释判成砂岩），
        # 半幅度点划层是测井解释惯例，同时修正砂/泥层厚度。
        if self.why is None or self.confidence is None:
            self.why = np.array([''] * len(lith), dtype=object)
            self.confidence = np.zeros(len(lith), dtype=float)
        try:
            lith = self._refine_sand_shale_layers(lith)
        except Exception as e:
            import logging as _lg
            _lg.getLogger('logInt').warning('半幅度划层失败(不影响主流程): %s', e)
        self.lith = lith
        return lith

    # ------------------------------------------------------------------
    def segments(self, lith=None):
        """返回 [(顶深, 底深, 厚度, 岩性, 平均置信度), ...]。"""
        if lith is None:
            lith = self.lith
        md = pd.to_numeric(self.raw['MD'], errors='coerce').values
        out = []
        i = 0
        n = len(lith)
        while i < n:
            j = i + 1
            while j < n and lith[j] == lith[i]:
                j += 1
            top, bot = md[i], md[min(j, n - 1)]
            cf = float(np.nanmean(self.confidence[i:j])) if self.confidence is not None else 0.0
            out.append((float(top), float(bot), float(bot - top), str(lith[i]), cf))
            i = j
        return out

    # ------------------------------------------------------------------
    def summary(self, lith=None, top_n=40):
        """按岩性汇总厚度与出现次数，并列出厚度最大的层段。"""
        segs = self.segments(lith)
        agg = {}
        for top, bot, th, key, cf in segs:
            agg.setdefault(key, [0, 0.0, 0.0])
            agg[key][0] += 1
            agg[key][1] += th
            agg[key][2] = max(agg[key][2], th)
        cn = {r['key']: r['cn'] for r in LITHOLOGY_RULES}
        unit = 'ft' if self.depth_unit == 'ft' else 'm'
        lines = ['=== 岩性识别结果统计（依据矿物特征值与曲线响应） ===',
                 '本井曲线分位数：']
        for k in ('DEN_p05', 'DEN_p20', 'DEN_p80', 'CNL_p80', 'CNL_p90',
                  'PE_p10', 'PE_p20', 'PE_p80', 'DT_p60', 'GR_p20', 'GR_p80'):
            if self.stats.get(k) is not None:
                lines.append('   %-10s %.2f' % (k, self.stats[k]))
        lines.append('')
        lines.append('%-16s %5s %10s %10s' % ('岩性', '层数', '总厚度(%s)' % unit,
                                          '最大单层(%s)' % unit))
        for key, (cnt, th, mx) in sorted(agg.items(), key=lambda x: -x[1][1]):
            lines.append('%-16s %5d %10.1f %10.1f' % (cn.get(key, key), cnt, th, mx))
        lines.append('')
        lines.append('=== 最厚的 %d 个层段 ===' % top_n)
        for top, bot, th, key, cf in sorted(segs, key=lambda s: -s[2])[:top_n]:
            lines.append('  %8.1f-%-8.1f ft  %6.1f ft  %-14s 置信%.1f'
                         % (top, bot, th, cn.get(key, key), cf))
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    def rule_report(self):
        """输出每条规则的判据说明（便于专家复核阈值是否合理）。"""
        lines = ['=== 岩性识别规则（多判据一致性：必要项 + 排除项 + M-of-K 一致性） ===']
        for r in LITHOLOGY_RULES:
            p = MINERAL_PROPS.get(r['key'], {})
            lines.append('')
            lines.append('【%s / %s】' % (r['cn'], r['key']))
            if p:
                lines.append('   矿物特征值: ρ=%s  Δt=%s  CNL=%s  Pe=%s  GR=%s  RT=%s'
                             % (p.get('rho', '-'), p.get('dt', '-'),
                                p.get('cnl', '-'), p.get('pe', '-'),
                                p.get('gr', '-'), p.get('rt', '-')))
            lines.append('   判别: %s' % r.get('desc', ''))
            must = '  '.join(_fmt_criteria(r.get('must', [])))
            deny = '  '.join(_fmt_criteria(r.get('deny', [])))
            core = '  '.join('%s%s%s×%s' % (it[0], it[1], _fmt_thr(it[2]),
                                             (it[3] if len(it) > 3 else 1))
                             for it in r.get('core', []))
            lines.append('   必要项(需全满足): %s' % (must or '-'))
            lines.append('   排除项(命中即否决): %s' % (deny or '-'))
            lines.append('   一致性项: %s' % (core or '-'))
            lines.append('   判定: 至少命中 %d 项一致性项 且 总分≥%.1f  优先级=%d'
                         % (r.get('core_min', 1), r.get('score_min', 2.0),
                            r.get('priority', 0)))
        # 本井自适应阈值解析结果（专家复核"自适应"引用的实际数值）
        _ad = {k: v for k, v in (self.stats or {}).items()
               if v is not None and ('GR_sand' in k or 'GR_shale' in k or k in ('GR_p05', 'GR_p10', 'GR_p80'))}
        if _ad:
            lines.append('')
            lines.append('   本井自适应阈值: ' + '  '.join('%s=%.1f' % (k, v) for k, v in sorted(_ad.items())))
        return '\n'.join(lines)

class SpringSegmentCorrector:
    """弹簧段校正类"""
    
    def __init__(self):
        """初始化弹簧段校正器"""
        pass
    
    def detect_spring_segments(self, data, curve_name='RHOB', sensitivity=3.0,
                               min_segment_length=5.0, use_drho=True,
                               use_caliper=True, use_cross_curve=True,
                               use_gr_independent=True):
        """
        检测弹簧段（螺旋井眼贴壁曲线周期性锯齿段）
        弹簧段特点（螺旋井眼机理，行业判据）：
        1. 在一段井段内变化的频率基本相同（周期性，对应螺旋槽距）
        2. 变化的最值相同（跳跃幅度一致）
        3. 和GR等其它曲线不相关（真地层信号会与GR相关，螺旋噪声不会）
        4. 至少是1米长度范围内
        5. 【增强判据】DRHO/Δρ 校正曲线同步异常（滑板间隙的直接证据）
        6. 【增强判据】井径 CALI 同周期锯齿（螺旋槽几何证据）
        7. 【增强判据】密度与贴壁电阻率（MSFL/RD）同周期跳跃（跨曲线同步）

        参数:
            data: 测井数据DataFrame
            curve_name: 要检测的曲线名称（默认RHOB密度曲线）
            sensitivity: 灵敏度（倍数），越高越敏感，默认3.0
            min_segment_length: 最小弹簧段长度（米），默认5米
            use_drho: 是否启用DRHO异常判据（默认True）
            use_caliper: 是否启用井径周期判据（默认True）
            use_cross_curve: 是否启用跨曲线同步判据（默认True）
            use_gr_independent: 是否启用与GR不相关判据（默认True）

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
        
        # 【2026-10-08 修正】波动度量改用"局部极差"（0.5m 窗口 max-min），
        # 替代相邻点差分。螺旋锯齿是数米尺度的峰-峰起伏（如 3m 周期、
        # 0.06 g/cc 振荡在 0.1m 采样下相邻点差仅 ~0.013），相邻点差分会
        # 把幅度稀释到阈值以下导致漏检；局部极差直接度量峰-峰幅度。
        window_pk = max(int(0.5 / dz), 5)      # 0.5m 窗口度量局部峰-峰
        if window_pk % 2 == 0:
            window_pk += 1
        _s = pd.Series(valid_curve)
        _smax = _s.rolling(window_pk, center=True, min_periods=3).max()
        _smin = _s.rolling(window_pk, center=True, min_periods=3).min()
        local_range = (_smax - _smin).to_numpy(copy=True)
        local_range[~np.isfinite(local_range)] = np.nan

        # 移除NaN
        valid_ranges = local_range[np.isfinite(local_range)]
        if len(valid_ranges) == 0:
            logger.warning(f"曲线 {curve_name} 局部极差数据全部无效，无法检测弹簧段")
            return []

        # 使用中位数和MAD计算阈值（更稳健）
        range_median = np.median(valid_ranges)
        range_mad = np.median(np.abs(valid_ranges - range_median))

        # 如果MAD为0，使用标准差作为替代
        if range_mad == 0 or np.isnan(range_mad):
            range_mad = np.std(valid_ranges)

        # 阈值 = 正常变化的sensitivity倍
        threshold = range_median + sensitivity * range_mad

        # 绝对阈值：峰-峰变化小于0.05 g/cm3不认为是螺旋锯齿
        # 【2026-10-27 R26】0.03→0.05：螺旋锯齿典型幅度 0.06-0.15 g/cc，
        # 岩性界面跳变常在 0.03-0.05 量级，抬高下限减少误报（用户定案）。
        min_abs_jump = 0.05
        threshold = max(threshold, min_abs_jump)

        # 波动点：局部峰-峰超过阈值（螺旋锯齿带）
        fluct = np.zeros(len(valid_curve), dtype=bool)
        _lr = np.nan_to_num(local_range, nan=0.0)
        fluct[_lr > threshold] = True

        # 1. 使用滑动窗口检测高频跳跃（1米窗口）
        window_size_1m = max(int(1 / dz), 10)  # 1米窗口
        if window_size_1m > 50:
            window_size_1m = 50

        # 计算每个点周围的跳跃率（1m 窗口内波动点占比）
        jump_rates_1m = np.zeros(len(valid_curve))
        _fr = pd.Series(fluct.astype(float)).rolling(
            window_size_1m, center=True, min_periods=5).mean().values
        jump_rates_1m[:] = np.nan_to_num(_fr, nan=0.0)

        # 2. 检测周期性模式（变化频率相同）
        # 使用自相关分析检测周期性
        acf_mask = np.zeros(len(valid_curve), dtype=bool)
        jump_locations = np.where(fluct)[0]
        if len(jump_locations) >= 5:
            from scipy.signal import correlate
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
        # 在波动区域内，局部极差的变异系数较小
        amplitude_consistency = np.zeros(len(valid_curve), dtype=bool)
        if np.sum(fluct) >= 5:
            jump_amplitudes = _lr[fluct]
            if len(jump_amplitudes) >= 5:
                amp_mean = np.mean(jump_amplitudes)
                amp_std = np.std(jump_amplitudes)
                # 如果波动幅度的变异系数较小，说明幅度一致
                if amp_mean > 0 and amp_std / amp_mean < 0.5:
                    amplitude_consistency[fluct] = True

        # 4. 检测与GR曲线的相关性（弹簧段通常与GR无关，弱证据）
        #    真地层变化（薄层/岩性）会让密度与GR同变，螺旋噪声不会。
        #    同样用局部极差度量 GR 波动，避免相邻点差分噪声化。
        gr_correlation_mask = np.zeros(len(valid_curve), dtype=bool)
        gr_range = None
        if use_gr_independent and 'GR' in data.columns:
            gr_data = data['GR'].values[valid_mask]
            _gs = pd.Series(gr_data)
            _gmax = _gs.rolling(window_pk, center=True, min_periods=3).max()
            _gmin = _gs.rolling(window_pk, center=True, min_periods=3).min()
            gr_range = (_gmax - _gmin).to_numpy(copy=True)
            gr_range[~np.isfinite(gr_range)] = np.nan

            # 计算局部相关性（密度局部极差 vs GR局部极差）
            corr_window = max(int(2 / dz), 20)
            _grr = np.nan_to_num(gr_range, nan=0.0)
            for i in range(len(valid_curve) - corr_window + 1):
                d_jump = _lr[i:i+corr_window]
                gr_change = _grr[i:i+corr_window]
                if len(d_jump) > 5 and np.std(d_jump) > 0 and np.std(gr_change) > 0:
                    corr = np.corrcoef(d_jump, gr_change)[0, 1]
                    # 如果相关性很低，可能是弹簧段
                    if np.abs(corr) < 0.3:
                        gr_correlation_mask[i:i+corr_window] = True

        # 5. 【增强判据】DRHO/Δρ 校正曲线同步异常（螺旋井眼 standoff 直接证据）
        #    密度补偿曲线（DRHO/DRHOC/DELTA_RHO/DEN_COR/CORR）异常波动表示
        #    滑板与井壁间隙大（桥接），是贴壁测井受螺旋井眼影响的直接指示。
        #    度量方式：DRHO 的局部极差（峰-峰）> 0.05 g/cc 且密度同时处于
        #    螺旋锯齿带（fluct）。
        drho_mask = np.zeros(len(valid_curve), dtype=bool)
        if use_drho:
            _drho_col = next((c for c in ('DRHO', 'DRHOC', 'DELTA_RHO', 'DEN_COR', 'CORR', 'DENCOR')
                              if c in data.columns), None)
            if _drho_col is not None:
                drho_data = data[_drho_col].values[valid_mask]
                _ds = pd.Series(np.abs(drho_data))
                _dmax = _ds.rolling(window_pk, center=True, min_periods=3).max()
                _dmin = _ds.rolling(window_pk, center=True, min_periods=3).min()
                drho_range = (_dmax - _dmin).to_numpy(copy=True)
                drho_range[~np.isfinite(drho_range)] = 0.0
                # DRHO 局部峰-峰 > 0.05（standoff 变化剧烈）且与密度锯齿同带
                # 【2026-10-27 R26】删除"<3 点退化为全井异常"兜底：全局 DRHO
                # 异常（井壁粗糙/扩径）不是弹簧段证据——111D 无弹簧段被误报
                # 10 段并错误校正 255 点的根因之一（用户定案"首先就不应该
                # 监测出来"）。
                drho_mask = (drho_range > 0.05) & fluct
                if np.sum(drho_mask) >= 3:
                    logger.info(f"  判据5(DRHO异常同步): {np.sum(drho_mask)} 点")

        # 6. 【增强判据】井径 CALI 周期同步（螺旋槽几何证据）
        #    螺旋井眼中多臂井径呈周期锯齿（1-3臂与2-4臂反相），单臂 CALI 也会
        #    与密度锯齿同步变化。度量方式：CALI 局部极差 > 0.25 in（螺旋槽深
        #    6mm 量级）且与密度锯齿同带。
        caliper_mask = np.zeros(len(valid_curve), dtype=bool)
        if use_caliper:
            _cal_col = next((c for c in ('CALI', 'CAL', 'DCAL', 'CAL1', 'HCAL')
                             if c in data.columns), None)
            if _cal_col is not None:
                cal_data = data[_cal_col].values[valid_mask]
                _cs = pd.Series(cal_data)
                _cmax = _cs.rolling(window_pk, center=True, min_periods=3).max()
                _cmin = _cs.rolling(window_pk, center=True, min_periods=3).min()
                cal_range = (_cmax - _cmin).to_numpy(copy=True)
                cal_range[~np.isfinite(cal_range)] = 0.0
                # 井径锯齿阈值：中位数+2*MAD，下限 0.25 in
                _cvalid = cal_range[cal_range > 0]
                if len(_cvalid) > 0:
                    _cmed = np.median(_cvalid)
                    _cmad = np.median(np.abs(_cvalid - _cmed))
                    if _cmad == 0 or np.isnan(_cmad):
                        _cmad = np.std(_cvalid)
                    cal_threshold = max(_cmed + 2.0 * _cmad, 0.25)
                    caliper_mask = (cal_range > cal_threshold) & fluct
                    # 【2026-10-27 R26】同判据5：删全局异常兜底（井壁粗糙不
                    # 等于弹簧段，必须与密度锯齿同带才算强证据）
                    if np.sum(caliper_mask) >= 3:
                        logger.info(f"  判据6(井径同步): {np.sum(caliper_mask)} 点")

        # 7. 【增强判据】跨曲线同步：密度与贴壁电阻率(MSFL/RD)同周期跳跃
        #    螺旋井眼同时影响所有贴壁仪器，密度与微球/浅侧向的锯齿应同周期同相位。
        #    度量方式：电阻率局部极差的相对值（%/100）> 15% 且与密度锯齿同带。
        cross_mask = np.zeros(len(valid_curve), dtype=bool)
        if use_cross_curve:
            _res_col = next((c for c in ('MSFL', 'RMSL', 'MCFL', 'RD', 'RS', 'LLS', 'LLD')
                             if c in data.columns), None)
            if _res_col is not None:
                res_data = data[_res_col].values[valid_mask]
                _rs = pd.Series(res_data)
                _rmax = _rs.rolling(window_pk, center=True, min_periods=3).max()
                _rmin = _rs.rolling(window_pk, center=True, min_periods=3).min()
                res_range = (_rmax - _rmin).to_numpy(copy=True)
                res_base = np.abs(res_data)
                res_base[~np.isfinite(res_base)] = 0.0
                with np.errstate(divide='ignore', invalid='ignore'):
                    res_rel = np.where(res_base > 0, res_range / res_base, 0.0)
                res_rel[~np.isfinite(res_rel)] = 0.0
                # 电阻率相对局部极差阈值：中位数+2*MAD，下限 15%
                _rvalid = res_rel[res_rel > 0]
                if len(_rvalid) > 0:
                    _rmed = np.median(_rvalid)
                    _rmad = np.median(np.abs(_rvalid - _rmed))
                    if _rmad == 0 or np.isnan(_rmad):
                        _rmad = np.std(_rvalid)
                    res_threshold = max(_rmed + 2.0 * _rmad, 0.15)
                    cross_mask = (res_rel > res_threshold) & fluct
                    # 【2026-10-27 R26】同判据5：删全局异常兜底
                    if np.sum(cross_mask) >= 3:
                        logger.info(f"  判据7(跨曲线同步): {np.sum(cross_mask)} 点")

        # 综合判定弹簧段
        # 条件1：跳跃率超过30%（更宽松）
        condition1 = jump_rates_1m > 0.3
        # 条件2：周期性或幅度一致性
        condition2 = acf_mask | amplitude_consistency
        # 条件3：与GR不相关（弱证据）
        condition3 = gr_correlation_mask
        # 【2026-10-08】条件4：物理/几何强证据（DRHO异常、井径同步、跨曲线同步）
        condition4 = drho_mask | caliper_mask | cross_mask

        # 综合规则：
        # 【2026-10-27 R26 用户定案】强证据**必须**：周期性/幅度一致这类
        # 统计特征在岩性边界跳变带同样成立（111D 碳酸盐岩/蒸发岩界面
        # 密度跳变 + 井壁粗糙 → 误报 10 段并错误校正 255 点），不能单独
        # 定案。弹簧段判定 = 高频跳跃 AND 周期/幅度一致 AND 物理几何
        # 强证据（DRHO/井径/跨曲线与密度锯齿**同带**）。无强证据（含
        # 曲线缺失）一律不判弹簧段——宁漏勿误；确有弹簧段的井由分井
        # 配置显式管理（_SPRING_SKIP_WELLS 为禁用表，检测参数
        # use_drho/use_caliper/use_cross_curve 可按井关掉强证据要求）。
        spring_mask = condition1 & condition2 & condition4
        
        logger.info(f"弹簧段检测 - {curve_name}:")
        logger.info(f"  采样间隔: {dz:.3f}m, 1米窗口大小: {window_size_1m}")
        logger.info(f"  峰-峰阈值: {threshold:.4f}, 中位数局部极差: {range_median:.4f}")
        logger.info(f"  条件1(跳跃率>30%): {np.sum(condition1)}/{len(valid_curve)}")
        logger.info(f"  条件2(周期性/幅度一致): {np.sum(condition2)}/{len(valid_curve)}")
        logger.info(f"  条件3(与GR无关): {np.sum(condition3)}/{len(valid_curve)}")
        logger.info(f"  条件4(DRHO/井径/跨曲线强证据): {np.sum(condition4)}/{len(valid_curve)}")
        logger.info(f"  综合候选弹簧段点数: {np.sum(spring_mask)}/{len(valid_curve)}")
        
        # 合并连续的弹簧段候选点
        # 【2026-10-08 修正】局部极差法的波动带是断续的（正弦锯齿每周期
        # 只有峰区超阈值，带长约半周期），若按"连续点"分段会被
        # min_segment_length 全部过滤。改为允许 gap 合并：间断不超过
        # 2m（≈螺旋周期量级）视为同一弹簧段。
        spring_segments = []
        in_spring = False
        start_depth = None
        gap_tol = max(int(2.0 / dz), 10)   # 2m 间断容忍
        _gap_run = 0

        for i in range(len(spring_mask)):
            if spring_mask[i]:
                if not in_spring:
                    in_spring = True
                    start_depth = valid_depth[i]
                _gap_run = 0
            else:
                if in_spring:
                    _gap_run += 1
                    if _gap_run > gap_tol:
                        in_spring = False
                        end_depth = valid_depth[i]
                        # 只有长度超过一定阈值的才认为是弹簧段
                        if end_depth - start_depth > min_segment_length:
                            spring_segments.append((start_depth, end_depth))
                        _gap_run = 0
        
        # 处理最后一个弹簧段
        if in_spring and start_depth is not None:
            end_depth = valid_depth[-1]
            if end_depth - start_depth > min_segment_length:
                spring_segments.append((start_depth, end_depth))

        logger.debug(f"  合并后候选段: {[(round(s,1), round(e,1)) for s, e in spring_segments]}")
        
        # 进一步验证每个候选弹簧段
        validated_segments = []
        for start_depth, end_depth in spring_segments:
            seg_mask = (valid_depth >= start_depth) & (valid_depth <= end_depth)
            seg_range = _lr[seg_mask]
            seg_fluct = fluct[seg_mask]

            if len(seg_range) >= 5:
                # 验证1：波动频率（波动点占比）
                jump_freq = float(np.sum(seg_fluct)) / len(seg_fluct)

                # 验证2：幅度一致性（局部极差变异系数）
                jump_amps = seg_range[seg_fluct]
                if len(jump_amps) >= 3:
                    amp_mean = np.mean(jump_amps)
                    amp_std = np.std(jump_amps)
                    amp_consistency = amp_std / amp_mean if amp_mean > 0 else 1.0
                else:
                    amp_consistency = 1.0

                # 验证3：与GR的相关性（密度局部极差 vs GR局部极差）
                # 【2026-10-08 修正】整段相关系数会被段内真实薄层（密度/GR同步
                # 变化）拉高而误杀整段。改为逐 2m 窗口统计"GR强同步窗口占比"，
                # 只有占比 < 50%（大多数窗口与GR无关）才判为弹簧段。
                # 同时修正原 bug：无 GR 曲线时 gr_corr=1.0 恒不过验证。
                gr_ok = True
                frac_gr_sync = 0.0
                if gr_range is not None:
                    gr_seg_range = gr_range[seg_mask]
                    sync_win = max(int(2 / dz), 20)
                    _nw = 0
                    _nsync = 0
                    _step = max(sync_win // 2, 1)
                    for k in range(0, len(seg_range) - sync_win + 1, _step):
                        _dr = seg_range[k:k + sync_win]
                        _gv = gr_seg_range[k:k + sync_win]
                        if (len(_dr) >= 8 and np.std(_dr) > 0 and
                                np.std(_gv) > 0):
                            _nw += 1
                            if abs(np.corrcoef(_dr, _gv)[0, 1]) > 0.5:
                                _nsync += 1
                    frac_gr_sync = (_nsync / _nw) if _nw > 0 else 0.0
                    gr_ok = frac_gr_sync < 0.5

                # 综合验证：波动频率高，幅度一致，且大多数窗口与GR无关
                _reason = []
                if not (jump_freq > 0.2):
                    _reason.append(f"freq={jump_freq:.2f}")
                if not (amp_consistency < 0.6):
                    _reason.append(f"ampCV={amp_consistency:.2f}")
                if not gr_ok:
                    _reason.append(f"grSync={frac_gr_sync:.2f}")
                if jump_freq > 0.2 and amp_consistency < 0.6 and gr_ok:
                    validated_segments.append((start_depth, end_depth))
                    logger.info(f"  验证通过弹簧段: {start_depth:.1f}m - {end_depth:.1f}m")
                    logger.info(f"    波动频率: {jump_freq:.2f}, 幅度一致性: {amp_consistency:.2f}, "
                                f"GR强同步窗口占比: {frac_gr_sync:.2f}")
                else:
                    logger.info(f"  候选段未通过验证 {start_depth:.1f}-{end_depth:.1f}m: "
                                f"{', '.join(_reason)}")
        
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

        # 【2026-10-07 修正】剔除 NaN/inf 再插值。
        # 实测 BET-1 在套管段（6344-6447 ft）密度/浅阻为 -999.25 哨兵值，
        # 样条要求 x/y 都不含 NaN，否则报
        # "Array must not contain infs or nans" 而整段校正失败。
        _xy = combined[['MD', curve_name]].apply(
            pd.to_numeric, errors='coerce').dropna()
        _xy = _xy[np.isfinite(_xy['MD']) & np.isfinite(_xy[curve_name])]
        # 至少需要 4 个有效点才能定三次样条（k=3）
        if len(_xy) < 4 or _xy[curve_name].nunique() < 2:
            logger.debug('弹簧段 %s 有效锚点不足（%d），跳过样条校正',
                         curve_name, len(_xy))
            return data

        x = _xy['MD'].values
        y = _xy[curve_name].values

        # 创建样条函数
        spline = make_interp_spline(x, y, k=3)

        # 对弹簧段内的深度进行插值（超出锚点范围的深度不外推）
        spring_depths = spring_data['MD'].values
        _sd = spring_depths[np.isfinite(spring_depths)]
        _in_range = _sd[( _sd >= x.min()) & (_sd <= x.max())]
        if len(_in_range) == 0:
            return data
        corrected_values = spline(_in_range)

        # 更新数据（只写回插值范围内的点）
        result = data.copy()
        _idx = result.index[(result['MD'].isin(_in_range)) & mask]
        result.loc[_idx, curve_name] = spline(
            result.loc[_idx, 'MD'].values)
        
        return result

    def _trend_correct(self, data, curve_name, start_depth, end_depth,
                       window_m=3.0, residual_ratio=3.0, drho_max=0.15):
        """
        【2026-10-08 新增】趋势分解校正（螺旋井眼弹簧段物理校正，默认方法）。

        原理：弹簧状锯齿是叠加在真实地层趋势上的高频周期振荡。用大步长
        Savitzky-Golay 提取整条曲线的地层趋势 baseline，弹簧段内残差
        （raw - trend）的标准差显著大于段外噪声水平时，判定为螺旋振荡，
        将段内值替换为趋势值——**保留段内真实地层变化，仅扣除周期振荡**。

        优于 spline：
          - spline 用段外锚点重建整段，段内真实薄层/岩性变化会被抹掉；
          - trend 基于段内数据本身，薄层信号仍保留在趋势里。
        优于固定窗口 moving_average/median：
          - 窗口与螺旋周期无关，会残留或过度平滑；
          - 本方法按螺旋周期（window_m）自适应。

        对电阻率（MSFL/RD 等）：在 log10 域做分解（电阻率动态范围大），
        避免线性平滑把高阻薄层的锯齿放大/失真。

        参数:
            data: 测井数据DataFrame
            curve_name: 要校正的曲线名称
            start_depth: 弹簧段起始深度（米）
            end_depth: 弹簧段结束深度（米）
            window_m: 趋势提取窗口（米），约 1~2 倍螺旋周期
            residual_ratio: 段内/段外残差标准差比阈值，超过则替换为趋势
            drho_max: DRHO 绝对值阈值，超过视为校正不可靠（仅用于标记）

        返回:
            (result, corrected_flag, unreliable_flag)
              result: 校正后的数据
              corrected_flag: 是否发生了替换校正
              unreliable_flag: 该段是否 DRHO 超限（校正不可靠）
        """
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        n_seg = int(mask.sum())
        if n_seg < 5:
            return data, False, False
        seg_idx = np.where(mask.values)[0]

        # 采样间隔
        md = pd.to_numeric(data['MD'], errors='coerce').values
        dz_med = np.nanmedian(np.abs(np.diff(md)))
        if not np.isfinite(dz_med) or dz_med <= 0:
            dz_med = 0.1

        raw = pd.to_numeric(data[curve_name], errors='coerce').values
        finite = np.isfinite(raw)

        # ---- 电阻率类曲线：log10 域分解 ----
        use_log = False
        curve_upper = curve_name.upper()
        if any(k in curve_upper for k in ('MSFL', 'RMSL', 'MCFL', 'RD', 'RS',
                                          'LLS', 'LLD', 'LLD9', 'RES', 'RT')):
            _pos = finite & (raw > 0)
            if np.sum(_pos) >= 10:
                use_log = True
                y = np.full_like(raw, np.nan, dtype=float)
                y[_pos] = np.log10(raw[_pos])
            else:
                y = raw.copy()
        else:
            y = raw.copy()

        _yf = np.isfinite(y)
        if np.sum(_yf) < 10:
            return data, False, False

        # ---- 估计段内螺旋主周期（用于趋势提取窗口）----
        # 【2026-10-08 修正】趋势窗口须与螺旋周期匹配：窗口=整数个周期时，
        # 滚动均值对正弦振荡完全平均（残差=原始振荡），且薄层（宽度≈周期）
        # 仍保留在趋势里。Savitzky-Golay 会把振荡吸进 baseline（残差变小，
        # 判据不触发），故弃用 SG，改用周期匹配的滚动均值。
        # 注意：窗口**不能**强制奇数化——偶数窗口才能精确覆盖整数个
        # 周期（如 30 点=3.0m 周期），31 点窗口会残留 ~60% 振荡。
        seg_md = md[seg_idx]
        seg_y = y[seg_idx]
        T_est = window_m
        if len(seg_y) >= 30:
            # FFT 主频估计螺旋周期（对主振荡稳健，不受次波/噪声干扰）
            try:
                from numpy.fft import rfft, rfftfreq
                _y0 = np.nan_to_num(seg_y - np.nanmean(seg_y), nan=0.0)
                if np.std(_y0) > 0:
                    _x = np.arange(len(_y0))
                    _p = np.polyfit(_x, _y0, 1)   # 去线性趋势防泄漏
                    _y0 = _y0 - np.polyval(_p, _x)
                    _win = np.hanning(len(_y0))
                    _spec = np.abs(rfft(_y0 * _win))
                    _freqs = rfftfreq(len(_y0), d=dz_med)
                    _lo = 1.0 / (2.0 * window_m)   # 周期下限=2*窗口
                    _hi = 1.0 / 0.5                # 周期上限=0.5m
                    _valid = (_freqs > _lo) & (_freqs <= _hi)
                    if np.any(_valid):
                        _f0 = _freqs[_valid][np.argmax(_spec[_valid])]
                        _T = 1.0 / _f0
                        if np.isfinite(_T) and 0.5 <= _T <= 2.0 * window_m:
                            T_est = _T
            except Exception:
                pass

        n_win = max(int(round(T_est / dz_med)), 5)
        # 整数周期匹配：窗口覆盖的周期数接近整数时，用偶数窗口
        # （整数周期滚动均值对正弦严格归零；奇数窗口残留 ~60% 振荡）
        _Tpts = max(T_est / dz_med, 1.0)
        _nper = n_win / _Tpts
        if abs(_nper - round(_nper)) < 0.15 and n_win % 2 == 1:
            n_win -= 1
            if n_win < 5:
                n_win = 5
        n_win = min(n_win, 201)          # 上限防止过度平滑
        # 窗口不能超过有效点数
        n_valid = int(np.sum(_yf))
        if n_win > n_valid:
            n_win = n_valid - 1 if n_valid % 2 == 0 else n_valid
            if n_win < 5:
                n_win = 5

        trend = np.full_like(y, np.nan, dtype=float)
        try:
            # 滚动均值：窗口=整数螺旋周期时对正弦完全平均
            _tm = pd.Series(y).rolling(n_win, center=True,
                                       min_periods=1).mean().values
            trend[:] = np.where(np.isfinite(_tm), _tm,
                                np.nanmedian(y[_yf]))
        except Exception:
            trend[_yf] = y[_yf]

        # ---- 残差：段内 vs 段外噪声水平 ----
        resid = np.where(_yf, y - trend, np.nan)
        seg_resid = resid[seg_idx]
        seg_resid = seg_resid[np.isfinite(seg_resid)]
        if len(seg_resid) < 3:
            return data, False, False
        # 段外相邻区（段前后各 window_m 范围）
        out_idx = np.where(~mask.values)[0]
        out_resid = resid[out_idx]
        out_resid = out_resid[np.isfinite(out_resid)]
        if len(out_resid) < 5:
            # 段外不足则用整段残差
            out_resid = resid[np.isfinite(resid)]

        std_seg = np.std(seg_resid)
        std_out = np.median(np.abs(out_resid - np.median(out_resid))) * 1.4826
        if std_out <= 0:
            std_out = np.std(out_resid)
        if std_out <= 1e-12:
            std_out = 1e-12

        # ---- 判定并替换 ----
        result = data.copy()
        corrected = False
        unreliable = False
        ratio = std_seg / std_out
        # 绝对峰-峰判据：段内残差峰-峰超过最小幅度即替换
        # （防止段外噪声过低时 ratio 判据不触发）
        seg_amp = float(np.ptp(seg_resid)) if len(seg_resid) > 1 else 0.0
        min_amp = 0.05 if not use_log else 0.2

        # DRHO 超限检查（密度类曲线）
        if any(k in curve_upper for k in ('RHOB', 'ZDEN', 'DEN', 'RHOZ')):
            _drho_col = next((c for c in ('DRHO', 'DRHOC', 'DELTA_RHO',
                                          'DEN_COR', 'CORR', 'DENCOR')
                              if c in data.columns), None)
            if _drho_col is not None:
                drho_seg = pd.to_numeric(data.loc[mask, _drho_col],
                                         errors='coerce').values
                drho_seg = drho_seg[np.isfinite(drho_seg)]
                if len(drho_seg) > 0 and np.max(np.abs(drho_seg)) > drho_max:
                    unreliable = True

        if ratio > residual_ratio or seg_amp > min_amp or unreliable:
            corrected = True
            # 残差钳制替换：仅替换 |残差| 超过噪声门限的"振荡点"为趋势值。
            # 段内薄层等真实地层变化处残差小 → 自动保留原值（不抹真实信息）。
            _idx = seg_idx[np.isfinite(resid[seg_idx])]
            _r = resid[_idx]
            thr_r = min(max(3.0 * std_out, 0.015 if not use_log else 0.06),
                        0.05 if not use_log else 0.15)
            _sel = np.abs(_r) > thr_r
            _replace = _idx[_sel]
            if len(_replace) > 0:
                if use_log:
                    result.loc[data.index[_replace], curve_name] = 10.0 ** trend[_replace]
                else:
                    result.loc[data.index[_replace], curve_name] = trend[_replace]
            logger.info(
                f"  [trend] {curve_name} {start_depth:.1f}-{end_depth:.1f}m: "
                f"段内残差σ={std_seg:.4f}, 段外σ={std_out:.4f}, 比={ratio:.2f}, "
                f"峰-峰={seg_amp:.4f}, 钳制门限={thr_r:.4f}"
                f"{' [DRHO超限,不可靠]' if unreliable else ''}, 替换 {len(_replace)}/{len(_idx)} 点")

        return result, corrected, unreliable

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
    
    def correct_spring_segments(self, data, curve_names=None, depth_range=None,
                                method='trend', spring_segments=None,
                                trend_params=None):
        """
        校正弹簧段（使用预检测的弹簧段）
        参数:
            data: 测井数据DataFrame
            curve_names: 要校正的曲线名称列表，默认为['MSFL', 'RHOB']
            depth_range: 要校正的深度范围 (start_depth, end_depth)
            method: 校正方法 'trend', 'spline', 'moving_average', 'median'
            spring_segments: 预检测的弹簧段列表，[(start_depth, end_depth), ...]
            trend_params: trend 方法参数 dict {window_m, residual_ratio, drho_max}
        
        返回:
            校正后的数据
        """
        if curve_names is None:
            curve_names = ['MSFL', 'RHOB']
        if trend_params is None:
            trend_params = {'window_m': 3.0, 'residual_ratio': 3.0,
                            'drho_max': 0.15}
        
        result = data.copy()
        
        # 【2026-10-08】弹簧段校正质量标记列：
        #   0 = 正常（非弹簧段或无需校正）
        #   1 = 弹簧段，已趋势校正（扣除了螺旋周期振荡）
        #   2 = 弹簧段，DRHO 超限，校正不可靠（该段密度不可用于孔隙度等计算）
        if 'SPRING_QC' not in result.columns:
            result['SPRING_QC'] = 0
        
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
                if method == 'trend':
                    result, _corr, _unrel = self._trend_correct(
                        result, curve_name, start_depth, end_depth,
                        window_m=trend_params.get('window_m', 3.0),
                        residual_ratio=trend_params.get('residual_ratio', 3.0),
                        drho_max=trend_params.get('drho_max', 0.15))
                    if _corr:
                        _qc_mask = ((result['MD'] >= start_depth) &
                                    (result['MD'] <= end_depth) &
                                    (result['SPRING_QC'] == 0))
                        result.loc[_qc_mask, 'SPRING_QC'] = 1
                    if _unrel:
                        _qc_mask2 = ((result['MD'] >= start_depth) &
                                     (result['MD'] <= end_depth))
                        result.loc[_qc_mask2, 'SPRING_QC'] = 2
                elif method == 'spline':
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
    
    def run_spring_correction(self, data, curve_names=None, detect_curve='RHOB',
                              depth_range=None, method='trend',
                              sensitivity=3.0, detect_opts=None,
                              trend_params=None):
        """
        运行弹簧段校正
        如果没有检测到弹簧段，返回None，不进行校正
        
        参数:
            data: 测井数据DataFrame
            curve_names: 要校正的曲线名称列表，默认为['MSFL', 'RHOB']
            detect_curve: 用于检测弹簧段的曲线（默认RHOB密度曲线）
            depth_range: 要校正的深度范围
            method: 校正方法（默认 'trend' 趋势分解校正）
            sensitivity: 检测灵敏度（倍数）
            detect_opts: 检测开关 dict {use_drho, use_caliper, use_cross_curve,
                                        use_gr_independent}
            trend_params: trend 方法参数 dict {window_m, residual_ratio, drho_max}
        """
        try:
            logger.info("开始弹簧段校正")
            
            if curve_names is None:
                curve_names = ['MSFL', 'RHOB']
            if detect_opts is None:
                detect_opts = {'use_drho': True, 'use_caliper': True,
                               'use_cross_curve': True,
                               'use_gr_independent': True}
            if trend_params is None:
                trend_params = {'window_m': 3.0, 'residual_ratio': 3.0,
                                'drho_max': 0.15}
            
            # 只使用detect_curve检测弹簧段
            all_segments = {}
            if detect_curve in data.columns:
                segments = self.detect_spring_segments(
                    data, detect_curve, sensitivity=sensitivity,
                    use_drho=detect_opts.get('use_drho', True),
                    use_caliper=detect_opts.get('use_caliper', True),
                    use_cross_curve=detect_opts.get('use_cross_curve', True),
                    use_gr_independent=detect_opts.get('use_gr_independent', True))
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
            corrected_data = self.correct_spring_segments(
                data, curve_names, depth_range, method,
                all_segments[detect_curve], trend_params=trend_params)
            
            logger.info("弹簧段校正完成")
            
            return {
                'data': corrected_data,
                'spring_segments': all_segments,
                'depth_range': depth_range,
                'corrected_curves': curve_names,
                'detect_curve': detect_curve,
                'method': method,
                'sensitivity': sensitivity
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
        # 【2026-10-10】出图格式（数据选择界面选定）: all/composite/crossplot
        # run_well_log_workflow 通过模块全局 _PLOT_MODE 传入
        try:
            _pm = globals().get('_PLOT_MODE', 'all')
            # 检查数据是否加载
            if self.data_processor.data is None or len(self.data_processor.data) == 0:
                if file_path and Path(file_path).exists():
                    # 【2026-10-10 quick look】有明确文件路径时直接加载，
                    # 避免无交互/后台环境下文件选择对话框阻塞
                    logger.info("使用指定文件: %s", file_path)
                    data = self.data_loader.load_data(file_path)
                    if data is None:
                        logger.error("指定文件加载失败: %s", file_path)
                        print(f"\n文件加载失败，程序终止: {file_path}")
                        return None
                else:
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
                # 中子曲线可靠性（2026-10-08 专项检查，供岩性识别跳过CNL判据）
                _nphi_reliable = loader_qc.get('neutron_reliable', None)
                if _nphi_reliable is not None:
                    self.results['neutron_reliable'] = bool(_nphi_reliable)
                    self.results['neutron_quality'] = loader_qc.get('neutron_quality', '未评价')
                
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
            # 必须覆盖 LAS 原始列名（ZDEN/CNCF/DTC/RD/RMSL），否则 BET-1 这类
            # 用 LAS 原名的井只能数出 1 条曲线，会被误判为"曲线不足"而跳过全流程
            valid_curves = ['GR', 'GRX', 'RT', 'LLD', 'ILD', 'R90', 'RD', 'RMSL',
                            'MSFL', 'DEN', 'RHOB', 'ZDEN',
                            'NPHI', 'CNL', 'CNCF', 'DT', 'DTCO', 'DTC', 'AC',
                            'PE', 'PEF']
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
            
            # ========== 1.5 套管段检测（必须早于弹簧段校正与岩性识别）==========
            # 【2026-10-07】为什么要提前：
            #  1) 弹簧段检测基于密度曲线的周期性跳变，而**套管内密度是泥浆**
            #     （实测 BET-1 6344-6447 ft 密度 1.41-2.22、PE 5-17），
            #     在套管段检测弹簧段必然误报，且样条插值会因 -999.25 哨兵值报错；
            #  2) 岩性识别与井级剖面预判都必须在排除套管段之后做，否则
            #     整套管段会被判成灰岩（此前 446 点误判）。
            _casing_mask = None
            _profile_type = 'mixed'
            _well_for_casing = getattr(self, 'well_name', 'Unknown')
            try:
                # 【2026-10-15】加载阶段 QC 前已检测过套管并缓存于 attrs，
                # 这里直接复用，避免重复检测且保证与 QC 剔除口径一致。
                _cm_cached = None
                _ci_cached = None
                try:
                    _cm_cached = self.data_processor.data.attrs.get('casing_mask_early')
                    _ci_cached = self.data_processor.data.attrs.get('casing_info_early')
                except Exception:
                    pass
                if (_cm_cached is not None
                        and len(_cm_cached) == len(self.data_processor.data)):
                    _cm = _cm_cached
                    _cinfo = _ci_cached
                    # 注意：本函数作用域内 np 为局部导入（后文），此处不可用 np，
                    # 用 Series/ndarray 自带的 .sum() 统计套管点数
                    logger.info("复用加载阶段缓存的套管掩码（QC前检测，套管/水泥%d点）",
                                int(_cm.sum()))
                else:
                    # 【2026-10-15】水泥带延伸的日志单位标签需要 depth_unit
                    _unit_cu = self.config.get('depth_unit', 'ft') \
                        if isinstance(getattr(self, 'config', None), dict) else 'ft'
                    _cm, _cinfo = detect_casing_interval(
                        self.data_processor.data, _well_for_casing,
                        depth_unit=_unit_cu)
                _casing_mask = _cm
                self.results['casing_info'] = _cinfo
                # 剖面预判要排除套管段，否则泥浆响应会把结论带偏
                _d2 = (self.data_processor.data.loc[~_cm.values].copy()
                       if _casing_mask is not None
                       else self.data_processor.data)
                _ptype, _pinfo = detect_well_profile_type(_d2, _well_for_casing)
                _profile_type = _ptype
                self.results['profile_type_detected'] = _pinfo
            except Exception as _e:
                logger.warning("套管/剖面预判失败（不影响主流程）: %s", _e)

            # 2. 弹簧段校正（基于密度变化检测，校正时同时校正RHOB和MSFL）
            # 【2026-10-27 R28 用户定案】解释截止值分井配置：0.06 等默认值是
            # 巴西海上深水经验知识，不作所有井统一要求——每口井可在
            # <井名>info.json「解释截止值」组覆盖（人工填非空值即生效）。
            try:
                cutoffs = load_interpretation_cutoffs(
                    str(well_output_dir), str(getattr(self, 'well_name', '')))
            except Exception as _ce:
                logger.warning("解释截止值加载回退默认: %s", _ce)
                cutoffs = dict(DEFAULT_CUTOFFS)
            set_active_cutoffs(cutoffs)
            _rules_well = build_interpretation_rules(cutoffs)
            logger.info("Step 2: Spring segment correction")

            # 检测时只用密度曲线，但校正时同时校正密度和电阻率曲线
            # 曲线名需覆盖 LAS 原始名：密度 ZDEN/RHOB/DEN，电阻率 RMSL/MSFL/RD
            detect_curve = next((c for c in ('RHOB', 'ZDEN', 'DEN', 'RHOZ')
                                 if c in self.data_processor.data.columns), None)
            correct_curves = [c for c in ('RHOB', 'ZDEN', 'DEN', 'RHOZ',
                                          'MSFL', 'RMSL', 'RD', 'RS')
                              if c in self.data_processor.data.columns]
            available_correct_curves = correct_curves

            # 【2026-10-26 R25 用户反馈】弹簧段自动检测会把岩性边界引起的密度
            # 跳变误报为弹簧段并施加校正，造成密度不合理尖峰（3-SPS-111D
            # 实测误报 10 段/替换 255 点；用户确认该井无弹簧段）→ 分井禁用
            # 表，如需恢复把井名移出 _SPRING_SKIP_WELLS 即可。
            _SPRING_SKIP_WELLS = {'3-SPS-111D'}
            if str(getattr(self, 'well_name', 'Unknown')).strip().upper() \
                    in _SPRING_SKIP_WELLS:
                logger.info("弹簧段校正: 井 %s 在分井禁用表中, 跳过检测与校正"
                            "（用户确认无弹簧段）",
                            getattr(self, 'well_name', 'Unknown'))
            elif detect_curve in self.data_processor.data.columns:
                # 【2026-10-07】套管段不参与弹簧段**检测** —— 套管内密度是
                # 泥浆而非岩石，据此检测必然误报。
                # 但**校正结果要合并回完整数据**（不能只保留剔除套管的子集），
                # 否则套管行会从数据里消失，深度轴不连续，图上无法显示
                # "套管段"这一重要信息。
                if _casing_mask is not None and _casing_mask.any():
                    # 用 NaN 屏蔽套管段的检测（detect_spring_segments 会跳过 NaN），
                    # 行数保持不变，校正后可整表写回。
                    # 注意：本方法内没有 numpy 的局部导入，这里用 pandas API。
                    _spring_input = self.data_processor.data.copy()
                    _cvals = pd.Series(_casing_mask, dtype=bool).values
                    if detect_curve in _spring_input.columns:
                        _spring_input.loc[_cvals, detect_curve] = float('nan')
                    logger.info("弹簧段检测已屏蔽套管段 %d 点",
                                int(pd.Series(_cvals).sum()))
                else:
                    _spring_input = self.data_processor.data.copy()
                spring_results = self.spring_corrector.run_spring_correction(
                    _spring_input,
                    curve_names=available_correct_curves,
                    detect_curve=detect_curve,
                    depth_range=None,
                    method=self.config.get('spring_correction', {}).get('method', 'trend')
                        if self.config else 'trend',
                    sensitivity=self.config.get('spring_correction', {}).get('sensitivity', 3.0)
                        if self.config else 3.0,
                    detect_opts=self.config.get('spring_correction', {}).get('detect', {})
                        if self.config else {},
                    trend_params=self.config.get('spring_correction', {}).get('trend', {})
                        if self.config else {}
                )
                if spring_results:
                    self.results['spring_correction'] = spring_results
                    # 保留VALID_CURVES_COUNT列
                    corrected_data = spring_results['data']
                    if 'VALID_CURVES_COUNT' in self.results['processed_data'].columns:
                        corrected_data['VALID_CURVES_COUNT'] = self.results['processed_data']['VALID_CURVES_COUNT']
                    # 【2026-10-07】弹簧段校正的数据行数与原数据一致（套管段用 NaN 屏蔽
                    # 检测而非删除行），因此套管掩码可直接沿用。
                    # 仍做一次长度校验兜底，防止将来有人改成删除行。
                    if _casing_mask is not None and \
                            len(_casing_mask) != len(corrected_data):
                        logger.warning('弹簧段校正后行数(%d)与套管掩码(%d)不一致，'
                                       '按 MD 重新对齐',
                                       len(corrected_data), len(_casing_mask))
                        _src_md = 'MD' if 'MD' in self.data_processor.data.columns \
                            else 'DEPT'
                        _tgt_md = 'MD' if 'MD' in corrected_data.columns else 'DEPT'
                        if _src_md in self.data_processor.data.columns and \
                                _tgt_md in corrected_data.columns:
                            _cmap = pd.Series(
                                pd.Series(_casing_mask, dtype=bool).values,
                                index=pd.Index(pd.to_numeric(
                                    self.data_processor.data[_src_md],
                                    errors='coerce').round(2).values))
                            _cmap = _cmap[~_cmap.index.duplicated(keep='first')]
                            _casing_mask = _cmap.reindex(pd.Index(
                                pd.to_numeric(corrected_data[_tgt_md],
                                              errors='coerce').round(2).values)
                            ).fillna(False).values.astype(bool)
                        self.results['casing_info']['casing_mask'] = _casing_mask
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
                    # 候选名需覆盖 LAS 原始名（ZDEN/CNCF/DTC/RD/RMSL/CALX…）
                    valid_curves = ['GR', 'SP', 'LLS', 'CAL', 'CALX', 'CALY', 'PE', 'PEF',
                                    'MSFL', 'RMSL', 'RD', 'RS',
                                    'RT', 'LLD', 'ILD', 'R90',
                                    'DEN', 'RHOB', 'ZDEN',
                                    'NPHI', 'CNL', 'CNCF',
                                    'DT', 'DTCO', 'DTC', 'AC']
                    data = self.results['processed_data']
                    available_curves = [curve for curve in valid_curves if curve in data.columns]

                    if len(available_curves) > 2:
                        # ---------- 先跑多判据岩性识别器 ----------
                        # 作用：把煤、碳质泥岩、岩盐、火成岩等特殊岩性从
                        # 砂/泥/碳酸盐中单独识别出来，作为沉积相判别的**输入**。
                        # 若不先识别，煤层会被误判成湖相泥、碳质泥岩会被误判成
                        # 三角洲前缘。这里用的是"必要项 + 排除项 + M-of-K一致性项"
                        # 的多判据一致性判定，不是单条件触发。
                        #
                        # 【2026-10-07 新增两项前置处理】
                        #  1) **套管段检测**：套管内测井反映的是泥浆/钢材
                        #     （PE 可达 15-17、密度 1.4-2.1、中子 38-54），
                        #     不是岩石。原逻辑只看井径比，而套管段井径正常
                        #     （CALX/BIT≈1.03），导致 6307-6460 ft 整段被判"灰岩"。
                        #  2) **井级剖面预判**：全井 GR 起伏大、密度<2.65，
                        #     是砂泥岩剖面。剖面类型作为井级约束，抑制
                        #     "PE>3.5 就判碳酸盐"造成的灰岩碎段。
                        #     【注】套管检测与剖面预判已在 Step 1.5 完成
                        #     （必须早于弹簧段校正），此处直接复用结果。
                        try:
                            _unit = self.config.get('depth_unit', 'ft') \
                                if isinstance(getattr(self, 'config', None), dict) else 'ft'
                            # PE 质量：程序本来就有 check_pe_quality()，它检测
                            # PE 与密度/GR/RT 的一致性。**PE 与密度不匹配时
                            # 不能用 PE 判断岩性** —— 把该结论传给识别器，
                            # PE 相关的所有判据（must/deny/core）会被跳过。
                            _pe_ok = bool(
                                (getattr(self, 'pe_quality', None) or {})
                                .get('pe_reliable', True))
                            _pe_reason = (getattr(self, 'pe_quality', None) or {}) \
                                .get('reason', '')
                            if not _pe_ok:
                                logger.info("PE质量不合格，岩性识别将忽略全部PE判据: %s",
                                            _pe_reason)
                            # 中子质量：QC专项检查(2026-10-08)判定中子与密度/
                            # 声波孔隙度矛盾时，CNL相关判据(must/deny/core)跳过
                            _nphi_ok = bool(self.results.get('neutron_reliable', True))
                            if not _nphi_ok:
                                logger.info("中子曲线质量不合格(%s)，岩性识别将忽略全部CNL判据",
                                            self.results.get('neutron_quality', ''))
                            _rec = LithologyRecognizer(
                                data, depth_unit=_unit,
                                casing_mask=_casing_mask,
                                pe_reliable=_pe_ok,
                                neutron_reliable=_nphi_ok,
                                profile_type=_profile_type)
                            _lith = _rec.run()
                            data['LITHOLOGY_MC'] = _lith       # 多判据岩性
                            # 【一处一功能 2026-10-08】岩性判定统一归多判据识别器
                            # （must/core/deny），LITHOLOGY 旧列同步为同一结果，
                            # 下游（绘图/图例/交汇图/解释/矿物归类）全部一致；
                            # 旧 classify_lithology 链路不再覆盖（见该方法内守卫）。
                            data['LITHOLOGY'] = _lith
                            data['LITH_MC_CONF'] = _rec.confidence
                            data['LITH_MC_WHY'] = _rec.why
                            # 套管掩码落盘，供绘图/报告使用。
                            # 【注意】必须与 LITHOLOGY_MC 一起在
                            # run_facies_analysis **之前**写入 ——
                            # 后者会用 valid_data 的列重建 data，
                            # 晚写的列会被丢弃。
                            if _casing_mask is not None:
                                data['IS_CASING'] = pd.Series(
                                    _casing_mask, dtype=bool).values
                            self.results['lithology_recognizer'] = {
                                'summary': _rec.summary(),
                                'rules': _rec.rule_report(),
                                'profile_type': _profile_type,
                                'pe_reliable': _pe_ok,
                                'pe_reason': _pe_reason,
                                'casing': (self.results.get('casing_info', {}) or {}).get('summary', ''),
                                'profile_info': (self.results.get('profile_type_detected', {})
                                                 or {}).get('summary', ''),
                            }
                            _vc = pd.Series(_lith).value_counts().to_dict()
                            logger.info("多判据岩性识别完成(剖面=%s): %s",
                                        _profile_type, _vc)
                        except Exception as _e:
                            logger.warning("多判据岩性识别失败（不影响主流程）: %s", _e)

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

                        # 【2026-10-07 兜底】run_facies_analysis 内部会对
                        # valid_indices 子集做矿物/岩性计算再写回，某些路径下
                        # 自定义列（IS_CASING / LITHOLOGY_MC 等）会丢失。
                        # 这里按 MD 对齐后补写，保证下游绘图与报告能拿到。
                        _keep = {'IS_CASING': _casing_mask}
                        for _cn, _cv in _keep.items():
                            if _cv is None:
                                continue
                            if _cn in data.columns:
                                continue
                            try:
                                _src = pd.Series(_cv, dtype=bool,
                                                 index=self.data_processor.data.index)
                                _key_now = pd.to_numeric(
                                    data['MD'], errors='coerce').round(2)
                                _key_src = pd.to_numeric(
                                    self.data_processor.data['MD'],
                                    errors='coerce').round(2)
                                data[_cn] = _src.reindex(
                                    _key_now.values).fillna(False).values.astype(bool)
                            except Exception as _ce:
                                logger.debug('补写 %s 失败: %s', _cn, _ce)
                        
                       
                        
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
                        
                        # ========== 计算孔隙度 (φ) - 根据2012国标质量评价结果优先使用密度孔隙度 ==========
                        # 密度孔隙度是最可靠的孔隙度计算方法，但需先确认密度曲线质量合格
                        den_priority = self.results.get('density_porosity_priority', None)
                        # 如果未做2012评价，默认优先使用密度（向后兼容）
                        use_density = (den_priority is None) or (den_priority is True)
                        
                        # ========== 第一步：始终计算密度孔隙度 PORD（固定骨架2.65）==========
                        # PORD = (2.65 - RHOB) / (2.65 - 1.0)，岩石物理理论极限约0.5，上限设为0.4
                        POROSITY_MAX = 0.4  # 理论随机堆积球体极限约0.48，保守取0.4
                        # 密度/中子曲线别名识别(2026-10-08, BET-1): SLAM成果曲线
                        # ZDEN(g/cm3)为密度、CNCF(pu)为中子孔隙度, 等价于RHOB/NPHI
                        den_col = None
                        for _c in ('RHOB', 'ZDEN', 'DEN', 'RHOZ'):
                            if _c in data.columns:
                                den_col = _c
                                break
                        nphi_col = None
                        for _c in ('NPHI', 'CNCF', 'CNL'):
                            if _c in data.columns:
                                nphi_col = _c
                                break
                        if den_col:
                            data['PORD'] = (2.65 - data[den_col]) / (2.65 - 1.0)
                            data['PORD'] = data['PORD'].clip(0, POROSITY_MAX)
                            logger.info(f"PORD (密度孔隙度, 骨架2.65, 源曲线{den_col}) 已计算，范围: {data['PORD'].min():.3f}-{data['PORD'].max():.3f}")

                        if den_col and use_density:
                            if is_sand_shale_profile:
                                # 砂泥岩剖面：直接使用密度孔隙度 PORD，骨架固定2.65
                                data['PHI'] = data['PORD'].copy()
                                logger.info(f"砂泥岩剖面 → 使用PORD (密度孔隙度, 骨架2.65), "
                                          f"范围: {data['PHI'].min():.3f}-{data['PHI'].max():.3f}")
                            else:
                                # 碳酸盐岩剖面：变骨架密度计算孔隙度，上限0.4
                                matrix_densities = {
                                    '砂岩': 2.65, 'sandstone': 2.65,
                                    '灰岩': 2.71, 'limestone': 2.71,
                                    '白云岩': 2.87, 'dolomite': 2.87,
                                    '碳酸盐岩': 2.71,
                                    '泥岩': 2.55, 'shale': 2.55,
                                    '硬石膏': 2.98, 'anhydrite': 2.98
                                }
                                fluid_density = 1.0
                                
                                def calculate_phi(row):
                                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                                    rhob = row.get(den_col, 2.65)
                                    if lithology in matrix_densities:
                                        matrix_density = matrix_densities[lithology]
                                    else:
                                        pe_val = row.get('PE', row.get('PEF', 3.0))
                                        if pe_val > 4.5:
                                            matrix_density = 2.71
                                        elif pe_val > 3.5:
                                            matrix_density = 2.87
                                        elif rhob < 2.68:
                                            matrix_density = 2.65
                                        elif rhob < 2.80:
                                            matrix_density = 2.71
                                        else:
                                            matrix_density = 2.87
                                    phi = (matrix_density - rhob) / (matrix_density - fluid_density)
                                    return max(0, min(POROSITY_MAX, phi))
                                
                                data['PHI'] = data.apply(calculate_phi, axis=1)
                                logger.info("碳酸盐岩剖面 → 使用密度孔隙度（变骨架, 上限0.4）")
                        elif den_col and nphi_col:
                            # 密度中子交汇计算孔隙度，上限0.4
                            if is_sand_shale_profile:
                                # 砂泥岩剖面：密度中子交汇也以PORD为主
                                data['PHI'] = data['PORD'].copy()
                                logger.info("砂泥岩剖面(无密度优先) → 使用PORD")
                            else:
                                matrix_densities = {
                                    '砂岩': 2.65, 'sandstone': 2.65,
                                    '灰岩': 2.71, 'limestone': 2.71,
                                    '白云岩': 2.87, 'dolomite': 2.87,
                                    '碳酸盐岩': 2.71,
                                    '泥岩': 2.55, 'shale': 2.55,
                                    '硬石膏': 2.98, 'anhydrite': 2.98
                                }
                                fluid_density = 1.0
                                
                                def calculate_phi_dn(row):
                                    rhob = row.get(den_col, 2.65)
                                    nphi = row.get(nphi_col, 0.15)
                                    if nphi > 1:
                                        nphi = nphi / 100.0
                                    lithology = row.get('LITHOLOGY', row.get('LITHOLOGY_EN', '其他'))
                                    if lithology in matrix_densities:
                                        matrix_density = matrix_densities[lithology]
                                    else:
                                        pe_val = row.get('PE', row.get('PEF', 3.0))
                                        if pe_val > 4.5:
                                            matrix_density = 2.71
                                        elif pe_val > 3.5:
                                            matrix_density = 2.87
                                        elif rhob < 2.68:
                                            matrix_density = 2.65
                                        elif rhob < 2.80:
                                            matrix_density = 2.71
                                        else:
                                            matrix_density = 2.87
                                    phi_den = (matrix_density - rhob) / (matrix_density - fluid_density)
                                    phi_cnl = nphi
                                    phi = (phi_den + phi_cnl) / 2.0
                                    return max(0, min(POROSITY_MAX, phi))
                                
                                data['PHI'] = data.apply(calculate_phi_dn, axis=1)
                                logger.info("碳酸盐岩剖面 → 使用密度中子交汇（上限0.4）")
                        elif 'POR' in data.columns:
                            # 成果孔隙度列(2026-10-08, BET-1): 单位感知 —— %单位
                            # (max>1.5)先/100转小数, 再截到上限0.4
                            data['PHI'] = pd.to_numeric(data['POR'], errors='coerce')
                            if data['PHI'].max() > 1.5:
                                data['PHI'] = data['PHI'] / 100.0
                                logger.info("POR孔隙度为%单位，已/100转小数")
                            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
                            logger.info("使用POR孔隙度（上限0.4）")
                        elif any(nmr_col in data.columns for nmr_col in ['MPHE', 'PHIE', 'MRP']):
                            for nmr_col in ['MPHE', 'PHIE', 'MRP']:
                                if nmr_col in data.columns:
                                    data['PHI'] = data[nmr_col].clip(0, POROSITY_MAX)
                                    logger.info(f"使用核磁孔隙度 {nmr_col}（上限0.4）")
                                    break
                        elif nphi_col:
                            data['PHI'] = data[nphi_col]
                            if data['PHI'].max() > 1:
                                data['PHI'] = data['PHI'] / 100.0
                            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
                            logger.info(f"使用中子孔隙度 {nphi_col}（上限0.4）")
                        elif 'DT' in data.columns or 'DTCO' in data.columns or 'DTC' in data.columns:
                            dt_col = 'DT' if 'DT' in data.columns else ('DTC' if 'DTC' in data.columns else 'DTCO')
                            data['PHI'] = (data[dt_col] - 55.5) / (189 - 55.5)
                            data['PHI'] = data['PHI'].clip(0, POROSITY_MAX)
                            logger.info("使用声波计算孔隙度（上限0.4）")
                        else:
                            data['PHI'] = 0.2
                            if 'PORD' not in data.columns:
                                data['PORD'] = 0.2
                            logger.info("使用默认孔隙度0.2")
                        
                        # ========== 核磁有效孔隙度优先（2026-10-16 用户要求） ==========
                        # 曲线描述同时含核磁词汇（MR/NMR/nuclear magnetic/核磁）
                        # 与有效孔隙度（如 MPHE: MR effective porosity）时，孔隙度
                        # 以核磁有效孔隙度为准——核磁直接测量值优于密度骨架模型
                        # 推断；PHI 随后驱动 Sw/PHI_DISP，综合图第5道孔隙度曲线
                        # 与 profile 道自动与核磁有效孔隙度一致
                        _nmr_phi = _find_nmr_effective_porosity_col(
                            data, getattr(getattr(self, 'data_loader', None),
                                          'curve_descriptions', {}) or {})
                        if _nmr_phi:
                            _raw_nmr = pd.to_numeric(data[_nmr_phi], errors='coerce')
                            if _raw_nmr.max() > 1.5:  # % 单位转小数
                                _raw_nmr = _raw_nmr / 100.0
                                logger.info("核磁有效孔隙度 %s 为%%单位，已/100转小数",
                                            _nmr_phi)
                            data['PHI'] = _raw_nmr.clip(0, POROSITY_MAX)
                            logger.info("孔隙度以核磁有效孔隙度为准: PHI ← %s（覆盖密度计算值，上限0.4）",
                                        _nmr_phi)

                        # 顶部/底部无效段：无有效中子/密度/声波曲线 → PHI/PORD 置 NaN
                        if '_POROSITY_VALID' in data.columns:
                            invalid_mask = ~data['_POROSITY_VALID']
                            for col in ['PHI', 'PORD', 'PHIE']:
                                if col in data.columns:
                                    data.loc[invalid_mask, col] = float('nan')
                            if invalid_mask.any():
                                logger.info(f"孔隙度无效段: {invalid_mask.sum()} 点 PHI/PORD 已置为 NaN")

                        # ========== 元素矿物精化（2026-10-16 用户要求） ==========
                        # 元素含量第一位：有效段保持元素矿物比例并按 (1-φ)
                        # 归一化闭合 ΣV_mineral+φ=1；无效元素段泥质用 KTH/GR
                        # 回归关联计算，剩余体积按已识别岩性分配（总体闭合）
                        if any(str(c).upper().startswith('VOL_')
                               for c in data.columns):
                            data = refine_element_mineral_volumes(data)
                        
                        # 计算Sw（含水饱和度）
                        # 【2026-10-20 重构】自算优先（反算为准口径）：
                        #   ① 已有 Sw 且非退化（非常数）→ 采用；
                        #   ② 否则调 calculate_saturation 统一自算（自动Rw水层
                        #      反算 + RT列回填，唯一实现入口）——矿物分析阶段
                        #      PHI 未就绪时其 Sw 缺失/退化为常数 1.0，此处孔隙
                        #      度(PHI←核磁)已就绪，必须重算（3-SPS-111D 实测：
                        #      全井 Sw 恒 1 → 0 个油气结论）；
                        #   ③ 自算仍无有效 Sw → 回退 LAS SW 列 → 兜底 1.0。
                        def _sw_effective(_s):
                            _v = pd.to_numeric(pd.Series(_s), errors='coerce').dropna()
                            return len(_v) > 0 and _v.nunique() > 1

                        _sw_ok = (_sw_effective(data['Sw'])
                                  if 'Sw' in data.columns else False)
                        if _sw_ok:
                            logger.info(f"Sw已存在（来自calculate_saturation），范围: {data['Sw'].min():.3f}-{data['Sw'].max():.3f}，跳过重算")
                        else:
                            if 'Sw' in data.columns:
                                logger.info("已有Sw为退化常数（矿物分析阶段PHI未就绪产物），重算")
                            try:
                                _ma = getattr(getattr(self, 'facies_analyzer', None),
                                              'mineral_analyzer', None)
                                if _ma is not None:
                                    data = _ma.calculate_saturation(data)
                                else:
                                    logger.warning("未找到 MineralAnalyzer，Sw 走回退链")
                            except Exception as _e_sw:
                                logger.error("主流程 Sw 自算失败: %s", _e_sw)
                            _sw_ok2 = (_sw_effective(data['Sw'])
                                       if 'Sw' in data.columns else False)
                            if not _sw_ok2:
                                if 'SW' in data.columns:
                                    data['Sw'] = data['SW']
                                    data['Sw'] = data['Sw'].clip(0, 1)
                                    logger.info(f"自算Sw仍缺，回退原始SW列，Sw范围: {data['Sw'].min():.3f}-{data['Sw'].max():.3f}")
                                else:
                                    data['Sw'] = 1.0
                                    logger.warning("自算Sw仍缺且无SW列，Sw兜底=1.0")
                        
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
                            # 电阻率: 优先 RT > RD > LLD > RDEEP > AT90 > ILD（跳过全零列）
                            rt_col = select_resistivity_column(
                                data, candidates=['RT', 'RD', 'LLD', 'RDEEP', 'AT90', 'ILD', 'RLA5'])
                            if rt_col is None:
                                rt_col = 'RT'
                            
                            # 泥质含量: 优先 VSH > VSH_GR，否则从GR计算
                            vsh_col = None
                            for candidate in ['VSH', 'VSH_GR', 'SH']:
                                if candidate in data.columns:
                                    vsh_col = candidate
                                    break
                            if vsh_col is None and 'GR' in data.columns:
                                # 从自然伽马计算泥质含量: VSH = (GR - GRmin) / (GRmax - GRmin)
                                gr_min = data['GR'].min()
                                gr_max = data['GR'].max()
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
                                
                                # 有效曲线不足3条的井段不解释
                                valid_count = row.get('VALID_CURVES_COUNT', 0)
                                if valid_count < 3:
                                    data.at[idx, 'INTERPRETATION'] = 'Undefined'
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
                                _cut_por = cutoffs.get('por_hc')
                                min_porosity = (_cut_por if _cut_por is not None else
                                                (0.06 if lithology in carbonate_lithologies else 0.08))
                                
                                reasons, phi_val, vsh_val, gr_val = _reservoir_filter_reasons(row, min_porosity)
                                
                                if reasons:
                                    # 【R30 用户定案】非储层=纯岩性概念；储层岩性
                                    # 但低于截止值(POR<下限/VSH/GR 门槛)=不解释
                                    # (TIGHT)：不成层、孔隙不归0——截止值就是这个
                                    # 意思。≥下限出不来油气也不是水层才是干层(DRY)
                                    _lith_bad = any(str(_r0).startswith('岩性=')
                                                    for _r0 in reasons)
                                    data.at[idx, 'INTERPRETATION'] = (
                                        'NonReservoir' if _lith_bad else 'TIGHT')
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
                                    # 干层首先是储层：统一储层验证（一处一功能）
                                    if not _is_dry_reservoir_point(phi_val, vsh_val, gr_val, lithology, min_porosity):
                                        conclusion_en = 'TIGHT'
                                        logger.debug(
                                            f"深度 {row.get('MD', idx):.1f}m: DRY→TIGHT (不满足储层条件)"
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
                                    elif param == 'RT':
                                        # 从有效深电阻率列映射（BET-1: RD；跳过全零列）
                                        _rt_src = select_resistivity_column(data)
                                        if _rt_src:
                                            data['RT'] = data[_rt_src]
                                        else:
                                            data[param] = 0
                                    elif param == 'POR' and 'PHI' in data.columns:
                                        data['POR'] = data['PHI']
                                    else:
                                        data[param] = 0
                            
                            target_values = data[core_params].values 
                            
                            for idx in range(len(data)):
                                row = data.iloc[idx]
                                
                                # 有效曲线不足3条的井段不解释
                                valid_count = row.get('VALID_CURVES_COUNT', 0)
                                if valid_count < 3:
                                    data.at[idx, 'INTERPRETATION'] = 'Undefined'
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
                                _cut_por = cutoffs.get('por_hc')
                                min_porosity = (_cut_por if _cut_por is not None else
                                                (0.06 if lithology in carbonate_lithologies else 0.08))
                                
                                reasons, phi_val, vsh_val, gr_val = _reservoir_filter_reasons(row, min_porosity)
                                
                                if reasons:
                                    # 【R30 用户定案】非储层=纯岩性概念；储层岩性
                                    # 但低于截止值=不解释(TIGHT)：不成层、孔隙不归0
                                    _lith_bad = any(str(_r0).startswith('岩性=')
                                                    for _r0 in reasons)
                                    _rj = 'NonReservoir' if _lith_bad else 'TIGHT'
                                    data.at[idx, 'INTERPRETATION'] = _rj
                                    data.at[idx, 'INTERPRETATION_SCORE'] = 0.0
                                    data.at[idx, 'DISTANCE'] = 999.0
                                    data.at[idx, 'HIT_RATE'] = 0.0
                                    data.at[idx, 'DIRECTION_SCORE'] = 0.0
                                    data.at[idx, 'BETTER_COUNT'] = 0
                                    results.append({
                                        'MD': row['MD'],
                                        'ITP': _rj
                                    })
                                    continue
                                
                                # ========== 图版判别（must/core/deny 规则优先，归一化距离兜底） ==========
                                # 用户图版已表为 INTERPRETATION_RULES（模块级唯一实现）：
                                #   must=特征条件 / core=核心计算模块量化证据(M-of-K) / deny=否决条件
                                similarity = {}
                                rule_based = False
                                sw_v = row.get('Sw', row.get('SW', np.nan))
                                try:
                                    sw_v = float(sw_v)
                                except (TypeError, ValueError):
                                    sw_v = np.nan
                                if np.isfinite(sw_v) and sw_v > 1.5:
                                    sw_v = sw_v / 100.0  # 百分数Sw容错
                                rt_v = row.get('RT', np.nan)
                                try:
                                    rt_v = float(rt_v)
                                except (TypeError, ValueError):
                                    rt_v = np.nan
                                if np.isfinite(rt_v) and rt_v <= 0:
                                    rt_v = np.nan

                                _mcd = match_interpretation_rules(sw_v, phi_val, rt_v,
                                                                  rules=_rules_well)
                                if _mcd is not None:
                                    result, _score, _why = _mcd
                                    rule_based = True
                                    logger.debug("解释规则命中 %s@%.1f: %s", result, row['MD'], _why)

                                if not rule_based:
                                    # 归一化欧氏距离（RT用对数域，各维量纲一致）
                                    # Sw<0.5偏向油气候选，否则偏向水/干候选
                                    if np.isfinite(sw_v) and sw_v < 0.5:
                                        cand_types = ('GAS', 'OIL')
                                    else:
                                        cand_types = ('WATER', 'DRY')
                                    vsh_c = vsh_val if np.isfinite(vsh_val) else 0.0
                                    vsh_c = min(max(vsh_c, 0.0), 1.0)

                                    def _sim_norm(rt_t):
                                        if not (np.isfinite(sw_v) and np.isfinite(rt_v)
                                                and np.isfinite(phi_val)):
                                            return np.nan
                                        d = np.sqrt(
                                            ((sw_v - 0.5) / 0.5) ** 2 +
                                            ((vsh_c - 0.3) / 0.7) ** 2 +
                                            ((np.log10(max(rt_v, 0.2)) - np.log10(rt_t)) / 1.5) ** 2 +
                                            ((min(max(phi_val, 0.0), 0.4) * 100.0 - 15.0) / 15.0) ** 2)
                                        return 1.0 / (1.0 + d)

                                    similarity = {ft: _sim_norm(templates[ft][2])
                                                  for ft in cand_types}
                                    valid_types = {k: v for k, v in similarity.items()
                                                   if np.isfinite(v) and v >= similarity_threshold}
                                    if valid_types:
                                        result = max(valid_types.items(), key=lambda x: x[1])[0]
                                    else:
                                        result = "Undefined"
                                
                                # ========== 干层储层验证（简化路径，统一实现） ==========
                                # 干层首先是储层！非储层不能判为干层
                                if result == 'DRY':
                                    if not _is_dry_reservoir_point(phi_val, vsh_val, gr_val, lithology, min_porosity):
                                        result = 'TIGHT'
                                
                                # 直接使用英文存储，不映射到中文
                                data.at[idx, 'INTERPRETATION'] = result
                                data.at[idx, 'INTERPRETATION_SCORE'] = (
                                    1.0 if rule_based else similarity.get(result, 0))
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

                        # 【2026-10-09】层内重力分异整饰：同一储层内油气水按密度
                        # 分异，自上而下 气→油→水 单调叠置。逐点独立判定产生的
                        # 油水交错（"一会油一会水"）在此按流动单元统一重整
                        # （一处一功能：enforce_fluid_segregation）。
                        enforce_fluid_segregation(data)

                        # 【2026-10-08】非储层不再清 PHI/PORD —— 孔隙度是
                        # calculate_porosity 的计算成果，全井有效（泥岩也有总孔隙度）；
                        # 解释成果统计的储层过滤由解释流程自身负责（一处一功能）。
                        # 此前清空导致孔隙度道只剩储层点（BET-1 仅 1117/10901），
                        # 第6道孔隙度曲线几乎不可见。

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

                # ========== 套管段统一标记（2026-10-07）==========
                # 老链路（LITHOLOGY，来自 classify_lithology 的逐点 apply）
                # 不认识套管，会把套管段判成砂岩/泥岩。
                # 在保存前按 IS_CASING 统一改写为 'casing'，
                # 保证两条岩性链路（LITHOLOGY / LITHOLOGY_MC）口径一致，
                # 且下游绘图能正确显示"套管"图例。
                _cmask = pd_data.get('IS_CASING')
                if _cmask is not None and _cmask.any():
                    _n_cs = int(pd.Series(_cmask).sum())
                    _both = ['LITHOLOGY', 'LITHOLOGY_MC']
                    for _lc in _both:
                        if _lc in pd_data.columns:
                            pd_data.loc[_cmask, _lc] = 'casing'
                    # 沉积相同样不能给套管段
                    if 'FACIES' in pd_data.columns:
                        pd_data.loc[_cmask, 'FACIES'] = 'casing'
                    # 【2026-10-08】解释结论同样不能给套管/人工井底水泥段：
                    # 专家指出套管内与水泥固结段不属于裸眼解释对象，
                    # 此前套管点残留 NonReservoir 结论并进入解释道/交会图。
                    for _ic in ('INTERPRETATION', 'ITP', 'INTERPRETATION_SCORE',
                                'INTERPRETATION_WHY'):
                        if _ic in pd_data.columns:
                            pd_data.loc[_cmask, _ic] = None
                    logger.info('套管段已在两条岩性链路中统一标记为 casing（%d 点）'
                                '，解释结论已清空', _n_cs)

                # ========== 井底无数据点清理（2026-10-15）==========
                # 井底段有效曲线数<3（如 3-SPS-111D 6951.8-6987.9m 共304点）
                # 属无数据点，不属于任何岩性/储层：旧逻辑标 'Unknown' 会以
                # Undefined 名义进入统计与解释道误导用户 → 各成果列清空，
                # 绘图端岩性道/解释道对 NaN 行本就跳过（留白）。
                if 'VALID_CURVES_COUNT' in pd_data.columns:
                    _nodata = pd.Series(
                        pd_data['VALID_CURVES_COUNT'] < 3).fillna(False)
                    if _nodata.any():
                        _n_nd = int(_nodata.sum())
                        for _lc in ('LITHOLOGY', 'LITHOLOGY_MC'):
                            if _lc in pd_data.columns:
                                pd_data.loc[_nodata.values, _lc] = None
                        if 'FACIES' in pd_data.columns:
                            pd_data.loc[_nodata.values, 'FACIES'] = None
                        for _ic in ('INTERPRETATION', 'ITP',
                                    'INTERPRETATION_SCORE',
                                    'INTERPRETATION_WHY'):
                            if _ic in pd_data.columns:
                                pd_data.loc[_nodata.values, _ic] = None
                        logger.info('井底无数据段（有效曲线数<3）%d 点已清空'
                                    '岩性/沉积相/解释结论', _n_nd)

                # ========== 特殊岩性孔隙度/饱和度归0 → 仅显示用列 ==========
                # 第6道孔隙度/饱和度是"真实储层孔隙度"语义：**特殊岩性**
                #（膏/盐/煤/火山岩/黄铁矿等）无储层概念 → 显示置0（曲线贴
                # 左边框连续，不像置NaN那样断开）。
                # 【2026-10-19 用户定案】归0范围收窄为"特殊岩性"：用户明确
                # "石膏是特殊岩性归0可以，但灰岩和白云岩不是特殊岩性不能
                # 归0"——碳酸盐岩是正常储层岩性，即使结论 NonReservoir/
                # DRY 也保留真实孔隙度与饱和度（与"按岩性归零、不按结论
                # 归零"的总口径一致：储层岩性即使非有效储层也保留真实
                # PHI/Sw）。套管/无数据段一并归0（非岩石）。
                # 【硬约束】归0只写入显示专用列 PHI_DISP/SW_DISP，仅供建模
                # 第5道(profile孔隙度留白)与第6道(孔隙度/饱和度曲线)绘制使用；
                # **原始 PHI/PHIE/Sw 计算列保持不动**——解释图版/矿物模型/
                # 统计/报告/试油修正等一切判断逻辑必须读原始计算值，禁止用
                # 显示值反向参与判断。
                # 中子/密度/声波等原始曲线不受任何限制，保持真实读数。
                _SPECIAL_ZERO_LITHS = (
                    'coal', 'anhydrite', 'gypsum', 'salt', 'halite', 'evaporite',
                    'volcanic', 'basement', 'tuff', 'basalt', 'granite',
                    'pyrite', 'casing',
                    # 【2026-10-20 用户定案 3-SPS-111D】泥岩是非储层，需要归0：
                    # 此前 2026-10-19 收窄时只剔除了灰岩/白云岩，泥岩漏加，
                    # 97 个泥岩点 PHI_DISP 全部保留真实值（用户指出未归0）
                    'shale', 'mudstone', 'claystone',
                    '煤层', '膏盐', '盐岩', '硬石膏', '火山岩', '花岗岩',
                    '黄铁矿', '石膏', '套管', '泥岩', '页岩')
                _lith_s = (pd_data['LITHOLOGY'].astype(str).str.lower().str.strip()
                           if 'LITHOLOGY' in pd_data.columns
                           else pd.Series('', index=pd_data.index))
                _zero_m = _lith_s.isin(_SPECIAL_ZERO_LITHS)
                _phi_src = ('PHI' if 'PHI' in pd_data.columns
                            else ('PHIE' if 'PHIE' in pd_data.columns else None))
                if _phi_src:
                    _v = pd.to_numeric(pd_data[_phi_src], errors='coerce')
                    pd_data['PHI_DISP'] = _v.where(~_zero_m, 0.0)
                if 'Sw' in pd_data.columns:
                    _v = pd.to_numeric(pd_data['Sw'], errors='coerce')
                    pd_data['SW_DISP'] = _v.where(~_zero_m, 0.0)
                logger.info('特殊岩性显示归0: %d点(灰岩/白云岩等正常岩性不归0，'
                            '保留真实PHI/Sw) → PHI_DISP/SW_DISP=0；'
                            '原始 PHI/PHIE/Sw 未改动，仅供解释判断使用',
                            int(_zero_m.sum()))

                if 'INTERPRETATION' in pd_data.columns:
                    vc = pd_data['INTERPRETATION'].value_counts().to_dict()
                    logger.info(f"保存前 INTERPRETATION分布: {vc}")
                else:
                    logger.warning("保存前 INTERPRETATION列不存在!")

                # ========== 矿物体积计算（保存前，2026-10-08 移位）==========
                # 此前在 CSV 保存之后才计算，导致交付 CSV 缺 VClay/VQuartz 等
                # 矿物列而绘图内存里有 —— 同一成果两套数据。现移到保存前，
                # CSV/LAS/绘图共用同一份矿物列（一处一功能）。
                if self.results['processed_data'] is not None:
                    self.results['processed_data'] = calculate_mineral_volumes(
                        self.results['processed_data'])
                    # ========== 矿物含量+孔隙度闭合=1（2026-10-19 用户定案）==========
                    # 孔隙度=PHI_DISP（核磁优先、非储层归0），缺口用主要岩性
                    # 主矿物补齐 → ΣVOL_*+PHI_DISP=1（套管/无岩性行除外）
                    self.results['processed_data'] = close_mineral_balance(
                        self.results['processed_data'])

            
            # 将输出目录保存到结果中，供可视化模块使用
            self.results['output_dir'] = str(well_output_dir)
            
            # 将LAS文件信息保存到结果中，供可视化模块使用
            las_info = {
                'well': self.data_loader.get_las_well_info() or {},
                'parameter': self.data_loader.get_las_parameter_info() or {}
            }
            # 【2026-10-15】深度单位透传：LAS加载时解析的 depth_unit 写在
            # data_loader 上（不在 get_las_*_info() 返回值里），此处重建
            # las_info 会丢失该键——报告逐层单位退回"MD中位>10000判英尺井"
            # 兜底
            _du = getattr(self.data_loader, 'depth_unit', None)
            if _du:
                las_info['depth_unit'] = str(_du)
            self.results['las_info'] = las_info
            
            # 加载气测数据（可选）
            gas_data = None
            logger.info("Step 5: 气测数据加载（可选，取消跳过）")
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
                    # 【2026-10-08】气测曲线平滑（用户要求：全烃曲线有台阶，
                    # 平滑成正常连续曲线）。气测采样远稀于测井网格(0.25ft)，
                    # nearest 对齐后同一样本被重复赋给多个测井点 → 阶梯状。
                    # 对数值型气测列做中心滑动平均消除台阶；窗口按气测采样
                    # 间隔自适应（≈2倍采样间隔）。缺测(NaN)不参与、保持缺测。
                    # 平滑发生在全部解释步骤之后、仅供建模绘制使用，
                    # 不会反哺任何解释判断。
                    try:
                        _mstep = float(np.median(np.diff(main_sorted['MD'].values))) \
                            if len(main_sorted) > 1 else 0.25
                        _gstep = float(np.median(np.diff(
                            gas_sorted['MD'].dropna().values))) \
                            if len(gas_sorted) > 1 else _mstep
                        _win = int(max(5, round(2.0 * _gstep / max(_mstep, 1e-6))))
                        _win += (_win + 1) % 2  # 取奇数窗
                        _gnum = [c for c in gas_data.select_dtypes(
                            include=[np.number]).columns if c != 'MD']
                        if _gnum and len(gas_data) >= _win:
                            gas_data[_gnum] = (
                                gas_data[_gnum]
                                .rolling(window=_win, center=True, min_periods=1)
                                .mean())
                            logger.info('气测曲线已平滑(中心滑动平均,窗口%d点'
                                        '≈气测采样%.2f×2): %s',
                                        _win, _gstep, _gnum)
                    except Exception as _gse:
                        logger.warning('气测曲线平滑失败（不影响主流程）: %s', _gse)
                    self.results['gas_data'] = gas_data
                else:
                    logger.warning("主数据中缺少MD列，无法对齐气测数据")
                    gas_data = None
            else:
                gas_data = None

            # 【2026-10-08】矿物体积计算已移至 CSV 保存前（一处一功能），
            # CSV/LAS/绘图共用同一份矿物列，此处不再重复计算。

            # 【2026-10-21】REG 法综合气层指示：RTI+NDI+GSI→CGI
            try:
                if 'processed_data' in self.results and self.results['processed_data'] is not None:
                    _pd = self.results['processed_data']
                    # 【2026-10-26 R25】不能用 `or` 兜底: DataFrame 的真值
                    # 判定歧义(ValueError: truth value ambiguous), 曾致 REG
                    # 法静默失败、CSV 恒缺 RTI/NDI/GSI/CGI。改显式 None 判断。
                    _gas_rg = self.results.get('gas_data')
                    if _gas_rg is None:
                        _gas_rg = gas_data
                    _pd = calculate_reg_indicators(_pd, gas_data=_gas_rg)
                    self.results['processed_data'] = _pd
                    logger.info("REG 法: RTI/NDI/GSI/CGI 四条列已写入 processed_data")
            except Exception as _re:
                logger.warning("REG 法计算失败（不影响主流程）: %s", _re)

            # 【2026-10-26 R24】盖层(盐岩/硬石膏)下气测异常储层:
            # WATER→油气补偿(用户要求, 详见 rejudge_hc_below_seal)
            try:
                if 'processed_data' in self.results \
                        and self.results['processed_data'] is not None:
                    _gas_rh = self.results.get('gas_data')
                    if _gas_rh is None:
                        _gas_rh = gas_data
                    _pd_rh, _nre = rejudge_hc_below_seal(
                        self.results['processed_data'],
                        gas_data=_gas_rh,
                        por_hc=cutoffs.get('por_hc'))
                    self.results['processed_data'] = _pd_rh
                    if _nre:
                        logger.info("盖层下油气补偿: %d 点已改判", _nre)
            except Exception as _rh:
                logger.warning("盖层下油气补偿判定失败（不影响主流程）: %s", _rh)
                logger.warning('盖层下油气补偿 traceback:\n%s',
                               __import__('traceback').format_exc())

            # 【2026-10-27 R26】盐下气层 REG 证据复核：无 REG 气层异常的
            # GAS 层降为 OIL（用户定案"盐岩下解释成气层没有依据，REG 方法
            # 没有明显异常特征"；按层核算 CGI/RTI/NDI/GSI，逐层留痕）
            try:
                if 'processed_data' in self.results \
                        and self.results['processed_data'] is not None:
                    _pd_gr, _n_gr = rejudge_gas_by_reg_below_seal(
                        self.results['processed_data'])
                    if _n_gr:
                        self.results['processed_data'] = _pd_gr
            except Exception as _gr:
                logger.warning("盐下气层REG复核失败（不影响主流程）: %s", _gr)


            # 【2026-10-27 R27】按孔隙度截止值分层解释：储层点聚合成层、
            # 层内多数票整层统一、薄层按流体分布规律并入邻层
            # （用户"解释要按孔隙度截止值分层"）
            try:
                if 'processed_data' in self.results \
                        and self.results['processed_data'] is not None:
                    _pd_ly, _n_ly = layered_interpretation_by_cutoff(
                        self.results['processed_data'])
                    if _n_ly:
                        self.results['processed_data'] = _pd_ly
            except Exception as _ly:
                logger.warning("按层解释整合失败（不影响主流程）: %s", _ly)
                logger.warning('按层解释 traceback:\n%s',
                               __import__('traceback').format_exc())

            # 【2026-10-26 R25】CSV/LAS 导出移到 REG 与盖层下油气补偿改判之后：
            # 此前 CSV 在 Step 4 保存、REG 列与 rejudge 改判发生在其后，
            # 导致 CSV 缺 REG 列且 354 点 WATER→OIL 改判不落盘
            # （CSV/LAS/绘图必须共用同一份成果——一处一功能口径）。
            processed_csv_path = well_output_dir / f"{well_name}_processed.csv"
            self.results['processed_data'].to_csv(processed_csv_path, index=False, encoding='utf-8')
            print(f"处理后数据已保存到: {processed_csv_path}")
            logger.info(f"处理后数据CSV已保存: {processed_csv_path}")

            # ========== 同时导出带套管头的 LAS（2026-10-07）==========
            # 为什么重要：SLAM 输出的 LAS 头段**没有套管字段**（实测 BET-1
            # 只有 WELL/STRT/STOP 等 15 个字段，无 CSIZ/CDF/CADT），
            # 导致后续处理只能靠曲线反演猜套管段。
            # 完善的 LAS 应该在 ~PARAMETER 段写入 CSIZ/CDF/CADT，
            # 这样套管信息随文件流转，换井/换软件都可靠。
            try:
                _las_ok = export_las_with_casing(
                    self.results['processed_data'],
                    well_output_dir / f"{well_name}_interpreted.LAS",
                    casing_info=self.results.get('casing_info', {}),
                    well_name=well_name,
                    depth_unit=self.config.get('depth_unit', 'ft')
                    if isinstance(getattr(self, 'config', None), dict) else 'ft')
                if _las_ok:
                    logger.info('带套管头的 LAS 已导出: %s', _las_ok)
            except Exception as _le:
                logger.warning('导出带套管头的 LAS 失败（不影响 CSV）: %s', _le)

            # 5. 结果可视化（调用visualize_composite_log函数）- 图片将保存在同一目录下
            if self.config['visualization']:
                logger.info("Step 6: 结果可视化（出图格式=%s）", _pm)
                if 'processed_data' in self.results and self.results['processed_data'] is not None:
                    data = self.results['processed_data']
                    # 深度单位优先取 LAS 加载时解析的真实单位（data_loader.depth_unit），
                    # 其次 results['las_info']，最后才 config 兜底——原 config.get(...,'ft')
                    # 恒兜底'ft'，公制井交汇图 patch_depth_unit 把全局'm'覆盖为'ft'
                    _du = getattr(self.data_loader, 'depth_unit', None) \
                        or (self.results.get('las_info') or {}).get('depth_unit') \
                        or (self.config.get('depth_unit')
                            if isinstance(getattr(self, 'config', None), dict) else None) \
                        or 'ft'
                    # 综合图（plot_mode=all|composite）
                    # 【2026-10-14 用户定案】综合图选择出标准综合图（Composite Log
                    # Plot 版式 + 尾部footer + 单页PDF）。原2026-10-10"综合图按
                    # quick look 格式出图"的固化废除——quick look 格式仅由
                    # quicklook_well 第5步专用出图（带图版/图标/井信息补全），
                    # 本处 quicklook=True 曾致选综合图却出快速解释图、且因缺
                    # _enrich_well_info/collect_well_info/quicklook_config 而
                    # 表1/表2/logo 缺失。
                    if _pm in ('all', 'composite'):
                        # 【2026-10-15 用户定案】综合图走综合图绘制流程
                        # （logvis.visualize_composite_log，quicklook=False 固定）；
                        # 快速解释图走 visualize_quicklook_log（quicklook_well 第5步）。
                        viz_result = self.data_visualizer.visualize_composite_log(
                            data, self.results, gas_data=gas_data)
                        if viz_result:
                            self.results['visualization_results'] = viz_result
                    # 流体/岩性交会图（plot_mode=all|crossplot）
                    if _pm in ('all', 'crossplot'):
                        try:
                            from logvis import visualize_fluid
                            _xp = visualize_fluid(data, self.results, depth_unit=_du,
                                                  gas_data=gas_data)
                            if _xp:
                                # 【2026-10-14 只出一次 PDF】交汇图合并为单文件
                                # 多页 PDF，返回值为 [pdf路径]
                                _xp0 = _xp[0] if isinstance(_xp, (list, tuple)) else _xp
                                logger.info("交会图已保存: %s", _xp0)
                        except Exception as _ve:
                            logger.warning('交会图生成失败（不影响综合图）: %s', _ve)
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
        有效曲线：曲线值 > 0 且 非NaN
        
        参数:
            data: 测井数据DataFrame
            window_size: 滑动窗口大小（数据点数）
        
        返回:
            data: 添加了 VALID_CURVES_COUNT 列的DataFrame
        """
        # 同上：必须覆盖 LAS 原始列名（ZDEN/CNCF/DTC/RD/RMSL/CALX…）
        valid_curves = ['GR', 'GRX', 'GR_LAS', 'RT', 'RT_LAS', 'LLD', 'ILD', 'R90',
                        'RD', 'RS', 'RMSL', 'MSFL', 'LLS',
                        # 【2026-10-21 R18】HAL7506 等老井的阵列电阻率 RAL1-5
                        'RAL1', 'RAL2', 'RAL3', 'RAL4', 'RAL5',
                        'DEN', 'DEN_LAS', 'RHOB', 'ZDEN',
                        'NPHI', 'CNL', 'CNL_LAS', 'CNCF', 'CNC',
                        'DT', 'DTCO', 'DTC', 'AC', 'DTTC', 'DTTST', 'DTTXX',
                        'PE', 'PEF',
                        # 【2026-10-21 R18】井径：RP-13 的井径列名是 CAL_AVERAGE，
                        # 原名单只有 CAL/CALS/CALX/CALY → 井径这条有效曲线数不出来
                        'CAL', 'CALS', 'CALX', 'CALY', 'CALI',
                        'CAL_AVERAGE', 'CAL-AVG', 'CALAVG', 'CAL_MEAN',
                        'SP', 'BIT']
        valid_counts = []
        
        for i in range(len(data)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(data), i + window_size // 2)
            
            count = 0
            for curve in valid_curves:
                if curve in data.columns:
                    window_data = data[curve].iloc[start_idx:end_idx]
                    valid_ratio = (window_data > 0).sum() / len(window_data)
                    if valid_ratio > 0.3:
                        count += 1
            
            valid_counts.append(count)
        
        data['VALID_CURVES_COUNT'] = valid_counts
        return data

# ============================================================================
#  quick look 快速解释模块（2026-10-10 嵌入 logInt 的功能之一）
#  流程: 解析井文件夹下所有文件知识(测井LAS/地质MD/气测/PDF/试油表)
#        → logInt 主流程快速解释 → 知识入库 logKnow → 出快速解释图
#  快速解释图格式参照 BET-1_8.5IN_SLAM_Res_MD200_20261003.pdf
#        （图头左上 company.png / 右上 contractor.png，由 logvis 绘制）
#  用法:  python logInt.py --quicklook <井文件夹>
#        python logInt.py --quicklook          (弹对话框选择井文件夹)
# ============================================================================

# 气测文件名关键词（用于知识解析登记；实际加载由 logInt.load_gas_data 自动发现）
_GAS_FILE_KW = ('gas', 'gastotal', 'tgas', '气测', '录井气', 'welltest', 'well test',
                'dst', 'rop', '钻井参数', '钻时')

def _is_gas_file(p):
    """判断文件是否为气测/录井/测试类数据文件"""
    name = p.name.lower()
    if p.suffix.lower() not in ('.txt', '.csv', '.xls', '.xlsx', '.dat'):
        return False
    return any(k in name for k in _GAS_FILE_KW)

def _find_main_las(well_dir):
    """在井文件夹中寻找主测井 LAS 文件。

    策略: 根目录下的 .LAS 优先（邻井 LAS 通常位于 supportdata/help/LAS_邻井曲线
    子目录中，根目录是主井资料）; 若根目录没有 LAS，退化为全文件夹最大 .LAS。
    【2026-10-15】排除气测/录井 LAS（如 *_DDP_GasAv-prof.las）——此前按文件
    最大选取，3-SPS-111D 井气测 LAS 更大被误选为主文件，导致快速图只有
    SPP+气测曲线（无 GR/电阻率/密度，电阻率道与岩性道全空）。
    """
    from pathlib import Path as _P
    well_dir = _P(well_dir)

    # 【2026-10-15】气测 LAS 按文件名关键词排除（_is_gas_file 后缀白名单不含
    # .las，无法识别 *_DDP_GasAv-prof.las 这类气测 LAS）——3-SPS-111D 井气测
    # LAS 更大被误选为主文件，导致快速图只有 SPP+气测曲线（无 GR/电阻率）
    _gas_name_kw = ('gas', 'tgas', 'gastotal', '气测', '录井气')

    def _not_gas(p):
        if any(k in p.name.lower() for k in _gas_name_kw):
            return False
        try:
            return not _is_gas_file(p)
        except Exception:
            return True

    root_las = [p for p in well_dir.glob('*.[lL][aA][sS]') if _not_gas(p)]
    if root_las:
        root_las.sort(key=lambda x: x.stat().st_size, reverse=True)
        return root_las[0]
    all_las = [p for p in well_dir.rglob('*.[lL][aA][sS]') if _not_gas(p)]
    if not all_las:
        # 全部被判定为气测 → 退回不过滤，避免无主文件可用
        all_las = list(well_dir.rglob('*.[lL][aA][sS]'))
    if not all_las:
        return None
    all_las.sort(key=lambda x: x.stat().st_size, reverse=True)
    return all_las[0]

def _extract_md_knowledge(md_files, limit_chars=6000):
    """从井文件夹中的 .md 知识文件提取结构化知识（BET-1 模式下这些是
    已知识化的地质认识/分层/岩性/试油/气测分析文档）。"""
    parts = []
    for i, md in enumerate(md_files[:12]):
        try:
            text = md.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            try:
                text = md.read_text(encoding='gbk', errors='ignore')
            except Exception:
                continue
        text = text.strip()
        if not text:
            continue
        # frontmatter 摘除
        body = text
        if text.startswith('---'):
            _end = text.find('\n---', 4)
            if _end > 0:
                body = text[_end + 4:].strip()
        # 取标题（首行）与正文前若干字符
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        title = lines[0] if lines else md.stem
        excerpt = '\n'.join(lines[1:])[:limit_chars]
        parts.append(f"### 来源: {md.name}\n**{title}**\n{excerpt[:limit_chars]}")
    return '\n\n'.join(parts)

def _extract_pdf_knowledge(pdf_files, max_pages=3, limit_chars=4000):
    """用 PyMuPDF 提取 PDF（mud log/DWOP/钻井程序等）关键文本。"""
    parts = []
    try:
        import fitz
    except Exception:
        return ''
    for i, pdf in enumerate(pdf_files[:6]):
        try:
            doc = fitz.open(str(pdf))
            txt_parts = []
            for pi in range(min(max_pages, doc.page_count)):
                txt_parts.append(doc[pi].get_text() or '')
            doc.close()
            txt = '\n'.join(txt_parts).strip()
            if not txt:
                continue
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            title = lines[0] if lines else pdf.stem
            excerpt = '\n'.join(lines[1:])[:limit_chars]
            parts.append(f"### PDF来源: {pdf.name}\n**{title}**\n{excerpt}")
        except Exception as e:
            logger.warning("PDF 文本提取失败 %s: %s", pdf.name, e)
    return '\n\n'.join(parts)

def _extract_table_knowledge(xls_files):
    """登记井文件夹中的试油/测试表格文件名（内容解析由后续试油库负责）。"""
    if not xls_files:
        return ''
    names = '\n'.join(f"- {p.name}" for p in xls_files[:10])
    return f"### 井文件夹表格资料（试油/测试/成果表）\n{names}"

def _guess_region(well_dir, las_info=None):
    """从文件夹路径层级 + LAS Well 段推断国家/区块（硬约束优先: 国家目录路径）。"""
    from pathlib import Path as _P
    parts = list(_P(well_dir).parts)
    hints = []
    # 常见国家/区块目录名
    region_kw = {
        'Indo': ('印尼', 'Indonesia'), 'Indonesia': ('印尼', 'Indonesia'),
        'Venezuela': ('委内瑞拉', 'Venezuela'), 'Chad': ('乍得', 'Chad'),
        'Niger': ('尼日尔', 'Niger'), 'Niger2': ('尼日尔', 'Niger'),
        'Uzbekistan': ('乌兹别克', 'Uzbekistan'), 'UZ': ('乌兹别克', 'Uzbekistan'),
        'Turkmenistan': ('土库曼', 'Turkmenistan'), '土库曼': ('土库曼', 'Turkmenistan'),
        'Bangladesh': ('孟加拉', 'Bangladesh'), '孟加拉': ('孟加拉', 'Bangladesh'),
        'Brazil': ('巴西', 'Brazil'), '巴西': ('巴西', 'Brazil'),
        'Myanmar': ('缅甸', 'Myanmar'), '缅甸': ('缅甸', 'Myanmar'),
        'Iran': ('伊朗', 'Iran'), '伊拉克': ('伊拉克', 'Iraq'),
        'Suriname': ('苏里南', 'Suriname'), '苏里南': ('苏里南', 'Suriname'),
        'Canada': ('加拿大', 'Canada'), '刚果': ('刚果', 'Congo'),
        '中东': ('中东', 'MiddleEast'), '海外': ('海外', 'Overseas'),
    }
    for part in parts:
        for kw, (cn, en) in region_kw.items():
            if kw.lower() in part.lower():
                hints.append(f"{cn}({en})")
    region = '、'.join(dict.fromkeys(hints)) or ''
    # LAS Well 段补充井名/油田
    well_extra = ''
    if las_info:
        w = las_info.get('well') or {}
        if w.get('field'):
            well_extra = f" 油田: {w['field']}"
    return region, well_extra

def _kb_add_knowledge(well_name, knowledge_md, category='well_quicklook'):
    """把 quick look 知识摘要写入 logKnow 知识库（增量索引）。

    为避免 Windows 命令行长度限制（WinError 206），知识正文写入临时文件，
    由子进程读取后调用 logKnow.add_local_document。
    """
    try:
        import subprocess
        import tempfile
        _script = Path(os.path.abspath(__file__)).parent / 'logKnow.py'
        if not _script.exists():
            logger.warning("logKnow.py 未找到, 跳过知识入库: %s", _script)
            return False
        title = f"{well_name} quick look 快速解释知识摘要"
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False,
                                         encoding='utf-8') as _tf:
            _tf.write(knowledge_md)
            _tmp = _tf.name
        _py_code = (
            "import sys, pathlib; sys.path.insert(0, sys.argv[1]); "
            "import logKnow; kb = logKnow.WellLogKnowledgeBase(auto_scan=False); "
            "c = pathlib.Path(sys.argv[3]).read_text(encoding='utf-8'); "
            "kb.add_local_document(c, sys.argv[4], sys.argv[5]); "
            "pathlib.Path(sys.argv[3]).unlink(missing_ok=True)"
        )
        cmd = [sys.executable, '-c', _py_code,
               str(_script.parent), str(_script), _tmp, title, category]
        # 【2026-10-20 RASHIDPUR_13】知识入库改为后台 fire-and-forget：
        # 子进程加载 logKnow（嵌入模型/向量库）曾超 300s 超时——既阻塞
        # 快速解释出图交付 5 分钟、入库又实际失败。改为 Popen 后台执行
        # 不等待（临时文件由子进程用后即删）；子进程输出写入日志备查。
        try:
            _log_dir = _script.parent / 'logs'
            _log_dir.mkdir(exist_ok=True)
            _lf = open(_log_dir / 'logknow_quicklook.log', 'a', encoding='utf-8')
            _proc = subprocess.Popen(cmd, stdout=_lf, stderr=subprocess.STDOUT)
            logger.info("知识入库 logKnow 已后台执行(pid=%d): %s", _proc.pid, title)
        except Exception as _pe:
            logger.warning("知识入库后台启动失败(降级同步执行): %s", _pe)
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=600)
            try:
                Path(_tmp).unlink(missing_ok=True)
            except Exception:
                pass
            if res.returncode == 0:
                logger.info("知识已入库 logKnow: %s", title)
                return True
            logger.warning("logKnow add 返回非零: %s", res.stderr[-500:])
        return False
    except Exception as e:
        logger.warning("知识入库 logKnow 失败: %s", e)
        return False

def _find_well_logos(well_dir):
    """查找业主/承包商图标（随井的业主动态更换）。

    优先级（2026-10-10 用户定案）:
      1. F:\\360\\src 根目录下文件名含 company/contractor（或 cnpc/cnlc/业主/服务等）的图标
      2. symbol 目录默认 company.png / contractor.png
      3. 井文件夹（根目录/子目录）下同名图标
      4. 均无 → 从 mudlog/masterlog 图纸截取（本函数返回 None 交由上层截取；
         截取能力在 quicklook_well 中尝试）
    返回 (company_logo, contractor_logo) 绝对路径或 None。
    """
    from pathlib import Path as _P
    _src = _P(os.path.abspath(__file__)).parent
    _sym = _src / 'symbol'
    _default_c, _default_ct = _sym / 'company.png', _sym / 'contractor.png'
    _kw_c = ('company', 'cnpc', '业主', '甲方')
    _kw_ct = ('contractor', 'cnlc', '服务', '承包商', '乙方')

    def _first_match(dirs, is_c):
        _exact = ('company.png', 'company_logo.png') if is_c else \
                 ('contractor.png', 'contractor_logo.png')
        for d in dirs:
            if not d.exists():
                continue
            try:
                # 1) 精确名优先（避免 CNPC-logo.png 抢占 company.png）
                for _e in _exact:
                    _f = d / _e
                    if _f.exists():
                        return _f
                # 2) 关键词包含匹配
                for f in sorted(d.glob('*.png')):
                    _n = f.name.lower()
                    _kws = _kw_c if is_c else _kw_ct
                    if any(k in _n for k in _kws):
                        return f
            except Exception:
                continue
        return None

    # 1. src 根目录（最高优先, 业主更换时直接放新图标到 src）
    found_c = _first_match([_src], True)
    found_ct = _first_match([_src], False)
    # 2. symbol 目录
    if found_c is None:
        found_c = _first_match([_sym], True)
    if found_ct is None:
        found_ct = _first_match([_sym], False)
    # 3. 井文件夹
    well_dir = _P(well_dir)
    _wdirs = [well_dir] + sorted([p for p in well_dir.rglob('*') if p.is_dir()])[:30]
    if found_c is None:
        found_c = _first_match(_wdirs, True)
    if found_ct is None:
        found_ct = _first_match(_wdirs, False)
    return (str(found_c) if found_c else str(_default_c),
            str(found_ct) if found_ct else str(_default_ct))

def _enrich_well_info(results, text_parts):
    """从知识文件文本补充 las_info['well'] 缺失字段（公司/国家/区块/日期/套管等）。

    快速解释图图头（BOREHOLE/CASING RECORD）数据来源优先级:
      LAS ~W 段（well_name/field_name/start/stop）→ 知识文件文本 grep 补充 →
      仍缺则留空（如实展示, 不编造）。
    """
    try:
        import re as _re
    except Exception:
        return
    las_info = results.get('las_info') or {}
    if not isinstance(las_info, dict):
        return
    well = las_info.setdefault('well', {})
    param = las_info.setdefault('parameter', {})
    blob = '\n'.join(str(p) for p in (text_parts or []) if p)[:80000]
    if not blob:
        return

    _pats_w = {
        'company': [
            r'(?:Company|COMPANY|COMP\.)\s*[:=]\s*([A-Za-z][A-Za-z &.\-]{2,60})',
            r'(?:公司|业主)\s*[:：]\s*([\u4e00-\u9fa5A-Za-z0-9 &.\-]{2,40})',
        ],
        'country': [
            r'(?:Country|COUNTRY)\s*[:=]\s*([A-Za-z][A-Za-z ]{2,40})',
            r'(?:国家)\s*[:：]\s*([\u4e00-\u9fa5]{2,12})',
        ],
        'area': [
            r'(?:Area|AREA)\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9 ,.\-]{2,60})',
            r'(?:地区|区域)\s*[:：]\s*([\u4e00-\u9fa5A-Za-z0-9 ,.\-]{2,40})',
        ],
        'log_date': [
            r'(?:Log Date|DATE LOGGED|Date Logged)\s*[:=]\s*([0-9]{1,2}[-/][A-Za-z0-9\-/]{2,20})',
            r'(?:测井日期|测井时间)\s*[:：]\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})',
        ],
    }
    for _k, _pats in _pats_w.items():
        if well.get(_k):
            continue
        for _p in _pats:
            _m = _re.search(_p, blob)
            if _m and _m.group(1).strip():
                well[_k] = _m.group(1).strip()
                break

    # BOREHOLE/CASING RECORD（SIZE-FROM-TO 表格，参考 BET-1 PDF）
    # 【2026-10-10 修正】按尺寸(≥12=钻头/<12=套管)区分 BH/CS 是错的：
    # 8.5IN 是钻头（BOREHOLE）而非套管。改为优先按段落上下文
    # （BOREHOLE RECORD / CASING RECORD 分节）提取；无上下文时回退旧逻辑。
    _bh_rows = []
    _cs_rows = []
    _row_re = (r'\s*[-–]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:FT|ft|M|m)?'
               r'\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:FT|ft|M|m)?')
    _sz_re = r'(26|17\.5|12\.25|8\.5|12\s?1/4|8\s?1/2|20|13\.375|9\.625|13\s?3/8|9\s?5/8|7)\s*(?:IN|in|")'
    _bh_sec = _re.search(r'BOREHOLE\s+RECORD(.*?)(?:CASING\s+RECORD|\Z)', blob, _re.S | _re.I)
    if _bh_sec:
        for _m in _re.finditer(_sz_re + _row_re, _bh_sec.group(1)):
            _bh_rows.append((_m.group(1), _m.group(2), _m.group(3)))
    _cs_sec = _re.search(r'(?:^|\n)\s*#*\s*CASING\s+RECORD\s*\n(.*?)(?:LEGEND|\Z)', blob, _re.S | _re.I)
    if _cs_sec:
        for _m in _re.finditer(_sz_re + _row_re, _cs_sec.group(1)):
            _cs_rows.append((_m.group(1), _m.group(2), _m.group(3)))
    # 回退：无 BOREHOLE/CASING 段落上下文时按旧尺寸规则（≥12 钻头，<12 套管）
    if not _bh_rows and not _cs_rows:
        for _m in _re.finditer(_sz_re + _row_re, blob):
            _sz, _fr, _to = _m.group(1), _m.group(2), _m.group(3)
            if float(_sz) >= 12:
                _bh_rows.append((_sz, _fr, _to))
            else:
                _cs_rows.append((_sz, _fr, _to))
    if _bh_rows:
        param['borehole_record'] = '; '.join(
            f"{s}in {f}-{t}ft" for s, f, t in _bh_rows)
        param['borehole_record_rows'] = [
            {'size': s, 'from': f, 'to': t} for s, f, t in _bh_rows]
    if _cs_rows:
        param['casing_record'] = '; '.join(
            f"{s}in {f}-{t}ft" for s, f, t in _cs_rows)
        param['casing_record_rows'] = [
            {'size': s, 'from': f, 'to': t} for s, f, t in _cs_rows]

def _scan_to_quicklook_config(res):
    """qlscan 扫描结果 → logvis 可消费的 quicklook_config 结构。

    qlscan 一次扫描样本 PDF 得到 {fields/big_text/disclaimer/legend_items}，
    这里转换出图所需字段：免责声明、图例标题与文字项（颜色按关键词
    映射默认色，symbol 有图则用图、无则留空但文字保留）、比例尺。
    """
    import re as _re
    _cfg = {'format_name': 'quick look (OCR 扫描样本)', 'legend_items': []}
    _QL_SCAN_COLORS = {
        'oil': '#ffd400', 'gas': '#ff0000', 'water': '#00a2e8',
        'shale': '#7f7f7f', 'sand': '#ffedb0', 'sandstone': '#ffedb0',
        'limestone': '#00b050', 'coal': '#000000', 'tight': '#a5a5a5',
        'condensate': '#ff7f27', 'pay': '#ffff00', 'dolomite': '#00b0f0',
    }
    for _pg in res.get('scanned', []):
        if _pg.get('disclaimer'):
            _cfg['disclaimer'] = _pg['disclaimer']
        if _pg.get('legend_title'):
            _cfg['legend_title'] = _pg['legend_title']
        for _it in _pg.get('legend_items', []):
            _lbl = (_it.get('label') or '').strip()
            if not _lbl:
                continue
            _color = '#bdbdbd'
            for _k, _c in _QL_SCAN_COLORS.items():
                if _k in _lbl.lower():
                    _color = _c
                    break
            _cfg['legend_items'].append({'label': _lbl, 'color': _color})
        for _b in _pg.get('big_text', []):
            _m = _re.search(r'1\s*:\s*(\d{2,4})', _b.get('text', ''))
            if _m:
                _cfg['scale'] = f"1:{_m.group(1)}"
    return _cfg

def _load_quicklook_config(config_file):
    """加载甲方 quick look 出图格式配置。

    - .json 文件：直接读取（图版/甲方格式文件，如 qlpt.json）
    - 样本 PDF/图片：调 qlscan 一次 OCR 扫描 → 自动生成格式配置，
      并存为同名 _qlpt.json 供复用于图（保留 qlscan 独立扫描器形式，
      但作为 logInt 的选择数据时的格式文件入口）
    返回 quicklook_config dict；失败/未选择 → None（走图版默认）。
    """
    import json as _json
    _p = Path(config_file)
    if not _p.exists():
        return None
    if _p.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'):
        try:
            # 2026-10-26 并库: qlscan 已内联本文件
            print(f"  [qlscan] 样本格式一次扫描: {_p.name} ...")
            _res = scan_pdf(str(_p), pages=(1, 2, 3))
            _cfg = _scan_to_quicklook_config(_res)
            _out = _p.with_name(_p.stem + '_qlpt.json')
            _out.write_text(_json.dumps(_cfg, ensure_ascii=False, indent=2),
                            encoding='utf-8')
            print(f"  [qlscan] 已生成格式配置: {_out}（可复用于下次出图）")
            return _cfg
        except Exception as _e:  # noqa: BLE001
            logger.warning("qlscan 样本扫描失败, 用图版默认: %s", _e)
            return None
    try:
        return _json.loads(_p.read_text(encoding='utf-8'))
    except Exception as _e:  # noqa: BLE001
        logger.warning("quicklook 配置解析失败, 用图版默认: %s", _e)
        return None

# ============================================================================
# 井信息收集模块（【2026-10-14 用户定案】原 wellinfo.py 并入 logInt：
# 多源收集井信息 → <井名>info.json（井名与 info 间无连字符，如 BET-1info.json），
# 可视化时读取，人工可直接修改 json（非空值优先生效，空值回退自动提取）
# ============================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
井信息收集模块（并入 logInt，不依赖外部 wellinfo.py）
========================
【2026-10-14 用户定案】logvis 原 well_info 仅从 LAS 头提取、信息有限；本模块
从多源收集井信息组成 <井名>info.json（如 BET-1info.json），可视化时读取，
人工可直接修改 json（非空值优先生效，空值回退自动提取，都没有留空白）。

数据来源（按字段优先级）:
  1. <井名>info.json 非空值 —— 第二次处理直接调用（人工修改即生效）
  2. 井设置 well_settings.json（旧版, 存在则一次性迁移, 不再更新）
  3. 录井图 PDF（文件名含 mud log/mudlog/录井）: 开钻/完钻日期、Lat/Long、
     UTM X/Y、RKB-GL→地面海拔GL、RKB-MSL→补心海拔KB、钻机名、测井单位
  4. 地质设计（钻探程序中文翻译MD / Drilling Program / DWOP）:
     目的层、井型、设计井深、构造位置、UTM X/Y 备用
  5. LAS 头: COMPANY/FLD/AREA/DATE、ENGI→测井工程师、EKB/EGL/EDF 海拔、
     LATI/LONG、LOC 的 UTM 备用
  6. 都没有 → 留空白（不编造）

人员字段: 测井工程师 field_recorded_by 取 LAS ENGI；解释工程师
processed_by / 校正工程师 corrected_by / 测井监督 field_witnessed_by
为人工填写字段（json 留空, 表1留白）。

英文均为简写（LATI=纬度、RKB=补心转盘、GL=地面、MSL=平均海平面），
按关键词综合判断。
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 录井图 PDF 表头解析（HOLE DATA 块）
# ---------------------------------------------------------------------------
_MUDLOG_LABEL_KEYWORDS = (
    # 标签简写词表: 用于剔除误入数值尾部的标签词（如 "... S UTM X"）
    'utm', 'coordinates', 'coordinate', 'rkb-gl', 'rkb-msl', 'rkb', 'lat',
    'long', 'latitude', 'longitude', 'spud', 'spuded', 'td', 'date', 'rig',
    'logging', 'unit', 'company', 'well', 'field', 'region', 'elevation',
    'classification', 'geologist', 'engineers', 'loggers', 'surface',
    'bottom', 'hole', 'location', 'x', 'y',
)

def _mudlog_match_label(label):
    """录井图标签英文简写模糊匹配（英文均为简写需综合判断）→ 内部键或 None。

    同行多对 "label : value" 时下一段标签会串入上一段数值
    （如 "103° 34' 35.019\\" E Y"）: 全串不匹配时从尾部取 1~3 词重试，
    且要求前缀含数字（像数值）才允许尾部截匹配，防误配。
    """

    def _core(s):
        lbl = ' '.join(str(s).split()).lower().strip(':： ')
        if not lbl or 'spuded' in lbl:
            return None
        if 'rkb' in lbl and 'msl' in lbl:
            return 'elevation_kb'
        if 'rkb' in lbl and 'gl' in lbl:
            return 'elevation_gl'
        if re.search(r'\bspud\b', lbl) and 'date' in lbl:
            return 'spud_date'
        if re.search(r'\btd\b', lbl) and 'date' in lbl:
            return 'td_date'
        if re.search(r'\brig\b', lbl):
            return 'rig_name'
        if 'logging' in lbl and 'unit' in lbl:
            return 'logging_unit'
        if 'geologist' in lbl:
            return 'geologist'
        if 'engineer' in lbl:
            return 'engineers'
        if 'logger' in lbl:
            return 'loggers'
        if re.search(r'\blat\b', lbl):
            return 'latitude'
        if re.search(r'\blong\b', lbl):
            return 'longitude'
        if 'utm' in lbl and lbl.endswith('x'):
            return 'x_coordinate'
        if 'utm' in lbl and lbl.endswith('y'):
            return 'y_coordinate'
        if lbl in ('x', 'y'):
            return lbl + '_coordinate'
        if ('coordinate' in lbl or 'location' in lbl) and re.search(r'\bx\b', lbl):
            return 'x_coordinate'
        if ('coordinate' in lbl or 'location' in lbl) and re.search(r'\by\b', lbl):
            return 'y_coordinate'
        if lbl == 'company':
            return 'company'
        if lbl == 'well':
            return 'well_name'
        if lbl == 'field':
            return 'field_name'
        if lbl == 'region':
            return 'area'
        if 'classification' in lbl:
            return 'classification'
        return None

    lbl = ' '.join(str(label).split()).lower().strip(':： ')
    _k = _core(lbl)
    if _k:
        return _k
    parts = lbl.split()
    for _n in (1, 2, 3):
        if len(parts) > _n:
            _lead = ' '.join(parts[:-_n])
            if not any(ch.isdigit() for ch in _lead):
                continue
            _k = _core(' '.join(parts[-_n:]))
            if _k:
                return _k
    return None

def find_mudlog_pdf(well_dir):
    """在井文件夹查找录井图/masterlog PDF（文件名含 mud log/mudlog/mud_log/录井/masterlog）。"""
    try:
        wd = Path(well_dir)
        if not wd.is_dir():
            return None
        _keys = ('mud log', 'mudlog', 'mud_log', '录井',
                 'masterlog', 'master log', 'master_log')
        for p in sorted(wd.rglob('*.pdf')):
            _low = p.name.lower()
            if any(k in _low for k in _keys):
                return p
    except Exception as e:
        logger.warning("查找录井图失败: %s", e)
    return None

def extract_mudlog_header(pdf_path):
    """解析录井图 PDF 第 1 页表头 HOLE DATA 块 → 井设置字段 dict。

    版式（BET-1 录井图样本）: 标签行/数值行交替，同行可含多对
    "label : value"（按冒号词切分段）；数值行冒号前无标签时归属上方
    最近未决标签（限相邻行）。数值截大空隙（>60px 跨列串入）并去尾部
    误入标签词；无值字段不进结果（调用方留空白）。
    """
    out = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        words = doc[0].get_text('words')
        doc.close()
        if not words:
            return out

        # ---- 按 y 中心聚行（容差4px, 锚点=行首词y中心） ----
        rows = []
        for w in sorted(words, key=lambda _w: ((_w[1] + _w[3]) / 2.0, _w[0])):
            yc = (w[1] + w[3]) / 2.0
            if rows and abs(yc - rows[-1][0]) <= 4.0:
                rows[-1][1].append(w)
            else:
                rows.append([yc, [w]])

        def _clean_value(ws):
            """数值清洗: 大空隙截断（跨列）+ 去尾部误入标签简写词。"""
            cut = []
            for _w in ws:
                if cut and _w[0] - cut[-1][2] > 60.0:
                    break
                cut.append(_w)
            parts = ' '.join(_w[4] for _w in cut).strip().split()
            while len(parts) > 1 and parts[-1].strip(':，。').lower() in _MUDLOG_LABEL_KEYWORDS:
                parts.pop()
            return ' '.join(parts).strip()

        # ---- 每行按冒号切分为 (label, value) 段；无冒号行整行视为标签 ----
        seg_rows = []
        for _yc, ws in rows:
            ws = sorted(ws, key=lambda _w: _w[0])
            colons = [i for i, _w in enumerate(ws) if _w[4] == ':']
            if not colons:
                seg_rows.append([(' '.join(_w[4] for _w in ws), '')])
                continue
            segs = []
            for si, ci in enumerate(colons):
                lo = (colons[si - 1] + 1) if si else 0
                label = ' '.join(_w[4] for _w in ws[lo:ci])
                _hi = colons[si + 1] if si + 1 < len(colons) else len(ws)
                segs.append((label, _clean_value(ws[ci + 1:_hi])))
            seg_rows.append(segs)

        # ---- 标签匹配 + 未决标签绑定（数值行冒号前无标签→上一行标签的值） ----
        pending = None   # (row_idx, key)
        for ri, segs in enumerate(seg_rows):
            for label, value in segs:
                if not label.strip():
                    if (pending and ri - pending[0] <= 2 and value
                            and pending[1] not in out):
                        out[pending[1]] = value
                        pending = None
                    continue
                key = _mudlog_match_label(label)
                if not key:
                    continue
                if value:
                    if key not in out:
                        out[key] = value
                    pending = None
                elif key not in out:
                    pending = (ri, key)
        return out
    except Exception as e:
        logger.warning("录井图表头解析失败: %s", e)
        return {}

# ---------------------------------------------------------------------------
# 【2026-10-21 R18】录井图「平面文本键值对」兜底 + 井眼/套管/泥浆程序
# ---------------------------------------------------------------------------
# 背景：RASHIDPUR_13 的 masterlog 第 1 页表头是**单行 key:value 串**
#（"WELL NAME:Rashidpur-13 | Latitude:24° 19' 48.14573" N | ..."），
# 坐标聚行版式解析（BET-1 竖排版）取不到任何字段 → 表1/表2 大量空白。
# 这里补一条「全文正则 key:value」通道，与版式解析互补（两路都跑，键不覆盖）。
_ML_KV_MAP = {
    'well name': 'well_name', 'well': 'well_name',
    'company name': 'company', 'company': 'company',
    'latitude': 'latitude', 'lat': 'latitude',
    'longitude': 'longitude', 'long': 'longitude',
    'well type': 'classification', 'classification': 'classification',
    'country': 'country',
    'drilling contractor': 'rig_name', 'rig name': 'rig_name',
    # 【2026-10-21 用户修正】RTE=Rotary Table Elevation=Kelly Bushing elevation=KB；
    #   RKB-GL 是 KB→GL 的**高差**（非 GL 本身），故 elevation_gl = KB - RKB-GL。
    'rkb-msl': 'elevation_kb', 'rkb': 'elevation_kb',
    'rte': 'elevation_kb',
    'rkb-gl': 'elevation_gl_diff',
    'spud-in date': 'spud_date', 'spud in date': 'spud_date',
    'drilling end date': 'td_date', 'td date': 'td_date',
    'date': 'log_date',
    'depth': 'total_depth_driller',
    'wellsite geologist': 'wellsite_geologist',
    'data engineer': 'data_engineer',
    'mud logging geologist': 'mud_logging_geologist',
    'field recorded by': 'field_recorded_by',
    'processed by': 'processed_by',
    'scale': 'scale',
}

def extract_mudlog_flat_kv(pdf_path, max_pages=2):
    """录井图「平面 key:value」兜底提取（第 1~2 页全文正则）。

    返回 {内部键: 值}；只收映射表里认识的键，值去尾部误入标签词。
    与 extract_mudlog_header（版式解析）互补，不覆盖已有键。
    """
    out = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        txt = '\n'.join(doc[i].get_text() for i in range(min(max_pages, len(doc))))
        doc.close()
    except Exception as e:
        logger.warning("录井图平面键值提取失败: %s", e)
        return out
    for m in re.finditer(r'([A-Za-z][A-Za-z0-9 /\-\_\.&]{1,40}?)\s*[:：]\s*([^\n|]{1,60})',
                         txt):
        label = ' '.join(m.group(1).split()).lower().strip(' :')
        key = _ML_KV_MAP.get(label)
        if not key or key in out:
            continue
        parts = m.group(2).split()
        while len(parts) > 1 and parts[-1].strip(':，。|').lower() in _MUDLOG_LABEL_KEYWORDS:
            parts.pop()
        val = ' '.join(parts).strip(' :：|')
        if val and not val.startswith('-999'):
            out[key] = val
    return out

def _parse_hole_size(txt):
    """井眼/套管尺寸文本 → float(inch)。支持 '17 1/2' / '13.375' / '9 5/8'。

    ⚠️ 坑（2026-10-21 R18 实测）：masterlog 里 "17 1/2\"" 是**空格分隔的
    整数+分数**，直接 float() 会崩并被 except 吞掉 → 该段井眼整条丢失
    （RP-13 井眼只剩 36"/26"/7"，最后钻头 8.5in 反而没进列表，bit 取错）。
    """
    t = ' '.join(str(txt).split())
    m = re.match(r'^(\d{1,2})\s+(\d)\s*/\s*(\d)$', t)
    if m:
        try:
            return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
        except Exception:
            return None
    m = re.match(r'^(\d{1,2})\s*/\s*(\d)$', t)
    if m:
        try:
            return int(m.group(1)) / int(m.group(2))
        except Exception:
            return None
    m = re.match(r'^(\d{1,2}(?:\.\d+)?)$', t)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None

def extract_mudlog_hole_casing(pdf_path, max_pages=2):
    """录井图井眼/套管程序 → (borehole_rows, casing_rows, bit_size, hole_sizes)。

    版式（masterlog）：两组并列 —— 左组井眼尺寸 `17 1/2" to 1523.00 m`，
    右组套管尺寸 `13 3/8" to 1521.66 m`。同一目的深度两条配对：
    **大尺寸 = 井眼（钻头）**，**小尺寸 = 套管**。

    返回:
      borehole_rows: [{'size': '17.5', 'from': '0', 'to': '1523'}, ...]
      casing_rows:   [{'size': '13.375', 'from': '0.0', 'to': '1521.66'}, ...]
      bit_size:      最后一个井眼尺寸文本（in）
      hole_sizes:    [(size_float, to_md), ...] 按 to 升序
    """
    _hole, _casing = [], []
    _bit, _holelist = '', []
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        txt = '\n'.join(doc[i].get_text() for i in range(min(max_pages, len(doc))))
        doc.close()
    except Exception as e:
        logger.warning("录井图井眼/套管解析失败: %s", e)
        return _hole, _casing, _bit, _holelist
    for a, b in (('½', ' 1/2'), ('¼', ' 1/4'), ('⅜', ' 3/8'),
                 ('⅝', ' 5/8'), ('⅞', ' 7/8'), ('″', '"'), ('”', '"'),
                 ('’', "'")):
        txt = txt.replace(a, b)
    pairs = []
    for m in re.finditer(
            r'(\d{1,2}(?:\s+\d/\d|\s*\.\d+|\.\d+)?)\s*"\s*(?:to|T0)\s*'
            r'(\d{1,5}(?:\.\d+)?)\s*m', txt, re.I):
        size = _parse_hole_size(m.group(1))
        if size is None or size <= 1 or size > 40:
            continue
        pairs.append((size, float(m.group(2))))
    if not pairs:
        return _hole, _casing, _bit, _holelist
    pairs.sort(key=lambda z: z[1])
    clusters = []
    for size, to_md in pairs:
        if clusters and abs(to_md - clusters[-1][-1][1]) <= 30.0:
            clusters[-1].append((size, to_md))
        else:
            clusters.append([(size, to_md)])
    _prev = 0.0
    for cl in clusters:
        # 【2026-10-21 用户修正】同层井眼(钻头)与套管**各有自己的真实深度**：
        # 大尺寸=钻头(裸眼)，小尺寸=套管；两者 to 不能共用簇首深度，否则
        # 套管 to 会被写成钻头 to（如 1521.66 写成 1523），图上"套管=钻头"。
        # 故每个尺寸保留各自 to_md；钻头 from 接上一钻头 to，套管 from=0。
        cl_sorted = sorted(cl, key=lambda z: z[0])   # 按尺寸升序，最大=钻头
        if not cl_sorted:
            continue
        _hs, _hto = cl_sorted[-1]
        _hole.append({'size': '%g' % _hs,
                      'from': '%g' % _prev, 'to': '%g' % _hto})
        _holelist.append((_hs, _hto))
        _prev = _hto
        for _cs, _cto in cl_sorted[:-1]:
            _casing.append({'size': '%g' % _cs, 'from': '0.0', 'to': '%g' % _cto})
    if _holelist:
        _bit = '%g' % _holelist[-1][0]
    return _hole, _casing, _bit, _holelist

def extract_mudlog_mud_program(pdf_path, max_pages=2):
    """录井图泥浆程序 → '类型(起止)' 串（表2 Type of Fluid in Hole）。

    版式：`10.5- 235.00m:Bentonite` / `235.00- 1523.00m:Polymer` / ...
    """
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        txt = '\n'.join(doc[i].get_text() for i in range(min(max_pages, len(doc))))
        doc.close()
    except Exception:
        return ''
    parts = []
    for m in re.finditer(
            r'([\d.]+)\s*-\s*([\d.]+)\s*m\s*[:：]\s*([A-Za-z][\w\- ]{2,20})', txt):
        lo, hi, kind = m.group(1), m.group(2), m.group(3).strip()
        parts.append('%s(%s-%sm)' % (kind, lo, hi))
    return ' / '.join(parts)

# ---------------------------------------------------------------------------
# 【2026-10-21 R18】MIFT/试油报告（第四信息源：测井单位/日期/井段/人员）
# ---------------------------------------------------------------------------
_MIFT_PDF_KEYS = ('mift', 'pressure data', 'formation test', '试油', 'mdt',
                  'drill stem test', 'dst report')

def find_test_report_pdf(well_dir):
    """查找 MIFT/试油/地层压力报告 PDF（井文件夹内）。"""
    try:
        wd = Path(well_dir)
        if not wd.is_dir():
            return None
        for p in sorted(wd.rglob('*.pdf')):
            low = p.name.lower()
            if any(k in low for k in _MIFT_PDF_KEYS):
                return p
    except Exception as e:
        logger.warning("查找试油/MIFT报告失败: %s", e)
    return None

def extract_test_report_info(pdf_path, max_pages=3):
    """MIFT/试油报告 → {field_name, logging_unit, log_date, ...}。

    版式（MIFT 报告 §1 Well Basic Information）：
        Well Name: / Gas Field: / Area: / Company: /
        Logged By: CNLC / Logging Date: 27-Aug-2026 /
        Prepared By: ... / Approved By: ...
    """
    out = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        txt = '\n'.join(doc[i].get_text() for i in range(min(max_pages, len(doc))))
        doc.close()
    except Exception as e:
        logger.warning("试油/MIFT报告解析失败: %s", e)
        return out
    pats = {
        'field_name': r'(?:Gas\s+Field|Field)\s*[:：]\s*([^\n]{2,40})',
        'area': r'\bArea\s*[:：]\s*([^\n]{2,40})',
        'company': r'\bCompany\s*[:：]\s*([^\n]{2,40})',
        'logging_unit': r'Logged\s+By\s*[:：]\s*([^\n]{2,40})',
        'log_date': r'Logging\s+Date\s*[:：]\s*([^\n]{2,40})',
        'field_recorded_by': r'Prepared\s+By\s*[:：]\s*([^\n]{2,40})',
        'field_witnessed_by': r'Approved\s+By\s*[:：]\s*([^\n]{2,40})',
    }
    for k, p in pats.items():
        m = re.search(p, txt, re.I)
        if m:
            out[k] = ' '.join(m.group(1).split())[:40]
    return out

# ---------------------------------------------------------------------------
# 地质设计（钻探程序 / DWOP / GTO）信息提取
# ---------------------------------------------------------------------------
_GEO_MD_KEYS = ('钻探程序', '地质设计', 'drillingprogram', 'dwop')
_GEO_PDF_KEYS = ('drilling program', 'dwop', '地质设计',
                 # 【2026-10-21 R18】孟加拉项目地质设计文件名 = GTO_<井号>_Final
                 # （Geological Technical Order），此前不在关键词内 → 地质设计
                 # 一个字段都提取不到（表1 目的层/井型/坐标全空）
                 'gto', 'geological technical order', 'well prognosis')

def find_geodesign_files(well_dir):
    """查找地质设计文件: 中文翻译/地质设计 MD + 钻探程序/DWOP PDF。"""
    mds, pdfs = [], []
    try:
        wd = Path(well_dir)
        if not wd.is_dir():
            return mds, pdfs
        for p in sorted(wd.rglob('*')):
            if p.suffix.lower() == '.md':
                low = p.name.lower()
                if any(k in low or k in p.name for k in _GEO_MD_KEYS):
                    mds.append(p)
            elif p.suffix.lower() == '.pdf':
                low = p.name.lower()
                if any(k in low for k in _GEO_PDF_KEYS):
                    pdfs.append(p)
    except Exception as e:
        logger.warning("查找地质设计文件失败: %s", e)
    return mds, pdfs

def extract_geodesign_info(well_dir):
    """从地质设计提取井信息 → {target_formation, well_type, designed_td,
    structure, x_coordinate, y_coordinate}（提取不到的字段不进结果）。

    中文翻译 MD 为主（关键词: 目的层/井型/设计井深/构造位置/圈闭一览表），
    英文 Drilling Program PDF 为辅（Total Depth / Target Formation）。
    """
    out = {}
    mds, pdfs = find_geodesign_files(well_dir)

    # ---- MD: 中文关键词 ----
    for md in mds[:3]:
        try:
            txt = md.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'target_formation' not in out:
            _m = re.search(r'目的层[^。\n]{0,40}?((?:[A-Z]{2,}[\s\-—]*\d[\s\-—、与和]*)+)',
                           txt)
            if _m:
                _toks = re.findall(r'[A-Z]{2,}[\s\-—]*\d', _m.group(1))
                _seen = []
                for _t in _toks:
                    _t = re.sub(r'\s+', '-', _t.strip())
                    if _t not in _seen:
                        _seen.append(_t)
                if _seen:
                    out['target_formation'] = '、'.join(_seen)
        if 'well_type' not in out:
            _m = re.search(r'(直井|斜井|水平井)[·、]?((?:勘探|评价|开发|探边)井)',
                           txt)
            if _m:
                out['well_type'] = _m.group(0)
        if 'designed_td' not in out:
            _m = re.search(r'(?:设计井深|预计井深|计划井深|完钻深度)[^\d\n]{0,30}'
                           r'(\d{3,5})\s*(m|米|ft|英尺)?', txt)
            if _m:
                out['designed_td'] = f"{_m.group(1)} {_m.group(2)}".strip()
        if 'structure' not in out:
            _m = re.search(r'构造[位形置][^\n:：]{0,20}[:：]\s*([^\n|（*。]{2,40})', txt)
            if _m:
                out['structure'] = _m.group(1).strip()
        # 圈闭一览表的 UTM X/Y 备用（含井名行内两个大整数）
        if 'x_coordinate' not in out:
            for line in txt.splitlines():
                if ('X' in line and 'Y' in line
                        and re.search(r'BET', line, re.I)):
                    _m = re.search(r'\|\s*(\d{5,7})\s*\|\s*(\d{6,9})\s*\|', line)
                    if _m:
                        out['x_coordinate'] = f"{_m.group(1)} m"
                        out['y_coordinate'] = f"{_m.group(2)} m"
                        break
        if len(out) >= 6:
            break

    # ---- PDF: 英文关键词（仅取 MD 缺失的字段） ----
    if pdfs and len(out) < 5:
        try:
            import fitz
            doc = fitz.open(str(pdfs[0]))
            txt = '\n'.join(doc[i].get_text() for i in range(min(6, len(doc))))
            doc.close()
            if 'designed_td' not in out:
                # 【2026-10-21 R18】GTO 口径：Target Depth (TD) : 42200 m TVDSS
                # (4258m MDSS) —— MD 口径才是井深设计值，优先取括号内 MD
                _m = re.search(r'Target\s*Depth\s*\(?TD\)?\s*[:：]?\s*'
                               r'[\d\s]{0,12}m?\s*TVDSS[^()]{0,20}\(\s*(\d{3,5})\s*m?\s*MD',
                               txt, re.I)
                if _m:
                    out['designed_td'] = f"{_m.group(1)} m MD"
                else:
                    _m = re.search(r'(?:Total\s*Depth|Proposed\s*TD|Design\s*TD|Planned\s*TD)'
                                   r'[^0-9\n]{0,40}(\d{3,5})\s*(m|ft)', txt, re.I)
                    if _m:
                        out['designed_td'] = f"{_m.group(1)} {_m.group(2)}"
            if 'well_type' not in out:
                _m = re.search(r'Type\s*of\s*well\s*[:：]\s*'
                               r'\b(Vertical|Directional|Deviated|Horizontal)\b', txt, re.I)
                if _m:
                    out['well_type'] = _m.group(1).title() + ' well'
                else:
                    _m = re.search(r'\b(Exploration|Appraisal|Development)\s+Well\b', txt, re.I)
                    if _m:
                        out['well_type'] = _m.group(0).title()
            if 'classification' not in out and 'well_type' not in out:
                _m = re.search(r'Classification\s*[:：]\s*'
                               r'\b(Exploratory|Exploration|Appraisal|Development)\b', txt, re.I)
                if _m:
                    out['classification'] = _m.group(1).title() + ' well'
            if 'target_formation' not in out:
                _m = re.search(r'(?:Target|Objective)\s*Formation[s]?\s*[:：]?\s*'
                               r'([A-Z][A-Za-z0-9 \-]{2,40})', txt)
                if _m:
                    out['target_formation'] = _m.group(1).strip()
            # 【2026-10-21 用户修正】field 取地质设计/客户端成果（Rashidpur Gas
            #   Field），不取 MIFT 报告的邻井/区块名（如 KAMTA Gas Field）。
            if 'field_name' not in out:
                # 【2026-10-21 修复】排除作业公司 "Gas Fields Limited"（复数 Fields +
                #   常作页眉碎片 "CTION COMPANY LIMITE\net Gas Field"）：用负向后顾
                #   (?!s) 要求 "Gas Field" 后不是 's'（公司 "Gas Fields" 必被排除）；
                #   前缀限定为 1~3 个「首字母大写+其余小写」专名词（如 Rashidpur），
                #   避免把 "Location map of Rashidpur Gas Field" 这类图名前缀吞进来。
                _m = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+Gas\s+Field(?!s))', txt)
                if _m:
                    out['field_name'] = _m.group(1).strip()
        except Exception as e:
            logger.warning("地质设计 PDF 解析失败: %s", e)

    # ---- 【2026-10-21 R18】GTO Well Summary **坐标法**兜底（正则无效，见下）----
    if pdfs:
        _kv = _extract_gto_summary_kv(pdfs[0])
        for _k, _v in _kv.items():
            if _v and not out.get(_k):
                out[_k] = _v
    return out

def _extract_gto_summary_kv(pdf_path, max_pages=12):
    """GTO(Geological Technical Order) Well Summary 键值 → 内部键。

    ⚠️ 坑（2026-10-21 R18 实测）：GTO PDF 的 Well Summary 是**两列表格**，
    文本层被拆成"标签列 + 值列"且**值列在 x≈205 起、标签列在 x≈77~190**，
    同一行被拆成 5~6 个碎片（如 "42" | "200" | "m" | "TVDSS" | "(±100m)"），
    **正则 `Target Depth (TD) : 42200 m TVDSS` 完全匹配不上**（值被换行拆散）；
    且经纬度/Easting/Northing 各列**列头 x 与数据 x 不对齐**，按 x 区间切列
    会串格 ⇒ 只能"y 聚行 + 冒号分列 + 整行文本正则"。
    """
    out = {}
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        logger.warning("GTO 打开失败: %s", e)
        return out
    try:
        for _pi in range(min(max_pages, len(doc))):
            _words = doc[_pi].get_text('words')
            if not _words:
                continue
            _rows = []
            for _w in sorted(_words, key=lambda z: ((z[1] + z[3]) / 2.0, z[0])):
                _yc = (_w[1] + _w[3]) / 2.0
                if _rows and abs(_yc - _rows[-1][0]) <= 4.0:
                    _rows[-1][1].append(_w)
                else:
                    _rows.append([_yc, [_w]])
            _rows = [[yc, sorted(ws, key=lambda z: z[0])] for yc, ws in _rows]
            # 标签行 = 含 ':' 词元；值 = 冒号右侧全部词元拼接
            for _yc, _ws in _rows:
                _texts = [w[4] for w in _ws]
                if ':' not in _texts:
                    continue
                _ci = _texts.index(':')
                _label = ' '.join(' '.join(_texts[:_ci]).split())
                if not _label or len(_label) > 40:
                    continue
                _val = ' '.join(' '.join(w[4] for w in _ws[_ci + 1:]).split())
                if not _val:
                    continue
                _lab_l = _label.lower()
                if 'target depth' in _lab_l or _lab_l in ('td', 'total depth'):
                    # "42 200 m TVDSS (±100m) (4258m MDSS)" → 取 MD 口径
                    _m = re.search(r'\(\s*([\d]{3,5})\s*m\s*MD', _val, re.I)
                    if _m:
                        out['designed_td'] = f"{_m.group(1)} m MD"
                    else:
                        _m = re.search(r'([\d]{3,5})\s*m\s*TVDSS', _val, re.I)
                        if _m:
                            out['designed_td'] = f"{_m.group(1)} m TVDSS"
                elif _lab_l in ('type of well', 'well type'):
                    _c = _val.replace(' ', '')
                    for _kw in ('Vertical', 'Directional', 'Deviated', 'Horizontal'):
                        if _kw.lower() in _c.lower():
                            out['well_type'] = _kw + ' well'
                            break
                elif _lab_l == 'classification':
                    _c = _val.replace(' ', '')
                    for _kw in ('Exploratory', 'Exploration', 'Appraisal', 'Development'):
                        if _kw.lower() in _c.lower():
                            out['classification'] = _kw + ' well'
                            break
                elif _lab_l == 'trap type':
                    out['structure'] = _val[:60]
            # ---- 坐标表：Easting/Northing/Latitude/Longitude 列头 + 数据行 ----
            _hdr_idx = -1
            for _ri, (_yc, _ws) in enumerate(_rows):
                _t = ' '.join(w[4] for w in _ws)
                if 'Easting' in _t and 'Northing' in _t and 'ongitude' in _t:
                    _hdr_idx = _ri
                    break
            if _hdr_idx >= 0:
                for _ri in range(_hdr_idx + 1, len(_rows)):
                    _yc, _ws = _rows[_ri]
                    _t = ' '.join(w[4] for w in _ws)
                    if 'Sub-' in _t or 'Depth' in _t or 'Location' in _t:
                        break
                    if not re.search(r'\d', _t) or '°' not in _t:
                        continue
                    # 整行文本正则：先取经纬度，剩下数字串依次 Easting/Northing
                    #（⚠️ PDF 把 "6661419.052m" 拆成 "66" + "61419.052m" 两块，
                    #  必须拼接而非各自成值）
                    _la = re.search(r"(\d+\s*°\s*\d+'\s*[\d.\s]*\"\s*[NS])", _t)
                    _lo = re.search(r"(\d+\s*°\s*\d+'\s*[\d.\s]*\"\s*[EW])", _t)
                    if _la and not out.get('latitude'):
                        out['latitude'] = ' '.join(_la.group(1).split())
                        if _lo:
                            out['longitude'] = ' '.join(_lo.group(1).split())
                    _rest = _t
                    for _mm in (_la, _lo):
                        if _mm:
                            _rest = _rest.replace(_mm.group(0), ' ')
                    _nums = re.findall(r'\d+\.?\d*\s*m?', _rest)
                    _nums = [re.sub(r'\s*m?$', '', z).strip() for z in _nums]
                    _nums = [z for z in _nums if z]
                    if len(_nums) >= 3 and 'x_coordinate' not in out:
                        out['x_coordinate'] = f'{_nums[0]}{_nums[1]}m'
                        out['y_coordinate'] = f'{_nums[2]}m'
                    elif len(_nums) == 2 and 'x_coordinate' not in out:
                        out['x_coordinate'] = f'{_nums[0]}m'
                        out['y_coordinate'] = f'{_nums[1]}m'
                    if out.get('x_coordinate') and out.get('latitude'):
                        break
            if out.get('x_coordinate') or out.get('designed_td'):
                break
        doc.close()
    except Exception as e:
        logger.warning("GTO Well Summary 解析失败: %s", e)
    return out

# ---------------------------------------------------------------------------
# 井名 info.json 收集 / 加载 / 应用
# ---------------------------------------------------------------------------
_GROUPS = ('井信息', '日期', '坐标', '海拔', '钻机', '人员', '井深', '地质设计',
           '泥浆信息', '测量记录', '图表标题', '免责声明', '图例', '曲线信息',
           '深度比例尺', '流体颜色')

# 表2 钻井液/测量参数 → LAS ~P 参数字典（其余键 → well 字典）
_PARAM_KEYS = {'bit_size', 'drilling_fluid_type', 'drilling_fluid_density',
               'drilling_fluid_viscosity', 'drilling_fluid_ph',
               'drilling_fluid_loss', 'rm_meas_temp', 'rmf_meas_temp',
               'rmc_meas_temp', 'rm_bht', 'time_since_circulation',
               'max_record_temp', 'casing_record', 'borehole_record'}

def _collect_las_curves(well_dir, results=None):
    """从 LAS ~C 收集曲线清单 "MNEM:UNIT:说明; ..."（失败返回 ''）。

    LAS 定位: results['las_path'] → 井文件夹顶层第一个 *.las。
    """
    try:
        _p = None
        _lp = (results or {}).get('las_path')
        if _lp and Path(_lp).exists():
            _p = Path(_lp)
        if _p is None:
            for _c in sorted(Path(well_dir).glob('*.las')):
                _p = _c
                break
        if _p is None:
            return ''
        _out, _in = [], False
        for _ln in _p.read_text(encoding='utf-8', errors='replace').splitlines():
            _s = _ln.strip()
            if _s.startswith('~'):
                _in = len(_s) > 1 and _s[1].upper() == 'C'
                continue
            if not _in or not _s or _s.startswith('#'):
                continue
            _m = re.match(r'([A-Za-z0-9_]+)\s*\.\s*(\S*)\s*.*?:\s*(.*)$', _s)
            if _m:
                _mn, _un, _desc = _m.group(1), _m.group(2).strip(), _m.group(3).strip()
                if _mn.upper() in ('DEPT', 'DEPTH', 'MD'):
                    continue
                _out.append(f"{_mn}:{_un}:{_desc}")
        return '; '.join(_out[:40])
    except Exception as e:
        logger.warning("LAS 曲线收集失败: %s", e)
        return ''

def well_info_json_path(well_dir, well_name=''):
    """<井名>info.json 路径（井文件夹下, 便于人工修改）。"""
    wd = Path(well_dir)
    _name = str(well_name or wd.name or 'well').strip() or 'well'
    return wd / f"{_name}info.json"

def _flatten_groups(cfg):
    """分组 json → 展平 dict（跳过 _ 开头说明键；仅保留非空值）。"""
    flat = {}
    if not isinstance(cfg, dict):
        return flat
    for _sec in cfg.values():
        if not isinstance(_sec, dict):
            continue
        for _k, _v in _sec.items():
            if _k.startswith('_') or _v is None:
                continue
            _sv = str(_v).strip()
            if _sv and not _sv.startswith('-999'):
                flat[_k] = _sv
    return flat

def load_well_info_json(results):
    """供可视化读取: 从 results 定位 <井名>info.json 并展平（找不到→{}）。

    定位顺序: results['well_info_json']（logInt 收集时写入）→
    results['well_dir']/<井名>info.json → results['output_dir'] 同级回退。
    """
    if not isinstance(results, dict):
        return {}
    _cands = []
    _p = results.get('well_info_json')
    if _p:
        _cands.append(Path(_p))
    _wd = results.get('well_dir')
    _wn = str((results.get('las_info') or {}).get('well', {}).get('well_name')
              or results.get('well_name') or '')
    if _wd:
        _cands.append(well_info_json_path(_wd, _wn))
    for p in _cands:
        try:
            if p.exists():
                return _flatten_groups(json.loads(p.read_text(encoding='utf-8')))
        except Exception as e:
            logger.warning("井信息 json 读取失败 %s: %s", p, e)
    return {}

def collect_well_info(results, well_dir):
    """多源收集井信息 → 生成/读取 <井名>info.json 并应用到 results。

    - 首次: 自动提取（录井图/地质设计/LAS头 + 旧版 well_settings.json 迁移）
      并回写 <井名>info.json（人工字段留空待填）
    - 再次: json 非空值优先直接调用（人工修改即生效）
    - 应用: 非空值并入 results['las_info']['well']; 同时记录
      results['well_info_json'] / results['well_dir'] 供可视化读取
    """
    from datetime import datetime as _dt
    las_info = results.get('las_info')
    if not isinstance(las_info, dict):
        las_info = {}
        results['las_info'] = las_info
    well = las_info.setdefault('well', {})
    param = las_info.setdefault('parameter', {})
    well_dir = str(well_dir or results.get('well_dir') or '')
    _today = _dt.now().strftime('%Y-%m-%d')

    def _first(*vals):
        for _v in vals:
            _s = str(_v).strip() if _v is not None else ''
            if _s and not _s.startswith('-999'):
                return _s
        return ''

    json_path = well_info_json_path(well_dir, well.get('well_name'))
    cfg = {}
    existed = False
    if json_path.exists():
        try:
            cfg = _flatten_groups(json.loads(json_path.read_text(encoding='utf-8')))
            existed = True
            print(f"  井信息: 读取 {json_path.name}（json 非空值优先）")
        except Exception as e:
            logger.warning("井信息 json 解析失败, 重新自动提取: %s", e)

    # 图版默认免责声明（templates/qlpt.json legend.disclaimer, 甲方样本原文）
    # 【2026-10-14 用户定案】免责声明内容进 json 便于查看/修改
    _tpl_disclaimer = ''
    try:
        _tj = Path(__file__).parent / 'templates' / 'qlpt.json'
        if _tj.exists():
            _td = json.loads(_tj.read_text(encoding='utf-8'))
            _tpl_disclaimer = str((_td.get('legend') or {}).get('disclaimer')
                                  or _td.get('disclaimer') or '').strip()
    except Exception as _te:
        logger.warning("图版免责声明读取失败: %s", _te)

    # ---- 自动提取（每次运行; json 非空值优先, 空缺键回退自动提取, 都没有留空白） ----
    legacy = {}
    if not existed:
        try:
            _lp = Path(well_dir) / 'well_settings.json'
            if _lp.exists():
                legacy = _flatten_groups(json.loads(
                    _lp.read_text(encoding='utf-8')))
        except Exception:
            legacy = {}
    _ml_path = find_mudlog_pdf(well_dir)
    _ml = extract_mudlog_header(_ml_path) or {}
    # 【2026-10-21 R18】平面 key:value 兜底 + 井眼/套管/泥浆程序
    # （RP-13 masterlog 是单行键值串，版式解析取不到任何字段 → 表1/表2 全空）
    _ml_flat = extract_mudlog_flat_kv(_ml_path) if _ml_path else {}
    for _k, _v in _ml_flat.items():
        _ml.setdefault(_k, _v)
    _bh_rows, _cs_rows, _bit_size, _hole_list = (
        extract_mudlog_hole_casing(_ml_path) if _ml_path else ([], [], '', []))
    _mud_program = extract_mudlog_mud_program(_ml_path) if _ml_path else ''
    _geo = extract_geodesign_info(well_dir) or {}
    # 【2026-10-21 R18】第四信息源：MIFT/试油报告（测井单位/日期/井名/人员）
    _tr_path = find_test_report_pdf(well_dir)
    _tr = extract_test_report_info(_tr_path) if _tr_path else {}
    if _tr:
        print(f"  井信息: 试油/MIFT报告提取 {len(_tr)} 项（{_tr_path.name}）")
    _curves_txt = _collect_las_curves(well_dir, results)
    _ml_n = sum(1 for k in ('spud_date', 'td_date', 'latitude', 'longitude',
                            'x_coordinate', 'y_coordinate', 'elevation_gl',
                            'elevation_kb', 'rig_name', 'logging_unit')
                if _ml.get(k))
    if _ml:
        print(f"  井信息: 录井图提取 {_ml_n} 项（{Path(find_mudlog_pdf(well_dir)).name}）")
    if _geo:
        print(f"  井信息: 地质设计提取 {len(_geo)} 项")

    # 井眼/套管记录 → json 字符串（人工可改；出图与表2/BIT 曲线共用）
    def _rows_to_str(rows):
        return '; '.join(f"{r['size']}in {r['from']}-{r['to']}" for r in rows
                         if r.get('size') and r.get('from') is not None)

    _bh_str = _rows_to_str(_bh_rows)
    _cs_str = _rows_to_str(_cs_rows)

    # LAS LOC 行提取 UTM X/Y 备用（支持全角冒号, X 先 Y 后各取一次）
    def _las_xy_pair():
        _txt = str(well.get('well_coordinate') or '')
        _ms = re.findall(r'([XY])\s*[：:]\s*([0-9][0-9,\.]*(?:\s*[a-zA-Z]+)?)', _txt)
        _d = {k.upper(): v.strip() for k, v in _ms}
        return _d.get('X', ''), _d.get('Y', '')

    _lx, _ly = _las_xy_pair()
    # 各字段优先级: json/旧设置 > 录井图 > 地质设计 > LAS/参数/默认 > 空白
    final = {
        'company':        _first(legacy.get('company'), _ml.get('company'), well.get('company')),
        'well_name':      _first(legacy.get('well_name'), _ml.get('well_name'), well.get('well_name')),
        # 【2026-10-21 用户修正】field 优先级：legacy > 录井图 > 地质设计(GTO) >
        #   MIFT/试油报告 > LAS。MIFT 报告常误给邻井/区块名（如 KAMTA），地质设计/
        #   客户端成果（Rashidpur Gas Field）才是本井真值，故 _geo 置于 _tr 之前。
        'field_name':     _first(legacy.get('field_name'), _ml.get('field_name'),
                               _geo.get('field_name'), _tr.get('field_name'),
                               well.get('field_name')),
        'area':           _first(legacy.get('area'), _ml.get('area'),
                                _tr.get('area'), well.get('area')),
        'country':        _first(legacy.get('country'), _ml.get('country'), well.get('country')),
        'classification': _first(legacy.get('classification'), _ml.get('classification'),
                                 _geo.get('classification')),
        'spud_date':      _first(legacy.get('spud_date'), _ml.get('spud_date'), well.get('spud_date')),
        'td_date':        _first(legacy.get('td_date'), _ml.get('td_date'), well.get('td_date')),
        # 【2026-10-14 二十轮】date 改名 log_date（测井日期）；旧 legacy/json 'date' 键兼容回退
        'log_date':       _first(legacy.get('log_date'), legacy.get('date'),
                                 well.get('log_date'), well.get('date'),
                                 _tr.get('log_date')),
        'process_date':   _first(legacy.get('process_date'), well.get('process_date')),
        'latitude':       _first(legacy.get('latitude'), _ml.get('latitude'), well.get('latitude')),
        'longitude':      _first(legacy.get('longitude'), _ml.get('longitude'), well.get('longitude')),
        'x_coordinate':   _first(legacy.get('x_coordinate'), _ml.get('x_coordinate'), _geo.get('x_coordinate'), _lx),
        'y_coordinate':   _first(legacy.get('y_coordinate'), _ml.get('y_coordinate'), _geo.get('y_coordinate'), _ly),
        'elevation_gl':   _first(legacy.get('elevation_gl'), _ml.get('elevation_gl'), param.get('elevation_ground_level')),
        'elevation_kb':   _first(legacy.get('elevation_kb'), _ml.get('elevation_kb'), param.get('elevation_kelly_bushing')),
        'elevation_df':   _first(legacy.get('elevation_df'), _ml.get('elevation_df'), param.get('elevation_drill_floor')),
        # 【2026-10-21 用户修正】RKB-GL 是 KB→GL 高差，落单独键供下方换算 GL
        'elevation_gl_diff': _ml.get('elevation_gl_diff'),
        'rig_name':       _first(legacy.get('rig_name'), _ml.get('rig_name'), well.get('rig_name')),
        'logging_unit':   _first(legacy.get('logging_unit'), _ml.get('logging_unit'),
                                _ml.get('mud_logging_geologist'),
                                _tr.get('logging_unit'), well.get('logging_unit_name')),
        'equipment_no':   _first(legacy.get('equipment_no'), well.get('equipment_no')),
        'processed_by':      _first(legacy.get('processed_by'), well.get('processed_by')),
        'corrected_by':      _first(legacy.get('corrected_by'), well.get('corrected_by')),
        'field_recorded_by': _first(legacy.get('field_recorded_by'), _ml.get('field_recorded_by'),
                                 _tr.get('field_recorded_by'),
                                 well.get('engineers_name'), well.get('engi')),
        'field_witnessed_by': _first(legacy.get('field_witnessed_by'),
                                     _ml.get('field_witnessed_by'),
                                     _tr.get('field_witnessed_by')),
        # ---- 【2026-10-21 R18】录井图人员（表1 空白的主要来源）----
        'wellsite_geologist':   _first(legacy.get('wellsite_geologist'), _ml.get('wellsite_geologist')),
        'data_engineer':        _first(legacy.get('data_engineer'), _ml.get('data_engineer')),
        'target_formation':  _first(legacy.get('target_formation'), _geo.get('target_formation')),
        'well_type':         _first(legacy.get('well_type'), _geo.get('well_type'), _ml.get('classification')),
        'designed_td':       _first(legacy.get('designed_td'), _geo.get('designed_td')),
        'structure':         _first(legacy.get('structure'), _geo.get('structure')),
        # ---- 表2 测量记录（LAS ~P 参数 + 知识文件提取, 空留白） ----
        # 【2026-10-21 R18】bit_size/泥浆程序：录井图井身结构优先
        # （用户："基础资料中很容易找到最后一个钻头是 8.5in 的，要以他为 bit"）
        'bit_size':                 _first(legacy.get('bit_size'), param.get('bit_size'), _bit_size),
        'drilling_fluid_type':      _first(legacy.get('drilling_fluid_type'),
                                           param.get('drilling_fluid_type'), _mud_program),
        'drilling_fluid_density':   _first(legacy.get('drilling_fluid_density'), param.get('drilling_fluid_density')),
        'drilling_fluid_viscosity': _first(legacy.get('drilling_fluid_viscosity'), param.get('drilling_fluid_viscosity')),
        'drilling_fluid_ph':        _first(legacy.get('drilling_fluid_ph'), param.get('drilling_fluid_ph')),
        'drilling_fluid_loss':      _first(legacy.get('drilling_fluid_loss'), param.get('drilling_fluid_loss')),
        'rm_meas_temp':             _first(legacy.get('rm_meas_temp'), param.get('rm_meas_temp')),
        'rmf_meas_temp':            _first(legacy.get('rmf_meas_temp'), param.get('rmf_meas_temp')),
        'rmc_meas_temp':            _first(legacy.get('rmc_meas_temp'), param.get('rmc_meas_temp')),
        'rm_bht':                   _first(legacy.get('rm_bht'), param.get('rm_bht')),
        'time_since_circulation':   _first(legacy.get('time_since_circulation'), param.get('time_since_circulation')),
        'max_record_temp':          _first(legacy.get('max_record_temp'), param.get('max_record_temp')),
        'casing_record':            _first(legacy.get('casing_record'), param.get('casing_record'), _cs_str),
        'borehole_record':          _first(legacy.get('borehole_record'), param.get('borehole_record'), _bh_str),
        # ---- 图表标题（空=程序默认） ----
        'ql_title':    _first(legacy.get('ql_title')),
        'cmpt_title':  _first(legacy.get('cmpt_title')),
        'xplot_title': _first(legacy.get('xplot_title')),
        'footer_text': _first(legacy.get('footer_text')),
        # ---- 免责声明【2026-10-14 用户定案】内容进 json 便于查看/修改：
        # 优先 json/旧设置, 无来源时写图版 qlpt.json 实际生效文本（样本原文）----
        'disclaimer':  _first(legacy.get('disclaimer'), _tpl_disclaimer),
        # ---- 图例（岩性空=数据自动提取; 微相/结论=程序默认起步值, 可改） ----
        'lithology_legend':      _first(legacy.get('lithology_legend')),
        'facies_legend':         _first(legacy.get('facies_legend'), 'Channel, Floodplain, Delta Front, Prodelta'),
        'interpretation_legend': _first(legacy.get('interpretation_legend'), 'Oil, Gas, Water'),
        # ---- 曲线信息（LAS ~C 自动收集, 可修改） ----
        'curves': _first(legacy.get('curves'), _curves_txt),
        # ---- 深度比例尺【2026-10-14 用户定案】英尺=1:240、公制=1:200（json 可改） ----
        'curve_scale_ft': _first(legacy.get('curve_scale_ft'), '1:240'),
        'curve_scale_m':  _first(legacy.get('curve_scale_m'), '1:200'),
        # ---- 流体颜色【2026-10-14 用户定案】气=红/油=深绿/水=蓝（与全局
        # FLUID_COLOR 一致, 交会图等出图消费, json 人工修改非空值优先） ----
        'gas_color':   _first(legacy.get('gas_color'), '#d73027'),
        'oil_color':   _first(legacy.get('oil_color'), '#1a9850'),
        'water_color': _first(legacy.get('water_color'), '#00a8f8'),
        # ---- 井信息补充键【2026-10-14 用户定案】logvis 消费全键进 json：
        # LAS 头自动提取（服务公司/州省/基准面/测井起止深/钻达·测井井深），缺留空人工填 ----
        'service_company_name': _first(legacy.get('service_company_name'), well.get('service_company_name')),
        'state_or_province':    _first(legacy.get('state_or_province'), well.get('state_or_province')),
        'permanent_datum':      _first(legacy.get('permanent_datum'), well.get('permanent_datum')),
        'start_depth':         _first(legacy.get('start_depth'), well.get('start_depth')),
        'stop_depth':          _first(legacy.get('stop_depth'), well.get('stop_depth')),
        'total_depth_driller': _first(legacy.get('total_depth_driller'), well.get('total_depth_driller')),
        'total_depth_logger':  _first(legacy.get('total_depth_logger'), well.get('total_depth_logger')),
    }
    # 【2026-10-21 用户修正】RKB-GL 是 KB→GL 的高差，不是 GL 本身：
    #   elevation_gl = elevation_kb - elevation_gl_diff（56.5m - 10.5m = 46.0m）。
    #   GL 未直接取到时由 KB 与高差反算（主取 KB，DF 近似亦可）。
    if not str(final.get('elevation_gl') or '').strip():
        _kb = str(final.get('elevation_kb') or final.get('elevation_df') or '').strip()
        _dgl = str(final.get('elevation_gl_diff') or '').strip()
        # 【2026-10-21 修复】提取值常带单位后缀（"56.5m"），float() 直接崩 →
        #   先抽数字再算（GL = KB - RKB-GL = 56.5 - 10.5 = 46.0）。
        import re as _re_num
        def _num(s):
            _m = _re_num.search(r'-?\d+(?:\.\d+)?', str(s))
            return float(_m.group(0)) if _m else None
        _kb_n, _dgl_n = _num(_kb), _num(_dgl)
        if _kb_n is not None and _dgl_n is not None:
            final['elevation_gl'] = '%.2f' % (_kb_n - _dgl_n)

    # 【2026-10-14 二十轮】旧版 json 'date' 键 → log_date 兼容（date 已改名 log_date）
    if not str(cfg.get('log_date') or '').strip() and str(cfg.get('date') or '').strip():
        cfg['log_date'] = cfg['date']
    # json 非空值覆盖; json 未含/为空的键回退自动提取值
    for _k, _v in list(final.items()):
        _cv = str(cfg.get(_k) or '').strip()
        if _cv:
            final[_k] = _cv
    cfg = {k: v for k, v in final.items() if str(v).strip()}

    # 【2026-10-14 用户定案】json 中为空、本次自动提取到值的键 → 回填 json
    # （免责声明/钻头套管等内容进 json 便于查看修改; 人工修改的非空值不覆盖）
    if existed:
        try:
            _old = json.loads(json_path.read_text(encoding='utf-8'))
            _n_fill = 0
            for _sec in _old.values():
                if not isinstance(_sec, dict):
                    continue
                for _k, _v in _sec.items():
                    if _k.startswith('_') or not isinstance(_v, (str, int, float)):
                        continue
                    if not str(_v or '').strip():
                        _nv = str(final.get(_k) or '').strip()
                        if _nv:
                            _sec[_k] = final[_k]
                            _n_fill += 1
            # 缺失组/缺失键补写（仅补缺, 不覆盖人工修改）：
            # 程序升级新增组（如"深度比例尺"/"井深"）或组内新增键时,
            # 旧 json 自动补齐, 保证字段清单完整
            _new_groups = {
                '深度比例尺': {
                    '_说明': '深度道比例尺【2026-10-14 用户定案】：深度单位英尺=1:240、'
                            '公制=1:200；人工修改非空值后出图直接调用',
                    'curve_scale_ft': final.get('curve_scale_ft') or '1:240',
                    'curve_scale_m': final.get('curve_scale_m') or '1:200',
                },
                '井深': {
                    '_说明': '测井起止深度与井深（LAS 头 STRT/STOP 及钻达/测井井深）；缺留空人工填',
                    'start_depth': final.get('start_depth') or '',
                    'stop_depth': final.get('stop_depth') or '',
                    'total_depth_driller': final.get('total_depth_driller') or '',
                    'total_depth_logger': final.get('total_depth_logger') or '',
                },
                '流体颜色': {
                    '_说明': '交会图流体统一色【2026-10-14 用户定案】气=红/油=深绿/水=蓝；'
                            '人工修改非空值后出图直接调用（#RRGGBB 或颜色名）',
                    'gas_color': final.get('gas_color') or '#d73027',
                    'oil_color': final.get('oil_color') or '#1a9850',
                    'water_color': final.get('water_color') or '#00a8f8',
                },
                # 【2026-10-14 二二轮】泥浆信息独立组（用户定案）：旧 json 补组，
                # 值随 final 迁入（含原'测量记录'组内泥浆键的非空值）
                '泥浆信息': {
                    '_说明': '泥浆类型/密度/粘度/酸碱度·失水与泥浆·滤液·泥饼电阻率'
                            '（LAS ~P 参数与知识文件提取；收集不到留空白）',
                    'drilling_fluid_type': final.get('drilling_fluid_type') or '',
                    'drilling_fluid_density': final.get('drilling_fluid_density') or '',
                    'drilling_fluid_viscosity': final.get('drilling_fluid_viscosity') or '',
                    'drilling_fluid_ph': final.get('drilling_fluid_ph') or '',
                    'drilling_fluid_loss': final.get('drilling_fluid_loss') or '',
                    'rm_meas_temp': final.get('rm_meas_temp') or '',
                    'rmf_meas_temp': final.get('rmf_meas_temp') or '',
                    'rmc_meas_temp': final.get('rmc_meas_temp') or '',
                    'rm_bht': final.get('rm_bht') or '',
                },
            }
            for _g, _d in _new_groups.items():
                if _g not in _old:
                    _old[_g] = dict(_d)
                    _n_fill += 1
            # 泥浆键组迁移【2026-10-14 二二轮】：旧 json '测量记录'组内泥浆键
            # 移入新'泥浆信息'组（值已随迁, 原位置移除避免双份）
            if isinstance(_old.get('测量记录'), dict):
                _MUD_KEYS = ('drilling_fluid_type', 'drilling_fluid_density',
                             'drilling_fluid_viscosity', 'drilling_fluid_ph',
                             'drilling_fluid_loss', 'rm_meas_temp',
                             'rmf_meas_temp', 'rmc_meas_temp', 'rm_bht')
                for _k in _MUD_KEYS:
                    _old['测量记录'].pop(_k, None)
                _old['测量记录']['_说明'] = ('表2 钻头尺寸/循环时间/最高记录温度/'
                                          '套管·井眼记录（LAS ~P 参数与知识文件提取；'
                                          '收集不到留空白）')
            _new_keys = {
                '井信息': {'service_company_name': final.get('service_company_name') or '',
                          'state_or_province': final.get('state_or_province') or '',
                          'permanent_datum': final.get('permanent_datum') or ''},
                # 【2026-10-14 二十轮】旧 json 补 log_date 键（date 改名，原 'date' 键留存不删）
                '日期': {'log_date': final.get('log_date') or ''},
                # 【2026-10-27 R28】旧 json 补「解释截止值」组（空值=默认）
                '解释截止值': {k: '' for k in DEFAULT_CUTOFFS},
            }
            for _g, _d in _new_keys.items():
                if _g == '解释截止值' and not isinstance(_old.get(_g), dict):
                    _old[_g] = {}
                if isinstance(_old.get(_g), dict):
                    for _k2, _v2 in _d.items():
                        if _k2 not in _old[_g]:
                            _old[_g][_k2] = _v2
                            _n_fill += 1
            if _n_fill:
                json_path.write_text(json.dumps(_old, ensure_ascii=False, indent=2),
                                     encoding='utf-8')
                print(f"  井信息: 回填 {_n_fill} 个空值字段 → {json_path.name}（可人工修改）")
        except Exception as e:
            logger.warning("井信息 json 空值回填失败: %s", e)

    if not existed:
        _geo_mds, _geo_pdfs = find_geodesign_files(well_dir)
        _src = ['录井图: ' + str(find_mudlog_pdf(well_dir) or ''),
                '地质设计: ' + '; '.join(str(p) for p in (_geo_mds + _geo_pdfs)),
                'LAS: ' + str(results.get('las_path') or '')]
        settings = {
            '_meta': {
                '说明': ('井信息文件（<井名>info.json）：快速解释/综合图/交汇图所有文字'
                        '信息由 logInt 井信息收集模块从 LAS/录井图/地质设计等基础资料自动收集'
                        '生成，人工可修改；处理与出图时本文件非空值优先直接调用，'
                        '空值回退自动提取，无值留空白。'),
                'well': final['well_name'],
                'updated': _today,
                'sources': [s for s in _src if s.split(':')[-1].strip()],
            },
            '解释截止值': {
                '_说明': ('解释截止值分井配置：默认=巴西海上深水经验值（por_hc 0.06、'
                        'por_dry_max 0.10、sw_hc 0.5、sw_deny 0.65、rt_gas 50、'
                        'rt_oil 30、rt_water 20），每个区块每口井可能不同——'
                        '人工填写非空数值即覆盖本井解释（孔隙度/饱和度填小数，'
                        'RT 单位 ohm·m），留空用默认'),
                'por_hc': '',
                'por_dry_max': '',
                'sw_hc': '',
                'sw_deny': '',
                'rt_gas': '',
                'rt_oil': '',
                'rt_water': '',
            },
            '井信息': {
                '_说明': '业主公司/井名/区块/区域/井别（LAS头 COMPANY/FLD/AREA、录井图、地质设计）；'
                        '服务公司/州省/永久基准面取 LAS 头（SVSC/PROV/PDAT），缺留空人工填',
                'company': final['company'],
                'well_name': final['well_name'],
                'field_name': final['field_name'],
                'area': final['area'],
                'country': final['country'],
                'classification': final['classification'],
                'service_company_name': final['service_company_name'],
                'state_or_province': final['state_or_province'],
                'permanent_datum': final['permanent_datum'],
            },
            '日期': {
                '_说明': '开钻/完钻日期取录井图 Spud Date/TD Date；测井日期 log_date 取 LAS DATE；处理日期默认出图当日（可改）',
                'spud_date': final['spud_date'],
                'td_date': final['td_date'],
                'log_date': final['log_date'],
                'process_date': final['process_date'] or _today,
            },
            '坐标': {
                '_说明': '经纬度取录井图 Lat/Long（LAS LATI=纬度/LONG=经度 备用）；'
                        'UTM XY 取录井图 Coordinates X/Y（地质设计、LAS LOC 备用）',
                'latitude': final['latitude'],
                'longitude': final['longitude'],
                'x_coordinate': final['x_coordinate'],
                'y_coordinate': final['y_coordinate'],
            },
            '海拔': {
                '_说明': '地面海拔GL←录井图 RKB-GL（LAS EGL 备用）；补心海拔KB←录井图 '
                        'RKB-MSL（RKB=补心转盘,井深起算点, LAS EKB 备用）；DF钻台海拔取 LAS EDF',
                'elevation_gl': final['elevation_gl'],
                'elevation_kb': final['elevation_kb'],
                'elevation_df': final['elevation_df'],
            },
            '钻机': {
                '_说明': '钻机名取录井图 Rig Name/Type；测井单位取录井图 Logging Unit；设备号备用',
                'rig_name': final['rig_name'],
                'logging_unit': final['logging_unit'],
                'equipment_no': final['equipment_no'],
            },
            '人员': {
                '_说明': '测井工程师 Field Recorded By 取 LAS ENGI；解释工程师 Processed By/'
                        '校正工程师 Corrected By/测井监督 Field Witnessed By 人工填写，留空则表1留白',
                'processed_by': final['processed_by'],
                'corrected_by': final['corrected_by'],
                'field_recorded_by': final['field_recorded_by'],
                'field_witnessed_by': final['field_witnessed_by'],
            },
            '井深': {
                '_说明': '测井起止深度与井深（LAS 头 STRT/STOP 及钻达/测井井深）；'
                        '综合图/快速图深度范围信息，缺留空人工填',
                'start_depth': final['start_depth'],
                'stop_depth': final['stop_depth'],
                'total_depth_driller': final['total_depth_driller'],
                'total_depth_logger': final['total_depth_logger'],
            },
            '地质设计': {
                '_说明': '目的层/井型/设计井深/构造位置（钻探程序地质章节、Drilling Program/DWOP）',
                'target_formation': final['target_formation'],
                'well_type': final['well_type'],
                'designed_td': final['designed_td'],
                'structure': final['structure'],
            },
            # 【2026-10-14 二二轮】泥浆信息独立组（用户定案）：泥浆类型/密度/
            # 粘度/酸碱度·失水与泥浆·滤液·泥饼电阻率单列一块, 便于人工查看修改
            '泥浆信息': {
                '_说明': '泥浆类型/密度/粘度/酸碱度·失水与泥浆·滤液·泥饼电阻率'
                        '（LAS ~P 参数与知识文件提取；收集不到留空白）',
                'drilling_fluid_type': final['drilling_fluid_type'],
                'drilling_fluid_density': final['drilling_fluid_density'],
                'drilling_fluid_viscosity': final['drilling_fluid_viscosity'],
                'drilling_fluid_ph': final['drilling_fluid_ph'],
                'drilling_fluid_loss': final['drilling_fluid_loss'],
                'rm_meas_temp': final['rm_meas_temp'],
                'rmf_meas_temp': final['rmf_meas_temp'],
                'rmc_meas_temp': final['rmc_meas_temp'],
                'rm_bht': final['rm_bht'],
            },
            '测量记录': {
                '_说明': '表2 钻头尺寸/循环时间/最高记录温度/套管·井眼记录'
                        '（LAS ~P 参数与知识文件提取；收集不到留空白）',
                'bit_size': final['bit_size'],
                'time_since_circulation': final['time_since_circulation'],
                'max_record_temp': final['max_record_temp'],
                'casing_record': final['casing_record'],
                'borehole_record': final['borehole_record'],
            },
            '图表标题': {
                '_说明': '各图标题文字；空=程序默认（ql_title=快速解释图名, cmpt_title=综合图图名, '
                        'xplot_title=交汇图标题, footer_text=页脚）',
                'ql_title': final['ql_title'],
                'cmpt_title': final['cmpt_title'],
                'xplot_title': final['xplot_title'],
                'footer_text': final['footer_text'],
            },
            '免责声明': {
                '_说明': '快速解释页2免责声明文字（默认取图版样本文本; 可人工修改, '
                        '甲方格式变体时更新此值即可生效）',
                'disclaimer': final['disclaimer'],
            },
            '图例': {
                '_说明': 'LEGEND 图例文字（逗号分隔）；岩性空=由数据自动提取；'
                        '沉积微相/解释结论空=程序默认',
                'lithology_legend': final['lithology_legend'],
                'facies_legend': final['facies_legend'],
                'interpretation_legend': final['interpretation_legend'],
            },
            '曲线信息': {
                '_说明': 'LAS 曲线清单 MNEM:UNIT:说明（分号分隔, ~C 自动收集, 可修改补充）',
                'curves': final['curves'],
            },
            '深度比例尺': {
                '_说明': '深度道比例尺【2026-10-14 用户定案】：深度单位英尺=1:240、'
                        '公制=1:200；人工修改非空值后出图直接调用',
                'curve_scale_ft': final['curve_scale_ft'],
                'curve_scale_m': final['curve_scale_m'],
            },
            '流体颜色': {
                '_说明': '交会图流体统一色【2026-10-14 用户定案】气=红/油=深绿/水=蓝；'
                        '人工修改非空值后出图直接调用（#RRGGBB 或颜色名）',
                'gas_color': final['gas_color'],
                'oil_color': final['oil_color'],
                'water_color': final['water_color'],
            },
        }
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2),
                                 encoding='utf-8')
            print(f"  井信息: 已生成 {json_path}（可人工修改, 处理与出图直接调用）")
        except Exception as e:
            logger.warning("井信息 json 写入失败: %s", e)

    # ---- 应用: 非空值 → las_info（well/param 分流, 处理与可视化直接调用） ----
    _n = 0
    for _k, _sv in cfg.items():
        if _k in _PARAM_KEYS:
            param[_k] = str(_sv)
        else:
            well[_k] = str(_sv)
        _n += 1
    if not str(well.get('process_date') or '').strip():
        well['process_date'] = _today
    results['well_info_json'] = str(json_path)
    if well_dir:
        results.setdefault('well_dir', well_dir)
    # 【2026-10-21 R18】井眼程序（井深→钻头尺寸）进 results：
    # 绘图侧据此生成 BIT 曲线（用户："最后一个钻头 8.5in 作 bit，
    # 之间的部分按统一的井径绘制规则由颜色冲填"）。
    if _hole_list:
        results['hole_program'] = [
            {'bit': float(_s), 'from_md': (float(_hole_list[i - 1][1])
                                            if i > 0 else 0.0),
             'to_md': float(_t)}
            for i, (_s, _t) in enumerate(_hole_list)
        ]
        results['bit_size'] = _bit_size
    print(f"  井信息: 应用 {_n} 个字段（{json_path.name}）")
    return cfg

def quicklook_well(well_dir=None, config_file=None, gas_file=None):
    """quick look 快速解释主入口（嵌入 logInt 的功能之一）。

    流程:
      1. 解析井文件夹下所有文件知识（测井LAS、地质MD、气测、PDF、试油表）
      2. 以 logInt 主流程快速解释该井（QC→岩性→沉积相→解释→矿物→CSV/LAS）
      3. 出快速解释图（logvis 综合图，图头左上company/右上contractor；
         格式随甲方变化: config_file 指定格式文件, 未指定用井文件夹
         quicklook_config.json → F:\\360\\src\\quicklook_config.json 默认参考格式）
      4. 知识摘要写入 logKnow 知识库
    """
    import tkinter as tk
    from tkinter import filedialog
    _arg_cfg = config_file

    print("\n" + "=" * 70)
    print("         ⚡ quick look 快速解释模块")
    print("=" * 70)

    if not well_dir:
        _root = tk.Tk()
        _root.withdraw()
        well_dir = filedialog.askdirectory(title="选择井文件夹 (quick look 快速解释)")
        _root.destroy()
        if not well_dir:
            print("未选择文件夹，退出 quick look")
            return None
    well_dir = Path(well_dir)
    # 【2026-10-20 RASHIDPUR_13 用户定案】目标是数据文件（如 .../RP-13/
    # RASHIDPUR_13_..._MAIN.las）时自动取其所在井文件夹，绝不把文件当
    # 文件夹报"无效的井文件夹"错误
    if well_dir.is_file():
        print(f"  目标是数据文件，自动取其所在井文件夹: {well_dir.parent}")
        well_dir = well_dir.parent
    if not well_dir.is_dir():
        print(f"✗ 无效的井文件夹: {well_dir}")
        return None
    print(f"  井文件夹: {well_dir}")

    # ---- 1. 文件发现 ----
    las_main = _find_main_las(well_dir)
    if las_main is None:
        print("✗ 未找到主测井 LAS 文件，退出 quick look")
        return None
    md_files = sorted(well_dir.rglob('*.md'))
    pdf_files = sorted(well_dir.rglob('*.pdf'))
    xls_files = sorted(p for p in well_dir.rglob('*') if p.suffix.lower() in ('.xls', '.xlsx'))
    gas_files = sorted(p for p in well_dir.rglob('*') if p.is_file() and _is_gas_file(p))
    print(f"  发现资料: LAS={las_main.name} | MD知识={len(md_files)} | "
          f"PDF={len(pdf_files)} | 表格={len(xls_files)} | 气测/录井={len(gas_files)}")

    # ---- 2. 知识解析（井文件夹全文件知识） ----
    kb_md_parts = []
    _md_k = _extract_md_knowledge(md_files)
    if _md_k:
        kb_md_parts.append(_md_k)
    _pdf_k = _extract_pdf_knowledge(pdf_files)
    if _pdf_k:
        kb_md_parts.append(_pdf_k)
    _tbl_k = _extract_table_knowledge(xls_files)
    if _tbl_k:
        kb_md_parts.append(_tbl_k)
    if gas_files:
        kb_md_parts.append("### 气测/录井数据文件\n"
                           + '\n'.join(f"- {p.name}" for p in gas_files[:10]))
    _region, _well_extra = _guess_region(well_dir, None)
    # 注意: 图头字段补充(_enrich_well_info)需在 run_workflow 解释完成后、
    # 出图前执行（results 此时才有 las_info），见下文第5步前。

    # ---- 3. 快速解释（logInt 主流程: QC/计算/解释/分析仍走 logInt） ----
    print(f"\n  正在快速解释: {las_main.name} ...")
    # 【2026-10-14 用户定案】quick look 模式下 run_workflow 的 Step6 不代画：
    # 综合图/交会图/快速解释图均不出——快速解释图统一由第5步专用出图
    # （图版+图标+_enrich_well_info/collect_well_info 井信息齐全）。
    # 此前 Step6 内部 quicklook=True 代画过一张无配置版快速解释图，
    # 表1/表2/logo 缺失，与第5步重复出图（用户看到的"不对的快速解释图"）。
    global _PLOT_MODE
    _PLOT_MODE = 'quicklook'
    processor = WellLogProcessor()
    # 【2026-10-15 二五轮】数据选择界面选定的气测文件优先于按井名自动发现
    if gas_file:
        processor.data_loader.gas_file_selected = str(gas_file)
    results = processor.run_workflow(str(las_main))
    if not results:
        print("✗ 解释流程失败")
        return None

    # 用解释结果里的 LAS 井信息补全知识摘要
    las_info = results.get('las_info') or {}
    _region, _well_extra = _guess_region(well_dir, las_info)
    well_name = results.get('well_name') or well_dir.name
    las_well = (las_info.get('well') or {})
    header = (
        f"# {well_name} quick look 快速解释摘要\n\n"
        f"- 井名: {well_name}\n"
        f"- 地区: {_region or '未知'}{_well_extra}\n"
        f"- 主LAS: {las_main.name}\n"
        f"- 井文件夹: {well_dir}\n"
        f"- 资料清单: MD知识{len(md_files)}份 / PDF{len(pdf_files)}份 / "
        f"表格{len(xls_files)}份 / 气测{len(gas_files)}份\n"
        f"- 解释深度范围: {las_well.get('start_depth', '')} - "
        f"{las_well.get('stop_depth', '')} {las_well.get('depth_unit', '')}\n"
    )
    knowledge_md = header + '\n\n' + '\n\n'.join(kb_md_parts)

    # ---- 4. 知识入库 logKnow ----
    print("  写入 logKnow 知识库 ...")
    _kb_add_knowledge(well_name, knowledge_md)

    # ---- 5. 快速解释专用出图（格式参照 BET-1 MD200 PDF，可随甲方配置化） ----
    # 图头信息与标准综合图不同: Well Logging Interpretation Result Plot +
    # BOREHOLE/CASING RECORD + 井位表 + LEGEND 流体类别;
    # 左上/右上图标随井的业主动态更换; 图例顺序/颜色/类别与标题模板随甲方
    # 变化（井文件夹 quicklook_config.json > F:\360\src\quicklook_config.json 默认）。
    try:
        # 图头字段补充: LAS ~W 段缺失的 Company/Country/Area/套管记录
        # 从本井知识文件(MD/PDF/表格)提取, 保证 BOREHOLE/CASING RECORD 有值
        _enrich_well_info(results, kb_md_parts)
        # 【2026-10-14 井信息收集】LAS/录井图/地质设计 → <井名>info.json
        # （json 非空值优先; 首次自动提取回写, 可人工修改, 可视化直接读取）
        try:
            collect_well_info(results, well_dir)
        except Exception as e:
            logger.warning("井信息收集失败（不影响出图）: %s", e)
        import json as _json
        import logvis as _lvis
        _ql_cfg = None
        # 【2026-10-10 图版化】默认格式 = templates/qlpt.json 图版（原
        # quicklook_config.json 内容的图版化），作图直接调用图版；
        # 仅当用户在数据选择界面显式选择了甲方格式文件(config_file)时，
        # 才以该文件作为甲方变体覆盖图版（格式随甲方变化的入口）。
        if _arg_cfg:
            # 【2026-10-13】格式文件可以是 json 图版，也可以是甲方样本
            # PDF/图片（内部调 qlscan 一次扫描生成格式配置）
            _ql_cfg = _load_quicklook_config(_arg_cfg)
            if _ql_cfg is not None:
                print(f"  加载 quick look 出图格式配置: {_arg_cfg}"
                      f"（{_ql_cfg.get('format_name', '')}）")
        if _ql_cfg is None:
            print("  未选择格式文件, 按图版默认格式(templates/qlpt.json)出图")
        _co_logo, _ct_logo = _find_well_logos(well_dir)
        print(f"  生成快速解释图 (company={Path(_co_logo).name} / "
              f"contractor={Path(_ct_logo).name}) ...")
        _ql_plot = _lvis.visualize_quicklook_log(
            results.get('processed_data'),
            results, gas_data=results.get('gas_data'),
            company_logo=_co_logo, contractor_logo=_ct_logo,
            quicklook_config=_ql_cfg)
        if _ql_plot:
            # 【2026-10-14 只出一次 PDF】出图只交付一个单页 PDF（中间页/
            # 长图 PNG 均为临时产物不落盘），返回值即最终 PDF 路径
            print(f"  快速解释图: {_ql_plot}")
    except Exception as e:
        logger.warning("quick look 专用出图失败（不影响主流程结果）: %s", e)

    # ---- 6. 交付 ----
    out_dir = results.get('output_dir') or str(Path('output') / well_name)
    print("\n" + "=" * 70)
    print(f"  ✓ quick look 快速解释完成")
    print(f"  输出目录: {out_dir}")
    print("=" * 70)
    return results

# --- 主函数 ---
import sys

# =============================================================================
# 【2026-10-10】数据选择界面（出图格式选择）
# logvis 保留 4 种出图格式：综合图 / 交汇图 / 快速解释图 / 格式文件。
# 在 logInt 数据选择界面一次选定：格式 + 井文件夹（quick look/格式文件）
# 或 LAS 文件（综合图/交汇图）。未选（直接确定默认项）→ 按 quick look
# 默认格式和默认图标出图；取消 → 返回 None。
# =============================================================================
def select_run_mode():
    """数据选择界面：出图格式 + 目标（井文件夹 / LAS 文件）+ 气测文件一次选定。
    返回：
      ('quicklook', 井文件夹, None, 气测文件或None)   - 快速解释图（默认格式+默认图标）
      ('config',    井文件夹, 格式文件路径, 气测或None) - 格式文件（甲方格式）
      ('composite', LAS文件,  None, 气测文件或None)   - 综合图
      ('crossplot', LAS文件,  None, 气测文件或None)   - 交汇图
      None                                            - 用户取消
    气测文件为可选项（2026-10-15 二五轮）：未选时回退按井名自动发现。
    """
    try:
        import logvis as _lvis
        _fmts = list(_lvis.PLOT_FORMATS.items())
    except Exception:
        _fmts = [('quicklook', '快速解释图（Quick Look，默认格式+默认图标）'),
                 ('composite', '综合图（Composite Log）'),
                 ('crossplot', '交汇图（Crossplot）'),
                 ('config', '格式文件（Config File，甲方格式）')]
    _result = {}

    import tkinter as tk
    from tkinter import ttk, filedialog

    # 默认项固定为 quick look（未选 → 默认格式+默认图标），不随 dict 顺序
    _def_label = '快速解释图（Quick Look，默认格式+默认图标）'
    _labels = [v for _, v in _fmts]
    if _def_label not in _labels:
        _def_label = _labels[0]

    _win = tk.Tk()
    _win.title('logInt - 数据选择界面')
    _win.geometry('560x310')
    _win.resizable(False, False)

    tk.Label(_win, text='出图格式（未选默认快速解释图）',
             font=('Microsoft YaHei', 10)).pack(anchor='w', padx=16, pady=(16, 4))
    _var = tk.StringVar(value=_def_label)
    _cb = ttk.Combobox(_win, textvariable=_var, state='readonly',
                       values=_labels, width=46)
    _cb.pack(anchor='w', padx=16)

    tk.Label(_win, text='目标：井文件夹（快速解释图/格式文件）或 LAS 文件（综合图/交汇图）',
             font=('Microsoft YaHei', 9), fg='#555555').pack(anchor='w', padx=16, pady=(12, 4))
    _target_var = tk.StringVar(value='未选择')
    _lbl = tk.Label(_win, textvariable=_target_var, fg='#1a5c9e',
                    font=('Microsoft YaHei', 9), width=62, anchor='w')
    _lbl.pack(anchor='w', padx=16)

    # 【2026-10-15 二五轮】气测数据选择（可选，取消跳过；未选回退按井名自动发现）
    tk.Label(_win, text='气测数据（可选，未选则按井名自动发现）',
             font=('Microsoft YaHei', 9), fg='#555555').pack(anchor='w', padx=16, pady=(8, 2))
    _gas_var = tk.StringVar(value='未选择')
    _gas_lbl = tk.Label(_win, textvariable=_gas_var, fg='#1a5c9e',
                        font=('Microsoft YaHei', 9), width=62, anchor='w')
    _gas_lbl.pack(anchor='w', padx=16)

    def _pick_gas():
        _g = filedialog.askopenfilename(
            title='选择气测数据文件（取消跳过）',
            filetypes=[('气测数据文件', '*.las;*.csv;*.xlsx;*.xls;*.txt;*.dat'),
                       ('LAS 测井文件', '*.las'),
                       ('Excel 文件', '*.xlsx;*.xls'),
                       ('CSV 文件', '*.csv'),
                       ('文本文件', '*.txt;*.dat'),
                       ('所有文件', '*.*')])
        if _g:
            _gas_var.set(_g)
            _result['gas'] = _g

    # 【2026-10-20 RASHIDPUR_13 用户定案】井文件夹与数据文件分开记录，
    # 不再共用一个 target 互相覆盖（后点的把先点的顶掉 → "打架"）；
    # 确定时按"文件夹优先"统一解析，见 _ok()。
    def _upd_target():
        _f, _fl = _result.get('folder'), _result.get('file')
        if _f and _fl:
            _target_var.set(f'文件夹(优先): {Path(_f).name} | 文件: {Path(_fl).name}')
        elif _f:
            _target_var.set(f'井文件夹: {_f}')
        elif _fl:
            _target_var.set(f'数据文件: {_fl}（未选文件夹时按其所在目录执行）')
        else:
            _target_var.set('未选择')

    def _pick_folder():
        _d = filedialog.askdirectory(title='选择井文件夹')
        if _d:
            _result['folder'] = _d
            _upd_target()

    def _pick_file():
        _f = filedialog.askopenfilename(
            title='选择 LAS 文件',
            filetypes=[('LAS 测井文件', '*.las'), ('DLIS 测井文件', '*.dlis'),
                       ('所有文件', '*.*')])
        if _f:
            _result['file'] = _f
            _upd_target()

    _btn_row = tk.Frame(_win)
    _btn_row.pack(anchor='w', padx=16, pady=8)
    tk.Button(_btn_row, text='选择井文件夹', width=14,
              command=_pick_folder).pack(side='left', padx=(0, 8))
    tk.Button(_btn_row, text='选择 LAS 文件', width=14,
              command=_pick_file).pack(side='left')
    # 【2026-10-15 二五轮】气测数据选择按钮（可选）
    tk.Button(_btn_row, text='选择气测数据', width=14,
              command=_pick_gas).pack(side='left', padx=(8, 0))

    _ret = {}

    def _ok():
        _sel = _var.get()
        _fmt = None
        for _k, _v in _fmts:
            if _v == _sel:
                _fmt = _k
                break
        # 【2026-10-20 RASHIDPUR_13 用户定案】目标解析：井文件夹优先；
        # 未选文件夹但选了数据文件时——quicklook/config 模式自动取文件
        # 所在目录作为井文件夹（不再把文件当文件夹报"无效的井文件夹"）；
        # composite/crossplot 模式选了文件夹时自动在文件夹内定位主 LAS。
        _folder = _result.get('folder')
        _file = _result.get('file')
        _ql_like = _fmt in (None, 'quicklook', 'config')
        if _folder:
            _tgt = _folder
        elif _file:
            _tgt = str(Path(_file).parent) if _ql_like else _file
        else:
            _tgt = None
        if _tgt and not _ql_like and Path(_tgt).is_dir():
            _main = _find_main_las(Path(_tgt))
            if _main:
                print(f"  已从井文件夹自动定位主 LAS: {_main}")
                _tgt = str(_main)
        if not _tgt:
            # 未选目标 → 直接按默认 quick look 弹文件夹（与旧行为一致）
            _ret['mode'] = 'quicklook'
            _ret['target'] = None
            _ret['config'] = None
        elif _fmt == 'config':
            # 【2026-10-13】格式文件可为 json 图版，也可为甲方样本
            # PDF/图片（选样本则内部 qlscan 一次扫描自动生成格式配置）
            _cfg = filedialog.askopenfilename(
                title='选择格式文件：json 图版 / 甲方样本 PDF 或图片',
                filetypes=[('格式配置或样本', '*.json *.pdf *.png *.jpg *.jpeg'),
                           ('格式配置文件', '*.json'),
                           ('样本 PDF/图片', '*.pdf *.png *.jpg *.jpeg'),
                           ('所有文件', '*.*')])
            _ret['mode'] = 'config'
            _ret['target'] = _tgt
            _ret['config'] = _cfg
        else:
            _ret['mode'] = _fmt
            _ret['target'] = _tgt
            _ret['config'] = None
        _win.destroy()

    def _cancel():
        _ret['mode'] = None
        _win.destroy()

    tk.Button(_win, text='确定开始', width=14, command=_ok,
              bg='#1a5c9e', fg='white').pack(side='left', padx=(16, 8), pady=(4, 12))
    tk.Button(_win, text='取消', width=10, command=_cancel).pack(
        side='left', pady=(4, 12))

    _win.mainloop()
    if not _ret:
        return None
    _m = _ret.get('mode')
    if _m is None:
        return None
    # 【2026-10-15 二五轮】第4元 = 数据选择界面选定的气测文件（未选 None）
    return _m, _ret.get('target'), _ret.get('config'), _ret.get('gas')

def run_well_log_workflow(plot_mode='all', file_path=None, gas_file=None):
    """运行测井资料处理工作流
    plot_mode: 'all'(综合图+交汇图) / 'composite'(仅综合图) / 'crossplot'(仅交汇图)
    file_path: 外部传入 LAS 文件（数据选择界面/命令行），None 时回退 sys.argv/弹窗
    gas_file: 数据选择界面选定的气测文件（2026-10-15 二五轮），None 时回退自动发现
    """
    global _PLOT_MODE
    _PLOT_MODE = plot_mode if plot_mode in ('all', 'composite', 'crossplot') else 'all'
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
        # 【2026-10-15 二五轮】数据选择界面选定的气测文件优先于按井名自动发现
        if gas_file:
            processor.data_loader.gas_file_selected = str(gas_file)
        print("✓ 处理器初始化成功")
        logger.info("Processor created successfully")
        
        # 检查命令行参数（file_path 参数优先，其次 sys.argv，最后弹窗）
        if file_path:
            _fp = file_path
            logger.info(f"使用指定文件: {_fp}")
            print(f"使用文件: {_fp}")
            print("正在加载数据...")
            logger.info(f"Loading data file: {_fp}")
            data = processor.load_data(_fp)
            if data is None:
                logger.error("Failed to load data")
                show_error_message(
                    "数据加载失败",
                    f"无法加载文件: {_fp}",
                    "请检查文件是否存在且格式正确。"
                )
                return
            print("正在处理数据...")
            results = processor.run_workflow(_fp)
        elif len(sys.argv) > 1:
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
            print("请在弹出的对话框中选择数据文件...")
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
            
    except Exception as e:
        import traceback
        # 使用统一的异常处理
        handle_exception(type(e), e, e.__traceback__, "程序运行")
        print()
        print("程序异常退出。")

# ============================================================================
#  岩性识别自检（内建回归测试）
# ============================================================================
#  为什么内建而不是单独脚本：岩性识别是本程序的核心，判据一旦被后续
#  维护改回"单条件触发"，错误会静默地产生大量假岩性，而现场往往等到
#  出图后才发现。把判据的**结构约束**与**实测样例**固化成自检，
#  任何改动后跑一次即可知道有没有退化。
#
#  用法：
#      python logInt.py --selftest
#      python logInt.py --selftest BET-1
# ============================================================================

# BET-1 实测标定值（来自 LAS 与录井记录，勿随意改动）
SELFTEST_SAMPLES = {
    # 名称:        (GR,  ρ,   CNL, Δt,  PE,  RT)
    'coal_7067':      (90,  1.50, 50.0, 125.0, 1.50, 5.0),   # 煤核
    'coal_7638':      (80,  1.40, 52.0, 135.0, 2.00, 5.0),   # 最厚煤层
    'sand_7600':      (112, 2.49, 17.0, 79.0,  2.85, 13.0),  # GR<134.36谷值→砂岩（全井实测同点判砂岩）
    'sand_7620':      (107, 2.50, 18.5, 81.0,  3.10, 18.0),  # GR<134.36谷值→砂岩（全井实测同点判砂岩）
    'shale_7040':     (155, 2.45, 24.0, 90.0,  3.20, 6.0),   # 泥岩
    'sandstone_7660': (44,  2.27, 25.7, 86.0,  2.39, 9.6),   # 砂岩（低GR高阻）
    'carb_6716':      (137, 2.59, 24.0, 85.0,  4.83, 20.0),  # 曾误判灰岩→砂泥岩
    'carb_7466':      (137, 2.37, 34.0, 107.0, 3.60, 6.0),   # 曾误判灰岩→碳质泥岩
    'carb_8486':      (97,  2.64, 21.0, 82.0,  3.80, 15.0),  # 曾误判灰岩→砂岩
    'true_limestone': (25,  2.71, 3.0,  55.0,  4.80, 200.0), # 真灰岩，必须仍能识别
}

SELFTEST_EXPECT = {
    'coal_7067': 'coal', 'coal_7638': 'coal',
    'sand_7600': 'sandstone', 'sand_7620': 'sandstone', 'shale_7040': 'shale',
    'sandstone_7660': 'sandstone',
    'carb_6716': 'shale', 'carb_7466': 'carbonaceous_shale',
    'carb_8486': 'sandstone',
    'true_limestone': 'limestone',
}

# 本文件源码文本（结构断言用）。延迟读取，读取失败只影响自检、不影响主流程。
try:
    with open(os.path.abspath(__file__), encoding='utf-8') as _f:
        _SRC_TEXT = _f.read()
except Exception:
    _SRC_TEXT = ''

# 自检项清单（供静默模式复用）
_SELFTEST_GROUPS = None

def _selftest_groups():
    global _SELFTEST_GROUPS
    if _SELFTEST_GROUPS is None:
        _SELFTEST_GROUPS = [
            ('规则结构（多判据一致性）', selftest_rule_structure),
            ('BET-1 实测样例', selftest_samples),
            ('套管/水泥返高段处理', selftest_casing_not_marker),
            ('标志层厚度保留', selftest_marker_thickness),
            ('沉积相与相名一致性', selftest_facies_names),
            ('绘图道岩性来源', selftest_plot_uses_mc),
            ('剖面/岩性防翻回归', selftest_profile_no_flip),
        ]
    return _SELFTEST_GROUPS

def selftest_rule_structure():
    """检查每条规则都是"必要项 + 排除项 + M-of-K"，杜绝单条件触发。"""
    errors = []
    for r in LITHOLOGY_RULES:
        key = r['key']
        if not r.get('must'):
            errors.append(f'[{key}] 缺 must（必要项）—— 可被单条判据定性')
        if not r.get('core') or int(r.get('core_min', 0)) < 2:
            errors.append(f'[{key}] core_min<{2 if not r.get("core") else 2}'
                          f' —— 一致性项不足，单条判据即可定性')
        # 煤必须有高声波必要项（专家：不能只靠密度判煤）
        if key == 'coal':
            must_cols = {c[0] for c in r['must'] if isinstance(c, tuple)}
            if 'DT' not in must_cols:
                errors.append('[coal] 必须有 Δt 必要项 —— '
                              '"密度小于1.7就是煤"是错的')
        # 碳质泥岩必须有 GR 判别（与煤低伽马/砂岩更低伽马区分）
        if key == 'carbonaceous_shale':
            cols = {c[0] for c in r['must'] if isinstance(c, tuple)}
            cols |= {c[0] for c in r.get('core', [])}
            if 'GR' not in cols:
                errors.append('[carbonaceous_shale] 无 GR 判别 —— '
                              '无法与煤（低伽马）/砂岩区分')
        # 不得有单独以扩径比为唯一依据的排除项（煤层本身就扩径）
        for d in r.get('deny', []):
            cols = d.get('all') if isinstance(d, dict) else [d]
            if any(c[0] == 'CALR' for c in cols) and len(cols) == 1:
                errors.append(f'[{key}] 有单独的 CALR 排除项 —— '
                              f'煤层本身扩径达 1.5，会误杀煤层核心')
    return errors

def selftest_samples():
    """用 BET-1 实测参数验证判定结果。"""
    errors = []
    df = pd.DataFrame([
        {'MD': 7000.0 + i * 0.25, 'GR': v[0], 'DEN': v[1], 'CNL': v[2],
         'DT': v[3], 'PE': v[4], 'RT': v[5]}
        for i, (_k, v) in enumerate(SELFTEST_SAMPLES.items())])
    rec = LithologyRecognizer(df, depth_unit='ft', smooth=1,
                              pe_reliable=True, profile_type='sand_shale')
    # 自适应GR分界需要≥50点才用谷值法；本自检只有9个合成点，回退公式
    # 会把分界算到81.6（BET-1全井谷值=134.36），使 carb_8486(GR=97)
    # 被划到泥岩侧。注入全井真实分界，样本按全井同一阈值口径判定。
    rec.stats['GR_sand_max'] = 134.36
    rec.stats['GR_shale_min'] = 134.36
    got = rec.recognize()      # 用 recognize() 而非 run()：后者会合并薄层
    for i, name in enumerate(SELFTEST_SAMPLES):
        exp = SELFTEST_EXPECT[name]
        act = got[i]
        flag = 'OK ' if act == exp else 'FAIL'
        print(f'  [{flag}] {name:18s} 期望={exp:18s} 实际={act:18s} '
              f'置信={rec.confidence[i]:.1f}')
        if act != exp:
            errors.append(f'{name}: 期望 {exp}，实际 {act}；'
                          f'命中判据={rec.why[i]}')
    return errors

def selftest_casing_not_marker():
    """套管/水泥返高段不得被当成煤或碳质泥岩。"""
    errors = []
    # 水泥返高段必须由 detect_casing_interval 纳入套管掩码，
    # 而不是靠岩性规则里的单条扩径判据 —— 煤层本身扩径到 1.5。
    i = _SRC_TEXT.index('def detect_casing_interval')
    # 到下一个顶层函数为止（不能只切到 detect_well_profile_type，
    # 中间还有若干辅助函数，水泥返高逻辑就在其中）
    body = _SRC_TEXT[i:i + 12000]
    if '水泥返高' not in body:
        errors.append('detect_casing_interval 缺少水泥返高段识别')
    elif '_shoe + 60.0' not in body:
        errors.append('水泥返高段识别未限定在套管鞋以下影响带内')
    return errors

def selftest_marker_thickness():
    """煤与碳质泥岩是标志层，薄层必须保留。"""
    errors = []
    # BET-1 实测：7 个煤层段厚 2.5-6.0 ft，碳质泥岩薄层仅 1.25-1.5 ft
    for key, lim in (('coal', 1.0), ('carbonaceous_shale', 1.5)):
        v = MIN_THICKNESS_FT.get(key)
        if v is None:
            errors.append(f'MIN_THICKNESS_FT 缺少 {key}')
        elif v > lim:
            errors.append(f'{key} 最小厚度 {v} ft 过大 —— '
                          f'实测该类薄层 1.25-1.5 ft，会被当毛刺抹平')
    # 段厚计算必须加上采样间隔，否则 6 点(0.25ft采样)=1.25ft < 1.5ft 阈值
    j = _SRC_TEXT.index('def _merge_thin')
    if '(md[b] - md[a]) + _step' not in _SRC_TEXT[j:j + 3000]:
        errors.append('_merge_thin 段厚未加采样间隔修正 `+ _step`')
    return errors

def selftest_facies_names():
    """沉积相命名：煤与碳质泥岩同属沼泽相。"""
    errors = []
    # 用**行首精确匹配**而非子串包含 —— 否则本自检代码里引用这些名字
    # 的断言语句本身会被匹配到（自指误判）。
    import re as _re
    for want in ("return 'swamp_peatro'", "return 'swamp_carbonaceous'"):
        if not _re.search(r'^\s+' + _re.escape(want) + r'\s*$',
                          _SRC_TEXT, _re.M):
            errors.append(f'logInt.py 缺少 {want}')
    for bad, why in (("return 'carbonaceous_mud'",
                      '碳质泥岩属沼泽相组（swamp_carbonaceous）'),
                     ("return 'floodplain'",
                      '与 flood_plain 是同一相，两种拼写会让图例裂成两项')):
        if _re.search(r'^\s+' + _re.escape(bad) + r'\s*$', _SRC_TEXT, _re.M):
            errors.append(f'仍有旧的 {bad} —— {why}')
    return errors

def selftest_plot_uses_mc():
    """绘图读的 LITHOLOGY 必须来自多判据识别器（同步守卫）。"""
    errors = []
    # 【2026-10-08 设计更新】岩性判定统一归多判据识别器后，logInt 在识别
    # 完成时把 LITHOLOGY 同步为同一结果（data['LITHOLOGY'] = _lith），
    # 绘图直接读 LITHOLOGY 即可，不再要求其源码出现 LITHOLOGY_MC。
    # 本自检改为守护 logInt 侧的同步赋值 —— 同步丢失才会退回老链路。
    import re as _re
    if not _re.search(r"data\['LITHOLOGY'\]\s*=\s*_lith", _SRC_TEXT):
        errors.append("logInt.py 缺少 data['LITHOLOGY'] = _lith 同步 —— "
                      '绘图读 LITHOLOGY 会退回老链路结果')
    # 相名拼写统一（两种拼写会让图例裂成两项）—— 绘图侧同样守护
    vis = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'logvis.py')
    if os.path.exists(vis):
        with open(vis, encoding='utf-8') as f:
            vsrc = f.read()
        if _re.search(r"['\"]floodplain['\"]", vsrc):
            errors.append("logvis.py 仍有 'floodplain' 拼写 —— "
                          "应统一为 'flood_plain'（同一相的两种拼写）")
    return errors

def selftest_profile_no_flip():
    """剖面/岩性防翻回归【2026-10-15】：砂泥岩⇄碳酸盐岩三次反复翻面
    （2026-07-06 碳酸盐井误判砂岩 / 2026-10-07 BET-1 套管段判灰岩 /
    2026-10-15 3-SPS-111D 碳酸盐井判砂泥岩）的共同根因 = 绝对阈值
    单判据跨越岩性系统做强判定。本组自检守护三类防翻机制：
    VOL 第一优先判据、PE 矿物铁证、剖面镜像守门（碳酸盐剖面
    sandstone need+2 / 无VOL硬石膏 DEN>2.92 提权）。"""
    errors = []
    rs = np.random.RandomState(42)
    n = 80

    # ---- 场景1：3-SPS-111D 元素测井特征 → carbonate（VOL 第一优先） ----
    df1 = pd.DataFrame({
        'MD': 6425.0 + np.arange(n) * 0.15,
        'GR': 90 + rs.normal(0, 2, n),
        'DEN': 2.63 + rs.normal(0, 0.02, n),
        'CNL': 3 + rs.normal(0, 0.5, n),
        'VOL_CALCITE': 0.63 + rs.normal(0, 0.02, n),
        'VOL_DOLOM': 0.16 + rs.normal(0, 0.02, n),
        'VOL_ANHY': 0.06 + rs.normal(0, 0.01, n),
    })
    ptype, info = detect_well_profile_type(df1, 'SELFTEST-1')
    _ok = ptype == 'carbonate'
    print(f'  [{"OK " if _ok else "FAIL"}] 场景1 3-SPS-111D元素测井 期望=carbonate '
          f'实际={ptype} ({str(info.get("summary", ""))[:46]})')
    if not _ok:
        errors.append(f'场景1: 期望 carbonate，实际 {ptype}')

    # ---- 场景2：BET-1 型砂泥岩（GR 双峰交替/CNL高/密度低）→ sand_shale ----
    df2 = pd.DataFrame({
        'MD': 6400.0 + np.arange(n) * 0.25,
        'GR': np.where(np.arange(n) % 2 == 0, 60.0, 140.0) + rs.normal(0, 2, n),
        'DEN': 2.42 + rs.normal(0, 0.02, n),
        'CNL': 36 + rs.normal(0, 2, n),
        'PE': 3.05 + rs.normal(0, 0.1, n),
    })
    ptype, info = detect_well_profile_type(df2, 'SELFTEST-2')
    _ok = ptype == 'sand_shale'
    print(f'  [{"OK " if _ok else "FAIL"}] 场景2 BET-1型砂泥岩 期望=sand_shale '
          f'实际={ptype} (ss={info.get("ss_score")}, cb={info.get("cb_score")})')
    if not _ok:
        errors.append(f'场景2: 期望 sand_shale，实际 {ptype}')

    # ---- 场景3：无VOL泥质灰岩（GR90/DEN2.63/CNL3/PE5.16）→ carbonate ----
    # ss=0.4(GR>70降权)+0.8(DEN2.63)=1.2；cb=2.0(低CNL)+1.5(PE方解石)=3.5
    # 【回归意义】修复前 GR P50=90 曾被绝对伽马带偏成 mixed→按砂泥岩处理
    df3 = pd.DataFrame({
        'MD': 6425.0 + np.arange(n) * 0.15,
        'GR': 90 + rs.normal(0, 2, n),
        'DEN': 2.63 + rs.normal(0, 0.01, n),
        'CNL': 3 + rs.normal(0, 0.5, n),
        'PE': 5.16 + rs.normal(0, 0.1, n),
    })
    ptype, info = detect_well_profile_type(df3, 'SELFTEST-3')
    _ok = ptype == 'carbonate'
    print(f'  [{"OK " if _ok else "FAIL"}] 场景3 无VOL泥质灰岩 期望=carbonate '
          f'实际={ptype} (ss={info.get("ss_score")}, cb={info.get("cb_score")})')
    if not _ok:
        errors.append(f'场景3: 期望 carbonate，实际 {ptype}')

    # ---- 场景4：carbonate剖面下泥质灰岩不得翻成砂岩（镜像守门） ----
    # 注入 GR_sand_max=105 模拟单峰GR回退：无守门时 sandstone 5.5 分
    # > limestone 5.0 会翻成砂岩；守门后 sandstone need=5(命中仅4)拦下
    df4 = pd.DataFrame({
        'MD': 6425.0 + np.arange(n) * 0.15,
        'GR': 90 + rs.normal(0, 2, n),
        'DEN': 2.65 + rs.normal(0, 0.01, n),
        'CNL': 2 + rs.normal(0, 0.4, n),
        'DT': 58 + rs.normal(0, 1.5, n),
        'PE': 5.1 + rs.normal(0, 0.1, n),
        'RT': 45 + rs.normal(0, 5, n),
    })
    rec4 = LithologyRecognizer(df4, depth_unit='m', smooth=1,
                               pe_reliable=True, profile_type='carbonate')
    rec4.stats['GR_sand_max'] = 105.0
    got4 = rec4.recognize()
    _n_lime = int((got4 == 'limestone').sum())
    _n_sand = int((got4 == 'sandstone').sum())
    _ok = _n_lime >= int(n * 0.9) and _n_sand == 0
    print(f'  [{"OK " if _ok else "FAIL"}] 场景4 碳酸盐剖面泥质灰岩 '
          f'期望=limestone 实际=limestone×{_n_lime}/sandstone×{_n_sand}')
    if not _ok:
        errors.append(f'场景4: 期望全 limestone，实际 limestone×{_n_lime}'
                      f'/sandstone×{_n_sand}（镜像守门失效）')

    # ---- 场景5：无VOL纯硬石膏不得被灰岩压过（DEN>2.92 提权） ----
    # anhydrite 8.3(DEN项3.5) > limestone 7.5；修复前 6.3 < 7.5 翻灰岩
    df5 = pd.DataFrame({
        'MD': 6425.0 + np.arange(n) * 0.15,
        'GR': 8 + rs.normal(0, 1, n),
        'DEN': 2.98 + rs.normal(0, 0.01, n),
        'CNL': 0.5 + rs.normal(0, 0.2, n),
        'DT': 50 + rs.normal(0, 1, n),
        'PE': 5.05 + rs.normal(0, 0.05, n),
        'RT': 120 + rs.normal(0, 10, n),
    })
    rec5 = LithologyRecognizer(df5, depth_unit='m', smooth=1,
                               pe_reliable=True, profile_type='carbonate')
    got5 = rec5.recognize()
    _n_ahy = int((got5 == 'anhydrite').sum())
    _n_lime = int((got5 == 'limestone').sum())
    _ok = _n_ahy >= int(n * 0.9) and _n_lime == 0
    print(f'  [{"OK " if _ok else "FAIL"}] 场景5 无VOL纯硬石膏 '
          f'期望=anhydrite 实际=anhydrite×{_n_ahy}/limestone×{_n_lime}')
    if not _ok:
        errors.append(f'场景5: 期望全 anhydrite，实际 anhydrite×{_n_ahy}'
                      f'/limestone×{_n_lime}（DEN提权失效）')

    # ---- 场景6：矿物主控分段定性（VOL_CALCITE→灰岩 / VOL_ANHY→硬石膏） ----
    df6 = pd.DataFrame({
        'MD': 6425.0 + np.arange(n) * 0.15,
        'GR': 20 + rs.normal(0, 2, n),
        'DEN': 2.68 + rs.normal(0, 0.02, n),
        'CNL': 1.5 + rs.normal(0, 0.3, n),
        'VOL_CALCITE': np.concatenate([np.full(n // 2, 0.62),
                                       np.full(n - n // 2, 0.02)]),
        'VOL_DOLOM': np.full(n, 0.02),
        'VOL_ANHY': np.concatenate([np.full(n // 2, 0.02),
                                    np.full(n - n // 2, 0.85)]),
    })
    rec6 = LithologyRecognizer(df6, depth_unit='m', smooth=1,
                               pe_reliable=True, profile_type='carbonate')
    got6 = rec6.recognize()
    _ok = (int((got6[:n // 2] == 'limestone').sum()) == n // 2 and
           int((got6[n // 2:] == 'anhydrite').sum()) == n - n // 2)
    print(f'  [{"OK " if _ok else "FAIL"}] 场景6 矿物主控分段 '
          f'期望=前半limestone/后半anhydrite 实际={got6[0]}/{got6[-1]}')
    if not _ok:
        errors.append(f'场景6: 矿物主控失效 实际前半={got6[0]} 后半={got6[-1]}')

    return errors

def run_selftest(verbose=True):
    """运行全部自检。返回错误列表（空 = 全部通过）。"""
    total = []
    if verbose:
        print('=' * 68)
        print('岩性识别自检（内建回归测试）')
        print('=' * 68)
        for title, fn in _selftest_groups():
            print(f'\n[{title}]')
            errs = fn()
            for e in errs:
                print('  [FAIL]', e)
            if not errs:
                print('  [OK ]')
            total += errs
        print('\n' + '=' * 68)
        if total:
            print(f'自检失败 {len(total)} 项：')
            for e in total:
                print('  -', e)
        else:
            print('自检全部通过：岩性识别为多判据一致性判定，非单条件触发')
        print('=' * 68)
        return total
    for _t, fn in _selftest_groups():
        total += fn()
    return total

def calculate_reg_indicators(data, gas_data=None):
    """REG 法综合气层指示（2026-10-21 用户最终命名 REG）。

    三证据加权：
      RTI = (dt-dt_base)/dt_base - log10(R/R_base)   电阻率-声波重叠，阈值0.20，权重0.40
      NDI = phi_D - phi_N                             中子-密度挖掘效应，阈值0.05，权重0.35
      GSI = log10(TG/TG_base)                         气测全烃异常，阈值0.5，权重0.25
      CGI = 0.40*RTIt + 0.35*NDIt + 0.25*GSIt         归一化后clip 0~1.5，CGI>=0.6 判气层
    """
    import numpy as np
    import pandas as pd
    if data is None or len(data) == 0:
        return data
    out = data.copy()

    # 【2026-10-21】复用 logInt DataLoader.curve_aliases 的别名体系 + 模糊匹配
    # 不再硬编码具体列名，避免不同井/服务商命名差异漏识别
    _ALIASES = {
        'rt': ['RT','LLD','RLLD','RILD','ILD','ILD_DEEP','RILD_DEEP',
               'RDEEP','RLA5','AT90','AF90','RLA1','RLA2','RLA3','RLA4',
               'HT01','HT02','HT03','HT04','HT05','HT06',
               'AT10','AT20','AT30','AT60','AT90_RAW','RD',
               'R90','RLD','DEEP_RES','DEEP_RESISTIVITY','RES_DEEP',
               'RT_HRLT','RT_DEEP','ILD_RAW','LLD_RAW'],
        'ac': ['AC','DT','DTCO','Sonic','SONIC','DT_COMP','AC_COMP',
               'ACOUSTIC','DTC','DT24','DTSM','DTL','DT_SHEAR',
               'DT4P','DT4S','DTCO_SLOW','AC_SLOW','DTP','DTS',
               'delta_t','DELTAT','DTT','DT_COMPRESSIONAL'],
        'nphi': ['NPHI','CNL','NEUTRON','PHIN','NPHI_CORR','CNL_CORR',
                 'PORN','TNPH','NPOR','NPH','NEU','NEUT','PHI_N',
                 'NPHI_LS','NPHI_SS','NPHIL','HEN','NEUTRON_POROSITY',
                 'CNCF','CNC'],
        'den': ['DEN','RHOB','DENSITY','RHOB_CORR','RHOB_COMP','RHO',
                'RHOZ','RHOM','DRHO','RHOB_RT','ZDEN','DEN_COMP',
                'DEN_CORR','BULK_DENSITY','ROB','DEN1','LDEN'],
        'gr': ['GR','GR_RAW','GR_COMP','GR_CORR','GAMMA','GRAP',
               'GR_EDTC','SGR','CGR','ECGR','HCGR','GRKT',
               'GRAT','GRBH','NGAM','GAMMA_RAY','GAMMARAY'],
    }
    # 模糊关键词（小写包含即命中）：处理拼写差异（RAL5 vs RLA5, DTTC vs DTT）
    _FUZZY = {
        'rt':   ['rla','ral','at90','deep','ild','lld','r90','resd'],
        'ac':   ['dt','ac','sonic','deltat','dtt'],
        'nphi': ['nphi','cnl','cnc','neu','npor','phin'],
        'den':  ['den','rho','density','zden','lden'],
        'gr':   ['gr','gamma'],
    }

    def _pick_curve(kind):
        cols_upper = {c.upper().strip(): c for c in out.columns}
        # 1. 精确别名匹配
        for alias in _ALIASES.get(kind, []):
            if alias.upper() in cols_upper:
                return cols_upper[alias.upper()]
        # 2. 模糊包含匹配（统一小写比较）
        for col_up, col_orig in cols_upper.items():
            col_low = col_up.lower()
            for kw in _FUZZY.get(kind, []):
                if kw.lower() in col_low:
                    # 排除明显误命中：gr 不能匹配到 GRDEN（密度伽马，不是自然伽马）
                    if kind == 'gr' and col_up == 'GRDEN':
                        continue
                    return col_orig
        return None

    r_col   = _pick_curve('rt')
    dt_col  = _pick_curve('ac')
    nphi_col= _pick_curve('nphi')
    rhob_col= _pick_curve('den')
    gr_col  = _pick_curve('gr')
    logger.info("REG 列识别: R=%s DT=%s NPHI=%s RHOB=%s GR=%s",
                r_col, dt_col, nphi_col, rhob_col, gr_col)

    # 基线：GR>=Q75 泥岩段中位数
    gr = pd.to_numeric(out[gr_col], errors='coerce') if gr_col else None
    if gr is not None and gr.notna().sum() > 50:
        base_mask = gr >= gr.quantile(0.75)
    else:
        base_mask = pd.Series(True, index=out.index)

    # RTI
    if r_col and dt_col:
        R  = pd.to_numeric(out[r_col], errors='coerce')
        dt = pd.to_numeric(out[dt_col], errors='coerce')
        Rb  = R[base_mask].median()
        dtb = dt[base_mask].median()
        if pd.notna(Rb) and Rb > 0 and pd.notna(dtb) and dtb > 0:
            with np.errstate(divide='ignore', invalid='ignore'):
                rti = (dt - dtb)/dtb - np.log10(R/Rb)
            out['RTI'] = rti
            logger.info("REG RTI: R=%s DT=%s R_base=%.2f dt_base=%.1f", r_col, dt_col, Rb, dtb)
        else:
            out['RTI'] = np.nan
            logger.info("REG RTI: 基线无效, 跳过")
    else:
        out['RTI'] = np.nan
        logger.info("REG RTI: 缺 R 或 DT 曲线, 跳过")

    # NDI
    if rhob_col and nphi_col:
        rho = pd.to_numeric(out[rhob_col], errors='coerce')
        nph_raw = pd.to_numeric(out[nphi_col], errors='coerce')
        # CNL/CNCF/NPOR 行业惯例是百分数（0~40），统一转成小数
        # 若中位数 > 1，则认为是百分数，除以 100
        _med = nph_raw.median()
        if pd.notna(_med) and _med > 1.0:
            nph = nph_raw / 100.0
            logger.info("REG NDI: %s 按百分数(中位=%.1f%%)已转小数", nphi_col, _med)
        else:
            nph = nph_raw
        phiD = (2.65 - rho) / (2.65 - 1.0)
        ndi_raw = phiD - nph
        # NDI 异常值：相对泥岩基线（GR Q75 段）的抬升量
        # 泥岩段 nph 偏高（含氢指数高）、phiD 偏低，ndi_raw 普遍为负
        # 气层时中子降低、密度降低，ndi_raw 向 0 或正方向抬升
        if gr is not None and base_mask.sum() > 20:
            ndi_base = ndi_raw[base_mask].median()
        else:
            ndi_base = ndi_raw.median()
        ndi = ndi_raw - ndi_base
        out['NDI'] = ndi
        logger.info("REG NDI: RHOB=%s NPHI=%s NDI_base=%.3f", rhob_col, nphi_col, ndi_base)
    else:
        out['NDI'] = np.nan
        logger.info("REG NDI: 缺 NPHI 或 RHOB, 跳过")

    # GSI
    out['GSI'] = np.nan
    if gas_data is not None:
        tg_col = _pick_in = None
        for c in gas_data.columns:
            cu = c.upper().strip()
            if cu in ('TG','TGAS','TOTALGAS','TOTAL_GAS'):
                tg_col = c; break
        if tg_col and 'MD' in gas_data.columns:
            tg = pd.to_numeric(gas_data[tg_col], errors='coerce')
            gmd = pd.to_numeric(gas_data['MD'], errors='coerce')
            if len(tg.dropna()) > 10:
                tg_base = tg[base_mask.reindex(gas_data.index).fillna(False)].median() if base_mask.sum() > 10 else tg.median()
                if pd.notna(tg_base) and tg_base > 0:
                    gsi = np.log10(tg / tg_base)
                    # 对齐深度
                    gsi_series = pd.Series(np.nan, index=out.index)
                    # 简单插值对齐
                    try:
                        gsi_on_main = np.interp(pd.to_numeric(out['MD'],errors='coerce').values,
                                                gmd.values, gsi.values, left=np.nan, right=np.nan)
                        out['GSI'] = gsi_on_main
                    except Exception:
                        pass
                    logger.info("REG GSI: TG=%s tg_base=%.4f", tg_col, tg_base)
                else:
                    logger.info("REG GSI: tg_base=0, 跳过")
            else:
                logger.info("REG GSI: 气测点太少, 跳过")
    else:
        logger.info("REG GSI: 无气测数据, 跳过")

    # CGI 加权综合
    def _norm(s, thr):
        v = pd.to_numeric(s, errors='coerce') / thr
        return v.clip(0, 1.5)
    rti_n = _norm(out['RTI'], 0.20)
    ndi_n = _norm(out['NDI'], 0.05)
    gsi_n = _norm(out['GSI'], 0.5)
    out['CGI'] = 0.40*rti_n + 0.35*ndi_n + 0.25*gsi_n
    n_gas = int((out['CGI'] >= 0.6).sum())
    logger.info("REG CGI: 综合完成, CGI>=0.6 层数=%d", n_gas)
    return out

def rejudge_gas_by_reg_below_seal(data):
    """【2026-10-27 R26 用户定案】盐下气层 REG 证据复核（按层）。

    背景：INTERPRETATION_RULES 的 GAS 规则只看 Sw<0.5+POR>=0.06+RT>50，
    蒸发岩盖层（盐岩/硬石膏）下大量储层因 RT 高被逐点判成 GAS，但 REG 法
    （RTI/NDI/GSI/CGI，calculate_reg_indicators）无气层异常特征——
    用户："盐岩下解释成气层没有依据，REG 方法没有明显异常特征，解释还是
    应该按 logInt 流程按层解释。"

    规则（按层，非逐点）：盖层（halite/anhydrite/gypsum/盐/膏）顶之下的
    GAS 点按连续段分层（间隔>1.5m 断层），逐层核算 REG 证据：
      层内 CGI 中位数 >= 0.6，或 RTI/NDI/GSI 三项中至少两项达阈值
      （RTI>=0.20 / NDI>=0.05 / GSI>=0.5）
    → 维持 GAS；否则整层降为 OIL（保留 Sw/POR/RT 的含油气证据，只撤
    无依据的"气"字）。逐层打印证据表，供交会图/综合图核对。
    """
    import numpy as np
    import pandas as pd
    if data is None or len(data) == 0 or 'INTERPRETATION' not in data.columns:
        return data, 0
    if 'LITHOLOGY' not in data.columns or 'MD' not in data.columns:
        return data, 0
    _md = pd.to_numeric(data['MD'], errors='coerce')
    _ls = data['LITHOLOGY'].astype(str).str.lower()
    _seal = _ls.str.contains('halite|anhydrite|gypsum|salt|盐|膏', na=False)
    if not _seal.any():
        return data, 0
    _seal_top = float(_md[_seal].min())
    _itp = data['INTERPRETATION'].astype(str)
    _gas = (_itp == 'GAS') & (_md > _seal_top)
    _gas = _gas.fillna(False)
    n_gas = int(_gas.sum())
    if n_gas == 0:
        logger.info('盐下气层REG复核: 盖层顶 %.1fm 之下无 GAS 点', _seal_top)
        return data, 0
    out = data.copy()
    _rows = np.where(_gas.values)[0]
    _mds = _md.values[_rows]
    _order = np.argsort(_mds)
    _rows = _rows[_order]
    _mds = _mds[_order]
    _brk = [0] + [i for i in range(1, len(_rows))
                  if _mds[i] - _mds[i - 1] > 1.5] + [len(_rows)]
    _col_itp = out.columns.get_loc('INTERPRETATION')
    _col_itp2 = out.columns.get_loc('ITP') if 'ITP' in out.columns else None
    n_demoted = 0
    for a, b in zip(_brk[:-1], _brk[1:]):
        _seg = _rows[a:b]

        def _med(col):
            if col in out.columns:
                return float(pd.to_numeric(
                    out.iloc[_seg][col], errors='coerce').median())
            return float('nan')

        _cgi, _rti, _ndi, _gsi = _med('CGI'), _med('RTI'), _med('NDI'), _med('GSI')
        _hits = sum(1 for v, t in ((_rti, 0.20), (_ndi, 0.05), (_gsi, 0.5))
                    if np.isfinite(v) and v >= t)
        _ok = (np.isfinite(_cgi) and _cgi >= 0.6) or _hits >= 2
        if not _ok:
            out.iloc[_seg, _col_itp] = 'OIL'
            if _col_itp2 is not None:
                out.iloc[_seg, _col_itp2] = 'OIL'
            n_demoted += len(_seg)
        logger.info(
            '盐下气层REG复核 %.1f-%.1fm n=%d: CGI=%.2f RTI=%.2f NDI=%.3f '
            'GSI=%.2f 达标项=%d → %s',
            float(_mds[a]), float(_mds[b - 1]), len(_seg),
            _cgi if np.isfinite(_cgi) else -9.0,
            _rti if np.isfinite(_rti) else -9.0,
            _ndi if np.isfinite(_ndi) else -9.0,
            _gsi if np.isfinite(_gsi) else -9.0,
            _hits, '维持GAS' if _ok else '降为OIL(无REG气层证据)')
    logger.info('盐下气层REG复核: GAS %d 点中 %d 点降为 OIL', n_gas, n_demoted)
    return out, n_demoted


def layered_interpretation_by_cutoff(data, min_thick=0.4, thin_absorb=0.6,
                                     gap_break=0.5):
    """【2026-10-27 R27 用户要求】按孔隙度截止值分层解释（分层聚合）。

    背景：主流程逐点解释产出碎片化结论段（如 5 点 OIL 夹在 NonReservoir
    之间），用户："解释感觉没有按照孔隙度截止值进行分层"。孔隙度截止
    （碳酸盐岩 6% 等）在逐点储层过滤时已严格执行（OIL/GAS 点全部
    POR>=0.06），缺的是"分层"——本函数把储层点按连续段聚合成层：
      - 层边界 = 储层资格（孔隙度截止/岩性过滤）变化处 + 深度间断(>gap_break m)；
      - 层内结论 = 层内逐点结论多数票（保留 rejudge/盐下 GAS 复核的成果）；
      - 【R29】干层（储层岩性但 POR<截止=无效储层）与有效储层（油气水）
        性质转折处强制切层——干层段独立成层, 与上下油气层分开；
      - 整层统一赋值（INTERPRETATION 与 ITP 同步）；
      - 薄层(<min_thick m)沿用前一层结论（首层用次层）；薄层(<thin_absorb m)
        夹在同结论两 层之间时并入（按流体分布规律整合）。
    非储层/未定义点保持原标签——截止口径不被破坏。逐层统计表落日志。
    返回 (data, 改写点数)。
    """
    import numpy as np
    import pandas as pd
    if data is None or len(data) == 0 or 'INTERPRETATION' not in data.columns:
        return data, 0
    if 'MD' not in data.columns:
        return data, 0
    out = data.copy()
    _md = pd.to_numeric(out['MD'], errors='coerce')
    # 【R27 修复】pandas 3.x str dtype 下 astype(str) 保留 NaN → NaN 点
    # 会被误判为储层点参与多数票（L01 全 NaN 段层标签='nan'）。先 fillna。
    _itp = out['INTERPRETATION'].fillna('').astype(str).str.strip().str.upper()
    _res = ~_itp.isin({'NONRESERVOIR', 'UNDEFINED', 'TIGHT',
                       'NAN', 'NONE', ''})
    _res = _res.fillna(False).values
    _rows = np.where(_res)[0]
    if len(_rows) == 0:
        logger.info('按层解释: 无储层点, 跳过')
        return out, 0
    _mds = _md.values[_rows]
    # 【R29 用户定案】干层(无效储层)与油气水层(有效储层)性质不同——
    # 层边界除深度间断外, 还要落在两者转折处（干层段独立成层, 与上下
    # 油气层分开, 不混入同一层）
    _kind = np.where(_itp.values[_rows] == 'DRY', 'DRY', 'EFF')
    _brk = [0] + [i for i in range(1, len(_rows))
                  if _mds[i] - _mds[i - 1] > gap_break
                  or _kind[i] != _kind[i - 1]] + [len(_rows)]
    layers = []
    for a, b in zip(_brk[:-1], _brk[1:]):
        _seg = _rows[a:b]
        layers.append({'rows': _seg,
                       'top': float(_mds[a]), 'bot': float(_mds[b - 1])})
    # ① 层内多数票（干层段固定 DRY；有效储层段对油气水投票）

    def _kind_of(lab):
        return 'DRY' if str(lab) == 'DRY' else 'EFF'

    for L in layers:
        labs = _itp.values[L['rows']]
        if _kind_of(labs[0]) == 'DRY':
            L['lab'] = 'DRY'
        else:
            vals, cnts = np.unique(labs, return_counts=True)
            L['lab'] = str(vals[int(np.argmax(cnts))])
    # ② 薄层并入前层（首层并入次层）——【R29】仅同性质（干层↔干层、
    #    有效储层↔有效储层）才并入, 干层不并入油气层
    for i, L in enumerate(layers):
        if (L['bot'] - L['top']) < min_thick:
            _nb = layers[i - 1] if i > 0 else (
                layers[1] if len(layers) > 1 else None)
            if _nb is not None and _kind_of(L['lab']) == _kind_of(_nb['lab']):
                L['lab'] = _nb['lab']
    # ③ 流体分布规律整合：薄层夹在同结论邻层之间 → 并入（同样限同性质）
    for i in range(1, len(layers) - 1):
        L = layers[i]
        if (L['bot'] - L['top']) < thin_absorb \
                and _kind_of(L['lab']) == _kind_of(layers[i - 1]['lab']) \
                and _kind_of(L['lab']) == _kind_of(layers[i + 1]['lab']) \
                and layers[i - 1]['lab'] == layers[i + 1]['lab'] \
                and L['lab'] != layers[i - 1]['lab']:
            L['lab'] = layers[i - 1]['lab']
    # ④ 整层赋值
    _col = out.columns.get_loc('INTERPRETATION')
    _col2 = out.columns.get_loc('ITP') if 'ITP' in out.columns else None
    n_chg = 0

    def _med(seg, c):
        if c in out.columns:
            v = pd.to_numeric(out.iloc[seg][c], errors='coerce').dropna()
            if len(v):
                return float(v.median())
        return float('nan')

    for k, L in enumerate(layers):
        seg = L['rows']
        old = out.iloc[seg, _col].astype(str).str.strip().str.upper().values
        chg = int((old != L['lab']).sum())
        n_chg += chg
        out.iloc[seg, _col] = L['lab']
        if _col2 is not None:
            out.iloc[seg, _col2] = L['lab']
        _pm = _med(seg, 'POR') if 'POR' in out.columns else _med(seg, 'PHI')
        logger.info(
            '按层解释 L%02d %.1f-%.1fm 厚%.1fm n=%d POR=%.3f Sw=%.3f RT=%.1f'
            ' → %s (改%d点)',
            k + 1, L['top'], L['bot'], L['bot'] - L['top'], len(seg),
            _pm if np.isfinite(_pm) else -1.0,
            _med(seg, 'Sw') if np.isfinite(_med(seg, 'Sw')) else -1.0,
            _med(seg, 'RT') if np.isfinite(_med(seg, 'RT')) else -1.0,
            L['lab'], chg)
    logger.info('按层解释: 共 %d 层, 改写 %d 点', len(layers), n_chg)
    return out, n_chg

def rejudge_hc_below_seal(data, gas_data=None, por_hc=None):
    """【2026-10-26 R24 用户要求】盖层(盐岩/硬石膏)下气测异常储层水层→油气补偿。

    3-SPS-111D 实测：硬石膏盖层(6507-6519m)以下 6676-6721m 石灰岩储层
    (POR≈0.10)被 Sw 图版判为 WATER，但该段 TG=基线3.4倍、C1=6.6倍、
    C1/C2=3.3(比值法油区)——Sw 反算偏淡(Rw Pickett 下包络)连带的低阻
    不构成水层证据，解释为水层不成立。

    口径(延续 2026-10-20 用户定案"盖层下有孔隙度+气测异常即为油气层")：
      1) 盖层下：本点深度大于最浅盐岩/硬石膏/石膏盖层段顶界(按 LITHOLOGY)；
      2) 储层：POR(缺省 PHI) >= 0.06，与 OIL must 门槛一致
         （por_hc 参数分井覆盖, ← <井名>info.json「解释截止值」）；
      3) 气测异常：对齐气测 TG >= 1.5×全井 TG 基线(中位，断测 NaN 不进分母)，
         与气测"有显示"双通道口径的比值通道一致。
    同时满足的 WATER/WATER_POSSIBLE 点改判油气——类型按比值法:
    C1/C2>=8 且 C1/C3>=15 → GAS，否则 OIL(组分缺失按 OIL，用户口径)。
    只动 Water 族；NonReservoir/DRY/TIGHT 保持原口径。

    Returns: (data, 改判点数)（原地修改）。
    """
    try:
        if data is None or len(data) == 0 \
                or 'INTERPRETATION' not in data.columns:
            return data, 0
        _itp = data['INTERPRETATION'].astype(str).str.upper()
        _wm = _itp.str.startswith('WATER')
        if not bool(_wm.any()):
            return data, 0
        if 'LITHOLOGY' not in data.columns or 'MD' not in data.columns:
            return data, 0
        _md = pd.to_numeric(data['MD'], errors='coerce')
        _lith = data['LITHOLOGY'].astype(str).str.lower().str.strip()
        _seal = _lith.isin(('anhydrite', 'halite', 'gypsum',
                            '硬石膏', '盐岩', '石膏'))
        if not bool(_seal.any()):
            return data, 0
        _seal_top = float(pd.to_numeric(_md[_seal], errors='coerce').min())
        _below = _md > _seal_top
        if 'POR' in data.columns:
            _por = pd.to_numeric(data['POR'], errors='coerce')
        elif data.get('PHI') is not None:
            _por = pd.to_numeric(data['PHI'], errors='coerce')
        else:
            return data, 0
        _res = _por >= (0.06 if por_hc is None else por_hc)
        _show = pd.Series(False, index=data.index)
        _c1 = pd.Series(np.nan, index=data.index)
        _c2 = pd.Series(np.nan, index=data.index)
        _c3 = pd.Series(np.nan, index=data.index)
        if gas_data is not None and 'MD' in gas_data.columns:
            # 【2026-10-26 R24b】对齐改 merge_asof(容差1.0m)：气测采样远稀于
            # 主网格，round(2) 键映射只命中个别点(实测 2/354)；重复列防御
            # (去重保首列)。
            _gd = gas_data.loc[:, ~gas_data.columns.duplicated(keep='first')]
            _cols = [c for c in ('TG', 'C1', 'C2', 'C3') if c in _gd.columns]
            _g = pd.DataFrame({
                'MD': pd.to_numeric(_gd['MD'], errors='coerce')
            })
            for c in _cols:
                _g[c] = pd.to_numeric(_gd[c], errors='coerce')
            _g = _g.dropna(subset=['MD']).sort_values('MD')
            if len(_g) and _cols:
                _left = pd.DataFrame({
                    'MD': _md.values,
                    '_i': np.arange(len(_md), dtype=int),
                }).sort_values('MD')
                _mrg = pd.merge_asof(_left, _g, on='MD',
                                     direction='nearest', tolerance=1.0)
                _mrg = _mrg.sort_values('_i')
                def _col(name):
                    if name not in _mrg.columns:
                        return pd.Series(np.nan, index=data.index)
                    return pd.Series(_mrg[name].values, index=data.index)
                _tg = _col('TG')
                # 基线口径=【盖层上邻接背景窗】(盖层顶上方 2-100m 的 TG 中位)：
                # 盖层封堵烃类垂向运移，其下 TG 整体抬升即聚集证据——与盖层上
                #   背景对比才是本井异常(111D: 背景窗≈479 → 阈值≈719, 水层段
                #   TG 中位 2627 全部命中)。全井中位会被下部高值段偏置
                #   (映射中位 2009/文件中位 535 均不可用)；背景窗不足 30 点
                #   回退气测列全量中位。
                _bg = _tg[(_md >= _seal_top - 100.0)
                          & (_md <= _seal_top - 2.0)]
                if _bg.notna().sum() >= 30:
                    _base = float(_bg.dropna().median())
                elif 'TG' in _gd.columns:
                    _tf = pd.to_numeric(_gd['TG'], errors='coerce')
                    _base = (float(_tf.dropna().median())
                             if _tf.notna().any() else float('nan'))
                else:
                    _base = float('nan')
                if np.isfinite(_base) and _base > 0:
                    _show = _tg >= 1.5 * _base
                _c1 = _col('C1')
                _c2 = _col('C2')
                _c3 = _col('C3')
        _rej = _wm & _below & _res & _show
        n = int(_rej.sum())
        if n == 0:
            logger.info("盖层下油气补偿: 无满足条件点(盖层下WATER储层+气测异常)")
            return data, 0
        _gas_like = ((_c1 / _c2.replace(0, np.nan) >= 8)
                     & (_c1 / _c3.replace(0, np.nan) >= 15))
        _new = np.where(
            _gas_like.fillna(False).values[_rej.values], 'GAS', 'OIL')
        data.loc[_rej, 'INTERPRETATION'] = _new
        if 'ITP' in data.columns:
            data.loc[_rej, 'ITP'] = _new
        _rng = (float(_md[_rej].min()), float(_md[_rej].max()))
        _kind = ('GAS' if (_new == 'GAS').all() else
                 'OIL' if (_new == 'OIL').all() else 'GAS/OIL')
        logger.info("盖层下油气补偿: %d 点 WATER→%s, 深度 %.1f-%.1f m "
                    "(盖层顶 %.1f m 之下, POR>=0.06, TG>=1.5x基线)",
                    n, _kind, _rng[0], _rng[1], _seal_top)
        return data, n
    except Exception as _e:
        logger.warning('盖层下油气补偿判定跳过: %s', _e)
        return data, 0

# ================= gas_constraint 闭包内联(2026-10-26 并库) =================
# logInt 使用: load_gas_file / find_gas_file / read_gas_text_table /
# normalize_gas_units(logger 复用本文件全局)。interpret/run_* 路径未内联
# (logInt 不调用, Gas.py 依赖随原模块保留)。
# 2026-10-26 用户拍板: Gas.py / Flair.py 为独立气测处理程序保留(带 main 入口,
# 可单独调用), 不并入主程序、不内联; gas_constraint.py 同步保留
# (其解释链优先调用 Gas.py 图版法; Gas.py 数据含 C6 时自动选 FLAIR 模式)。

# ----------------------------------------------------------------------------
# 气测组分列归一化映射（原始列名(去空格/换行/小写/去单位) -> 标准名）
# ----------------------------------------------------------------------------
_COLUMN_ALIASES = {
    "md": "MD", "depth": "MD", "dep": "MD", "dept": "MD", "tdep": "MD",
    "md(m)": "MD", "depthm": "MD", "mdm": "MD",
    # BET-1 txt深度列 'MDEPTH (ft)'(2026-10-08): _norm_header_key去括号后为
    # 'mdepth(ft)'/去单位尾缀后为'mdepthft', 均需映射
    "mdepth": "MD", "mdepth(ft)": "MD", "mdepthft": "MD", "depthft": "MD",
    "tg": "TG", "tgas": "TG", "totgas": "TG", "totalgas": "TG",
    "total_gas": "TG", "gas_total": "TG", "total": "TG", "totle": "TG",
    "c1": "C1", "methane": "C1", "ch4": "C1",
    "c2": "C2", "ethane": "C2", "c2h6": "C2",
    "c3": "C3", "propane": "C3", "c3h8": "C3",
    "ic4": "IC4", "isobutane": "IC4",
    "nc4": "NC4", "nbutane": "NC4",
    "ic5": "IC5", "isopentane": "IC5",
    "nc5": "NC5", "npentane": "NC5",
    # 注: 裸 'c5'/'c4' 是"总戊烷/总丁烷", 不可当作异构体 (用户2026-09-14)
    "c4": "C4", "c5": "C5",
    "c6": "C6", "c7": "C7", "c8": "C8",
    "co2": "CO2", "h2s": "H2S",
}
# 全烃(TG)碳数加权合成用的权重 (用户2026-09-14 口径)
_TG_WEIGHTS = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5,
               "C6": 6, "C7": 7, "C8": 8, "BZ": 6, "MCH": 7, "TL": 7}
def _norm_header_key(name) -> str:
    """列名归一化key (与 _normalize_columns 同规则): 小写/去空格换行括号/去单位尾缀。"""
    key = (str(name).replace("\n", " ").replace("\r", " ")
           .strip().lower()
           .replace(" ", "")
           .replace("(m)", "").replace("(ppm)", "")
           .replace("(%)", "").replace("(", "").replace(")", ""))
    # 去掉可能的单位尾缀
    for suf in ["ppm", "mg/l", "mg/l)", "%", "(%)", "m", "min/m", "min/m)", "ft", "(ft)"]:
        if key.endswith(suf):
            key = key[: -len(suf)]
    return key
def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将气测原始列名归一化为标准名（MD / C1..C8 / TG / CO2 / H2S）。"""
    rename = {}
    for col in df.columns:
        if not isinstance(col, str):
            continue
        key = _norm_header_key(col)
        if key in _COLUMN_ALIASES and _COLUMN_ALIASES[key] not in rename.values():
            rename[col] = _COLUMN_ALIASES[key]
    if rename:
        df = df.rename(columns=rename)
    # 清理未命名列
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
    return df
# 气测烃类组分列(用于单位自洽性检测; 不含 CO2/H2S/H2 —— 全烃TG是非烃气体以外的总烃)
_GAS_HC_COLS = ("C1", "C2", "C3", "C4", "IC4", "NC4", "C5", "IC5", "NC5",
                "C6", "C7", "C8", "MCH", "BZ", "TL")
def normalize_gas_units(df: pd.DataFrame, unit_hints=None) -> pd.DataFrame:
    """气测单位统一为 ppm —— 识别单位并换算 (用户2026-09-30, TITAS-31)。

    用户口径: "气测数据的列名是自带单位的, 应该能识别, 有的单位是单独占一行,
    要智能分析, 因为不是ppm就是%, 绘图单位统一是ppm"。此前 TG(%) 与组分(ppm)
    被当同一单位直接绘图/解释 —— TG 曲线被压在 ppm 对数刻度最左侧成贴边直线,
    异常门槛(TG≥50ppm)对 TG 失真。

    单位识别两级(单位有 ppm / % / unit 三种):
      阶段0(表头显式标注, 权威): 列名自带单位('TG (%)'/'C1 ppm'/'TGAS (unit)')
        或单位单独占一行(表头下一行 '(%)'/'(ppm)'/'unit', 见 'Gas Show' 表)
        —— 由 attach_gas_unit_hints 捕获为 {标准列名: '%'|'ppm'|'unit'}; 本函数
        按 GAS_UNIT_TO_PPM 换算: %×10^4, unit×200(印尼气测仪刻度, 2026-10-08
        BET-1, 已写入logknow), ppm不变;
      阶段1(值域判定, 无标注时兜底; 用户2026-09-30规则; 判定顺序B/C先于A
        —— 2026-10-08 BET-1: TGAS为%但max 395>100, 演绎证据B/C须优先于
        归纳阈值A):
        · 规则B: 组分一般都是ppm, C1最大值>100且TG中位<C1中位 -> TG为非ppm,
          需换算(系数按自洽性在 unit×200 与 %×10000 中选择, 见下);
        · 规则C: ratio=median(TG)/median(Σ组分), 同单位下必有TG>=Σ组分:
          ratio<0.05 -> TG为非ppm需换算; ratio>100且组分均<=100 -> 组分=%(×10000);
        · 规则A: 列内出现>100的值 -> 该列肯定是ppm (%不会超过100);
        · TG换算系数自洽性选择(2026-10-08印尼BET-1): unit×200 与 %×10000 中取
          换算后TG/Σ组分中位比值最接近1者 —— BET-1 TGAS中位8.27 unit×200=1654ppm
          与Σ组分中位约1100ppm比值1.5自洽, %×10000=82700比值75荒谬;
        · TG与全部组分最大值均<=100 -> 全文件疑似% -> 整体×10000(告警);
        · 其余 -> 同为ppm不换算。
      阶段0换算后仍做自洽性校验: 若 ratio 仍在 0.05~100 之外, 告警"表头标注
      可能有误"(只告警不二次换算, 防止双重换算)。
    换算系数 1% = 10^4 ppm。实测 TITAS-31: TG中位0.33(%)/Σ组分中位约3990(ppm)
    -> TG×10000 后中位3292ppm, 与C1(3798ppm)同量级, 自洽。
    幂等护栏: attrs['gas_units_normalized'] 防止重复换算。
    """
    try:
        if df is None or len(df) == 0 or "TG" not in df.columns:
            return df
        try:
            if getattr(df, "attrs", {}).get("gas_units_normalized"):
                return df
        except Exception:
            pass
        comp_cols = [c for c in _GAS_HC_COLS if c in df.columns]

        def _pos_median(s):
            v = pd.to_numeric(s, errors="coerce")
            v = v[v > 0]
            return float(v.median()) if bool(len(v)) else float("nan")

        # ---------- 阶段0: 表头显式单位标注(列名自带/单位行), 权威 ----------
        hints = unit_hints if isinstance(unit_hints, dict) and unit_hints else None
        if not hints:
            try:
                hints = getattr(df, "attrs", {}).get("gas_unit_hints") or None
            except Exception:
                hints = None
        if hints:
            converted = {}
            for col, u in hints.items():
                u_key = str(u)
                factor = GAS_UNIT_TO_PPM.get(u_key, 1.0)
                if (col in df.columns and col != "MD" and factor > 1.0):
                    df[col] = pd.to_numeric(df[col], errors="coerce") * factor
                    converted[col] = f"{u_key}→ppm(×{factor:g})"
            if converted:
                _units = "/".join(sorted({str(hints[c]) for c in converted}))
                logger.warning("气测单位识别(表头标注): %s 原始单位为%s, 已换算为统一单位ppm",
                               "/".join(converted), _units)
                print(f"★ 气测单位: {'/'.join(converted)} 表头标注单位={_units}, "
                      f"已换算为统一单位ppm")
            try:
                df.attrs["gas_unit_converted"] = converted
            except Exception:
                pass
            # 物理自洽性校验(只告警不二次换算 —— 防止对已换算列双重×10000)
            if "TG" in df.columns and comp_cols:
                tg_med = _pos_median(df["TG"])
                comp_sum = None
                for c in comp_cols:
                    v = pd.to_numeric(df[c], errors="coerce").clip(lower=0.0).fillna(0.0)
                    comp_sum = v if comp_sum is None else comp_sum + v
                comp_med = _pos_median(comp_sum)
                if np.isfinite(tg_med) and np.isfinite(comp_med) and tg_med > 0 and comp_med > 0:
                    ratio = tg_med / comp_med
                    if ratio < 0.05 or ratio > 100:
                        logger.warning("气测单位校验: 表头标注换算后 TG/Σ组分=%.3g 仍超出0.05~100, "
                                       "表头单位标注可能有误, 请人工核对", ratio)
            try:
                df.attrs["gas_units_normalized"] = True
            except Exception:
                pass
            return df

        # ---------- 阶段1: 值域判定(无表头标注时兜底; 用户2026-09-30规则) ----------
        # 判定顺序 B/C(演绎) 先于 A(归纳), 见函数docstring(2026-10-08 BET-1)
        # 规则A: 列内出现>100的值 -> 该列肯定是ppm (%不会超过100)
        # 规则B: 组分一般都是ppm; TG(总体)中位 < C1中位(原始值) -> 物理上TG>=C1,
        #        TG反而小 -> TG=%, C1=ppm -> TG×10000
        # 规则C: 同单位自洽 ratio=TG中位/Σ组分中位(同单位下必有TG>=Σ组分):
        #        <0.05 -> TG=%(×10000); >100且组分均<=100 -> 组分=%(×10000)
        # 追加: TG与全部组分最大值都<=100 -> 全文件疑似% -> 整体×10000(告警)
        if not comp_cols:
            return df
        tg_med = _pos_median(df["TG"])
        tg_max = float(pd.to_numeric(df["TG"], errors="coerce").max())
        tg_max = tg_max if np.isfinite(tg_max) else -1.0
        c1_med = c1_max = float("nan")
        if "C1" in df.columns:
            _c1 = pd.to_numeric(df["C1"], errors="coerce")
            c1_med = _pos_median(_c1)
            c1_max = float(_c1.max())
            c1_max = c1_max if np.isfinite(c1_max) else -1.0
        if not (np.isfinite(tg_med) and tg_med > 0):
            return df

        comp_sum = None
        for c in comp_cols:
            v = pd.to_numeric(df[c], errors="coerce").clip(lower=0.0).fillna(0.0)
            comp_sum = v if comp_sum is None else comp_sum + v
        comp_med = _pos_median(comp_sum)
        comp_max = -1.0
        for c in comp_cols:
            _m = float(pd.to_numeric(df[c], errors="coerce").max())
            if np.isfinite(_m):
                comp_max = max(comp_max, _m)
        ratio = (tg_med / comp_med) if (np.isfinite(comp_med) and comp_med > 0) else float("nan")

        # 判定优先级(2026-10-08, BET-1): 规则B/C是演绎物理证据(同单位下必有
        # TG>=C1 且 TG>=Σ组分), 规则A只是归纳阈值 —— BET-1 的 TGAS(%)最大值
        # 395>100 会误触发规则A阻断正确换算, 故 B/C 必须先于 A 判定。
        tg_is_pct = None
        _rule = ""
        # 规则B: 组分一般都是ppm —— C1最大值>100 且 TG中位<C1中位 -> TG=%
        if (np.isfinite(c1_med) and c1_med > 0
                and c1_max > 100 and tg_med < c1_med):
            tg_is_pct = True
            _rule = "规则B(TG中位%.4g<C1中位%.4g, 组分ppm)" % (tg_med, c1_med)
        # 规则C: TG中位远小于组分和中位 -> TG=% (同单位下必有TG>=Σ组分)
        if tg_is_pct is None and np.isfinite(ratio) and ratio < 0.05:
            tg_is_pct = True
            _rule = "规则C(TG中位%.4g远小于Σ组分中位%.4g)" % (tg_med, comp_med)
        # 规则A: TG最大值>100 -> TG肯定是ppm(%不会超过100), 不再换算
        if tg_is_pct is None and tg_max > 100:
            tg_is_pct = False
            _rule = "规则A(TG最大值%.4g>100)" % tg_max

        if tg_is_pct:
            # TG非ppm -> 需换算为ppm。换算系数按自洽性选择(2026-10-08印尼BET-1):
            # 候选 unit(×200, 印尼气测仪刻度单位, 见logknow知识库) 与 %(×10000),
            # 取换算后 TG中位/Σ组分中位 比值最接近1(物理上TG>=Σ组分且同量级)者。
            # BET-1实测: TG中位8.27 unit -> ×200=1654ppm vs Σ组分中位约1100ppm
            # (比值1.5, 自洽); 若误按%×10000=82700ppm(比值75, 荒谬)。
            factor, unit_name = 10000.0, "%"
            if np.isfinite(comp_med) and comp_med > 0:
                def _unit_dev(f):
                    r = (tg_med * f) / comp_med
                    return abs(np.log10(r)) if r > 0 else float("inf")
                if _unit_dev(200.0) < _unit_dev(10000.0):
                    factor, unit_name = 200.0, "unit"
            df["TG"] = pd.to_numeric(df["TG"], errors="coerce") * factor
            try:
                df.attrs["gas_unit_converted"] = {"TG": f"{unit_name}→ppm(×{factor:g})"}
            except Exception:
                pass
            if not _rule:
                _rule = "全部值<=100, 疑似全文件%%单位"
            logger.warning("气测单位识别(值域): TG原始单位=%s [%s]; TG已×%g换算为统一单位ppm",
                           unit_name, _rule, factor)
            print(f"★ 气测单位: TG原始单位={unit_name} [{_rule}] -> TG已×{factor:g}换算为统一单位ppm")
        elif np.isfinite(ratio) and ratio > 100 and tg_max > 100 and 0 < comp_max <= 100:
            # 规则C(组分=%): TG已证为ppm(最大值>100), 组分均<=100且之和远小于TG -> 组分×10000
            for c in comp_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce") * 10000.0
            try:
                df.attrs["gas_unit_converted"] = {c: "%→ppm(×10000)" for c in comp_cols}
            except Exception:
                pass
            logger.warning("气测单位识别(值域): TG中位%.4g vs 组分和中位%.4g (比值%.3g>100) "
                           "-> 组分单位为%%, TG为ppm; 组分%s已×10000换算为统一单位ppm",
                           tg_med, comp_med, ratio, "/".join(comp_cols))
            print("★ 气测单位: 组分原始单位=%, TG单位=ppm -> 组分已×10000换算为统一单位ppm")
        elif tg_max <= 100 and 0 < comp_max <= 100:
            # 追加: TG与全部组分最大值都<=100 -> 全文件疑似% (ppm井全组分<100极罕见)
            _all = ["TG"] + list(comp_cols)
            for c in _all:
                df[c] = pd.to_numeric(df[c], errors="coerce") * 10000.0
            try:
                df.attrs["gas_unit_converted"] = {c: "%→ppm(×10000)" for c in _all}
            except Exception:
                pass
            logger.warning("气测单位识别(值域): TG与全部组分最大值均<=100 -> 全文件疑似%%单位; "
                           "%s已×10000换算为统一单位ppm, 请人工核对", "/".join(_all))
            print("★ 气测单位: TG与全部组分最大值均≤100, 判定为%单位 -> 已整体×10000换算为ppm(请人工核对)")
        else:
            if np.isfinite(ratio) and ratio < 0.05:
                logger.warning("气测单位检查: TG最大值%.4g>100(ppm特征)但TG中位%.4g远小于组分和%.4g, "
                               "数据自相矛盾, 未做换算, 请人工核对", tg_max, tg_med, comp_med)
            else:
                logger.info("气测单位检查: TG与组分同为ppm(TG中位%.4g, 最大%.4g>100), 无需换算",
                            tg_med, tg_max)
        try:
            df.attrs["gas_units_normalized"] = True
        except Exception:
            pass
        return df
    except Exception as e:
        logger.warning(f"气测单位统一失败(按原值继续): {e}")
        return df
def _column_unit_hint(name):
    """从列名提取单位提示: 含'ppm'->'ppm', 含'%'->'%', 含'unit'->'unit'。

    2026-10-08(印尼, BET-1): 印尼气测数据(如 'ASCI GAS dan ROP' 文本)全烃
    TGAS 的单位是气测仪刻度单位 'unit', 1 unit = 200 ppm (印尼地区经验,
    已写入 logknow 知识库) —— 不是 % 的 ×10000。
    """
    s = str(name).lower()
    if "ppm" in s:
        return "ppm"
    if "%" in s:
        return "%"
    if "unit" in s:
        return "unit"
    return None
# 气测单位 -> ppm 换算系数 (统一单位为ppm; 用户2026-09-30/2026-10-08)
# %: 1% = 10^4 ppm; unit: 印尼气测仪刻度单位 1 unit = 200 ppm (logknow)
GAS_UNIT_TO_PPM = {"ppm": 1.0, "unit": 200.0, "%": 10000.0}
def attach_gas_unit_hints(df: pd.DataFrame) -> pd.DataFrame:
    """捕获气测表头单位提示并剔除"单位行" (用户2026-09-30)。

    用户口径: "气测数据的列名是自带单位的, 应该能识别, 有的单位是单独占一行,
    要智能分析, 因为不是ppm就是%"。两种形态:
      ① 列名自带单位: 'TG (%)'/'C1 ppm' (TITAS-31 'Gas data' 表表头行);
      ② 单位单独占一行: 表头下一行整行是 '(%)'/'(ppm)'/'m MD' (TITAS-31
         'Gas Show' 表) —— 该行数值化时会被 coerce 成 NaN 自动剔除, 但单位
         信息会丢失, 必须在剔除前捕获。
    提示写入 df.attrs['gas_unit_hints'] = {标准列名: '%'|'ppm'} 供
    normalize_gas_units 消费; 单位行从数据中删除。
    """
    try:
        if df is None or len(df) == 0:
            return df

        def _std(col):
            k = _norm_header_key(col)
            return _COLUMN_ALIASES.get(k, k.upper())

        hints = {}
        # ① 列名自带单位
        for col in df.columns:
            u = _column_unit_hint(col)
            if u:
                hints[_std(col)] = u
        # ② 单位行: 表头之下前5行内, 一行中≥2个非空格是纯单位串 -> 捕获并整行删除
        drop_idx = []
        for i in range(min(5, len(df))):
            row = df.iloc[i]
            unit_cells = []
            for j, v in enumerate(row.values):
                if pd.isna(v):
                    continue
                s = re.sub(r"[^a-z%]", "", str(v).lower())
                if s in ("ppm", "%", "unit"):
                    unit_cells.append((j, s))
            if len(unit_cells) >= 2:
                for j, u in unit_cells:
                    if j < len(df.columns):
                        hints[_std(df.columns[j])] = u
                drop_idx.append(df.index[i])
        if drop_idx:
            logger.info(f"气测表头单位行识别: 数据第{[str(x) for x in drop_idx]}行为单位行, "
                        f"已捕获单位并从数据中剔除")
            df = df.drop(index=drop_idx)
        if hints:
            try:
                df.attrs["gas_unit_hints"] = dict(hints)
            except Exception:
                pass
            logger.info(f"气测表头单位提示: {hints}")
        return df
    except Exception as e:
        logger.warning(f"气测表头单位提示捕获失败(按无提示继续): {e}")
        return df
def _detect_gas_header_row(raw: pd.DataFrame):
    """在无表头 DataFrame 中探测"深度列+气体组分"表头行; 未找到返回 None。

    要求同时命中: 深度关键词(depth/md) **且** ≥2 个气体组分关键词(tg/c1..c5)。
    """
    for i in range(len(raw)):
        cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                 .replace(" ", "") for x in raw.iloc[i].tolist()]
        has_depth = any(("depth" in c) or ("md" in c and len(c) <= 6) for c in cells)
        gas_hits = sum(1 for c in cells
                       for tok in ("tg", "c1", "c2", "c3", "c4", "c5")
                       if tok in c)
        if has_depth and gas_hits >= 2:
            return i
    return None
def _excel_sheet_priority(xls) -> list:
    """按"像气测数据表"的程度给 sheet 名排序(索引序)。

    2026-09-29(TITAS-31): 气测数据常不在第一个 sheet —— 本井气测在 'Gas data' 表,
    第一个表是俄文日报 'Rus.'。优先级: gas data/气测数据 > 含 gas/气测(排除
    show/异常段——那是**区间**异常表, 不是逐点曲线) > 其余。
    """
    names = list(xls.sheet_names)

    def _rank(nm):
        l = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(nm).lower())
        if "gasdata" in l or ("气测" in str(nm) and "异常" not in str(nm)):
            return 0
        if (("gas" in l or "气测" in str(nm)) and "show" not in l
                and "异常" not in str(nm)):
            return 1
        return 2

    return sorted(range(len(names)), key=lambda k: (_rank(names[k]), k))
def _read_table_with_header(path: str) -> pd.DataFrame:
    """读取表格文件并自动探测表头行（兼容单行/双行(标题+列名)表头）。

    Excel 多表(2026-09-29, TITAS-31): 逐 sheet(按 _excel_sheet_priority 排序)
    探测"深度+气体组分"表头行, 命中即用; 全部未命中退回第一个表(旧行为)。
    """
    if not path.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_csv(path, encoding="utf-8", engine="python", header=None)
        # 在前 5 行内寻找"看起来像列名"的行（含 depth/md/c1/c2 之一）
        hdr_row = 0
        for i in range(min(5, len(raw))):
            cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                     .replace(" ", "") for x in raw.iloc[i].tolist()]
            if any(tok in c for c in cells for tok in ("depth", "md", "c1", "c2")):
                hdr_row = i
                break
        df = raw.iloc[hdr_row + 1:].copy()
        df.columns = [str(x).strip() for x in raw.iloc[hdr_row].tolist()]
        return attach_gas_unit_hints(df)

    xls = pd.ExcelFile(path)
    _names = list(xls.sheet_names)
    for k in _excel_sheet_priority(xls):
        nm = _names[k]
        try:
            raw = pd.read_excel(xls, sheet_name=nm, header=None)
        except Exception as e:
            logger.debug(f"气测Excel读取表 '{nm}' 失败: {e}")
            continue
        i = _detect_gas_header_row(raw)
        if i is None:
            continue
        logger.info(f"气测Excel: 在表 '{nm}' 第{i+1}行找到表头")
        df = raw.iloc[i + 1:].copy()
        df.columns = [str(x).strip() for x in raw.iloc[i].tolist()]
        return attach_gas_unit_hints(df)
    # 兜底: 所有表均未命中 -> 第一个表按旧行为(前5行找 depth/md/c1/c2)
    logger.warning(f"气测Excel: 所有表{_names}均未命中气测表头, 退回第一个表")
    raw = pd.read_excel(xls, sheet_name=_names[0], header=None)
    hdr_row = 0
    for i in range(min(5, len(raw))):
        cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                 .replace(" ", "") for x in raw.iloc[i].tolist()]
        if any(tok in c for c in cells for tok in ("depth", "md", "c1", "c2")):
            hdr_row = i
            break
    df = raw.iloc[hdr_row + 1:].copy()
    df.columns = [str(x).strip() for x in raw.iloc[hdr_row].tolist()]
    return attach_gas_unit_hints(df)
def read_gas_text_table(path: str) -> pd.DataFrame:
    """读取 txt/dat 气测文本文件（制表符/逗号/空白分隔），自动定位表头行。

    示例(BET-1, 2026-10-08): Tab分隔, 首行即表头
      'MDEPTH (ft)\tROP (ft/hrs)\tWOB\tTRPM\tTGAS\tC1\tC2\tC3\tiC4\tnC4\tiC5\tnC5'
    表头行识别标准: 同时包含深度关键词(MD/DEPTH/DEPT/TDEP)与
    >=2 个气体组分关键词(TG/TGAS/C1..C5)。
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
    hdr = None
    for i, line in enumerate(lines[:200]):
        fields = [x.strip().upper() for x in re.split(r"[\t,;]+", line.strip()) if x.strip()]
        if not fields:
            continue
        has_depth = any(any(k in fld for k in ("MD", "DEPTH", "DEPT", "TDEP"))
                        for fld in fields)
        n_gas = sum(1 for fld in fields
                    for k in ("TG", "TGAS", "TOTGAS", "C1", "C2", "C3", "C4", "C5")
                    if k in fld)
        if has_depth and n_gas >= 2:
            hdr = i
            break
    if hdr is None:
        hdr = 0
        logger.warning(f"气测文本文件未定位到表头行, 默认首行为表头: {path}")
    sep = "\t" if "\t" in lines[hdr] else ("," if "," in lines[hdr] else r"\s+")
    df = pd.read_csv(path, sep=sep, skiprows=hdr, engine="python",
                     encoding="utf-8-sig", header=0)
    logger.info(f"气测文本文件: 表头在第{hdr + 1}行(分隔符={'Tab' if sep == chr(9) else sep}), "
                f"{len(df.columns)}列, {len(df)}行")
    return df
def load_gas_file(path: str) -> pd.DataFrame:
    """读取气测文件（xls/xlsx/csv/txt/dat/las），返回归一化后的 DataFrame（含 MD 与 C1..C5）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".csv"):
        df = _read_table_with_header(path)
    elif ext in (".txt", ".dat"):
        df = read_gas_text_table(path)
    elif ext == ".las":
        try:
            import lasio
            las = lasio.read(path)
            df = las.df().reset_index()
        except Exception as e:
            raise RuntimeError(f"读取 LAS 气测文件失败: {e}")
    else:
        raise ValueError(f"不支持的气测文件格式: {ext}")
    # 表头单位提示必须在列名归一化前取出(rename可能丢attrs), 换算时显式传入
    try:
        _gas_uhints = dict(df.attrs.get("gas_unit_hints") or {})
    except Exception:
        _gas_uhints = {}
    df = _normalize_columns(df)
    # 统一深度列名
    for dcol in ("MD", "DEPTH", "DEPT", "DEP", "TDEP"):
        if dcol in df.columns:
            if dcol != "MD":
                df = df.rename(columns={dcol: "MD"})
            break
    # 【2026-10-20 RASHIDPUR_13】重复列名防御：xls 尾部无名空列被读成重复
    # 'nan' 列（本例 14 列中 2 个 'nan'），取 df[c] 得到 DataFrame 而非
    # Series → pd.to_numeric 抛 "arg must be a list, tuple, 1-d array, or
    # Series" → 自动发现加载失败回退对话框（CLI 后台运行卡死）。
    # 去重（保留首列）后再数值化。
    if df.columns.duplicated().any():
        _dupcols = df.columns[df.columns.duplicated()].unique().tolist()
        logger.warning(f"气测数据存在重复列名，保留首列去重: {_dupcols}")
        df = df.loc[:, ~df.columns.duplicated()]
    # 关键修复(2026-09-14, 3-SPS-111D): lasio 对含非数值记号的行会把整列保留为字符串
    # (该井气测 LAS 85 列中 82 列为 str), 导致后续比值运算 TypeError("str"/"str")、
    # 气测解释整体失败被静默跳过。气测各道均为数值测量, 这里统一强制数值化(非数值置 NaN)。
    _n_coerced = 0
    for c in list(df.columns):
        if str(c).startswith("Unnamed"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_numeric(df[c], errors="coerce")
            _n_coerced += 1
    if _n_coerced:
        logger.info(f"气测数据数值化: {_n_coerced}列 由字符串/混合类型转为数值")
    if "MD" in df.columns:
        df = df.dropna(subset=["MD"])
    # 丁烷/戊烷总量合成: iC4+nC4 才是 C4, iC5+nC5 才是 C5 (用户2026-09-14)
    # 2026-09-29(3-SPS-111D): 两个组分**都缺测**时总量须为 NaN, 不能 fillna(0) 相加
    #   得 0.0 —— 假"有值"会让下游 TG 合成的"全组分缺测"掩膜永不触发(共 0 点),
    #   断测语义又退化为 TG=0。
    for _tot, _parts in (("C4", ("IC4", "NC4")), ("C5", ("IC5", "NC5"))):
        if _tot not in df.columns and all(p in df.columns for p in _parts):
            _p0 = pd.to_numeric(df[_parts[0]], errors="coerce")
            _p1 = pd.to_numeric(df[_parts[1]], errors="coerce")
            _tot_s = _p0.fillna(0.0) + _p1.fillna(0.0)
            df[_tot] = _tot_s.where(_p0.notna() | _p1.notna())
            logger.info("气测组分合成: %s = %s + %s (两者均缺测 -> NaN)", _tot, _parts[0], _parts[1])

    # 全烃(TG)合成: 无可信全烃测量列(且绝不可取 TMPGAS 类泥浆温度)时按碳数加权合成
    # 2026-09-29(3-SPS-111D): 与 logInt.load_gas_data 同口径 —— 全部组分均缺测
    #   (断测/停钻)的行 TG=NaN, 保留"无数据"语义; compute_gas_anomaly 据此把
    #   ratio 置 NaN, 排除断测点对"相对异常占比"分母的污染。部分缺测行其余
    #   组分照常加权(缺项计 0)。
    if "TG" not in df.columns:
        _avail = {k: w for k, w in _TG_WEIGHTS.items() if k in df.columns}
        if _avail:
            _tg = pd.Series(0.0, index=df.index)
            _any = pd.Series(False, index=df.index)
            for _k, _w in _avail.items():
                _kv = pd.to_numeric(df[_k], errors="coerce")
                _tg = _tg + _w * _kv.fillna(0.0)
                _any = _any | _kv.notna()
            df["TG"] = _tg.where(_any)
            logger.info("气测全烃(TG)按碳数加权合成: %s (全组分缺测点 TG=NaN, 共 %d 点)",
                        "+".join(f"{w}*{k}" for k, w in _avail.items()),
                        int((~_any).sum()))

    # 单位统一为ppm (用户2026-09-30, TITAS-31): 阶段0按表头显式单位(列名自带/
    # 单位行)换算, 阶段1值域自洽性兜底 —— 必须在 T15/异常检测之前, 使异常门槛
    # (TG≥50ppm等)生效
    df = normalize_gas_units(df, unit_hints=_gas_uhints)

    # 计算总烃 T15（C1..C5 之和），缺失组分按 0 处理；异构体缺失时用总量列兜底
    comp = [c for c in ("C1", "C2", "C3", "IC4", "NC4", "IC5", "NC5") if c in df.columns]
    if "IC4" not in df.columns and "NC4" not in df.columns and "C4" in df.columns:
        comp.append("C4")
    if "IC5" not in df.columns and "NC5" not in df.columns and "C5" in df.columns:
        comp.append("C5")
    if comp:
        df["T15"] = df[comp].fillna(0).sum(axis=1)
    else:
        df["T15"] = 0.0
        logger.warning(f"气测文件缺少 C1..C5 组分列: {path}")
    # 关键修复(2026-09-22, TrakesKE-1): 归一化索引为 0..n-1。
    # _read_table_with_header 用 raw.iloc[hdr+1:] 取数据, 索引残留 Excel 行号
    # (本井为 2..1360)。而 Gas.py 的 star_interpretation 用 range(len(df)) 作
    # **位置**下标、却用 df.at[idx, ...] 按**标签**写入 —— 标签 0/1 不存在,
    # pandas 会**凭空追加 2 行**(1359->1361), 且 2..1360 号行的结果整体**错位 2 行**。
    # 后果: run_gas_constraint_for_well 里 df["ITP_traditional"]=itp.values 长度不符
    # 抛异常 -> **整个气测约束(含气测异常约束)被静默跳过**。
    df = df.reset_index(drop=True)
    return df
def find_gas_file(well_name: str, search_dirs=None) -> str:
    """按井名在常见目录中查找气测文件。匹配 gas_*.las / *Gas*.xls(x) / *gas*.csv / *GAS*.txt。

    2026-09-29(TITAS-31): 文件名无 'gas' 但含 'dgr'(检测气测读数, 如
    '147 Titas-31 (Deep) DGR 20260913.xlsx')同样收录; search_dirs 可传入
    主数据(LAS)所在目录 —— 气测文件常与 LAS 放同一目录。
    2026-10-08(BET-1): ①匹配数字前导零剥离 —— 井名'BET-1'也能匹配文件名
    'BET-001'(bet-001 与 bet-1 归一化后同为 bet1); ②search_dirs 递归搜索
    子目录(气测文件常放 supportdata/ 等子目录); ③支持 .txt/.dat 文本格式。
    """
    if not well_name:
        return None
    def _norm(s):
        s = re.sub(r"[^a-z0-9]", "", str(s).lower())
        # 前导零剥离: 'bet001'->'bet1' (井号/日期等数字段前导零无语义)
        s = re.sub(r"0+(\d)", r"\1", s)
        return s

    wn = _norm(well_name)
    if search_dirs is None:
        base = os.path.dirname(os.path.abspath(__file__))
        search_dirs = [
            os.path.join(base, "data", "uploads"),
            os.path.join(os.getcwd(), "data", "uploads"),
            os.getcwd(),
        ]
    import glob
    cands = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        # 递归搜索子目录 (BET-1 气测文件在 supportdata/ 下)
        for root, _dirs, _files in os.walk(d):
            for pat in ("*.xlsx", "*.xls", "*.csv", "*.las", "*.txt", "*.dat"):
                for p in glob.glob(os.path.join(root, pat)):
                    base_n = _norm(os.path.basename(p))
                    if (("gas" in base_n or "flair" in base_n or "dgr" in base_n)
                            and (wn in base_n or wn == "")):
                        cands.append(p)
    if not cands:
        return None
    # 优先文件名中包含完整井名的, 其次路径更短/更浅的(浅目录优先于深层子目录)
    cands.sort(key=lambda p: (wn not in _norm(os.path.basename(p)),
                              p.count(os.sep), len(p)))
    return cands[0]

# ================= qlscan 闭包内联(2026-10-26 并库) =================
import fitz

_HAS_RAPID = False
_OCR = None
def _get_ocr():
    global _OCR, _HAS_RAPID
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
            _HAS_RAPID = True
        except Exception as e:  # noqa: BLE001
            print(f'[qlscan] rapidocr 不可用: {e}（回退无 OCR）')
            _OCR = False
    return _OCR or None
def page_to_png(pdf_path, pno, dpi=150, out_dir=None, crop=(0.0, 1.0)):
    """提取 PDF 指定页为 PNG，返回图片路径与尺寸。

    crop=(top_ratio, bottom_ratio)：只渲染页面上部区域（免责声明/LEGEND
    等表头都在页面顶部，裁上部可放大文字、显著提高 OCR 识别率）。
    """
    doc = fitz.open(pdf_path)
    if pno < 0 or pno >= doc.page_count:
        doc.close()
        return None, (0, 0)
    pg = doc[pno]
    rect = pg.rect
    top_r, bot_r = crop
    clip = fitz.Rect(0, rect.height * top_r, rect.width, rect.height * bot_r)
    pix = pg.get_pixmap(dpi=dpi, clip=clip)
    if out_dir is None:
        out_dir = Path(pdf_path).parent
    out = Path(out_dir) / f'_qlscan_p{pno + 1}.png'
    pix.save(str(out))
    doc.close()
    return str(out), (pix.width, pix.height)
def ocr_page(img_path):
    """整页 OCR，返回带坐标文本项列表"""
    ocr = _get_ocr()
    if ocr is None:
        return []
    res, _ = ocr(str(img_path))
    items = []
    for b, txt, score in (res or []):
        pts = [[int(v) for v in p] for p in b]
        x0, y0 = pts[0]
        x1, y1 = pts[2]
        items.append({
            'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
            'text': (txt or '').strip(), 'score': float(score),
        })
    return items
def rows_from_items(items, y_gap=14):
    """按 y0 聚类成行（行内按 x0 排序），返回 [{y, x0, x1, text}]"""
    rows = []
    for it in sorted(items, key=lambda i: (i['y0'], i['x0'])):
        hit = None
        for r in rows:
            if abs(r['y'] - it['y0']) <= y_gap:
                hit = r
                break
        if hit is None:
            hit = {'y': it['y0'], 'items': []}
            rows.append(hit)
        hit['items'].append(it)
    out = []
    for r in rows:
        r['items'].sort(key=lambda i: i['x0'])
        xs = [i['x0'] for i in r['items']]
        xe = [i['x1'] for i in r['items']]
        out.append({
            'y': r['y'], 'x0': min(xs), 'x1': max(xe),
            'text': ' '.join(i['text'] for i in r['items']),
            'cells': [(i['x0'], i['text']) for i in r['items']],
        })
    out.sort(key=lambda r: r['y'])
    return out
_HEADER_FIELD_KEYS = (
    'rig name', 'well name', 'field', 'company', 'contractor', 'location',
    'country', 'spudded', 'reached', 'td', 'date', 'logged', 'processed',
    'coord', 'long', 'lat', 'x :', 'y :', 'elevation', 'elev', 'kb', 'gl',
    'density', 'mud', 'interval', 'equip', 'corrected', 'depth', 'scale',
    'datum', 'unit', 'permit', 'lease', 'operator',
)
def scan_header_page(items, W, H):
    """页1（右转信息表放正后）字段提取：字段名行/值行配对 + 井名/图名/比例尺。
    样本页1 是完整右转表（信息字段+BH/CS+免责+LEGEND 同页），rows 全部保留，
    供免责/图例/套管记录二次分类提取。"""
    rows = rows_from_items(items)
    fields = []      # [{label, value, y}]
    big_text = []    # 大字号文本（井名/图名/比例尺候选）
    all_rows = []    # 全行文本（供免责/图例/BH-CS 提取）
    for r in rows:
        cells = r['cells']
        text = r['text']
        all_rows.append({
            'y': r['y'], 'x0': r['x0'], 'x1': r['x1'],
            'text': text, 'cells': cells,
        })
        span = r['x1'] - r['x0']
        # 图名：Well Logging ... Result Plot
        if re.search(r'well\s*logging', text, re.I) and 'plot' in text.lower():
            big_text.append({'kind': 'title', 'text': text, 'y': r['y']})
            continue
        # 井名：含 (…-…) 或大写字母+数字+横杠的长文本
        if len(text) > 8 and re.search(r'[A-Z0-9]{2,}[\s-]+[A-Z0-9]', text) \
                and not any(k in text.lower() for k in _HEADER_FIELD_KEYS):
            big_text.append({'kind': 'well_name', 'text': text, 'y': r['y']})
            continue
        # 比例尺：含 1:xxx 或 SCALE
        if re.search(r'1\s*:\s*\d{2,4}', text):
            big_text.append({'kind': 'scale', 'text': text, 'y': r['y']})
            continue
        # 字段名:值 配对（同列相邻行）
        for x0, cell in cells:
            low = cell.lower().rstrip('.: ')
            if len(low) < 2 or len(low) > 40:
                continue
            if any(low.startswith(k) or k in low for k in _HEADER_FIELD_KEYS):
                # 同行右邻或下一行同 x 区域为值
                val = ''
                same_row = [c for c in cells if c[0] > x0]
                if same_row:
                    val = same_row[0][1]
                fields.append({'label': cell, 'value': val, 'x0': x0, 'y': r['y']})
                break
    return {'fields': fields, 'big_text': big_text, 'rows': all_rows}
def scan_disclaimer(items, W, H):
    """免责声明：从命中关键词的行起向后收集连续行（表底部区域），
    遇到下一表标题（BOREHOLE/CASING/LEGEND）截断。"""
    rows = rows_from_items(items, y_gap=14)
    disc_lines = []
    started = False
    for r in rows:
        t = r['text']
        if re.search(r'interpret|opinion|customer|guarantee|inferences', t, re.I) \
                and not re.search(r'result\s*plot', t, re.I):
            started = True
        if started:
            if re.search(r'^borehole|casing\s*record|^legend', t, re.I):
                break
            disc_lines.append(t)
    return {'disclaimer': ' '.join(disc_lines) if disc_lines else None}
def scan_legend(items, W, H):
    """LEGEND：标题 + 图例文字项（图标无法 OCR，保留文字供 symbol 匹配；
    无 symbol 时留空但文字必须保留）。整行与单元格双通道匹配，去重。"""
    rows = rows_from_items(items)
    title = None
    legend = []
    _KEY = ('oil', 'gas', 'water', 'shale', 'sand', 'coal', 'tight',
            'condensate', 'pay', 'reservoir', 'limestone', 'dolomite',
            'porosity', 'perme')
    for r in rows:
        text = r['text']
        if 'legend' in text.lower():
            title = text
            continue
        if any(k in text.lower() for k in _KEY):
            if not any(x.get('label') == text for x in legend):
                legend.append({'label': text, 'y': r['y']})
            continue
        for _x0, cell in r['cells']:
            low = cell.lower()
            if any(k in low for k in _KEY):
                if not any(x.get('label') == cell for x in legend):
                    legend.append({'label': cell, 'y': r['y']})
    return {'legend_title': title, 'legend_items': legend}
def scan_pdf(pdf_path, pages=(1, 2, 3), dpi=150, tmp_dir=None):
    doc = fitz.open(pdf_path)
    npages = doc.page_count
    doc.close()
    result = {'source': str(pdf_path), 'pages': npages, 'scanned': []}
    for pno in pages:
        if pno < 1 or pno > npages:
            continue
        # 页2/页3 只裁页面上部（免责声明/LEGEND 表头在顶部），OCR 更清晰
        _crop = (0.0, 1.0)
        if pno == 2:
            _crop = (0.0, 0.45)
        if pno == 3:
            _crop = (0.0, 0.35)
        img, (W, H) = page_to_png(pdf_path, pno - 1, dpi=dpi, out_dir=tmp_dir,
                                  crop=_crop)
        if not img:
            continue
        items = ocr_page(img)
        page = {'page': pno, 'size': [W, H], 'n_items': len(items),
                'crop': list(_crop)}
        # 页1 即完整右转表（信息字段+BH/CS+免责+LEGEND 同页），页2/3 按需
        if pno == 1:
            hdr = scan_header_page(items, W, H)
            page.update(hdr)
            page.update(scan_disclaimer(items, W, H))
            page.update(scan_legend(items, W, H))
        if pno in (2, 3):
            page.update(scan_disclaimer(items, W, H))
        if pno == 3:
            page.update(scan_legend(items, W, H))
        result['scanned'].append(page)
    return result

if __name__ == "__main__":
    if '--selftest' in sys.argv:
        _st_errs = run_selftest()
        sys.exit(1 if _st_errs else 0)
    if '--quicklook' in sys.argv:
        # quick look 快速解释: --quicklook <井文件夹> 或 --quicklook (弹对话框)
        # 可选 --quicklook-config <格式文件>：甲方格式配置文件，未指定按默认参考格式
        _ql_dir = None
        _ql_cfg_file = None
        if '--quicklook-config' in sys.argv:
            _ci = sys.argv.index('--quicklook-config')
            if _ci + 1 < len(sys.argv):
                _ql_cfg_file = sys.argv[_ci + 1]
        _ql_dir = None
        for _a in sys.argv[1:]:
            if not _a.startswith('-') and _a != _ql_cfg_file:
                _ql_dir = _a
                break
        try:
            quicklook_well(_ql_dir, config_file=_ql_cfg_file)
        except Exception as e:
            import traceback
            handle_exception(type(e), e, e.__traceback__, "quick look 快速解释")
            print()
            print("程序异常退出。")
        sys.exit(0)
    # 【2026-10-10】默认入口：数据选择界面（出图格式一次选定）
    # 未选 → 快速解释图（默认格式+默认图标）；也可命令行直传 LAS 走原工作流
    try:
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            run_well_log_workflow(file_path=sys.argv[1], plot_mode='all')
        else:
            _sel = select_run_mode()
            if _sel is None:
                print("已取消，未执行。")
                sys.exit(0)
            # 【2026-10-15 二五轮】_gas = 数据选择界面选定的气测文件（未选 None）
            _mode, _tgt, _cfg, _gas = _sel
            if _mode in ('quicklook', 'config'):
                quicklook_well(_tgt, config_file=_cfg, gas_file=_gas)
            else:
                run_well_log_workflow(file_path=_tgt, plot_mode=_mode, gas_file=_gas)
    except Exception as e:
        import traceback
        handle_exception(type(e), e, e.__traceback__, "程序启动")
        print()
        print("按 Enter 键退出...")
        input()