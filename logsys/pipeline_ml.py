# -*- coding: utf-8 -*-
"""流水线 ML 流体结论接入：主流程解释完成后，若该井有标定模型，自动产出 ML 层表。

设计（零静默失败 / 可回退）：
- 模型目录默认 D:\\360\\src\\data\\calibration\\models，可用环境变量 LOGSYS_MODEL_DIR 覆盖；
- 无模型 → 直接跳过（返回 {'available': False}），主流程不受影响；
- 任何异常 → 记录 warning，返回 {'error': ...}，不中断主流程；
- 产出：<井>_interpretation_layers_ML.csv（与规则层表并列，不覆盖原表）。
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = os.path.join(r'D:\360\src', 'data', 'calibration', 'models')


def model_dir() -> str:
    return os.environ.get('LOGSYS_MODEL_DIR', DEFAULT_MODEL_DIR)


def _feature_frame(d: pd.DataFrame, feats: list) -> pd.DataFrame:
    def num(*names):
        for n in names:
            if n in d.columns:
                s = pd.to_numeric(d[n], errors='coerce')
                if s.notna().sum() > 0:
                    return s
        return pd.Series(np.nan, index=d.index)

    sw_log = num('SW')
    sw_log = sw_log.where(sw_log <= 1.5, sw_log / 100.0)
    frame = pd.DataFrame({
        'GR': num('GR', 'GR_NOU', 'CGR'),
        'PHI': num('PHI', 'POR'),
        'SW_COMP': num('Sw'),
        'SW_LOG': sw_log,
        'RT': num('RT', 'RD', 'LLD'),
        'VSH': num('VSH', 'VSHALE'),
        'LOG_RT': np.log10(num('RT', 'RD', 'LLD').clip(lower=1e-3)),
        'TG': num('TG'),
        'PLATE_FLUID': d['PLATE_FLUID'].astype(str).str.upper() if 'PLATE_FLUID' in d.columns else '',
    })
    frame['LOG_TG'] = np.log10(frame['TG'].clip(lower=1.0))
    frame['PLATE_NUM'] = frame['PLATE_FLUID'].map({'GAS': 2.0, 'OIL': 1.0, 'DRY': 0.0})
    return frame[feats]


def _smooth(pred: np.ndarray, win: int = 5) -> np.ndarray:
    if win <= 1 or len(pred) < win:
        return pred
    classes = sorted(set(pred))
    idx = {c: i for i, c in enumerate(classes)}
    code = np.array([idx[p] for p in pred], dtype=int)
    out = code.copy()
    half = win // 2
    for i in range(len(code)):
        seg = code[max(0, i - half): min(len(code), i + half + 1)]
        vals, cnt = np.unique(seg, return_counts=True)
        out[i] = vals[np.argmax(cnt)]
    return np.array([classes[i] for i in out], dtype=object)


CLASS_TO_LAYER = {'GAS': 'GAS', 'GAS_OIL': 'GAS_OIL', 'OIL': 'OIL',
                  'WATER': 'WATER', 'TIGHT': 'NonReservoir'}


def apply_ml_fluid(processed_data: pd.DataFrame, well_name: str, output_dir: str,
                   unit: str = 'm') -> dict:
    """对成果数据应用标定模型，产出 ML 层表。返回状态 dict（永不抛异常）。"""
    try:
        model_path = os.path.join(model_dir(), str(well_name) + '.joblib')
        if not os.path.exists(model_path):
            logger.info('ML 流体: 无标定模型（%s），跳过', model_path)
            return {'available': False, 'model_path': model_path}
        import joblib
        pack = joblib.load(model_path)
        model = pack['model']
        feats = pack.get('features') or []
        medians = pack.get('medians') or {}

        d = processed_data
        if 'MD' not in d.columns:
            return {'available': False, 'error': 'processed data 无 MD 列'}
        X = _feature_frame(d, feats).fillna(pd.Series(medians))
        pred = np.asarray(model.predict(X), dtype=object)
        proba = model.predict_proba(X).max(axis=1) if hasattr(model, 'predict_proba') else np.ones(len(X))
        # 与 wellcal 后处理同一口径：图版判 GAS 而模型判 OIL → 油气同层 GAS_OIL（用户 2026-10-31 口径）
        try:
            plate_num = pd.to_numeric(d.get('PLATE_FLUID', pd.Series('', index=d.index))
                                      .astype(str).str.upper().map({'GAS': 2.0, 'OIL': 1.0, 'DRY': 0.0}),
                                      errors='coerce').values
            pred = np.where((pred == 'OIL') & (plate_num == 2.0), 'GAS_OIL', pred)
        except Exception:
            pass
        pred = _smooth(np.asarray(pred, dtype=object), win=5)

        # 油气同层必须气上油下：把 ML 的 GAS_OIL 段按气测证据拆成 GAS(上)+OIL(下)
        try:
            from .mixed_split import split_gas_oil
            _tmp = pd.DataFrame({'MD': pd.to_numeric(d['MD'], errors='coerce'),
                                 'INTERPRETATION': pd.Series(pred)})
            if 'PLATE_FLUID' in d.columns:
                _tmp['PLATE_FLUID'] = d['PLATE_FLUID'].astype(str).values
            for _c in ('TG', 'C1'):
                if _c in d.columns:
                    _tmp[_c] = pd.to_numeric(d[_c], errors='coerce').values
            _ms = split_gas_oil(_tmp)
            if _ms.get('splits'):
                pred = _tmp['INTERPRETATION'].astype(object).values
                logger.info('ML 油气同层拆分: %d 段/%d 点', _ms['splits'], _ms['points'])
        except Exception as _mse:
            logger.warning('ML 油气同层拆分失败（忽略）: %s', _mse)

        # 关键特征缺失点不外推
        ph = pd.to_numeric(d.get('PHI', d.get('POR')), errors='coerce')
        sw = pd.to_numeric(d.get('Sw'), errors='coerce')
        valid = (ph.notna() | sw.notna()).values
        pred = np.where(valid, pred, 'UNKNOWN')

        # 层表（与规则层表相同的聚合器）
        from .layers import build_layers
        itp = np.array([CLASS_TO_LAYER.get(p, '') for p in pred], dtype=object)
        lay = build_layers(pd.DataFrame({'MD': pd.to_numeric(d['MD'], errors='coerce'),
                                         'INTERPRETATION': itp}),
                           min_thick=0.4 if unit == 'm' else 1.3,
                           thin_absorb=0.6 if unit == 'm' else 2.0,
                           gap_break=0.5 if unit == 'm' else 1.6)
        os.makedirs(output_dir, exist_ok=True)
        lp = os.path.join(output_dir, str(well_name) + '_interpretation_layers_ML.csv')
        if len(lay):
            lay.to_csv(lp, index=False, encoding='utf-8-sig')
        dist = pd.Series(pred).value_counts().to_dict()
        logger.info('ML 流体: 已产出 %s（层数=%d，分布=%s）', lp, len(lay), dist)
        return {'available': True, 'model_path': model_path, 'layers_path': lp,
                'layers': int(len(lay)), 'dist': {k: int(v) for k, v in dist.items()},
                'conf_mean': round(float(np.mean(proba)), 3)}
    except Exception as e:  # 零静默失败：记录但不中断主流程
        logger.warning('ML 流体接入失败（不影响规则法结果）: %s: %s', type(e).__name__, e)
        return {'available': False, 'error': '%s: %s' % (type(e).__name__, e)}
