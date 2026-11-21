# -*- coding: utf-8 -*-
"""数据功能统一入口：加载 / 清洗 / 质检 / 导入 / 导出。

R86 起，主界面的「数据功能」区只用这一层，不再把数据操作散落在右键菜单
和 logInt 内部。设计原则：

- **只读优先**：加载与质检不改任何文件；清洗与导出写**新文件**，绝不覆盖
  解释原始产物；导入只做复制，不移动、不删除源文件；
- **产物留痕**：清洗/质检报告落在 ``output/<井名>/``，与曲线产物同处，供
  项目树扫描与追溯；
- **纯标准库 + pandas**：不在 GUI 进程里 import logInt（那是 2 万行重模块，
  会带 Qt/fitz/matplotlib 全局状态）。

用法：见各函数 docstring，或主界面「数据功能」功能区。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

#: 常见测井曲线列（质检时按存在与否检查）
CURVE_HINTS = ('GR', 'SP', 'RT', 'RXO', 'RHOB', 'NPHI', 'DT', 'PHI', 'CAL', 'PE')


def _read_csv(path: str):
    import pandas as pd
    return pd.read_csv(path, encoding='utf-8-sig')


def _depth_col(df) -> str:
    for c in ('DEPTH', 'MD', 'Depth', 'depth', 'DEPTH_MD'):
        if c in df.columns:
            return c
    return ''


def _text_lines(lines: list[str]) -> str:
    return '\n'.join(str(x) for x in lines)


# ---------------------------------------------------------------- 数据加载

def discover_inputs(source_dir: str, out_dir: str = '') -> dict:
    """扫描一口井的可用数据（只读），按用途分组返回绝对路径列表。"""
    out = {'las': [], 'gas': [], 'nmr': [], 'fmi': [], 'processed': [], 'array': [], 'doc': []}
    roots = [d for d in (source_dir, out_dir) if d and os.path.isdir(d)]
    for root in roots:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fn in files:
                p = os.path.join(base, fn)
                low = fn.lower()
                if low.endswith(('.las', '.las2')) and 'gas' not in low:
                    out['las'].append(p)
                elif any(k in low for k in ('gas', 'flair', '气测')) and low.endswith(
                        ('.las', '.csv', '.txt', '.dat', '.xls', '.xlsx')):
                    out['gas'].append(p)
                elif any(k in low for k in ('nmr', '核磁', 't2', 'cmr')):
                    out['nmr'].append(p)
                elif any(k in low for k in ('fmi', '成像', 'image', 'microres')):
                    out['fmi'].append(p)
                elif low.endswith('_processed.csv') or low.endswith('-processed.csv'):
                    out['processed'].append(p)
                elif low.endswith(('.csv', '.xlsx', '.xls')):
                    out['array'].append(p)
                elif low.endswith(('.pdf', '.docx', '.doc', '.md')):
                    out['doc'].append(p)
    for k in out:
        out[k] = sorted(set(out[k]))
    return out


def load_summary(well: str, source_dir: str, out_dir: str = '') -> str:
    """为「数据加载」面板生成只读摘要。"""
    d = discover_inputs(source_dir, out_dir)
    lines = ['井：%s' % well,
             '源目录：%s' % (source_dir or '（未关联）'),
             '产物目录：%s' % (out_dir or '（尚未生成）'), '']
    for key, label in (('las', '测井 LAS'), ('gas', '气测数据'), ('nmr', '核磁数据'),
                       ('fmi', '电成像数据'), ('processed', '解释曲线集'),
                       ('array', '二维/表格数据'), ('doc', '文档资料')):
        items = d[key]
        lines.append('%s：%d 个' % (label, len(items)))
        for p in items[:4]:
            lines.append('    %s' % p)
        if len(items) > 4:
            lines.append('    … 另有 %d 个' % (len(items) - 4))
    if not any(d.values()):
        lines += ['', '未发现任何可用数据：请先「数据导入」或在右键菜单关联原始资料目录。']
    return _text_lines(lines)


# ---------------------------------------------------------------- 数据清洗

def clean_csv(csv_path: str, out_dir: str, well: str) -> dict:
    """对解释曲线集做保守清洗，写 ``<well>_cleaned.csv`` + 报告。"""
    if not csv_path or not os.path.isfile(csv_path):
        return {'ok': False, 'error': '未找到可清洗的曲线集：%s' % csv_path}
    os.makedirs(out_dir, exist_ok=True)
    try:
        from logsys import clean as _clean
        df = _read_csv(csv_path)
        cleaned, report = _clean.clean_well(df, context=well)
        report['source'] = csv_path
        report['well'] = well
        report['time'] = datetime.now().isoformat(timespec='seconds')
        data_path = os.path.join(out_dir, '%s_cleaned.csv' % well)
        rep_path = os.path.join(out_dir, '%s_data_clean_report.json' % well)
        cleaned.to_csv(data_path, index=False, encoding='utf-8')
        with open(rep_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return {'ok': bool(report.get('ok')), 'data': data_path, 'report': rep_path,
                'rows_in': report.get('rows_in', 0), 'rows_out': report.get('rows_out', 0),
                'detail': report}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


# ---------------------------------------------------------------- 数据质检

def qc_csv(csv_path: str, out_dir: str, well: str) -> dict:
    """按 SY/T 5132 的常识口径做单井曲线质检（只读源文件，写报告）。"""
    if not csv_path or not os.path.isfile(csv_path):
        return {'ok': False, 'error': '未找到可质检的曲线集：%s' % csv_path}
    try:
        import numpy as np
        df = _read_csv(csv_path)
        dep = _depth_col(df)
        checks = []
        if not dep:
            checks.append({'item': '深度列', 'level': 'error', 'detail': '缺 DEPTH/MD 列'})
        else:
            d = np.asarray(df[dep].astype(float), dtype=float)
            finite = np.isfinite(d)
            bad = int((~finite).sum())
            dup = int(len(d) - len(np.unique(d[finite])))
            mono = bool(np.all(np.diff(d[finite]) >= 0))
            r = d[finite]
            checks.append({'item': '深度有效值', 'level': 'error' if bad else 'ok',
                           'detail': '非法深度 %d 点' % bad})
            checks.append({'item': '深度重复', 'level': 'warn' if dup else 'ok',
                           'detail': '重复深度 %d 点' % dup})
            checks.append({'item': '深度递增', 'level': 'warn' if not mono else 'ok',
                           'detail': '单调递增' if mono else '存在乱序'})
            if len(r) > 1:
                step = np.diff(np.sort(r))
                irregular = int((step <= 0).sum() + (step > 3 * np.median(step[step > 0])).sum())
                checks.append({'item': '采样间隔', 'level': 'warn' if irregular else 'ok',
                               'detail': '间隔 %.4f m，异常 %d 处' % (float(np.median(step[step > 0])), irregular)})
        present = [c for c in CURVE_HINTS if c in df.columns]
        checks.append({'item': '关键曲线', 'level': 'ok' if len(present) >= 5 else 'warn',
                       'detail': '检出 %d/%d：%s' % (len(present), len(CURVE_HINTS),
                                                   ', '.join(present) or '无')})
        ranges = {'RHOB': (1.5, 3.2), 'NPHI': (-0.05, 1.05), 'GR': (0, 350),
                  'DT': (30, 250), 'CAL': (3, 40)}
        for col, (lo, hi) in ranges.items():
            cc = next((c for c in df.columns if str(c).upper() == col), None)
            if cc is None:
                continue
            v = df[cc].astype(float)
            v = v[np.isfinite(v)]
            if len(v) == 0:
                checks.append({'item': col, 'level': 'error', 'detail': '全为缺测'})
                continue
            out_n = int(((v < lo) | (v > hi)).sum())
            med = float(v.median())
            # 中子若显然是百分数（中位 20~60），按百分数口径检查，不误报
            if col == 'NPHI' and med > 1.5:
                lo, hi = -5, 105
                out_n = int(((v < lo) | (v > hi)).sum())
            checks.append({'item': '%s 值域' % col,
                           'level': 'warn' if out_n / len(v) > 0.02 else 'ok',
                           'detail': '中位 %.3f，越界 %d/%d（%.1f%%，合理区间 %s~%s）'
                                     % (med, out_n, len(v), 100.0 * out_n / len(v), lo, hi)})
        nulls = [(c, int(df[c].isna().sum())) for c in df.columns]
        worst = sorted([x for x in nulls if x[1] > 0], key=lambda x: -x[1])[:6]
        checks.append({'item': '缺测统计', 'level': 'warn' if worst else 'ok',
                       'detail': ('；'.join('%s %d' % x for x in worst) if worst else '无缺测')})
        n_err = sum(1 for c in checks if c['level'] == 'error')
        n_warn = sum(1 for c in checks if c['level'] == 'warn')
        report = {'well': well, 'source': csv_path, 'rows': int(len(df)),
                  'columns': int(len(df.columns)), 'checks': checks,
                  'errors': n_err, 'warnings': n_warn,
                  'level': 'error' if n_err else ('warn' if n_warn else 'ok'),
                  'time': datetime.now().isoformat(timespec='seconds')}
        os.makedirs(out_dir, exist_ok=True)
        rep_path = os.path.join(out_dir, '%s_qc_report.json' % well)
        with open(rep_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return {'ok': True, 'report': rep_path, 'detail': report}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


# ---------------------------------------------------------------- 数据导入

def import_files(files: list[str], dest_dir: str, overwrite: bool = False) -> dict:
    """把外部数据文件**复制**到井的原始资料目录（不移动、不删除源文件）。"""
    if not files:
        return {'ok': False, 'error': '未选择文件'}
    if not dest_dir:
        return {'ok': False, 'error': '未指定目标井的原始资料目录'}
    try:
        os.makedirs(dest_dir, exist_ok=True)
        copied, skipped = [], []
        for src in files:
            src = os.path.abspath(str(src))
            dst = os.path.join(dest_dir, os.path.basename(src))
            if os.path.abspath(dst) == src:
                skipped.append('%s（已在目标目录）' % os.path.basename(src))
                continue
            if os.path.exists(dst) and not overwrite:
                skipped.append('%s（同名已存在，取消勾选覆盖才会替换）' % os.path.basename(src))
                continue
            shutil.copy2(src, dst)
            copied.append(dst)
        return {'ok': bool(copied), 'copied': copied, 'skipped': skipped}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


# ---------------------------------------------------------------- 数据导出

def _las_header(data, well: str, cols: list[str]) -> list[str]:
    """最小 LAS 2.0 头（仅导出选中的曲线，避免依赖 lasio）。"""
    start = float(data.iloc[0, 0]) if len(data) else 0.0
    step = 0.1524
    try:
        import numpy as np
        d = np.asarray(data.iloc[:, 0], dtype=float)
        d = d[np.isfinite(d)]
        if len(d) > 1:
            step = float(np.median(np.diff(np.sort(d)))) or step
    except Exception:
        pass
    head = ['~VERSION INFORMATION',
            ' VERS.      2.0:   CWLS LOG ASCII STANDARD - VERSION 2.0',
            ' WRAP.      NO:   ONE LINE PER DEPTH STEP',
            '~WELL INFORMATION BLOCK',
            ' WLL . %-40s:   WELL NAME' % well.replace(' ', '_'),
            ' STRT.M %.5f:   START DEPTH' % start,
            ' STOP.M %.5f:   STOP DEPTH' % (start + step * max(0, len(data) - 1)),
            ' STEP.M %.5f:   STEP' % step,
            ' NULL.  -999.25:   NULL VALUE',
            '~CURVE INFORMATION BLOCK']
    for i, c in enumerate(cols, 1):
        head.append(' %-10s.           :   %s' % (c.replace(' ', '_')[:10], c))
    head += ['~PARAMETER INFORMATION', '~OTHER', '~A  DEPTH']
    return head


def export_curves(csv_path: str, out_dir: str, well: str, fmt: str = 'csv',
                  columns: list[str] | None = None) -> dict:
    """把曲线集导出为 CSV / XLSX / LAS（写到 out_dir，不覆盖源文件）。"""
    if not csv_path or not os.path.isfile(csv_path):
        return {'ok': False, 'error': '未找到可导出的曲线集：%s' % csv_path}
    try:
        import pandas as pd
        df = _read_csv(csv_path)
        cols = [c for c in (columns or []) if c in df.columns]
        if not cols:
            cols = list(df.columns)
        data = df[cols].copy()
        os.makedirs(out_dir, exist_ok=True)
        ext = fmt.lower()
        if ext == 'xlsx':
            path = os.path.join(out_dir, '%s_export.xlsx' % well)
            data.to_excel(path, index=False)
        elif ext == 'las':
            path = os.path.join(out_dir, '%s_export.las' % well)
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(_las_header(data, well, cols)) + '\n')
                for row in data.itertuples(index=False, name=None):
                    f.write(' '.join('-999.25' if pd.isna(v) else
                                     (v if isinstance(v, str) else '%.5f' % v)
                                     for v in row) + '\n')
        else:
            path = os.path.join(out_dir, '%s_export.csv' % well)
            data.to_csv(path, index=False, encoding='utf-8')
        return {'ok': True, 'file': path, 'columns': cols, 'rows': int(len(data))}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


def columns_of(csv_path: str) -> list[str]:
    if not csv_path or not os.path.isfile(csv_path):
        return []
    try:
        return list(_read_csv(csv_path).columns)
    except Exception:
        return []
