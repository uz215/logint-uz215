# -*- coding: utf-8 -*-
"""变量字典库自检（R87）：族 / 分支变量 / 图例 / 绘图方式 / 持久化 CRUD。

运行：
    python -m logsys.test_variable_catalog

测试全程使用临时库文件，不改动仓库里的 logsys/variable_catalog.json。
"""
import os
import shutil
import sys
import tempfile

from . import variable_catalog as vc
from . import project_model as pm

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


def _use_temp_catalog(tmp):
    """把变量库切到临时文件，避免污染仓库里的正式库。"""
    vc.CATALOG_PATH = os.path.join(tmp, 'variable_catalog.json')
    vc._CACHE = None
    vc._CACHE_MTIME = -1.0
    vc.get_catalog(refresh=True)


def test_defaults():
    print('\n== 默认库结构 ==')
    cat = vc.get_catalog()
    check('15 个族', len(cat['groups']) == 15, len(cat['groups']))
    check('91 个分支变量（R89 增三作业产物变量）', len(cat['variables']) == 91, len(cat['variables']))
    check('3 个图例', len(cat['legends']) == 3, len(cat['legends']))
    check('9 条前缀规则', len(cat['prefix_rules']) == 9, len(cat['prefix_rules']))
    names = vc.all_group_names()
    for g in ('深度族', '电阻率族', '岩性族', '解释结论族', '矿物/组分族',
              '气测族', '核磁族', '电成像族', '未分类'):
        check('族「%s」存在' % g, g in names, names)
    check('族按 order 排序', vc.groups()[0]['id'] == 'DEPTH', vc.groups()[0])


def test_classify():
    print('\n== 族 / 分支 / 单位 / 绘图方式分类 ==')
    cases = [
        ('MD', '深度族', '测量深度', 'm', 'linear', '', 'ok'),
        ('GR', '放射性族', '自然伽马', 'API', 'linear', '', 'ok'),
        ('RT', '电阻率族', '电阻率', 'ohm.m', 'log', '', 'ok'),
        ('LITHOLOGY', '岩性族', '岩性', None, 'qualitative', 'LITHOLOGY', 'warn'),
        ('INTERPRETATION', '解释结论族', '解释结论', None, 'qualitative',
         'INTERPRETATION', 'warn'),
        ('VOL_CALCITE', '矿物/组分族', '方解石含量', 'v/v', 'linear', '', 'ok'),
        ('T2LM', '核磁族', 'T2 几何均值', 'ms', 'log', '', 'ok'),
    ]
    for col, group, family, unit, scale, legend, color in cases:
        i = vc.classify(col)
        check('%-16s 族=%s' % (col, group), i['group'] == group, i['group'])
        check('%-16s 分支=%s' % (col, family), i['family'] == family, i['family'])
        check('%-16s 单位/刻度/图例/色' % col,
              i['unit'] == unit and i['scale'] == scale
              and i['legend_id'] == legend and i['color'] == color, i)

    i = vc.classify('LITHOLOGY')
    check('岩性族 draw_mode=qualitative', i['draw_mode'] == 'qualitative', i['draw_mode'])
    i = vc.classify('INTERPRETATION')
    check('解释结论族 draw_mode=qualitative', i['draw_mode'] == 'qualitative', i['draw_mode'])
    i = vc.classify('RT')
    check('电阻率族 draw_mode=log', i['draw_mode'] == 'log', i['draw_mode'])
    check('变量级刻度覆盖族默认（LITH_MC_CONF）',
          vc.classify('LITH_MC_CONF')['scale'] == 'linear'
          and vc.classify('LITH_MC_CONF')['draw_mode'] == 'linear')

    # 前缀规则
    i = vc.classify('VOL_SOMETHING')
    check('VOL_* 前缀 → 矿物含量', i['group'] == '矿物/组分族'
          and i['family'] == '矿物含量' and i['unit'] == 'v/v', i)
    i = vc.classify('LITHOLOGY_EXTRA')
    check('LITHOLOGY* 前缀 → 岩性解释', i['family'] == '岩性解释'
          and i['scale'] == 'qualitative' and i['legend_id'] == 'LITHOLOGY', i)
    check('长前缀优先（CORE_LITH_EXTRA）',
          vc.classify('CORE_LITH_EXTRA')['family'] == '岩心岩性',
          vc.classify('CORE_LITH_EXTRA')['family'])

    # 别名 / 大小写 / 未登记 / 内部列
    check('小写 gr 与 GR 同族', vc.classify('gr')['group'] == '放射性族')
    check('别名 RHOB → 密度', vc.classify('RHOB')['family'] == '密度')
    check('别名 FLUID_FINAL → 解释结论族',
          vc.classify('FLUID_FINAL')['group'] == '解释结论族')
    u = vc.classify('ZZZ_UNKNOWN_CURVE')
    check('未登记列 → 未分类/红色', u['group'] == '未分类'
          and u['color'] == 'error' and not u['family'], u)
    check('内部质量列 → internal', vc.classify('_POROSITY_VALID')['kind'] == 'internal')

    # 与 project_model 口径一致
    check('pm.classify_variable 委托变量库',
          pm.classify_variable('GR')['group'] == '放射性族'
          and pm.classify_variable('GR')['family'] == '自然伽马')


