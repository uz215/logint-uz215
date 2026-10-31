# -*- coding: utf-8 -*-
"""岩性 ML 接入主流程：若该井有岩性标定模型（lithcal fit 产物），应用后用 ML 岩性。

- 模型：data/calibration/lith_models/<井>.joblib（lithcal fit 生成）
- 应用：全井预测 + 11 点深度多数票平滑 → LITHOLOGY_ML；同时把 LITHOLOGY 替换为 ML
  （保留原值到 LITHOLOGY_RULE 便于追溯），使层表/出图使用标定后的岩性。
- 无模型/异常 → 跳过，不中断主流程（零静默失败）。
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
MODEL_DIR = os.path.join(r'D:\360\src', 'data', 'calibration', 'lith_models')


def _smooth(pred: np.ndarray, win: int = 11) -> np.ndarray:
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


def apply_lith_ml(processed_data: pd.DataFrame, well_name: str,
                  output_dir: str | None = None, replace_rules: bool = True) -> dict:
    try:
        mp = os.path.join(MODEL_DIR, str(well_name) + '.joblib')
        if not os.path.exists(mp):
            return {'available': False, 'model_path': mp}
        import joblib
        pack = joblib.load(mp)
        clf, feats, med = pack['model'], pack['features'], pack['medians']
        # 【2026-10-31 修复】滚动特征需由 lithcal._features 生成，不能直接取原列
        from .lithcal import _features as _lith_features
        _Xall, _ = _lith_features(processed_data)
        _miss = [c for c in feats if c not in _Xall.columns]
        if _miss:
            raise KeyError('缺少模型特征: %s' % _miss[:8])
        X = _Xall[feats].apply(pd.to_numeric, errors='coerce') \
            .fillna(pd.Series(med)).values
        pred = _smooth(np.asarray(clf.predict(X), dtype=object), win=11)
        try:
            from .region_lith import constrain, region_of_well
            _reg = region_of_well(well_name)
            if _reg:
                pred = constrain(pred, _reg)
        except Exception:
            pass
        out = processed_data
        out['LITHOLOGY_ML'] = pred
        # 【2026-10-31】有元素测井矿物反演（VOL_CALCITE 等覆盖>50%）时，矿物岩性更可靠：
        # 只输出 LITHOLOGY_ML，不替换 LITHOLOGY（保留矿物真岩性）
        _min_cols = [c for c in ('VOL_CALCITE', 'VOL_DOLOM', 'VOL_ANHY',
                                 'VOL_BASALT', 'VOL_SALT', 'VOL_ILLITE')
                     if c in out.columns]
        _has_mineral = False
        if _min_cols:
            try:
                _cov = float(out[_min_cols].notna().any(axis=1).mean())
                _has_mineral = _cov > 0.50
            except Exception:
                _has_mineral = False
        if replace_rules and not _has_mineral:
            if 'LITHOLOGY' in out.columns:
                out['LITHOLOGY_RULE'] = out['LITHOLOGY']
            out['LITHOLOGY'] = pred
        dist = pd.Series(pred).value_counts().to_dict()
        logger.info('岩性ML: 已应用 %s（点=%d，分布=%s）', mp, len(out), dist)
        return {'available': True, 'model_path': mp, 'points': int(len(out)),
                'dist': {str(k): int(v) for k, v in dist.items()}}
    except Exception as e:
        logger.warning('岩性ML应用失败（忽略，保留规则岩性）: %s: %s', type(e).__name__, e)
        return {'available': False, 'error': '%s: %s' % (type(e).__name__, e)}
