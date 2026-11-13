# -*- coding: utf-8 -*-
"""生成知识库统计交付物（纯 .replace 占位，避免 CSS 花括号与 .format 冲突）：
  1) output/country_domain_stacked.html  国别 × 领域 堆叠图（交互：悬停明细 + 缩放 + 图例切换）
  2) output/country_domain_matrix.html    国别 × 领域 交叉分布表（可排序）
  3) output/分类说明文档.html            完整分类体系 + 堆叠图 + 交叉表（自包含）
"""
import sqlite3, sys, os, json, base64
sys.path.insert(0, '.')
from logsys.knowledge import db

OUT = 'output'
os.makedirs(OUT, exist_ok=True)
conn = db.connect('data/kb/kb.db')

# ---------- 取数 ----------
total = conn.execute("SELECT COUNT(*) FROM doc").fetchone()[0]
n_country = conn.execute(
    "SELECT COUNT(*) FROM doc WHERE country IS NOT NULL AND country!=''").fetchone()[0]
n_nocountry = total - n_country

domains = [r[0] for r in conn.execute(
    "SELECT category, COUNT(*) FROM doc GROUP BY category ORDER BY 2 DESC")]
domain_counts = dict(conn.execute(
    "SELECT category, COUNT(*) FROM doc GROUP BY category ORDER BY 2 DESC").fetchall())

dmin = conn.execute(
    "SELECT category, tech_type, tech_minor, COUNT(*) FROM doc "
    "GROUP BY category, tech_type, tech_minor ORDER BY 1, 2, 4 DESC").fetchall()

countries = conn.execute(
    "SELECT country, COUNT(*) n FROM doc WHERE country IS NOT NULL AND country!='' "
    "GROUP BY country ORDER BY n DESC").fetchall()
country_rows = [{'c': c, 'n': n} for c, n in countries]
cum_total = sum(c['n'] for c in country_rows)
max_c = max(c['n'] for c in country_rows)

matrix = conn.execute(
    "SELECT country, category, COUNT(*) FROM doc "
    "WHERE country IS NOT NULL AND country!='' "
    "GROUP BY country, category").fetchall()
mx = {}
for c, d, n in matrix:
    mx.setdefault(c, {})[d] = n

# ---------- 收录范围与合规抽查（K-SYS-003，只读，不删改）----------
# 个人敏感信息正则：仅扫 title+meta_json，列命中项供人工复核。
import re as _re
_SENS = {
    '身份证号': _re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'),
    '手机号':   _re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
    '电子邮箱': _re.compile(r'[\w.\-]+@[\w.\-]+\.\w+'),
}
_sens_hits = {k: [] for k in _SENS}
for _t, _m in conn.execute("SELECT title, COALESCE(meta_json,'') FROM doc").fetchall():
    _s = ((_t or '') + ' ' + (_m or ''))
    for _k, _p in _SENS.items():
        for _mm in _p.finditer(_s):
            _val = _mm.group(0)
            # 邮箱：DOI/题名 @ 误判（含 DOI 前缀 10. 或期刊域名）标注为疑似非隐私
            _tag = ''
            if _k == '电子邮箱' and (_re.match(r'^10\.\d{4,}', _val) or '@j.' in _val or '@10.' in _val):
                _tag = '（DOI/题名@ 疑似误判）'
            _sens_hits[_k].append(((_t or '')[:60], _val[:48], _tag))
# 正向清单佐证：测井类服务合同 / 技术要求类文档（K-SYS-003 二.3 可入档）
_CONTRACT_KW = ['合同', 'contract', '服务', '任务书', '技术要求', '工作范围', 'scope of work', '采集服务', '业主要求']
_c_like = " OR ".join(["title LIKE ?" for _ in _CONTRACT_KW])
_contract_docs = conn.execute(
    "SELECT title, category, tech_type FROM doc WHERE " + _c_like,
    ["%" + k + "%" for k in _CONTRACT_KW]).fetchall()

# ---------- scope 轴（顶层：global / 国别）----------
scopes = [r[0] for r in conn.execute("SELECT scope, COUNT(*) FROM doc GROUP BY scope ORDER BY 2 DESC")]
scope_counts = dict(conn.execute("SELECT scope, COUNT(*) FROM doc GROUP BY scope ORDER BY 2 DESC").fetchall())
global_by_domain = dict(conn.execute(
    "SELECT category, COUNT(*) FROM doc WHERE scope='global' GROUP BY category ORDER BY 2 DESC").fetchall())
country_scope_rows = [{'c': c, 'n': n} for c, n in conn.execute(
    "SELECT country, COUNT(*) n FROM doc WHERE scope='国别' GROUP BY country ORDER BY n DESC").fetchall()]
mx_sc = {}
for c, d, n in conn.execute("SELECT country, category, COUNT(*) FROM doc WHERE scope='国别' GROUP BY country, category").fetchall():
    mx_sc.setdefault(c, {})[d] = n
sc_stack = [{'c': csr['c'], 'segs': [{'d': d, 'n': mx_sc.get(csr['c'], {}).get(d, 0)} for d in domains], 'total': csr['n']}
            for csr in country_scope_rows]
sc_stack_data = json.dumps(sc_stack, ensure_ascii=False)

# 领域配色（画图与图例统一）
DOM_COLORS = {'地质': '#4C9AFF', '测井方法': '#1F2A44', '通用知识': '#F2A33C', '录井': '#57C3A0'}
for d in domains:
    if d not in DOM_COLORS:
        DOM_COLORS[d] = '#9AA7B8'