def test_legends():
    print('\n== 图例（岩性 / 解释结论按族调用） ==')
    lith = vc.legend_codes('LITHOLOGY')
    interp = vc.legend_codes('INTERPRETATION')
    check('岩性图例含砂岩（英文代码）', 'SANDSTONE' in lith, list(lith)[:6])
    check('岩性图例含中文代码「砂岩」', '砂岩' in lith)
    check('中英代码同色', lith['SANDSTONE'][1] == lith['砂岩'][1])
    check('解释结论图例含油/气/水/干层',
          all(k in interp for k in ('OIL', 'GAS', 'WATER', 'DRY')), list(interp)[:8])
    check('油层绿色', interp['OIL'][1] == '#1a9850', interp['OIL'])
    check('legend_for 岩性族 → LITHOLOGY',
          vc.legend_for('LITHOLOGY') == 'LITHOLOGY')
    check('legend_for 解释结论族 → INTERPRETATION',
          vc.legend_for('INTERPRETATION') == 'INTERPRETATION')
    check('legend_for 数值曲线 → 空', vc.legend_for('GR') == '')
    check('draw_mode_of 岩性族', vc.draw_mode_of('LITHOLOGY') == 'qualitative')
    check('group_of 电阻率族', vc.group_of('RT') == '电阻率族')


def test_crud():
    print('\n== 增删改（族名 / 单位 / 绘图方式 / 图例） ==')
    # 改族名 + 改单位
    check('改单位成功', vc.upsert_variable({
        'key': 'GR', 'name': '自然伽马', 'group_id': 'RAD',
        'unit': 'GAPI', 'scale': 'linear'}))
    check('改单位即时生效', vc.classify('GR')['unit'] == 'GAPI')
    check('改族名成功', vc.upsert_group({
        'id': 'RAD', 'name': '自然伽马族', 'draw_mode': 'linear',
        'unit_default': 'API', 'order': 2}))
    check('改族名即时生效', vc.classify('GR')['group'] == '自然伽马族')

    # 新增族 + 新增变量
    check('新增族成功', vc.upsert_group({
        'id': 'SPECIAL', 'name': '特殊测井族', 'draw_mode': 'image',
        'unit_default': '', 'order': 20}))
    check('新增变量成功', vc.upsert_variable({
        'key': 'MY_NEW_CURVE', 'name': '我的新曲线', 'group_id': 'SPECIAL',
        'unit': 'count', 'scale': 'linear'}))
    i = vc.classify('MY_NEW_CURVE')
    check('新变量归属新族 / 绘图方式', i['group'] == '特殊测井族'
          and i['draw_mode'] == 'linear' and i['unit'] == 'count', i)

    # 新增图例与代码
    check('新增图例成功', vc.upsert_legend({
        'id': 'MYLEGEND', 'name': '自定义图例',
        'codes': [['AAA|甲', '甲类', '#112233'], ['BBB|乙', '乙类', '#445566']]}))
    codes = vc.legend_codes('MYLEGEND')
    check('自定义图例别名可用', 'AAA' in codes and '甲' in codes and 'BBB' in codes, codes)
    check('自定义图例颜色正确', codes['甲'][1] == '#112233', codes['甲'])

    # 前缀规则
    check('新增前缀规则成功', vc.upsert_prefix_rule({
        'prefix': 'MYPFX_', 'name': '自定义前缀', 'group_id': 'SPECIAL',
        'unit': 'count', 'scale': 'linear'}))
    check('前缀规则生效', vc.classify('MYPFX_X')['group'] == '特殊测井族')
    check('删除前缀规则成功', vc.delete_prefix_rule('MYPFX_'))
    check('删除前缀规则生效', vc.classify('MYPFX_X')['group'] == '未分类')

    # 删除族：其下变量改挂未分类
    check('删除族成功', vc.delete_group('SPECIAL'))
    check('删族后变量改挂未分类',
          vc.classify('MY_NEW_CURVE')['group'] == '未分类')
    check('删除变量成功', vc.delete_variable('MY_NEW_CURVE'))
    check('删除变量生效', vc.classify('MY_NEW_CURVE')['color'] == 'error')

    # 整库导入 / 恢复默认
    snap = vc.as_dict()
    check('整库导入成功', vc.import_dict(snap))
    check('恢复默认成功', len(vc.reset_defaults()['groups']) == 15)
    check('恢复默认后 GR 单位回 API', vc.classify('GR')['unit'] == 'API')
    check('恢复默认后族名回放射性族', vc.classify('GR')['group'] == '放射性族')


