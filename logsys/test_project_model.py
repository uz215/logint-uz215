# -*- coding: utf-8 -*-
"""项目-井模型自检（无需 pytest、不依赖 GUI、不写项目目录）。

覆盖：
  - Techlog 变量三色规则（黑/灰/红）
  - 曲线族与单位推断
  - 数据集识别与变量提取
  - 井状态判定（已解释/部分完成/仅建目录/缺原始资料）
  - 过滤 / 分组 / 条件选择
  - 汇总统计

运行：
    python -m logsys.test_project_model
"""
import json
import os
import shutil
import sys
import tempfile

from . import project_model as pm

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


# ---------------------------------------------------------------- 三色规则

def test_variable_colors():
    print('\n== Techlog 变量三色规则 ==')
    # 黑 = 族 + 单位 齐备
    v = pm.classify_variable('GR')
    check('GR → 黑色（族+单位齐备）', v['color'] == 'ok' and v['family'] and v['unit'], v)
    check('GR 族名=自然伽马', v['family'] == '自然伽马', v['family'])
    check('GR 单位=API', v['unit'] == 'API', v['unit'])

    # 灰 = 有族无单位（如解释类 LITHOLOGY）
    v = pm.classify_variable('LITHOLOGY')
    check('LITHOLOGY → 灰色（有族无单位）', v['color'] == 'warn' and v['family'] and not v['unit'], v)

    # 红 = 族与单位皆缺（未知列）
    v = pm.classify_variable('ZZZ_UNKNOWN_CURVE')
    check('未知列 → 红色（族单位皆缺）', v['color'] == 'error' and not v['family'] and not v['unit'], v)

    # 内部列 = 灰点（不作为用户变量）
    v = pm.classify_variable('_POROSITY_VALID')
    check('内部列标记为 internal', v['kind'] == 'internal', v)

    # 深度有族有单位
    v = pm.classify_variable('MD')
    check('MD → 测量深度族 + m', v['family'] == '测量深度' and v['unit'] == 'm', v)

    # 大小写不敏感
    check('小写 gr 与 GR 同族', pm.classify_variable('gr')['family'] == '自然伽马')

    # 电阻率对数刻度
    check('RT 为对数刻度', pm.classify_variable('RT')['scale'] == 'log')


# ---------------------------------------------------------------- 扫描

def _make_fixture(root):
    """构造一个最小项目：2 口井（1 完整 / 1 空目录）。"""
    w1 = os.path.join(root, 'WELL-A')
    os.makedirs(w1)
    with open(os.path.join(w1, 'WELL-A_processed.csv'), 'w', encoding='utf-8') as f:
        f.write('MD,GR,RT,POR,LITHOLOGY,INTERPRETATION,ZZZ_WEIRD\n')
        f.write('100.0,50.0,20.0,0.15,sandstone,OIL,1.0\n')
        f.write('100.5,55.0,25.0,0.18,sandstone,OIL,1.0\n')
        f.write('101.0,60.0,30.0,0.20,shale,WATER,1.0\n')
    with open(os.path.join(w1, 'WELL-A_interpretation_layers.csv'), 'w', encoding='utf-8') as f:
        f.write('LAYER_ID,TOP_MD,BASE_MD,LITHOLOGY,INTERPRETATION\n')
        f.write('1,100.0,101.0,sandstone,OIL\n')
        f.write('2,101.0,101.5,shale,WATER\n')
    with open(os.path.join(w1, 'WELL-Ainfo.json'), 'w', encoding='utf-8') as f:
        json.dump({'井信息': {'well_name': 'WELL-A', 'country': 'Chad', 'field_name': 'Bongor'}},
                  f, ensure_ascii=False)
    w2 = os.path.join(root, 'WELL-B')
    os.makedirs(w2)
    return root


