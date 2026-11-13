import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class SpringSegmentDetector:
    """
    使用差分符号变化次数（过零率）检测弹簧段
    弹簧段特点：曲线在短距离内频繁改变方向，差分符号频繁变化
    """
    
    def __init__(self):
        pass
    
    def detect_spring_segments(self, data, curve_name='MSFL', min_segment_length=5.0):
        """
        使用差分符号变化次数（过零率）检测弹簧段
        
        参数:
            data: 测井数据DataFrame
            curve_name: 要检测的曲线名称
            min_segment_length: 最小弹簧段长度（米）
        
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
        
        # 计算采样间隔
        dz = np.mean(np.diff(depth_data))
        if dz == 0:
            dz = 0.1
        
        # ==================== 核心检测：差分符号变化次数（过零率）检测 ====================
        
        # 1. 计算一阶差分
        first_diff = np.diff(curve_data)
        
        # 2. 计算差分的符号序列
        diff_signs = np.sign(first_diff)
        
        # 3. 滑动窗口过零率检测
        window_size = int(3 / dz)  # 3米窗口
        if window_size < 10:
            window_size = 10
        if window_size > 20:
            window_size = 20
        
        half_window = window_size // 2
        zc_rates = np.zeros(len(curve_data))
        
        # 先计算所有窗口的过零率
        for i in range(half_window, len(curve_data) - half_window):
            window_diff = first_diff[i-half_window:i+half_window]
            window_signs = np.sign(window_diff)
            window_sign_changes = np.sum(np.diff(window_signs) != 0)
            
            window_length_m = window_size * dz
            if window_length_m > 0:
                zc_rates[i] = window_sign_changes / window_length_m
        
        # 计算过零率的中位数（更稳健）
        valid_zc_rates = zc_rates[zc_rates > 0]
        if len(valid_zc_rates) == 0:
            logger.warning(f"{curve_name} 曲线数据变化为零，无法检测弹簧段")
            return []
        
        median_zc_rate = np.median(valid_zc_rates)
        mad_zc = np.median(np.abs(valid_zc_rates - median_zc_rate))
        
        # 弹簧段判定：过零率显著高于中位数
        # 使用中位数 + 2*MAD作为阈值（降低阈值提高灵敏度）
        zc_threshold = median_zc_rate + 2 * mad_zc
        
        # 设置合理的阈值范围
        # 根据曲线类型调整阈值
        if curve_name in ['RHOB', 'DEN']:
            # 密度曲线振荡幅度较小，降低阈值
            min_threshold = 4
            max_threshold = 8
        else:
            # 电阻率曲线振荡幅度较大
            min_threshold = 5
            max_threshold = 10
        
        if zc_threshold < min_threshold:
            zc_threshold = min_threshold
        if zc_threshold > max_threshold:
            zc_threshold = max_threshold
        
        # 标记弹簧段候选区域（使用 >= 以包含等于阈值的情况）
        spring_candidate = zc_rates >= zc_threshold
        
        # 使用形态学操作连接邻近的候选区域
        # 创建一个结构元素来连接邻近的点
        min_connect_length = int(5 / dz)  # 至少5米的连续区域
        if min_connect_length < 10:
            min_connect_length = 10
        
        # 先进行膨胀操作，连接邻近的候选点
        expanded = np.copy(spring_candidate)
        for i in range(len(spring_candidate)):
            if spring_candidate[i]:
                # 扩展到前后各min_connect_length/2个点
                start_idx = max(0, i - min_connect_length // 2)
                end_idx = min(len(spring_candidate), i + min_connect_length // 2)
                expanded[start_idx:end_idx] = True
        
        # 然后进行腐蚀操作，保持区域完整性
        final_candidate = np.copy(expanded)
        for i in range(len(expanded)):
            if expanded[i]:
                # 检查周围是否有足够的候选点
                start_idx = max(0, i - min_connect_length // 2)
                end_idx = min(len(expanded), i + min_connect_length // 2)
                if np.sum(expanded[start_idx:end_idx]) < min_connect_length // 2:
                    final_candidate[i] = False
        
        spring_candidate = final_candidate
        
        logger.info(f"弹簧段检测 - {curve_name}:")
        logger.info(f"  采样间隔: {dz:.3f}m")
        logger.info(f"  过零率中位数: {median_zc_rate:.2f} 次/米")
        logger.info(f"  过零率阈值: {zc_threshold:.2f} 次/米")
        logger.info(f"  候选弹簧段点数: {np.sum(spring_candidate)}/{len(spring_candidate)}")
        
        # 检查候选点的连续性
        if np.sum(spring_candidate) > 0:
            # 找到所有连续区域
            candidate_indices = np.where(spring_candidate)[0]
            if len(candidate_indices) > 0:
                # 计算连续区域
                regions = []
                start_idx = candidate_indices[0]
                for i in range(1, len(candidate_indices)):
                    if candidate_indices[i] != candidate_indices[i-1] + 1:
                        regions.append((candidate_indices[i-1] - start_idx + 1))
                        start_idx = candidate_indices[i]
                regions.append((candidate_indices[-1] - start_idx + 1))
                
                logger.info(f"  候选区域数量: {len(regions)}")
                logger.info(f"  最大连续候选点数: {max(regions) if regions else 0}")
                logger.info(f"  最大连续长度: {max(regions) * dz:.2f}m")
        
        # ==================== 合并连续的弹簧段候选点 ====================
        spring_segments = []
        in_spring = False
        start_depth = None
        
        for i in range(len(spring_candidate)):
            if spring_candidate[i]:
                if not in_spring:
                    in_spring = True
                    start_depth = depth_data[i]
            else:
                if in_spring:
                    in_spring = False
                    end_depth = depth_data[i]
                    if end_depth - start_depth >= min_segment_length:
                        spring_segments.append((start_depth, end_depth))
        
        # 处理最后一个弹簧段
        if in_spring and start_depth is not None:
            end_depth = depth_data[-1]
            if end_depth - start_depth >= min_segment_length:
                spring_segments.append((start_depth, end_depth))
        
        logger.info(f"{curve_name} 曲线检测到 {len(spring_segments)} 个弹簧段")
        if spring_segments:
            for seg in spring_segments:
                logger.info(f"  - 弹簧段: {seg[0]:.1f}m - {seg[1]:.1f}m")
        
        return spring_segments

    def correct_spring_segments(self, data, curve_names=None, depth_range=None, method='spline'):
        """
        校正弹簧段
        """
        if curve_names is None:
            curve_names = ['MSFL', 'RHOB']
        
        result = data.copy()
        
        for curve_name in curve_names:
            if curve_name not in data.columns:
                logger.warning(f"曲线 {curve_name} 不存在，跳过校正")
                continue
            
            spring_segments = self.detect_spring_segments(data, curve_name)
            
            if depth_range is not None:
                start_range, end_range = depth_range
                spring_segments = [(s, e) for s, e in spring_segments 
                                   if s >= start_range and e <= end_range]
            
            logger.info(f"对 {curve_name} 曲线进行弹簧段校正，共 {len(spring_segments)} 个弹簧段")
            
            for start_depth, end_depth in spring_segments:
                if method == 'spline':
                    result = self._spline_smoothing(result, curve_name, start_depth, end_depth)
                elif method == 'median':
                    result = self._median_filter(result, curve_name, start_depth, end_depth)
            
            result[f'{curve_name}_corrected'] = False
            if depth_range is not None:
                result.loc[(result['MD'] >= depth_range[0]) & (result['MD'] <= depth_range[1]), f'{curve_name}_corrected'] = True
        
        return result
    
    def _spline_smoothing(self, data, curve_name, start_depth, end_depth):
        """使用样条插值平滑校正弹簧段"""
        from scipy.interpolate import make_interp_spline
        
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        spring_data = data[mask].copy()
        
        if len(spring_data) < 3:
            return data
        
        before_mask = data['MD'] < start_depth
        after_mask = data['MD'] > end_depth
        
        if not before_mask.any() or not after_mask.any():
            return data
        
        before_points = data[before_mask].tail(5)
        after_points = data[after_mask].head(5)
        
        combined = pd.concat([before_points, spring_data, after_points])
        
        x = combined['MD'].values
        y = combined[curve_name].values
        
        spline = make_interp_spline(x, y, k=3)
        
        spring_depths = spring_data['MD'].values
        corrected_values = spline(spring_depths)
        
        result = data.copy()
        result.loc[mask, curve_name] = corrected_values
        
        return result
    
    def _median_filter(self, data, curve_name, start_depth, end_depth, window_size=5):
        """使用中值滤波校正弹簧段"""
        mask = (data['MD'] >= start_depth) & (data['MD'] <= end_depth)
        
        if not mask.any():
            return data
        
        result = data.copy()
        result.loc[mask, curve_name] = result[curve_name].rolling(window_size, center=True, min_periods=1).median()
        
        return result

# 测试函数
def test_spring_detection():
    logging.basicConfig(level=logging.INFO)
    
    # 创建测试数据
    depths = np.arange(2700, 2850, 0.1)
    data = pd.DataFrame({'MD': depths})
    
    # 创建正常曲线
    data['GR'] = 50 + 20 * np.sin(depths * 0.1)
    
    # 创建弹簧段曲线（2710-2830米）
    msfl_base = 10 + depths * 0.01
    spring_mask = (depths >= 2710) & (depths <= 2830)
    
    # 弹簧段：模拟真实的弹簧效应 - 高频振荡
    # 使用更高频率和更大幅度的振荡来模拟弹簧段
    msfl_base[spring_mask] += 5 * np.sin(depths[spring_mask] * 40) + 3 * np.cos(depths[spring_mask] * 60)
    data['MSFL'] = msfl_base
    
    # 创建密度曲线（也有弹簧段）
    rho_base = 2.65 - 0.001 * (depths - 2700)
    rho_base[spring_mask] += 0.05 * np.sin(depths[spring_mask] * 50) + 0.03 * np.cos(depths[spring_mask] * 70)
    data['RHOB'] = rho_base
    
    # 检测弹簧段
    detector = SpringSegmentDetector()
    msfl_segments = detector.detect_spring_segments(data, 'MSFL')
    rhob_segments = detector.detect_spring_segments(data, 'RHOB')
    
    print(f"\nMSFL 弹簧段检测结果: {msfl_segments}")
    print(f"RHOB 弹簧段检测结果: {rhob_segments}")
    
    # 校正
    corrected_data = detector.correct_spring_segments(data, ['MSFL', 'RHOB'])
    print("\n弹簧段校正完成")
    
    return corrected_data

if __name__ == '__main__':
    test_spring_detection()