def test_persistence():
    print('\n== 持久化与自动重载 ==')
    check('库文件已落盘', os.path.isfile(vc.CATALOG_PATH))
    before = vc.classify('GR')['unit']
    check('保存成功', vc.upsert_variable({
        'key': 'GR', 'name': '自然伽马', 'group_id': 'RAD',
        'unit': 'GAPI2', 'scale': 'linear'}))
    vc._CACHE = None                     # 模拟新进程/外部改动
    check('重读磁盘拿到最新值', vc.get_catalog(refresh=True)
          and vc.classify('GR')['unit'] == 'GAPI2', vc.classify('GR')['unit'])
    check('改动前值不同', before != 'GAPI2')
    vc.reset_defaults()

    # 外部直接改文件 → mtime 变化自动重载
    import json
    with open(vc.CATALOG_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for g in data['groups']:
        if g['id'] == 'RES':
            g['name'] = '电阻率族（外部改名）'
    with open(vc.CATALOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.utime(vc.CATALOG_PATH, (os.path.getmtime(vc.CATALOG_PATH) + 2,
                               os.path.getmtime(vc.CATALOG_PATH) + 2))
    check('外部改文件自动重载', vc.classify('RT')['group'] == '电阻率族（外部改名）',
          vc.classify('RT')['group'])
    vc.reset_defaults()


def test_model_grouping():
    print('\n== 模型层按族分组 / 变量归属 ==')
    vs = [pm.variable_from_info(pm.classify_variable(c))
          for c in ('GR', 'RT', 'LLD', 'LITHOLOGY', 'VOL_CALCITE',
                    'INTERPRETATION', 'ZZZ_UNKNOWN')]
    groups = pm.group_variables(vs)
    names = [g for g, _ in groups]
    check('按族分组出多组', len(groups) >= 5, names)
    check('未分类排最后', names[-1] == '未分类', names)
    check('电阻率族含 RT/LLD',
          any(g == '电阻率族' and sorted(v.name for v in items) == ['LLD', 'RT']
              for g, items in groups), names)
    check('岩性族含 LITHOLOGY',
          any(g == '岩性族' and 'LITHOLOGY' in [v.name for v in items]
              for g, items in groups))
    check('解释结论族带图例',
          any(v.legend_id == 'INTERPRETATION' for g, items in groups
              for v in items if g == '解释结论族'))
    check('变量带 origin/source_file 字段',
          all(hasattr(v, 'origin') and hasattr(v, 'source_file') for v in vs))


def main():
    print('=' * 68)
    print('  变量字典库自检（R87）')
    print('=' * 68)
    tmp = tempfile.mkdtemp(prefix='vcatalog_')
    orig = vc.CATALOG_PATH
    try:
        _use_temp_catalog(tmp)
        test_defaults()
        test_classify()
        test_legends()
        test_crud()
        test_persistence()
        test_model_grouping()
    finally:
        vc.CATALOG_PATH = orig
        vc._CACHE = None
        vc._CACHE_MTIME = -1.0
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项:')
        for f in FAIL:
            print('  -', f)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