def test_scan():
    print('\n== 项目扫描 ==')
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        root = _make_fixture(tmp)
        p = pm.scan_project(root)
        check('识别 2 口井', len(p.wells) == 2, [w.name for w in p.wells])
        names = sorted(w.name for w in p.wells)
        check('井名正确', names == ['WELL-A', 'WELL-B'], names)

        wa = next(w for w in p.wells if w.name == 'WELL-A')
        check('WELL-A 状态=complete', wa.status == 'complete', wa.status)
        check('WELL-A 识别到曲线数据集', any(d.dtype == 'curve' for d in wa.datasets),
              [d.dtype for d in wa.datasets])
        check('WELL-A 识别到层段表', any(d.dtype == 'table' for d in wa.datasets),
              [d.dtype for d in wa.datasets])
        check('WELL-A 层数=2', wa.layer_count == 2, wa.layer_count)
        check('WELL-A 流体分布 OIL/WATER', wa.fluid_dist.get('OIL') == 1 and
              wa.fluid_dist.get('WATER') == 1, wa.fluid_dist)
        check('WELL-A 深度范围 100-101', wa.depth_min == 100.0 and wa.depth_max == 101.0,
              (wa.depth_min, wa.depth_max))

        cur = next(d for d in wa.datasets if d.dtype == 'curve')
        check('曲线集含 7 个变量', len(cur.variables) == 7, len(cur.variables))
        names_v = [v.name for v in cur.variables]
        check('变量含 MD/GR/LITHOLOGY', 'MD' in names_v and 'GR' in names_v
              and 'LITHOLOGY' in names_v, names_v)
        gr = next(v for v in cur.variables if v.name == 'GR')
        check('GR 变量黑色', gr.color == 'ok', gr)
        weird = next(v for v in cur.variables if v.name == 'ZZZ_WEIRD')
        check('未知变量红色', weird.color == 'error', weird)

        wb = next(w for w in p.wells if w.name == 'WELL-B')
        check('WELL-B 状态=empty', wb.status == 'empty', wb.status)
        check('WELL-B 无数据集', len(wb.datasets) == 0, len(wb.datasets))

        # 井信息读取
        check('读取井信息 country=Chad', wa.info.get('井信息/country') == 'Chad', wa.info)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_status_with_source():
    print('\n== 井状态：产物完成度 × 源关联（两个正交维度） ==')
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        root = os.path.join(tmp, 'proj')
        os.makedirs(os.path.join(root, 'WELL-C'))
        src = os.path.join(tmp, 'src')
        os.makedirs(os.path.join(src, 'WELL-C'))
        p = pm.scan_project(root, src)
        wc = p.wells[0]
        # 【2026-11-11 修正】有源无产物 = "待解释"（可在项目里跑 QuickLook），
        # 原判据与标签相反（曾标为"缺原始资料"）
        check('有源无产物 → pending（待解释）', wc.status == 'pending', wc.status)
        check('pending 标签正确', wc.status_label == '待解释', wc.status_label)
        check('有源 → 源状态=已关联', wc.source_label == '已关联', wc.source_label)
        check('有源 → has_source=True', wc.has_source)

        # 有产物但无源：产物维度独立判定，源维度单独标记为"缺源"
        w2 = os.path.join(root, 'WELL-D')
        os.makedirs(w2)
        with open(os.path.join(w2, 'WELL-D_processed.csv'), 'w', encoding='utf-8') as f:
            f.write('MD,GR\n100.0,50.0\n')
        p2 = pm.scan_project(root, src)
        wd = next(w for w in p2.wells if w.name == 'WELL-D')
        check('有产物无源 → 产物维度=部分完成', wd.status == 'partial', wd.status)
        check('有产物无源 → 源维度=缺源', wd.source_label == '缺源', wd.source_label)
        check('有产物无源 → has_source=False', not wd.has_source)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_source_datasets():
    print('\n== 源数据集（原始资料） ==')
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        root = os.path.join(tmp, 'proj')
        os.makedirs(os.path.join(root, 'WELL-E'))
        src = os.path.join(tmp, 'src', 'WELL-E')
        os.makedirs(src)
        with open(os.path.join(src, 'WELL-E.las'), 'w', encoding='utf-8') as f:
            f.write('~Version Information\n'
                    'VERS.   2.0 : CWLS LOG ASCII STANDARD -VERSION 2.0\n'
                    '~Well Information\n'
                    'STRT.MS : 1000.0\n'
                    'STOP.MS : 1200.0\n'
                    'WELL.   WELL-E : Well\n'
                    '~Curve Information\n'
                    'DEPT.M : Depth\n'
                    'GR.API : Gamma Ray\n'
                    '~ASCII\n'
                    '1000.0 50.0\n'
                    '1000.5 52.0\n')
        with open(os.path.join(src, 'WELL-E_qlpt.json'), 'w', encoding='utf-8') as f:
            json.dump({'legend_items': [{'label': 'OIL', 'color': '#ffd400'}]},
                      f, ensure_ascii=False)
        p = pm.scan_project(root, source_map={'WELL-E': src})
        w = p.wells[0]
        check('源数据集已识别', len(w.source_datasets) >= 2,
              [d.name for d in w.source_datasets])
        src_ds = [d for d in w.source_datasets if d.dtype == 'source']
        check('识别到原始 LAS 数据集', len(src_ds) == 1, [d.name for d in src_ds])
        if src_ds:
            vnames = [v.name for v in src_ds[0].variables]
            check('原始 LAS 变量含 GR', 'GR' in vnames, vnames)
            check('原始 LAS 深度范围 1000-1200',
                  src_ds[0].depth_min == 1000.0 and src_ds[0].depth_max == 1200.0,
                  (src_ds[0].depth_min, src_ds[0].depth_max))
        check('甲方格式识别为 meta 数据集',
              any(d.dtype == 'meta' for d in w.source_datasets),
              [(d.name, d.dtype) for d in w.source_datasets])
        check('井标记 has_source=True', w.has_source)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 过滤/分组/选择

