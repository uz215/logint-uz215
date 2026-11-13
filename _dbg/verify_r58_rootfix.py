# -*- coding: utf-8 -*-
"""R58 根因修复验证：剖面预判是否真的进入识别器 + 三口井回归。

验证项：
1. 直接测 run_workflow 第13950行的 Profile 预判块能否执行（不再被
   UnboundLocalError 吞掉）——用最小复现：准备带套管 mask 的 data，
   调用 detect_well_profile_type / pti_profile_type 并打印。
2. 三口井（1-SPS-108 / XIMENIA-5 / 3-SPS-111D）岩性分布回归。
"""
import os
import sys
import logging

logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import logInt
from logInt import (LithologyRecognizer, standardize_curve_names,
                    sanitize_null_markers, reconcile_vsh_with_gr,
                    detect_well_profile_type, pti_profile_type)
from logint.dlis_tool import DlisTool


def load_dlis_pipeline(fp, well_name):
    """复刻 load_data 的 DLIS 分支 + 后处理顺序。"""
    raw, _info = DlisTool().load_dlis(fp)
    df = raw.copy()
    df.columns = [str(c).upper() for c in df.columns]
    df = standardize_curve_names(df, os.path.basename(fp))
    df = sanitize_null_markers(df)
    df = reconcile_vsh_with_gr(df)
    for cand in ('MD', 'DEPTH', 'DEPT'):
        if cand in df.columns:
            if cand != 'MD':
                df = df.rename(columns={cand: 'MD'})
            break
    df['MD'] = pd.to_numeric(df['MD'], errors='coerce')
    df = df.dropna(subset=['MD']).sort_values('MD').reset_index(drop=True)
    return df


def load_las_pipeline(fp):
    import lasio
    las = lasio.read(fp)
    df = las.df().reset_index()
    df.columns = [str(c).upper() for c in df.columns]
    df = standardize_curve_names(df, os.path.basename(fp))
    df = sanitize_null_markers(df)
    df = reconcile_vsh_with_gr(df)
    for cand in ('MD', 'DEPTH', 'DEPT'):
        if cand in df.columns:
            if cand != 'MD':
                df = df.rename(columns={cand: 'MD'})
            break
    df['MD'] = pd.to_numeric(df['MD'], errors='coerce')
    df = df.dropna(subset=['MD']).sort_values('MD').reset_index(drop=True)
    return df


def run_well(tag, df, well_name):
    print("\n" + "=" * 74)
    print("%s  (%s)  rows=%d cols=%d" % (tag, well_name, len(df), len(df.columns)))
    print("=" * 74)

    # --- 1. 剖面预判（对应 run_workflow 第13948-13983行同款逻辑） ---
    try:
        import numpy as _np
        _cm_v = _np.zeros(len(df), dtype=bool)   # 无套管场景
        _d2 = df.loc[~_cm_v].copy()
        _ptype, _pinfo = detect_well_profile_type(_d2, well_name)
        _pti_t, _pti_v, _pti_d = pti_profile_type(_d2, well_name)
        if _pti_t:
            _pinfo['pti'] = {'value': round(_pti_v, 3), 'type': _pti_t,
                             'detail': _pti_d}
            _ptype = _pti_t
        profile = _ptype
        print("剖面预判: %s   PTI=%.3f  %s" % (profile, _pti_v, _pti_d))
    except Exception as e:
        profile = 'mixed'
        print("剖面预判失败(!): %r" % (e,))

    # --- 2. PE / 中子质量 ---
    pe_reliable = True
    try:
        from logint.mineral_analysis import MineralAnalyzer  # 可能不存在
        pe_reliable = True
    except Exception:
        pass
    # 用生产同款 check_pe_quality（挂在 logInt 内或 MineralAnalyzer）
    try:
        _fn = getattr(logInt, 'check_pe_quality', None)
        if _fn is not None:
            q = _fn(df, well_name)
            pe_reliable = bool((q or {}).get('pe_reliable', True))
            print("PE质量: reliable=%s  reason=%s"
                  % (pe_reliable, (q or {}).get('reason', '')[:70]))
    except Exception as e:
        print("PE质量检查跳过: %r" % (e,))

    # --- 3. 识别 ---
    rec = LithologyRecognizer(df, depth_unit='m', pe_reliable=pe_reliable,
                              profile_type=profile, neutron_reliable=True)
    rec.recognize()
    lith = pd.Series(np.asarray(rec.lith).ravel())
    vc = lith.value_counts(dropna=False)
    for k, v in vc.items():
        print("   %-18s %7d (%5.1f%%)" % (str(k), v, 100.0 * v / len(lith)))
    return profile, lith


def main():
    wells = [
        ("SPS-108", "F:/360/data/uploads/1-SPS-108_all.dlis", 'dlis', "1-SPS-108"),
        ("RASHIDPUR_13", "data/RASHIDPUR_13_SP-CAL-HAL7506-SNGR_MAIN.las", 'las', "RASHIDPUR_13"),
        ("3-SPS-111D", "data/uploads/3-sps-111d_lqc.las", 'las', "3-SPS-111D"),
    ]
    for tag, fp, kind, wn in wells:
        if not os.path.exists(fp):
            print("\n[跳过] %s 文件不存在: %s" % (tag, fp))
            continue
        try:
            df = (load_dlis_pipeline(fp, wn) if kind == 'dlis'
                  else load_las_pipeline(fp))
            run_well(tag, df, wn)
        except Exception as e:
            import traceback
            print("\n[%s] 失败: %r" % (tag, e))
            traceback.print_exc(limit=3)


if __name__ == '__main__':
    main()