# 堆叠数据：每个国别 = 各领域段（按 domains 顺序）
stack_rows = []
for c in country_rows:
    cc = mx.get(c['c'], {})
    stack_rows.append({'c': c['c'], 'segs': [{'d': d, 'n': cc.get(d, 0)} for d in domains], 'total': c['n']})

# ---------- 占位替换工具 ----------
def sub(t, **kw):
    for k, v in kw.items():
        t = t.replace('{' + k + '}', str(v))
    return t

# ============================================================
# 0) 静态堆叠 PNG（给说明文档内嵌）
# ============================================================
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
for cand in ['Microsoft YaHei', 'SimHei', 'SimSun']:
    try:
        font_manager.findfont(cand, fallback_to_default=False)
        plt.rcParams['font.sans-serif'] = [cand]
        break
    except Exception:
        continue
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(12, 6.2), dpi=140)
xs = list(range(len(stack_rows)))
bottoms = [0] * len(stack_rows)
for di, d in enumerate(domains):
    vals = [sr['segs'][di]['n'] for sr in stack_rows]
    ax.bar(xs, vals, bottom=bottoms, label=d, color=DOM_COLORS[d], width=0.64,
           edgecolor='white', linewidth=0.5)
    for i, v in enumerate(vals):
        if v:
            ax.text(i, bottoms[i] + v / 2, str(v), ha='center', va='center', fontsize=8, color='white')
    bottoms = [b + v for b, v in zip(bottoms, vals)]
ax.set_xticks(xs)
ax.set_xticklabels([sr['c'] for sr in stack_rows], rotation=40, ha='right', fontsize=9)
ax.set_ylabel('知识文档数（篇）', fontsize=11)
ax.set_title('测井知识库 · 国别 × 领域 知识数量堆叠图\n（有国别合计 %d 篇；另有 %d 篇为通用/专业方法类未标注国别）'
             % (cum_total, n_nocountry), fontsize=13, fontweight='bold', pad=14)
ax.set_ylim(0, max(bottoms) * 1.12 if bottoms else 1)
ax.legend(title='领域', fontsize=10, title_fontsize=10)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='y', color='#E6EAF0', lw=0.8)
plt.tight_layout()
png_path = os.path.join(OUT, 'country_stacked.png')
plt.savefig(png_path, bbox_inches='tight')
plt.close()
with open(png_path, 'rb') as f:
    png_b64 = base64.b64encode(f.read()).decode('ascii')
print('written country_stacked.png')

# ============================================================
# 1) 交互堆叠图 HTML
# ============================================================
stack_data = json.dumps(stack_rows, ensure_ascii=False)
dom_colors = json.dumps(DOM_COLORS, ensure_ascii=False)
domjs = json.dumps(domains, ensure_ascii=False)

