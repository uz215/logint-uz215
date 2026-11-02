# -*- coding: utf-8 -*-
"""批量状态报告：汇总验收矩阵、批量回归、运行清单、知识库统计为一份状态报告。

用法：
    python -m logsys.status --out data/status
输出：
    data/status/status_<ts>.json / status_<ts>.md
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'


def _latest(pattern: str) -> str | None:
    fs = glob.glob(pattern)
    return max(fs, key=os.path.getmtime) if fs else None


def collect() -> dict:
    out = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'git': {}, 'acceptance': None,
           'regress': None, 'manifests': [], 'kb': None}
    # git
    try:
        import subprocess
        out['git']['head'] = subprocess.check_output(
            ['git', '-C', BASE, 'rev-parse', '--short', 'HEAD'], text=True).strip()
        out['git']['commits'] = int(subprocess.check_output(
            ['git', '-C', BASE, 'rev-list', '--count', 'HEAD'], text=True).strip())
    except Exception:
        pass
    # 验收
    ap = _latest(os.path.join(BASE, 'data', 'acceptance', 'acceptance_*.json'))
    if ap:
        try:
            rows = json.load(open(ap, encoding='utf-8'))
            acc = [r for r in rows if r.get('accept')]
            out['acceptance'] = {
                'path': ap, 'wells': len(rows),
                'acc_wells': len(acc),
                'fluid_mean': round(sum(r['fluid_agreement'] for r in acc
                                        if r.get('fluid_agreement') is not None) /
                                    max(1, len([r for r in acc if r.get('fluid_agreement') is not None])), 4),
                'completeness_mean': round(sum(r.get('completeness') or 0 for r in acc) / max(1, len(acc)), 4),
                'review_mean': round(sum(r.get('review_rate') or 0 for r in acc) / max(1, len(acc)), 4),
                'lith': [{'well': r['well'], 'lith_accuracy': r.get('lith_accuracy')} for r in rows
                         if r.get('lith_accuracy') is not None],
            }
        except Exception as e:
            out['acceptance'] = {'path': ap, 'error': str(e)}
    # 回归
    rp = _latest(os.path.join(BASE, 'data', 'regress', 'regress_*.json'))
    if rp:
        try:
            d = json.load(open(rp, encoding='utf-8'))
            out['regress'] = {'path': rp, 'summary': d.get('summary'),
                              'golden': (d.get('golden') or {}).get('status'),
                              'wells': [{'well': w.get('well'), 'status': w.get('status'),
                                         'layers': w.get('layers'), 'ml_layers': w.get('ml_layers')}
                                        for w in d.get('wells', [])]}
        except Exception as e:
            out['regress'] = {'path': rp, 'error': str(e)}
    # 运行清单
    man = []
    for root in (os.path.join(WS, 'output'), os.path.join(BASE, 'output')):
        for p in glob.glob(os.path.join(root, '*', '*_run_manifest.json')):
            try:
                d = json.load(open(p, encoding='utf-8'))
                man.append({'well': d.get('well'), 'created_at': d.get('created_at'),
                            'path': p})
            except Exception:
                pass
    out['manifests'] = man
    # 知识库
    try:
        import sys
        sys.path.insert(0, BASE)
        from logsys.knowledge.db import connect, stats
        conn = connect(os.path.join(BASE, 'data', 'kb', 'kb.db'))
        out['kb'] = stats(conn)
        out['kb']['region_calib'] = conn.execute('SELECT COUNT(*) FROM region_calib').fetchone()[0]
        _tp = os.path.join(BASE, 'data', 'kb', 'topics')
        if os.path.isdir(_tp):
            _files = [f for f in glob.glob(os.path.join(_tp, '*.md')) if os.path.basename(f) != 'index.md']
            out['kb']['topics'] = len(_files)
    except Exception as e:
        out['kb'] = {'error': str(e)}
    return out


def render_md(s: dict) -> str:
    a = s.get('acceptance') or {}
    r = s.get('regress') or {}
    md = ['# 智能测井解释系统 批量状态报告', '',
          '> 生成时间：%s　|　代码基线：%s（%s commits）' % (
              s['ts'], (s.get('git') or {}).get('head', '?'),
              (s.get('git') or {}).get('commits', '?')),
          '', '## 验收矩阵（汇总）', '']
    if a.get('error'):
        md.append('- 验收读取失败: ' + a['error'])
    elif a:
        md += ['| 指标 | 值 |', '|---|---|',
               '| 井数（验收/展示） | %d / %d |' % (a.get('acc_wells', 0), a.get('wells', 0)),
               '| 流体层一致率（试油井平均） | %.1f%% |' % (100 * a.get('fluid_mean', 0)),
               '| 层表完整性 | %.1f%% |' % (100 * a.get('completeness_mean', 0)),
               '| 人工复核率 | %.1f%% |' % (100 * a.get('review_mean', 0))]
        for l in a.get('lith', []):
            md.append('| 岩性一致率（%s） | %.1f%% |' % (l['well'], 100 * (l['lith_accuracy'] or 0)))
    md += ['', '## 批量回归', '']
    if r.get('error'):
        md.append('- 回归读取失败: ' + r['error'])
    elif r:
        md += ['| 项 | 值 |', '|---|---|',
               '| 汇总 | %s |' % json.dumps(r.get('summary'), ensure_ascii=False),
               '| 黄金图 | %s |' % r.get('golden')]
    md += ['', '## 运行清单', '',
           '共 **%d** 份（输入指纹/配置快照/版本/产物可追溯）' % len(s.get('manifests', []))]
    for m in s.get('manifests', [])[:10]:
        md.append('- %s（%s）' % (m.get('well'), m.get('created_at')))
    md += ['', '## 知识库', '']
    kb = s.get('kb') or {}
    if kb.get('error'):
        md.append('- 读取失败: ' + kb['error'])
    else:
        md.append('- 文档 %s / 块 %s / 实体 %s / 事实 %s / 案例 %s / 条款 %s / 区域标定 %s' % (
            kb.get('docs'), kb.get('chunks'), kb.get('entities'), kb.get('facts'),
            kb.get('cases'), kb.get('clauses'), kb.get('region_calib')))
        if kb.get('topics'):
            md.append('- 知识库专题报告：%d 个（data/kb/topics/index.md）' % kb['topics'])
    md += ['', '## 产物路径', '',
           '- 验收：`%s`' % a.get('path', '-'),
           '- 回归：`%s`' % r.get('path', '-'),
           '- 状态 JSON：见同目录 status_<ts>.json', '']
    return '\n'.join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description='批量状态报告')
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'status'))
    args = ap.parse_args(argv)
    s = collect()
    os.makedirs(args.out, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    jp = os.path.join(args.out, 'status_%s.json' % ts)
    mp = os.path.join(args.out, 'status_%s.md' % ts)
    json.dump(s, open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    md = render_md(s)
    open(mp, 'w', encoding='utf-8').write(md)
    print(md)
    print('\nsaved:', mp, '|', jp)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
