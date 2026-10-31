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
    # 录井图（masterlog）解析结果
    _mlp = os.path.join(d, '%s_masterlog_extract.json' % well)
    if os.path.exists(_mlp):
        rec.setdefault('knowledge', {})['masterlog'] = _read_json(_mlp)
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


def _layer_details(pr: pd.DataFrame, lay: pd.DataFrame, gas_zones: pd.DataFrame | None,
                   well: str, gas_events: pd.DataFrame | None = None) -> list:
    """逐层解释依据：曲线统计 + 气测异常/显示 + 岩性 + 图版/证据。"""
    rows = []
    if len(lay) == 0 or len(pr) == 0 or 'MD' not in pr.columns:
        return rows
    md = pd.to_numeric(pr['MD'], errors='coerce')
    def _med(c, m):
        if c not in pr.columns:
            return None
        x = pd.to_numeric(pr.loc[m, c], errors='coerce')
        return round(float(x.median()), 4) if x.notna().any() else None
    for _, r in lay.iterrows():
        try:
            t0, t1 = float(r['TOP_MD']), float(r['BASE_MD'])
        except Exception:
            continue
        m = (md >= t0) & (md < t1)
        if not m.any():
            continue
        itp = str(r.get('INTERPRETATION') or '')
        gz = ''
        if gas_zones is not None and len(gas_zones):
            _ov = ((gas_zones['MD_END'] > t0) & (gas_zones['MD_START'] < t1))
            if _ov.any():
                _z = gas_zones.loc[_ov]
                gz = '%.1f–%.1f m（%d段）' % (float(_z['MD_START'].min()),
                                              float(_z['MD_END'].max()), int(len(_z)))
        # 气测异常点占比
        mg = None
        if 'MASTERLOG_GAS_SHOW' in pr.columns:
            mg = round(float(pd.Series(pr.loc[m, 'MASTERLOG_GAS_SHOW']).fillna(0)
                             .astype(bool).mean()), 2)
        _oil = ''
        if gas_events is not None and len(gas_events):
            _oe = gas_events[gas_events['TYPE'].astype(str).isin(['OIL_SHOW', 'FLUORESCENCE'])]
            if len(_oe):
                _ov2 = ((_oe['MD_END'] > t0) & (_oe['MD_START'] < t1))
                if _ov2.any():
                    _oil = ';'.join(sorted(set(_oe.loc[_ov2, 'TYPE'].astype(str))))
        plate = ''
        if 'PLATE_FLUID' in pr.columns:
            vc = pr.loc[m, 'PLATE_FLUID'].astype(str).value_counts()
            plate = str(vc.index[0]) if len(vc) else ''
        why = str(r.get('REVIEW_FLAG') or '')
        ev = str(r.get('EV_SUMMARY') or '')[:80] if 'EV_SUMMARY' in lay.columns else ''
        rows.append({
            'TOP': round(t0, 1), 'BASE': round(t1, 1),
            'TH': round(float(r.get('THICKNESS') or (t1 - t0)), 1),
            'ITP': itp, 'LITH': str(r.get('LITHOLOGY') or ''),
            'GR': _med('GR', m), 'VSH': _med('VSH', m),
            'PHI': _med('PHI', m) if _med('PHI', m) is not None else _med('POR', m),
            'SW': _med('Sw', m) if _med('Sw', m) is not None else _med('SW_COMP', m),
            'RT': _med('RT', m),
            'DEN': (_med('RHOB', m) if _med('RHOB', m) is not None else _med('DEN', m)),
            'CNL': (_med('CNL', m) if _med('CNL', m) is not None else _med('NPHI', m)),
            'DT': _med('DT', m),
            'PLATE': plate, 'GAS_ZONE': gz, 'MGAS': mg, 'OIL': _oil,
            'FLAG': why, 'EV': ev,
        })
    return rows


