# -*- coding: utf-8 -*-
"""
================================================================================
测井综合解释报告模块（录井 + 气测 + 电测 三资料交汇）  —— 2026-10-06 新增
================================================================================
本模块把"解释一口井"的完整流程固化成代码，以后每解释完一口井即可一键输出
Word 格式的综合报告，报告结构固定为六节（与 BET-1 报告一致）：

    一、基础数据            井位/井身结构/分层/井温/泥浆/资料覆盖范围
    二、测井解释油气层段综合分析
        2.1 曲线特征        分层段 GR/RT/φ/PERM/SW 统计 + 界面与锯齿特征
        2.2 气测显示解释    分段 TGAS、C1-C5 组分、湿度、峰值清单
        2.3 录井含油显示    直照荧光 / 滴照 C·SC / 油迹 / 显示等级（术语对照）
        2.4 三资料交汇      每个重点层段一张交汇图 + 层段数据表
    三、建议试油层段        综合排序 + 施工建议 + 风险提示
    四、结论与建议

对外接口
--------
    generate_comprehensive_report(results, config=None, data=None,
                                  gas_data=None, mudlog_data=None,
                                  output_dir='output', layer_table=None,
                                  well_name=None, top_layers=6)

依赖：pandas / numpy / matplotlib / python-docx
================================================================================
"""

import os
import re
import glob
import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# ---------------------------------------------------------------- 中文字体
_CJK = None


def _setup_cjk_font():
    """注册中文字体，返回字体名（避免图内中文乱码）"""
    global _CJK
    if _CJK:
        return _CJK
    import matplotlib.font_manager as fm
    for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf',
              r'C:\Windows\Fonts\simsun.ttc'):
        if os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
            except Exception:
                pass
    names = {f.name for f in fm.fontManager.ttflist}
    for n in ('Microsoft YaHei', 'SimHei', 'SimSun', 'NSimSun'):
        if n in names:
            matplotlib.rcParams['font.sans-serif'] = [n]
            matplotlib.rcParams['axes.unicode_minus'] = False
            _CJK = n
            return _CJK
    return None


# ---------------------------------------------------------------- 工具函数
def _first_col(df, cands):
    for c in cands:
        if c in df.columns:
            return c
    return None


def _num(df, col):
    if col is None or col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors='coerce')


def fluid_class_from_text(txt):
    """把解释结论（SLAM/人工）归到油/气/水/干四类"""
    s = str(txt or '').lower()
    if not s or s == 'nan':
        return 'OTHER'
    if 'gas&oil' in s or ('gas' in s and 'oil' in s):
        return 'GAS'
    if s.startswith('gas') or '气' in s:
        return 'GAS'
    if 'oil' in s and 'water' in s:
        return 'OIL'          # 油水同层：按油处理并在报告中注明
    if 'oil' in s or '油' in s:
        return 'OIL'
    if 'water' in s or '水' in s:
        return 'WATER'
    return 'OTHER'


FLUID_CN = {'OIL': '油', 'GAS': '气', 'WATER': '水', 'OTHER': '其它'}
FLUID_COLOR = {'OIL': '#2E7D32', 'GAS': '#C62828', 'WATER': '#1565C0',
               'OTHER': '#9E9E9E'}


# ---------------------------------------------------------------- 分层定义
def default_zones(well_depth_top, well_depth_bot):
    """默认层段划分（ft MD）。可由外部按实际分层覆盖。"""
    return [
        ('Gumai 组', None, 6463.0),
        ('Batu Raja 灰岩 (BRF)', 6463.0, 7050.0),
        ('UTAF 上 Talang Akar', 7050.0, 7119.0),
        ('LTAF 上部 (LTAF1)', 7119.0, 7677.0),
        ('LTAF 中部 (LTAF2)', 7677.0, 8333.0),
        ('LTAF 下部 (LTAF3)', 8333.0, 8980.0),
        ('基底', 8980.0, well_depth_bot),
    ]


