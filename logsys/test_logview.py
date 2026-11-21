# -*- coding: utf-8 -*-
"""交互绘图（logvis）自检（无需 pytest、不依赖 GUI、不跑真实解释）。

覆盖：
  - 道布局解析（模板 track.layout 优先、内置兜底、enabled/width 规则）
  - **兜底布局与 logvis 现状逐一对齐**（改了布局解析器不能改坏静态出图）
  - 模板 track.layout 与代码兜底等价（模板与代码不分叉）
  - 道/曲线数据类序列化往返
  - 包络降采样（保留尖峰）与深度窗口切片
  - 井数据装配（产物定位、曲线表/层段表/井信息）
  - 曲线目录（三色分类、族分组、按族取默认曲线）
  - 图头字段展平与分组写回（临时目录）

运行：
    python -m logsys.test_logview
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

from . import project_model as pm
# 【R81】交互绘图已合并进根目录 logvis.py，统一从 logvis 导入
import logvis as lv
ct = ds = hd = ts = lv
from logvis import (decimate_for_pixels, depth_window_slice, envelope_decimate)

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


# ---------------------------------------------------------------- 布局解析

#: logvis.py 两处布局构造的**实测值**（改动 logvis 时须同步更新本表）
LOGVIS_QLPT = [('LITHO', 1.2), ('RES_TRAD', 1.4), ('RES_ARRAY', 1.4), ('POR', 1.0),
               ('DEPTH', 0.30), ('SW', 0.6), ('POR2', 0.6), ('CALIB', 0.9),
               ('GAS', 'gas'), ('PROFILE', 1.0), ('INTERP', 0.42)]
LOGVIS_CMPT = [('LITHO', 1.0), ('RES_TRAD', 1.4), ('RES_ARRAY', 1.4), ('POR', 1.25),
               ('DEPTH', 0.5), ('SWPOR', 1.0), ('GAS', 'gas'), ('LITHO_FILL', 1.0),
               ('FACIES', 1.0), ('PROFILE', 1.0), ('INTERP', 1.0)]

FLAGS_ALL = {'has_res_trad': True, 'has_res_array': True, 'has_gas': True}
FLAGS_MIN = {'has_res_trad': False, 'has_res_array': False, 'has_gas': False}


def test_layout_fallback_matches_logvis():
    print('\n== 兜底布局与 logvis 实测值对齐 ==')
    for kind, expect in (('qlpt', LOGVIS_QLPT), ('cmpt', LOGVIS_CMPT)):
        got, from_tpl = ts.resolve_track_layout(None, kind, FLAGS_ALL, 1.6)
        want = [(t, (1.6 if w == 'gas' else w)) for t, w in expect]
        check(f'{kind} 兜底布局 == logvis 实测值', got == want,
              f'\n    got :{got}\n    want:{want}')
        check(f'{kind} 兜底时 from_template=False', from_tpl is False)


def test_layout_conditions():
    print('\n== enabled / 条件道 ==')
    got, _ = ts.resolve_track_layout(None, 'qlpt', FLAGS_MIN, 1.0)
    ids = [t for t, _ in got]
    check('无电阻率/无气测时不含 RES_TRAD/RES_ARRAY/GAS',
          'RES_TRAD' not in ids and 'RES_ARRAY' not in ids and 'GAS' not in ids, ids)
    check('无气测时气测道被剔除且不占宽度', 'GAS' not in ids, ids)
    got2, _ = ts.resolve_track_layout(None, 'qlpt', FLAGS_ALL, 1.0)
    check('有气测时气测道出现且宽度取实算值',
          ('GAS', 1.0) in got2, got2)


def test_layout_from_template():
    print('\n== 模板 track.layout 解析 ==')
    tpl = {'track': {'layout': [
        {'id': 'LITHO', 'name': '岩性道', 'width': 1.2, 'enabled': True},
        {'id': 'GAS', 'name': '气测道', 'width': 'gas', 'enabled': 'auto'},
        {'id': 'POR2', 'name': '孔隙度2', 'width': 0.6, 'enabled': False},
        {'id': 'INTERP', 'name': '解释', 'width': 0.42, 'enabled': 'auto'},
    ]}}
    got, from_tpl = ts.resolve_track_layout(tpl, 'qlpt', FLAGS_ALL, 1.25)
    check('来源标记为模板', from_tpl is True)
    check('enabled=false 的道被剔除', 'POR2' not in [t for t, _ in got], got)
    check('width="gas" 被替换为实算宽度', ('GAS', 1.25) in got, got)
    check('模板道序保持', [t for t, _ in got] == ['LITHO', 'GAS', 'INTERP'], got)
    # 模板全禁用 → 回落兜底
    tpl2 = {'track': {'layout': [{'id': 'LITHO', 'width': 1.0, 'enabled': False}]}}
    got2, from_tpl2 = ts.resolve_track_layout(tpl2, 'qlpt', FLAGS_ALL, 1.0)
    check('模板全禁用时回落兜底且 from_template=False',
          from_tpl2 is False and len(got2) > 1, got2)


def test_template_layout_equivalence():
    print('\n== 模板 track.layout 与代码兜底等价 ==')
    """模板与代码必须给出同一套道序与道宽，否则静态出图与交互画布会分叉。"""
    for kind, expect in (('qlpt', LOGVIS_QLPT), ('cmpt', LOGVIS_CMPT)):
        path = os.path.join('templates', f'{kind}.json')
        if not os.path.exists(path):
            check(f'{kind} 模板存在', False, path)
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                tpl = json.load(f)
        except Exception as e:
            check(f'{kind} 模板可解析', False, e)
            continue
        got, from_tpl = ts.resolve_track_layout(tpl, kind, FLAGS_ALL, 1.6)
        want = [(t, (1.6 if w == 'gas' else w)) for t, w in expect]
        check(f'{kind} 模板 layout 存在且来源为模板', from_tpl is True)
        check(f'{kind} 模板 layout == 代码兜底', got == want,
              f'\n    模板:{got}\n    兜底:{want}')


# ---------------------------------------------------------------- 数据类

def test_dataclass_roundtrip():
    print('\n== 道/曲线数据类往返 ==')
    t = ts.TrackSpec(id='X', name='测试道', kind='curve', width=1.5,
                     curves=[ts.CurveSpec(column='GR', label='伽马', scale='log')])
    d = t.to_dict()
    t2 = ts.TrackSpec.from_dict(d)
    check('TrackSpec 往返一致', t2.id == t.id and t2.name == t.name
          and t2.width == t.width and len(t2.curves) == 1
          and t2.curves[0].column == 'GR' and t2.curves[0].scale == 'log')
    check('tracks_to_dicts/from_dicts 往返一致',
          ts.tracks_from_dicts(ts.tracks_to_dicts([t]))[0].id == 'X')


def test_build_tracks_family_default():
    print('\n== 按族挑默认曲线 ==')
    cols = ['MD', 'RT', 'AT10', 'AT20', 'POR', 'PHI', 'Sw', 'LITHOLOGY', 'C1TG']
    fam = {c: pm.classify_variable(c)['family'] or '' for c in cols}
    tracks = ts.build_tracks(None, 'qlpt', FLAGS_ALL, 1.0,
                             available_columns=cols, column_family=fam)
    by_id = {t.id: t for t in tracks}
    check('电阻率道取到 RT', [c.column for c in by_id['RES_TRAD'].curves] == ['RT'],
          by_id['RES_TRAD'].curves)
    check('电阻率道曲线为对数刻度',
          by_id['RES_TRAD'].curves[0].scale == 'log')
    check('孔隙度道按族取到 POR/PHI',
          [c.column for c in by_id['POR'].curves] == ['POR', 'PHI'],
          by_id['POR'].curves)
    check('含水饱和度道取到 Sw',
          [c.column for c in by_id['SW'].curves] == ['Sw'], by_id['SW'].curves)
    check('气测道按列名子串取到 C1TG',
          [c.column for c in by_id['GAS'].curves] == ['C1TG'], by_id['GAS'].curves)


# ---------------------------------------------------------------- 降采样

def test_decimate():
    print('\n== 包络降采样 ==')
    v = np.sin(np.linspace(0, 20, 1000))
    v[500] = 999.0                      # 尖峰
    out, idx = envelope_decimate(v, 50)
    check('抽稀后点数显著减少', out.size < 200, out.size)
    check('尖峰被保留', np.isclose(out.max(), 999.0), out.max())
    check('索引单调递增', bool(np.all(np.diff(idx) >= 0)))
    out2, idx2 = envelope_decimate(v, 0)
    check('n_bins<=0 时原样返回', out2.size == v.size and idx2.size == v.size)
    d = np.array([0., 1., 2., 3., 4.])
    m = depth_window_slice(d, 1, 3)
    check('深度窗口切片正确', list(m) == [False, True, True, True, False], list(m))
    vals, dvals, _ = decimate_for_pixels(v, d, 0, 4, 100)
    check('decimate_for_pixels 返回深度单调', bool(np.all(np.diff(dvals) >= 0)))


# ---------------------------------------------------------------- 数据装配

def test_datasource():
    print('\n== 井数据装配 ==')
    tmp = tempfile.mkdtemp(prefix='logview_')
    try:
        with open(os.path.join(tmp, 'X_processed.csv'), 'w', encoding='utf-8') as f:
            f.write('MD,GR,RT\n100,10,0.5\n101,12,0.6\n102,11,0.7\n')
        with open(os.path.join(tmp, 'X_interpretation_layers.csv'), 'w', encoding='utf-8') as f:
            f.write('LAYER_ID,TOP_MD,BASE_MD\n1,100,102\n')
        with open(os.path.join(tmp, 'Xinfo.json'), 'w', encoding='utf-8') as f:
            json.dump({'井信息': {'well_name': 'X', 'company': 'ACME'},
                       '图表标题': {'ql_title': '快速图'}}, f, ensure_ascii=False)
        wd = ds.load_well_data('X', out_dir=tmp)
        check('曲线表已装配', wd.has_data and len(wd.depth) == 3, wd.note)
        check('深度列正确', list(wd.depth) == [100.0, 101.0, 102.0])
        check('层段表已装配', wd.layers is not None and len(wd.layers) == 1)
        check('井信息已装配', wd.info.get('井信息', {}).get('company') == 'ACME')
        check('产物定位正确',
              os.path.basename(ds.find_processed_csv(tmp, 'X')) == 'X_processed.csv')
        check('井信息定位正确',
              os.path.basename(ds.find_info_json(tmp, 'X')) == 'Xinfo.json')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_catalog():
    print('\n== 曲线目录 ==')
    tmp = tempfile.mkdtemp(prefix='logview_cat_')
    try:
        with open(os.path.join(tmp, 'X_processed.csv'), 'w', encoding='utf-8') as f:
            f.write('MD,GR,RT,LITHOLOGY,_POROSITY_VALID,FOO\n'
                    '100,10,0.5,shale,1,3\n101,12,0.6,sand,1,4\n')
        wd = ds.load_well_data('X', out_dir=tmp)
        items = ct.build_catalog(wd)
        names = [i.column for i in items]
        check('深度列不入目录', 'MD' not in names, names)
        check('内部列不入目录', '_POROSITY_VALID' not in names, names)
        check('GR 在目录中且族正确',
              any(i.column == 'GR' and i.family == '自然伽马' for i in items), names)
        check('RT 在目录中且单位为 ohm.m',
              any(i.column == 'RT' and i.unit == 'ohm.m' for i in items), names)
        check('定性列（岩性）标记为定性',
              any(i.column == 'LITHOLOGY' and i.kind == 'qualitative' for i in items))
        groups = ct.catalog_groups(items)
        check('按族分组且有未分类组',
              any(g == '未分类' for g, _ in groups), [g for g, _ in groups])
        check('按族取色稳定', ct.suggest_curve_color(items, 'RT') ==
              ct.suggest_curve_color(items, 'RT'))
        check('电阻率族建议对数刻度', ct.suggest_scale(items, 'RT') == 'log')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_header():
    print('\n== 图头字段 ==')
    tmp = tempfile.mkdtemp(prefix='logview_hdr_')
    try:
        path = os.path.join(tmp, 'Xinfo.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'井信息': {'well_name': 'X', '_说明': '不参与编辑'},
                       '日期': {'log_date': '2026-01-01'}}, f, ensure_ascii=False)
        info = ds._read_json(path)
        fields = hd.load_header_fields(info)
        keys = {(f.section, f.key) for f in fields}
        check('说明键被排除', ('井信息', '_说明') not in keys, keys)
        check('字段带中文标签',
              any(f.key == 'well_name' and f.label == '井名' for f in fields))
        flat = hd.flatten_info(info)
        check('扁平取值正确', flat.get('well_name') == 'X' and flat.get('log_date') == '2026-01-01')
        check('写回保持分组结构',
              hd.save_header_field(path, '井信息', 'company', 'NEWCO') is True)
        data = ds._read_json(path)
        check('写回后分组结构不变',
              '日期' in data and data['井信息']['company'] == 'NEWCO'
              and data['井信息']['well_name'] == 'X', data)
        check('写回不影响其他字段',
              data['日期']['log_date'] == '2026-01-01')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_layout_fallback_matches_logvis()
    test_layout_conditions()
    test_layout_from_template()
    test_template_layout_equivalence()
    test_dataclass_roundtrip()
    test_build_tracks_family_default()
    test_decimate()
    test_datasource()
    test_catalog()
    test_header()
    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项:')
        for f in FAIL:
            print('  -', f)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
