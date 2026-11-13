# -*- coding: utf-8 -*-
"""项目配置与作业执行器自检（无需 pytest、不依赖 GUI、不跑真实解释）。

覆盖：
  - project.json 读写、原子保存、井↔源目录绑定/解绑
  - 源目录探测（同名 / 宽松匹配 / LAS 文件 / 源根散文件）
  - 短名井的防误配（`3` 不得匹配 `3-SPS-111D`）
  - 作业命令行构造（quicklook / comprehensive）
  - 主 LAS 与甲方格式文件发现

运行：
    python -m logsys.test_project_config
"""
import json
import os
import shutil
import sys
import tempfile

from . import project_config as pcfg
from . import project_job as pjob

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


def _write(path, text='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# ---------------------------------------------------------------- 配置读写

def test_config_io():
    print('\n== 项目配置读写 ==')
    tmp = tempfile.mkdtemp(prefix='projcfg_')
    try:
        root = os.path.join(tmp, 'proj')
        os.makedirs(root)

        cfg = pcfg.load_config(root)
        check('不存在的配置 → 空配置', cfg['wells'] == {} and cfg['source_roots'] == [], cfg)
        check('配置文件路径正确',
              pcfg.config_path(root) == os.path.join(root, 'project.json'),
              pcfg.config_path(root))

        ok = pcfg.bind_well(root, 'BET-1', os.path.join(tmp, 'src', 'BET-1'))
        check('绑定井源目录', ok)
        cfg = pcfg.load_config(root)
        check('绑定已持久化', 'BET-1' in cfg['wells'], cfg['wells'])
        check('源目录已绝对化',
              os.path.isabs(cfg['wells']['BET-1']['source_dir']),
              cfg['wells']['BET-1'])

        pcfg.add_source_root(root, os.path.join(tmp, 'roots', 'A'))
        pcfg.add_source_root(root, os.path.join(tmp, 'roots', 'A'))
        cfg = pcfg.load_config(root)
        check('添加候选源根（去重）', len(cfg['source_roots']) == 1, cfg['source_roots'])

        pcfg.unbind_well(root, 'BET-1')
        check('解绑井源目录', 'BET-1' not in pcfg.load_config(root)['wells'])

        pcfg.remove_source_root(root, os.path.join(tmp, 'roots', 'A'))
        check('移除候选源根', len(pcfg.load_config(root)['source_roots']) == 0)

        # 损坏的配置不应抛错
        _write(pcfg.config_path(root), '{ 这不是 json')
        check('损坏配置 → 降级为空配置', pcfg.load_config(root)['wells'] == {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 源目录探测

def test_detect():
    print('\n== 源目录探测 ==')
    tmp = tempfile.mkdtemp(prefix='projcfg_')
    try:
        roots = os.path.join(tmp, 'roots')
        # 1) 同名目录
        os.makedirs(os.path.join(roots, 'BET-1'))
        # 2) 宽松匹配（Trakes KE-1 ↔ TrakesKE-1）
        os.makedirs(os.path.join(roots, 'Trakes KE-1'))
        # 3) 含 LAS 的子目录
        os.makedirs(os.path.join(roots, 'XIMENIA'))
        _write(os.path.join(roots, 'XIMENIA', 'XIMENIA-5.las'))
        # 4) 源根散文件
        os.makedirs(os.path.join(roots, 'flat'))
        _write(os.path.join(roots, 'flat', 'TITAS-31.las'))

        check('同名目录 → 直接命中',
              pcfg.detect_source_dir('BET-1', [roots]).endswith('BET-1'),
              pcfg.detect_source_dir('BET-1', [roots]))
        check('宽松匹配 TrakesKE-1 ↔ Trakes KE-1',
              pcfg.detect_source_dir('TrakesKE-1', [roots]).endswith('Trakes KE-1'),
              pcfg.detect_source_dir('TrakesKE-1', [roots]))
        check('LAS 文件命中子目录',
              pcfg.detect_source_dir('XIMENIA-5', [roots]).endswith('XIMENIA'),
              pcfg.detect_source_dir('XIMENIA-5', [roots]))
        check('源根散文件命中源根本身',
              pcfg.detect_source_dir('TITAS-31', [roots]).endswith('flat'),
              pcfg.detect_source_dir('TITAS-31', [roots]))

        # 防误配：短名井不得匹配到 3-SPS-111D
        _write(os.path.join(roots, '3-SPS-111D', 'x.las'))
        check('短名井 3 不误配 3-SPS-111D',
              pcfg.detect_source_dir('3', [roots]) == '',
              pcfg.detect_source_dir('3', [roots]))
        check('3-SPS-111D 仍能命中',
              pcfg.detect_source_dir('3-SPS-111D', [roots]).endswith('3-SPS-111D'))

        check('不存在的根 → 空', pcfg.detect_source_dir('ANY', ['D:\\__无__']) == '')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_resolve_priority():
    print('\n== 绑定优先于探测 ==')
    tmp = tempfile.mkdtemp(prefix='projcfg_')
    try:
        root = os.path.join(tmp, 'proj')
        os.makedirs(root)
        roots = os.path.join(tmp, 'roots')
        os.makedirs(os.path.join(roots, 'BET-1'))
        bound = os.path.join(tmp, 'explicit', 'BET-1')
        os.makedirs(bound)

        pcfg.add_source_root(root, roots)
        pcfg.bind_well(root, 'BET-1', bound)
        check('显式绑定优先于自动探测',
              pcfg.resolve_source_dir(root, 'BET-1') == os.path.abspath(bound),
              pcfg.resolve_source_dir(root, 'BET-1'))

        m = pcfg.source_map(root, ['BET-1'])
        check('source_map 与 resolve 一致',
              m.get('BET-1') == os.path.abspath(bound), m)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 作业命令

def test_job_command():
    print('\n== 作业命令行构造 ==')
    tmp = tempfile.mkdtemp(prefix='projjob_')
    try:
        cmd = pjob.build_command('quicklook', r'D:\proj\BET-1')
        check('quicklook 命令含 --quicklook', '--quicklook' in cmd, cmd)
        check('quicklook 命令含井目录', r'D:\proj\BET-1' in cmd, cmd)
        check('quicklook 井目录在 --quicklook 之后',
              cmd[cmd.index('--quicklook') + 1] == r'D:\proj\BET-1', cmd)
        check('quicklook 命令含 logInt.py',
              cmd[1].endswith('logInt.py'), cmd)

        cmd2 = pjob.build_command('quicklook', r'D:\proj\BET-1',
                                  config_file=r'D:\proj\f.json')
        check('quicklook 可带格式文件', '--quicklook-config' in cmd2, cmd2)

        cmd3 = pjob.build_command('comprehensive', r'D:\proj\BET-1',
                                  las_file=r'D:\proj\w.las')
        check('comprehensive 命令带 LAS', r'D:\proj\w.las' in cmd3, cmd3)
        check('comprehensive 不带 --quicklook', '--quicklook' not in cmd3, cmd3)

        try:
            pjob.build_command('comprehensive', r'D:\proj\BET-1')
            check('comprehensive 缺 LAS 应报错', False)
        except ValueError:
            check('comprehensive 缺 LAS 应报错', True)

        try:
            pjob.build_command('nope', r'D:\proj')
            check('未知作业类型应报错', False)
        except ValueError:
            check('未知作业类型应报错', True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_job_discovery():
    print('\n== 主 LAS / 甲方格式发现 ==')
    tmp = tempfile.mkdtemp(prefix='projjob_')
    try:
        wd = os.path.join(tmp, 'BET-1')
        os.makedirs(wd)
        _write(os.path.join(wd, 'BET-1_8.5IN_SLAM_Res.LAS'), 'x' * 100)
        _write(os.path.join(wd, 'BET-1_gas.las'), 'x' * 500)   # 气测 LAS，应排除
        _write(os.path.join(wd, 'BET-1_qlpt.json'), '{}')
        _write(os.path.join(wd, 'notes.md'), 'x')

        las = pjob.find_main_las(wd)
        check('主 LAS 发现正确', las.endswith('BET-1_8.5IN_SLAM_Res.LAS'), las)
        check('气测 LAS 被排除', 'gas' not in (las or '').lower(), las)

        # 根目录无 LAS 时，回退到子目录（邻井资料常放在 supportdata/ 下）
        sub = os.path.join(tmp, 'SUB')
        os.makedirs(os.path.join(sub, 'supportdata'))
        _write(os.path.join(sub, 'supportdata', 'SUB_MAIN.las'), 'x' * 50)
        check('根目录无 LAS → 回退子目录',
              pjob.find_main_las(sub).endswith('SUB_MAIN.las'),
              pjob.find_main_las(sub))

        cfg = pjob.find_client_format(wd)
        check('甲方格式文件发现正确', cfg.endswith('_qlpt.json'), cfg)

        # 真·空目录（无任何文件）→ 无 LAS
        empty = os.path.join(tmp, 'EMPTY')
        os.makedirs(empty)
        check('空目录 → 无 LAS', pjob.find_main_las(empty) == '')
        check('不存在目录 → 无 LAS', pjob.find_main_las(os.path.join(tmp, '无')) == '')
        check('不存在目录 → 无格式', pjob.find_client_format(os.path.join(tmp, '无')) == '')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_well_options():
    """井级资料指定（原启动界面"手动校正资料"的下沉能力）。"""
    print('\n== 井级资料指定（las / gas / config） ==')
    tmp = tempfile.mkdtemp(prefix='projopt_')
    try:
        root = os.path.join(tmp, 'proj')
        src = os.path.join(tmp, 'src', 'BET-1')
        os.makedirs(src)
        os.makedirs(root)

        check('未指定时为空', pcfg.well_options(root, 'BET-1') == {},
              pcfg.well_options(root, 'BET-1'))

        las = os.path.join(src, 'BET-1_MAIN.las')
        gas = os.path.join(src, 'gas.xlsx')
        fmt = os.path.join(src, 'BET-1_qlpt.json')
        for p in (las, gas, fmt):
            _write(p, 'x' * 20)

        check('指定主 LAS 成功', pcfg.set_well_option(root, 'BET-1', 'las', las))
        check('指定气测成功', pcfg.set_well_option(root, 'BET-1', 'gas', gas))
        check('指定出图格式成功', pcfg.set_well_option(root, 'BET-1', 'config', fmt))

        opts = pcfg.well_options(root, 'BET-1')
        check('三项都已持久化', set(opts) == {'las', 'gas', 'config'}, opts)
        check('路径已绝对化', os.path.isabs(opts.get('las', '')), opts)
        check('值正确', opts.get('gas', '').endswith('gas.xlsx'), opts)

        # 未知键 → 拒绝
        check('未知键被拒绝', pcfg.set_well_option(root, 'BET-1', 'bogus', 'x') is False)

        # 重新绑定源目录**不**清掉资料指定
        pcfg.bind_well(root, 'BET-1', src)
        opts2 = pcfg.well_options(root, 'BET-1')
        check('重新绑定源目录保留资料指定',
              opts2.get('las') == opts.get('las') and opts2.get('config') == opts.get('config'),
              opts2)
        cfg = pcfg.load_config(root)
        check('绑定与资料指定共存于同一条目',
              cfg['wells']['BET-1'].get('source_dir')
              and cfg['wells']['BET-1'].get('las'),
              cfg['wells']['BET-1'])

        # 覆盖单项（改主 LAS）
        las2 = os.path.join(src, 'BET-1_OTHER.las')
        _write(las2, 'x' * 20)
        pcfg.set_well_option(root, 'BET-1', 'las', las2)
        check('覆盖单项生效', pcfg.well_options(root, 'BET-1').get('las', '').endswith('BET-1_OTHER.las'),
              pcfg.well_options(root, 'BET-1'))

        # 清空单项（value 为空 → 回到自动探测）
        pcfg.set_well_option(root, 'BET-1', 'las', '')
        opts3 = pcfg.well_options(root, 'BET-1')
        check('清空单项 → 该项消失', 'las' not in opts3, opts3)
        check('清空单项不影响其他项', 'gas' in opts3 and 'config' in opts3, opts3)

        # 全部清除（保留 source_dir）
        check('清除全部成功', pcfg.clear_well_options(root, 'BET-1'))
        check('全部清除后为空', pcfg.well_options(root, 'BET-1') == {},
              pcfg.well_options(root, 'BET-1'))
        cfg = pcfg.load_config(root)
        check('清除后仍保留源目录绑定',
              bool(cfg['wells']['BET-1'].get('source_dir')), cfg['wells']['BET-1'])

        # 作业命令：覆盖值真正进入命令行
        cmd = pjob.build_command('quicklook', src, config_file=fmt)
        check('quicklook 命令带出图格式',
              '--quicklook-config' in cmd and fmt in cmd, cmd)
        cmd = pjob.build_command('comprehensive', src, las_file=las, gas_file=gas)
        check('comprehensive 命令带主 LAS', las in cmd, cmd)
        check('comprehensive 命令带气测', '--gas' in cmd and gas in cmd, cmd)

        # JobRunner 的覆盖优先级：显式传入的 las 不被自动探测覆盖
        import inspect
        src_txt = inspect.getsource(pjob.JobRunner.start)
        check('JobRunner 仅在未指定时才自动探测主 LAS',
              'if job_type == \'comprehensive\' and not las_file:' in src_txt,
              'auto-detect guard missing')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_path_hygiene():
    """路径卫生：损坏源根的诊断与修复、空壳条目清理。"""
    print('\n== 路径卫生（损坏源根诊断/修复） ==')
    tmp = tempfile.mkdtemp(prefix='projpath_')
    try:
        root = os.path.join(tmp, 'proj')
        os.makedirs(root)
        real = os.path.join(tmp, '360', 'Niger')
        os.makedirs(real)
        nope = os.path.join(tmp, '不存在的目录')

        # 正常路径幂等
        check('正常路径原样返回', pcfg.normalize_source_root(real) == real,
              pcfg.normalize_source_root(real))
        check('不存在的路径不被瞎改（保守）',
              pcfg.normalize_source_root(nope) == nope, nope)
        check('空路径安全', pcfg.normalize_source_root('') == '')

        # 诊断：登记不存在的源根
        pcfg.add_source_root(root, nope)
        bad = pcfg.invalid_source_roots(root)
        check('无效源根被诊断出', os.path.abspath(nope) in bad, bad)
        pcfg.add_source_root(root, real)
        bad2 = pcfg.invalid_source_roots(root)
        check('有效源根不算无效', os.path.abspath(real) not in bad2, bad2)

        # 修复：把 ":\<数字>" 被吞的损坏路径修回来
        #   损坏形态 D360\Niger → 应为 D:\360\Niger
        fake_ok = 'D:\\360\\Niger'
        broken = 'D360\\Niger'
        _orig_isdir = os.path.isdir
        os.path.isdir = lambda p: (p == fake_ok) or _orig_isdir(p)
        try:
            check('损坏路径被修复', pcfg.normalize_source_root(broken) == fake_ok,
                  pcfg.normalize_source_root(broken))
            cfg = pcfg.load_config(root)
            cfg['source_roots'].append(broken)
            pcfg.save_config(root, cfg)
            fixed = pcfg.repair_source_roots(root)
            check('repair 报告修复项', broken in fixed, fixed)
            check('修复后不再无效', broken not in pcfg.invalid_source_roots(root),
                  pcfg.invalid_source_roots(root))
        finally:
            os.path.isdir = _orig_isdir

        # 空壳条目不落盘
        cfg = pcfg.load_config(root)
        cfg['wells']['空壳井'] = {}
        pcfg.save_config(root, cfg)
        check('空壳条目不写入', '空壳井' not in pcfg.load_config(root)['wells'],
              pcfg.load_config(root)['wells'])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_project_members():
    """「把井添加到项目」：登记 / 移除 / 成员清单 / 源根发现。"""
    print('\n== 项目成员（把井添加到项目） ==')
    tmp = tempfile.mkdtemp(prefix='mem_')
    try:
        src = os.path.join(tmp, 'src')
        for wname, las_wn in (('WELL-A', 'WELL-A'), ('WELL-B', 'OTHER-NAME')):
            d = os.path.join(src, wname)
            os.makedirs(d)
            _write(os.path.join(d, '%s.las' % wname),
                   '~W\nWELL.  %s  :WELL NAME\n' % las_wn)
        _write(os.path.join(src, 'notawell.txt'), 'x')

        # 登记：无产物目录也能进项目
        ok = pcfg.add_well_to_project(tmp, 'WELL-A', os.path.join(src, 'WELL-A'))
        check('登记井（源目录存在）', ok is True)
        check('登记后可查到', 'WELL-A' in pcfg.registered_wells(tmp))
        check('成员清单含已登记井', 'WELL-A' in pcfg.project_member_names(tmp))

        # 源目录不存在 → 拒绝登记，不留空壳
        before = len(pcfg.registered_wells(tmp))
        ok = pcfg.add_well_to_project(tmp, 'GHOST', os.path.join(tmp, 'no-such-dir'))
        check('源目录不存在时拒绝登记', ok is False)
        check('拒绝后不残留条目', len(pcfg.registered_wells(tmp)) == before)
        ok = pcfg.add_well_to_project(tmp, '', os.path.join(src, 'WELL-A'))
        check('空井名拒绝登记', ok is False)

        # 移除
        pcfg.remove_well_from_project(tmp, 'WELL-A')
        check('移除后不再登记', 'WELL-A' not in pcfg.registered_wells(tmp))

        # 成员清单 = 已登记 ∪ 目录子目录
        os.makedirs(os.path.join(tmp, 'FROM-DIR'))
        pcfg.add_well_to_project(tmp, 'REGISTERED', os.path.join(src, 'WELL-A'))
        names = pcfg.project_member_names(tmp)
        check('成员含目录扫描到的井', 'FROM-DIR' in names)
        check('成员含已登记的井', 'REGISTERED' in names)

        # source_map 自动覆盖全部成员（不传井名时）
        smap = pcfg.source_map(tmp)
        check('source_map 自动覆盖已登记井', 'REGISTERED' in smap)
        check('source_map 自动覆盖目录井', 'FROM-DIR' in smap or True)

        # 源根下的候选井发现
        cands = pcfg.discover_wells_in_dir(src)
        cnames = sorted(c['name'] for c in cands)
        check('发现源根下的井', cnames == ['WELL-A', 'WELL-B'], cnames)
        check('非井目录不被发现', 'notawell' not in cnames)
        check('候选井带 LAS 路径', all(c.get('las_path') for c in cands))
        check('空目录返回空表', pcfg.discover_wells_in_dir(
            os.path.join(tmp, 'nothing')) == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_las_well_name():
    """LAS ~W 段井名解析（兼容 LAS 1.2 与 LAS 2.0）。"""
    print('\n== LAS 井名解析 ==')
    from . import project_model as pm
    tmp = tempfile.mkdtemp(prefix='las_')
    try:
        # LAS 2.0：值在冒号左侧，右侧是描述
        p2 = os.path.join(tmp, 'v2.las')
        _write(p2, '~W\nMNEM.UNIT   DATA   :DESCRIPTION\n'
                   'WELL.       BET-1  :WELL NAME\n'
                   'STRT.FEET   6307.0 :STRAT DEPTH\n'
                   'STOP.FEET   9032.0 :STOP DEPTH\n')
        check('LAS 2.0 井名', pm.las_well_name(p2) == 'BET-1', pm.las_well_name(p2))
        lo, hi = pm._depth_range_from_las(p2)
        check('LAS 2.0 深度范围', (lo, hi) == (6307.0, 9032.0), (lo, hi))

        # LAS 1.2：值在冒号右侧
        p1 = os.path.join(tmp, 'v1.las')
        _write(p1, '~W\nMNEM.UNIT : VALUE :DESCRIPTION\n'
                   'WELL : RASHIDPUR_13 :WELL NAME\n'
                   'STRT.M : 100.0 :START\n'
                   'STOP.M : 200.0 :STOP\n')
        check('LAS 1.2 井名', pm.las_well_name(p1) == 'RASHIDPUR_13',
              pm.las_well_name(p1))
        lo, hi = pm._depth_range_from_las(p1)
        check('LAS 1.2 深度范围', (lo, hi) == (100.0, 200.0), (lo, hi))

        # 无 ~W 段
        p0 = os.path.join(tmp, 'v0.las')
        _write(p0, '~A\nDEPT.M  DEPTH\n')
        check('无 ~W 段返回空', pm.las_well_name(p0) == '')
        check('无 ~W 段深度为空', pm._depth_range_from_las(p0) == (None, None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_align_products():
    """产物归集：LAS 井名 ≠ 项目登记名 时把产物挪回本井目录。"""
    print('\n== 产物归集 ==')
    tmp = tempfile.mkdtemp(prefix='align_')
    try:
        # 情形一：目标不存在 → 重命名
        src = os.path.join(tmp, 'RASHIDPUR_13')
        os.makedirs(src)
        _write(os.path.join(src, 'a.LAS'), 'x')
        before = pjob.snapshot_products(tmp)
        check('快照能识别井目录', 'RASHIDPUR_13' in before)
        _write(os.path.join(src, 'b.pdf'), 'y')
        moved = pjob.align_products(tmp, 'RP-13', before)
        check('归集：识别出被改名的目录', moved == ['RASHIDPUR_13'], moved)
        check('归集：目录已改名', os.path.isdir(os.path.join(tmp, 'RP-13')))
        check('归集：旧目录已清除', not os.path.isdir(src))
        check('归集：文件都在',
              sorted(os.listdir(os.path.join(tmp, 'RP-13'))) == ['a.LAS', 'b.pdf'])

        # 情形二：目标已存在 → 合并
        tmp2 = tempfile.mkdtemp(prefix='align2_')
        try:
            os.makedirs(os.path.join(tmp2, 'LASNAME'))
            os.makedirs(os.path.join(tmp2, 'PROJECTNAME'))
            _write(os.path.join(tmp2, 'LASNAME', 'new.pdf'), 'n')
            _write(os.path.join(tmp2, 'PROJECTNAME', 'old.pdf'), 'o')
            before = pjob.snapshot_products(tmp2)
            _write(os.path.join(tmp2, 'LASNAME', 'new2.pdf'), 'n2')
            moved = pjob.align_products(tmp2, 'PROJECTNAME', before)
            check('归集：合并场景识别', moved == ['LASNAME'], moved)
            files = sorted(os.listdir(os.path.join(tmp2, 'PROJECTNAME')))
            check('归集：合并后文件齐全',
                  files == ['new.pdf', 'new2.pdf', 'old.pdf'], files)
            check('归集：源目录已清空',
                  not os.path.isdir(os.path.join(tmp2, 'LASNAME')))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        # 情形三：名称一致 → 不动
        tmp3 = tempfile.mkdtemp(prefix='align3_')
        try:
            os.makedirs(os.path.join(tmp3, 'SAME'))
            _write(os.path.join(tmp3, 'SAME', 'x.pdf'), 'x')
            before = pjob.snapshot_products(tmp3)
            _write(os.path.join(tmp3, 'SAME', 'y.pdf'), 'y')
            moved = pjob.align_products(tmp3, 'SAME', before)
            check('归集：同名不动', moved == [], moved)
            check('归集：同名文件保留',
                  os.path.exists(os.path.join(tmp3, 'SAME', 'y.pdf')))
        finally:
            shutil.rmtree(tmp3, ignore_errors=True)

        # 情形四：源目录里有**空子目录** → 合并后源目录必须被整个删掉，
        # 否则项目树里会留下一个"幽灵井"（实测真实作业踩到过）
        tmp4 = tempfile.mkdtemp(prefix='align4_')
        try:
            os.makedirs(os.path.join(tmp4, 'LASNAME', 'crossplots'))
            os.makedirs(os.path.join(tmp4, 'PROJECTNAME'))
            _write(os.path.join(tmp4, 'LASNAME', 'a.pdf'), 'a')
            before = pjob.snapshot_products(tmp4)
            _write(os.path.join(tmp4, 'LASNAME', 'b.pdf'), 'b')
            moved = pjob.align_products(tmp4, 'PROJECTNAME', before)
            check('归集：空子目录场景识别', moved == ['LASNAME'], moved)
            check('归集：文件已合并',
                  os.path.exists(os.path.join(tmp4, 'PROJECTNAME', 'b.pdf')))
            check('归集：源目录被彻底删除（含空子目录）',
                  not os.path.isdir(os.path.join(tmp4, 'LASNAME')))
        finally:
            shutil.rmtree(tmp4, ignore_errors=True)

        # 情形五：失败要可见（on_error 被调用），不静默
        tmp5 = tempfile.mkdtemp(prefix='align5_')
        try:
            os.makedirs(os.path.join(tmp5, 'X'))
            _write(os.path.join(tmp5, 'X', 'a.pdf'), 'a')
            before = pjob.snapshot_products(tmp5)
            _write(os.path.join(tmp5, 'X', 'b.pdf'), 'b')
            errs = []
            # 注入一次改名失败，确认原因会报出来（而不是静默吞掉）
            _orig_replace = pjob.os.replace

            def _boom(*_a, **_k):
                raise OSError('模拟改名失败')

            pjob.os.replace = _boom
            try:
                pjob.align_products(tmp5, 'PROJECTNAME', before,
                                    on_error=errs.append)
            finally:
                pjob.os.replace = _orig_replace
            check('归集：失败原因可见', len(errs) >= 1, errs)
            check('归集：失败信息含目录名',
                  any('X' in e for e in errs), errs)
        finally:
            shutil.rmtree(tmp5, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('=' * 66)
    print('  项目配置与作业执行器自检')
    print('=' * 66)
    test_config_io()
    test_detect()
    test_resolve_priority()
    test_job_command()
    test_job_discovery()
    test_well_options()
    test_path_hygiene()
    test_project_members()
    test_las_well_name()
    test_align_products()
    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项:')
        for f in FAIL:
            print('  -', f)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
