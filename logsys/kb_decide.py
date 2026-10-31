# -*- coding: utf-8 -*-
"""知识驱动决策与成果报告（一条链路）：

输入：井输出目录（processed CSV / canonical 层表 / 决策 JSON / QC / 清洗报告 / 清单）
知识：kb.db（案例/条款/区域标定）、region_lithology.json（区域岩性规则）、
      井 info.json（解释截止值/解释来源/解释井段）、真值库（岩性剖面/试油真值）
输出：
  - <井>_knowledge_decision.json：参数来源、依据、指标、知识使用情况
  - <井>_decision_report.html：结论 + 准确率 + 指标 + 图（岩性/流体分布、验收指标）

设计：所有参数来自"一处"（info.json/区域标定/默认）并在记录里注明来源；
报告只读成果，不改结论（结论由 arbiter 一处确定）。
"""
from __future__ import annotations

import glob
import json
import os
import time

import numpy as np
import pandas as pd

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'


def _read_json(p):
    try:
        return json.load(open(p, encoding='utf-8')) if p and os.path.exists(p) else {}
    except Exception:
        return {}


def _read_csv(p, **kw):
    try:
        return pd.read_csv(p, low_memory=False, **kw)
    except Exception:
        return pd.DataFrame()


def _img_data_uri(p: str) -> str:
    try:
        import base64
        if p and os.path.exists(p):
            b = base64.b64encode(open(p, 'rb').read()).decode('ascii')
            return 'data:image/png;base64,' + b
    except Exception:
        pass
    return ''


def _html_to_pdf(html_text: str, pdf_path: str) -> str | None:
    try:
        import fitz
        story = fitz.Story(html=html_text)
        writer = fitz.DocumentWriter(pdf_path)
        mediabox = fitz.paper_rect('a4')
        where = mediabox + (36, 36, -36, -36)
        more = True
        while more:
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
        writer.close()
        return pdf_path
    except Exception:
        return None


def _fmt_pct(v):
    return ('%.1f%%' % (100 * v)) if isinstance(v, (int, float)) and v == v else '-'