# ================================================================ 一、基础数据
def collect_basic_data(results, config, data, gas_data):
    """汇总报告第一节所需的井筒与资料信息"""
    r = results or {}
    cfg = config or {}
    info = {
        'well_name': r.get('well_name') or cfg.get('well_name') or 'Unknown',
        'company': r.get('company', ''),
        'field': r.get('field_name', ''),
        'state': r.get('state_or_province', ''),
        'country': r.get('country', ''),
        'well_info': r.get('well_info', {}) or {},
        'param_info': r.get('parameter_info', {}) or {},
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    wi = info['well_info']
    pi = info['param_info']
    info['td_driller'] = wi.get('total_depth_driller', '') or r.get('total_depth', '')
    info['td_logger'] = wi.get('total_depth_logger', '')
    info['log_date'] = wi.get('date', '')
    info['bit_size'] = pi.get('bit_size', '')
    info['casing'] = pi.get('current_casing_size', '')
    info['casing_from'] = pi.get('casing_depth_from', '')
    info['mud_type'] = pi.get('drilling_fluid_type', '')
    info['mud_density'] = pi.get('drilling_fluid_density', '')
    info['mud_viscosity'] = pi.get('drilling_fluid_viscosity', '')
    info['datum'] = wi.get('permanent_datum', '')
    if data is not None and len(data):
        info['log_start'] = float(pd.to_numeric(data['MD'], errors='coerce').min())
        info['log_stop'] = float(pd.to_numeric(data['MD'], errors='coerce').max())
        info['records'] = int(len(data))
    if gas_data is not None and len(gas_data):
        gm = _num(gas_data, _first_col(gas_data, ['MD', 'DEPTH', 'DEPT']))
        info['gas_start'] = float(gm.min())
        info['gas_stop'] = float(gm.max())
    return info


# ================================================================ 二、曲线特征
def curve_features_by_zone(data, zones=None):
    """按层段统计 GR / RT / PHI / PERM / SW / DEN / CNL 的中值与分位数"""
    if data is None or 'MD' not in data.columns:
        return pd.DataFrame()
    d = data.copy()
    d['MD'] = pd.to_numeric(d['MD'], errors='coerce')
    md = d['MD']
    cols = {
        'GR': _first_col(d, ['GR', 'GR_XMAC', 'CGR']),
        'RT': _first_col(d, ['RT', 'RD', 'LLD', 'R90']),
        'PHI': _first_col(d, ['PHI', 'PHI_DN', 'POR', 'PHIE']),
        'PERM': _first_col(d, ['PERM']),
        'SW': _first_col(d, ['SW', 'SW_A', 'Sw']),
        'DEN': _first_col(d, ['DEN', 'ZDEN', 'RHOB']),
        'CNL': _first_col(d, ['CNL', 'CNCF', 'NPHI']),
        'VSH': _first_col(d, ['VSH', 'VSH_GR', 'VSHALE']),
    }
    if zones is None:
        zones = default_zones(float(md.min()), float(md.max()))
    rows = []
    for name, top, bot in zones:
        m = pd.Series(True, index=d.index)
        if top is not None:
            m &= md >= top
        if bot is not None:
            m &= md <= bot
        sub = d[m]
        if not len(sub):
            continue
        row = {'层段': name, '顶深': top, '底深': bot, '样本': int(len(sub))}
        for k, c in cols.items():
            v = pd.to_numeric(sub[c], errors='coerce') if c else pd.Series(dtype=float)
            v = v.replace(-99999, np.nan).dropna()
            if not len(v):
                row[k + '_中值'] = np.nan
                row[k + '_P10'] = np.nan
                row[k + '_P90'] = np.nan
            else:
                row[k + '_中值'] = float(np.percentile(v, 50))
                row[k + '_P10'] = float(np.percentile(v, 10))
                row[k + '_P90'] = float(np.percentile(v, 90))
        rows.append(row)
    return pd.DataFrame(rows)


# ================================================================ 三、气测显示
def gas_summary_by_zone(gas_data, zones=None, tgas_cands=('TGAS', 'TG', 'TGS', 'TOTAL_GAS')):
    """按层段统计气测：TGAS 均值/峰值、组分 C1-C5 占比、湿度 C1/(C2+C3)"""
    if gas_data is None or len(gas_data) == 0:
        return pd.DataFrame(), []
    g = gas_data.copy()
    g['MD'] = pd.to_numeric(g[_first_col(g, ['MD', 'DEPTH', 'DEPT', 'MDEPTH'])], errors='coerce')
    tg = _first_col(g, list(tgas_cands))
    comp = {c: _first_col(g, [c]) for c in ('C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5')}
    if zones is None:
        zones = default_zones(float(g['MD'].min()), float(g['MD'].max()))
    rows = []
    for name, top, bot in zones:
        m = pd.Series(True, index=g.index)
        if top is not None:
            m &= g['MD'] >= top
        if bot is not None:
            m &= g['MD'] <= bot
        sub = g[m]
        if not len(sub):
            continue
        t = pd.to_numeric(sub[tg], errors='coerce') if tg else pd.Series(dtype=float)
        t = t[(t > 0)]
        c1 = _num(sub, comp['C1'])
        c2 = _num(sub, comp['C2'])
        c3 = _num(sub, comp['C3'])
        c4 = _num(sub, comp['IC4']).fillna(0) + _num(sub, comp['NC4']).fillna(0)
        c5 = _num(sub, comp['IC5']).fillna(0) + _num(sub, comp['NC5']).fillna(0)
        tot = (c1.fillna(0) + c2.fillna(0) + c3.fillna(0) + c4 + c5)
        good = tot > 0
        ratio = (c1[good] / (c2[good] + c3[good])).replace([np.inf, -np.inf], np.nan).dropna()
        row = {
            '层段': name, '顶深': top, '底深': bot,
            'TGAS均值': float(t.mean()) if len(t) else np.nan,
            'TGAS峰值': float(t.max()) if len(t) else np.nan,
            'C1占比%': float(c1[good].sum() / tot[good].sum() * 100) if good.any() else np.nan,
            'C2占比%': float(c2[good].sum() / tot[good].sum() * 100) if good.any() else np.nan,
            'C3占比%': float(c3[good].sum() / tot[good].sum() * 100) if good.any() else np.nan,
            'C4+C5占比%': float((c4[good].sum() + c5[good].sum()) / tot[good].sum() * 100) if good.any() else np.nan,
            'C1/(C2+C3)中位': float(ratio.median()) if len(ratio) else np.nan,
        }
        rows.append(row)
    # 峰值清单（局部极大值，±5 ft 合并）
    peaks = []
    if tg:
        arr = g[['MD', tg]].dropna()
        arr = arr[arr[tg] > 0].sort_values('MD')
        vals = arr[tg].values
        mds = arr['MD'].values
        med = float(np.median(vals)) if len(vals) else 0
        for i in range(1, len(vals) - 1):
            if vals[i] >= vals[i - 1] and vals[i] >= vals[i + 1] and vals[i] > max(3 * med, 20):
                if peaks and mds[i] - peaks[-1][0] <= 5:
                    if vals[i] > peaks[-1][1]:
                        peaks[-1] = (float(mds[i]), float(vals[i]))
                else:
                    peaks.append((float(mds[i]), float(vals[i])))
    return pd.DataFrame(rows), sorted(peaks, key=lambda x: -x[1])


# ================================================================ 四、录井含油显示
SHOW_TERMS = [
    ('直照荧光', ['pale yellow', 'yellowish flo', 'pale yellowish', 'dull yellow',
                  'bluishwh sc', 'bluishyell sc', '淡黄色荧光', '暗黄色荧光'],
     '直照荧光颜色（pale yellow=淡黄，dull yellow=暗黄，bluish-white=蓝白）'),
    ('滴照速度', ['slow cut', 'v.slow', 'slow bluishwh', 'vslow', ' sc,', ' cut'],
     'C=快切，SC=slow cut 慢切，V.SLOW=很慢'),
    ('滴照颜色', ['blwsh yellow', 'bluishyell', 'bluishwh', '蓝白', '蓝黄'],
     '蓝白 / 蓝黄 / 蓝白黄'),
    ('油显示', ['oil stain', 'spotty oil stain', 'tr oil show', 'trace-poor oil show',
                'trace oil show', 'no oil odour', '油迹', '微量油'],
     'oil stain=油迹，spotty=零星油迹，tr/trace oil show=微量油显示'),
]

# ---- 录井描述行识别（用于把录井文字落到深度上）----
_ML_LITH = re.compile(r'^\s*(CLYST|SST|SIST|SS|CLST|LIME|DOLO|COAL|META|SAND|DOLO)[\s:]+',
                      re.I)
_ML_SHOW = re.compile(r'(oil stain|tr oil show|trace-poor oil show|trace oil show|'
                      r'no oil (?:stain|odour|show)|good show|fair show|trace show)', re.I)
_ML_FLUOR = re.compile(r'(pale yellowish flo|yellowish flo|dull yellowish flo|'
                       r'pale yell flo|dull yellow flo|bluishwh sc|bluishyell sc|'
                       r'w/\s*\d*-?\s*\d*%?\s*(?:pale |dull |pl )?(?:yellowish|yellow|pale wh) flo)', re.I)
_ML_CUT = re.compile(r'\b(v\.slow|slow|v\.slow|slow cut|sc)\b', re.I)

_LITH_CN_MAP = [
    ('CLYST', '泥岩'), ('CLST', '泥岩'), ('SST', '砂岩'), ('SS', '砂岩'),
    ('SIST', '粉砂岩'), ('COAL', '煤'), ('LIME', '灰岩'), ('DOLO', '白云岩'),
    ('META', '变质岩'), ('SAND', '砂岩'),
]


def _ml_lith_cn(text):
    for key, cn in _LITH_CN_MAP:
        if re.match(r'\s*' + key + r'\b', text, re.I):
            return cn
    return ''


def parse_mudlog(text, page_map=None):
    """把录井报告文本解析成带深度的描述记录。

    录井 PDF 文本层里描述行本身不带深度，只有每页的深度轴刻度是矢量图形（取不到文字）。
    因此深度定位采用两种方式：
      ①传入 page_map = {页号: (页顶深度, 页底深度)}（推荐：由测井/录井资料标定后传入）；
      ②未传入时用"页内最大四位数 + 强制单调"做自动估算（仅作兜底，浅井段可能偏 100-300 ft）。
    页内按描述条目出现顺序在 [页顶, 页底] 间线性插值（误差约 ±20 ft）。

    返回 dict：pages=[(页号, 顶, 底)]、records=[(深度, 类别, 原文)]
    """
    if text is None:
        return {'pages': [], 'records': []}
    if os.path.exists(str(text)):
        txt = open(text, encoding='utf-8', errors='ignore').read()
    else:
        txt = str(text)
    chunks = re.split(r'===PAGE\s+(\d+)===', txt)
    pages, records = [], []
    prev_bottom = 0.0
    for i in range(1, len(chunks), 2):
        no = int(chunks[i])
        body = chunks[i + 1] if i + 1 < len(chunks) else ''
        if page_map and no in page_map:
            top, bottom = float(page_map[no][0]), float(page_map[no][1])
        else:
            nums = [int(x) for x in re.findall(r'\b(\d{4})\b', body)]
            cand = max(nums) if nums else None
            if no == 1:
                bottom = float(cand) if cand else 500.0
                top = 0.0
            else:
                # 兜底：只有比上一页更深才采信，否则按 500 ft 递推
                bottom = float(cand) if (cand and cand > prev_bottom + 100) else prev_bottom + 500.0
                top = prev_bottom
        pages.append((no, top, bottom))
        prev_bottom = bottom

        # 描述条目切分：大写岩性缩写（CLYST/SST/COAL…）或含荧光/油显示关键词的行 = 新条目；
        # 其余以小写开头的行视为上一条目的续行
        entries, cur = [], []
        for ln in body.split('\n'):
            s = ln.strip()
            if not s:
                if cur:
                    entries.append(' '.join(cur))
                    cur = []
                continue
            is_new = bool(_ML_LITH.match(s)) or bool(_ML_SHOW.search(s)) or bool(_ML_FLUOR.search(s))
            if is_new:
                if cur:
                    entries.append(' '.join(cur))
                cur = [s]
            elif cur:
                cur.append(s)
            elif re.match(r'^[a-z]{2,}[\w\s\-]*[,;]', s):
                cur = [s]
        if cur:
            entries.append(' '.join(cur))

        n = len(entries)
        for k, s in enumerate(entries):
            frac = (k + 0.5) / n if n else 0.5
            md = top + (bottom - top) * frac
            cat = 'LITH' if _ML_LITH.match(s) else ('SHOW' if _ML_SHOW.search(s) else 'FLUOR')
            records.append((md, cat, s))
    records.sort(key=lambda r: r[0])
    return {'pages': pages, 'records': records}


def mudlog_evidence(parsed, top, bot, max_items=4, neighbor_ft=0.0):
    """取某井段内的录井证据（岩性 / 直照荧光 / 滴照 / 油显示）。

    neighbor_ft > 0 时，若井段内没有描述条目（薄层常落在条目间隙），
    则补录距井段最近 neighbor_ft 英尺内的描述，并标记为"邻近"。
    """
    out = {'lith': [], 'fluor': [], 'cut': [], 'show': [], 'depth_md': (top, bot),
           'from_neighbor': False}

    def collect(lo, hi):
        for md, cat, s in parsed['records']:
            if lo - 1e-6 <= md <= hi + 1e-6:
                cn = _ml_lith_cn(s)
                if cn:
                    out['lith'].append(cn)
                m = re.search(r'((?:pale |dull |pl |spty )?(?:yellowish|yellow)[a-z]*\s*flo[^,;]*)',
                              s, re.I)
                if m or _ML_FLUOR.search(s):
                    out['fluor'].append((m.group(1).strip() if m else '见荧光描述')[:40])
                m2 = re.search(r'((?:v\.slow|slow)[a-z\s]*sc)', s, re.I)
                if m2:
                    out['cut'].append(m2.group(1).strip()[:24])
                if _ML_SHOW.search(s):
                    m3 = re.search(r'((?:spotty |no |tr |trace-poor |trace )?oil (?:stain|show|odour))',
                                   s, re.I)
                    out['show'].append((m3.group(1).strip() if m3 else '见显示描述')[:46])

    collect(top, bot)
    if neighbor_ft > 0:
        # 薄层常落在描述条目间隙：缺失的类别用邻近条目补齐（并标记为邻近参考）
        missing = [k for k in ('fluor', 'cut', 'show') if not out[k]]
        if missing:
            near = [r for r in parsed['records']
                    if (top - neighbor_ft) <= r[0] <= (bot + neighbor_ft)]
            near.sort(key=lambda r: min(abs(r[0] - top), abs(r[0] - bot)))
            for md, cat, s in near:
                m = re.search(r'((?:pale |dull |pl |spty )?(?:yellowish|yellow)[a-z]*\s*flo[^,;]*)',
                              s, re.I)
                if 'fluor' in missing and (m or _ML_FLUOR.search(s)):
                    out['fluor'].append((m.group(1).strip() if m else '见荧光描述')[:40])
                    missing.remove('fluor')
                    out['from_neighbor'] = True
                m2 = re.search(r'((?:v\.slow|slow)[a-z\s]*sc)', s, re.I)
                if 'cut' in missing and m2:
                    out['cut'].append(m2.group(1).strip()[:24])
                    missing.remove('cut')
                    out['from_neighbor'] = True
                if 'show' in missing and _ML_SHOW.search(s):
                    m3 = re.search(
                        r'((?:spotty |no |tr |trace-poor |trace )?oil (?:stain|show|odour))', s, re.I)
                    out['show'].append((m3.group(1).strip() if m3 else '见显示描述')[:46])
                    missing.remove('show')
                    out['from_neighbor'] = True
                if not missing:
                    break
        if not out['lith']:
            cn = [_ml_lith_cn(r[2]) for r in parsed['records']
                  if top - neighbor_ft <= r[0] <= bot + neighbor_ft and _ml_lith_cn(r[2])]
            if cn:
                out['lith'] = cn[:max_items]
                out['from_neighbor'] = True
    for k in ('lith', 'fluor', 'cut', 'show'):
        out[k] = out[k][:max_items]
    return out


def mudlog_evidence_text(ev):
    """把录井证据拼成一句话，用于表格/结论"""
    parts = []
    if ev.get('lith'):
        parts.append('岩性：' + '、'.join(dict.fromkeys(ev['lith'])))
    if ev.get('fluor'):
        parts.append('直照：' + '；'.join(dict.fromkeys(ev['fluor'])))
    if ev.get('cut'):
        parts.append('滴照：' + '、'.join(dict.fromkeys(ev['cut'])))
    if ev.get('show'):
        parts.append('油显示：' + '；'.join(dict.fromkeys(ev['show'])))
    txt = ' | '.join(parts) if parts else '该井段录井未见明显含油显示'
    if ev.get('from_neighbor'):
        txt += '（录井描述取自邻近井段）'
    return txt


def mudlog_show_summary(mudlog_text_or_path, depth_ranges=None):
    """从录井报告文本中统计含油显示术语（可给深度区间做分段统计）。

    mudlog_text_or_path : 录井报告全文字符串或 txt 路径
    depth_ranges : [(标签, 顶, 底), ...]，None 表示全文统计
    返回 {标签: {术语类别: [命中的原文片段...]}}
    """
    if mudlog_text_or_path is None:
        return {}
    if os.path.exists(str(mudlog_text_or_path)):
        txt = open(mudlog_text_or_path, encoding='utf-8', errors='ignore').read()
    else:
        txt = str(mudlog_text_or_path)
    lines = [l.strip() for l in txt.split('\n') if l.strip()]
    out = {}
    groups = depth_ranges or [('全井', None, None)]
    for label, top, bot in groups:
        # 无深度信息时按整段文本统计；有区间时按行内出现的深度数字粗略归属
        seg_lines = lines
        if top is not None:
            seg_lines = []
            for i, l in enumerate(lines):
                nums = re.findall(r'\b(\d{3,5})\b', l)
                if nums and any(top <= float(n) <= bot for n in nums):
                    seg_lines.append(l)
                    seg_lines.extend(lines[max(0, i - 1):i])
                    seg_lines.extend(lines[i + 1:i + 2])
        d = {}
        for cat, keys, desc in SHOW_TERMS:
            hits = []
            for l in seg_lines:
                low = l.lower()
                for k in keys:
                    if k.lower() in low:
                        hits.append(l[:120])
                        break
            if hits:
                d[cat] = hits[:12]
        d['__术语说明__'] = [x[2] for x in SHOW_TERMS]
        out[label] = d
    return out


# ================================================================ 五、层段排序
def rank_layers(data, zones=None, gas_data=None, top_n=6,
                min_thick=3.0, fluid_col_cands=('INTERPRETATION', 'INTERP', 'FLUID')):
    """按物性×含油气性对层段排序，返回候选试油层段列表"""
    if data is None or 'MD' not in data.columns:
        return []
    d = data.copy().sort_values('MD').reset_index(drop=True)
    d['MD'] = pd.to_numeric(d['MD'], errors='coerce')
    fcol = _first_col(d, list(fluid_col_cands))
    if fcol is None:
        d['__FLUID__'] = 'OTHER'
        fcol = '__FLUID__'
    else:
        d['__FLUID__'] = [fluid_class_from_text(v) for v in d[fcol]]
    g = _num(d, _first_col(d, ['GR', 'GR_XMAC', 'CGR']))
    rt = _num(d, _first_col(d, ['RT', 'RD', 'LLD', 'R90']))
    phi = _num(d, _first_col(d, ['PHI', 'PHI_DN', 'POR', 'PHIE']))
    perm = _num(d, 'PERM')
    sw = _num(d, _first_col(d, ['SW_A', 'SW', 'Sw']))
    tgas = None
    if gas_data is not None and len(gas_data):
        gd = gas_data.copy()
        gd['MD'] = pd.to_numeric(gd[_first_col(gd, ['MD', 'DEPTH', 'DEPT', 'MDEPTH'])], errors='coerce')
        tgas = pd.to_numeric(gd[_first_col(gd, ['TGAS', 'TG', 'TGS'])], errors='coerce') \
            if _first_col(gd, ['TGAS', 'TG', 'TGS']) else None
        gd = gd.assign(_t=tgas)

    # 逐点储层判据
    ok = (g < 110) & (rt > 8) & (phi > 3) & (g.notna()) & (rt.notna())
    d['_ok'] = ok.fillna(False)
    segs = []
    i = 0
    n = len(d)
    while i < n:
        if d.at[i, '_ok']:
            j = i + 1
            while j < n and d.at[j, '_ok']:
                j += 1
            top, bot = float(d.at[i, 'MD']), float(d.at[j - 1, 'MD'])
            if bot - top >= min_thick:
                segs.append((i, j, top, bot))
            i = j
        else:
            i += 1
    out = []
    for (i0, i1, top, bot) in segs:
        sub = d.iloc[i0:i1]
        fluids = [f for f in sub['__FLUID__'] if f != 'OTHER']
        fac = max(set(fluids), key=fluids.count) if fluids else 'OTHER'
        tg_peak = np.nan
        if tgas is not None and gd is not None:
            sel = gd[(gd['MD'] >= top) & (gd['MD'] <= bot)]['_t']
            if len(sel):
                tg_peak = float(sel.max())
        out.append({
            'top': top, 'bot': bot, 'thick': bot - top,
            'gr': float(g.iloc[i0:i1].median()),
            'rt': float(rt.iloc[i0:i1].median()),
            'phi': float(phi.iloc[i0:i1].median()) if phi.iloc[i0:i1].notna().any() else np.nan,
            'perm': float(perm.iloc[i0:i1].median()) if perm.iloc[i0:i1].notna().any() else np.nan,
            'sw': float(sw.iloc[i0:i1].median()) if sw.iloc[i0:i1].notna().any() else np.nan,
            'fluid': fac, 'tgas_peak': tg_peak,
        })
    # 评分：厚度 + 储集物性 + 含油气性 + 气测
    for s in out:
        s['score'] = (min(s['thick'], 25) * 1.0 +
                      (0 if np.isnan(s['phi']) else min(s['phi'], 25)) * 1.2 +
                      (0 if np.isnan(s['perm']) else min(np.log10(max(s['perm'], 0.01)) + 2, 6)) * 6 +
                      (0 if np.isnan(s['sw']) else max(0, 80 - s['sw'])) * 0.25 +
                      (0 if np.isnan(s['tgas_peak']) else min(np.log10(max(s['tgas_peak'], 1)), 3)) * 8 +
                      {'OIL': 30, 'GAS': 26, 'WATER': 0, 'OTHER': 8}.get(s['fluid'], 8))
    out.sort(key=lambda x: -x['score'])
    for k, s in enumerate(out):
        s['no'] = k + 1
    return out[:top_n]


# ================================================================ 六、层段交汇图
def plot_layer_crossplot(data, seg, out_png, title_extra='', depth_unit='ft'):
    """为重点层段生成专属交汇图（RT-φ + GR-ρ），按流体类型着色并标注层段数据"""
    _setup_cjk_font()
    d = data.copy()
    d['MD'] = pd.to_numeric(d['MD'], errors='coerce')
    sub = d[(d['MD'] >= seg['top']) & (d['MD'] <= seg['bot'])].copy()
    if not len(sub):
        return None
    rt = pd.to_numeric(sub[_first_col(sub, ['RT_LAS', 'RT', 'RD', 'LLD', 'R90'])], errors='coerce')
    phi = pd.to_numeric(sub[_first_col(sub, ['PHI_LAS', 'PHI', 'PHI_DN', 'POR', 'PHIE'])], errors='coerce')
    gr = pd.to_numeric(sub[_first_col(sub, ['GR_LAS', 'GR', 'GR_XMAC', 'CGR'])], errors='coerce')
    den = pd.to_numeric(sub[_first_col(sub, ['DEN_LAS', 'DEN', 'ZDEN', 'RHOB'])], errors='coerce')
    fcol = _first_col(sub, ['__FLUID__', 'INTERPRETATION', 'INTERP', 'FLUID'])
    if fcol is None:
        fl = pd.Series(['OTHER'] * len(sub), index=sub.index)
    else:
        fl = sub[fcol] if fcol == '__FLUID__' else [fluid_class_from_text(v) for v in sub[fcol]]
        fl = pd.Series(fl, index=sub.index)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, (x, y, xl, yl, logx) in zip(axes, [
            (rt, phi, 'RT/RD (Ω·m)', '孔隙度 φ (%)', True),
            (gr, den, 'GR (API)', '密度 DEN (g/cm³)', False)]):
        for f in ('OIL', 'GAS', 'WATER', 'OTHER'):
            m = (fl == f) & x.notna() & y.notna()
            if not m.any():
                continue
            ax.scatter(x[m], y[m], s=16, c=FLUID_COLOR[f], alpha=0.75,
                       edgecolors='none', label=FLUID_CN[f])
        if logx:
            ax.set_xscale('log')
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.grid(alpha=0.3, lw=0.5)
        ax.legend(loc='upper right', fontsize=8)
    fig.suptitle('%s  %s  井段 %.0f-%.0f %s（厚 %.1f %s）%s'
                 % (seg.get('well', ''), seg.get('name', ''), seg['top'], seg['bot'],
                    depth_unit, seg['thick'], depth_unit, title_extra),
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    return out_png


def plot_zone_crosspot(data, out_png, title='', depth_unit='ft'):
    """全井两幅交会图：RT-φ（含水饱和度配色）与 GR-ρ"""
    _setup_cjk_font()
    d = data.copy()
    d['MD'] = pd.to_numeric(d['MD'], errors='coerce')
    rt = pd.to_numeric(d[_first_col(d, ['RT_LAS', 'RT', 'RD', 'LLD', 'R90'])], errors='coerce')
    phi = pd.to_numeric(d[_first_col(d, ['PHI_LAS', 'PHI', 'PHI_DN', 'POR', 'PHIE'])], errors='coerce')
    gr = pd.to_numeric(d[_first_col(d, ['GR_LAS', 'GR', 'GR_XMAC', 'CGR'])], errors='coerce')
    den = pd.to_numeric(d[_first_col(d, ['DEN_LAS', 'DEN', 'ZDEN', 'RHOB'])], errors='coerce')
    sw = pd.to_numeric(d[_first_col(d, ['SW_LAS', 'SW_A', 'SW', 'Sw'])], errors='coerce')
    fcol = _first_col(d, ['__FLUID__', 'INTERPRETATION', 'INTERP', 'FLUID'])
    fl = (d[fcol] if fcol == '__FLUID__' else
          [fluid_class_from_text(v) for v in d[fcol]] if fcol else ['OTHER'] * len(d))
    fl = pd.Series(fl, index=d.index)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for f in ('OIL', 'GAS', 'WATER', 'OTHER'):
        m = (fl == f) & rt.notna() & phi.notna() & (rt > 0)
        if m.any():
            axes[0].scatter(rt[m], phi[m], s=12, c=FLUID_COLOR[f], alpha=0.7,
                            edgecolors='none', label=FLUID_CN[f])
    axes[0].set_xscale('log')
    axes[0].set_xlabel('RT/RD (Ω·m, 对数)')
    axes[0].set_ylabel('孔隙度 φ (%)')
    axes[0].set_title('电阻率-孔隙度（流体类型）', fontsize=10)
    axes[0].grid(alpha=0.3, lw=0.5)
    axes[0].legend(loc='upper right', fontsize=8, title='流体')
    sc = axes[1].scatter(gr, den, s=12, c=sw, cmap='viridis', alpha=0.8, edgecolors='none')
    axes[1].set_xlabel('GR (API)')
    axes[1].set_ylabel('密度 DEN (g/cm³)')
    axes[1].set_title('伽马-密度（颜色=含水饱和度 Sw）', fontsize=10)
    axes[1].grid(alpha=0.3, lw=0.5)
    fig.colorbar(sc, ax=axes[1], label='Sw (%)')
    fig.suptitle(title or '全井交会图', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    return out_png


# ================================================================ 七、Word 输出
def _fmt(v, nd=2, dash='-'):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return dash
        return ('%.*f' % (nd, float(v)))
    except Exception:
        return str(v)


def _add_table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = str(h)
        for pr in c.paragraphs:
            for r in pr.runs:
                r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = '' if v is None else str(v)
    return t


def build_docx(path, basic, zone_stats, gas_stats, gas_peaks, shows,
               layers, layer_images, zone_image, extra_notes=None,
               extra_images=None, fluid_stats=None, zone_mudlog=None):
    """按六节结构生成 Word 报告

    extra_images : [(标题, png路径), ...] 额外的整井图件（如流体交会图）
    fluid_stats  : 流体类型统计 DataFrame（油/气/水层段数与厚度）
    zone_mudlog  : [(层段, 顶, 底, 岩性, 直照, 滴照, 油显示), ...] 分段录井证据
    """
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    st = doc.styles['Normal']
    st.font.name = '宋体'
    st.font.size = Pt(10.5)

    doc.add_heading('%s 测井综合解释报告（录井+气测+电测）' % basic['well_name'], level=0)
    p = doc.add_paragraph()
    p.add_run('生成时间：%s    数据源：电测 + 气测 + 录井三资料交汇' % basic['generated_at']).italic = True

    # 一、基础数据
    doc.add_heading('一、基础数据', level=1)
    rows = [
        ['井名', basic['well_name'], '区块/油田', basic.get('field', '')],
        ['国家/省', '%s / %s' % (basic.get('country', ''), basic.get('state', '')), '公司', basic.get('company', '')],
        ['测井井段', '%s - %s %s' % (basic.get('log_start', '-'), basic.get('log_stop', '-'), 'ft'),
         '记录数', basic.get('records', '-')],
        ['气测井段', '%s - %s ft' % (basic.get('gas_start', '-'), basic.get('gas_stop', '-')),
         '完钻井深(钻员/测井)', '%s / %s' % (basic.get('td_driller', '-'), basic.get('td_logger', '-'))],
        ['井眼/套管', '%s @ %s' % (basic.get('bit_size', '-'), basic.get('casing_from', '-')),
         '套管尺寸', basic.get('casing', '-')],
        ['泥浆类型', basic.get('mud_type', '-'), '泥浆密度/粘度',
         '%s / %s' % (basic.get('mud_density', '-'), basic.get('mud_viscosity', '-'))],
        ['基准面', basic.get('datum', '-'), '测井日期', basic.get('log_date', '-')],
    ]
    _add_table(doc, ['项目', '内容', '项目', '内容'], rows)

    # 二、综合分析
    doc.add_heading('二、测井解释油气层段综合分析', level=1)
    doc.add_heading('2.1 曲线特征（分层段统计）', level=2)
    if len(zone_stats):
        rows = []
        for _, r in zone_stats.iterrows():
            rows.append([r['层段'],
                         _fmt(r.get('GR_中值'), 1), '%s-%s' % (_fmt(r.get('GR_P10'), 0), _fmt(r.get('GR_P90'), 0)),
                         _fmt(r.get('RT_中值'), 2), _fmt(r.get('RT_P90'), 1),
                         _fmt(r.get('PHI_中值'), 1), _fmt(r.get('PHI_P90'), 1),
                         _fmt(r.get('PERM_P90'), 2), _fmt(r.get('SW_P10'), 1),
                         _fmt(r.get('DEN_中值'), 2)])
        _add_table(doc, ['层段', 'GR中值', 'GR P10-P90', 'RT中值', 'RT P90',
                         'φ中值', 'φ P90', 'PERM P90', 'Sw P10', 'DEN中值'], rows)
    else:
        doc.add_paragraph('（无电测数据，跳过）')

    doc.add_heading('2.2 气测显示解释', level=2)
    if len(gas_stats):
        rows = []
        for _, r in gas_stats.iterrows():
            rows.append([r['层段'], _fmt(r.get('TGAS均值'), 1), _fmt(r.get('TGAS峰值'), 0),
                         _fmt(r.get('C1占比%'), 1), _fmt(r.get('C2占比%'), 1),
                         _fmt(r.get('C3占比%'), 1), _fmt(r.get('C4+C5占比%'), 1),
                         _fmt(r.get('C1/(C2+C3)中位'), 1)])
        _add_table(doc, ['层段', 'TGAS均值', 'TGAS峰值', 'C1%', 'C2%', 'C3%', 'C4+C5%',
                         'C1/(C2+C3)'], rows)
    if gas_peaks:
        doc.add_paragraph('重点气显示（Top 15）：' + '；'.join(
            '%.0f ft（TGAS %.0f）' % (d, v) for d, v in gas_peaks[:15]))
    else:
        doc.add_paragraph('（无气测数据）')

    doc.add_heading('2.3 录井含油显示', level=2)
    if zone_mudlog:
        doc.add_paragraph('录井描述按页内顺序定位到深度（页内插值，深度误差约 ±20 ft）；'
                          '荧光/滴照/油显示术语按录井原报告记录。')
        rows = []
        for (zn, zt, zb, lith, fluor, cut, show) in zone_mudlog:
            rows.append([zn, '%.0f-%.0f' % (zt, zb),
                         '、'.join(list(dict.fromkeys(lith))[:3]) if lith else '-',
                         '；'.join(list(dict.fromkeys(fluor))[:2]) if fluor else '未见荧光',
                         '、'.join(list(dict.fromkeys(cut))[:2]) if cut else '-',
                         '；'.join(list(dict.fromkeys(show))[:3]) if show else '无油显示'])
        _add_table(doc, ['层段', '井段(ft)', '录井岩性', '直照荧光', '滴照', '油显示'], rows)
        doc.add_paragraph('术语：直照荧光（pale yellow=淡黄 / dull yellow=暗黄）；'
                          '滴照 C=快切、SC=slow cut 慢切、V.SLOW=很慢，'
                          '颜色 bluish-white=蓝白、bluish-yellow=蓝黄；'
                          'oil stain=油迹、spotty=零星油迹、tr/trace oil show=微量油显示。')
    elif shows:
        for label, d in shows.items():
            doc.add_paragraph('【%s】' % label)
            rows = [[k, '；'.join(v[:4])] for k, v in d.items() if k != '__术语说明__']
            if rows:
                _add_table(doc, ['显示类别', '录井描述（摘录）'], rows)
            doc.add_paragraph('术语：' + '；'.join(d.get('__术语说明__', [])))
    else:
        doc.add_paragraph('（未提供录井文本）')

    doc.add_heading('2.4 交汇图', level=2)
    if fluid_stats is not None and len(fluid_stats):
        rows = [[r.get('流体类型', ''), r.get('层段数', ''), r.get('厚度(ft)', ''),
                 r.get('厚度占比%', '')] for _, r in fluid_stats.iterrows()]
        _add_table(doc, ['流体类型', '层段数', '厚度(ft)', '厚度占比%'], rows)
    if zone_image and os.path.exists(zone_image):
        doc.add_picture(zone_image, width=Inches(6.3))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph('图：全井电阻率-孔隙度 / 伽马-密度交汇图').alignment = WD_ALIGN_PARAGRAPH.CENTER
    for cap, p in (extra_images or []):
        if p and os.path.exists(p):
            doc.add_picture(p, width=Inches(6.3))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph(cap).alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 三、建议试油层段
    doc.add_heading('三、建议试油层段', level=1)
    if layers:
        rows = []
        for s in layers:
            rows.append([s['no'], '%.1f-%.1f' % (s['top'], s['bot']), _fmt(s['thick'], 1),
                         _fmt(s['gr'], 1), _fmt(s['rt'], 2), _fmt(s['phi'], 1),
                         _fmt(s['perm'], 2), _fmt(s['sw'], 1),
                         _fmt(s['tgas_peak'], 0), FLUID_CN.get(s['fluid'], '其它'),
                         (s.get('mudlog_short') or '-')])
        _add_table(doc, ['排序', '井段(ft)', '厚度(ft)', 'GR', 'RT', 'φ(%)', 'PERM(mD)',
                         'Sw(%)', 'TGAS峰', '流体', '录井含油显示'], rows)
    else:
        doc.add_paragraph('（未识别出满足判据的储层段：GR<110、RT>8Ω·m、φ>3%、厚度≥3ft）')

    # 四、逐层交汇图
    doc.add_heading('四、逐层交汇图与层段评价', level=1)
    for s in layers:
        img = layer_images.get(s['no'])
        doc.add_heading('层 %d：%.0f-%.0f ft（厚 %.1f ft）' % (s['no'], s['top'], s['bot'], s['thick']), level=2)
        rows = [['解释结论', '%s' % FLUID_CN.get(s['fluid'], '其它')],
                ['GR / RT', '%s API / %s Ω·m' % (_fmt(s['gr'], 1), _fmt(s['rt'], 2))],
                ['φ / PERM', '%s %% / %s mD' % (_fmt(s['phi'], 1), _fmt(s['perm'], 2))],
                ['Sw', _fmt(s['sw'], 1)],
                ['气测峰值', _fmt(s['tgas_peak'], 0)],
                ['录井显示', s.get('mudlog_text') or '该井段录井未见明显含油显示'],
                ['测井判据', '低伽马+高阻+中高孔隙度'],
                ['建议', '试油/酸化压裂优先段' if s['no'] <= 3 else '作为后续评价或对比层']]
        _add_table(doc, ['项目', '数值'], rows)
        if img and os.path.exists(img):
            doc.add_picture(img, width=Inches(6.1))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 五、结论与建议
    doc.add_heading('五、结论与建议', level=1)
    for line in (extra_notes or []):
        doc.add_paragraph(line, style='List Bullet')

    doc.save(path)
    return path


# ================================================================ 入口
def generate_comprehensive_report(results, config=None, data=None, gas_data=None,
                                  mudlog_data=None, output_dir='output',
                                  layer_table=None, well_name=None,
                                  top_layers=6, zones=None, extra_notes=None,
                                  make_plots=True, extra_images=None,
                                  depth_unit='ft', mudlog_page_map=None):
    """一键生成 Word 综合解释报告，返回文件路径

    extra_images    : [(标题, png路径), ...] 额外的整井图件（如流体交会图）
    mudlog_page_map : {页号: (页顶深度, 页底深度)}，录井页深度标定（强烈建议传入）
    """
    _setup_cjk_font()
    results = results or {}
    cfg = config or {}
    well = well_name or results.get('well_name') or (cfg.get('well_name') or 'Unknown')
    outdir = os.path.join(output_dir, str(well))
    os.makedirs(outdir, exist_ok=True)

    basic = collect_basic_data(results, cfg, data, gas_data)
    basic['well_name'] = well
    if zones is None and data is not None and len(data):
        md = pd.to_numeric(data['MD'], errors='coerce')
        zones = default_zones(float(md.min()), float(md.max()))

    zs = curve_features_by_zone(data, zones)
    gs, peaks = gas_summary_by_zone(gas_data, zones)
    shows = mudlog_show_summary(mudlog_data) if mudlog_data is not None else {}
    layers = rank_layers(data, zones, gas_data, top_n=top_layers)

    # ---- 录井：解析出带深度的描述记录，并按层段/候选层取证据 ----
    ml_parsed = parse_mudlog(mudlog_data, page_map=mudlog_page_map) if mudlog_data is not None else None
    zone_mudlog = []
    if ml_parsed and ml_parsed['records']:
        for (zn, zt, zb) in (zones or []):
            if zt is None:
                continue
            ev = mudlog_evidence(ml_parsed, zt, zb, max_items=4)
            zone_mudlog.append((zn, zt, zb, ev['lith'], ev['fluor'], ev['cut'], ev['show']))
        for s in layers:
            ev = mudlog_evidence(ml_parsed, s['top'], s['bot'], max_items=3, neighbor_ft=25)
            s['mudlog_text'] = mudlog_evidence_text(ev)
            tags = []
            if ev['lith']:
                tags.append('/'.join(list(dict.fromkeys(ev['lith']))[:2]))
            if ev['fluor']:
                tags.append('直照淡黄' if any('yellow' in f.lower() for f in ev['fluor']) else '见荧光')
            if ev['cut']:
                tags.append('滴照' + list(dict.fromkeys(ev['cut']))[0])
            shows = [t for t in ev['show'] if not t.lower().startswith('no ')]
            if any('stain' in t.lower() for t in shows):
                tags.append('油迹')
            elif shows:
                tags.append('微量油')
            if ev['from_neighbor']:
                tags.append('(邻近段)')
            s['mudlog_short'] = '；'.join(tags) if tags else '无显示'

    # 图件
    zone_img = None
    layer_imgs = {}
    if make_plots and data is not None and len(data):
        try:
            zone_img = plot_zone_crosspot(data, os.path.join(outdir, '%s_全井交汇图.png' % well),
                                         title='%s 全井交汇图' % well)
        except Exception as e:
            print('[报告] 全井交汇图失败:', e)
        for s in layers:
            try:
                nm = '%s_层%d_%.0f-%.0fft_交汇图.png' % (well, s['no'], s['top'], s['bot'])
                p = plot_layer_crossplot(data, s, os.path.join(outdir, nm))
                if p:
                    layer_imgs[s['no']] = p
            except Exception as e:
                print('[报告] 层段交汇图失败:', e)

    notes = extra_notes or []
    if layers:
        top = layers[0]
        notes = (['共识别 %d 个储层候选段，最优层段为 %.0f-%.0f ft（厚 %.1f ft，φ=%s%%，PERM=%s mD，Sw=%s%%）。'
                  % (len(layers), top['top'], top['bot'], top['thick'],
                     _fmt(top['phi'], 1), _fmt(top['perm'], 2), _fmt(top['sw'], 1))]
                 + notes)
    else:
        notes = ['按当前判据（GR<110、RT>8Ω·m、φ>3%、厚度≥3ft）未识别出候选层段，'
                 '建议检查解释参数（孔隙度/电阻率门限）或复核曲线单位。'] + notes

    # 流体类型统计（油/气/水层段数与厚度）
    fluid_stats = None
    if data is not None and 'MD' in data.columns and len(data):
        try:
            dd = data.copy()
            dd['MD'] = pd.to_numeric(dd['MD'], errors='coerce')
            fc = _first_col(dd, ['__FLUID__', 'INTERPRETATION', 'INTERP', 'FLUID'])
            if fc is not None:
                fl = (dd[fc] if fc == '__FLUID__' else
                      [fluid_class_from_text(v) for v in dd[fc]])
                fl = pd.Series(fl, index=dd.index)
                mdv = dd['MD']
                segs, prev, start = [], None, None
                for i in range(len(dd)):
                    f = fl.iloc[i]
                    if f != prev:
                        if prev is not None and prev != 'OTHER':
                            segs.append((prev, float(start), float(mdv.iloc[i - 1])))
                        prev, start = f, mdv.iloc[i]
                if prev is not None and prev != 'OTHER':
                    segs.append((prev, float(start), float(mdv.iloc[-1])))
                agg = {}
                for f, a, b in segs:
                    if b - a < 1.0:            # 小于 1ft 的碎层不计入
                        continue
                    d_ = agg.setdefault(f, [0, 0.0])
                    d_[0] += 1
                    d_[1] += (b - a)
                total = sum(v[1] for v in agg.values()) or 1.0
                fluid_stats = pd.DataFrame(
                    [{'流体类型': FLUID_CN.get(k, k), '层段数': v[0], '厚度(ft)': round(v[1], 1),
                      '厚度占比%': round(v[1] / total * 100, 1)} for k, v in agg.items()])
        except Exception as e:
            print('[报告] 流体统计失败:', e)

    path = os.path.join(outdir, '%s_综合解释报告.docx' % well)
    build_docx(path, basic, zs, gs, peaks, shows, layers, layer_imgs, zone_img, notes,
               extra_images=extra_images, fluid_stats=fluid_stats,
               zone_mudlog=zone_mudlog)
    return path
