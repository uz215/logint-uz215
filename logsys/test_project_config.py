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


def main():
    print('=' * 66)
    print('  项目配置与作业执行器自检')
    print('=' * 66)
    test_config_io()
    test_detect()
    test_resolve_priority()
    test_job_command()
    test_job_discovery()
    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项:')
        for f in FAIL:
            print('  -', f)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