def collect(out_dir: str, well: str, info: dict | None = None) -> dict:
    """收集成果 + 知识 + 指标，返回决策记录 dict（不写文件）。"""
    rec = {'well': well, 'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
           'artifacts': {}, 'knowledge': {}, 'parameters': {}, 'metrics': {},
           'conclusion': {}, 'notes': []}
    d = str(out_dir)
    # ---------- 成果文件 ----------
    paths = {
        'processed_csv': os.path.join(d, '%s_processed.csv' % well),
        'layers_canonical': os.path.join(d, '%s_interpretation_layers.csv' % well),
        'layers_rules': os.path.join(d, '%s_interpretation_layers_rules.csv' % well),
        'layers_ml': os.path.join(d, '%s_interpretation_layers_ML.csv' % well),
        'decision': os.path.join(d, '%s_interpretation_decision.json' % well),
        'qc_report': os.path.join(d, '%s_qc_report.json' % well),
        'clean_report': os.path.join(d, '%s_data_clean_report.json' % well),
        'manifest': os.path.join(d, '%s_run_manifest.json' % well),
    }
    rec['artifacts'] = {k: (p if os.path.exists(p) else None) for k, p in paths.items()}
    dec = _read_json(paths['decision'])
    rec['conclusion']['interpretation'] = {
        'chosen': dec.get('chosen'), 'policy': dec.get('policy'),
        'reason': dec.get('reason'), 'canonical_rows': dec.get('canonical_rows'),
        'interval': dec.get('interval')}
    # 层表统计
    lay = _read_csv(paths['layers_canonical'])
    if len(lay):
        rec['conclusion']['layers'] = int(len(lay))
        rec['conclusion']['fluid_dist'] = {str(k): int(v) for k, v in
                                           lay['INTERPRETATION'].astype(str).value_counts().items()}
        rec['conclusion']['lith_dist'] = {str(k): int(v) for k, v in
                                          lay['LITHOLOGY'].astype(str).value_counts().items()} if 'LITHOLOGY' in lay else {}
        if 'REVIEW_FLAG' in lay:
            rec['conclusion']['review_rate'] = round(float(
                (lay['REVIEW_FLAG'].fillna('').astype(str).str.len() > 0).mean()), 4)
    # 点级分布
    pr = _read_csv(paths['processed_csv'])
    if len(pr):
        itp = pr['INTERPRETATION'].astype(str) if 'INTERPRETATION' in pr else pd.Series(dtype=str)
        rec['conclusion']['points'] = int(len(pr))
        rec['conclusion']['point_fluid_dist'] = {str(k): int(v) for k, v in itp.value_counts().items()}
        if 'LITHOLOGY' in pr:
            rec['conclusion']['point_lith_dist'] = {str(k): int(v) for k, v in
                                                    pr['LITHOLOGY'].astype(str).value_counts().items()}
    # ---------- 知识使用 ----------
    info = info or {}
    try:
        from .region_lith import region_of_well, allowed_classes, load_cfg
        reg = region_of_well(well)
        rec['knowledge']['region'] = reg
        if reg:
            c = (load_cfg().get('regions') or {}).get(reg) or {}
            rec['knowledge']['region_rules'] = {
                'dominant': c.get('dominant_lithology'), 'allowed': c.get('allowed_classes'),
                'notable': c.get('notable'), 'source': c.get('source')}
            rec['knowledge']['allowed_classes'] = allowed_classes(reg)
    except Exception as e:
        rec['notes'].append('区域岩性规则读取失败: %s' % e)
    # KB 区域标定/案例/条款
    try:
        from .knowledge.db import connect
        conn = connect(os.path.join(BASE, 'data', 'kb', 'kb.db'))
        rec['knowledge']['kb_stats'] = {
            'docs': conn.execute('SELECT COUNT(*) FROM doc').fetchone()[0],
            'cases': conn.execute('SELECT COUNT(*) FROM case_layer').fetchone()[0],
            'clauses': conn.execute('SELECT COUNT(*) FROM clause').fetchone()[0],
        }
        reg2 = rec['knowledge'].get('region') or ''
        country = str(info.get('country') or '').strip()
        rows = conn.execute('SELECT country, region, n_wells, conf, cutoffs_json FROM region_calib').fetchall()
        rec['knowledge']['region_calib'] = [
            {'country': r[0], 'region': r[1], 'n_wells': r[2], 'conf': r[3],
             'cutoffs': _read_json_str(r[4])} for r in rows]
        # 同区域案例数
        if reg2:
            n = conn.execute("SELECT COUNT(*) FROM case_layer WHERE well_id IN "
                             "(SELECT DISTINCT well_id FROM case_layer)").fetchone()[0]
            rec['knowledge']['cases_total'] = n
        cl = [r[0] for r in conn.execute("SELECT std_no FROM clause ORDER BY std_no")]
        rec['knowledge']['clauses'] = cl
    except Exception as e:
        rec['notes'].append('KB 读取失败: %s' % e)
    # ---------- 参数来源（一处确定） ----------
    # 只保留数值参数（去掉 info.json 的说明字段），并标注来源
    _cut = info.get('解释截止值') or {}
    _cut_num = {}
    if isinstance(_cut, dict):
        for _k, _v in _cut.items():
            if str(_k).startswith('_') or _v in ('', None):
                continue
            try:
                _cut_num[_k] = float(_v)
            except Exception:
                pass
    # 截止值来源：井配置 > 国家/区域匹配的区域标定 > 默认
    _rc_match = False
    try:
        _ctry = str(info.get('country') or '').strip().lower()
        for _r in (rec['knowledge'].get('region_calib') or []):
            if _ctry and str(_r.get('country') or '').lower() == _ctry:
                _rc_match = True
                break
    except Exception:
        pass
    _cut_src = ('info.json<井>（井级配置）' if _cut_num else
                ('区域标定(kb region_calib，同国家/区域)' if _rc_match else
                 '默认（区域标定无同国家匹配）'))
    rec['parameters'] = {
        '解释来源': dec.get('policy') or info.get('解释来源') or 'auto',
        '解释截止值': _cut_num,
        '解释截止值来源': _cut_src,
        '解释井段': info.get('解释井段') or dec.get('interval'),
        '区域岩性规则': rec['knowledge'].get('region'),
        '允许岩性': rec['knowledge'].get('allowed_classes'),
    }
    # 清洗/QC 摘要
    cln = _read_json(paths['clean_report'])
    if cln:
        rec['metrics']['data_cleaning'] = {
            'rows_in': cln.get('rows_in'), 'rows_out': cln.get('rows_out'),
            'unit_fixes': list((cln.get('unit_fixes') or {}).keys()),
            'value_total': cln.get('value_total'),
            'vendor_quarantine': cln.get('vendor_quarantine')}
    qc = _read_json(paths['qc_report'])
    if qc:
        rec['metrics']['qc'] = {'quality_level': qc.get('quality_level'),
                                'overall_score': qc.get('overall_score')}
    # ---------- 指标（有真值则算） ----------
    try:
        from .acceptance import WELLS, LITH_PROFILES, compute_well
        spec = WELLS.get(well)
        if spec:
            r = compute_well(well, spec)
            rec['metrics']['fluid'] = {
                'agreement': r.get('fluid_agreement'), 'layers': r.get('layers'),
                'completeness': r.get('completeness'), 'review_rate': r.get('review_rate')}
            if r.get('lith_accuracy') is not None:
                rec['metrics']['lithology'] = {
                    'accuracy': r.get('lith_accuracy'), 'large': r.get('lith_large'),
                    'thin': r.get('lith_thin'), 'truth': LITH_PROFILES.get(well)}
    except Exception as e:
        rec['notes'].append('指标计算失败: %s' % e)
    return rec