stack_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>测井知识库 · 国别 × 领域 堆叠图（交互版）</title>
<style>
  html,body{margin:0;font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;background:#f6f8fb;color:#1f2a44;}
  .wrap{max-width:1100px;margin:0 auto;padding:24px;}
  h1{font-size:20px;margin:0 0 4px;}
  .sub{color:#5b6678;font-size:13px;margin-bottom:16px;}
  .ctrls{display:flex;align-items:center;gap:14px;margin-bottom:10px;font-size:13px;}
  .ctrls input[type=range]{width:220px;}
  .card{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:16px;overflow-x:auto;}
  svg{display:block;}
  .seg{cursor:pointer;transition:opacity .12s;}
  .seg:hover{opacity:.82;}
  .barlbl{font-size:10px;fill:#3a4760;}
  .vallbl{font-size:10px;fill:#1f2a44;text-anchor:middle;font-weight:600;}
  .axline{stroke:#cdd6e3;stroke-width:1;}
  .legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:#3a4760;cursor:pointer;}
  .legend span{user-select:none;}
  .legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px;}
  #tip{position:fixed;pointer-events:none;background:#1f2a44;color:#fff;font-size:12px;
       padding:8px 10px;border-radius:6px;opacity:0;transition:opacity .1s;z-index:10;line-height:1.6;}
  .leg{font-size:12px;color:#5b6678;margin-top:8px;}
</style>
</head>
<body>
<div class="wrap">
  <h1>测井知识库 · 国别 × 领域 知识数量堆叠图</h1>
  <div class="sub">本知识库是以测井专业为主的油气知识库。每根柱为一个国别，按 4 个领域堆叠；另有 {nc} 篇为通用/专业方法类未标注国别。共 {nctry} 个国别、有国别合计 {total} 篇。</div>
  <div class="ctrls">
    <label>缩放 <input id="zoom" type="range" min="0.6" max="2.4" step="0.05" value="1"/></label>
    <span id="zval">100%</span>
  </div>
  <div class="card"><div id="chart"></div></div>
  <div class="legend" id="legend"></div>
  <div class="leg">悬停柱段查看该国别该领域篇数；点击图例可隐藏/显示对应领域。</div>
</div>
<div id="tip"></div>
<script>
const DATA = {data};
const DOMAINS = {domjs};
const COLORS = {colors};
const hidden = {};
function drawLegend(){
  const el = document.getElementById('legend');
  el.innerHTML = DOMAINS.map(d=>'<span data-d="'+d+'"><i style="background:'+(hidden[d]?'#ccc':COLORS[d])+'"></i>'+d+'</span>').join('');
  el.querySelectorAll('span').forEach(sp=>sp.onclick=()=>{ const d=sp.dataset.d; hidden[d]=!hidden[d]; drawLegend(); render(); });
}
const baseW=980, baseH=470, padL=40, padR=20, padT=24, padB=120;
function maxTopNow(){
  let m=0;
  DATA.forEach(s=>{ let t=0; for(let i=0;i<DOMAINS.length;i++){ if(!hidden[DOMAINS[i]]) t+=s.segs[i].n; } if(t>m)m=t; });
  return m*1.10 || 1;
}
function render(){
  const zoom=parseFloat(document.getElementById('zoom').value);
  document.getElementById('zval').textContent=Math.round(zoom*100)+'%';
  const W=baseW*zoom, H=baseH, n=DATA.length;
  const plotW=W-padL-padR, plotH=H-padT-padB, gap=plotW/n, bw=gap*0.64;
  const maxTop=maxTopNow();
  const yScale=v=>padT+plotH*(1-v/maxTop);
  let svg='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';
  const ticks=5;
  for(let t=0;t<=ticks;t++){ const v=maxTop*t/ticks, y=yScale(v);
    svg+='<line class="axline" x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'"/>';
    svg+='<text class="barlbl" x="'+(padL-6)+'" y="'+(y+3)+'" text-anchor="end">'+Math.round(v)+'</text>'; }
  for(let i=0;i<n;i++){
    const s=DATA[i]; const x=padL+gap*i+(gap-bw)/2; let yb=0;
    for(let di=0;di<DOMAINS.length;di++){
      const d=DOMAINS[di], v=s.segs[di].n;
      if(hidden[d] || !v) continue;
      const yTop=padT+plotH*(1-(yb+v)/maxTop);
      const yBottom=padT+plotH*(1-yb/maxTop);
      svg+='<rect class="seg" x="'+x.toFixed(1)+'" y="'+yTop.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(yBottom-yTop).toFixed(1)+'" fill="'+COLORS[d]+'" data-i="'+i+'" data-di="'+di+'"></rect>';
      yb+=v;
    }
    const lx=padL+gap*i+gap/2;
    svg+='<text class="vallbl" x="'+lx.toFixed(1)+'" y="'+(yScale(yb)-5).toFixed(1)+'">'+yb+'</text>';
    svg+='<text class="barlbl" x="'+lx.toFixed(1)+'" y="'+(H-padB+14).toFixed(1)+'" text-anchor="end" transform="rotate(-40 '+lx.toFixed(1)+' '+(H-padB+14).toFixed(1)+')">'+s.c+'</text>';
  }
  svg+='</svg>';
  document.getElementById('chart').innerHTML=svg;
  const tip=document.getElementById('tip');
  document.querySelectorAll('.seg').forEach(b=>{
    b.addEventListener('mousemove',e=>{ const s=DATA[+b.dataset.i], d=DOMAINS[+b.dataset.di], v=s.segs[+b.dataset.di].n;
      tip.innerHTML='<b>'+s.c+' · '+d+'</b><br/>'+v+' 篇（该国别 '+s.total+' 篇）';
      tip.style.opacity=1; tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY+12)+'px'; });
    b.addEventListener('mouseleave',()=>tip.style.opacity=0);
  });
}
document.getElementById('zoom').addEventListener('input', render);
drawLegend(); render();
</script>
</body>
</html>"""
stack_html = sub(stack_html, data=stack_data, domjs=domjs, colors=dom_colors,
                 nc=n_nocountry, nctry=len(country_rows), total=cum_total)
with open(os.path.join(OUT, 'country_domain_stacked.html'), 'w', encoding='utf-8') as f:
    f.write(stack_html)
print('written country_domain_stacked.html')

# ============================================================
# 2) 国别 × 领域 交叉分布表
# ============================================================
rows_js = []
for c in country_rows:
    cc = mx.get(c['c'], {})
    tot = sum(cc.values())
    rows_js.append({'c': c['c'], 'total': tot, 'cells': [cc.get(d, 0) for d in domains]})
heads = ''.join('<th data-k="%d">%s</th>' % (i, d) for i, d in enumerate(domains))
matrix_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>测井知识库 · 国别 × 领域 交叉分布</title>
<style>
  html,body{margin:0;font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;background:#f6f8fb;color:#1f2a44;}
  .wrap{max-width:920px;margin:0 auto;padding:24px;}
  h1{font-size:20px;margin:0 0 4px;}
  .sub{color:#5b6678;font-size:13px;margin-bottom:14px;}
  table{border-collapse:collapse;background:#fff;width:100%;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,.06);}
  th,td{border:1px solid #e6eaf0;padding:7px 10px;text-align:right;}
  th{background:#1f2a44;color:#fff;cursor:pointer;user-select:none;position:relative;}
  th:hover{background:#2c3a5c;}
  th.sorted::after{content:" \\25B2";font-size:9px;}
  th.sorted.desc::after{content:" \\25BC";}
  td.country{text-align:left;font-weight:600;background:#fafbfe;}
  tr:hover td{background:#eef4ff;}
  tfoot td{font-weight:700;background:#f0f3f9;border-top:2px solid #cdd6e3;}
  .legend{font-size:12px;color:#5b6678;margin-top:10px;}
</style>
</head>
<body>
<div class="wrap">
  <h1>测井知识库 · 国别 × 领域 交叉分布</h1>
  <div class="sub">仅统计带国别标注的 {ncountry} 篇文档（共 {total} 篇，另 {nrest} 篇为通用/专业方法类未标国别）。点击表头排序。</div>
  <table id="t">
    <thead><tr><th data-k="country" class="country">国别</th>
    {heads}
    <th data-k="total">合计</th></tr></thead>
    <tbody></tbody>
    <tfoot></tfoot>
  </table>
  <div class="legend">领域：{domleg}</div>
</div>
<script>
const DOMAINS = {domjs};
const ROWS = {rows};
const tbody = document.querySelector('#t tbody');
const tfoot = document.querySelector('#t tfoot');
let sortKey='total', desc=true;
function draw(){
  const arr=[].concat(ROWS).sort(function(a,b){
    let x,y;
    if(sortKey==='country'){x=a.c;y=b.c;return desc?y.localeCompare(x,'zh'):x.localeCompare(y,'zh');}
    x = sortKey==='total'?a.total:a.cells[sortKey];
    y = sortKey==='total'?b.total:b.cells[sortKey];
    return desc? y-x : x-y;
  });
  tbody.innerHTML = arr.map(function(r){
    return '<tr><td class="country">'+r.c+'</td>'+
      r.cells.map(function(v){return '<td>'+(v||'')+'</td>';}).join('')+
      '<td>'+r.total+'</td></tr>';
  }).join('');
  const foot=['合计'];
  DOMAINS.forEach(function(d,i){ foot.push(ROWS.reduce(function(s,r){return s+r.cells[i];},0)); });
  foot.push(ROWS.reduce(function(s,r){return s+r.total;},0));
  tfoot.innerHTML='<tr><td class="country">'+foot[0]+'</td>'+foot.slice(1).map(function(v){return '<td>'+v+'</td>';}).join('')+'</tr>';
  document.querySelectorAll('th').forEach(function(th){th.classList.remove('sorted','desc');});
  const th=document.querySelector('th[data-k="'+sortKey+'"]'); th.classList.add('sorted'); if(desc) th.classList.add('desc');
}
document.querySelectorAll('th').forEach(function(th){th.addEventListener('click',function(){
  const k=th.dataset.k;
  if(sortKey===k) desc=!desc; else {sortKey=k; desc=true;}
  draw();
});});
draw();
</script>
</body>
</html>"""
matrix_html = sub(matrix_html, ncountry=n_country, total=total, nrest=n_nocountry,
                  heads=heads, domleg=' · '.join(domains), domjs=domjs, rows=json.dumps(rows_js, ensure_ascii=False))
with open(os.path.join(OUT, 'country_domain_matrix.html'), 'w', encoding='utf-8') as f:
    f.write(matrix_html)
print('written country_domain_matrix.html')

# ============================================================
# 2.5) scope 顶层（global / 国别）概览
# ============================================================
g_n = scope_counts.get('global', 0)
c_n = scope_counts.get('国别', 0)
# global 下 4 域横向条
gdom_bars = ''.join(
    '<div class="barrow"><span class="blab">%s</span><div class="btrack"><div class="bfill" style="width:%.1f%%;background:%s"></div></div><span class="bval">%d</span></div>'
    % (d, 100.0 * global_by_domain.get(d, 0) / max(g_n, 1), DOM_COLORS.get(d, '#9AA7B8'), global_by_domain.get(d, 0))
    for d in domains if global_by_domain.get(d, 0))
ccountry_rows = ''.join('<tr><td class="country">%s</td><td style="text-align:right">%d</td></tr>' % (r['c'], r['n']) for r in country_scope_rows)

scope_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>测井知识库 · 顶层分类（global / 国别）概览</title>
<style>
  html,body{margin:0;font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;background:#f6f8fb;color:#1f2a44;line-height:1.6;}
  .wrap{max-width:1080px;margin:0 auto;padding:28px 36px 56px;}
  h1{font-size:22px;border-bottom:3px solid #4c9aff;padding-bottom:8px;}
  h2{font-size:17px;margin-top:26px;}
  .kpi{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0;}
  .kpi div{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:14px 20px;min-width:140px;}
  .kpi b{font-size:24px;display:block;}
  .kpi .g{color:#4c9aff;} .kpi .c{color:#57C3A0;}
  .kpi span{font-size:12px;color:#5b6678;}
  .panel{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:16px 18px;margin-top:10px;}
  .barrow{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px;}
  .blab{width:84px;text-align:right;color:#3a4760;}
  .btrack{flex:1;background:#eef2f7;border-radius:6px;height:16px;overflow:hidden;}
  .bfill{height:100%;border-radius:6px;}
  .bval{width:42px;text-align:right;font-weight:600;}
  table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px;}
  th,td{border:1px solid #e6eaf0;padding:6px 10px;text-align:left;}
  th{background:#1f2a44;color:#fff;}
  td.country{font-weight:600;background:#fafbfe;}
  .note{background:#fff7e6;border:1px solid #ffe2a8;padding:10px 14px;border-radius:8px;font-size:13px;color:#7a5b00;margin:10px 0;}
  .legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:#3a4760;cursor:pointer;}
  .legend span{user-select:none;}
  .legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px;}
  .card{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:16px;overflow-x:auto;margin-top:10px;}
  svg{display:block;}
  .seg{cursor:pointer;transition:opacity .12s;} .seg:hover{opacity:.82;}
  .barlbl{font-size:10px;fill:#3a4760;} .vallbl{font-size:10px;fill:#1f2a44;text-anchor:middle;font-weight:600;}
  .axline{stroke:#cdd6e3;stroke-width:1;}
  #tip{position:fixed;pointer-events:none;background:#1f2a44;color:#fff;font-size:12px;padding:8px 10px;border-radius:6px;opacity:0;transition:opacity .1s;z-index:10;line-height:1.6;}
</style>
</head>
<body>
<div class="wrap">
  <h1>测井知识库 · 顶层分类（global / 国别）概览</h1>
  <div class="note">知识库按<b>适用范围(scope)</b>分两类：<b>global</b>=普适/专业方法类知识（不绑定特定国家）；<b>国别</b>=区域专属知识（区域地质·区域规范·区域公式及参数·区域阈值·区域曲线特征，由 country 标注）。两路下再按「领域 → 大类 → 小类」细分。</div>
  <div class="kpi">
    <div><b class="g">{g}</b><span>global（普适知识）</span></div>
    <div><b class="c">{c}</b><span>国别（区域专属，{ncs} 国）</span></div>
    <div><b>{total}</b><span>知识文档总数</span></div>
  </div>

  <h2>一、global 下按领域细分</h2>
  <div class="panel">{gdom}</div>

  <h2>二、国别 下按国家细分</h2>
  <div class="panel"><table><thead><tr><th>国别</th><th style="text-align:right">篇数</th></tr></thead><tbody>{ccountry}</tbody></table></div>

  <h2>三、国别 × 领域 堆叠图（下钻细分）</h2>
  <div class="card"><div id="chart"></div></div>
  <div class="legend" id="legend"></div>
  <div class="note" style="background:#eef4ff;border-color:#cfe0ff;color:#27406b;">悬停柱段查看该国别该领域篇数；点击图例可隐藏/显示对应领域。交互堆叠图原始数据同 <a href="country_domain_stacked.html">country_domain_stacked.html</a>。</div>
</div>
<div id="tip"></div>
<script>
const DATA = {scdata};
const DOMAINS = {domjs};
const COLORS = {colors};
const hidden = {};
function drawLegend(){
  const el=document.getElementById('legend');
  el.innerHTML=DOMAINS.map(d=>'<span data-d="'+d+'"><i style="background:'+(hidden[d]?'#ccc':COLORS[d])+'"></i>'+d+'</span>').join('');
  el.querySelectorAll('span').forEach(sp=>sp.onclick=()=>{const d=sp.dataset.d;hidden[d]=!hidden[d];drawLegend();render();});
}
const baseW=980,baseH=470,padL=40,padR=20,padT=24,padB=120;
function maxTopNow(){let m=0;DATA.forEach(s=>{let t=0;for(let i=0;i<DOMAINS.length;i++){if(!hidden[DOMAINS[i]])t+=s.segs[i].n;}if(t>m)m=t;}return m*1.10||1;});
function render(){
  const zoom=1,W=baseW*zoom,H=baseH,n=DATA.length;
  const plotW=W-padL-padR,plotH=H-padT-padB,gap=plotW/n,bw=gap*0.64,maxTop=maxTopNow();
  const yScale=v=>padT+plotH*(1-v/maxTop);
  let svg='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';
  for(let t=0;t<=5;t++){const v=maxTop*t/5,y=yScale(v);svg+='<line class="axline" x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'"/>';svg+='<text class="barlbl" x="'+(padL-6)+'" y="'+(y+3)+'" text-anchor="end">'+Math.round(v)+'</text>';}
  for(let i=0;i<n;i++){const s=DATA[i],x=padL+gap*i+(gap-bw)/2;let yb=0;
    for(let di=0;di<DOMAINS.length;di++){const d=DOMAINS[di],v=s.segs[di].n;if(hidden[d]||!v)continue;
      const yT=padT+plotH*(1-(yb+v)/maxTop),yB=padT+plotH*(1-yb/maxTop);
      svg+='<rect class="seg" x="'+x.toFixed(1)+'" y="'+yT.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(yB-yT).toFixed(1)+'" fill="'+COLORS[d]+'" data-i="'+i+'" data-di="'+di+'"></rect>';yb+=v;}
    const lx=padL+gap*i+gap/2;svg+='<text class="vallbl" x="'+lx.toFixed(1)+'" y="'+(yScale(yb)-5).toFixed(1)+'">'+yb+'</text>';
    svg+='<text class="barlbl" x="'+lx.toFixed(1)+'" y="'+(H-padB+14).toFixed(1)+'" text-anchor="end" transform="rotate(-40 '+lx.toFixed(1)+' '+(H-padB+14).toFixed(1)+')">'+s.c+'</text>';}
  svg+='</svg>';document.getElementById('chart').innerHTML=svg;
  const tip=document.getElementById('tip');
  document.querySelectorAll('.seg').forEach(b=>{b.addEventListener('mousemove',e=>{const s=DATA[+b.dataset.i],d=DOMAINS[+b.dataset.di],v=s.segs[+b.dataset.di].n;tip.innerHTML='<b>'+s.c+' · '+d+'</b><br/>'+v+' 篇（该国别 '+s.total+' 篇）';tip.style.opacity=1;tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';});b.addEventListener('mouseleave',()=>tip.style.opacity=0);});
}
drawLegend();render();
</script>
</body>
</html>"""
scope_html = sub(scope_html, g=g_n, c=c_n, ncs=len(country_scope_rows), total=total,
                 gdom=gdom_bars, ccountry=ccountry_rows, scdata=sc_stack_data, domjs=domjs, colors=dom_colors)
with open(os.path.join(OUT, 'scope_overview.html'), 'w', encoding='utf-8') as f:
    f.write(scope_html)
print('written scope_overview.html')

# 供分类说明文档复用的 scope 段
scope_kpi = ('<div><b class="g">%d</b><span>global（普适知识）</span></div>'
             '<div><b class="c">%d</b><span>国别（区域专属，%d 国）</span></div>'
             '<div><b>%d</b><span>知识文档总数</span></div>') % (g_n, c_n, len(country_scope_rows), total)
scope_section = (
    '<h2>〇、顶层分类（global / 国别）</h2>'
    '<div class="kpi">%s</div>'
    '<p>知识库按<b>适用范围(scope)</b>分两类：<b>global</b>（普适/专业方法类知识，不绑定特定国家）与 <b>国别</b>（区域专属知识：区域地质、区域规范、区域公式及参数、区域阈值、区域曲线特征，由 country 标注）。两路下再按「领域 → 大类(tech_type) → 小类(tech_minor)」细分（详见后文）。</p>'
    '<h3>global 下按领域细分</h3><div class="panel">%s</div>'
    '<h3>国别 下按国家细分（共 %d 国）</h3><div class="panel"><table><thead><tr><th>国别</th><th style="text-align:right">篇数</th></tr></thead><tbody>%s</tbody></table></div>'
    '<p style="font-size:13px;color:#5b6678;">国别 × 领域 堆叠交互图见 <a href="scope_overview.html">scope_overview.html</a>；国别明细交叉表见 <a href="country_domain_matrix.html">country_domain_matrix.html</a>。</p>'
) % (scope_kpi, gdom_bars, len(country_scope_rows), ccountry_rows)

# ============================================================
# 3) 分类说明文档
# ============================================================
from collections import defaultdict
tree = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
for cat, maj, minr, n in dmin:
    tree[cat][maj][minr] += n

doc_sections = []
for cat in domains:
    rows_t = []
    for maj, minors in sorted(tree[cat].items(), key=lambda kv: -sum(kv[1].values())):
        msum = sum(minors.values())
        minor_str = '、'.join('%s %d' % (m, v) for m, v in sorted(minors.items(), key=lambda kv: -kv[1])) if any(minors.values()) else '—'
        rows_t.append('<tr><td>%s</td><td style="text-align:right">%d</td><td>%s</td></tr>' % (maj, msum, minor_str))
    doc_sections.append(
        '<h3>%s（%d 篇）</h3><table><thead><tr><th>大类（tech_type）</th><th>篇数</th><th>小类（tech_minor）细分</th></tr></thead><tbody>%s</tbody></table>'
        % (cat, domain_counts.get(cat, 0), ''.join(rows_t)))

domain_desc = {
    '测井方法': '测井专业技术/方法知识，含电缆测井、随钻测井、生产测井、裸眼测井、光纤、射孔、解释方法等，按技术类型（大类）× 厂商来源（小类）二级细分。',
    '录井': '录井专业知识（综合/气测/地化/岩屑/钻井液录井等），与测井方法并列的一级领域。',
    '地质': '以油气地质为主的地质知识，含油气地质、非常规地质、基础地质（构造·沉积·岩性），按大类×技术细分小类。',
    '通用知识': '属于油气通用、但不属于测井专业的知识，含标准规范、项目管理、软件工具、其他。',
}
doc_intro = ''.join('<li><b>%s</b>：%s</li>' % (d, domain_desc.get(d, '')) for d in domains)

def build_matrix_top(domains, rows_js, topn=12):
    head = ''.join('<th>%s</th>' % d for d in domains)
    body = ''.join(
        '<tr><td class="country">%s</td>' % r['c'] +
        ''.join('<td style="text-align:right">%s</td>' % (v or '') for v in r['cells']) +
        '<td style="text-align:right"><b>%d</b></td></tr>' % r['total']
        for r in rows_js[:topn])
    foot = '<tr><td><b>合计</b></td>' + ''.join(
        '<td style="text-align:right"><b>%d</b></td>' % sum(r['cells'][i] for r in rows_js) for i in range(len(domains))) + \
        '<td style="text-align:right"><b>%d</b></td></tr>' % sum(r['total'] for r in rows_js)
    return '<table><thead><tr><th>国别</th>%s<th>合计</th></tr></thead><tbody>%s</tbody><tfoot>%s</tfoot></table>' % (head, body, foot)

matrix_top = build_matrix_top(domains, rows_js)

doc_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>测井知识库 · 分类体系说明</title>
<style>
  html,body{margin:0;font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;background:#f6f8fb;color:#1f2a44;line-height:1.65;}
  .wrap{max-width:1080px;margin:0 auto;padding:32px 40px 60px;}
  h1{font-size:24px;border-bottom:3px solid #4c9aff;padding-bottom:8px;}
  h2{font-size:18px;margin-top:30px;color:#1f2a44;}
  h3{font-size:15px;margin:18px 0 6px;color:#2c3a5c;background:#eef4ff;padding:6px 10px;border-radius:6px;}
  table{border-collapse:collapse;background:#fff;width:100%;font-size:13px;margin:6px 0 6px;box-shadow:0 1px 3px rgba(0,0,0,.06);}
  th,td{border:1px solid #e6eaf0;padding:6px 10px;text-align:left;}
  th{background:#1f2a44;color:#fff;}
  ul{font-size:14px;}
  .note{background:#fff7e6;border:1px solid #ffe2a8;padding:10px 14px;border-radius:8px;font-size:13px;color:#7a5b00;}
  .imgbox{text-align:center;margin:14px 0;}
  .imgbox img{max-width:100%;border:1px solid #e6eaf0;border-radius:8px;background:#fff;}
  .kpi{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0;}
  .kpi div{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:12px 18px;min-width:120px;}
  .kpi b{font-size:22px;color:#4c9aff;display:block;}
  .kpi span{font-size:12px;color:#5b6678;}
  a{color:#4c9aff;}
  td.country{text-align:left;font-weight:600;background:#fafbfe;}
</style>
</head>
<body>
<div class="wrap">
  <h1>测井知识库 · 分类体系说明</h1>
  <div class="note">本知识库定位：<b>以测井专业为主的油气知识库</b>。知识先按<b>适用范围(scope)</b>分两层——<b>global</b>（普适/专业方法类）与 <b>国别</b>（区域专属：区域地质·规范·公式参数·阈值·曲线特征）；两路下再按「领域 → 大类(tech_type) → 小类(tech_minor)」三级细分。国别由 country 列承载。</div>
  <div class="kpi">
    <div><b>{total}</b><span>知识文档总数</span></div>
    <div><b>{ncountry}</b><span>带国别标注</span></div>
    <div><b>{nrest}</b><span>未标国别（通用/方法）</span></div>
    <div><b>{ndom}</b><span>一级领域</span></div>
  </div>
  {scope_section}
  <h2>一、一级领域</h2>
  <ul>{intro}</ul>
  <h2>二、各级领域分类明细</h2>
  {sections}
  <h2>三、国别 × 领域 知识数量堆叠图</h2>
  <div class="imgbox"><img src="data:image/png;base64,{png}" alt="国别×领域堆叠图"/></div>
  <p style="font-size:13px;color:#5b6678;">有国别知识累计 {cumtotal} 篇，分布于 {ncountries} 个国别；单一国别最多 {maxc} 篇。交互版（可悬停看各国别各领域明细、点击图例切换领域）见 <a href="country_domain_stacked.html">country_domain_stacked.html</a>。</p>
  <h2>四、国别 × 领域 交叉分布</h2>
  <p style="font-size:13px;color:#5b6678;">完整可排序表见 <a href="country_domain_matrix.html">country_domain_matrix.html</a>。下表为前 12 国别概览：</p>
  {matrix_top}
  <h2>五、分类规则要点</h2>
  <ul>
    <li><b>领域判定优先级</b>：通用内容型（标准规范/项目管理/软件工具）&gt; 录井 &gt; 地质 &gt; 测井方法 &gt; 通用行政 &gt; 兜底其他。确保课题/软件/标准不误归技术方法。</li>
    <li><b>标准规范仅跨专业归通用</b>：某项测井/地质/录井专业技术规范，回退到对应技术域；仅真正跨专业的通用规范留通用。</li>
    <li><b>厂商小类</b>：测井方法下按来源细分 SLB / 贝克休斯 / 哈里伯顿 / CNLC / 中海油；缺来源归“其他”。</li>
    <li><b>国别归一</b>：孟加拉→孟加拉国、阿拉伯联合酋长国等别名已归一；国别由 detect_country 自动推导，不影响领域分类。</li>
    <li><b>新增文档自动分类</b>：入库脚本（md/docx/pdf/pptx）统一调用 classify_knowledge，落库即带 领域/大类/小类/国别。</li>
  </ul>
  <h2>六、收录范围与合规准则（K-SYS-003）</h2>
  <div class="note" style="background:#eef7f0;border-color:#c8e6d0;color:#1f5c33;">
    本库是<b>以测井专业知识为主的油气知识库</b>，收录<b>按内容实质判定，不按文件名/文种/字样一刀切</b>。
    合规抽查为<b>只读</b>（不自动删改数据），命中项人工复核后处置。详见 <a href="收录合规报告.html">收录合规报告.html</a>。
  </div>
  <h3>可入档（正向）</h3>
  <ul>
    <li>测井专业技术（方法/仪器/采集/处理/解释/规范/专业软件）、油气地质、录井、跨专业通用知识。</li>
    <li><b>测井类服务合同及技术附件</b>：研究的要求、采集服务的项目及要求、体现一定时期业主关注点与期望结果 —— 属需求侧/期望侧的专业史料，<b>可入档</b>，按内容实质归类（通用-项目管理或相应技术域），不因「合同」字样贬为行政杂项或排除。</li>
  </ul>
  <h3>排除 / 脱敏（负向）</h3>
  <ul>
    <li><b>个人隐私</b>：身份证号、私人手机/邮箱/住址、签字人身份、个人证件影像。</li>
    <li><b>纯行政流程</b>：人事任免、考勤、内部通知流转、与专业无关的红头/会务。</li>
    <li><b>纯商务敏感</b>：金额/报价/付款账户/税务/法律责任与争议、商业保密条款；<b>依法禁止</b>：国家秘密、涉密测绘等。</li>
    <li>可分离者只入技术部分或脱敏后入；无法分离且以敏感内容为主体者整篇不入库。</li>
  </ul>
  <h3>合规抽查基线（本次扫描）</h3>
  <ul>{compliance_brief}</ul>
</div>
</body>
</html>"""
compliance_brief = ''.join(
    '<li><b>%s</b>：命中 %d 项%s</li>' % (
        k, len(v),
        '（均为 DOI/题名@ 误判，非个人隐私）' if k == '电子邮箱' and v and all(x[2] for x in v) else '')
    for k, v in _sens_hits.items())
doc_html = sub(doc_html, total=total, ncountry=n_country, nrest=n_nocountry, ndom=len(domains),
              intro=doc_intro, sections=''.join(doc_sections), png=png_b64,
              cumtotal=cum_total, ncountries=len(country_rows), maxc=max_c, matrix_top=matrix_top,
              scope_section=scope_section, compliance_brief=compliance_brief)
with open(os.path.join(OUT, '分类说明文档.html'), 'w', encoding='utf-8') as f:
    f.write(doc_html)
print('written 分类说明文档.html')

# ============================================================
# 5) 收录合规报告（K-SYS-003，只读抽查结果）
# ============================================================
def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

sens_rows = []
for k, hits in _sens_hits.items():
    if not hits:
        sens_rows.append('<tr><td><b>%s</b></td><td style="color:#1f5c33;">0</td><td>—</td></tr>' % k)
    else:
        sample = '；'.join('%s <span style="color:#888;">[%s]%s</span>' % (_esc(t), _esc(v), _esc(tag))
                          for t, v, tag in hits[:15])
        more = ' …（共 %d 项）' % len(hits) if len(hits) > 15 else ''
        sens_rows.append('<tr><td><b>%s</b></td><td>%d</td><td style="font-size:12px;">%s%s</td></tr>'
                         % (k, len(hits), sample, more))

contract_rows = ''.join(
    '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (_esc(t), _esc(cat), _esc(tt))
    for t, cat, tt in _contract_docs[:60]) or '<tr><td colspan="3" style="color:#888;">（无）</td></tr>'
contract_more = ('<p style="font-size:12px;color:#888;">仅列前 60 篇，共 %d 篇。</p>' % len(_contract_docs)) if len(_contract_docs) > 60 else ''

compliance_html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>测井知识库 · 收录合规报告</title>
<style>
body{font-family:"Microsoft YaHei",Arial,sans-serif;background:#f5f7fb;color:#22304a;margin:0;padding:24px;}
.wrap{max-width:1000px;margin:0 auto;background:#fff;border-radius:12px;padding:28px 34px;box-shadow:0 2px 10px rgba(0,0,0,.06);}
h1{font-size:22px;margin:0 0 4px;} h2{font-size:17px;margin-top:26px;color:#1f2a44;border-left:4px solid #4c9aff;padding-left:10px;}
.note{background:#eef7f0;border:1px solid #c8e6d0;padding:10px 14px;border-radius:8px;font-size:13px;color:#1f5c33;margin:10px 0;}
table{border-collapse:collapse;background:#fff;width:100%;font-size:13px;margin:8px 0;box-shadow:0 1px 3px rgba(0,0,0,.06);}
th,td{border:1px solid #e6eaf0;padding:6px 10px;text-align:left;vertical-align:top;}
th{background:#1f2a44;color:#fff;} ul{font-size:14px;line-height:1.9;}
.kpi{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0;}
.kpi div{background:#fff;border:1px solid #e6eaf0;border-radius:10px;padding:12px 18px;min-width:130px;}
.kpi b{font-size:22px;color:#4c9aff;display:block;} .kpi span{font-size:12px;color:#5b6678;}
a{color:#4c9aff;}
</style></head><body><div class="wrap">
<h1>测井知识库 · 收录合规报告</h1>
<div style="font-size:13px;color:#888;">依据 K-SYS-003 收录范围与合规准则 · 只读抽查，不删改任何数据</div>
<div class="note">本库 = <b>以测井专业知识为主的油气知识库</b>。收录按内容实质判定；合规红线=个人隐私/纯行政流程/纯商务敏感/依法禁止内容。
<b>测井类服务合同可入档</b>（研究要求、采集服务项目及要求、业主关注点与期望结果=需求侧专业史料）。</div>
<div class="kpi">
  <div><b>{TOTAL}</b><span>扫描文档数</span></div>
  <div><b>{ID}</b><span>身份证号命中</span></div>
  <div><b>{PHONE}</b><span>手机号命中</span></div>
  <div><b>{EMAIL}</b><span>电子邮箱命中</span></div>
  <div><b>{CONTRACT}</b><span>服务合同/技术要求类</span></div>
</div>
<h2>一、个人敏感信息扫描（doc.title + meta_json）</h2>
<table><tr><th style="width:120px;">模式</th><th style="width:70px;">命中数</th><th>命中项（标题 [值] 标注，最多 15 项）</th></tr>
{SENS_ROWS}</table>
<p style="font-size:12px;color:#888;">电子邮箱命中多为文献 DOI / 题名中的 <code>@</code>（如 <code>10.1016@j.jappgeo…</code>）误判，非个人隐私；所有命中项均需人工复核后再按准则处置。抽查为只读，不自动删除。</p>
<h2>二、可入档正向清单佐证：测井类服务合同 / 技术要求文档</h2>
<p style="font-size:13px;color:#5b6678;">命中标题含 合同/服务/任务书/技术要求/工作范围/采集服务/业主要求 的文档，按 K-SYS-003 二.3 属可入档范围（按其技术内容归类）。</p>
<table><tr><th>标题</th><th style="width:110px;">领域</th><th style="width:110px;">大类</th></tr>
{CONTRACT_ROWS}</table>
{CONTRACT_MORE}
<h2>三、准则摘要</h2>
<ul>
  <li><b>准入从宽、隐私从严</b>：技术/需求类内容尽量收录；个人敏感信息一项命中即须脱敏或排除。</li>
  <li><b>不按字样一刀切</b>：「合同/招标/协议/要求」不是排除理由；「研究报告」字样也不豁免隐私检查。</li>
  <li><b>排除需有证据</b>：能指出具体敏感要素，不凭文件名猜测；可分离者只入技术部分。</li>
  <li><b>合规操作以只读抽查为主</b>：不自动删改数据，命中项人工复核后处置。</li>
</ul>
<p style="font-size:13px;color:#888;">返回 <a href="分类说明文档.html">分类体系说明</a> · 知识条目正本 <code>knowledge/entries/K-SYS-003_收录范围与合规准则.md</code></p>
</div></body></html>"""
compliance_html = sub(compliance_html,
                      TOTAL=total, ID=len(_sens_hits['身份证号']), PHONE=len(_sens_hits['手机号']),
                      EMAIL=len(_sens_hits['电子邮箱']), CONTRACT=len(_contract_docs),
                      SENS_ROWS=''.join(sens_rows), CONTRACT_ROWS=contract_rows, CONTRACT_MORE=contract_more)
with open(os.path.join(OUT, '收录合规报告.html'), 'w', encoding='utf-8') as f:
    f.write(compliance_html)
print('written 收录合规报告.html')
print('DONE. total=%d country=%d nocountry=%d domains=%s' % (total, n_country, n_nocountry, domains))
