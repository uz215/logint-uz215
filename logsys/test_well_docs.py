# -*- coding: utf-8 -*-
"""well_docs 模块自检：地质设计 + masterlog 读取（RP-13 样例）。"""
import os, sys, json
sys.path.insert(0, r'D:\360\src')
from logsys.well_docs import build_context, read_design, read_masterlog, load_context

WELL = r'D:\360\Bangladesh\RP-13'
OUT = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace\output\RASHIDPUR_13'
ok = 0; fail = 0
def chk(name, cond, detail=''):
    global ok, fail
    if cond:
        ok += 1; print('  PASS ', name)
    else:
        fail += 1; print('  FAIL ', name, detail)

ctx = build_context(WELL, out_dir=OUT, use_cache=False, well_name='RASHIDPUR_13')
d = ctx.get('design') or {}
m = ctx.get('masterlog') or {}
chk('上下文文件', os.path.exists(os.path.join(OUT, 'RASHIDPUR_13_well_context.json')))
chk('设计井段 2900-4200', bool(d.get('interval')) and abs(d['interval']['top'] - 2900) < 1 and abs(d['interval']['bottom'] - 4200) < 1, str(d.get('interval')))
chk('套管程序 8½', any('8½' in str(c.get('size_in')) for c in (d.get('casing') or [])))
chk('预测地层序列', len(d.get('formation_names') or []) >= 4, str([x.get('name') for x in d.get('formation_names') or []]))
chk('masterlog 岩性层', (m.get('lith_layers') or 0) >= 5, str(m.get('lith_layers')))
chk('masterlog 气测井段', (m.get('gas_zones') or 0) >= 5, str(m.get('gas_zones')))
chk('缓存读取', bool(load_context(OUT, 'RASHIDPUR_13').get('design')))

# info.json 单配置：同步后可读可改（三个分区 + 目标井段 + 图例）
from logsys.well_docs import sync_info_json
_syn = sync_info_json(WELL, ctx, out_dir=OUT, well_name='RASHIDPUR_13')
_inf = json.load(open(_syn['path'], encoding='utf-8'))
chk('info.json 同步', _syn.get('updated'))
for _k in ('地质设计', '录井图', '甲方格式'):
    chk('info 分区: ' + _k, isinstance(_inf.get(_k), dict))
chk('info 目标井段', bool((_inf.get('地质设计') or {}).get('目标井段')))
chk('info 录井图头', bool((_inf.get('录井图') or {}).get('图头', {}).get('作业公司')))
chk('info 甲方图例', len((_inf.get('甲方格式') or {}).get('图例') or []) >= 4)

print('\n结果: %d 通过, %d 失败' % (ok, fail))
sys.exit(0 if fail == 0 else 1)