def _read_json_str(s):
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}


def write_record(rec: dict, out_dir: str) -> str:
    p = os.path.join(str(out_dir), str(rec.get('well')) + '_knowledge_decision.json')
    json.dump(rec, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return p


def render_html(rec: dict, out_dir: str) -> str:
    """生成完整 HTML 报告（结论+准确率+指标+分布图）。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d = str(out_dir)
    well = rec.get('well', '')
    # 图：岩性/流体分布
    figs = {}
    try:
        pl = rec['conclusion'].get('point_lith_dist') or {}
        if pl:
            fig, ax = plt.subplots(figsize=(6, 3))
            ks = list(pl.keys())[:10]; vs = [pl[k] for k in ks]
            ax.bar(range(len(ks)), vs, color='#4C78A8')
            ax.set_xticks(range(len(ks))); ax.set_xticklabels(ks, rotation=30, ha='right', fontsize=8)
            ax.set_title('Lithology points'); fig.tight_layout()
            p = os.path.join(d, '%s_report_lith.png' % well); fig.savefig(p, dpi=110); plt.close(fig)
            figs['lith'] = p
    except Exception:
        pass
    try:
        pf = rec['conclusion'].get('fluid_dist') or {}
        if pf:
            fig, ax = plt.subplots(figsize=(5, 3))
            ks = list(pf.keys()); vs = [pf[k] for k in ks]
            ax.bar(range(len(ks)), vs, color='#F58518')
            ax.set_xticks(range(len(ks))); ax.set_xticklabels(ks, rotation=30, ha='right', fontsize=8)
            ax.set_title('Layers by fluid'); fig.tight_layout()
            p = os.path.join(d, '%s_report_fluid.png' % well); fig.savefig(p, dpi=110); plt.close(fig)
            figs['fluid'] = p
    except Exception:
        pass
    # 指标
    m = rec.get('metrics') or {}
    fluid_m = m.get('fluid') or {}
    lith_m = m.get('lithology') or {}
    # 知识表
    kb = rec.get('knowledge') or {}
    reg = kb.get('region_rules') or {}
    rc = kb.get('region_calib') or []
    html = ['<!doctype html><html><meta charset="utf-8"><title>%s 解释决策报告</title>' % well,
            '<style>body{font-family:"Microsoft YaHei",Arial;margin:24px;color:#222}'
            'table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px}'
            'h2{border-left:5px solid #4C78A8;padding-left:8px}img{max-width:680px;margin:6px 0}'
            '.ok{color:#1a7f37}.warn{color:#b35900}</style><body>',
            '<h1>%s 知识驱动解释决策报告</h1>' % well,
            '<p>生成时间：%s</p>' % rec.get('created_at')]
    html.append('<h2>1. 决策结论（一处确定）</h2><table>')
    ic = rec.get('conclusion', {}).get('interpretation') or {}
    for k, v in (('解释来源', ic.get('chosen')), ('策略', ic.get('policy')), ('依据', ic.get('reason')),
                 ('canonical 层数', ic.get('canonical_rows')), ('解释井段', ic.get('interval'))):
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (k, v if v is not None else '-'))
    html.append('</table>')
    # 知识
    html.append('<h2>2. 知识使用</h2><table>')
    html.append('<tr><th>区域</th><td>%s</td></tr>' % (kb.get('region') or '-'))
    html.append('<tr><th>区域主要岩性</th><td>%s</td></tr>' % ('、'.join(reg.get('dominant') or []) or '-'))
    html.append('<tr><th>允许岩性</th><td>%s</td></tr>' % ('、'.join(reg.get('allowed') or []) or '-'))
    html.append('<tr><th>区域标定</th><td>%d 个（KB region_calib）</td></tr>' % len(rc))
    if kb.get('kb_stats'):
        html.append('<tr><th>知识库</th><td>文档 %s / 案例 %s / 条款 %s</td></tr>' % (
            kb['kb_stats'].get('docs'), kb['kb_stats'].get('cases'), kb['kb_stats'].get('clauses')))
    html.append('</table>')
    # 参数
    pr = rec.get('parameters') or {}
    html.append('<h2>3. 参数选择（来源可追溯）</h2><table>')
    for k, v in pr.items():
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (k, v))
    html.append('</table>')
    # 结论分布
    html.append('<h2>4. 结论与分布</h2>')
    cd = rec.get('conclusion') or {}
    html.append('<p>点流体：%s</p>' % cd.get('point_fluid_dist'))
    html.append('<p>层流体：%s</p>' % cd.get('fluid_dist'))
    if figs.get('lith'):
        _u = _img_data_uri(figs.get('lith'))
        if _u:
            html.append('<img src="%s" width="640">' % _u)
    if figs.get('fluid'):
        _u = _img_data_uri(figs.get('fluid'))
        if _u:
            html.append('<img src="%s" width="560">' % _u)
    # 指标
    html.append('<h2>5. 准确率与指标</h2><table>')
    if fluid_m:
        html.append('<tr><th>流体层一致率</th><td>%s</td></tr>' % _fmt_pct(fluid_m.get('agreement')))
        html.append('<tr><th>层表完整性</th><td>%s</td></tr>' % _fmt_pct(fluid_m.get('completeness')))
        html.append('<tr><th>人工复核率</th><td>%s</td></tr>' % _fmt_pct(fluid_m.get('review_rate')))
    if lith_m:
        html.append('<tr><th>岩性一致率（层口径）</th><td>%s</td></tr>' % _fmt_pct(lith_m.get('accuracy')))
        html.append('<tr><th>岩性大段(≥2m)</th><td>%s</td></tr>' % _fmt_pct(lith_m.get('large')))
        html.append('<tr><th>岩性薄层(<2m)</th><td>%s</td></tr>' % _fmt_pct(lith_m.get('thin')))
        html.append('<tr><th>岩性真值</th><td>%s</td></tr>' % (lith_m.get('truth') or '-'))
    if not (fluid_m or lith_m):
        html.append('<tr><td>无试油/岩性真值：仅输出结论与过程指标</td></tr>')
    html.append('</table>')
    # 清洗/QC
    mt = rec.get('metrics') or {}
    if mt.get('data_cleaning'):
        c = mt['data_cleaning']
        html.append('<h2>6. 数据清洗与 QC</h2><table>'
                    '<tr><th>清洗行数</th><td>%s → %s</td></tr>'
                    '<tr><th>单位修正</th><td>%s</td></tr>'
                    '<tr><th>非法值</th><td>%s</td></tr>'
                    '<tr><th>厂家退化列隔离</th><td>%s</td></tr>'
                    '<tr><th>QC 等级</th><td>%s（%s）</td></tr></table>' % (
                        c.get('rows_in'), c.get('rows_out'), c.get('unit_fixes'),
                        c.get('value_total'),
                        (c.get('vendor_quarantine') or {}).get('degenerate'),
                        (mt.get('qc') or {}).get('quality_level'), (mt.get('qc') or {}).get('overall_score')))
    if rec.get('notes'):
        html.append('<h2>7. 说明</h2><ul>')
        for n in rec['notes']:
            html.append('<li>%s</li>' % n)
        html.append('</ul>')
    html.append('</body></html>')
    p = os.path.join(d, '%s_decision_report.html' % well)
    _txt = '\n'.join(html)
    open(p, 'w', encoding='utf-8').write(_txt)
    # PDF 版（HTML→PDF；失败不影响主流程）
    try:
        _pdf = os.path.join(d, '%s_decision_report.pdf' % well)
        if _html_to_pdf(_txt, _pdf):
            pass
    except Exception:
        pass
    return p


def build(out_dir: str, well: str, info: dict | None = None) -> dict:
    """收集 → 写决策 JSON → 生成 HTML 报告。返回 {record_path, report_path, ok}。"""
    try:
        rec = collect(out_dir, well, info)
        rp = write_record(rec, out_dir)
        hp = render_html(rec, out_dir)
        _pf = os.path.join(str(out_dir), str(well) + '_decision_report.pdf')
        return {'ok': True, 'record_path': rp, 'report_path': hp,
                'report_pdf': (_pf if os.path.exists(_pf) else None)}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='知识驱动决策记录 + 成果报告')
    ap.add_argument('--well', required=True)
    ap.add_argument('--dir', default=None)
    args = ap.parse_args(argv)
    d = args.dir or os.path.join(WS, 'output', args.well)
    if not os.path.isdir(d):
        d = os.path.join(BASE, 'output', args.well)
    print(json.dumps(build(d, args.well, _read_json(os.path.join(d, args.well + 'info.json'))),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
