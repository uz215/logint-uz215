"""
NMR T2谱数据分析和可视化
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import json

def load_nmr_data(csv_file):
    """加载NMR数据"""
    df = pd.read_csv(csv_file)
    print(f"加载数据: {csv_file}")
    print(f"数据形状: {df.shape}")
    print(f"列名: {list(df.columns)[:10]}...")  # 显示前10列
    return df

def process_depth(df, depth_col='TDEP'):
    """处理深度数据"""
    # TDEP单位通常是0.1英寸，转换为米
    # 1英寸 = 0.0254米，所以 0.1英寸 = 0.00254米
    df['DEPTH_M'] = df[depth_col] * 0.00254
    
    # 或者如果TDEP是以0.1英尺为单位
    # df['DEPTH_M'] = df[depth_col] * 0.03048
    
    print(f"\n深度范围: {df['DEPTH_M'].min():.2f} m - {df['DEPTH_M'].max():.2f} m")
    print(f"深度间隔: {(df['DEPTH_M'].diff().mean()):.4f} m")
    
    return df

def extract_t2_spectrum(df):
    """提取T2谱数据"""
    # 获取T2_DIST列
    t2_cols = [col for col in df.columns if col.startswith('T2_DIST_')]
    t2_cols = sorted(t2_cols, key=lambda x: int(x.split('_')[-1]))
    
    print(f"\nT2谱分量数: {len(t2_cols)}")
    
    # 提取T2谱矩阵
    t2_spectrum = df[t2_cols].values
    
    # 处理无效值(-9999)
    t2_spectrum = np.where(t2_spectrum == -9999, np.nan, t2_spectrum)
    
    return t2_spectrum, t2_cols

def generate_t2_time_axis(n_components=64, t2_min=0.3e-3, t2_max=3.0):
    """
    生成T2时间轴（对数刻度）
    
    参数:
        n_components: T2分量数
        t2_min: 最小T2时间 (秒)
        t2_max: 最大T2时间 (秒)
    """
    # 对数均匀分布
    t2_times = np.logspace(np.log10(t2_min), np.log10(t2_max), n_components)
    return t2_times

def plot_t2_spectrum_map(df, t2_spectrum, t2_times, output_dir):
    """绘制T2谱深度分布图"""
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 10), gridspec_kw={'width_ratios': [3, 1]})
    
    depth = df['DEPTH_M'].values
    
    # 过滤无效数据
    valid_mask = ~np.isnan(t2_spectrum).all(axis=1)
    depth_valid = depth[valid_mask]
    t2_valid = t2_spectrum[valid_mask]
    
    # 左图：T2谱深度分布
    ax1 = axes[0]
    
    # 使用对数刻度显示T2时间
    t2_log = np.log10(t2_times * 1000)  # 转换为毫秒并取对数
    
    # 绘制热力图
    im = ax1.imshow(
        t2_valid.T,
        aspect='auto',
        origin='upper',
        extent=[depth_valid.min(), depth_valid.max(), t2_log.min(), t2_log.max()],
        cmap='jet',
        vmin=np.nanpercentile(t2_valid, 1),
        vmax=np.nanpercentile(t2_valid, 99)
    )
    
    ax1.set_xlabel('Depth (m)', fontsize=12)
    ax1.set_ylabel('T2 Time (ms, log scale)', fontsize=12)
    ax1.set_title('NMR T2 Spectrum Distribution', fontsize=14, fontweight='bold')
    
    # 设置Y轴刻度标签
    y_ticks = np.linspace(t2_log.min(), t2_log.max(), 5)
    y_labels = [f'{10**t:.2f}' for t in y_ticks]
    ax1.set_yticks(y_ticks)
    ax1.set_yticklabels(y_labels)
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax1, orientation='horizontal', pad=0.1, aspect=30)
    cbar.set_label('Porosity (v/v)', fontsize=10)
    
    # 右图：平均T2谱
    ax2 = axes[1]
    
    # 计算平均T2谱
    mean_t2 = np.nanmean(t2_valid, axis=0)
    ax2.plot(mean_t2, t2_log, 'b-', linewidth=2)
    ax2.fill_betweenx(t2_log, 0, mean_t2, alpha=0.3, color='blue')
    
    ax2.set_ylim(t2_log.min(), t2_log.max())
    ax2.set_yticks(y_ticks)
    ax2.set_yticklabels(y_labels)
    ax2.set_xlabel('Average Porosity', fontsize=12)
    ax2.set_title('Mean T2 Spectrum', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path = Path(output_dir) / 't2_spectrum_map.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n保存T2谱图: {output_path}")
    plt.close()

def plot_t2_logs(df, t2_spectrum, t2_times, output_dir):
    """绘制T2谱测井曲线"""
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    fig, axes = plt.subplots(1, 4, figsize=(16, 12), sharey=True)
    
    depth = df['DEPTH_M'].values
    
    # 过滤无效数据
    valid_mask = ~np.isnan(t2_spectrum).all(axis=1)
    depth_valid = depth[valid_mask]
    t2_valid = t2_spectrum[valid_mask]
    
    # 1. 深度道
    ax = axes[0]
    ax.plot(depth_valid, depth_valid, 'k-', linewidth=0.5)
    ax.set_xlabel('Depth (m)', fontsize=11)
    ax.set_ylabel('Depth (m)', fontsize=11)
    ax.set_title('Depth', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()
    
    # 2. 总孔隙度（所有T2分量之和）
    ax = axes[1]
    total_porosity = np.nansum(t2_valid, axis=1)
    ax.plot(total_porosity, depth_valid, 'b-', linewidth=1)
    ax.set_xlabel('Total Porosity (v/v)', fontsize=11)
    ax.set_title('Total Porosity', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, np.nanpercentile(total_porosity, 99) * 1.2)
    
    # 3. T2几何平均值
    ax = axes[2]
    # 计算T2几何平均值（加权几何平均）
    t2_log_mean = np.zeros(len(t2_valid))
    for i in range(len(t2_valid)):
        row = t2_valid[i]
        valid_t2 = ~np.isnan(row)
        if valid_t2.any():
            weights = row[valid_t2]
            times = t2_times[valid_t2]
            if weights.sum() > 0:
                log_times = np.log(times)
                t2_log_mean[i] = np.exp(np.average(log_times, weights=weights))
    
    ax.semilogx(t2_log_mean * 1000, depth_valid, 'g-', linewidth=1)  # 转换为毫秒
    ax.set_xlabel('T2 Log Mean (ms)', fontsize=11)
    ax.set_title('T2 Log Mean', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.1, 1000)
    
    # 4. T2谱分布（堆叠）
    ax = axes[3]
    
    # 选择几个代表性的T2分量显示
    indices = [0, 15, 31, 47, 63]  # 对应不同的T2时间
    colors = ['purple', 'blue', 'green', 'orange', 'red']
    labels = ['Short T2', 'Med-Short', 'Medium', 'Med-Long', 'Long T2']
    
    for idx, color, label in zip(indices, colors, labels):
        if idx < t2_valid.shape[1]:
            ax.plot(t2_valid[:, idx], depth_valid, color=color, linewidth=1, label=label)
    
    ax.set_xlabel('Porosity Component (v/v)', fontsize=11)
    ax.set_title('T2 Components', fontsize=12, fontweight='bold')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path = Path(output_dir) / 't2_logs.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"保存T2测井曲线: {output_path}")
    plt.close()

def calculate_nmr_parameters(df, t2_spectrum, t2_times):
    """计算NMR参数"""
    
    params = {}
    
    # 总孔隙度
    total_porosity = np.nansum(t2_spectrum, axis=1)
    params['total_porosity'] = total_porosity
    df['PHIT_NMR'] = total_porosity
    
    # 有效孔隙度 (T2 > 3ms通常认为是有效孔隙)
    effective_mask = t2_times > 3e-3
    effective_porosity = np.nansum(t2_spectrum[:, effective_mask], axis=1)
    params['effective_porosity'] = effective_porosity
    df['PHIE_NMR'] = effective_porosity
    
    # 束缚流体孔隙度 (T2 < 33ms通常认为是束缚流体)
    bound_mask = t2_times < 33e-3
    bound_porosity = np.nansum(t2_spectrum[:, bound_mask], axis=1)
    params['bound_porosity'] = bound_porosity
    df['PHIB_NMR'] = bound_porosity
    
    # 自由流体孔隙度
    free_porosity = effective_porosity - bound_porosity
    params['free_porosity'] = free_porosity
    df['PHIF_NMR'] = free_porosity
    
    # T2对数平均值
    t2_lm = np.zeros(len(t2_spectrum))
    for i in range(len(t2_spectrum)):
        row = t2_spectrum[i]
        valid = ~np.isnan(row)
        if valid.any():
            weights = row[valid]
            times = t2_times[valid]
            if weights.sum() > 0:
                log_times = np.log(times)
                t2_lm[i] = np.exp(np.average(log_times, weights=weights))
    params['t2_log_mean'] = t2_lm
    df['T2LM'] = t2_lm
    
    # 渗透率估算 (Coates模型)
    # K = C * (PHIE^4) * ((PHIF/PHIB)^2)
    c_factor = 10  # 经验系数
    permeability = np.zeros(len(t2_spectrum))
    for i in range(len(t2_spectrum)):
        if bound_porosity[i] > 0 and effective_porosity[i] > 0:
            perm = c_factor * (effective_porosity[i]**4) * ((free_porosity[i]/bound_porosity[i])**2)
            permeability[i] = perm
    params['permeability'] = permeability
    df['PERM_NMR'] = permeability
    
    print("\nNMR参数统计:")
    print(f"  总孔隙度: {np.nanmean(total_porosity):.4f} ± {np.nanstd(total_porosity):.4f}")
    print(f"  有效孔隙度: {np.nanmean(effective_porosity):.4f} ± {np.nanstd(effective_porosity):.4f}")
    print(f"  束缚流体: {np.nanmean(bound_porosity):.4f} ± {np.nanstd(bound_porosity):.4f}")
    print(f"  自由流体: {np.nanmean(free_porosity):.4f} ± {np.nanstd(free_porosity):.4f}")
    print(f"  T2对数均值: {np.nanmean(t2_lm)*1000:.2f} ms ± {np.nanstd(t2_lm)*1000:.2f} ms")
    print(f"  渗透率: {np.nanmean(permeability):.4f} mD ± {np.nanstd(permeability):.4f} mD")
    
    return params

def save_results(df, output_dir):
    """保存处理结果"""
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 保存完整数据
    csv_path = output_path / 'nmr_processed_data.csv'
    df.to_csv(csv_path, index=False)
    print(f"\n保存处理结果: {csv_path}")
    
    # 保存参数统计
    stats = {
        'depth_range': [float(df['DEPTH_M'].min()), float(df['DEPTH_M'].max())],
        'total_porosity_mean': float(df['PHIT_NMR'].mean()),
        'total_porosity_std': float(df['PHIT_NMR'].std()),
        'effective_porosity_mean': float(df['PHIE_NMR'].mean()),
        'effective_porosity_std': float(df['PHIE_NMR'].std()),
        't2_log_mean_mean': float(df['T2LM'].mean()),
        't2_log_mean_std': float(df['T2LM'].std()),
        'permeability_mean': float(df['PERM_NMR'].mean()),
        'permeability_std': float(df['PERM_NMR'].std()),
    }
    
    json_path = output_path / 'nmr_statistics.json'
    with open(json_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"保存统计信息: {json_path}")

def main():
    """主函数"""
    
    # 输入文件
    input_file = Path("output/dlis_data/dlis_lf1_frame1_75B.csv")
    output_dir = "output/nmr_analysis"
    
    if not input_file.exists():
        print(f"错误: 输入文件不存在 {input_file}")
        return
    
    print("="*60)
    print("NMR T2谱数据分析")
    print("="*60)
    
    # 1. 加载数据
    df = load_nmr_data(input_file)
    
    # 2. 处理深度
    df = process_depth(df)
    
    # 3. 提取T2谱
    t2_spectrum, t2_cols = extract_t2_spectrum(df)
    
    # 4. 生成T2时间轴
    t2_times = generate_t2_time_axis(n_components=len(t2_cols))
    print(f"\nT2时间范围: {t2_times.min()*1000:.3f} ms - {t2_times.max()*1000:.1f} ms")
    
    # 5. 计算NMR参数
    params = calculate_nmr_parameters(df, t2_spectrum, t2_times)
    
    # 6. 绘制T2谱图
    print("\n生成可视化...")
    plot_t2_spectrum_map(df, t2_spectrum, t2_times, output_dir)
    plot_t2_logs(df, t2_spectrum, t2_times, output_dir)
    
    # 7. 保存结果
    save_results(df, output_dir)
    
    print("\n" + "="*60)
    print("分析完成!")
    print("="*60)

if __name__ == "__main__":
    main()
