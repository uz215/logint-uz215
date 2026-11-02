import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import binary_dilation, label

def read_data(filename):
    """读取数据，返回原始数组和有效掩码"""
    depths, msfls, rhobs = [], [], []
    with open(filename, 'r') as f:
        lines = f.readlines()[1:]  # 跳过表头
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            d = float(parts[0])
            m = float(parts[1])
            r = float(parts[2])
        except:
            continue
        depths.append(d)
        msfls.append(m)
        rhobs.append(r)
    depths = np.array(depths)
    msfls = np.array(msfls)
    rhobs = np.array(rhobs)
    
    # 定义有效数据的掩码（排除仪器失效和无效值）
    valid = (msfls > -90000) & (rhobs > -90000)  # 排除 -99999
    valid &= (msfls < 1000) & (rhobs < 10)       # 排除特大值（如4806）
    valid &= (rhobs > 0.5)                       # 排除密度极小值
    return depths, msfls, rhobs, valid

def zero_crossing_rate(data, win=5):
    """
    计算滑动窗口内差分符号变化的次数（过零率）
    data: 一维数组
    win: 窗口大小（奇数）
    返回与原数据等长的数组，表示每个点的局部过零率
    """
    diff = np.diff(data)                # 差分
    sign = np.sign(diff)                # 符号：-1,0,1
    # 符号变化：相邻符号不同且非零
    sign_change = (sign[:-1] != sign[1:]) & (sign[:-1] != 0) & (sign[1:] != 0)
    # 扩展长度与原数据一致
    change_padded = np.zeros(len(data), dtype=int)
    change_padded[1:-1] = sign_change   # diff 长度 = len(data)-1, change 长度为 len(data)-2
    
    half = win // 2
    zcr = np.zeros(len(data))
    for i in range(len(data)):
        start = max(0, i - half)
        end = min(len(data), i + half + 1)
        zcr[i] = np.sum(change_padded[start:end])
    return zcr

def detect_spring_segments(zcr, threshold=3, min_len=3):
    """根据过零率标记弹簧段，合并相邻且长度足够的区域"""
    mask = zcr > threshold
    # 膨胀使相邻段连接（允许1个点的间隙）
    mask = binary_dilation(mask, iterations=1)
    # 去除长度小于 min_len 的孤立段
    labeled, num = label(mask)
    for i in range(1, num+1):
        if np.sum(labeled == i) < min_len:
            mask[labeled == i] = False
    return mask

def find_intervals(mask, depths):
    """从掩码中提取深度区间"""
    intervals = []
    in_seg = False
    start_idx = None
    for i, v in enumerate(mask):
        if v and not in_seg:
            in_seg = True
            start_idx = i
        elif not v and in_seg:
            in_seg = False
            intervals.append((depths[start_idx], depths[i-1]))
    if in_seg:
        intervals.append((depths[start_idx], depths[-1]))
    return intervals

def main():
    filename = '1.txt'
    depths, msfls, rhobs, valid = read_data(filename)
    
    # 只在有效数据点上进行检测（无效点不参与计算，但绘图时仍保留原始数据）
    valid_idx = np.where(valid)[0]
    if len(valid_idx) < 10:
        print("有效数据点太少，无法检测弹簧段。")
        return
    
    # 提取有效数据子集
    depths_valid = depths[valid_idx]
    msfls_valid = msfls[valid_idx]
    rhobs_valid = rhobs[valid_idx]
    
    # 计算过零率 (窗口大小可根据数据采样间隔调整，此处用5点)
    zcr_msfl = zero_crossing_rate(msfls_valid, win=5)
    zcr_rhob = zero_crossing_rate(rhobs_valid, win=5)
    
    # 阈值：可调整，经验值3~5
    mask_msfl = detect_spring_segments(zcr_msfl, threshold=3, min_len=3)
    mask_rhob = detect_spring_segments(zcr_rhob, threshold=3, min_len=3)
    
    # 提取深度区间（注意掩码对应有效子集的索引，需映射回原深度）
    msfl_intervals = find_intervals(mask_msfl, depths_valid)
    rhob_intervals = find_intervals(mask_rhob, depths_valid)
    
    print("MSFL 弹簧段深度区间：")
    for start, end in msfl_intervals:
        print(f"  {start:.2f} ~ {end:.2f}")
    print("RHOB 弹簧段深度区间：")
    for start, end in rhob_intervals:
        print(f"  {start:.2f} ~ {end:.2f}")
    
    # 绘图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 10))
    ax1.invert_yaxis()
    ax2.invert_yaxis()
    
    # 原始完整曲线（包括无效值，但图上可能显示异常尖峰，没关系）
    ax1.plot(msfls, depths, 'b-', linewidth=0.5, label='MSFL')
    ax2.plot(rhobs, depths, 'g-', linewidth=0.5, label='RHOB')
    
    # 高亮弹簧段（根据有效子集里的区间，在完整深度轴上绘制背景）
    for start, end in msfl_intervals:
        ax1.axhspan(start, end, facecolor='red', alpha=0.3)
    for start, end in rhob_intervals:
        ax2.axhspan(start, end, facecolor='red', alpha=0.3)
    
    ax1.set_xlabel('MSFL')
    ax1.set_ylabel('Depth (m)')
    ax1.set_title('MSFL (spring segments in red)')
    ax1.grid(True, alpha=0.3)
    ax2.set_xlabel('RHOB')
    ax2.set_ylabel('Depth (m)')
    ax2.set_title('RHOB (spring segments in red)')
    ax2.grid(True, alpha=0.3)
    ax1.legend(), ax2.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
核心改进说明
基于频率的检测
使用滑动窗口内的差分符号变化次数（过零率）来判断振荡频繁程度。正常地层变化平缓，差分符号变化少；弹簧段则会在小深度区间内来回跳动，过零率显著升高。

排除无效数据
通过 valid 掩码过滤掉 MSFL > 1000、RHOB < 0.5 或等于 -99999 等明显异常值，只对有效段进行过零率计算，避免这些点干扰检测结果。

独立检测 MSFL 和 RHOB
每条曲线单独检测，不强制合并，分别输出各自的弹簧段深度区间。绘图时也分别用红色背景高亮（您可以根据需要将二者合并，但脚本默认分开）。

参数可调

win（窗口大小）：默认 5 点（对应 0.5 米采样），可改为 7 或 9 适应不同频率。

threshold：过零率阈值，默认 3。调低会检出更多振荡段，调高更严格。

min_len：最小连续点数，过滤单点噪声。