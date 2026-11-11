# -*- coding: utf-8 -*-
"""隔离渲染 profile 道并保存 PNG，检查 1103-1373m 实际颜色"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, r'f:\360\src')
import logvis as lv

data = pd.read_csv(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv')
depth = data['MD'].values
depth_min = depth.min()
depth_max = depth.max()

# 模拟大图布局: ylim 330-2850, axes 高 0.9737
DEPTH_MIN_IMG, DEPTH_MAX_IMG = 330.0, 2850.0

fig = plt.figure(figsize=(24, 2500))
ax = fig.add_subplot(111)
ax.set_xlim(0, 1)
ax.set_ylim(DEPTH_MAX_IMG, DEPTH_MIN_IMG)
ax.patch.set_alpha(0)

# 模拟 set_position
fig.canvas.draw()
pos = ax.get_position()
ax.set_position([pos.x0, 0, pos.x1 - pos.x0, 0.9737])

lv._setup_profile_track(ax, data, depth, depth_min, depth_max,
                        0.9, 0.9, 1.0, True)

fig.savefig(r'f:\360\src\isolated_profile.png', dpi=80, bbox_inches='tight')
plt.close(fig)
print('saved isolated_profile.png')
