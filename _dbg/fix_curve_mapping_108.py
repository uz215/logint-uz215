# -*- coding: utf-8 -*-
"""修复 1-SPS-108 全泥岩根因之一：真实曲线因命名不在白名单被识别器忽略。
- GR_EDTC(校正后GR, 本井真实值中位87) 未映射到 GR -> 识别器 GR=None
- NPOR(本井中子/孔隙, 中位0.1) 未映射到 CNL -> 识别器 CNL=None
同时把 curve_aliases 里已有的中子别名(NPOR/NPH/NEU/NEUT 等)补进 CNL 归一化与候选表。
仅改映射白名单，不动任何判据阈值。CRLF 保真。
"""
import io

P = r"F:/360/src/logInt.py"
raw = open(P, "rb").read().decode("utf-8")
text = raw.replace("\r\n", "\n")  # 统一处理, 最后再还原 CRLF

repls = [
    # COL_CANDIDATES['GR'] 增加 GR_EDTC
    ("    'GR':   ['GR_LAS', 'GR', 'GRX', 'GR_XMAC'],",
     "    'GR':   ['GR_LAS', 'GR', 'GRX', 'GR_XMAC', 'GR_EDTC'],"),
    # COL_CANDIDATES['CNL'] 增加 NPOR 及 curve_aliases 中子别名
    ("    'CNL':  ['CNL_LAS', 'CNL', 'CNCF', 'NPHI', 'CNC'],",
     "    'CNL':  ['CNL_LAS', 'CNL', 'CNCF', 'NPHI', 'CNC', 'NPOR', 'NPH', 'NEU',\n"
     "              'NEUT', 'PHIN', 'TNPH', 'PHI_N', 'NEUTRON', 'PORN'],"),
    # CURVE_NAME_ALIASES['GR'] 增加 GR_EDTC
    ("    'GR':  ['GR_XMAC', 'GRGC', 'GRTO', 'GRAP'],",
     "    'GR':  ['GR_XMAC', 'GRGC', 'GRTO', 'GRAP', 'GR_EDTC'],"),
    # CURVE_NAME_ALIASES['CNL'] 增加中子别名
    ("    'CNL': ['CNCF', 'CNC', 'CN', 'TNPH', 'NPHI', 'PHIN'],",
     "    'CNL': ['CNCF', 'CNC', 'CN', 'TNPH', 'NPHI', 'PHIN', 'NPOR', 'NPH',\n"
     "            'NEU', 'NEUT', 'PHI_N', 'NEUTRON', 'PORN'],"),
]

for old, new in repls:
    assert text.count(old) == 1, "锚点未唯一命中: %r (count=%d)" % (old, text.count(old))
    text = text.replace(old, new)

out = text.replace("\n", "\r\n")
open(P, "wb").write(out.encode("utf-8"))
print("OK: 4 处曲线映射白名单已更新 (GR_EDTC->GR, NPOR/中子别名->CNL)")