def test_filter_group_select():
    print('\n== 过滤 / 分组 / 条件选择 ==')
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        root = _make_fixture(tmp)
        p = pm.scan_project(root)

        # 过滤：关键字
        f = pm.filter_wells(p, 'WELL-A')
        check('按井名过滤命中 1 口', len(f) == 1 and f[0].name == 'WELL-A', [w.name for w in f])
        f = pm.filter_wells(p, 'zzz-no-match')
        check('无匹配过滤 → 0 口', len(f) == 0, len(f))
        # 按变量名过滤
        f = pm.filter_wells(p, '', variable='LITHOLOGY')
        check('按变量名过滤命中 1 口', len(f) == 1, [w.name for w in f])
        # 按状态过滤
        f = pm.filter_wells(p, '', status='complete')
        check('按状态过滤命中 1 口', len(f) == 1, [w.name for w in f])
        # 按数据集类型过滤
        f = pm.filter_wells(p, '', dataset_type='curve')
        check('按数据集类型过滤命中 1 口', len(f) == 1, [w.name for w in f])

        # 分组
        g = pm.group_wells(p.wells, 'status')
        check('按状态分组出 2 组', len(g) == 2, list(g.keys()))
        g = pm.group_wells(p.wells, 'country')
        check('按国别分组：Chad 1 口 / 未标注 1 口',
              len(g.get('Chad', [])) == 1 and len(g.get('未标注国别', [])) == 1,
              {k: len(v) for k, v in g.items()})

        # 条件选择
        sel = pm.conditional_select(p, family='自然伽马')
        check('条件选择：自然伽马族命中', bool(sel.get('WELL-A')), sel)
        sel = pm.conditional_select(p, unit='ohm.m')
        check('条件选择：单位 ohm.m 命中 RT', bool(sel.get('WELL-A')), sel)
        sel = pm.conditional_select(p, family='不存在族')
        check('条件选择：无匹配 → 空', not sel, sel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_summary():
    print('\n== 汇总统计 ==')
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        root = _make_fixture(tmp)
        p = pm.scan_project(root)
        s = pm.summarize(p)
        check('井数=2', s['wells'] == 2, s['wells'])
        # 7 个曲线变量 + 层段表派生的 2 个流体结论变量 = 9
        check('变量数=9（曲线7 + 层段结论2）', s['variables'] == 9, s['variables'])
        check('层数=2', s['layers'] == 2, s['layers'])
        check('状态分布含 2 项', len(s['by_status']) == 2, s['by_status'])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_robustness():
    print('\n== 健壮性 ==')
    p = pm.scan_project('D:\\__不存在的路径__\\xyz')
    check('不存在路径 → 空项目不抛错', len(p.wells) == 0)
    tmp = tempfile.mkdtemp(prefix='projmodel_')
    try:
        # 井目录里有垃圾文件
        w = os.path.join(tmp, 'JUNK')
        os.makedirs(w)
        with open(os.path.join(w, 'random.txt'), 'w') as f:
            f.write('hello')
        p = pm.scan_project(tmp)
        check('垃圾井目录 → empty 状态', p.wells[0].status == 'empty', p.wells[0].status)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('=' * 66)
    print('  项目-井模型自检')
    print('=' * 66)
    test_variable_colors()
    test_scan()
    test_status_with_source()
    test_source_datasets()
    test_filter_group_select()
    test_summary()
    test_robustness()
    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项:')
        for f in FAIL:
            print('  -', f)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