def _crossplots(pr: pd.DataFrame, lay: pd.DataFrame, out_dir: str, well: str) -> dict:
    """交汇图（按解释结论着色）：DEN-CNL、GR-RT、PHI-SW。返回 {name: path}。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as _np
    figs = {}
    if len(pr) == 0:
        return figs
    def num(c):
        return pd.to_numeric(pr[c], errors='coerce') if c in pr.columns else None
    itp = pr['INTERPRETATION'].astype(str).str.upper() if 'INTERPRETATION' in pr else None
    classes = ['GAS', 'OIL', 'GAS_OIL', 'OIL_WATER', 'WATER', 'DRY']
    colors = {'GAS': '#d62728', 'OIL': '#2ca02c', 'GAS_OIL': '#ff7f0e',
              'OIL_WATER': '#9467bd', 'WATER': '#1f77b4', 'DRY': '#7f7f7f'}
    def scatter(x, y, fname, xlabel, ylabel, logx=False):
        if x is None or y is None:
            return
        x = pd.to_numeric(x, errors='coerce')
        y = pd.to_numeric(y, errors='coerce')
        ok = x.notna() & y.notna()
        if ok.sum() < 30:
            return
        idx = _np.where(ok.values)[0]
        step = max(1, len(idx) // 4000)
        idx = idx[::step]
        fig, ax = plt.subplots(figsize=(5.6, 4.2))
        if itp is not None:
            for c in classes:
                mm = (itp.values[idx] == c)
                if mm.any():
                    ax.scatter(x.values[idx][mm], y.values[idx][mm], s=6, alpha=0.65,
                               c=colors.get(c, 'k'), label=c)
            ax.legend(fontsize=7, markerscale=1.6, loc='best')
        else:
            ax.scatter(x.values[idx], y.values[idx], s=6, alpha=0.5)
        if logx:
            ax.set_xscale('log')
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.grid(alpha=0.25)
        fig.tight_layout()
        fp = os.path.join(out_dir, '%s_xplot_%s.png' % (well, fname))
        fig.savefig(fp, dpi=120); plt.close(fig)
        figs[fname] = fp
    _den = num('RHOB') if num('RHOB') is not None else num('DEN')
    _cnl = num('CNL') if num('CNL') is not None else num('NPHI')
    scatter(_den, _cnl, 'den_cnl', 'DEN/RHOB (g/cc)', 'CNL/NPHI (%)')
    scatter(num('GR'), num('RT'), 'gr_rt', 'GR (API)', 'RT (ohm·m)', logx=True)
    scatter(num('PHI'), num('SW'), 'phi_sw', 'PHI', 'Sw')
def render_html(rec: dict, out_dir: str) -> str:
    """生成完整 HTML 报告（结论+准确率+指标+分布图）。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d = str(out_dir)
    well = rec.get('well', '')
    # 读取成果数据（分层依据/交汇图）
    _arts = rec.get('artifacts') or {}
    pr = _read_csv(_arts.get('processed_csv')) if _arts.get('processed_csv') else pd.DataFrame()
    lay = _read_csv(_arts.get('layers_canonical')) if _arts.get('layers_canonical') else pd.DataFrame()
    _zf = os.path.join(d, '%s_masterlog_gas_zones.csv' % well)
    _zones = _read_csv(_zf) if os.path.exists(_zf) else None
    _gf = os.path.join(d, '%s_masterlog_gas.csv' % well)
    _gev = _read_csv(_gf) if os.path.exists(_gf) else None
    try:
        _details = _layer_details(pr, lay, _zones, well, _gev)
    except Exception:
        _details = []
    try:
        _xfigs = _crossplots(pr, lay, d, well)
    except Exception:
        _xfigs = {}
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
    # ---- 0. 基础数据 ----
    _pr = pr
    _nrow = int(len(_pr)) if len(_pr) else 0
    _md = pd.to_numeric(_pr['MD'], errors='coerce') if 'MD' in _pr.columns else pd.Series(dtype=float)
    _dmin = round(float(_md.min()), 1) if _md.notna().any() else None
    _dmax = round(float(_md.max()), 1) if _md.notna().any() else None
    _curves = [str(c) for c in _pr.columns if c not in ('MD',)][:40]
    _curves_n = max(0, len(_pr.columns) - 1) if len(_pr.columns) else 0
    html.append('<h2>0. 基础数据</h2><table>')
    html.append('<tr><th>井名</th><td>%s</td></tr>' % well)
    html.append('<tr><th>地区/区域</th><td>%s</td></tr>' % ((rec.get('knowledge') or {}).get('region') or '-'))
    html.append('<tr><th>数据深度范围</th><td>%s–%s m（%d 点）</td></tr>' % (_dmin, _dmax, _nrow))
    html.append('<tr><th>曲线数量</th><td>%d（%s）</td></tr>' % (_curves_n, '、'.join(_curves[:16])))
    _mlr = (rec.get('knowledge') or {}).get('masterlog') or {}
    if _mlr:
        html.append('<tr><th>录井图 masterlog</th><td>岩性 %s 层；气测异常 %s 段/总厚 %s m；范围 %s</td></tr>' % (
            _mlr.get('lith_layers'), _mlr.get('gas_zones'),
            _mlr.get('gas_zone_total_m'), _mlr.get('gas_zone_range')))
    _cl = (rec.get('metrics') or {}).get('data_cleaning') or {}
    _qc = (rec.get('metrics') or {}).get('qc') or {}
    html.append('<tr><th>数据清洗/QC</th><td>%s→%s 行；非法值 %s；QC %s（%s）</td></tr>' % (
        _cl.get('rows_in'), _cl.get('rows_out'), _cl.get('value_total'),
        _qc.get('quality_level'), _qc.get('overall_score')))
    html.append('</table>')
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
    # ---- 4.1 逐层解释依据 ----
    if _details:
        _sel = [x for x in _details if str(x.get('ITP', '')).upper() in
                ('GAS', 'OIL', 'GAS_OIL', 'OIL_WATER', 'WATER', 'DRY')]
        _sel = sorted(_sel, key=lambda x: -(x.get('TH') or 0))[:40]
        html.append('<h2>4.1 逐层解释依据（主要层，按厚度前 %d）</h2>' % len(_sel))
        html.append('<table><tr><th>顶(m)</th><th>底(m)</th><th>厚(m)</th><th>结论</th><th>岩性</th>'
                    '<th>GR</th><th>VSH</th><th>PHI</th><th>Sw</th><th>RT</th>'
                    '<th>气测异常井段</th><th>气测异常点</th><th>油/荧光显示</th>'
                    '<th>图版</th><th>依据/标志</th></tr>')
        for x in _sel:
            html.append('<tr><td>%.1f</td><td>%.1f</td><td>%.1f</td><td><b>%s</b></td><td>%s</td>'
                        '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                        '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                            x['TOP'], x['BASE'], x['TH'], x['ITP'], x['LITH'],
                            x['GR'], x['VSH'], x['PHI'], x['SW'], x['RT'],
                            x['GAS_ZONE'] or '-', x['MGAS'] if x['MGAS'] is not None else '-',
                            x.get('OIL') or '-', x['PLATE'] or '-', (x['FLAG'] or '')[:60]))
        html.append('</table>')
    # ---- 4.2 交汇图 ----
    if _xfigs:
        html.append('<h2>4.2 交汇图（按解释结论着色）</h2>')
        for _k, _fp in _xfigs.items():
            _u = _img_data_uri(_fp)
            if _u:
                html.append('<img src="%s" width="520">' % _u)
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
    # 录井图证据（masterlog）
    _ml = (rec.get('knowledge') or {}).get('masterlog') or {}
    if _ml:
        html.append('<h2>6. 录井图（masterlog）证据</h2><table>')
        html.append('<tr><th>来源 PDF</th><td>%s</td></tr>' % _ml.get('pdf'))
        html.append('<tr><th>岩性层段</th><td>%s 层（%s）</td></tr>' % (
            _ml.get('lith_layers'), _ml.get('lith_dist')))
        html.append('<tr><th>气测异常/油气显示</th><td>%s 条（%s）</td></tr>' % (
            _ml.get('gas_events'), _ml.get('gas_types')))
        html.append('<tr><th>岩性深度范围</th><td>%s</td></tr>' % (_ml.get('depth_range'),))
        html.append('<tr><th>气测异常井段</th><td>%s 段，总厚 %.1f m，范围 %s</td></tr>' % (
            _ml.get('gas_zones'), _ml.get('gas_zone_total_m') or 0, _ml.get('gas_zone_range')))
        html.append('</table>')
        # 气测异常井段明细
        _zf = os.path.join(d, '%s_masterlog_gas_zones.csv' % well)
        if os.path.exists(_zf):
            try:
                _z = pd.read_csv(_zf)
                html.append('<table><tr><th>气测异常井段顶(m)</th><th>底(m)</th>'
                            '<th>厚度(m)</th><th>事件数</th></tr>')
                for _, _r in _z.head(40).iterrows():
                    html.append('<tr><td>%.1f</td><td>%.1f</td><td>%.1f</td><td>%d</td></tr>' % (
                        float(_r['MD_START']), float(_r['MD_END']),
                        float(_r.get('THICK_M') or 0), int(_r.get('EVENTS') or 0)))
                html.append('</table>')
            except Exception:
                pass
        rec.setdefault('metrics', {})['masterlog'] = {
            'lith_layers': _ml.get('lith_layers'), 'gas_events': _ml.get('gas_events'),
            'lith_dist': _ml.get('lith_dist'), 'gas_types': _ml.get('gas_types')}
    # 清洗/QC
    mt = rec.get('metrics') or {}
    if mt.get('data_cleaning'):
        c = mt['data_cleaning']
        html.append('<h2>7. 数据清洗与 QC</h2><table>'
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
