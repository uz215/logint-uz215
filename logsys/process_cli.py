# -*- coding: utf-8 -*-
"""专用处理作业的无界面 CLI：气测解释 / 核磁处理 / 电成像处理。

为什么单独做一层
----------------
三个历史脚本（Gas.py、NMR20260318.py、FMI.py）都把「弹文件对话框」写进了
``__main__``，且各自硬编码 ``output/`` 相对路径；直接在项目作业子进程里跑会
阻塞、产物散落、井名对不上。本模块只调用它们的**纯计算入口**，把井名与输出
目录显式传进去，产物统一写 ``<项目根>/<井名>/``，与 quicklook / 综合解释的
闭环一致。

本文件被 :meth:`logsys.project_job.JobRunner` 以子进程方式调用，GUI 不 import 它。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

# matplotlib 后端必须在 import 任何绘图模块之前确定（子进程无显示）
os.environ.setdefault('MPLBACKEND', 'Agg')

# 子进程以 `python logsys/process_cli.py` 启动时 sys.path[0] 是 logsys/，
# 仓库根不在搜索路径里；三个历史脚本都在根目录，必须显式补上。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ----------------------------------------------------------------- 公共工具

def _out_dir(project_root: str, well: str) -> str:
    if not project_root or not well:
        raise ValueError('缺少项目根或井名')
    d = os.path.join(os.path.abspath(project_root), well)
    os.makedirs(d, exist_ok=True)
    return d


def _find_file(source_dir: str, keys: tuple[str, ...], exts: tuple[str, ...]) -> str:
    if not source_dir or not os.path.isdir(source_dir):
        return ''
    cands = []
    for base, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            low = fn.lower()
            if not low.endswith(exts):
                continue
            if not any(k in low for k in keys):
                continue
            cands.append(os.path.join(base, fn))
    cands.sort(key=lambda p: (p.count(os.sep), len(p)))
    return cands[0] if cands else ''


def _depth_from(path: str):
    """从解释曲线集（CSV）或 LAS 读主深度网格，返回 pandas.Series。"""
    import pandas as pd
    if not path or not os.path.isfile(path):
        raise ValueError('缺少可用于对齐深度的曲线集或 LAS：%s' % path)
    if path.lower().endswith(('.csv', '.txt')):
        df = pd.read_csv(path, encoding='utf-8-sig')
        col = next((c for c in ('DEPTH', 'MD', 'Depth', 'depth') if c in df.columns), '')
        if not col:
            raise ValueError('深度文件无 DEPTH/MD 列：%s' % path)
        return df[col].astype(float)
    import lasio
    las = lasio.read(path)
    df = las.df()
    return pd.Series(df.index.astype(float), name='DEPTH')


def _find_main_las(source_dir: str) -> str:
    if not source_dir or not os.path.isdir(source_dir):
        return ''
    cands = []
    for fn in os.listdir(source_dir):
        low = fn.lower()
        if low.endswith(('.las', '.las2')) and not any(
                k in low for k in ('gas', 'flair', '气测')):
            p = os.path.join(source_dir, fn)
            cands.append((os.path.getsize(p), p))
    if not cands:
        return ''
    return sorted(cands, reverse=True)[0][1]


def _write_json(path: str, payload: dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


# ----------------------------------------------------------------- 产物并入曲线集
# 【R89】所有专用处理作业的输出都并入 <井>_processed.csv，成为**处理井的
# 曲线变量**：与测井曲线同权、挂在输入 LAS/DLIS 数据集下、可拖入 logvis
# 作图。产物 CSV 本身仍保留作为原始记录，但变量来源 = 曲线集。


def _resample_to_grid(src_depth, src_vals, grid, qualitative: bool):
    """把产物列对齐到曲线集深度网格：数值线性插值，定性最近邻（不外推）。"""
    import numpy as np
    import pandas as pd
    x = np.asarray(pd.to_numeric(pd.Series(src_depth), errors='coerce'), dtype=float)
    ok = np.isfinite(x)
    x = x[ok]
    if qualitative:
        vals = [list(src_vals)[i] for i in np.where(ok)[0]]
        out = []
        for g in np.asarray(grid, dtype=float):
            if x.size == 0:
                out.append('')
                continue
            i = int(np.abs(x - g).argmin())
            out.append(vals[i] if abs(x[i] - g) <= 1e-3 else '')
        return out
    y = np.asarray(pd.to_numeric(pd.Series(list(src_vals))[ok] if hasattr(src_vals, '__len__') else src_vals,
                                  errors='coerce'), dtype=float)
    out = np.full(len(grid), np.nan)
    if x.size >= 2:
        g = np.asarray(grid, dtype=float)
        m = (g >= x.min()) & (g <= x.max())
        out[m] = np.interp(g[m], x, y)
    return out


def _merge_into_processed(well: str, out_dir: str, df, mapping: dict = None,
                          qualitative_cols: tuple = ()) -> str:
    """把作业产物 DataFrame 按 DEPTH 对齐并入 ``<井>_processed.csv``。

    mapping: {产物列名 → 变量库 key}；未列出的产物列丢弃（原始 CSV 里仍留档）。
    产物深度列（DEPTH/MD/Depth/depth）统一为 DEPTH。
    - 曲线集已存在：同名列先删旧再写入（重跑作业覆盖旧结果），数值列插值、
      定性列最近邻对齐到**曲线集的深度网格**；
    - 不存在：以产物深度为骨架新建（即首个作业先建立处理井曲线集）。
    返回 processed.csv 路径。
    """
    import pandas as pd
    proc = os.path.join(out_dir, '%s_processed.csv' % well)
    mapping = dict(mapping or {})
    dcol = next((c for c in ('DEPTH', 'MD', 'Depth', 'depth') if c in df.columns), '')
    if not dcol:
        raise ValueError('产物缺少深度列（DEPTH/MD）：%s' % list(df.columns))
    depth = pd.to_numeric(df[dcol], errors='coerce')
    cols: dict[str, object] = {}
    for src, dst in mapping.items():
        if src in df.columns:
            cols[dst] = df[src]
    if not mapping:
        # 产物列名即变量 key（如气测 GAS_ITP/GAS_ANOM/GAS_ANOM_RATIO）：
        # 保留全部非深度列
        for c in df.columns:
            if c != dcol:
                cols[str(c).strip()] = df[c]
    if not cols:
        raise ValueError('产物无可用映射列：%s → %s' % (list(df.columns), mapping))

    if os.path.isfile(proc):
        base = pd.read_csv(proc, encoding='utf-8-sig')
        base.columns = [str(c).strip() for c in base.columns]
        bdep = next((c for c in ('DEPTH', 'MD', 'Depth', 'depth') if c in base.columns), '')
        if not bdep:
            raise ValueError('曲线集缺深度列：%s' % list(base.columns))
        if bdep != 'DEPTH':
            base = base.rename(columns={bdep: 'DEPTH'})
        grid = pd.to_numeric(base['DEPTH'], errors='coerce').to_numpy(dtype=float)
        added = pd.DataFrame({'DEPTH': grid})
        for dst, vals in cols.items():
            qual = dst in qualitative_cols or (
                hasattr(vals, 'dtype') and vals.dtype == object)
            added[dst] = _resample_to_grid(depth, vals, grid, qualitative=bool(qual))
        # 重跑覆盖：删掉旧的同名列再并入
        for c in added.columns[1:]:
            if c in base.columns:
                base = base.drop(columns=[c])
        merged = pd.concat([base.reset_index(drop=True),
                            added.drop(columns=['DEPTH']).reset_index(drop=True)],
                           axis=1)
        merged = merged.sort_values('DEPTH').reset_index(drop=True)
    else:
        added = pd.DataFrame({'DEPTH': depth.to_numpy(dtype=float)})
        for dst, vals in cols.items():
            added[dst] = list(vals)
        merged = added.sort_values('DEPTH').reset_index(drop=True)
    merged.to_csv(proc, index=False, encoding='utf-8')
    return proc


# ----------------------------------------------------------------- 气测解释

def run_gas(args):
    import pandas as pd
    out = _out_dir(args.project_root, args.well)
    gas = args.input or ''
    if not gas and args.source_dir:
        from gas_constraint import find_gas_file
        gas = find_gas_file(args.well, [args.source_dir]) or ''
    if not gas or not os.path.isfile(gas):
        raise FileNotFoundError('未找到气测数据文件（可在「数据导入 / 井级资料指定」中手工指定）')

    depth_src = args.depth_from or _find_main_las(args.source_dir)
    if not depth_src and args.project_root:
        # 产物目录里已有解释曲线集时，直接用它对齐（省去重复读 LAS）
        p = os.path.join(args.project_root, args.well, '%s_processed.csv' % args.well)
        if os.path.isfile(p):
            depth_src = p
    main_md = _depth_from(depth_src)

    print('▶ 气测解释：%s' % gas, flush=True)
    print('  深度来源：%s（%d 点）' % (depth_src, len(main_md)), flush=True)
    from gas_constraint import run_gas_constraint_for_well
    r = run_gas_constraint_for_well(args.well, gas, main_md)
    itp = r.get('itp')
    anom = r.get('anom')
    ratio = r.get('anom_ratio')
    if itp is None:
        print('⚠ 图版法未产出 ITP（已保留相对异常曲线）', flush=True)
        itp = pd.Series(['DRY'] * len(main_md))
    out_df = pd.DataFrame({
        'DEPTH': main_md.to_numpy(dtype=float),
        'GAS_ITP': list(itp),
        'GAS_ANOM': list(anom) if anom is not None else [float('nan')] * len(main_md),
        'GAS_ANOM_RATIO': list(ratio) if ratio is not None else [float('nan')] * len(main_md),
    })
    curves = os.path.join(out, '%s_gas_curves.csv' % args.well)
    out_df.to_csv(curves, index=False, encoding='utf-8')
    raw = r.get('raw')
    if raw is not None and hasattr(raw, 'to_csv'):
        raw.to_csv(os.path.join(out, '%s_gas_raw.csv' % args.well),
                   index=False, encoding='utf-8')
    # 【R89】产物并入处理井曲线集（GAS_ITP 为定性代码 → 最近邻对齐）
    proc = _merge_into_processed(args.well, out, out_df,
                                 qualitative_cols=('GAS_ITP',))
    summary = {
        'well': args.well, 'gas_file': gas, 'depth_source': depth_src,
        'points': len(out_df), 'used_gaspy': bool(r.get('used_gaspy')),
        'anomaly_points': int(pd.to_numeric(out_df['GAS_ANOM'], errors='coerce').fillna(0).sum()),
        'itp_counts': {str(k): int(v) for k, v in out_df['GAS_ITP'].value_counts().items()},
        'merged_into': proc,
        'time': datetime.now().isoformat(timespec='seconds'),
    }
    _write_json(os.path.join(out, '%s_gas_result.json' % args.well), summary)
    print('✔ 气测解释完成：%s（%d 点）\n  已并入曲线集：%s'
          % (curves, len(out_df), proc), flush=True)
    return 0


# ----------------------------------------------------------------- 核磁处理

def run_nmr(args):
    import glob
    import shutil
    out = _out_dir(args.project_root, args.well)
    src = args.input or ''
    if not src and args.source_dir:
        src = _find_file(args.source_dir,
                         ('nmr', '核磁', 't2', 'cmr'),
                         ('.csv', '.xlsx', '.xls', '.dlis')) or _find_main_las(args.source_dir)
    if not src or not os.path.isfile(src):
        raise FileNotFoundError('未找到核磁数据文件（可在「数据导入 / 井级资料指定」中手工指定）')

    # 输出目录显式给绝对路径；脚本内部 CSV 固定写 <output_dir>/nmr/。
    cfg = {'output_dir': out, 'data_formats': ['csv', 'las', 'dlis'],
           'quality_check': True, 'feature_engineering': True,
           'interpretation_methods': ['traditional'],
           'visualization': True, 'report_generation': False, 'model_config': {}}
    print('▶ 核磁处理：%s' % src, flush=True)
    from NMR20260318 import NMRProcessor
    res = NMRProcessor(cfg).run_workflow(src)
    if res is None:
        raise RuntimeError('核磁工作流返回空结果，请检查输入数据是否含 T2 分量列')

    # 脚本按输入文件名猜井名；统一改成项目登记名，logvis 才能按 <井名> 聚合。
    orig = str(res.get('well_name') or '').strip()
    for p in sorted(glob.glob(os.path.join(out, '%s_*.png' % orig))) if orig else []:
        if orig == args.well:
            continue
        dst = os.path.join(out, args.well + os.path.basename(p)[len(orig):])
        shutil.move(p, dst)
    # 历史脚本的 CSV 路径硬编码为相对 CWD 的 output/nmr/，不认 config 的
    # output_dir（PNG 走 config，CSV 不走）。因此两处都找，以最新一份为准。
    csv_dirs = [os.path.join(out, 'nmr'),
                os.path.join(os.getcwd(), 'output', 'nmr')]
    csvs = []
    for d in csv_dirs:
        csvs += glob.glob(os.path.join(d, '*_nmr_results_*.csv'))
    csvs = sorted(set(csvs), key=os.path.getmtime, reverse=True)
    if not csvs:
        raise RuntimeError('核磁处理结果 CSV 未生成（查找：%s）' % '；'.join(csv_dirs))
    # 只留最新一份，避免 logvis 按排序取到过期谱
    kept = os.path.join(out, '%s_nmr_results_latest.csv' % args.well)
    shutil.copy2(csvs[0], kept)
    for p in csvs[1:]:
        try:
            os.remove(p)
        except OSError:
            pass
    depth = res.get('depth')
    centers = res.get('t2_centers')
    # 【R89】核磁一维派生量并入处理井曲线集（T2 谱二维数据仍由 latest.csv 供 logvis 读）
    nmr_map = {'T2_GM': 'T2LM', 'T1': 'NMR_T1', 'D': 'NMR_D', 'Porosity': 'TCMR',
               'Permeability_SDR': 'NMR_PERM_SDR',
               'Permeability_Coates': 'NMR_PERM_COATES',
               'Clay_Bound_Fluid': 'NMR_CBW',
               'Capillary_Bound_Fluid': 'BVI', 'Free_Fluid': 'FFI',
               '0.3-1ms': 'NMR_IV03_1', '1-10ms': 'NMR_IV1_10',
               '10-33ms': 'NMR_IV10_33', '33-100ms': 'NMR_IV33_100',
               '100-300ms': 'NMR_IV100_300', '300-1000ms': 'NMR_IV300_1000',
               '1000-3000ms': 'NMR_IV1000_3000'}
    proc = ''
    try:
        import pandas as pd
        nmr_df = pd.read_csv(kept, encoding='utf-8-sig')
        proc = _merge_into_processed(args.well, out, nmr_df, mapping=nmr_map)
    except Exception as e:  # 并入失败不掩盖处理本身的成功
        print('⚠ 核磁产物并入曲线集失败：%s: %s' % (type(e).__name__, e), flush=True)
    summary = {
        'well': args.well, 'input': src,
        'rows': int(len(depth)) if depth is not None else 0,
        't2_bins': int(len(centers)) if centers is not None else 0,
        'csv': kept, 'source_name': orig, 'merged_into': proc,
        'time': datetime.now().isoformat(timespec='seconds'),
    }
    _write_json(os.path.join(out, '%s_nmr_result.json' % args.well), summary)
    print('✔ 核磁处理完成：%s（%d 点，%d 个 T2 bin）%s'
          % (kept, summary['rows'], summary['t2_bins'],
             '\n  已并入曲线集：%s' % proc if proc else ''), flush=True)
    return 0


# ----------------------------------------------------------------- 电成像处理

def run_fmi(args):
    import glob
    import shutil
    out = _out_dir(args.project_root, args.well)
    src = args.input or ''
    if not src and args.source_dir:
        src = _find_file(args.source_dir,
                         ('fmi', '成像', 'image', 'microres'),
                         ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.csv', '.las'))
    if not src or not os.path.isfile(src):
        raise FileNotFoundError('未找到电成像数据文件（可在「数据导入 / 井级资料指定」中手工指定）')

    print('▶ 电成像处理：%s' % src, flush=True)
    from microresistivity_imaging import MicroresistivityImagingProcessor
    # 必须带全套默认参数（sigma / canny_sigma / 阈值…），只给 output_dir
    # 会在 identify_features 里 KeyError: 'sigma'。
    config = MicroresistivityImagingProcessor().config
    config['output_dir'] = out
    r = MicroresistivityImagingProcessor(config).run_workflow(src)
    if r is None:
        raise RuntimeError('电成像工作流返回空结果，请检查图像/曲线数据格式')
    # 固定输出名统一带井名，避免多井互相覆盖
    raw = os.path.join(out, 'microresistivity_results.csv')
    named = os.path.join(out, '%s_fmi_results.csv' % args.well)
    if os.path.isfile(raw) and os.path.abspath(raw) != os.path.abspath(named):
        shutil.move(raw, named)
    imgs = sorted(glob.glob(os.path.join(out, 'visualization', '*.png')))
    # 【R89】电成像逐深度结果并入处理井曲线集；图像路径的单行汇总不并入（无深度）
    fmi_map = {'Porosity': 'FMI_POROSITY', 'Pore_Count': 'FMI_VUG',
               'Fracture_Count': 'FMI_FRAC'}
    proc = ''
    try:
        import pandas as pd
        fmi_df = pd.read_csv(named, encoding='utf-8-sig')
        if any(c in fmi_df.columns for c in fmi_map) and \
                any(str(c).upper() in ('MD', 'DEPTH') for c in fmi_df.columns):
            proc = _merge_into_processed(args.well, out, fmi_df, mapping=fmi_map)
        else:
            print('ℹ 电成像结果为整段汇总（无逐深度数据），不并入曲线集', flush=True)
    except Exception as e:  # 并入失败不掩盖处理本身的成功
        print('⚠ 电成像产物并入曲线集失败：%s: %s' % (type(e).__name__, e), flush=True)
    summary = {
        'well': args.well, 'input': src, 'result': r,
        'csv': named if os.path.isfile(named) else '',
        'images': len(imgs), 'merged_into': proc,
        'time': datetime.now().isoformat(timespec='seconds'),
    }
    _write_json(os.path.join(out, '%s_fmi_result.json' % args.well), summary)
    print('✔ 电成像处理完成：%s（%d 张图）%s'
          % (named, len(imgs),
             '\n  已并入曲线集：%s' % proc if proc else ''), flush=True)
    return 0


# ----------------------------------------------------------------- 入口

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='专用处理作业（供项目工作台调用）')
    ap.add_argument('job', choices=('gas', 'nmr', 'fmi'))
    ap.add_argument('--well', required=True)
    ap.add_argument('--project-root', required=True, help='项目产物根（如 <repo>/output）')
    ap.add_argument('--source-dir', default='', help='井的原始资料目录')
    ap.add_argument('--input', default='', help='手工指定的处理输入文件（优先）')
    ap.add_argument('--depth-from', default='', help='气测对齐用的 LAS / 解释曲线集')
    args = ap.parse_args(argv)
    try:
        return {'gas': run_gas, 'nmr': run_nmr, 'fmi': run_fmi}[args.job](args)
    except Exception as e:
        import traceback
        print('✖ %s 处理失败：%s: %s' % (args.job, type(e).__name__, e), flush=True)
        print(traceback.format_exc(), flush=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
